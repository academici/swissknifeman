"""Managed Markdown blocks with idempotent marker- and hash-based updates.

Shared monorepo primitive, moved from maind.blocks. It preserves surrounding text
and detects drift with a short content hash. stdlib-only.
"""
import hashlib
import re


def content_hash(text: str) -> str:
    """Return a short, stable content hash for managed-artifact drift detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def managed_block(content: str, marker: str, *, owner: str = "maind") -> str:
    """Build a managed begin/end-marker block; ``owner`` is its sole writer."""
    h = content_hash(content)
    return (f"<!-- {marker} hash={h} (managed by {owner} — не редактировать вручную) -->\n"
            f"{content.rstrip()}\n<!-- /{marker} -->")


def upsert_block(text: str, content: str, marker: str,
                 *, owner: str = "maind") -> "tuple[str, bool, str]":
    """Insert or update a managed block and return ``(text, changed, state)``.

    State is ``absent``, ``stale``, or ``fresh``; surrounding text remains intact.
    """
    block = managed_block(content, marker, owner=owner)
    pat = re.compile(rf"<!-- {re.escape(marker)}\b.*?<!-- /{re.escape(marker)} -->",
                     re.DOTALL)
    m = pat.search(text or "")
    if m is None:
        sep = "" if not text or text.endswith("\n") else "\n"
        joiner = "\n" if text else ""
        return (text or "") + sep + joiner + block + "\n", True, "absent"
    if m.group(0).strip() == block.strip():
        return text, False, "fresh"
    return text[:m.start()] + block + text[m.end():], True, "stale"
