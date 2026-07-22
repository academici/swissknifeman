"""Named reader for the legacy Claude SCHEMA=2 report; raw shape stays here."""
from . import reject_sensitive, source_provenance


class ClaudeRunReportReader:
    reader_id = "claude-run-report"
    reader_version = "1.0.0"

    def normalize(self, raw, *, project_id, raw_ref, source_bytes=None, declared_sha256=None):
        if not isinstance(raw, dict) or raw.get("schema") != 2:
            raise ValueError("ANALYTICS_UNKNOWN_SCHEMA")
        reject_sensitive(raw)
        session_id = raw.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("ANALYTICS_MISSING_PROVENANCE")
        source_hash, provenance = source_provenance(
            raw, supplied_bytes=source_bytes, declared_sha256=declared_sha256, raw_ref=raw_ref,
            reader_id=self.reader_id, reader_version=self.reader_version)
        bash = raw.get("bash") or {}
        metrics = {
            "tools": int((raw.get("tools") or {}).get("total", 0)),
            "files": len(raw.get("files_changed") or ()),
            "workflows": len(raw.get("workflows") or ()),
            "reads": int((raw.get("tools") or {}).get("by_name", {}).get("Read", 0)),
            "errors": len(raw.get("tool_failures") or ()),
        }
        return {"contract_version": "1.0.0", "provider_id": "claude-code",
                "session_id": session_id, "project_id": project_id,
                "event_id": "sha256:" + source_hash,
                "occurred_at": raw.get("generated_at") or "1970-01-01T00:00:00Z",
                "event_kind": "run_summary", "outcome": "ok" if not bash.get("failed") else "failed",
                "metrics": metrics,
                "provenance": provenance}
