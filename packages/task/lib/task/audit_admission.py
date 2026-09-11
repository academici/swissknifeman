"""Owner-consented, single-use admission for an optional phase audit.

The owner-message carrier records provenance; it is not cryptographic authentication.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = "audit-admission/v2"
BRANCH = "phase-audit"

_PHASE_RE = re.compile(r"^P\d+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BLOCK_RE = re.compile(
    r"^```audit-admission/v2[ \t]*\n(?P<payload>.*?)\n```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_TERMINAL_RESULTS = frozenset(("audit-green", "audit-attention", "audit-red"))
_RECORD_KEYS = frozenset((
    "schema_version", "target", "run_id", "residual_risks", "owner_message",
    "scope_sha256",
))
_TARGET_KEYS = frozenset(("phase_id", "candidate_fingerprint"))
_RISK_KEYS = frozenset(("id", "impact", "evidence_gap", "bounded_question"))


def _result(allowed: bool, code: str, record=None) -> dict:
    return {"allowed": allowed, "code": code, "record": record}


def _nonempty(value) -> bool:
    return isinstance(value, str) and value == value.strip() and bool(value)


def _scope_sha256(record: dict) -> str:
    bound = {
        "target": record["target"],
        "run_id": record["run_id"],
        "residual_risks": record["residual_risks"],
    }
    encoded = json.dumps(bound, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_record(value) -> dict:
    if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
        raise ValueError("audit admission: недопустимый набор полей")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("audit admission: неверный schema_version")
    target = value["target"]
    if (not isinstance(target, dict) or set(target) != _TARGET_KEYS
            or not _PHASE_RE.fullmatch(target.get("phase_id", ""))
            or not _SHA256_RE.fullmatch(target.get("candidate_fingerprint", ""))):
        raise ValueError("audit admission: неверный target")
    if not _nonempty(value["run_id"]):
        raise ValueError("audit admission: неверный run_id")
    risks = value["residual_risks"]
    if not isinstance(risks, list) or not risks:
        raise ValueError("audit admission: нужны остаточные риски")
    risk_ids = []
    for risk in risks:
        if (not isinstance(risk, dict) or set(risk) != _RISK_KEYS
                or any(not _nonempty(risk.get(field)) for field in _RISK_KEYS)):
            raise ValueError("audit admission: неверная строка остаточного риска")
        risk_ids.append(risk["id"])
    if len(risk_ids) != len(set(risk_ids)):
        raise ValueError("audit admission: идентификаторы рисков повторяются")
    if (not _SHA256_RE.fullmatch(value.get("scope_sha256", ""))
            or value["scope_sha256"] != _scope_sha256(value)):
        raise ValueError("audit admission: scope не совпадает со связанными входами")
    if not _nonempty(value["owner_message"]):
        raise ValueError("audit admission: неверный owner_message")
    return value


def consent_request(record: dict) -> dict:
    """Return the exact request restated by the repository-owner message."""
    record = _validate_record(record)
    phase_id = record["target"]["phase_id"]
    return {
        "gate_id": f"AUDIT-{phase_id}",
        "branch": BRANCH,
        "scope": f"{SCHEMA_VERSION}:{record['scope_sha256']}",
    }


def _decision_records(plan_dir: Path):
    from task import plan_decisions, plan_layout

    pattern = plan_layout.carrier_glob(plan_dir, "decision-record")
    directory = pattern.parent
    if directory.is_symlink():
        raise ValueError("audit admission: каталог решений не может быть символьной ссылкой")
    if not directory.exists():
        return (), "AUDIT_CONSENT_MISSING"
    if not directory.is_dir():
        raise ValueError("audit admission: каталог решений не является обычным каталогом")
    decisions = plan_decisions.load_decisions(plan_dir)
    if any(decision.path.is_symlink() for decision in decisions):
        raise ValueError("audit admission: решение не может быть символьной ссылкой")

    records = []
    for decision in decisions:
        if decision.status != "accepted" or decision.superseded_by is not None:
            continue
        blocks = list(_BLOCK_RE.finditer(decision.body))
        if decision.body.count("```audit-admission/v2") != len(blocks):
            raise ValueError("audit admission: повреждён fenced-блок")
        for block in blocks:
            try:
                value = json.loads(block.group("payload"))
            except json.JSONDecodeError as exc:
                raise ValueError("audit admission: повреждён JSON") from exc
            records.append((decision, _validate_record(value)))
    return tuple(records), None


def _journal_state(plan_dir: Path, record: dict) -> str:
    path = plan_dir / "journal.jsonl"
    if not path.exists():
        return "available"
    if not path.is_file() or path.is_symlink():
        return "invalid"
    try:
        rows = [json.loads(line) for line in path.read_text(
            encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "invalid"
    if any(not isinstance(row, dict) for row in rows):
        return "invalid"

    run_id = record["run_id"]
    phase_id = record["target"]["phase_id"]
    fingerprint = record["target"]["candidate_fingerprint"]
    matches = [row for row in rows if row.get("run_id") == run_id]
    if not matches:
        return "available"
    if any(row.get("command") != "plan-audit"
           or row.get("item_id") != phase_id
           or row.get("fingerprint") != fingerprint for row in matches):
        return "invalid"
    if any(row.get("result") in _TERMINAL_RESULTS for row in matches):
        return "consumed"
    starts = [row for row in matches if row.get("result") == "in-progress"]
    if len(starts) != 1:
        return "invalid"
    return "reserved"


def evaluate(plan_dir, phase_id, candidate, *, run_id=None) -> dict:
    """Evaluate one optional audit grant without affecting normal phase closure."""
    if (not isinstance(phase_id, str) or not _PHASE_RE.fullmatch(phase_id)
            or not isinstance(candidate, dict)
            or (run_id is not None and not _nonempty(run_id))):
        return _result(False, "AUDIT_CONSENT_INVALID")
    try:
        plan_dir = Path(plan_dir)
        from task.plan_gates import _candidate_snapshot_fingerprint

        if candidate.get("phase_id") != phase_id:
            raise ValueError("candidate указывает на другую фазу")
        fingerprint = _candidate_snapshot_fingerprint(candidate)
        records, missing_code = _decision_records(plan_dir)
    except (KeyError, TypeError, ValueError, OSError, UnicodeDecodeError):
        # Decision/layout parsers expose ValueError subclasses. Any carrier defect
        # refuses only this optional branch; callers remain free to close directly.
        return _result(False, "AUDIT_CONSENT_INVALID")
    if missing_code:
        return _result(False, missing_code)

    scoped = [(decision, record) for decision, record in records
              if phase_id in decision.items and record["target"]["phase_id"] == phase_id]
    matching = [(decision, record) for decision, record in scoped
                if record["target"]["candidate_fingerprint"] == fingerprint
                and (run_id is None or record["run_id"] == run_id)]
    if not matching:
        return _result(False, "AUDIT_CONSENT_MISSING")

    try:
        from task.task_contract import _owner_message_matches

        states = []
        for _decision, record in matching:
            if sum(other["run_id"] == record["run_id"] for _, other in records) != 1:
                return _result(False, "AUDIT_CONSENT_AMBIGUOUS")
            if not _owner_message_matches(plan_dir, record["owner_message"],
                                          consent_request(record)):
                return _result(False, "AUDIT_CONSENT_INVALID")
            state = _journal_state(plan_dir, record)
            if state == "invalid":
                return _result(False, "AUDIT_CONSENT_INVALID")
            states.append((record, state))
    except (OSError, UnicodeDecodeError, ValueError):
        return _result(False, "AUDIT_CONSENT_INVALID")

    active = [(record, state) for record, state in states if state != "consumed"]
    if len(active) > 1 or (run_id is not None and len(states) > 1):
        return _result(False, "AUDIT_CONSENT_AMBIGUOUS")
    if not active:
        record = states[0][0] if len(states) == 1 else None
        return _result(False, "AUDIT_CONSENT_CONSUMED", record)
    record, _state = active[0]
    return _result(True, "AUDIT_ADMITTED", record)
