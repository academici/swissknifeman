"""Named reader for Cursor hook envelopes (schema=1)."""
from core.runs import ANALYTICS_METRICS, ANALYTICS_OUTCOMES

from . import reject_sensitive, source_provenance

_TOP_LEVEL_REQUIRED = frozenset((
    "schema", "provider_id", "session_id", "occurred_at", "event_kind", "outcome", "metrics", "cursor",
))
_TOP_LEVEL_OPTIONAL = frozenset(("conversation_id",))
_TOP_LEVEL_ALLOWED = _TOP_LEVEL_REQUIRED | _TOP_LEVEL_OPTIONAL
_CURSOR_REASON = frozenset(("completed", "aborted", "error", "window_close", "user_close"))
_CURSOR_FIELDS = frozenset(("end_reason", "final_status", "native_session_id", "duration_ms"))


class CursorCaptureReader:
    reader_id = "cursor-hook-envelope"
    reader_version = "1.0.0"

    def normalize(self, raw, *, project_id, raw_ref, source_bytes=None, declared_sha256=None):
        if not isinstance(raw, dict) or raw.get("schema") != 1:
            raise ValueError("ANALYTICS_UNKNOWN_SCHEMA")
        reject_sensitive(raw)
        if not set(raw).issubset(_TOP_LEVEL_ALLOWED):
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        if not _TOP_LEVEL_REQUIRED.issubset(raw):
            raise ValueError("ANALYTICS_MISSING_PROVENANCE")
        if raw.get("provider_id") != "cursor":
            raise ValueError("ANALYTICS_UNKNOWN_PROVIDER")
        if raw.get("event_kind") != "run_summary":
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        session_id = raw.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("ANALYTICS_MISSING_PROVENANCE")
        conversation_id = raw.get("conversation_id")
        if conversation_id is not None:
            if not isinstance(conversation_id, str) or not conversation_id:
                raise ValueError("ANALYTICS_REDACTION_FAILED")
            if conversation_id != session_id:
                raise ValueError("ANALYTICS_REDACTION_FAILED")
        outcome = raw.get("outcome")
        if outcome not in ANALYTICS_OUTCOMES:
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        metrics = raw.get("metrics")
        if (not isinstance(metrics, dict) or not set(metrics).issubset(ANALYTICS_METRICS)
                or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                           for value in metrics.values())):
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        cursor = raw.get("cursor")
        if not isinstance(cursor, dict) or not set(cursor).issubset(_CURSOR_FIELDS):
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        reason = cursor.get("end_reason")
        if reason not in _CURSOR_REASON:
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        for key in ("final_status", "native_session_id"):
            value = cursor.get(key)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError("ANALYTICS_REDACTION_FAILED")
        duration_ms = cursor.get("duration_ms")
        if duration_ms is not None and (not isinstance(duration_ms, (int, float))
                                        or isinstance(duration_ms, bool)):
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        source_hash, provenance = source_provenance(
            raw, supplied_bytes=source_bytes, declared_sha256=declared_sha256, raw_ref=raw_ref,
            reader_id=self.reader_id, reader_version=self.reader_version)
        return {"contract_version": "1.0.0", "provider_id": "cursor",
                "session_id": session_id, "project_id": project_id,
                "event_id": "sha256:" + source_hash,
                "occurred_at": raw.get("occurred_at") or "1970-01-01T00:00:00Z",
                "event_kind": "run_summary", "outcome": outcome,
                "metrics": metrics,
                "provenance": provenance}
