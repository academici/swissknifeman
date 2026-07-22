"""Explicit provider reader registry and safe source/provenance boundary."""
import hashlib
import json
from types import MappingProxyType


def source_bytes(raw, supplied):
    """Canonical fallback is only for in-memory fixtures; file callers pass raw bytes."""
    if supplied is not None:
        return bytes(supplied)
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def source_provenance(raw, *, supplied_bytes, declared_sha256, raw_ref, reader_id, reader_version):
    if (not isinstance(raw_ref, str) or not raw_ref.startswith("local:")
            or not raw_ref.removeprefix("local:") or "/" in raw_ref.removeprefix("local:")
            or ".." in raw_ref):
        raise ValueError("ANALYTICS_MISSING_PROVENANCE")
    actual = hashlib.sha256(source_bytes(raw, supplied_bytes)).hexdigest()
    if declared_sha256 is None:
        declared_sha256 = actual
    if not isinstance(declared_sha256, str) or len(declared_sha256) != 64:
        raise ValueError("ANALYTICS_MISSING_PROVENANCE")
    if declared_sha256 != actual:
        raise ValueError("ANALYTICS_CORRUPT_EVENT")
    return actual, {"raw_ref": raw_ref, "sha256": actual,
                    "reader_id": reader_id, "reader_version": reader_version}


def reject_sensitive(value):
    """Fail closed before normalization; never expose the rejected value."""
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or any(word in key.lower() for word in
                                               ("prompt", "secret", "transcript", "raw_body")):
                raise ValueError("ANALYTICS_REDACTION_FAILED")
            reject_sensitive(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_sensitive(child)


from .claude_code import ClaudeRunReportReader
from .codex import CodexCaptureReader

READERS = MappingProxyType({
    ("claude-code", 2): ClaudeRunReportReader(),
    ("codex", 1): CodexCaptureReader(),
})


def reader_for(provider_id, schema):
    try:
        return READERS[(provider_id, schema)]
    except KeyError as exc:
        if provider_id not in {key[0] for key in READERS}:
            raise ValueError("ANALYTICS_UNKNOWN_PROVIDER") from exc
        raise ValueError("ANALYTICS_UNKNOWN_SCHEMA") from exc
