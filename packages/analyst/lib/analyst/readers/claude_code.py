"""Named reader for the legacy Claude SCHEMA=2 report; raw shape stays here."""
import hashlib


class ClaudeRunReportReader:
    reader_id = "claude-run-report"
    reader_version = "1.0.0"

    def normalize(self, raw, *, project_id, raw_ref):
        if not isinstance(raw, dict) or raw.get("schema") != 2:
            raise ValueError("ANALYTICS_UNKNOWN_SCHEMA")
        session_id = raw.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("ANALYTICS_MISSING_PROVENANCE")
        body = str(raw).encode("utf-8")
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
                "event_id": "sha256:" + hashlib.sha256(body).hexdigest()[:24],
                "occurred_at": raw.get("generated_at") or "1970-01-01T00:00:00Z",
                "event_kind": "run_summary", "outcome": "ok" if not bash.get("failed") else "failed",
                "metrics": metrics,
                "provenance": {"raw_ref": raw_ref, "sha256": hashlib.sha256(body).hexdigest(),
                               "reader_id": self.reader_id, "reader_version": self.reader_version}}
