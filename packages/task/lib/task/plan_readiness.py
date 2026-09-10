"""Typed producer readiness and terminal-phase re-entry evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class ReadinessError(ValueError):
    pass


_ITEM = re.compile(r"^P[0-9]+\.[0-9]+$")
_PHASE = re.compile(r"^P[0-9]+$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_DECISION = re.compile(r"^D[1-9][0-9]*$")
_OBSERVED_MODES = frozenset((
    "approved-no-op", "valid-output", "stale-derived", "missing-or-corrupt",
    "contract-conflict",
))
_DIRECTIVE = re.compile(
    r"`producer-readiness/v1`\s*:\s*consumer=(P\d+\.\d+)\s*;\s*"
    r"modes=(nonempty-candidates\|empty-by-decision|empty-by-decision\|nonempty-candidates)")


def _closed(value, fields, name):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ReadinessError(f"{name}: closed schema mismatch")


def _strings(value, name, *, required=False):
    if not isinstance(value, list) or (required and not value) or len(value) != len(set(value)) \
            or any(not isinstance(row, str) or not row for row in value):
        raise ReadinessError(f"{name}: expected unique strings")


def directive(deliverables: str) -> dict | None:
    matches = _DIRECTIVE.findall(deliverables or "")
    if not matches:
        return None
    if len(matches) != 1:
        raise ReadinessError("Deliverables: требуется ровно одна producer-readiness/v1 directive")
    consumer, modes = matches[0]
    return {"consumer_item": consumer, "modes": tuple(modes.split("|"))}


def _accepted_decision(plan_dir: Path, identifier: str) -> bool:
    matches = sorted((plan_dir / "decisions").glob(f"{identifier}-*.md"))
    if len(matches) != 1:
        return False
    try:
        frontmatter = matches[0].read_text(encoding="utf-8").split("---", 2)[1]
    except (OSError, UnicodeDecodeError, IndexError):
        return False
    fields = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields.get("id") == identifier and fields.get("status") == "accepted"


def validate_readiness(record: dict, *, plan_dir: Path | None = None) -> None:
    fields = {"schema_version", "producer_item", "consumer_item", "mode", "roots", "command",
              "candidate_count", "candidate_paths_sha256", "source_commit", "predicate", "exclusions"}
    if not isinstance(record, dict):
        raise ReadinessError("producer readiness: expected object")
    if record.get("mode") == "empty-by-decision":
        fields.add("owner_decision")
    _closed(record, fields, "producer readiness")
    if record["schema_version"] != "producer-readiness/v1" or not _ITEM.fullmatch(record["producer_item"]) \
            or not _ITEM.fullmatch(record["consumer_item"]):
        raise ReadinessError("producer readiness: invalid identity")
    if record["mode"] not in {"nonempty-candidates", "empty-by-decision"}:
        raise ReadinessError("producer readiness: invalid mode")
    _strings(record["roots"], "roots", required=True)
    _strings(record["exclusions"], "exclusions")
    if not isinstance(record["command"], str) or not record["command"] or not isinstance(record["predicate"], str) or not record["predicate"]:
        raise ReadinessError("producer readiness: command/predicate required")
    if isinstance(record["candidate_count"], bool) or not isinstance(record["candidate_count"], int) or record["candidate_count"] < 0:
        raise ReadinessError("producer readiness: candidate_count invalid")
    if not _SHA.fullmatch(record["candidate_paths_sha256"]) or not _COMMIT.fullmatch(record["source_commit"]):
        raise ReadinessError("producer readiness: digest/commit invalid")
    if record["mode"] == "nonempty-candidates" and record["candidate_count"] == 0:
        raise ReadinessError("nonempty-candidates requires candidate_count > 0")
    if record["mode"] == "empty-by-decision":
        if record["candidate_count"] != 0 or not _DECISION.fullmatch(record["owner_decision"]):
            raise ReadinessError("empty-by-decision requires zero candidates and D#")
        if plan_dir is not None and not _accepted_decision(Path(plan_dir), record["owner_decision"]):
            raise ReadinessError("empty-by-decision requires one accepted owner D#")


def readiness_digest(record: dict) -> str:
    validate_readiness(record)
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_reentry(record: dict) -> None:
    _closed(record, {"schema_version", "phase_id", "trigger", "evidence_ids", "origin_item", "resume_item"}, "phase reentry")
    if record["schema_version"] != "phase-reentry-justification/v1" or not _PHASE.fullmatch(record["phase_id"]) \
            or not _ITEM.fullmatch(record["origin_item"]) or not _ITEM.fullmatch(record["resume_item"]):
        raise ReadinessError("phase reentry: invalid identity")
    if record["trigger"] not in {"owner-decision-change", "terminal-evidence-invalid", "safety-or-authority-boundary"}:
        raise ReadinessError("phase reentry: trigger is not allowed")
    _strings(record["evidence_ids"], "evidence_ids", required=True)


def validate_fix_branch(record: dict, *, declared_items=()) -> None:
    fields = {"schema_version", "origin_item", "owner", "scope", "priority", "rollback", "validation", "target_item", "resume_item"}
    _closed(record, fields, "fix branch")
    if record["schema_version"] != "fix-branch/v1" or record["priority"] != "priority":
        raise ReadinessError("fix branch: invalid version or priority")
    for field in ("origin_item", "target_item", "resume_item"):
        if not _ITEM.fullmatch(record[field]):
            raise ReadinessError(f"fix branch: {field} must be Pn.m")
    for field in ("owner", "scope", "rollback", "validation"):
        if not isinstance(record[field], str) or not record[field]:
            raise ReadinessError(f"fix branch: {field} required")
    if declared_items and record["target_item"] not in set(declared_items):
        raise ReadinessError("fix branch: target item is not declared")


def correction_decision(*, observed_mode: str, reentry: dict | None = None,
                        fix_branch: dict | None = None, declared_items=()) -> dict:
    """Reduce producer/re-entry facts to one closed continuation action."""
    if observed_mode not in _OBSERVED_MODES:
        raise ReadinessError("correction: observed mode is not allowed")
    if reentry is not None and fix_branch is not None:
        raise ReadinessError("correction: reentry and fix branch are mutually exclusive")
    if reentry is not None:
        validate_reentry(reentry)
    if fix_branch is not None:
        validate_fix_branch(fix_branch, declared_items=declared_items)

    if observed_mode in {"approved-no-op", "valid-output"}:
        if reentry is not None or fix_branch is not None:
            raise ReadinessError("correction: verified producer mode forbids re-entry or priority fix")
        action, reason = "continue-current", "PRODUCER_ALREADY_READY"
    elif reentry is not None:
        if observed_mode != "contract-conflict":
            raise ReadinessError("correction: reopen requires a proved contract conflict")
        action, reason = "reopen-phase", "PHASE_REENTRY_JUSTIFIED"
    elif fix_branch is not None:
        action, reason = "priority-fix", "DECLARED_PRIORITY_FIX"
    elif observed_mode in {"stale-derived", "missing-or-corrupt"}:
        action, reason = "repair-in-current-attempt", "PRODUCER_REPAIR_REQUIRED"
    else:
        action, reason = "gather-evidence", "REENTRY_EVIDENCE_REQUIRED"

    decision = {
        "signal_class": "producer-readiness",
        "scope_class": "item",
        "action": action,
        "recovered": action in {"continue-current", "repair-in-current-attempt", "priority-fix"},
        "terminal": False,
        "reason_code": reason,
        "observed_mode": observed_mode,
    }
    if reentry is not None:
        decision["phase_reentry"] = reentry
    if fix_branch is not None:
        decision["fix_branch"] = fix_branch
    return decision


def latest_correction(plan_dir) -> dict | None:
    """Return the latest unconsumed producer/re-entry decision from the journal."""
    path = Path(plan_dir) / "journal.jsonl"
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    latest = None
    latest_index = None
    events = []
    from task import journal
    for index, raw in enumerate(rows):
        try:
            event = json.loads(raw)
            journal.validate_entry(event)
        except (json.JSONDecodeError, journal.JournalValidationError):
            continue
        events.append((index, event))
        decision = event.get("decision")
        if not isinstance(decision, dict) or decision.get("signal_class") != "producer-readiness":
            continue
        try:
            expected = correction_decision(
                observed_mode=decision.get("observed_mode"),
                reentry=decision.get("phase_reentry"),
                fix_branch=decision.get("fix_branch"),
            )
        except ReadinessError:
            continue
        if set(decision) == set(expected) and all(
                decision.get(key) == value for key, value in expected.items()):
            latest = decision
            latest_index = index
    if latest is None:
        return None
    for index, event in events:
        if index <= latest_index:
            continue
        subject = str(event.get("item_id") or "")
        command = event.get("command")
        if latest["action"] == "reopen-phase":
            phase = latest["phase_reentry"]["phase_id"]
            if command == "plan-design" and (subject == phase or subject.startswith(phase + ".")):
                return None
        if latest["action"] == "priority-fix":
            target = latest["fix_branch"]["target_item"]
            if command in {"plan-exec", "plan-run", "plan-close"} and subject == target:
                return None
    return latest


def validate_execution_target(plan_dir, item_ids) -> None:
    """Bind an active priority-fix route to its one declared target item."""
    decision = latest_correction(plan_dir)
    if not isinstance(decision, dict) or decision.get("action") != "priority-fix":
        return
    requested = tuple(item_ids)
    expected = (decision["fix_branch"]["target_item"],)
    if requested != expected:
        raise ReadinessError(
            f"PRIORITY_FIX_TARGET_MISMATCH: expected {expected[0]}, got {list(requested)}")


def validate_design_target(plan_dir, phase_id: str) -> None:
    """Require an exact re-entry decision before design targets a terminal phase."""
    from task import plan_layout

    plan_dir = Path(plan_dir)
    statuses = []
    for spec in plan_layout.item_spec_paths(plan_dir, phase_id):
        state_path = spec.with_name(spec.stem + ".state.md")
        try:
            text = state_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        match = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", text, re.MULTILINE)
        if match is None:
            return
        statuses.append(match.group(1))
    terminal = {"🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision"}
    if not statuses or not all(status in terminal for status in statuses):
        return
    decision = latest_correction(plan_dir)
    record = (decision or {}).get("phase_reentry")
    if (not isinstance(decision, dict) or decision.get("action") != "reopen-phase"
            or not isinstance(record, dict) or record.get("phase_id") != phase_id):
        raise ReadinessError(
            f"PHASE_REENTRY_UNJUSTIFIED: terminal phase {phase_id} requires re-entry evidence")


def terminal_projection(record: dict, *, plan_dir: Path | None = None) -> dict:
    """Return the only consumer-visible, digest-bound subset."""
    validate_readiness(record, plan_dir=plan_dir)
    return {"schema_version": "producer-readiness-projection/v1", "digest": readiness_digest(record),
            "producer_item": record["producer_item"], "consumer_item": record["consumer_item"],
            "mode": record["mode"], "candidate_count": record["candidate_count"],
            "source_commit": record["source_commit"]}
