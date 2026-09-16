"""Idempotent post-terminal reconciliation over existing plan state owners."""
from __future__ import annotations

import fcntl
import json
import re
from pathlib import Path

from task import (journal, plan_bundle, plan_decisions, plan_delivery,
                  plan_item_state, plan_recovery, plan_status)


class ReconciliationError(ValueError):
    """A reconciliation stage could not converge and remains resumable."""

    def __init__(self, stage: str, cause: Exception):
        self.stage = stage
        self.code = "PLAN_RECONCILIATION_INCOMPLETE"
        super().__init__(f"{self.code}: {stage}: {cause}")


def _terminal_items(plan_dir: Path) -> tuple[str, ...]:
    latest = {}
    try:
        rows = (plan_dir / journal.FILENAME).read_text(encoding="utf-8").splitlines()
        for raw in rows:
            if not raw.strip():
                continue
            event = json.loads(raw)
            item_id = event.get("item_id")
            if isinstance(item_id, str) and re.fullmatch(r"P\d+\.\d+", item_id):
                latest.setdefault(item_id, []).append(event)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise ReconciliationError("journal", exc) from exc
    return tuple(sorted(
        (item for item, history in latest.items()
         if (position := plan_item_state.latest_execution_event(history)) is not None
         and position.get("result") in journal.TERMINAL_CLOSE_RESULTS),
        key=lambda item: tuple(int(part) for part in item[1:].split(".")),
    ))


def reconcile_terminal(plan_dir, item_id: str) -> dict:
    """Resume-safe journal → views → frontier bundle → receipt convergence.

    The durable terminal journal remains authoritative.  Each projection owner is
    invoked in dependency order and checked again before delivery.  No future item
    beyond the single newly ready frontier is materialized.
    """
    root = Path(plan_dir)
    lock_path = root / ".plan-cache" / "terminal-reconciliation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            terminal = plan_delivery._terminal_journal(root, item_id)
        except Exception as exc:
            raise ReconciliationError("terminal-journal", exc) from exc
        terminal_items = _terminal_items(root)
        try:
            for subject in terminal_items:
                plan_item_state.build_states(
                    root, item_id=subject, materialize_successor=False)
            plan_decisions.build_views(root)
            plan_status.build_status(root)
        except Exception as exc:
            raise ReconciliationError("owner-views", exc) from exc
        try:
            successor = plan_recovery.materialize_next_ready(root, item_id)
        except Exception as exc:
            raise ReconciliationError("next-frontier", exc) from exc
        try:
            for subject in terminal_items:
                plan_item_state.build_states(root, item_id=subject, check=True)
            plan_decisions.build_views(root, check=True)
            plan_status.build_status(root, check=True)
            if successor is not None:
                plan_bundle.build(root, successor.stem, check=True)
        except Exception as exc:
            raise ReconciliationError("freshness", exc) from exc
        try:
            receipt = plan_delivery.build_terminal_receipt(root, item_id)
        except Exception as exc:
            raise ReconciliationError("delivery", exc) from exc
        return {
            "schema_version": "plan-terminal-reconciliation/v1",
            "plan_id": root.name,
            "item_id": item_id,
            "terminal": terminal,
            "reconciled_items": list(terminal_items),
            "next_bundle": (successor.relative_to(root).as_posix()
                            if successor is not None else None),
            "receipt": receipt,
        }
