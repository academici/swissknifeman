"""Telemetry names of analyst: spans of Unified Agent Trace dispatch events and metric labels.

The names come from ``aicore.util.telemetry`` (the conventions of the foundation); analyst only maps its own
vocabulary onto them. OpenTelemetry export is not part of analyst. The closed formats ``unified-agent-trace/v1``
and ``reliability-metrics-digest/v1`` are not changed: their fields are record fields, not metric labels.
"""
from aicore.util.telemetry import metric_label_problems, span_name

from .trace import DISPATCH_EVENTS

_STAGE = "skm.stage"
_EFFECT = "skm.effect.apply"
_RUN = "skm.run"

SPAN_FOR_DISPATCH_EVENT = {
    "dispatch": _STAGE,
    "pre-mutation-allow": _EFFECT,
    "pre-mutation-deny": _EFFECT,
    "mutation-complete": _EFFECT,
    "validation-green": _STAGE,
    "validation-red": _STAGE,
    "typed-finding": _STAGE,
    "same-finding-third": _STAGE,
    "pre-final-allow": _STAGE,
    "pre-final-deny": _STAGE,
    "close-committed": _STAGE,
    "audit-verdict": _STAGE,
    "owner-decision": _RUN,
    "escalation-trigger": _RUN,
    "skip-by-decision": _RUN,
}

# Grouping keys analyst puts on counters: the type and the outcome of recorded ecosystem events
# (``analyst events list``, ``analyst status``). The conventions name them as follows; ids such as run_id,
# session_id, trace_id, project_id or event_id stay fields of records and are never labels.
LABEL_NAME = {"type": "skm.event.type", "outcome": "skm.outcome", "provider": "skm.provider"}
METRIC_LABELS = tuple(LABEL_NAME.values())

for _event, _span in SPAN_FOR_DISPATCH_EVENT.items():
    span_name(_span)


def span_for(event):
    """The span name of a dispatch event of the trace; ``KeyError`` for an unknown event."""
    return SPAN_FOR_DISPATCH_EVENT[event]


__all__ = ["DISPATCH_EVENTS", "LABEL_NAME", "METRIC_LABELS", "SPAN_FOR_DISPATCH_EVENT",
           "metric_label_problems", "span_for"]
