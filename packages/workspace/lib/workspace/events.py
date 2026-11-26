"""Journal the ``workspace.*`` events of a command. Emission is best-effort and happens after every lock is released:
a failure of the event journal never changes the result of the command and is reported on stderr. Data that breaks the
schema of its type is not journaled (``EVENT_DATA_INVALID``); under ``SKM_CONTRACTS_STRICT=1`` it raises instead."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Union

SOURCE = "workspace"
DATA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "event-data" / "v1"
DATA_SCHEMA = "urn:swissknifeman:workspace:event-data:{name}:v1"
EVENT_TYPES = ("workspace.root.initialized", "workspace.project.attached", "workspace.migration.applied",
               "workspace.migration.rolled-back", "workspace.sync.committed", "workspace.sync.pulled",
               "workspace.sync.conflict", "workspace.sync.pushed")


def data_schema(event_type: str) -> str:
    """The ``$id`` of the data schema of an event type (the dots of the type become hyphens)."""
    return DATA_SCHEMA.format(name=event_type.replace(".", "-"))


def emit(event_type: str, data: Mapping[str, Any], *, subject: str, env: Optional[Mapping[str, str]] = None,
         home: Optional[Union[str, "os.PathLike[str]"]] = None) -> Optional[str]:
    """Journal one event of module ``workspace`` in the machine journal; returns its id or ``None``. Never raises."""
    try:
        from aicore.ext import events as journal
        from aicore.ext.errors import ExtError
        problem = journal.check_data(dict(data), data_schema(event_type), DATA_DIR, env=env)
        if problem is not None:
            raise ExtError("EVENT_DATA_INVALID", problem)
        stored = journal.emit(event_type, dict(data), source=SOURCE, subject=subject, project=None,
                              dataschema=data_schema(event_type), env=env, home=home, strict=True)
        return stored.id if stored is not None else None
    except Exception as exc:  # noqa: BLE001 — the command that produced the event must not fail
        if getattr(exc, "code", None) == "EVENT_DATA_INVALID" and _strict(env):
            raise
        reason = getattr(exc, "message", None) or exc
        try:
            print(f"WORKSPACE_EVENT_NOT_EMITTED: {event_type}: {getattr(exc, 'code', None) or type(exc).__name__}: "
                  f"{reason}", file=sys.stderr)
        except (OSError, ValueError):
            pass
    return None


def _strict(env: Optional[Mapping[str, str]]) -> bool:
    from aicore.ext import events as journal
    return journal.contracts_strict(env)
