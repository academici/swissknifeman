"""Bounded working memory. Metadata lives in content because the daemon rewrites type.

Repository documents, plans and git own durable information. Every memory expires;
reading never renews it. Legacy records get at most 72 hours from creation.
"""
import base64
import json
import math
import os
import re
import time
from datetime import datetime

DEFAULT_TTL_HOURS = 48
MAX_TTL_HOURS = 72
MAX_CHARS = 800
MAX_SCOPE_ITEMS = 8
PREFIX = "[maind-memory:"
MARKER_RE = re.compile(r"^\[maind-memory:([A-Za-z0-9_=-]+)\]\s?")
SCOPE_RE = re.compile(r"^\[\[s:([^\]]+)\]\]\s?")
ALLOWED_KEYS = {"context", "fact", "blocker", "coordination", "active-handoff", "health-probe"}
JOURNAL_KEYS = {"progress", "plan-progress", "checkpoint", "session-log", "decision",
                "plan-decision", "architecture", "release", "feature-log", "ecosystem-link"}
# Deliberately narrow structural patterns, not individual words such as "plan" or "decision".
REPOSITORY_COPY_RE = re.compile(
    r"^(?:\[maind:(?:ecosystem-link|feature-log)\]|AD\d{2}\b|"
    r"P\d+(?:\.\d+)?\s+(?:closed[- ]green|designed|completed)\b)", re.I)


def unpack(text):
    """Return clean text and metadata (None for legacy, {} for malformed envelopes)."""
    m = MARKER_RE.match(text or "")
    if not m:
        return text, {} if (text or "").startswith(PREFIX) else None
    try:
        meta = json.loads(base64.urlsafe_b64decode(m[1]).decode("utf-8"))
        if not isinstance(meta, dict):
            return text, {}
    except (ValueError, UnicodeError):
        return text, {}
    return text[m.end():], meta


def record_parts(row):
    obs = row.get("observation") or row
    raw = row.get("content") or obs.get("narrative") or obs.get("title") or ""
    m = SCOPE_RE.match(raw)
    scope, text = (m[1], raw[m.end():]) if m else (None, raw)
    while SCOPE_RE.match(text):
        text = text[SCOPE_RE.match(text).end():]
    clean, meta = unpack(text)
    return scope, clean or "", meta


def timestamp(value):
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value) if math.isfinite(value) else None
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp() if dt.tzinfo is not None else None
    except (ValueError, AttributeError, OverflowError):
        return None


def expired(row, *, now=None):
    now = time.time() if now is None else now
    _scope, _text, meta = record_parts(row)
    if meta is not None:
        created, expires = timestamp(meta.get("created_at")), timestamp(meta.get("expires_at"))
        if created is None or expires is None or expires <= created or created > now + 60:
            return True
        return now >= min(expires, created + MAX_TTL_HOURS * 3600)
    created = timestamp(row.get("createdAt") or row.get("timestamp"))
    # Recall resolves search projections through a full dump before applying this policy.
    # Unknown age and future timestamps cannot establish bounded temporary context.
    return created is None or created > now + 60 or now >= created + MAX_TTL_HOURS * 3600


def rejection_reason(key, value):
    if key in JOURNAL_KEYS:
        return "repository-journal"
    if key not in ALLOWED_KEYS:
        return "unsupported-category"
    if not isinstance(value, str) or not value.strip():
        return "empty"
    if len(value) > MAX_CHARS:
        return "oversized"
    if "[[s:" in value or PREFIX in value:
        return "reserved-marker"
    if value.lstrip().startswith(("```", "# ", "## ", "{", "[maind:ecosystem-link]",
                                  "[maind:feature-log]")):
        return "repository-copy"
    if key != "active-handoff" and REPOSITORY_COPY_RE.match(value.strip()):
        return "repository-copy"
    return None


def envelope(key, value, *, ttl_hours=DEFAULT_TTL_HOURS, source="internal", now=None):
    key = (key or "context").strip().lower()
    reason = rejection_reason(key, value)
    if reason:
        raise ValueError(f"memory rejected: {reason}; not durable memory. Keep plans, decisions, "
                         "progress and code/git facts in repository artifacts; use a short "
                         "context/blocker/coordination or one active-handoff (max 800 chars).")
    if isinstance(ttl_hours, bool) or not isinstance(ttl_hours, (int, float)) or \
            not math.isfinite(ttl_hours) or not 0 < ttl_hours <= MAX_TTL_HOURS:
        raise ValueError("ttl_hours must be positive and at most 72 (default 48)")
    now = time.time() if now is None else now
    writer = next((name for name, var in (("grok", "GROK_SESSION_ID"),
                  ("codex", "CODEX_THREAD_ID"), ("claude-code", "CLAUDE_SESSION_ID"),
                  ("cursor", "CURSOR_SESSION_ID"), ("antigravity", "ANTIGRAVITY_SESSION_ID")) if os.environ.get(var)), "unknown")
    meta = {"key": key, "created_at": now,
            "expires_at": now + (min(ttl_hours * 3600, 300) if key == "health-probe"
                                  else ttl_hours * 3600), "source": source, "writer": writer}
    encoded = base64.urlsafe_b64encode(json.dumps(meta, separators=(",", ":")).encode()).decode()
    return f"{PREFIX}{encoded}] {value.strip()}"


def prune_reason(row, *, now=None):
    scope, text, meta = record_parts(row)
    if row.get("isLatest") is False:
        return "superseded"
    if scope is None:
        return "unscoped"
    if expired(row, now=now):
        return "expired"
    if meta is None and timestamp(row.get("createdAt") or row.get("timestamp")) is None:
        return "missing-timestamp"
    key = meta.get("key", "context") if meta else \
        ("active-handoff" if text.startswith("[active-handoff]") else "context")
    return rejection_reason(key, text)
