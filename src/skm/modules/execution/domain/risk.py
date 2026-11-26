"""Risk score of an executor round for dynamic review (execution §5.9; port of ``conductor/risk.py``).

``score(facts, config)`` sums the weights of the present features and caps the sum at 100. ``config`` holds
the frozen values by their dotted keys (``execution.review.risk.weights``, ``.patterns``, ``.diff_lines``,
``.critical``), as in the run's config snapshot; a missing key takes the §5.9 default and a weight of 0
switches its feature off. A present feature listed in ``critical`` asks for a review by itself
(``review_triggered``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skm.kernel.json_types import JsonValue

__all__ = [
    "DEFAULT_CRITICAL",
    "DEFAULT_DIFF_LINES",
    "DEFAULT_PATTERNS",
    "DEFAULT_THRESHOLD",
    "DEFAULT_WEIGHTS",
    "FEATURES",
    "RiskFacts",
    "RiskFeature",
    "RiskScore",
    "matching",
    "path_matches",
    "patterns_of",
    "review_triggered",
    "score",
]

FEATURES: Final = (
    "public_cli",
    "schema",
    "security",
    "shared",
    "diff_size",
    "red_first",
    "deviation",
    "outside_write_set",
    "executor_recommended",
)
DEFAULT_WEIGHTS: Final[Mapping[str, int]] = {
    "public_cli": 25,
    "schema": 25,
    "security": 30,
    "shared": 15,
    "diff_size": 10,
    "red_first": 10,
    "deviation": 10,
    "outside_write_set": 15,
    "executor_recommended": 30,
}
DEFAULT_PATTERNS: Final[Mapping[str, tuple[str, ...]]] = {
    "public_cli": ("bin/**", "**/cli.py", "**/cli/**"),
    "schema": ("**/schemas/**", "**/migrations/**"),
    "security": (
        "**/auth/**",
        "**/security/**",
        "**/permissions*",
        "**/*secret*",
        "**/sandbox*",
        "**/hooks/**",
        ".github/workflows/**",
        "**/install.sh",
    ),
    "shared": (),
}
DEFAULT_DIFF_LINES: Final = 400
DEFAULT_CRITICAL: Final = ("security",)
DEFAULT_THRESHOLD: Final = 60
_CAP: Final = 100


def score(facts: RiskFacts, config: JsonObject) -> RiskScore:
    weights = {**DEFAULT_WEIGHTS, **_int_map(config.get("execution.review.risk.weights"))}
    diff_lines = _int(config.get("execution.review.risk.diff_lines"), DEFAULT_DIFF_LINES)
    critical = frozenset(_strings(config.get("execution.review.risk.critical"), DEFAULT_CRITICAL))
    patterns = config.get("execution.review.risk.patterns")
    evidence: dict[str, tuple[str, ...]] = {
        name: matching(facts.changed, patterns_of(patterns, name))
        for name in ("public_cli", "schema", "security", "shared")
    }
    evidence["diff_size"] = (f"{facts.diff_lines} lines",) if facts.diff_lines >= diff_lines else ()
    evidence["red_first"] = ("a required check was red in the first round",) if facts.red_first else ()
    evidence["deviation"] = ("the executor reported a deviation",) if facts.deviation else ()
    evidence["outside_write_set"] = tuple(sorted(set(facts.outside)))
    evidence["executor_recommended"] = ("the executor recommended a review",) if facts.recommended else ()
    features = tuple(
        RiskFeature(name, weights[name], evidence[name])
        for name in FEATURES
        if evidence[name] and weights[name] > 0
    )
    return RiskScore(
        score=min(_CAP, sum(feature.weight for feature in features)),
        features=features,
        critical=tuple(feature.name for feature in features if feature.name in critical),
    )


def review_triggered(risk: RiskScore, threshold: int) -> bool:
    """D2: the score reaches the threshold, or a critical feature is present."""
    return risk.score >= threshold or bool(risk.critical)


@dataclass(frozen=True, slots=True)
class RiskFacts:
    changed: tuple[str, ...]
    outside: tuple[str, ...]
    diff_lines: int
    red_first: bool
    deviation: bool
    recommended: bool


@dataclass(frozen=True, slots=True)
class RiskFeature:
    name: str
    weight: int
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskScore:
    score: int
    features: tuple[RiskFeature, ...]
    critical: tuple[str, ...]

    def has(self, name: str) -> bool:
        return any(feature.name == name for feature in self.features)


def patterns_of(patterns: JsonValue | None, name: str) -> tuple[str, ...]:
    """Path globs of one path feature from ``execution.review.risk.patterns``, or the default."""
    if isinstance(patterns, Mapping):
        found = cast("Mapping[str, JsonValue]", patterns).get(name)
        if isinstance(found, Sequence) and not isinstance(found, str):
            return tuple(str(item) for item in cast("Sequence[JsonValue]", found))
    return DEFAULT_PATTERNS.get(name, ())


def matching(paths: Iterable[str], patterns: Sequence[str]) -> tuple[str, ...]:
    """The sorted distinct paths that match at least one glob."""
    return tuple(sorted({path for path in paths if any(path_matches(path, glob) for glob in patterns)}))


def path_matches(path: str, pattern: str) -> bool:
    """Glob match of a repository-relative path: ``**`` spans segments, ``*`` and ``?`` stay in one."""
    return _compiled(pattern).fullmatch(path.strip().replace("\\", "/").removeprefix("./")) is not None


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern[str]:
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return re.compile("".join(out))


def _int_map(value: JsonValue | None) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in cast("Mapping[str, JsonValue]", value).items()
        if isinstance(item, int) and not isinstance(item, bool) and str(key) in DEFAULT_WEIGHTS
    }


def _int(value: JsonValue | None, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _strings(value: JsonValue | None, default: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(str(item) for item in cast("Sequence[JsonValue]", value))
    return tuple(default)
