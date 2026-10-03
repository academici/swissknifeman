"""Named reader for the P6 generated Codex capture envelope, never Claude fallback."""
from core.runs import ANALYTICS_METRICS

from . import reject_sensitive, source_provenance


class CodexCaptureReader:
    reader_id = "codex-hook-context"
    reader_version = "1.0.0"
    provider_id = "codex"

    def normalize(self, raw, *, project_id, raw_ref, source_bytes=None, declared_sha256=None):
        if not isinstance(raw, dict) or raw.get("schema") != 1:
            raise ValueError("ANALYTICS_UNKNOWN_SCHEMA")
        reject_sensitive(raw)
        session_id = raw.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("ANALYTICS_MISSING_PROVENANCE")
        metrics = raw.get("metrics")
        if (not isinstance(metrics, dict) or not set(metrics).issubset(ANALYTICS_METRICS)
                or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                           for value in metrics.values())):
            raise ValueError("ANALYTICS_REDACTION_FAILED")
        source_hash, provenance = source_provenance(
            raw, supplied_bytes=source_bytes, declared_sha256=declared_sha256, raw_ref=raw_ref,
            reader_id=self.reader_id, reader_version=self.reader_version)
        return {"contract_version": "1.0.0", "provider_id": self.provider_id,
                "session_id": session_id, "project_id": project_id,
                "event_id": "sha256:" + source_hash,
                "occurred_at": raw.get("occurred_at") or "1970-01-01T00:00:00Z",
                "event_kind": "run_summary", "outcome": raw.get("outcome", "unknown"),
                "metrics": metrics,
                "provenance": provenance}
