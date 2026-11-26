"""Exact instruction identity and Unicode shortlist scoring."""

import re
from unicodedata import normalize

TOKEN_RE = re.compile(r"[^\W_]+")


def norm(text: str) -> str:
    return normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").strip()


def tokens(text: str) -> frozenset[str]:
    return frozenset(TOKEN_RE.findall(normalize("NFC", text).casefold()))


def jaccard(a: str, b: str) -> float:
    left, right = tokens(a), tokens(b)
    union = left | right
    return len(left & right) / len(union) if union else 0.0
