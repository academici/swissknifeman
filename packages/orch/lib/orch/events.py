"""Journal the ``orch.run.*`` events of a command after the run journal is written and no lock is held.

Emission is best-effort: with ``events.enabled`` false nothing happens, and a failure of the event journal never changes
the exit code or the output of the command; it is reported on stderr as ``ORCH_EVENT_NOT_EMITTED``. Pure operations
(``prepare --dry-run``, ``policy test``) never emit. The data of every type is described by
``schemas/event-data/v1/<type>.schema.json``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Optional

SOURCE = "orch"
DATA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "event-data" / "v1"
DATA_SCHEMA = "urn:swissknifeman:orch:event-data:{name}:v1"
EVENT_TYPES = ("orch.run.started", "orch.run.stage.finished", "orch.run.finished", "orch.run.refused",
               "orch.agent.started", "orch.agent.finished", "orch.agent.failed", "orch.agent.questioned",
               "orch.run.warning", "orch.run.waiting", "orch.work.blocked", "orch.review.added",
               "orch.deviation.recorded", "orch.deviation.resolved", "orch.provider.rate-limited",
               "orch.provider.quota-exhausted", "orch.provider.fallback", "orch.input.rebuilt", "orch.conductor.health")


def data_schema(event_type: str) -> str:
    """The ``$id`` of the data schema of an event type (the dots of the type become hyphens)."""
    return DATA_SCHEMA.format(name=event_type.replace(".", "-"))


def emit(event_type: str, data: Mapping[str, Any], *, subject: str, causationid: Optional[str] = None,
         correlationid: Optional[str] = None, settings: Any = None, project: Any = None,
         config_file: Any = None) -> Optional[str]:
    """Journal one event of module ``orch`` about ``subject`` (a run id, a submission id of a refusal, or
    ``<run>/<item>/<agent run id>`` of an agent run).

    Returns the id of the journaled event, ``None`` when nothing was journaled; ``correlationid`` is the run id.

    ``settings`` is the effective ``orch.settings.Settings``; without it ``events.enabled`` is read from the
    configuration. Data that breaks the schema of the type is not journaled (``EVENT_DATA_INVALID`` on stderr). Never
    raises, except ``ExtError('EVENT_DATA_INVALID')`` under ``SKM_CONTRACTS_STRICT=1`` (the test runners).
    """
    try:
        if settings is None:
            from . import settings as settings_module
            settings = settings_module.load(project=project, config_file=config_file)
        if not settings.events_enabled:
            return None
        from aicore.ext import events as journal
        from aicore.ext.errors import ExtError
        from aicore.util.redact import env_secrets, redact_document
        data = redact_document(dict(data), secrets=env_secrets())
        problem = journal.check_data(data, data_schema(event_type), DATA_DIR)
        if problem is not None:
            raise ExtError("EVENT_DATA_INVALID", problem)
        stored = journal.emit(event_type, dict(data), source=SOURCE, subject=subject, project=project,
                              dataschema=data_schema(event_type), causationid=causationid,
                              correlationid=correlationid, config_file=config_file, strict=True)
        return stored.id if stored is not None else None
    except Exception as exc:  # noqa: BLE001 — the command that produced the event must not fail
        if getattr(exc, "code", None) == "EVENT_DATA_INVALID" and _strict():
            raise
        reason = getattr(exc, "message", None) or exc
        try:
            print(f"ORCH_EVENT_NOT_EMITTED: {event_type}: {getattr(exc, 'code', None) or type(exc).__name__}: {reason}",
                  file=sys.stderr)
        except (OSError, ValueError):  # a closed or broken stderr is not a reason to fail either
            pass
    return None


def _strict() -> bool:
    from aicore.ext import events as journal
    return journal.contracts_strict()
