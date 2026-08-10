"""Hard admission gates for executable-plan layout v2.

The gate deliberately delegates all measurement and timing decisions: ``plan_weight``
owns the mandatory-read graph and its one weight, while ``plan_admission`` owns the
``historical``/``pending``/``ready`` state machine.  This module only turns a failed
ready D2 result into actionable plan-lint diagnostics.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from task import (plan_bundle, plan_decisions, plan_downstream, plan_gate_activation, plan_item_state, plan_layout,
                  plan_projection, plan_requests, plan_returns, plan_status, plan_weight)


GATE_ID = "read-budget-v1"
BUNDLE_GATE_ID = "bundle-v1"
PATH_GATE_ID = "read-path-v1"
RETURN_LOOP_GATE_ID = "return-loop-v1"
DECISION_QUEUE_GATE_ID = "decision-queue-v1"


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

    admission = measured["totals"].get("admission") or {}
    contract = admission.get("contract")
    if contract is None:
        _error(diag, plan_dir / "root" / "contracts" / "read-budget-v1.md",
               "контракт порога отсутствует или невалиден; D2 не может быть применён")
        return

    threshold = contract["item_tokens"]
    calibration = _calibration_label(measurer)
    limits = measurer.limits
    for item in measured["items"]:
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
