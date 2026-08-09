"""Forward-only activation of hard layout-v2 checks.

The registry is the sole activation carrier.  Journal timestamps are projected per
item, so enabling a check cannot retroactively gate historic producers.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from task import plan_status


class ActivationError(ValueError):
    pass


_REGISTRY = Path(__file__).resolve().parents[2] / "configs" / "lint-check-dispositions.json"


def activated_from(check: str) -> date | None:
    try:
        record = json.loads(_REGISTRY.read_text(encoding="utf-8"))["checks"][check]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise ActivationError(f"activation registry unreadable for {check}") from exc
    raw = record.get("activated_from")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ActivationError(f"activated_from for {check} must be ISO date")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ActivationError(f"activated_from for {check} must be ISO date") from exc


def _activation_line(check: str) -> int:
    try:
        record = json.loads(_REGISTRY.read_text(encoding="utf-8"))["checks"][check]
        line = record["activated_after_journal_line"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise ActivationError(f"activation journal boundary missing for {check}") from exc
    if isinstance(line, bool) or not isinstance(line, int) or line < 0:
        raise ActivationError(f"activation journal boundary invalid for {check}")
    return line


def active_items(plan_dir, check: str) -> set[str]:
    cutoff = activated_from(check)
    if cutoff is None:
        return set()
    boundary = _activation_line(check)
    journal = Path(plan_dir) / "journal.jsonl"
    try:
        rows = journal.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ActivationError("activation journal unreadable") from exc
    result = set()
    for number, raw in enumerate(rows, start=1):
        if number <= boundary or not raw.strip():
            continue
        try:
            event = json.loads(raw)
            item = event["item_id"]
            event_day = date.fromisoformat(str(event["ts"])[:10])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ActivationError("activation journal entry invalid") from exc
        if event_day >= cutoff and isinstance(item, str):
            result.add(item)
    return result


def active_phases(plan_dir, check: str) -> set[str]:
    active = active_items(plan_dir, check)
    if not active:
        return set()
    model = plan_status.status_model(plan_dir)
    return {phase["id"] for phase in model["phases"] if any(item["id"] in active for item in phase["items"])}
