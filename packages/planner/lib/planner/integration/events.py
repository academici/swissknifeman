"""Journal the ``planner.*`` events of a command after the plan lock is released.

The plan engine collects ``(type, data)`` pairs while it mutates a plan and hands them to :func:`emit_all` after it
left the lock, so a subscriber that runs synchronously and calls ``plan.py`` on the same plan cannot block.
Emission is best-effort: with ``events.enabled`` false or without aicore nothing happens, and a failure of the journal never
changes the result of the command; it is reported once per process on stderr.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from . import available

SOURCE = "planner"
DATA_SCHEMA = "urn:swissknifeman:planner:event-data:{name}:v1"

_WARNED: set = set()


def data_schema(event_type: str) -> str:
    """The ``$id`` of the data schema of an event type (the dots of the type become hyphens)."""
    return DATA_SCHEMA.format(name=event_type.replace(".", "-"))


def enabled(project_root: str | Path | None) -> bool:
    """``events.enabled`` of the configuration of the project (the machine configuration without one)."""
    from planner.plan import settings
    from . import config
    return bool(config.resolve(project_root=project_root, config_file=settings.invocation_file()).get("events.enabled"))


def _warn(reason: str) -> None:
    if "emit" in _WARNED:
        return
    _WARNED.add("emit")
    print(f"PLANNER_EVENT_NOT_EMITTED: {reason}", file=sys.stderr)


def emit_all(events: Iterable[tuple[str, dict]], *, project_root: str | Path | None, plan_id: str) -> None:
    """Journal ``events`` in order as events of module ``planner`` about ``plan_id``.

    Each event names the previous one of the batch as its cause. ``project_root`` selects the journal of a
    project; ``None`` the machine journal. Never raises.
    """
    batch = list(events)
    if not batch or not available():
        return
    try:
        if not enabled(project_root):
            return
        from aicore.ext import events as journal
        from planner.plan import settings
        config_file = settings.invocation_file()
        cause = None
        for event_type, data in batch:
            stored = journal.emit(event_type, data, source=SOURCE, subject=plan_id, project=project_root,
                                  dataschema=data_schema(event_type), causationid=cause, config_file=config_file)
            if stored is not None:  # a journal that failed was already reported by aicore
                cause = stored.id
    except Exception as exc:  # noqa: BLE001 — the command that produced the events must not fail
        _warn(f"{getattr(exc, 'code', None) or type(exc).__name__}: {getattr(exc, 'message', None) or exc}")
