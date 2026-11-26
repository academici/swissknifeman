"""Unit tests for the built-in heuristic token estimator (context §4.3)."""

from __future__ import annotations

import math

from skm.kernel.tokens import TokenEstimator
from skm.platform.tokens.heuristic import (
    CHARS_PER_TOKEN_CYR,
    CHARS_PER_TOKEN_LAT,
    ESTIMATOR_ID,
    HeuristicTokenEstimator,
    estimate_tokens,
)


def test_constants_and_estimator_id() -> None:
    assert CHARS_PER_TOKEN_CYR == 2.9
    assert CHARS_PER_TOKEN_LAT == 3.4
    assert ESTIMATOR_ID == "heuristic-v1"
    estimator: TokenEstimator = HeuristicTokenEstimator()
    assert estimator.estimator_id == "heuristic-v1"


def test_empty_string_returns_zero() -> None:
    estimator = HeuristicTokenEstimator()
    assert estimate_tokens("") == 0
    assert estimator.estimate("") == 0


def test_pure_latin_and_ascii_ratio() -> None:
    estimator = HeuristicTokenEstimator()
    for length in (1, 3, 4, 10, 34, 35, 100):
        sample = "a" * length
        expected = math.ceil(length / CHARS_PER_TOKEN_LAT)
        assert estimate_tokens(sample) == expected
        assert estimator.estimate(sample) == expected


def test_pure_cyrillic_and_cyrillic_supplement_ratio() -> None:
    estimator = HeuristicTokenEstimator()
    # Basic Cyrillic (\u0400..\u04ff) and Cyrillic Supplement (\u0500..\u052f)
    sample_basic = "приветмир"  # 9 Cyrillic chars -> ceil(9 / 2.9) = ceil(3.103...) = 4
    assert estimate_tokens(sample_basic) == math.ceil(len(sample_basic) / CHARS_PER_TOKEN_CYR)
    assert estimate_tokens(sample_basic) == 4

    supplement_edges = "\u0400\u04ff\u0500\u052f"
    assert estimator.estimate(supplement_edges) == math.ceil(4 / CHARS_PER_TOKEN_CYR)


def test_boundary_characters_outside_cyrillic_ranges_use_latin_ratio() -> None:
    # \u03ff (Greek) and \u0530 (Armenian) sit immediately outside \u0400..\u052f
    outside = "\u03ff\u0530" * 5  # 10 non-Cyrillic chars -> ceil(10 / 3.4) = 3
    assert estimate_tokens(outside) == math.ceil(10 / CHARS_PER_TOKEN_LAT)
    assert estimate_tokens(outside) == 3


def test_mixed_cyrillic_and_latin_text_is_deterministic() -> None:
    estimator = HeuristicTokenEstimator()
    mixed = "Задача P09.04.a: draft -> final protocol!"
    cyr_count = sum(1 for ch in mixed if ("\u0400" <= ch <= "\u04ff") or ("\u0500" <= ch <= "\u052f"))
    lat_count = len(mixed) - cyr_count
    expected = math.ceil(cyr_count / CHARS_PER_TOKEN_CYR + lat_count / CHARS_PER_TOKEN_LAT)
    first = estimator.estimate(mixed)
    second = estimator.estimate(mixed)
    assert first == expected
    assert second == expected
