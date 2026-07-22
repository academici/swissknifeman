"""Reader orchestration and explicit copy+verify legacy migration."""
import hashlib
import json
from pathlib import Path

from .events import append_event, read_events
from .readers import reader_for


def normalize(provider_id, schema, raw, *, project_id, raw_ref, source_bytes=None, declared_sha256=None):
    return reader_for(provider_id, schema).normalize(
        raw, project_id=project_id, raw_ref=raw_ref, source_bytes=source_bytes,
        declared_sha256=declared_sha256)


def neutral_run_report(project_path, session=None):
    """Consumer-safe projection; callers use legacy files only as bounded fallback."""
    events = [event for event in read_events(project_path)
              if session is None or event.session_id == session]
    if not events:
        return None
    events.sort(key=lambda event: (event.occurred_at, event.event_id))
    metrics = {}
    for event in events:
        for name, value in event.metrics.items():
            metrics[name] = metrics.get(name, 0) + value
    latest = events[-1]
    return {"schema": "1.0.0", "session_id": latest.session_id,
            "generated_at": latest.occurred_at,
            "tools": {"total": metrics.get("tools", 0), "by_name": {}},
            "files_changed": ["normalized"] * int(metrics.get("files", 0)),
            "workflows": [], "tool_failures": ["normalized"] * int(metrics.get("errors", 0)),
            "bash": {"tests": [], "lints": [], "failed": []}, "devloop": {},
            "analytics_provenance": [dict(event.provenance) for event in events]}


def migrate_legacy(project_path, *, project_id, source, operation="plan"):
    source = Path(source)
    if operation not in {"plan", "dry-run", "check", "apply"}:
        raise ValueError("ANALYTICS_MIGRATION_CONFLICT")
    if not source.is_file():
        raise ValueError("ANALYTICS_CORRUPT_EVENT")
    before = source.read_bytes()
    try:
        raw = json.loads(before)
    except ValueError as exc:
        raise ValueError("ANALYTICS_CORRUPT_EVENT") from exc
    source_hash = hashlib.sha256(before).hexdigest()
    event = normalize("claude-code", 2, raw, project_id=project_id,
                      raw_ref="local:legacy-" + source_hash[:16], source_bytes=before,
                      declared_sha256=source_hash)
    found = [item for item in read_events(project_path)
             if (item.provider_id, item.project_id, item.session_id)
             == (event["provider_id"], event["project_id"], event["session_id"])]
    if found and (found[0].event_id != event["event_id"]
                  or found[0].provenance["sha256"] != event["provenance"]["sha256"]):
        raise ValueError("ANALYTICS_MIGRATION_CONFLICT")
    result = {"operation": operation, "event_id": event["event_id"], "would_copy": not bool(found),
              "source_sha256": source_hash}
    if operation == "apply" and not found:
        append_event(project_path, event, audit={"code": "ANALYTICS_LEGACY_INFERRED_PROVIDER",
                                                 "reader_version": "1.0.0", "redaction": "passed",
                                                 "source_sha256": source_hash})
        if source.read_bytes() != before:
            raise ValueError("ANALYTICS_MIGRATION_CONFLICT")
        result["copied"] = True
    return result
