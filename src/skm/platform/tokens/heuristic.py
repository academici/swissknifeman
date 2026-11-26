"""Deterministic character-ratio token estimator (context §4.3; donor ``aicore/content/budget.py:32-49``)."""

from __future__ import annotations

import math
from typing import Final, Literal

__all__ = [
    "CHARS_PER_TOKEN_CYR",
    "CHARS_PER_TOKEN_LAT",
    "ESTIMATOR_ID",
    "HeuristicTokenEstimator",
    "estimate_tokens",
]

CHARS_PER_TOKEN_CYR: Final[float] = 2.9
CHARS_PER_TOKEN_LAT: Final[float] = 3.4
ESTIMATOR_ID: Final[Literal["heuristic-v1"]] = "heuristic-v1"


def _is_cyrillic(ch: str) -> bool:
    return ("\u0400" <= ch <= "\u04ff") or ("\u0500" <= ch <= "\u052f")


def estimate_tokens(text: str) -> int:
    """Estimate token count deterministically from Cyrillic and non-Cyrillic character counts."""
    if not text:
        return 0
    cyr = sum(1 for ch in text if _is_cyrillic(ch))
    lat = len(text) - cyr
    return math.ceil(cyr / CHARS_PER_TOKEN_CYR + lat / CHARS_PER_TOKEN_LAT)


class HeuristicTokenEstimator:
    """Built-in ``TokenEstimator`` implementation ``heuristic-v1``."""

    estimator_id: str = ESTIMATOR_ID

    def estimate(self, text: str) -> int:
        return estimate_tokens(text)
