"""Identifiers, status enums and ordering for v3 plan documents (stdlib only).

The ID patterns here are the same literals as ``schemas/plan/v1/*.schema.json``; a test keeps them in sync.
Match them with ``fullmatch`` — ``$`` alone would also accept a trailing newline.
"""
from __future__ import annotations

from enum import Enum
import re
from typing import Iterable, NamedTuple

# Same Plan ID literal as plan_numbering._DIR_ID, plus the historical codename-only form.
PLAN_ID = re.compile(r"^(\d{4}\.\d{2}\.\d{2}-№[1-9][0-9]*-[A-Z][A-Z0-9-]*|[A-Z][A-Z0-9-]+)$", re.ASCII)
SHORT_ID = re.compile(r"^PLAN[1-9][0-9]*$", re.ASCII)
PHASE_ID = re.compile(r"^P[0-9]+$", re.ASCII)
ITEM_ID = re.compile(r"^P[0-9]+\.[0-9]+$", re.ASCII)
DECISION_ID = re.compile(r"^D[0-9]+$", re.ASCII)
REF = re.compile(r"^((?:[a-z0-9-]+:)?PLAN[0-9]+\.)?(P[0-9]+(\.[0-9]+)?|D[0-9]+)$", re.ASCII)
_REF_PARTS = re.compile(r"^(?:(?:(?P<repo>[a-z0-9-]+):)?(?P<plan>PLAN[0-9]+)\.)?(?P<target>[A-Z]+[0-9]+(?:\.[0-9]+)?)$",
                        re.ASCII)
_SORTABLE = re.compile(r"^(?P<prefix>[A-Z]+)(?P<nums>[0-9]+(?:\.[0-9]+)*)$", re.ASCII)

CLASS_ORDER = ("economy", "implementation", "frontier")
EFFORT_ORDER = ("low", "medium", "high", "xhigh")


class ItemStatus(str, Enum):
    """Item statuses; members compare equal to their JSON string values."""

    todo = "todo"
    in_progress = "in_progress"
    done = "done"
    done_with_deviations = "done_with_deviations"
    blocked = "blocked"
    skipped = "skipped"


# Terminal items are finished by the lifecycle; only SATISFYING ones unblock a dependent item.
TERMINAL = frozenset({ItemStatus.done, ItemStatus.done_with_deviations, ItemStatus.blocked, ItemStatus.skipped})
SATISFYING = frozenset({ItemStatus.done, ItemStatus.done_with_deviations, ItemStatus.skipped})

STATUS_LABEL = {
    ItemStatus.todo: "⬜ Not started",
    ItemStatus.in_progress: "🟡 In progress",
    ItemStatus.done: "🟢 Done",
    ItemStatus.done_with_deviations: "🟠 Done with deviations",
    ItemStatus.blocked: "🔴 Blocked",
    ItemStatus.skipped: "⛔ Skipped by decision",
}

# Worst-of order for phase closure: later entries win.
_PHASE_RESULT_ORDER = (ItemStatus.skipped, ItemStatus.done, ItemStatus.done_with_deviations, ItemStatus.blocked)


class Ref(NamedTuple):
    repo: str | None
    plan: str | None
    target: str
    kind: str  # "phase" | "item" | "decision"


def parse_ref(ref: str) -> Ref:
    """Split a local or qualified reference; raise ValueError when it is malformed."""
    if not isinstance(ref, str) or not REF.fullmatch(ref):
        raise ValueError(f"invalid ref: {ref!r}")
    parts = _REF_PARTS.fullmatch(ref)
    assert parts is not None  # REF guarantees the shape
    target = parts["target"]
    kind = "decision" if target.startswith("D") else ("item" if "." in target else "phase")
    return Ref(parts["repo"], parts["plan"], target, kind)


def item_phase(item_id: str) -> str:
    """Phase id of an item id: ``P1.2`` -> ``P1``."""
    if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id):
        raise ValueError(f"invalid item id: {item_id!r}")
    return item_id.split(".", 1)[0]


def id_sort_key(identifier: str) -> tuple:
    """Numeric sort key so that ``P1.10`` follows ``P1.9`` and a phase precedes its items."""
    match = _SORTABLE.fullmatch(identifier) if isinstance(identifier, str) else None
    if match is None:
        raise ValueError(f"invalid id: {identifier!r}")
    return (match["prefix"], *(int(n) for n in match["nums"].split(".")))


def phase_status(statuses: Iterable[str]) -> str | None:
    """Closure result of a phase from its item statuses, or None while it is still open.

    Worst-of: blocked > done_with_deviations > done; all skipped -> skipped.
    """
    members = [ItemStatus(s) for s in statuses]
    if not members or any(s not in TERMINAL for s in members):
        return None
    return max(members, key=_PHASE_RESULT_ORDER.index).value
