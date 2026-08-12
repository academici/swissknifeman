"""Hard admission gates for executable-plan layout v2.

The gate deliberately delegates all measurement and timing decisions: ``plan_weight``
owns the mandatory-read graph and its one weight, while ``plan_admission`` owns the
``historical``/``pending``/``ready`` state machine.  This module only turns a failed
ready D2 result into actionable plan-lint diagnostics.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from task import (plan_bundle, plan_decisions, plan_downstream, plan_gate_activation, plan_item_state, plan_layout,
                  plan_projection, plan_requests, plan_returns, plan_status, plan_weight)


GATE_ID = "read-budget-v1"
BUNDLE_GATE_ID = "bundle-v1"
PATH_GATE_ID = "read-path-v1"
RETURN_LOOP_GATE_ID = "return-loop-v1"
DECISION_QUEUE_GATE_ID = "decision-queue-v1"
_FILES_FIELD_RE = re.compile(r"^\*\*Files:\*\*\s*(.*)$")
_BACKTICK_PATH_RE = re.compile(r"`([^`]+)`")


def baseline_delta(*, current_failures, baseline_failures, owned_failures=()):
    """Classify inherited red without letting unrelated baseline failures gate work."""
    current = set(current_failures)
    baseline = set(baseline_failures)
    owned = set(owned_failures)
    introduced = current - baseline
    return {
        "introduced": tuple(sorted(introduced)),
        "owned_regressions": tuple(sorted(introduced & owned if owned else introduced)),
        "pre_existing": tuple(sorted(current & baseline)),
        "blocks": bool(introduced & owned if owned else introduced),
    }


def _declared_file_paths(value: str) -> tuple[str, ...]:
    """Extract repository paths from the canonical Files field without inventing scope."""
    paths = _BACKTICK_PATH_RE.findall(value or "")
    if not paths and value and value.strip() != "—":
        paths = [part.strip() for part in re.split(r"\s*[·,]\s*", value) if part.strip()]
    return tuple(sorted(set(paths)))


def _product_tree(plan_dir: Path, declared_paths: set[str]) -> tuple[str, list[dict]]:
    """Hash declared product carriers while excluding plan/audit bookkeeping."""
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=plan_dir, text=True,
        capture_output=True, check=False,
    )
    repository_root = (Path(completed.stdout.strip()) if completed.returncode == 0
                       and completed.stdout.strip() else plan_dir.parents[1])
    rows = []
    for declared in sorted(declared_paths):
        candidate = Path(declared)
        if candidate.is_absolute() or declared.startswith(("~", "../")):
            rows.append({"declared": declared, "state": "external"})
            continue
        path = repository_root / candidate
        if path.is_symlink():
            rows.append({"declared": declared, "path": candidate.as_posix(),
                         "state": "symlink", "target": str(path.readlink())})
            continue
        if path.is_file():
            rows.append({"declared": declared, "path": candidate.as_posix(), "state": "file",
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            continue
        if path.is_dir():
            members = []
            for member in sorted(path.rglob("*")):
                relative = member.relative_to(repository_root).as_posix()
                if ".git" in member.relative_to(repository_root).parts:
                    continue
                if member.is_symlink():
                    members.append({"path": relative, "state": "symlink",
                                    "target": str(member.readlink())})
                elif member.is_file():
                    members.append({"path": relative, "state": "file",
                                    "sha256": hashlib.sha256(member.read_bytes()).hexdigest()})
            rows.append({"declared": declared, "state": "directory", "members": members})
            continue
        rows.append({"declared": declared, "state": "missing"})
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), rows


def phase_candidate_fingerprint(plan_dir, phase_id, *, scope=(), material_risks=()):
    """Build D14's stable scope/item-head/risk fingerprint for a terminal candidate."""
    plan_dir = Path(plan_dir)
    if not re.fullmatch(r"P\d+", phase_id):
        raise ValueError("phase_id должен иметь форму Pn")
    items = []
    declared_paths = set()
    if plan_layout.layout_version(plan_dir) == "v1":
        # A v1 phase co-locates item specs, state, and append-only audit blocks.
        # Hash canonical per-item fields so appending the audit verdict does not
        # invalidate the exact candidate it attests.
        from task.plan_lint_checks.common import (  # local import avoids a lint coordinator cycle
            Diagnostics, ITEM_SPEC_FIELDS, ITEM_STATE_FIELDS,
        )
        from task.plan_lint_checks.parsing import parse_phase_md

        phase_path = plan_layout.phase_path(plan_dir, phase_id)
        diagnostics = Diagnostics()
        parsed = parse_phase_md(phase_path, phase_id, diagnostics, layout="v1")
        if parsed is None or diagnostics.errors:
            raise ValueError(f"{phase_id} не candidate: phase carrier невалиден")
        for item_id, occurrences in sorted(parsed["items"].items()):
            item = occurrences[0]
            fields = {key: value[0] for key, value in item["fields"].items()}
            declared_paths.update(_declared_file_paths(fields.get("Files", "")))
            status = fields.get("Status")
            if status not in {
                    plan_status.STATUS_DONE, plan_status.STATUS_DEVIATIONS,
                    plan_status.STATUS_BLOCKED}:
                raise ValueError(f"{phase_id} не candidate: {item_id} имеет статус {status}")
            spec = {key: fields[key] for key in ITEM_SPEC_FIELDS if key in fields}
            state = {key: fields[key] for key in ITEM_STATE_FIELDS if key in fields}
            spec_bytes = json.dumps(
                {"title": item["title"], "fields": spec}, ensure_ascii=False,
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            state_bytes = json.dumps(
                state, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            items.append({
                "item_id": item_id,
                "status": status,
                "spec_sha256": hashlib.sha256(spec_bytes).hexdigest(),
                "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
            })
    else:
        for spec_path in plan_layout.item_spec_paths(plan_dir, phase_id):
            item_id = spec_path.stem
            files_value = next((match.group(1) for line in spec_path.read_text(
                encoding="utf-8").splitlines() if (match := _FILES_FIELD_RE.match(line))), "")
            declared_paths.update(_declared_file_paths(files_value))
            model, _note, _friction = plan_item_state.state_model(plan_dir, item_id)
            status = model["state"]["position"]["status"]
            if status not in {
                    plan_status.STATUS_DONE, plan_status.STATUS_DEVIATIONS,
                    plan_status.STATUS_BLOCKED}:
                raise ValueError(f"{phase_id} не candidate: {item_id} имеет статус {status}")
            state_path = plan_layout.carrier_path(plan_dir, "item-state", item_id=item_id)
            items.append({
                "item_id": item_id,
                "status": status,
                "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
                "state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
            })
    if not items:
        raise ValueError(f"{phase_id} не содержит items")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=plan_dir, text=True,
        capture_output=True, check=False)
    head = completed.stdout.strip() if completed.returncode == 0 else "unknown"
    product_tree_sha256, product_files = _product_tree(plan_dir, declared_paths)
    digest_snapshot = {
        "phase_id": phase_id,
        "scope": sorted(str(value) for value in scope),
        "terminal_item_heads": sorted(items, key=lambda row: row["item_id"]),
        "material_risks": sorted(str(value) for value in material_risks),
        "declared_files": sorted(declared_paths),
        "product_tree_sha256": product_tree_sha256,
    }
    encoded = json.dumps(digest_snapshot, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    snapshot = {**digest_snapshot, "product_files": product_files,
                "observed_repository_head": head}
    return {"fingerprint": hashlib.sha256(encoded).hexdigest(), "snapshot": snapshot}


def _phase_close_owner_override(plan_dir: Path, phase_id: str, owner_decision: str | None):
    """Validate D26's deliberately narrow direct-green-validation escape hatch."""
    if owner_decision is None:
        return None
    if not isinstance(owner_decision, str) or not re.fullmatch(r"D[1-9][0-9]*", owner_decision):
        return {"allow": False, "code": "PHASE_OWNER_DECISION_INVALID"}
    paths = sorted((plan_dir / "decisions").glob(f"{owner_decision}-*.md"))
    if len(paths) != 1:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_MISSING"}
    try:
        decision = plan_decisions.parse_decision(paths[0])
    except plan_decisions.DecisionError:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_INVALID"}
    if decision.status != "accepted" or decision.superseded_by:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_NOT_ACCEPTED"}
    if decision.item != phase_id or phase_id not in decision.items:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_SCOPE_MISMATCH"}
    if not decision.supersedes:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_SUPERSEDES_MISSING"}
    if "`phase-close: direct-green-validation`" not in decision.body:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_LITERAL_MISSING"}
    return {"allow": True, "code": "allow", "owner_decision": decision.identifier}


def phase_close_gate(plan_dir, phase_id, *, candidate_fingerprint, owner_decision=None):
    """Allow a matching GREEN audit or an accepted phase-scoped owner override."""
    plan_dir = Path(plan_dir)
    override = _phase_close_owner_override(plan_dir, phase_id, owner_decision)
    if override is not None:
        return override
    journal_path = Path(plan_dir) / "journal.jsonl"
    latest = None
    if journal_path.is_file():
        for line_number, raw in enumerate(
                journal_path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("command") == "plan-audit" and event.get("item_id") == phase_id:
                latest = (line_number, event)
    if latest is None:
        return {"allow": False, "code": "PHASE_AUDIT_MISSING", "journal_line": None}
    line_number, event = latest
    if event.get("fingerprint") != candidate_fingerprint:
        return {"allow": False, "code": "PHASE_AUDIT_STALE", "journal_line": line_number}
    codes = {
        "audit-green": (True, "allow"),
        "audit-attention": (False, "PHASE_AUDIT_ATTENTION"),
        "audit-red": (False, "PHASE_AUDIT_RED"),
    }
    allow, code = codes.get(event.get("result"), (False, "PHASE_AUDIT_INVALID"))
    return {"allow": allow, "code": code, "journal_line": line_number}


def _calibration_label(measurer) -> str:
    artifact = measurer.artifact
    target = artifact["calibration_target"]
    return (f"token-estimate-calibration v{artifact['version']} "
            f"({target['provider']}/{target['requested_model_id']})")


def _error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{GATE_ID}: {message}")


def _bundle_error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{BUNDLE_GATE_ID}: {message}")


def _path_error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{PATH_GATE_ID}: {message}")


def _return_error(diag, path, message: str) -> None:
    diag.error(Path(path), None, f"{RETURN_LOOP_GATE_ID}: {message}")


def _active_items(plan_dir: Path, check: str, diag, gate: str) -> set[str]:
    try:
        return plan_gate_activation.active_items(plan_dir, check)
    except plan_gate_activation.ActivationError as exc:
        diag.error(plan_dir / "plan.md", None, f"{gate}: {exc}")
        return set()


def _return_evidence(plan_dir: Path) -> tuple[dict[str, dict], list[tuple[Path, str]]]:
    by_digest, malformed = {}, []
    for row in plan_returns.return_loop_evidence(plan_dir):
        fields, path = row["fields"], row["path"]
        errors = plan_returns.evidence_errors(fields)
        if errors:
            malformed.append((path, "; ".join(errors)))
            continue
        digest = fields.get("fingerprint_digest")
        if digest:
            by_digest.setdefault(digest, {"path": path, "fields": fields})
    return by_digest, malformed


def _lint_return_escalation_qualification(plan_dir, layout: str, diag) -> None:
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    active = _active_items(plan_dir, "task.plan_gates._lint_return_escalation_qualification", diag, RETURN_LOOP_GATE_ID)
    if not active:
        return
    try:
        projection = plan_returns.returns(plan_dir)
        evidence, malformed = _return_evidence(plan_dir)
    except plan_returns.ReturnError as exc:
        _return_error(diag, plan_dir / "findings", f"RETURN_LOOP_QUALIFICATION_REQUIRED: {exc}")
        return
    for path, message in malformed:
        _return_error(diag, path, f"RETURN_LOOP_QUALIFICATION_REQUIRED: {message}")
    fingerprints = [record for record in projection["fingerprints"]
                    if record["tuple"]["subject"] in active]
    counts = Counter(record["digest"] for record in fingerprints)
    for digest, occurrences in counts.items():
        row = evidence.get(digest)
        if row is None:
            _return_error(diag, plan_dir / "findings",
                          f"RETURN_LOOP_QUALIFICATION_REQUIRED: {digest}: evidence отсутствует")
            continue
        fields = row["fields"]
        expected = "new" if occurrences == 1 else "repeat"
        subject = next(record["tuple"]["subject"] for record in fingerprints
                       if record["digest"] == digest)
        if (fields.get("qualification") != expected or int(fields["occurrences"]) != occurrences
                or fields.get("item") != subject):
            _return_error(diag, row["path"],
                          f"RETURN_LOOP_QUALIFICATION_REQUIRED: {digest}: ожидается "
                          f"item={subject}, qualification={expected}, occurrences={occurrences}")


def _lint_return_owner_authorization(plan_dir, layout: str, diag) -> None:
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    active = _active_items(plan_dir, "task.plan_gates._lint_return_owner_authorization", diag, RETURN_LOOP_GATE_ID)
    if not active:
        return
    try:
        gates = plan_returns.return_loop_gates(plan_dir)
        evidence, _malformed = _return_evidence(plan_dir)
        decision_ids = {record.identifier for record in plan_decisions.load_decisions(plan_dir)}
    except (plan_returns.ReturnError, plan_decisions.DecisionError) as exc:
        _return_error(diag, plan_dir / "findings", f"RETURN_LOOP_OWNER_GATE_REQUIRED: {exc}")
        return
    active_digests = {record["digest"] for record in plan_returns.returns(plan_dir)["fingerprints"]
                      if record["tuple"]["subject"] in active}
    for gate in gates:
        if gate["fingerprint_digest"] not in active_digests:
            continue
        if not gate["blocks"] or gate["action"] != "owner-gate":
            continue
        digest, row = gate["fingerprint_digest"], evidence.get(gate["fingerprint_digest"])
        authorization = row["fields"].get("owner_authorization") if row else None
        if not isinstance(authorization, str) or authorization not in decision_ids:
            _return_error(diag, row["path"] if row else plan_dir / "findings",
                          f"RETURN_LOOP_OWNER_GATE_REQUIRED: {digest}: требуется существующий D# "
                          "в owner_authorization")


def lint_return_loop(plan_dir, layout: str, diag) -> None:
    """Run the execution-only return-loop checks for a live plan."""
    if Path(plan_dir).parent.name == "archive":
        return
    _lint_return_escalation_qualification(plan_dir, layout, diag)
    _lint_return_owner_authorization(plan_dir, layout, diag)
    _lint_terminal_phase_unresolved_decisions(plan_dir, layout, diag)


def _lint_terminal_phase_unresolved_decisions(plan_dir, layout: str, diag) -> None:
    """Opt-in join: a terminal phase cannot leave a queue request unresolved."""
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    try:
        active = plan_gate_activation.active_phases(plan_dir, "task.plan_gates._lint_terminal_phase_unresolved_decisions")
    except plan_gate_activation.ActivationError as exc:
        diag.error(plan_dir / "decisions" / "queue.jsonl", None, f"{DECISION_QUEUE_GATE_ID}: {exc}")
        return
    try:
        for phase_id in plan_layout.phase_paths(plan_dir):
            if phase_id not in active:
                continue
            if not plan_layout.is_terminal_phase(plan_dir, phase_id):
                continue
            unresolved = plan_requests.unresolved_for_phase(plan_dir, phase_id)
            if unresolved:
                diag.error(Path(plan_dir) / "decisions" / "queue.jsonl", None,
                           f"{DECISION_QUEUE_GATE_ID}: {phase_id}: unresolved decisions: "
                           f"{', '.join(unresolved)}")
    except (plan_layout.PlanLayoutError, plan_requests.RequestError) as exc:
        diag.error(Path(plan_dir) / "decisions" / "queue.jsonl", None,
                   f"{DECISION_QUEUE_GATE_ID}: queue unreadable: {exc}")


def lint_read_budget(plan_dir, layout: str, diag) -> None:
    """Emit D2 errors for ready layout-v2 items only.

    Layout v1 and archived plans are structurally outside the execution gate. In a
    live layout-v2 plan a missing calibration, read-limit artifact, or plan-owned
    contract is an error rather than an implicit skip. ``measure_plan`` attaches the
    canonical admission result to each item, so this function never re-counts files
    or parses producer annotations.
    """
    if layout != "v2":
        return

    plan_dir = Path(plan_dir)
    if plan_dir.parent.name == "archive":
        return
    try:
        measurer = plan_weight.Measurer()
        measured = plan_weight.measure_plan(plan_dir, measurer)
    except plan_weight.PlanWeightError as exc:
        _error(diag, plan_dir / "plan.md", f"не удалось загрузить вход гейта: {exc}")
        return

    try:
        active_phases = {phase_id for phase_id, status in plan_layout.phase_statuses(plan_dir).items()
                         if status == plan_status.STATUS_PROGRESS}
    except plan_layout.PlanLayoutError:
        # Isolated gate fixtures and pre-projection diagnostics have no owner
        # status view yet.  Preserve the previous all-items fail-closed check
        # until the generated carrier exists.
        active_items = measured["items"]
    else:
        active_items = [item for item in measured["items"]
                        if item["item_id"].split(".", 1)[0] in active_phases]
    if not active_items:
        return

    admission = measured["totals"].get("admission") or {}
    contract = admission.get("contract")
    if contract is None:
        _error(diag, plan_dir / "root" / "contracts" / "read-budget-v1.md",
               "контракт порога отсутствует или невалиден; D2 не может быть применён")
        return

    threshold = contract["item_tokens"]
    calibration = _calibration_label(measurer)
    limits = measurer.limits
    for item in active_items:
        if item.get("admission_state") != "ready" or item.get("admission_pass") is not False:
            continue

        item_id = item["item_id"]
        if item.get("d2a_pass") is False:
            _error(diag, plan_dir / "plan.md",
                   f"пункт {item_id}: вес {item['weight_tokens']} > порога {threshold} "
                   f"оценочных токенов ({calibration})")

        for gap in item.get("gaps", []):
            kind = gap.get("kind")
            if kind == plan_weight.GAP_OVERSIZED_FILE:
                _error(diag, plan_dir / "plan.md",
                       f"пункт {item_id}: файл {gap['path']} — {gap['bytes']} байт, "
                       f"{gap['est_tokens']} оценочных токенов; лимиты одного чтения "
                       f"{limits['size_bytes']} байт / {limits['tokens']} токенов "
                       f"({calibration})")
            elif kind in (plan_weight.GAP_MISSING_FILE, plan_weight.GAP_UNREADABLE_ROOT,
                          plan_weight.GAP_UNRESOLVED_ENTRY):
                subject = gap.get("path") or gap.get("entry") or "обязательный вход"
                _error(diag, plan_dir / "plan.md",
                       f"пункт {item_id}: обязательный вход {subject!r} не проходит "
                       f"D2(b): {gap['detail']}")

        for gap in item.get("admission_gaps", []):
            if gap.get("code") == "read_budget_contract_invalid":
               _error(diag, plan_dir / "root" / "contracts" / "read-budget-v1.md",
                       f"пункт {item_id}: {gap.get('detail')}")


def lint_bundle_freshness(plan_dir, layout: str, diag) -> None:
    """Verify ready v2 bundles and committed deterministic projections without rebuilding."""
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    try:
        measured = plan_weight.measure_plan(plan_dir, plan_weight.Measurer())
        active_phases = {phase_id for phase_id, status in plan_layout.phase_statuses(plan_dir).items()
                         if status == plan_status.STATUS_PROGRESS}
    except plan_weight.PlanWeightError as exc:
        _bundle_error(diag, plan_dir / "plan.md", f"не удалось загрузить ready-область: {exc}")
        return
    except plan_layout.PlanLayoutError as exc:
        _bundle_error(diag, plan_dir / "status.md", f"не удалось определить активную фазу: {exc}")
        return
    active_items = [item for item in measured["items"]
                    if item.get("admission_state") == "ready"
                    and item["item_id"].split(".", 1)[0] in active_phases]
    # Bundle v1 became a committed carrier in P3. A v2 plan that has not entered
    # that producer surface must remain compatible with the pre-P3 reader path.
    if not any(plan_layout.carrier_path(plan_dir, "bundle", item_id=item["item_id"]).is_file()
               for item in active_items):
        return
    for item in active_items:
        if item.get("admission_state") != "ready":
            continue
        item_id = item["item_id"]
        target = plan_layout.carrier_path(plan_dir, "bundle", item_id=item_id)
        try:
            expected = plan_bundle.render(plan_dir, item_id).encode("utf-8")
            actual = target.read_bytes()
        except plan_bundle.BundleError as exc:
            _bundle_error(diag, target, f"пункт {item_id}: {exc}")
            continue
        except OSError:
            _bundle_error(diag, target, f"пункт {item_id}: missing_entry: bundle отсутствует")
            continue
        if actual == expected:
            continue
        try:
            current = json.loads(actual)
            expected_model = json.loads(expected)
            current_entries = {(e["declaration_ref"]["field"], e["declaration_ref"]["ordinal"],
                                e["path"], str(e["selector"])) for e in current.get("entries", [])}
            expected_entries = {(e["declaration_ref"]["field"], e["declaration_ref"]["ordinal"],
                                 e["path"], str(e["selector"])) for e in expected_model["entries"]}
            if current.get("declaration") != expected_model["declaration"]:
                code = "stale_vs_spec"
            elif expected_entries - current_entries:
                code = "missing_entry"
            elif current_entries - expected_entries:
                diag.warning(target, None, f"{BUNDLE_GATE_ID}: пункт {item_id}: extraneous_entry")
                continue
            else:
                code = "hash_mismatch"
        except Exception:
            code = "hash_mismatch"
        _bundle_error(diag, target, f"пункт {item_id}: {code}")
    for builder in (plan_decisions.build_views, plan_status.build_status, plan_item_state.build_states):
        try:
            builder(plan_dir, check=True)
        except (plan_decisions.DecisionError, plan_status.StatusError,
                plan_item_state.ItemStateError, plan_projection.ProjectionError) as exc:
            _bundle_error(diag, plan_dir, f"generated view stale: {exc}")


def lint_read_path_boundaries(plan_dir, layout: str, diag) -> None:
    """Check frozen carrier declarations and item inputs without inspecting prose."""
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    try:
        spec = plan_layout.read_path_spec()
        registry = plan_layout.registry()
        ranks = spec["volatility_rank"]
    except (KeyError, plan_layout.PlanLayoutError) as exc:
        _path_error(diag, plan_dir / "plan.md", f"контракт пути не читается: {exc}")
        return

    for reader, path in spec.get("paths", {}).items():
        prior_rank = -1
        for slot in sorted(path.get("slots", ()), key=lambda row: row.get("order", 0)):
            carrier_id = slot.get("carrier_id")
            carrier = registry.get(carrier_id)
            if carrier is None:
                _path_error(diag, plan_dir / "plan.md",
                            f"путь {reader}, слот {slot.get('id')}: неизвестный носитель {carrier_id!r}")
                continue
            rank = ranks.get(carrier.get("volatility"))
            if rank is None:
                _path_error(diag, plan_dir / "plan.md",
                            f"путь {reader}, слот {slot.get('id')}, носитель {carrier_id}: неизвестная волатильность")
                continue
            if rank < prior_rank:
                _path_error(diag, plan_dir / "plan.md",
                            f"путь {reader}, слот {slot.get('id')}, носитель {carrier_id}: "
                            "волатильность нарушает монотонный предикат порядка")
            prior_rank = max(prior_rank, rank)
            if reader == "executor" and carrier.get("class") == "history":
                _path_error(diag, plan_dir / "plan.md",
                            f"путь executor, слот {slot.get('id')}, носитель {carrier_id} класса history "
                            "стоит на обязательном пути")

    for carrier_id, sections in spec.get("section_order", {}).items():
        prior_rank = -1
        for section in sorted(sections, key=lambda row: row.get("order", 0)):
            rank = ranks.get(section.get("volatility"))
            if rank is None:
                _path_error(diag, plan_dir / "plan.md",
                            f"носитель {carrier_id}, секция {section.get('section')}: неизвестная волатильность")
                continue
            if rank < prior_rank:
                _path_error(diag, plan_dir / "plan.md",
                            f"носитель {carrier_id}, секция {section.get('section')}: "
                            "волатильность нарушает монотонный предикат порядка")
            prior_rank = max(prior_rank, rank)
            if carrier_id == "plan-core" and rank == ranks.get("volatile"):
                _path_error(diag, plan_dir / "plan.md",
                            f"носитель plan-core, секция {section.get('section')}: volatile запрещён")

    try:
        terminal_specs = {path.resolve() for phase_id in plan_layout.phase_paths(plan_dir)
                          if plan_layout.is_terminal_phase(plan_dir, phase_id)
                          for path in plan_layout.item_spec_paths(plan_dir, phase_id)}
        active_phases = {phase_id for phase_id, status in plan_layout.phase_statuses(plan_dir).items()
                         if status == plan_status.STATUS_PROGRESS}
        measured = plan_weight.measure_plan(plan_dir, plan_weight.Measurer())
    except (plan_layout.PlanLayoutError, plan_weight.PlanWeightError) as exc:
        _path_error(diag, plan_dir / "plan.md", f"не удалось разрешить терминальную фазу: {exc}")
        return
    repo_root = plan_weight.repo_root_for(plan_dir)
    for item in measured["items"]:
        if item["phase_id"] not in active_phases:
            continue
        try:
            fields = plan_bundle._fields(plan_dir, item["item_id"])
        except plan_bundle.BundleError:
            continue
        for field in ("Inputs", "Required Reads"):
            for raw in plan_bundle._raw_entries(fields.get(field, ""), field):
                for candidate, declared in plan_weight.path_candidates(raw):
                    if not declared:
                        continue
                    resolved = plan_weight.resolve_candidate(candidate, (plan_dir, repo_root))
                    if resolved is not None and resolved.resolve() in terminal_specs:
                        _path_error(diag, plan_dir / "plan.md",
                                    f"пункт {item['item_id']}, {field}: {candidate} адресует файл "
                                    "терминальной фазы; допустим только её closure digest")
    _lint_downstream_records(plan_dir, layout, diag)


def _lint_downstream_records(plan_dir, layout: str, diag) -> None:
    plan_downstream.lint_records(plan_dir, layout, diag)


__all__ = ("BUNDLE_GATE_ID", "DECISION_QUEUE_GATE_ID", "GATE_ID", "PATH_GATE_ID", "RETURN_LOOP_GATE_ID",
           "lint_bundle_freshness", "lint_read_budget", "lint_read_path_boundaries",
           "lint_return_loop")
