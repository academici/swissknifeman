"""The ``orch.*`` events that stand next to a beacon of the progress log (knowledge/p12-observability#types): the
beacon says it to a person, the event to a consumer of the journal. Emission is best-effort and only with
``events.enabled`` (``orch.events.emit`` decides); the subject is ``<run>/<item>``, the correlation id the run id."""
from __future__ import annotations

from typing import Optional

from orch import events
from orch.conductor.domain.item import Item

RATE_LIMIT_CLASSES = {"rate_limit": "orch.provider.rate-limited", "quota": "orch.provider.quota-exhausted"}


def beacon_event(self, event_type: str, item: Optional[Item], data: dict) -> Optional[str]:
    """Journal ``event_type`` about ``item`` (or the run when ``item`` is None); ``data`` gets ``run_id``, ``work_id``
    and ``item``, and a ``None`` value is left out. The id of the event, ``None`` when none was journaled."""
    run_id = item.orch_run if item is not None else self.run_id
    base = {"run_id": run_id}
    if item is not None:
        base.update(work_id=item.input_doc.get("input_id") or item.ref, item=item.ref)
    body = {key: value for key, value in {**base, **data}.items() if value is not None}
    return events.emit(event_type, body, subject=f"{run_id}/{item.ref}" if item is not None else run_id,
                       correlationid=run_id, settings=self.settings, project=self.project,
                       config_file=self.config_file)


def route_data(route: dict) -> dict:
    """``{provider, model_class?, model?, effort?}`` of a route for an event."""
    return {key: route[key] for key in ("provider", "model_class", "model", "effort") if route.get(key)}


def provider_limit(self, item: Item, key: str, role: str, provider: str, error_class: str, reason_code: str,
                   until: Optional[str] = None, wait_s: Optional[int] = None) -> None:
    """``orch.provider.rate-limited`` / ``orch.provider.quota-exhausted`` for a wait or a gate; other error classes
    (a transient transport failure) are not a limit and give no event."""
    event_type = RATE_LIMIT_CLASSES.get(error_class)
    if event_type and provider:
        self._beacon_event(event_type, item, {"role": role, "step": key, "provider": provider,
                                              "reason_code": reason_code, "until": until, "wait_s": wait_s})


def route_fallback(self, item: Item, key: Optional[str], role: str, old: dict, new: dict, reasons: list) -> None:
    """``orch.provider.fallback`` for a role that moved to another route."""
    self._beacon_event("orch.provider.fallback", item, {"role": role, "step": key, "from": route_data(old),
                                                        "to": route_data(new), "reason_codes": list(reasons)})
