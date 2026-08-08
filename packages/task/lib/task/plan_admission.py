"""Stage-aware admission for layout-v2 plan read budgets.

The module decides *when* the frozen D2(a)/D2(b) predicates apply.  It does not
measure files: ``task.plan_weight`` remains the single owner of weights and
single-read results.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


STATE_HISTORICAL = "historical-pre-v2"
STATE_PENDING = "pending-producer"
STATE_READY = "ready"
STATES = (STATE_HISTORICAL, STATE_PENDING, STATE_READY)

CODE_MISSING_PRODUCER = "missing_without_producer"
CODE_PRODUCER_UNKNOWN = "producer_not_found"
CODE_PRODUCER_ORDER = "producer_not_predecessor"
CODE_PRODUCER_DELIVERABLE = "producer_deliverable_mismatch"
CODE_PRODUCER_PENDING = "producer_pending"
CODE_PRODUCER_TERMINAL_MISSING = "producer_terminal_missing"
CODE_UNRESOLVED = "unresolved_entry"
CODE_CONTRACT = "read_budget_contract_invalid"

TERMINAL_STATUSES = frozenset(
    ("🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision")
)
_PRODUCER_RE = re.compile(r"(?:^|[\s(;,])producer\s*[:=]\s*(P\d+\.\d+)\b", re.IGNORECASE)
_MIGRATION_RE = re.compile(r"(?:layout[\s-]*v2|v1\s*(?:→|->|to)\s*v2)", re.IGNORECASE)
_VERSION_RE = re.compile(
    r"^\*\*Version:\*\*\s*`?([0-9]+\.[0-9]+\.[0-9]+)`?\s*$", re.MULTILINE)
_THRESHOLD_RE = re.compile(r"estimated_required_read_tokens\(i\)\s*<=\s*(\d+)")


class AdmissionError(ValueError):
    """The public admission contract cannot be applied deterministically."""


def producer_annotation(entry: str) -> str | None:
    match = _PRODUCER_RE.search(entry or "")
    return match.group(1) if match else None


def load_contract(plan_dir) -> dict:
    """Load the threshold and version from the plan-owned frozen contract.

    No numeric fallback is legal: an absent or ambiguous contract is itself a
    fail-closed admission result.
    """
    path = Path(plan_dir) / "root" / "contracts" / "read-budget-v1.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AdmissionError(f"контракт read-budget не читается: {path}: {exc}") from exc
    version = _VERSION_RE.search(text)
    thresholds = {int(value) for value in _THRESHOLD_RE.findall(text)}
    if version is None or len(thresholds) != 1:
        raise AdmissionError(
            f"контракт read-budget не несёт однозначные Version/порог D2(a): {path}")
    version_value = version.group(1)
    if tuple(int(part) for part in version_value.split(".")) < (1, 1, 0):
        raise AdmissionError(
            f"контракт read-budget не несёт stage-aware admission >= 1.1.0: {path}")
    return {"path": str(path), "version": version_value,
            "item_tokens": thresholds.pop()}


def _journal_facts(plan_dir: Path) -> tuple[int | None, dict[str, int]]:
    """Return the layout-v2 activation line and terminal line per item."""
    path = plan_dir / "journal.jsonl"
    activation = None
    terminal = {}
    if not path.is_file():
        return activation, terminal
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdmissionError(f"журнал невалиден: {path}:{lineno}") from exc
        note = str(event.get("note") or "")
        if activation is None and _MIGRATION_RE.search(note):
            activation = lineno
        if str(event.get("result") or "").startswith("closed-"):
            item_id = str(event.get("item_id") or "")
            if item_id:
                terminal[item_id] = lineno
    return activation, terminal


def _entry_for_path(entries: list[str], path: str) -> str:
    matches = [entry for entry in entries if path in entry]
    return matches[0] if len(matches) == 1 else ""


def classify(plan_dir, items: list[dict], specs: dict[str, dict], *, contract=None) -> dict:
    """Attach admission facts to measured layout-v2 item records.

    ``items`` are records from ``plan_weight``. ``specs`` maps item id to the
    parsed ``Required Reads`` entries and ``Deliverables`` text.  The caller
    supplies already measured D2 facts; this function never reads a measured
    carrier itself.
    """
    plan_dir = Path(plan_dir)
    contract_error = None
    if contract is None:
        try:
            contract = load_contract(plan_dir)
        except AdmissionError as exc:
            contract = None
            contract_error = str(exc)
    activation, terminal_lines = _journal_facts(plan_dir)
    order = {record["item_id"]: index for index, record in enumerate(items)}
    by_id = {record["item_id"]: record for record in items}
    admission_counts = {state: 0 for state in STATES}
    code_counts = {}

    for record in items:
        item_id = record["item_id"]
        spec = specs.get(item_id, {})
        codes = []
        edges = []
        terminal_line = terminal_lines.get(item_id)
        historical = (activation is not None and terminal_line is not None
                      and terminal_line <= activation)

        for gap in record.get("gaps", []):
            kind = gap.get("kind")
            if kind == "unresolved_entry":
                codes.append({"code": CODE_UNRESOLVED, "item_id": item_id,
                              "entry": gap.get("entry")})
                continue
            if kind != "missing_file" or gap.get("role") != "required_read":
                continue
            missing_path = str(gap.get("path") or "")
            entry = _entry_for_path(spec.get("required_read_entries", []), missing_path)
            producer = producer_annotation(entry)
            if producer is None:
                codes.append({"code": CODE_MISSING_PRODUCER, "item_id": item_id,
                              "path": missing_path})
                continue
            producer_record = by_id.get(producer)
            if producer_record is None:
                codes.append({"code": CODE_PRODUCER_UNKNOWN, "item_id": item_id,
                              "path": missing_path, "producer_item": producer})
                continue
            if order[producer] >= order[item_id]:
                codes.append({"code": CODE_PRODUCER_ORDER, "item_id": item_id,
                              "path": missing_path, "producer_item": producer})
                continue
            producer_spec = specs.get(producer, {})
            if missing_path not in str(producer_spec.get("deliverables") or ""):
                codes.append({"code": CODE_PRODUCER_DELIVERABLE, "item_id": item_id,
                              "path": missing_path, "producer_item": producer})
                continue
            edge = {"path": missing_path, "producer_item": producer}
            edges.append(edge)
            if producer_record.get("status") in TERMINAL_STATUSES:
                codes.append({"code": CODE_PRODUCER_TERMINAL_MISSING, "item_id": item_id,
                              **edge})
            else:
                codes.append({"code": CODE_PRODUCER_PENDING, "item_id": item_id, **edge})

        if historical:
            state = STATE_HISTORICAL
            admission_pass = None
        elif edges and codes and all(row["code"] == CODE_PRODUCER_PENDING for row in codes):
            state = STATE_PENDING
            admission_pass = None
        else:
            state = STATE_READY
            d2a = bool(contract) and record["weight_tokens"] <= contract["item_tokens"]
            d2b = not any(gap.get("kind") in
                          ("unreadable_root", "unresolved_entry", "missing_file", "oversized_file")
                          for gap in record.get("gaps", []))
            admission_pass = bool(d2a and d2b and not codes and contract_error is None)

        if contract_error:
            codes.append({"code": CODE_CONTRACT, "item_id": item_id,
                          "detail": contract_error})
            if state == STATE_READY:
                admission_pass = False
        record.update({
            "admission_state": state,
            "producer_item": edges[0]["producer_item"] if len(edges) == 1 else None,
            "producer_edges": edges,
            "admission_gaps": codes,
            "admission_pass": admission_pass,
            "d2a_pass": (None if state != STATE_READY or contract is None else
                         record["weight_tokens"] <= contract["item_tokens"]),
            "d2b_pass": (None if state != STATE_READY else not any(
                gap.get("kind") in
                ("unreadable_root", "unresolved_entry", "missing_file", "oversized_file")
                for gap in record.get("gaps", []))),
        })
        admission_counts[state] += 1
        for row in codes:
            code_counts[row["code"]] = code_counts.get(row["code"], 0) + 1

    return {"contract": contract, "counts": admission_counts,
            "gap_counts": code_counts,
            "ready_failed": sum(record.get("admission_state") == STATE_READY
                                and record.get("admission_pass") is False for record in items)}
