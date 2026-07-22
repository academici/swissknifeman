"""Named reader for the P6 generated Codex capture envelope, never Claude fallback."""
import hashlib


class CodexCaptureReader:
    reader_id = "codex-hook-context"
    reader_version = "1.0.0"

    def normalize(self, raw, *, project_id, raw_ref):
        if not isinstance(raw, dict) or raw.get("schema") != 1:
            raise ValueError("ANALYTICS_UNKNOWN_SCHEMA")
        session_id = raw.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("ANALYTICS_MISSING_PROVENANCE")
        body = str(raw).encode("utf-8")
        metrics = raw.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("ANALYTICS_CORRUPT_EVENT")
        return {"contract_version": "1.0.0", "provider_id": "codex",
                "session_id": session_id, "project_id": project_id,
                "event_id": "sha256:" + hashlib.sha256(body).hexdigest()[:24],
                "occurred_at": raw.get("occurred_at") or "1970-01-01T00:00:00Z",
                "event_kind": "run_summary", "outcome": raw.get("outcome", "unknown"),
                "metrics": metrics,
                "provenance": {"raw_ref": raw_ref, "sha256": hashlib.sha256(body).hexdigest(),
                               "reader_id": self.reader_id, "reader_version": self.reader_version}}
