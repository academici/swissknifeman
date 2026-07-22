"""Explicit provider reader registry; no filesystem, content, or import-order detection."""
from .claude_code import ClaudeRunReportReader
from .codex import CodexCaptureReader


READERS = {
    ("claude-code", 2): ClaudeRunReportReader(),
    ("codex", 1): CodexCaptureReader(),
}


def reader_for(provider_id, schema):
    try:
        return READERS[(provider_id, schema)]
    except KeyError as exc:
        if provider_id not in {key[0] for key in READERS}:
            raise ValueError("ANALYTICS_UNKNOWN_PROVIDER") from exc
        raise ValueError("ANALYTICS_UNKNOWN_SCHEMA") from exc
