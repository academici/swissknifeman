"""Risk score of dynamic review (execution §5.9; port of the conductor risk tests)."""

from __future__ import annotations

from typing import Any

import pytest

from skm.modules.execution.domain.risk import (
    DEFAULT_WEIGHTS,
    RiskFacts,
    path_matches,
    review_triggered,
    score,
)


def facts(**changes: Any) -> RiskFacts:
    values: dict[str, Any] = {
        "changed": ("src/app/core.py",),
        "outside": (),
        "diff_lines": 10,
        "red_first": False,
        "deviation": False,
        "recommended": False,
    }
    values.update(changes)
    return RiskFacts(**values)


FEATURE_CASES: list[tuple[str, dict[str, Any]]] = [
    ("public_cli", {"changed": ("bin/skm",)}),
    ("public_cli", {"changed": ("src/skm/cli.py",)}),
    ("schema", {"changed": ("src/skm/schemas/x.json",)}),
    ("schema", {"changed": ("db/migrations/0001.sql",)}),
    ("security", {"changed": ("src/auth/token.py",)}),
    ("security", {"changed": (".github/workflows/ci.yml",)}),
    ("diff_size", {"diff_lines": 400}),
    ("red_first", {"red_first": True}),
    ("deviation", {"deviation": True}),
    ("outside_write_set", {"outside": ("docs/x.md",)}),
    ("executor_recommended", {"recommended": True}),
]


@pytest.mark.parametrize(("name", "change"), FEATURE_CASES)
def test_each_feature_counts_its_weight(name: str, change: dict[str, Any]) -> None:
    risk = score(facts(**change), {})
    assert [feature.name for feature in risk.features] == [name]
    assert risk.score == DEFAULT_WEIGHTS[name]
    assert risk.features[0].evidence


def test_no_feature_scores_zero() -> None:
    risk = score(facts(diff_lines=399), {})
    assert (risk.score, risk.features, risk.critical) == (0, (), ())
    assert not review_triggered(risk, 60)


def test_shared_is_project_specific_and_empty_by_default() -> None:
    assert score(facts(changed=("packages/aicore/x.py",)), {}).score == 0
    config: dict[str, Any] = {"execution.review.risk.patterns": {"shared": ["packages/aicore/**"]}}
    assert score(facts(changed=("packages/aicore/x.py",)), config).score == 15


def test_weight_zero_switches_a_feature_off_including_critical() -> None:
    risky = facts(changed=("src/auth/a.py",))
    assert score(risky, {}).critical == ("security",)
    off = score(risky, {"execution.review.risk.weights": {"security": 0}})
    assert (off.score, off.features, off.critical) == (0, (), ())


def test_critical_feature_adds_review_below_threshold() -> None:
    risk = score(facts(changed=("src/auth/a.py",)), {})
    assert risk.score == 30 < 60
    assert review_triggered(risk, 60)
    no_critical: dict[str, Any] = {"execution.review.risk.critical": []}
    assert not review_triggered(score(facts(changed=("src/auth/a.py",)), no_critical), 60)


def test_threshold_and_cap() -> None:
    everything = facts(
        changed=("bin/x", "src/schemas/a.json", "src/auth/a.py"),
        outside=("x",),
        diff_lines=5000,
        red_first=True,
        deviation=True,
        recommended=True,
    )
    risk = score(everything, {})
    assert risk.score == 100
    assert sum(feature.weight for feature in risk.features) > 100
    assert review_triggered(score(facts(recommended=True, deviation=True, red_first=True), {}), 50)
    assert not review_triggered(score(facts(red_first=True), {}), 60)


def test_custom_diff_lines_and_patterns() -> None:
    assert score(facts(diff_lines=50), {"execution.review.risk.diff_lines": 50}).score == 10
    cli: dict[str, Any] = {"execution.review.risk.patterns": {"public_cli": ["lib/api.py"]}}
    assert score(facts(changed=("lib/api.py",)), cli).score == 25


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("bin/skm", "bin/**", True),
        ("cli.py", "**/cli.py", True),
        ("a/b/cli.py", "**/cli.py", True),
        ("a/b/cli.pyc", "**/cli.py", False),
        ("src/permissions.py", "**/permissions*", True),
        ("src/x/permissions/y.py", "**/permissions*", False),
        ("./src/auth/x.py", "**/auth/**", True),
        ("src\\auth\\x.py", "**/auth/**", True),
        ("src/a.py", "src/?.py", True),
        ("src/a/b.py", "src/*.py", False),
    ],
)
def test_path_matches(path: str, pattern: str, expected: bool) -> None:
    assert path_matches(path, pattern) is expected
