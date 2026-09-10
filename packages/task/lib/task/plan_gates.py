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
from pathlib import Path, PurePosixPath

from task import (plan_bundle, plan_decisions, plan_downstream, plan_evidence, plan_gate_activation, plan_item_state, plan_layout,
                  plan_assurance, plan_projection, plan_requests, plan_returns, plan_status, plan_weight,
                  review_policy, task_contract)


GATE_ID = "read-budget-v1"
BUNDLE_GATE_ID = "bundle-v1"
TERMINAL_ITEM_STATUSES = {
    plan_status.STATUS_DONE,
    plan_status.STATUS_DEVIATIONS,
    plan_status.STATUS_BLOCKED,
    "⛔ Skipped by decision",
}
PATH_GATE_ID = "read-path-v1"
RETURN_LOOP_GATE_ID = "return-loop-v1"
DECISION_QUEUE_GATE_ID = "decision-queue-v1"
_FILES_FIELD_RE = re.compile(r"^\*\*Files:\*\*\s*(.*)$")
_BACKTICK_PATH_RE = re.compile(r"`([^`]+)`")
_ROUTING_ITEM_RE = re.compile(r"^P\d+\.\d+$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")
_REVIEW_ORDER = {"none": 0, "light": 1, "full": 2}
_BRACE_EXPANSION_LIMIT = 64
_GLOB_CHARS = frozenset("*?[")


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


def _validate_declared_path(value: str) -> None:
    """Reject paths whose meaning would depend on a shell or host filesystem."""
    if not value or "\0" in value or "\\" in value:
        raise ValueError(f"invalid declared Files path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("~") or ".." in path.parts:
        raise ValueError(f"declared Files path escapes repository: {value!r}")
    if value.startswith("./") or "//" in value or "/./" in value or value.endswith("/."):
        raise ValueError(f"declared Files path is not normalized POSIX: {value!r}")
    if value.count("[") != value.count("]"):
        raise ValueError(f"invalid Git glob character class: {value!r}")


def _expand_braces(value: str, *, limit: int = _BRACE_EXPANSION_LIMIT) -> tuple[str, ...]:
    """Expand bounded, non-nested ``{a,b}`` groups without shell semantics."""
    _validate_declared_path(value)
    expanded = [value]
    while any("{" in item or "}" in item for item in expanded):
        next_items = []
        for item in expanded:
            opening = item.find("{")
            closing = item.find("}")
            if opening < 0 or closing < 0 or closing < opening:
                raise ValueError(f"unbalanced brace path: {value!r}")
            body = item[opening + 1:closing]
            if "{" in body or "}" in body or "{" in item[closing + 1:closing + 2]:
                raise ValueError(f"nested brace path is not supported: {value!r}")
            alternatives = body.split(",")
            if len(alternatives) < 2 or any(not alternative for alternative in alternatives):
                raise ValueError(f"brace path needs non-empty alternatives: {value!r}")
            prefix, suffix = item[:opening], item[closing + 1:]
            next_items.extend(f"{prefix}{alternative}{suffix}" for alternative in alternatives)
            if len(next_items) > limit:
                raise ValueError(f"brace expansion exceeds {limit}: {value!r}")
        expanded = next_items
    for item in expanded:
        _validate_declared_path(item)
    return tuple(sorted(set(expanded)))


def _is_glob(value: str) -> bool:
    return any(character in value for character in _GLOB_CHARS)


def _tracked_members(repository_root: Path, patterns: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve one declaration through Git's tracked index, failing closed."""
    pathspecs = [f":(glob){pattern}" if _is_glob(pattern) else f":(literal){pattern}"
                 for pattern in patterns]
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--", *pathspecs],
        cwd=repository_root, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git ls-files rejected declared Files pathspec: {message}")
    try:
        decoded = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("git ls-files returned a non-UTF-8 tracked path") from exc
    members = []
    for raw in decoded.split("\0"):
        if not raw:
            continue
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"git ls-files returned an escaping path: {raw!r}")
        members.append(path.as_posix())
    return tuple(sorted(set(members)))


def _tracked_member_row(repository_root: Path, relative: str) -> dict:
    path = repository_root / PurePosixPath(relative)
    if path.is_symlink():
        return {"path": relative, "state": "symlink", "target": str(path.readlink())}
    if path.is_file():
        return {"path": relative, "state": "file",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"path": relative, "state": "deleted"}


def _product_tree(plan_dir: Path, declared_paths: set[str]) -> tuple[str, list[dict]]:
    """Hash current bytes of deterministic Git-tracked declared product members."""
    plan_dir = plan_dir.resolve()
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=plan_dir, text=True,
        capture_output=True, check=False,
    )
    repository_root = (Path(completed.stdout.strip()).resolve() if completed.returncode == 0
                       and completed.stdout.strip() else plan_weight.repo_root_for(plan_dir))
    try:
        plan_prefix = plan_dir.relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise ValueError("plan directory is outside the repository root") from exc
    rows = []
    for declared in sorted(declared_paths):
        expanded = _expand_braces(declared)
        candidates = (
            expanded,
            tuple(f"{plan_prefix}/{path}" for path in expanded),
        )
        patterns, members = candidates[-1], ()
        for candidate_patterns in candidates:
            candidate_members = _tracked_members(repository_root, candidate_patterns)
            if candidate_members:
                patterns, members = candidate_patterns, candidate_members
                break
        if not members:
            rows.append({"declared": declared, "state": "missing"})
            continue
        member_rows = [_tracked_member_row(repository_root, relative) for relative in members]
        if len(patterns) == 1 and not _is_glob(patterns[0]) and members == patterns:
            rows.append({"declared": declared, **member_rows[0]})
        else:
            rows.append({"declared": declared, "state": "tracked-set", "members": member_rows})
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), rows


def _candidate_snapshot_fingerprint(snapshot: dict) -> str:
    """Bind the policy input to the exact candidate material fingerprint."""
    digest_snapshot = {
        key: snapshot[key]
        for key in ("phase_id", "scope", "terminal_item_heads", "material_risks",
                    "declared_files", "product_tree_sha256")
    }
    encoded = json.dumps(digest_snapshot, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def phase_candidate_fingerprint(plan_dir, phase_id, *, scope=(), material_risks=()):
    """Build D14's stable scope/item-head/risk fingerprint for a terminal candidate."""
    plan_dir = Path(plan_dir)
    if not re.fullmatch(r"P\d+", phase_id):
        raise ValueError("phase_id должен иметь форму Pn")
    items = []
    declared_paths = set()
    plan_layout.layout_version(plan_dir)
    for spec_path in plan_layout.item_spec_paths(plan_dir, phase_id):
        item_id = spec_path.stem
        files_value = next((match.group(1) for line in spec_path.read_text(
            encoding="utf-8").splitlines() if (match := _FILES_FIELD_RE.match(line))), "")
        declared_paths.update(plan_evidence.material_product_paths(plan_dir, item_id))
        model, _note, _friction = plan_item_state.state_model(plan_dir, item_id)
        status = model["state"]["position"]["status"]
        if status not in {
                plan_status.STATUS_DONE, plan_status.STATUS_DEVIATIONS,
                plan_status.STATUS_BLOCKED}:
            raise ValueError(f"{phase_id} не candidate: {item_id} имеет статус {status}")
        material_evidence = plan_item_state.material_terminal_evidence(plan_dir, item_id)
        material_bytes = json.dumps(
            material_evidence, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        items.append({
            "item_id": item_id,
            "status": status,
            "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            "terminal_evidence_sha256": hashlib.sha256(material_bytes).hexdigest(),
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
    snapshot = {**digest_snapshot, "product_files": product_files,
                "observed_repository_head": head}
    return {"fingerprint": _candidate_snapshot_fingerprint(snapshot), "snapshot": snapshot}


def audit_fixer_rebind(before, after):
    """Bind an audit verdict to the candidate rebuilt after an inline repair.

    Candidate bookkeeping is deliberately absent from the fingerprint.  Therefore
    an unchanged digest is audit bookkeeping only; a changed digest proves that a
    product carrier or terminal item evidence changed and must be rebound before a
    verdict may be emitted.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("audit candidates must be mappings")
    before_snapshot, after_snapshot = before.get("snapshot"), after.get("snapshot")
    if not isinstance(before_snapshot, dict) or not isinstance(after_snapshot, dict):
        raise ValueError("audit candidate snapshot is required")
    if before_snapshot.get("phase_id") != after_snapshot.get("phase_id"):
        raise ValueError("audit candidates must belong to one phase")
    before_fingerprint = before.get("fingerprint")
    after_fingerprint = after.get("fingerprint")
    if (before_fingerprint != _candidate_snapshot_fingerprint(before_snapshot)
            or after_fingerprint != _candidate_snapshot_fingerprint(after_snapshot)):
        raise ValueError("audit candidate fingerprint does not bind its snapshot")
    rebound = before_fingerprint != after_fingerprint
    return {
        "phase_id": after_snapshot["phase_id"],
        "before": before_fingerprint,
        "after": after_fingerprint,
        "rebound": rebound,
        "reason": "product-or-terminal-evidence-changed" if rebound else "audit-bookkeeping-only",
    }


def _routing_items(value: str) -> tuple[str, ...] | None:
    value = value.strip().strip("`")
    if _ROUTING_ITEM_RE.fullmatch(value):
        return (value,)
    match = _ROUTING_RANGE_RE.fullmatch(value)
    if not match or match.group(1) != match.group(3):
        return None
    first, last = int(match.group(2)), int(match.group(4))
    if first > last:
        return None
    return tuple(f"{match.group(1)}.{number}" for number in range(first, last + 1))


def _phase_reviews(plan_dir: Path, phase_id: str) -> dict[str, str]:
    """Project one phase's Review cells from the Task Contract Routing model."""
    table = task_contract.executable_routing_table(plan_dir)
    reviews = {}
    for row, _line in table["rows"]:
        for item_id in row["_items"]:
            if item_id.startswith(f"{phase_id}."):
                reviews[item_id] = row["Review"]
    return reviews


def _audit_policy_decision(plan_dir: Path, phase_id: str, *, required: bool,
                           code: str, review: str, reason: str) -> dict:
    kind = "audit-phase" if required else "close"
    command = "task:plan-audit" if required else "task:plan-close"
    return {
        "audit_required": required,
        "code": code,
        "effective_review": review,
        "next_kind": kind,
        "next_exact": f"{kind}: {command} {plan_dir.name} {phase_id}",
        "reasons": [reason],
    }


def phase_audit_policy(plan_dir, phase_id, *, candidate_snapshot=None):
    """Compatibility facade over the sole phase-assurance policy owner.

    The historical signature is intentionally retained for callers and fixtures,
    but Routing review and item count no longer participate in phase risk.
    """
    plan_dir = Path(plan_dir)
    if not re.fullmatch(r"P\d+", phase_id):
        raise ValueError("phase_id должен иметь форму Pn")
    snapshot = candidate_snapshot if isinstance(candidate_snapshot, dict) else None
    try:
        reviews = _phase_reviews(plan_dir, phase_id)
    except task_contract.TaskContractBuildError as exc:
        # Routing ambiguity is an admission defect, not an assurance inference.
        # Keep P3.1 as the sole assurance reducer while refusing audit/close
        # before any historical audit receipt can be reused.
        if "duplicate executable Routing tables" in str(exc) or "assigned more than once" in str(exc):
            return _audit_policy_decision(
                Path(plan_dir), phase_id, required=True,
                code="PHASE_ROUTING_UNRESOLVED", review="unassessed",
                reason=f"Routing compiler: {exc}")
        reviews = {}
    policy = plan_assurance.evaluate(plan_dir, phase_id, candidate=snapshot)
    # Existing consumers expose these legacy keys; they carry no independent
    # decision semantics and may be removed only in a separately versioned API.
    return {
        **policy,
        # This is reporting-only.  Assurance remains the P3.1 decision owner.
        "effective_review": (max(reviews.values(), key=_REVIEW_ORDER.__getitem__)
                             if reviews else "assurance"),
        "routing_reviews": reviews,
    }


def _phase_close_owner_override(plan_dir: Path, phase_id: str, owner_decision: str | None):
    """Validate a deliberately narrow direct-green-validation escape hatch."""
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
    if decision.item == phase_id and phase_id in decision.items:
        if not decision.supersedes:
            return {"allow": False, "code": "PHASE_OWNER_DECISION_SUPERSEDES_MISSING"}
        if "`phase-close: direct-green-validation`" not in decision.body:
            return {"allow": False, "code": "PHASE_OWNER_DECISION_LITERAL_MISSING"}
        return {"allow": True, "code": "allow", "owner_decision": decision.identifier}

    try:
        phase_items = {path.stem for path in plan_layout.item_spec_paths(plan_dir, phase_id)}
    except plan_layout.PlanLayoutError:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_SCOPE_MISMATCH"}
    if decision.item not in phase_items:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_SCOPE_MISMATCH"}
    if set(decision.items) != phase_items:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_ITEM_SET_MISMATCH"}
    if not ("AUDIT-CAP" in decision.body
            and f"третьего Audit {phase_id}" in decision.body
            and "фаза закрывается штатным `task:plan-close`" in decision.body):
        return {"allow": False, "code": "PHASE_OWNER_DECISION_LITERAL_MISSING"}
    return {"allow": True, "code": "allow", "owner_decision": decision.identifier}


def _phase_terminal_blocked_owner_override(plan_dir: Path, phase_id: str,
                                           owner_decision: str | None):
    """Validate the explicit owner exception for a terminal blocked phase."""
    if owner_decision is None or not isinstance(owner_decision, str):
        return None
    paths = sorted((plan_dir / "decisions").glob(f"{owner_decision}-*.md"))
    if len(paths) != 1:
        return None
    try:
        decision = plan_decisions.parse_decision(paths[0])
    except plan_decisions.DecisionError:
        return None
    if "`phase-close: terminal-blocked-deviations`" not in decision.body:
        return None
    if decision.status != "accepted" or decision.superseded_by:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_NOT_ACCEPTED", "recognized": True}
    try:
        phase_items = {path.stem for path in plan_layout.item_spec_paths(plan_dir, phase_id)}
    except plan_layout.PlanLayoutError:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_SCOPE_MISMATCH", "recognized": True}
    if decision.item != phase_id or set(decision.items) != {phase_id, *phase_items}:
        return {"allow": False, "code": "PHASE_OWNER_DECISION_TERMINAL_BLOCK_SCOPE_MISMATCH",
                "recognized": True}
    return {"allow": True, "code": "allow", "owner_decision": decision.identifier,
            "recognized": True, "mode": "terminal-blocked-deviations"}


def terminal_blocked_phase_closure(plan_dir, phase_id: str) -> bool:
    """Whether a durable owner-gated close declares this phase as deviations."""
    plan_dir = Path(plan_dir)
    journal_path = plan_dir / "journal.jsonl"
    if not journal_path.is_file():
        return False
    latest = None
    for raw in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("command") == "plan-close" and event.get("item_id") == phase_id:
            latest = event
    if latest is None or latest.get("result") != "closed-deviations":
        return False
    decision = latest.get("decision")
    if (not isinstance(decision, dict)
            or decision.get("action") != "phase-close-terminal-blocked-deviations"):
        return False
    override = _phase_terminal_blocked_owner_override(
        plan_dir, phase_id, decision.get("owner_decision"))
    return bool(override and override.get("allow"))


def phase_close_gate(plan_dir, phase_id, *, candidate_fingerprint, candidate_snapshot=None,
                     owner_decision=None):
    """Allow adaptive direct close, matching GREEN audit, or an owner override."""
    plan_dir = Path(plan_dir)
    if candidate_snapshot is not None:
        try:
            bound_fingerprint = _candidate_snapshot_fingerprint(candidate_snapshot)
        except (KeyError, TypeError, ValueError):
            bound_fingerprint = None
        if bound_fingerprint != candidate_fingerprint:
            return {"allow": False, "code": "PHASE_CANDIDATE_SNAPSHOT_MISMATCH",
                    "journal_line": None}
    terminal_override = _phase_terminal_blocked_owner_override(
        plan_dir, phase_id, owner_decision)
    if terminal_override is not None and terminal_override.get("recognized"):
        if not terminal_override["allow"]:
            return terminal_override
        heads = candidate_snapshot.get("terminal_item_heads") if isinstance(candidate_snapshot, dict) else None
        statuses = [row.get("status") for row in heads if isinstance(row, dict)] if isinstance(heads, list) else []
        terminal = {plan_status.STATUS_DONE, plan_status.STATUS_DEVIATIONS,
                    plan_status.STATUS_BLOCKED, plan_status.STATUS_SKIPPED}
        if not heads or len(statuses) != len(heads):
            return {"allow": False, "code": "PHASE_TERMINAL_BLOCKED_CANDIDATE_REQUIRED"}
        if any(status not in terminal for status in statuses):
            return {"allow": False, "code": "PHASE_TERMINAL_BLOCKED_NONTERMINAL_ITEM"}
        if plan_status.STATUS_BLOCKED not in statuses:
            return {"allow": False, "code": "PHASE_TERMINAL_BLOCKED_ITEMS_REQUIRED"}
        return {**terminal_override, "phase_status": plan_status.STATUS_DEVIATIONS}
    override = _phase_close_owner_override(plan_dir, phase_id, owner_decision)
    if override is not None:
        return override
    audit_policy = phase_audit_policy(
        plan_dir, phase_id, candidate_snapshot=candidate_snapshot)
    if audit_policy["code"] == "PHASE_ROUTING_UNRESOLVED":
        return {"allow": False, "code": "PHASE_ROUTING_UNRESOLVED", "journal_line": None,
                "audit_policy": audit_policy}
    if not audit_policy["audit_required"]:
        return {"allow": True, "code": "allow", "journal_line": None,
                "audit_policy": audit_policy}
    journal_path = Path(plan_dir) / "journal.jsonl"
    latest = None
    if journal_path.is_file():
        for line_number, raw in enumerate(
                journal_path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (event.get("command") == "plan-audit"
                    and review_policy.phase_audit_subject(event.get("item_id")) == phase_id):
                latest = (line_number, event)
    if latest is None:
        return {"allow": False, "code": "PHASE_AUDIT_MISSING", "journal_line": None,
                "audit_policy": audit_policy}
    line_number, event = latest
    if event.get("fingerprint") != candidate_fingerprint:
        # Historical minimal callers have no snapshot to classify.  Preserve
        # their readable refusal while all runtime-built candidates receive a
        # closed `audit-impact/v1` continuation instead of bare stale/full.
        if candidate_snapshot is None:
            return {"allow": False, "code": "PHASE_AUDIT_STALE", "journal_line": line_number,
                    "audit_policy": audit_policy}
        broker = plan_assurance.evaluate(
            plan_dir, phase_id, candidate=candidate_snapshot,
            baseline=event.get("candidate_snapshot"),
            second_full_justification=event.get("second_full_justification"),
        )
        return {
            "allow": False,
            "code": broker["code"],
            "journal_line": line_number,
            "audit_policy": audit_policy,
            "impact": broker.get("impact"),
            "continuation": broker["action"],
            "next_exact": broker["next_exact"],
        }
    codes = {
        "audit-green": (True, "allow"),
        "audit-attention": (False, "PHASE_AUDIT_ATTENTION"),
        "audit-red": (False, "PHASE_AUDIT_RED"),
    }
    allow, code = codes.get(event.get("result"), (False, "PHASE_AUDIT_INVALID"))
    return {"allow": allow, "code": code, "journal_line": line_number,
            "audit_policy": audit_policy}


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

    Archived plans are structurally outside the execution gate. In a live plan a
    missing calibration, read-limit artifact, or plan-owned
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
                        if item["item_id"].split(".", 1)[0] in active_phases
                        and item.get("status") not in TERMINAL_ITEM_STATUSES]
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
                    and item["item_id"].split(".", 1)[0] in active_phases
                    and item.get("status") not in TERMINAL_ITEM_STATUSES]
    # D17: a terminal bundle remains historical evidence.  Keep validating its
    # own bytes/schema, but never re-render it or resolve retired source inputs.
    for item in measured["items"]:
        if item.get("status") not in TERMINAL_ITEM_STATUSES:
            continue
        target = plan_layout.carrier_path(plan_dir, "bundle", item_id=item["item_id"])
        if not target.is_file():
            continue
        try:
            plan_bundle.validate(json.loads(target.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, plan_bundle.BundleError) as exc:
            _bundle_error(diag, target,
                          f"пункт {item['item_id']}: terminal evidence schema invalid: {exc}")
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


def lint_static_bundle_evidence(plan_dir, layout: str, diag) -> None:
    """Validate terminal bundle schemas without reopening ready scope.

    The next-runnable bundle gate intentionally avoids rendering future consumers,
    but terminal bundles are historical safety evidence.  Their schema checks
    must therefore remain active independently of which item is currently
    runnable.  Generated views stay owned by their dedicated materializers: lint
    fixtures may deliberately omit them while testing an earlier structural gate.
    """
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    try:
        measured = plan_weight.measure_plan(plan_dir, plan_weight.Measurer())
    except plan_weight.PlanWeightError as exc:
        _bundle_error(diag, plan_dir / "plan.md", f"не удалось загрузить terminal evidence: {exc}")
        return
    for item in measured["items"]:
        if item.get("status") not in TERMINAL_ITEM_STATUSES:
            continue
        target = plan_layout.carrier_path(plan_dir, "bundle", item_id=item["item_id"])
        if not target.is_file():
            continue
        try:
            plan_bundle.validate(json.loads(target.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, plan_bundle.BundleError) as exc:
            _bundle_error(diag, target,
                          f"пункт {item['item_id']}: terminal evidence schema invalid: {exc}")


def lint_read_path_boundaries(plan_dir, layout: str, diag) -> None:
    """Check frozen carrier declarations and item inputs without inspecting prose."""
    if layout != "v2":
        return
    plan_dir = Path(plan_dir)
    lint_static_bundle_evidence(plan_dir, layout, diag)
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
           "lint_bundle_freshness", "lint_static_bundle_evidence", "lint_read_budget", "lint_read_path_boundaries",
           "lint_return_loop")
