"""Neutral append-only analytics event store; provider parsing lives in readers."""
import json
from pathlib import Path

from core.runs import EventEnvelope, event_key


def analytics_home(project_path):
    return Path(project_path) / ".swissknife" / "analytics"


def events_path(project_path):
    return analytics_home(project_path) / "events.ndjson"


def audit_path(project_path):
    return analytics_home(project_path) / "audit.ndjson"


def append_event(project_path, event, *, audit=None):
    envelope = event if isinstance(event, EventEnvelope) else EventEnvelope.from_mapping(event)
    dst = events_path(project_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    payload = {name: getattr(envelope, name) for name in (
        "contract_version", "provider_id", "session_id", "project_id", "event_id", "occurred_at",
        "event_kind", "outcome", "metrics", "provenance")}
    payload["metrics"] = dict(payload["metrics"])
    payload["provenance"] = dict(payload["provenance"])
    existing = {event_key(item) for item in read_events(project_path)}
    if event_key(envelope) in existing:
        return False
    with open(dst, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    if audit is not None:
        apath = audit_path(project_path)
        with open(apath, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(audit), sort_keys=True) + "\n")
    return True


def read_events(project_path):
    result = []
    path = events_path(project_path)
    if not path.is_file():
        return result
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                result.append(EventEnvelope.from_mapping(json.loads(line)))
            except (ValueError, TypeError):
                continue
    return result
