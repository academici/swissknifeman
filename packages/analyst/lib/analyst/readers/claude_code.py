"""Named reader for the legacy Claude SCHEMA=2 report; raw shape stays here."""
from . import reject_sensitive, source_provenance


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("ANALYTICS_CORRUPT_EVENT")
    return value


def _list(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("ANALYTICS_CORRUPT_EVENT")
    return value


def _usage_scalar(value):
    if not isinstance(value, dict):
        raise ValueError("ANALYTICS_CORRUPT_EVENT")
    totals = value.get("totals")
    if isinstance(totals, dict):
        observed = [_number(totals[name]) for name in ("in", "out", "cache_read", "cache_creation")
                    if name in totals]
        return sum(observed) if observed else None
    agents = value.get("agents")
    if agents is None:
        return None
    observed = []
    for agent in _list(agents):
        if not isinstance(agent, dict):
            raise ValueError("ANALYTICS_CORRUPT_EVENT")
        observed.extend(_number(agent[name]) for name in ("in", "out", "cache_read", "cache_creation")
                        if name in agent)
    return sum(observed) if observed else None


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
        metrics = {}
        tools = raw.get("tools")
        if tools is not None:
            if not isinstance(tools, dict):
                raise ValueError("ANALYTICS_CORRUPT_EVENT")
            if "total" in tools:
                metrics["tools"] = _number(tools["total"])
            if "by_name" in tools:
                by_name = tools["by_name"]
                if not isinstance(by_name, dict):
                    raise ValueError("ANALYTICS_CORRUPT_EVENT")
        reads = raw.get("reads")
        if reads is not None:
            if not isinstance(reads, dict):
                raise ValueError("ANALYTICS_CORRUPT_EVENT")
            if "total" in reads:
                metrics["reads"] = _number(reads["total"])
        for raw_name, metric_name in (("files_changed", "files"), ("workflows", "workflows"),
                                      ("tool_failures", "errors")):
            if raw_name in raw:
                metrics[metric_name] = len(_list(raw[raw_name]))
        retrieval = raw.get("retrieval")
        if retrieval is not None:
            if not isinstance(retrieval, dict):
                raise ValueError("ANALYTICS_CORRUPT_EVENT")
            if "calls" in retrieval:
                metrics["retrieval"] = _number(retrieval["calls"])
        devloop = raw.get("devloop")
        if devloop is not None:
            if not isinstance(devloop, dict):
                raise ValueError("ANALYTICS_CORRUPT_EVENT")
            observed = [_list(devloop[name]) for name in ("workarounds", "deferred", "open_questions")
                        if name in devloop]
            if observed:
                metrics["devloop"] = sum(len(value) for value in observed)
        maind = raw.get("maind")
        if maind is not None:
            if not isinstance(maind, dict):
                raise ValueError("ANALYTICS_CORRUPT_EVENT")
            observed = []
            for item in maind.values():
                if not isinstance(item, dict):
                    raise ValueError("ANALYTICS_CORRUPT_EVENT")
                if "calls" in item:
                    observed.append(_number(item["calls"]))
            if observed:
                metrics["maind"] = sum(observed)
        if "usage" in raw:
            usage = _usage_scalar(raw["usage"])
            if usage is not None:
                metrics["usage"] = usage
        bash = raw.get("bash")
        if bash is not None and not isinstance(bash, dict):
            raise ValueError("ANALYTICS_CORRUPT_EVENT")
        outcome = "unknown"
        if isinstance(bash, dict) and "failed" in bash:
            outcome = "failed" if _list(bash["failed"]) else "ok"
        return {"contract_version": "1.0.0", "provider_id": "claude-code",
                "session_id": session_id, "project_id": project_id,
                "event_id": "sha256:" + source_hash,
                "occurred_at": raw.get("generated_at") or "1970-01-01T00:00:00Z",
                "event_kind": "run_summary", "outcome": outcome,
                "metrics": metrics,
                "provenance": provenance}
