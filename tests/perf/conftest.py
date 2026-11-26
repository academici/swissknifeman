"""Persist opt-in benchmark samples before asserting their budgets."""

import json
from collections.abc import Callable, Sequence
from math import ceil
from pathlib import Path
from statistics import median
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("perf")
    group.addoption("--perf-results", type=Path, help="Append benchmark samples to this JSON Lines file.")
    group.addoption(
        "--perf-history-dsn", help="Optional dedicated PostgreSQL test server for the history dataset."
    )


@pytest.fixture
def measure(request: pytest.FixtureRequest) -> Callable[..., dict[str, float]]:
    def record(series: str, samples: Sequence[float], **facts: Any) -> dict[str, float]:
        ordered = sorted(samples)
        stats = {"p50": median(ordered), "p95": ordered[ceil(0.95 * len(ordered)) - 1]} if ordered else {}
        data = {
            "test": request.node.name,
            "series": series,
            "samples": [round(x, 3) for x in samples],
            **{key: round(value, 3) for key, value in stats.items()},
            **facts,
        }
        line = json.dumps(data, sort_keys=True)
        print(line, flush=True)
        if path := request.config.getoption("--perf-results"):
            with path.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
        return stats

    return record
