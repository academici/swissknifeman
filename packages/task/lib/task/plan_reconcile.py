"""Idempotent post-terminal reconciliation over existing plan state owners."""
from __future__ import annotations

import fcntl
from pathlib import Path

from task import (plan_bundle, plan_decisions, plan_delivery, plan_completion,
                  plan_item_state, plan_recovery, plan_status, task_contract, command_render, plan_continuity)


class ReconciliationError(ValueError):
    """A reconciliation stage could not converge and remains resumable."""

    def __init__(self, stage: str, cause: Exception):
        self.stage = stage
        self.code = "PLAN_RECONCILIATION_INCOMPLETE"
        super().__init__(f"{self.code}: {stage}: {cause}")


def write_handoff(root: Path, item_id: str, next_exact: str) -> None:
    """One deterministic same-session recommendation; no successor execution."""
    carrier = command_render.parse_next_carrier(next_exact)
    model, effort, batch = "implementation", "low", "n/a"
    if carrier.kind == "manual":
        model, effort = carrier.arguments[0].split("/", 1)
    elif carrier.command_id == "task:plan-design":
        model, effort = "frontier", "high"
    elif carrier.command_id == "task:plan-audit":
        model, effort = "frontier", "xhigh"
    elif carrier.command_id == "task:plan-run":
        routing = task_contract.compile_batch_routing(root)
        target = carrier.arguments[1]
        group = next((value for value in routing["batches"].values() if target in value["items"]), None)
        if group:
            model, effort, batch = group["route"]["model_class"], group["route"]["effort"], group["batch_id"]
    context = "terminal" if carrier.kind == "terminal" else "waiting-owner" if carrier.kind == "waiting" else "continue-root"
    continuity = ""
    if carrier.kind == "waiting":
        import json
        decision = plan_continuity.ContinuityDecision("waiting-owner", "owner-wait",
            ("checkpoint:" + item_id, "condition:" + next_exact), False)
        plan_continuity.validate_decision(decision)
        continuity = "```session-continuity-decision/v1\n" + json.dumps(decision.as_dict()) + "\n```\n\n"
    command = ("$ " + carrier.command_id + " " + " ".join(carrier.arguments)) if carrier.command_id else "—"
    text = (f"# HANDOFF — Task — after {item_id}\n\n**Next:** {next_exact}\n\n"
            f"| Parameter | Meaning |\n|:--|:--|\n| Batch | {batch} |\n| Model | {model} |\n| Thinking | {effort} |\n"
            f"| Context | {context} |\n| Command | {command} |\n\n"
            + continuity +
            f"**Done:** {item_id}: terminal evidence persisted.\n"
            "**Remaining:** actual successor above; no execution authority is added.\n"
            "**Sources of truth:** `plan.md`, phase/item contracts, `journal.jsonl`, item states and acceptance evidence.\n"
            "**Open risks:** retained in item states, decisions and acceptance.\n")
    path = root / "handoff.md"
    if not path.exists() or path.read_text() != text:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text)
        temporary.replace(path)


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
        try:
            # Item-state freshness is scoped to this item's journal rows. A new
            # terminal event cannot stale projections of previously closed items.
            plan_item_state.build_states(
                root, item_id=item_id, materialize_successor=False)
            plan_decisions.build_views(root)
            plan_status.build_status(root)
        except Exception as exc:
            raise ReconciliationError("owner-views", exc) from exc
        try:
            successor = plan_recovery.materialize_next_ready(root, item_id)
        except Exception as exc:
            raise ReconciliationError("next-frontier", exc) from exc
        try:
            plan_item_state.build_states(root, item_id=item_id, check=True)
            plan_decisions.build_views(root, check=True)
            plan_status.build_status(root, check=True)
            if successor is not None:
                plan_bundle.build(root, successor.stem, check=True)
        except Exception as exc:
            raise ReconciliationError("freshness", exc) from exc
        try:
            if terminal["result"] == "closed-green":
                plan_delivery._require_completed_phase_before_item_handoff(root, item_id)
            next_exact = plan_completion.successor(root)
            write_handoff(root, item_id, next_exact)
            receipt = plan_delivery.build_terminal_receipt(root, item_id)
            plan_delivery.write_receipt(root / ".plan-cache" / f"{item_id}-terminal-delivery-receipt.json", receipt)
        except Exception as exc:
            raise ReconciliationError("delivery", exc) from exc
        return {
            "schema_version": "plan-terminal-reconciliation/v1",
            "plan_id": root.name,
            "item_id": item_id,
            "terminal": terminal,
            "reconciled_items": [item_id],
            "next_bundle": (successor.relative_to(root).as_posix()
                            if successor is not None else None),
            "receipt": receipt,
        }
