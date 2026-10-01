"""journal — append-only writer of the per-plan execution log
`plans/<PLAN-ID>/journal.jsonl` (diagram sealed v1,
) and optional append-only sidecar
`journal-exceptions.jsonl` for owner-gated historical schema exceptions.

One entry = one line of valid JSON (NDJSON, D20). The entry is only APPENDING -
existing lines are never overwritten/are not deleted (§1 contract); therefore
`append()` opens the file in `"a"` and does EXACTLY one `write()` to write -
concurrent sessions add their own line without someone else's line break (git-merge
resolved by string concatenation, contract §1).

Called close-command protocol `/task:plan-*` — start-record
(`result="in-progress"`) at the beginning of execution item'ah, final recording (terminal
`result` + baked cost/turns/duration) when closing (contract §2, «pair of records»).

stdlib-only (json/argparse/pathlib) — package convention task."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

try:
    # core.term.now_iso — same format as schema §2 (`2026-07-18T18:42:07Z`).
    # core/ optional (standalone-package layout without monorepo parent, like
    # y task.plan_lint) — the fallback below gives the same byte-for-byte format.
    from core.term import now_iso as _now_iso
except ImportError:  # pragma: no cover - standalone-fallback
    from datetime import datetime, timezone

    def _now_iso():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

FILENAME = "journal.jsonl"
EXCEPTIONS_FILENAME = "journal-exceptions.jsonl"
NOTE_MAX_CHARS = 300
UPDATE_LOG_WHAT_MAX_CHARS = 300

# --- schema canon -----
COMMANDS = ("plan-run", "plan-exec", "plan-close", "plan-audit", "plan-design")
# Readers accept the legacy spelling; writers emit only the canonical command.
LEGACY_COMMAND_ALIASES = {"plan-exec": "plan-run"}


def canonical_command(command: str) -> str:
    """Map a legacy command spelling (`plan-exec`) to its canonical name (`plan-run`)."""
    return LEGACY_COMMAND_ALIASES.get(command, command)

FRICTION_VALUES = (
    "escalation", "routing-blocked", "route-deviation", "red-audit", "deviation", "retry", "no-op",
    "local-repair", "block-review", "external-evidence",
)
RESULT_VALUES = (
    "in-progress", "closed-green", "closed-deviations", "blocked",
    "escalated", "no-op", "audit-green", "audit-attention", "audit-red",
    "routing-rejected", "decision-pending", "local-repair", "rag-pending", "block-candidate",
)
TERMINAL_CLOSE_RESULTS = ("closed-green", "closed-deviations", "blocked", "escalated")
REQUIRED_FIELDS = (
    "ts", "plan_id", "item_id", "command", "session_id", "run_id", "attempt",
    "actor", "friction", "result", "cost_usd", "num_turns", "duration_ms", "note",
)
EXCEPTION_REQUIRED_FIELDS = (
    "ts", "plan_id", "target_line", "target_sha256", "invalid_fields",
    "owner_decision", "actor", "reason",
)
# v1 is intentionally narrow: exception does not become a general cancellation mechanism schema.
EXEMPTABLE_FIELDS = ("friction",)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DECISION_RE = re.compile(r"^D[1-9][0-9]*$")
_UTC_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_EXCEPTION_GRANT_RE = re.compile(
    r"\[JOURNAL-EXCEPTION:(?P<digest>[0-9a-f]{64})\]\s*\n"
    r"fields=`(?P<fields>[^`]*)`;\s*\n"
    r"plan=`(?P<plan>[^`]*)`;\s*\n"
    r"item=`(?P<item>[^`]*)`",
)


class JournalValidationError(ValueError):
    """Recording failed schema-validation - `append()` does not write a line."""


def entry_validation_errors(entry):
    """Returns schema-violations as pairs ``(field, message)``.

    Field required linter'y for exact matching with owner-gated historical exception;
    normal writer still uses :func:`validate_entry` and fail-closed."""
    if not isinstance(entry, dict):
        return [("$", "entry must be dict")]

    errors = [(f, f"no required field «{f}»")
              for f in REQUIRED_FIELDS if f not in entry]
    if errors:
        return errors

    def _check_str(name, *, allow_none=False, allow_empty=False):
        v = entry[name]
        if v is None and allow_none:
            return
        if not isinstance(v, str) or (not allow_empty and not v):
            errors.append((
                name,
                f"{name}: must be {'str|null' if allow_none else 'non-empty str'}",
            ))

    def _check_number(name):
        v = entry[name]
        if (v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                               or not math.isfinite(v) or v < 0)):
            errors.append((name, f"{name}: must be finite number ≥0|null"))

    _check_str("ts")
    _check_str("plan_id")
    _check_str("item_id") # always set (narrowing str|null, §5)
    _check_str("session_id", allow_none=True)
    _check_str("run_id", allow_none=True)
    _check_str("actor")
    _check_str("note", allow_none=True)
    try:
        _parse_utc(entry["ts"])
    except ValueError as exc:
        errors.append(("ts", str(exc)))

    if entry["command"] not in COMMANDS:
        errors.append(("command", f"command: «{entry['command']}» is not included {COMMANDS}"))
    if entry["result"] not in RESULT_VALUES:
        errors.append(("result", f"result: «{entry['result']}» is not included {RESULT_VALUES}"))

    attempt = entry["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        errors.append(("attempt", "attempt: must be int ≥1"))

    friction = entry["friction"]
    if not isinstance(friction, list) or any(v not in FRICTION_VALUES for v in friction):
        errors.append((
            "friction",
            f"friction: must be an array of values from {FRICTION_VALUES}",
        ))

    for name in ("cost_usd", "duration_ms"):
        _check_number(name)
    turns = entry["num_turns"]
    if turns is not None and (isinstance(turns, bool) or not isinstance(turns, int) or turns < 0):
        errors.append(("num_turns", "num_turns: must be int ≥0|null"))

    fingerprint = entry.get("fingerprint")
    if fingerprint is not None and (
            not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint)):
        errors.append(("fingerprint", "fingerprint: must be lowercase SHA-256|null"))
    decision = entry.get("decision")
    if decision is not None:
        required = {"signal_class", "scope_class", "action", "recovered", "terminal"}
        if not isinstance(decision, dict) or not required <= set(decision):
            errors.append(("decision", "decision: missing required fields evidence"))
    if "batch_receipt" in entry:
        try:
            from task.task_contract import validate_batch_receipt
            validate_batch_receipt(entry["batch_receipt"])
        except (ImportError, ValueError) as exc:
            errors.append(("batch_receipt", f"batch_receipt: {exc}"))
    if "repair_decision" in entry:
        try:
            from task import plan_repair
            plan_repair.validate(entry["repair_decision"])
            if entry.get("repair_digest") != plan_repair.digest(entry["repair_decision"]):
                raise ValueError("repair_digest does not match record")
            action = entry.get("repair_action")
            if action not in plan_repair._ACTIONS:
                raise ValueError("unknown repair_action")
            if (action == "repair-in-current-attempt"
                    and entry.get("result") in TERMINAL_CLOSE_RESULTS):
                raise ValueError("qualified repair cannot write terminal result")
            if (entry.get("command") == "plan-design"
                    and action != "design-required"):
                raise ValueError("plan-design requires repair action design-required")
        except (ImportError, ValueError) as exc:
            errors.append(("repair_decision", f"repair_decision: {exc}"))
    if "candidate_snapshot" in entry:
        snapshot = entry["candidate_snapshot"]
        required_snapshot = {"phase_id", "terminal_item_heads", "declared_files", "product_tree_sha256"}
        if (entry.get("command") != "plan-audit" or not isinstance(snapshot, dict)
                or not required_snapshot <= set(snapshot)):
            errors.append(("candidate_snapshot", "candidate_snapshot valid only as full audit candidate"))

    return errors


def _parse_utc(value, *, field="ts"):
    if not isinstance(value, str) or not _UTC_TS_RE.fullmatch(value):
        raise ValueError(f"{field}: must be strict UTC timestamp with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field}: calendar invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field}: must be UTC")
    return parsed


def validate_entry(entry):
    """Verifies event-record with schema (§2), accumulating all the violations at once."""
    errors = entry_validation_errors(entry)
    if errors:
        raise JournalValidationError("; ".join(message for _, message in errors))


def validate_append_policy(entry, *, plan_dir=None):
    """Validate forward-only writer policy outside the sealed event schema.

    Historical rows with longer notes remain schema-valid and readable.  Only a
    new append is rejected, before any bytes are written.
    """
    note = entry.get("note") if isinstance(entry, dict) else None
    if (isinstance(entry, dict) and plan_dir is not None
            and entry.get("command") == "plan-audit"
            and entry.get("item_id") == "design"):
        from task import plan_readiness
        if plan_readiness.design_gate_enabled(plan_dir):
            try:
                snapshot = plan_readiness.design_snapshot(plan_dir)
            except (ValueError, OSError) as exc:
                raise JournalValidationError(f"PLAN_DESIGN_INCOMPLETE: {exc}") from exc
            if entry.get("fingerprint") != snapshot["fingerprint"]:
                raise JournalValidationError(
                    "PLAN_DESIGN_AUDIT_STALE: audit fingerprint does not match design inputs")
            events = [json.loads(line) for line in (Path(plan_dir) / FILENAME).read_text(
                encoding="utf-8").splitlines() if line.strip()]
            if not any(event.get("command") == "plan-design"
                       and event.get("item_id") == "finish"
                       and event.get("fingerprint") == snapshot["fingerprint"]
                       for event in events):
                raise JournalValidationError("PLAN_DESIGN_FINISH_MISSING: first finalize-design --finish")
    if isinstance(entry, dict) and "repair_decision" in entry:
        from task import plan_repair
        if entry.get("repair_action") != plan_repair.evaluate(entry["repair_decision"], plan_dir=plan_dir)["action"]:
            raise JournalValidationError("repair_action does not match current reducer result")
    if isinstance(note, str) and len(note) > NOTE_MAX_CHARS:
        raise JournalValidationError(
            f"note: {len(note)} characters > {NOTE_MAX_CHARS}; "
            "take the details to Completion Notes/findings")
    if (isinstance(entry, dict) and entry.get("command") == "plan-audit"
            and re.fullmatch(r"P\d+", str(entry.get("item_id", "")))
            and (entry.get("result") == "in-progress" or entry.get("run_id") is not None)):
        # Admission applies to live runs. Historical terminal rows with no run
        # identity remain readable/importable; they never authorize a new run.
        from task import audit_admission, plan_gates
        if plan_dir is None or not entry.get("run_id"):
            raise JournalValidationError("AUDIT_CONSENT_INVALID: phase audit requires plan_dir and run_id")
        try:
            candidate = plan_gates.phase_candidate_fingerprint(plan_dir, entry["item_id"])
        except (OSError, ValueError, KeyError) as exc:
            raise JournalValidationError(f"AUDIT_CANDIDATE_UNRESOLVED: {exc}") from exc
        if entry.get("fingerprint") != candidate["fingerprint"]:
            raise JournalValidationError("AUDIT_CANDIDATE_MISMATCH: fingerprint does not match current candidate")
        admission = audit_admission.evaluate(
            Path(plan_dir), entry["item_id"], candidate["snapshot"], run_id=entry["run_id"])
        if not admission["allowed"]:
            raise JournalValidationError(f"{admission['code']}: no targeted consent for phase audit")
        if (entry.get("result") == "in-progress"
                and audit_admission._journal_state(Path(plan_dir), admission["record"]) != "available"):
            raise JournalValidationError("AUDIT_RUN_ALREADY_STARTED: continue current audit run")
    if (isinstance(entry, dict) and entry.get("command") == "plan-audit"
            and entry.get("result") in {"audit-green", "audit-attention", "audit-red"}):
        from task import review_policy
        if review_policy.phase_audit_subject(entry.get("item_id")) is not None:
            try:
                review_policy.phase_audit_terminal_policy(entry, plan_dir=plan_dir)
            except review_policy.ReviewPolicyError as exc:
                raise JournalValidationError(str(exc)) from exc
    if isinstance(entry, dict):
        from task import terminal_policy
        try:
            terminal_policy.validate_entry(
                entry, plan_dir=Path(plan_dir) if plan_dir is not None else None)
        except terminal_policy.TerminalPolicyError as exc:
            raise JournalValidationError(str(exc)) from exc


def project_update_log_what(entry, line_number):
    """Return the bounded owner-facing ``What`` cell for one journal row.

    The immutable journal remains the full source.  A projection that would
    exceed the owner-view limit is replaced by a deterministic line pointer.
    """
    note = str(entry.get("note") or "—")
    command = str(entry.get("command") or "—")
    result = str(entry.get("result") or "—")
    what = " · ".join((command, result, note))
    if len(what) <= UPDATE_LOG_WHAT_MAX_CHARS:
        return what
    return f"{command} · {result} · note abbreviated; full text: {FILENAME}:{line_number}"


def validate_exception(exception):
    """Validates one record sidecar-schemas historical schema exception v1."""
    if not isinstance(exception, dict):
        raise JournalValidationError("schema exception must be dict")
    errors = [f"no required field «{f}»"
              for f in EXCEPTION_REQUIRED_FIELDS if f not in exception]
    unknown = sorted(set(exception) - set(EXCEPTION_REQUIRED_FIELDS))
    if unknown:
        errors.append(f"unknown fields schema exception: {unknown}")
    if errors:
        raise JournalValidationError("; ".join(errors))

    for name in ("ts", "plan_id", "actor", "reason"):
        value = exception[name]
        if not isinstance(value, str) or not value:
            errors.append(f"{name}: must be non-empty str")
    try:
        _parse_utc(exception["ts"])
    except ValueError as exc:
        errors.append(str(exc))

    target_line = exception["target_line"]
    if isinstance(target_line, bool) or not isinstance(target_line, int) or target_line < 1:
        errors.append("target_line: must be int ≥1")
    target_sha256 = exception["target_sha256"]
    if not isinstance(target_sha256, str) or not _SHA256_RE.fullmatch(target_sha256):
        errors.append("target_sha256: must be lowercase SHA-256")
    invalid_fields = exception["invalid_fields"]
    if (not isinstance(invalid_fields, list) or not invalid_fields
            or len(invalid_fields) != len(set(invalid_fields))
            or any(v not in EXEMPTABLE_FIELDS for v in invalid_fields)):
        errors.append(
            f"invalid_fields: non-empty unique-array of values from {EXEMPTABLE_FIELDS}")
    owner_decision = exception["owner_decision"]
    if not isinstance(owner_decision, str) or not _DECISION_RE.fullmatch(owner_decision):
        errors.append("owner_decision: must be D#")

    if errors:
        raise JournalValidationError("; ".join(errors))


def line_sha256(raw_line):
    """SHA-256 accurate UTF-8 bytes lines journal without trailing newline."""
    return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()


def derive_run_id(*, plan_id, item_id, attempt, session_id):
    """Return one deterministic identity for a start/terminal execution pair."""
    if (not all(isinstance(value, str) and value for value in (plan_id, item_id, session_id))
            or isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1):
        raise JournalValidationError(
            "run_id: plan_id/item_id/session_id and attempt ≥1 are required")
    value = "\0".join((plan_id, item_id, str(attempt), session_id))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_exception(*, plan_id, target_line, target_sha256, invalid_fields,
                  owner_decision, actor, reason, ts=None):
    """Collects owner-gated sidecar-record without change historical journal bytes."""
    return {
        "ts": ts or _now_iso(),
        "plan_id": plan_id,
        "target_line": target_line,
        "target_sha256": target_sha256,
        "invalid_fields": list(invalid_fields),
        "owner_decision": owner_decision,
        "actor": actor,
        "reason": reason,
    }


def validate_exception_target(plan_dir, exception, *, check_duplicate=True):
    """Checks provenance, owner gate and the exact set waived schema-fields.

    Sidecar is physically separated from event-log, so exception cannot reference
    to another exception and correction-loop is structurally impossible.
    """
    validate_exception(exception)
    plan_dir = Path(plan_dir)
    canonical_plan_id = plan_dir.name
    if exception["plan_id"] != canonical_plan_id:
        raise JournalValidationError(
            f"exception: plan_id «{exception['plan_id']}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")
    from task import plan_layout
    try:
        journal_path = plan_layout.carrier_path(plan_dir, "journal")
    except plan_layout.PlanLayoutError as exc:
        raise JournalValidationError(f"journal: media does not resolve: {exc}") from exc
    try:
        lines = journal_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalValidationError(f"target journal is not readable: {exc}") from exc

    target_line = exception["target_line"]
    if target_line > len(lines) or not lines[target_line - 1].strip():
        raise JournalValidationError("target_line: no such non-empty string journal")
    raw_line = lines[target_line - 1]
    if line_sha256(raw_line) != exception["target_sha256"]:
        raise JournalValidationError("target_sha256: does not match raw journal line")
    try:
        target = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise JournalValidationError(
            "target: malformed JSON does not allow schema exception") from exc
    target_plan_id = target.get("plan_id") if isinstance(target, dict) else None
    if target_plan_id != canonical_plan_id:
        raise JournalValidationError(
            f"target event: plan_id «{target_plan_id}» ≠ canonical plan directory "
            f"«{canonical_plan_id}»")

    target_errors = entry_validation_errors(target)
    target_fields = {field for field, _ in target_errors}
    if not target_errors:
        raise JournalValidationError("target: line is already running")
    if target_fields != set(exception["invalid_fields"]):
        raise JournalValidationError(
            f"invalid_fields: expected exact set {sorted(target_fields)}")

    from task import plan_decisions
    try:
        decisions = plan_decisions.load_decisions(plan_dir)
    except (OSError, UnicodeDecodeError, plan_layout.PlanLayoutError,
            plan_decisions.DecisionError) as exc:
        raise JournalValidationError(f"owner_decision: decision media is invalid: {exc}") from exc
    matches = [decision for decision in decisions
               if decision.identifier == exception["owner_decision"]]
    if len(matches) != 1:
        raise JournalValidationError("owner_decision: requires exactly one permit D#")
    decision = matches[0]
    target_item = target.get("item_id")
    if (decision.status != "accepted" or decision.superseded_by is not None
            or target_item not in decision.items):
        raise JournalValidationError(
            "owner_decision: no solution accepted/current or not related target item")
    grants = list(_EXCEPTION_GRANT_RE.finditer(decision.body))
    expected_fields = ",".join(sorted(exception["invalid_fields"]))
    if len(grants) != 1:
        raise JournalValidationError("owner_decision: exactly one is required JOURNAL-EXCEPTION grant")
    grant = grants[0].groupdict()
    if grant != {"digest": exception["target_sha256"], "fields": expected_fields,
                  "plan": canonical_plan_id, "item": target_item}:
        raise JournalValidationError("owner_decision: JOURNAL-EXCEPTION grant is not associated with exact target/scope")

    if check_duplicate:
        exceptions_path = plan_dir / EXCEPTIONS_FILENAME
        if exceptions_path.is_file():
            try:
                existing_lines = exceptions_path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                raise JournalValidationError(
                    f"existing exception sidecar is not readable: {exc}") from exc
            for raw in existing_lines:
                if not raw.strip():
                    continue
                try:
                    existing = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if (isinstance(existing, dict)
                        and existing.get("target_line") == target_line
                        and existing.get("target_sha256") == exception["target_sha256"]):
                    raise JournalValidationError("target: exception already exists")


def new_entry(*, plan_id, item_id, command, actor, result, session_id=None, run_id=None,
              attempt=1, friction=(), cost_usd=None, num_turns=None, duration_ms=None,
              note=None, ts=None, trace_ref=None, fingerprint=None, decision=None,
              batch_receipt=None, candidate_snapshot=None, second_full_justification=None):
    """Collects a record according to the scheme with contract defaults (§2) — single assembly point,
    to close-command log was not collected dict manually in scattered fields.

    `trace_ref`
    — ADDITIVE optional linkage to a Unified Agent Trace `trace_id`, outside
    `REQUIRED_FIELDS`: omitted (`None`, the default) it is not written at all, so
    every caller that does not pass it gets a byte-identical entry to before this
    field existed. The journal never carries trace METRICS, only this pointer."""
    entry = {
        "ts": ts or _now_iso(),
        "plan_id": plan_id,
        "item_id": _canonical_phase_audit_item_id(command, item_id),
        "command": command,
        "session_id": session_id,
        "run_id": run_id,
        "attempt": attempt,
        "actor": actor,
        "friction": list(friction),
        "result": result,
        "cost_usd": cost_usd,
        "num_turns": num_turns,
        "duration_ms": duration_ms,
        "note": note,
    }
    if trace_ref is not None:
        entry["trace_ref"] = trace_ref
    if fingerprint is not None:
        entry["fingerprint"] = fingerprint
    if decision is not None:
        entry["decision"] = dict(decision)
    if batch_receipt is not None:
        entry["batch_receipt"] = dict(batch_receipt)
    if candidate_snapshot is not None:
        entry["candidate_snapshot"] = dict(candidate_snapshot)
    if second_full_justification is not None:
        entry["second_full_justification"] = dict(second_full_justification)
    return entry


def _canonical_phase_audit_item_id(command, item_id):
    """New audit writers emit only canonical Pn; historical rows remain readable."""
    if command != "plan-audit":
        return item_id
    from task import review_policy
    return review_policy.phase_audit_subject(item_id) or item_id


@contextmanager
def _journal_lock(plan_dir):
    plan_dir = Path(plan_dir)
    cache = plan_dir / ".plan-cache"
    cache.mkdir(parents=True, exist_ok=True)
    if cache.is_symlink() or not cache.is_dir() or not hasattr(os, "O_NOFOLLOW"):
        raise JournalValidationError("JOURNAL_DURABILITY_FAILED: lock domain is insecure")
    path = cache / "journal.lock"
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise JournalValidationError(f"JOURNAL_DURABILITY_FAILED: lock not available: {exc}") from exc
    try:
        with os.fdopen(descriptor, "a+") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            yield
    finally:
        pass


def _read_json_lines(path, *, validator, label):
    path = Path(path)
    if not path.exists():
        return []
    if path.is_symlink():
        raise JournalValidationError(f"JOURNAL_CORRUPT: {label} is symlink")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise JournalValidationError(f"JOURNAL_CORRUPT: {label} not regular file")
        with os.fdopen(descriptor, "rb") as stream:
            payload = stream.read()
        text = payload.decode("utf-8")
    except JournalValidationError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise JournalValidationError(f"JOURNAL_CORRUPT: {label} is not readable: {exc}") from exc
    records = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
            validator(record)
        except (json.JSONDecodeError, JournalValidationError) as exc:
            raise JournalValidationError(
                f"JOURNAL_CORRUPT: {label}:{line_number}: {exc}") from exc
        records.append((line_number, raw, record))
    return records


_HISTORICAL_ABSENT_NEUTRAL = frozenset(("friction", "cost_usd", "num_turns", "duration_ms"))


def _historical_schema_errors(entry):
    """Historical rows may omit neutral metric fields; free-form values stay invalid.

    New appends still pass through :func:`validate_entry`.  This filter is only
    the read of an already durable journal.
    """
    return [
        (field, message)
        for field, message in entry_validation_errors(entry)
        if not (field in _HISTORICAL_ABSENT_NEUTRAL
                and str(message).startswith("no required field"))
    ]


def _sidecar_waivers(plan_dir, journal_rows, sidecar_rows):
    """Bind an existing sidecar to exact lines without requiring a later grant marker.

    Decisions accepted before the JOURNAL-EXCEPTION grant stay authoritative
    when they name the target item.  A decision that already carries grants must
    match one of them; a sha or field mismatch never becomes a waiver.
    """
    from task import plan_decisions

    try:
        decisions = plan_decisions.load_decisions(plan_dir)
    except (OSError, UnicodeDecodeError, plan_decisions.DecisionError) as exc:
        raise JournalValidationError(
            f"owner_decision: decision media is invalid: {exc}") from exc
    by_id = {}
    for decision in decisions:
        by_id.setdefault(decision.identifier, []).append(decision)
    by_line = {line_number: (raw, record) for line_number, raw, record in journal_rows}
    waivers = {}
    for _sidecar_line, _raw_exception, exception in sidecar_rows:
        target_line = exception["target_line"]
        if target_line not in by_line:
            raise JournalValidationError("target_line: no such non-empty string journal")
        raw, record = by_line[target_line]
        if line_sha256(raw) != exception["target_sha256"]:
            raise JournalValidationError("target_sha256: does not match raw journal line")
        fields = {field for field, _message in _historical_schema_errors(record)}
        if fields != set(exception["invalid_fields"]):
            raise JournalValidationError(
                f"invalid_fields: expected exact set {sorted(fields)}")
        matches = by_id.get(exception["owner_decision"], [])
        if len(matches) != 1:
            raise JournalValidationError("owner_decision: requires exactly one permit D#")
        decision = matches[0]
        target_item = record.get("item_id") if isinstance(record, dict) else None
        if (decision.status != "accepted" or decision.superseded_by is not None
                or target_item not in decision.items):
            raise JournalValidationError(
                "owner_decision: no solution accepted/current or not related target item")
        grants = list(_EXCEPTION_GRANT_RE.finditer(decision.body))
        if grants:
            expected_fields = ",".join(sorted(exception["invalid_fields"]))
            expected = {"digest": exception["target_sha256"], "fields": expected_fields,
                        "plan": Path(plan_dir).name, "item": target_item}
            if not any(grant.groupdict() == expected for grant in grants):
                raise JournalValidationError(
                    "owner_decision: JOURNAL-EXCEPTION grant is not associated with exact target/scope")
        waivers[(target_line, exception["target_sha256"])] = fields
    return waivers


def _authoritative_state_locked(plan_dir, *, allow_invalid_target=None):
    plan_dir = Path(plan_dir)
    journal_rows = _read_json_lines(
        plan_dir / FILENAME, validator=lambda record: None, label=FILENAME)
    sidecar_path = plan_dir / EXCEPTIONS_FILENAME
    sidecar_rows = _read_json_lines(
        sidecar_path, validator=validate_exception, label=EXCEPTIONS_FILENAME)
    waivers = _sidecar_waivers(plan_dir, journal_rows, sidecar_rows) if sidecar_rows else {}
    for line_number, raw, record in journal_rows:
        errors = _historical_schema_errors(record)
        if not errors:
            continue
        digest = line_sha256(raw)
        allowed = (allow_invalid_target is not None
                   and line_number == allow_invalid_target[0]
                   and digest == allow_invalid_target[1])
        if not allowed and waivers.get((line_number, digest)) != {field for field, _message in errors}:
            message = "; ".join(error for _field, error in errors)
            raise JournalValidationError(
                f"JOURNAL_CORRUPT: {FILENAME}:{line_number}: {message}")
    targets = [(row[2]["target_line"], row[2]["target_sha256"]) for row in sidecar_rows]
    if len(targets) != len(set(targets)):
        raise JournalValidationError("JOURNAL_CORRUPT: duplicate schema exception")
    return journal_rows, sidecar_rows


def read_authoritative_entries(plan_dir):
    """Read validated history, including exact owner-approved schema exceptions."""
    rows, _exceptions = _authoritative_state_locked(plan_dir)
    return [record for _line_number, _raw, record in rows]


def _write_line_durable(path, line):
    path = Path(path)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise JournalValidationError("JOURNAL_DURABILITY_FAILED: append target not regular file")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
    payload = (line + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise JournalValidationError("JOURNAL_DURABILITY_FAILED: append target not regular file")
            cursor = 0
            while cursor < len(payload):
                written = os.write(descriptor, payload[cursor:])
                if written <= 0:
                    raise OSError("short append")
                cursor += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except JournalValidationError:
        raise
    except OSError as exc:
        raise JournalValidationError(f"JOURNAL_DURABILITY_FAILED: {exc}") from exc


def _validate_terminal_order(rows, entry):
    if entry.get("result") not in TERMINAL_CLOSE_RESULTS or not entry.get("run_id"):
        return
    identity = (entry.get("item_id"), entry.get("attempt"), entry.get("run_id"))
    starts = [record for _line, _raw, record in rows
              if (record.get("item_id"), record.get("attempt"), record.get("run_id")) == identity
              and record.get("result") == "in-progress"]
    if not starts:
        raise JournalValidationError("JOURNAL_CONFLICT: terminal without start")
    if len(starts) != 1:
        raise JournalValidationError("JOURNAL_CONFLICT: terminal requires exactly one start")
    if _parse_utc(entry["ts"]) < _parse_utc(starts[0]["ts"]):
        raise JournalValidationError("JOURNAL_CONFLICT: terminal timestamp before start")


def _append_locked(plan_dir, entry, rows, *, enforce_terminal_order=False):
    canonical_plan_id = Path(plan_dir).name
    if entry["plan_id"] != canonical_plan_id:
        raise JournalValidationError(
            f"event plan_id «{entry['plan_id']}» ≠ canonical plan directory «{canonical_plan_id}»")
    if enforce_terminal_order:
        _validate_terminal_order(rows, entry)
    path = Path(plan_dir) / FILENAME
    _write_line_durable(path, json.dumps(entry, ensure_ascii=False, sort_keys=True))
    return path


def append(plan_dir, entry):
    """Adds ONE entry to `plans/<ID>/journal.jsonl`. Validates BEFORE writing
    (§2) — broken record is not included in durable-plan history (§1). Returns the path
    file. No file - being created (append-mode creates itself)."""
    validate_entry(entry)
    plan_dir = Path(plan_dir)
    with _journal_lock(plan_dir):
        rows, _exceptions = _authoritative_state_locked(plan_dir)
        validate_append_policy(entry, plan_dir=plan_dir)
        return _append_locked(plan_dir, entry, rows)


def append_idempotent_terminal(plan_dir, entry):
    """Append one terminal, or return its existing line without changing bytes."""
    validate_entry(entry)
    plan_dir = Path(plan_dir)
    path = plan_dir / FILENAME
    with _journal_lock(plan_dir):
        rows, _exceptions = _authoritative_state_locked(plan_dir)
        validate_append_policy(entry, plan_dir=plan_dir)
        if entry.get("result") not in TERMINAL_CLOSE_RESULTS or not entry.get("run_id"):
            return _append_locked(plan_dir, entry, rows), None, True
        for line_number, _raw, current in rows:
            identity = (entry.get("item_id"), entry.get("attempt"), entry.get("run_id"))
            if (current.get("item_id"), current.get("attempt"), current.get("run_id")) != identity:
                continue
            if current.get("result") not in TERMINAL_CLOSE_RESULTS:
                continue
            if all(current.get(field) == entry.get(field) for field in ("result", "fingerprint")):
                return path, line_number, False
            raise JournalValidationError(
                f"terminal conflict: run_id is already closed in {FILENAME}:{line_number}")
        return _append_locked(
            plan_dir, entry, rows, enforce_terminal_order=True), None, True


def append_exception(plan_dir, exception):
    """Append-only adds exactly one owner-gated historical schema exception."""
    validate_exception(exception)
    with _journal_lock(plan_dir):
        _authoritative_state_locked(
            plan_dir,
            allow_invalid_target=(exception["target_line"], exception["target_sha256"]),
        )
        validate_exception_target(plan_dir, exception)
        path = Path(plan_dir) / EXCEPTIONS_FILENAME
        _write_line_durable(path, json.dumps(exception, ensure_ascii=False, sort_keys=True))
        return path


# --- CLI: `python3 -m task.journal append --plan … --item … …` (call from commands) --

def _parse_friction(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _build_arg_parser():
    p = argparse.ArgumentParser(
        prog="task.journal", description="Append-only plan execution log (P1.1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("append", help="add entry to plans/<ID>/journal.jsonl")
    ap.add_argument("--plan-dir", required=True, help="plan directory plans/<PLAN-ID>")
    ap.add_argument("--plan", required=True, dest="plan_id")
    ap.add_argument("--item", required=True, dest="item_id")
    ap.add_argument("--command", required=True, choices=COMMANDS)
    ap.add_argument("--result", required=True, choices=RESULT_VALUES)
    ap.add_argument("--actor", default=None, help="`<model>/<effort>` or `owner`")
    ap.add_argument(
        "--route-evidence", default=None,
        help="alternative --actor: path to JSON `task.route_evidence.capture_actual()` "
            "(P2.4/P2.6) — actor is output canonical `<model>/<effort>`-spelling form "
            "(`findings/02` — 34 observed spellings), and not assembled by hand in place")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--friction", default="", help="separated by commas, from a closed list")
    ap.add_argument("--cost-usd", type=float, default=None)
    ap.add_argument("--num-turns", type=int, default=None)
    ap.add_argument("--duration-ms", type=float, default=None)
    ap.add_argument("--note", default=None)
    ap.add_argument(
        "--trace-ref", default=None,
        help="optional: trace_id Unified Agent Trace (P3.1) — additive, has no effect "
            "REQUIRED_FIELDS; omitted by default")
    ap.add_argument("--fingerprint", default=None,
                    help="SHA-256 material scope/SHA/risk or terminal evidence")
    ap.add_argument("--decision-json", default=None,
                    help="compact D12 decision evidence like JSON object")
    ap.add_argument("--batch-receipt-json", default=None,
                    help="optional digest-bound batch receipt as JSON object")
    ap.add_argument("--repair-decision-json", default=None,
                    help="closed repair-decision/v1 JSON object for a forward repair event")
    ap.add_argument("--repair-action", default=None,
                    choices=("repair-in-current-attempt", "gather-evidence", "block-candidate", "design-required"),
                    help="action returned by task.plan_repair.evaluate()")
    ep = sub.add_parser(
        "exception", help="add owner-gated exception for historical schema-invalid lines")
    ep.add_argument("--plan-dir", required=True, help="plan directory plans/<PLAN-ID>")
    ep.add_argument("--plan", required=True, dest="plan_id")
    ep.add_argument("--target-line", required=True, type=int)
    ep.add_argument("--invalid-fields", required=True,
                    help="separated by commas; v1 only allows friction")
    ep.add_argument("--owner-decision", required=True, help="existing owner-approved D#")
    ep.add_argument("--actor", required=True, help="`<model>/<effort>` or `owner`")
    ep.add_argument("--reason", required=True, help="why exception is safe and necessary")
    return p


def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    if args.cmd == "exception":
        journal_path = Path(args.plan_dir) / FILENAME
        try:
            lines = journal_path.read_text(encoding="utf-8").splitlines()
            raw_line = lines[args.target_line - 1]
        except (OSError, UnicodeDecodeError, IndexError) as exc:
            print(f"ERROR: target journal line is not readable: {exc}", file=sys.stderr)
            return 1
        exception = new_exception(
            plan_id=args.plan_id,
            target_line=args.target_line,
            target_sha256=line_sha256(raw_line),
            invalid_fields=_parse_friction(args.invalid_fields),
            owner_decision=args.owner_decision,
            actor=args.actor,
            reason=args.reason,
        )
        try:
            path = append_exception(args.plan_dir, exception)
        except JournalValidationError as exc:
            print(f"ERROR: schema exception failed validation: {exc}", file=sys.stderr)
            return 1
        print(f"journal: exception append → {path}")
        return 0

    if args.cmd != "append":  # pragma: no cover - argparse is already gating choices
        return 1
    if (args.actor is None) == (args.route_evidence is None):
        print("ERROR: exactly one of --actor / --route-evidence required", file=sys.stderr)
        return 1
    actor = args.actor
    if args.route_evidence is not None:
        # Lazy import (task_contract.evaluate_finding pattern): journal.py's own
        # schema/writer stay importable without task.route_evidence on the path.
        from task.route_evidence import RouteEvidenceError, canonical_actor
        try:
            evidence = json.loads(Path(args.route_evidence).read_text(encoding="utf-8"))
            # D72/F8: canonical_actor now reads the concrete `model` evidence field
            # never `model_class` — a historical evidence blob predating
            # this item simply lacks "model" and renders `unknown/<effort>`.
            actor = canonical_actor(evidence.get("model"), evidence.get("effort"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError,
               RouteEvidenceError) as exc:
            print(f"ERROR: --route-evidence is not readable: {exc}", file=sys.stderr)
            return 1
    decision = None
    if args.decision_json is not None:
        try:
            decision = json.loads(args.decision_json)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --decision-json is invalid: {exc}", file=sys.stderr)
            return 1
    batch_receipt = None
    if args.batch_receipt_json is not None:
        try:
            batch_receipt = json.loads(args.batch_receipt_json)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --batch-receipt-json is invalid: {exc}", file=sys.stderr)
            return 1
    repair_decision = None
    if args.repair_decision_json is not None:
        try:
            repair_decision = json.loads(args.repair_decision_json)
            from task import plan_repair
            outcome = plan_repair.evaluate(repair_decision, plan_dir=args.plan_dir)
            if args.repair_action != outcome["action"]:
                raise ValueError("--repair-action must match reducer result")
            repair_digest = outcome["repair_digest"]
        except (json.JSONDecodeError, ImportError, ValueError) as exc:
            print(f"ERROR: --repair-decision-json is invalid: {exc}", file=sys.stderr)
            return 1
    elif args.repair_action is not None:
        print("ERROR: --repair-action requires --repair-decision-json", file=sys.stderr)
        return 1
    entry = new_entry(
        plan_id=args.plan_id, item_id=args.item_id, command=args.command,
        actor=actor, result=args.result, session_id=args.session_id,
        run_id=args.run_id, attempt=args.attempt,
        friction=_parse_friction(args.friction), cost_usd=args.cost_usd,
        num_turns=args.num_turns, duration_ms=args.duration_ms, note=args.note,
        trace_ref=args.trace_ref, fingerprint=args.fingerprint, decision=decision,
        batch_receipt=batch_receipt,
    )
    if repair_decision is not None:
        entry.update({"repair_decision": repair_decision, "repair_digest": repair_digest,
                      "repair_action": args.repair_action})
    try:
        path, line_number, appended = append_idempotent_terminal(args.plan_dir, entry)
    except JournalValidationError as e:
        print(f"ERROR: log entry failed validation: {e}", file=sys.stderr)
        return 1
    if appended:
        print(f"journal: append → {path}")
    else:
        print(f"journal: existing → {path}:{line_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
