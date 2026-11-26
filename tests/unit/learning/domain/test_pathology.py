"""Neutral pathology thresholds, missing telemetry and isolation."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skm.modules.learning.domain import pathology
from skm.modules.learning.domain.activity import (
    DEFAULT_SETTINGS,
    ActivitySummary,
    AgentUsage,
    ErrorLoop,
    Outcome,
    SourceKind,
)
from skm.modules.learning.domain.pathology import (
    PathologyCode,
    detect,
    detect_with_evidence,
    replay_pathology,
)

SUMMARY = ActivitySummary(
    SourceKind.ATTEMPT, "attempt-1", Outcome.UNKNOWN, datetime(2026, 11, 10, tzinfo=UTC)
)
MAIN = AgentUsage("main", 211, 0, 3)


@pytest.mark.parametrize(
    ("firing", "quiet", "code", "severity"),
    [
        (
            replace(SUMMARY, reads_total=10, reads_unique=5),
            replace(SUMMARY, reads_total=10, reads_unique=6),
            PathologyCode.FILE_REREAD,
            "attention",
        ),
        (
            replace(SUMMARY, error_loops=(ErrorLoop("shell", 3, ""),)),
            replace(SUMMARY, error_loops=(ErrorLoop("shell", 2, ""),)),
            PathologyCode.TOOL_ERROR_LOOP,
            "info",
        ),
        (
            replace(SUMMARY, tools_total=20, files_changed=(), checks=(), retrieval_calls=0),
            replace(SUMMARY, tools_total=19, files_changed=(), checks=(), retrieval_calls=0),
            PathologyCode.NO_OP_RUN,
            "info",
        ),
        (
            replace(SUMMARY, files_changed=("a",), checks=()),
            replace(SUMMARY, files_changed=("a",)),
            PathologyCode.NO_VERIFY,
            "attention",
        ),
        (
            replace(SUMMARY, cache_hit=0.39, usage_input=200_001, usage_cache_read=0, usage_cache_write=0),
            replace(SUMMARY, cache_hit=0.39, usage_input=200_000, usage_cache_read=0, usage_cache_write=0),
            PathologyCode.CACHE_MISS,
            "info",
        ),
        (
            replace(SUMMARY, usage_input=100, retrieval_result_chars=101, retrieval_repeated_queries=2),
            replace(SUMMARY, usage_input=100, retrieval_result_chars=100, retrieval_repeated_queries=2),
            PathologyCode.RETRIEVAL_STUFFING,
            "attention",
        ),
        (
            replace(SUMMARY, protected_writes=("project.md",)),
            replace(SUMMARY, protected_writes=()),
            PathologyCode.PROTECTED_WRITE,
            "attention",
        ),
        (
            replace(SUMMARY, agents=(MAIN,), context_window_tokens=100, tools_total=14),
            replace(SUMMARY, agents=(MAIN,), context_window_tokens=100, tools_total=15),
            PathologyCode.STATIC_CONTEXT,
            "info",
        ),
        (
            replace(SUMMARY, agents=(MAIN,) * 9, files_changed=("a",) * 4),
            replace(SUMMARY, agents=(MAIN,) * 9, files_changed=("a",) * 5),
            PathologyCode.FANOUT,
            "info",
        ),
    ],
)
def test_pathology_boundary(
    firing: ActivitySummary,
    quiet: ActivitySummary,
    code: PathologyCode,
    severity: str,
) -> None:
    result = detect_with_evidence(firing, DEFAULT_SETTINGS)
    finding = next(finding for finding in result.findings if finding.code is code)
    bundle = next(
        bundle for bundle in result.evidence if bundle.detector_version == f"pathology/{code.value}:v1"
    )
    assert finding.severity == severity
    assert replay_pathology(bundle).finding == finding
    assert code not in {finding.code for finding in detect(quiet, DEFAULT_SETTINGS)}


def test_missing_window_and_retrieval_stay_unknown() -> None:
    summary = replace(SUMMARY, agents=(MAIN,), tools_total=20, files_changed=(), checks=())
    result = detect_with_evidence(summary, DEFAULT_SETTINGS)
    assert not result.findings
    decisions = {bundle.detector_version: bundle for bundle in result.evidence}
    for code, field in (("static_context", "context_window_tokens"), ("no_op_run", "retrieval_calls")):
        bundle = decisions[f"pathology/{code}:v1"]
        assert bundle.decision == "unknown"
        assert bundle.coverage[field] == "missing"


def test_reread_hypothesis_describes_population_and_unknown_exclusions() -> None:
    result = detect_with_evidence(replace(SUMMARY, reads_total=12, reads_unique=5), DEFAULT_SETTINGS)
    bundle = next(
        bundle for bundle in result.evidence if bundle.detector_version == "pathology/file_reread:v1"
    )
    assert bundle.population["reads_total"] == 12
    assert bundle.population["reads_unique"] == 5
    assert bundle.exclusions == {"file_version": "unknown", "compaction": "unknown", "reviewer": "unknown"}
    assert len(bundle.alternative_explanations) == 4


def test_failed_pathology_does_not_break_other_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = dict(pathology._RULES)
    rule = rules[PathologyCode.FILE_REREAD]

    def fail(_summary: ActivitySummary) -> dict[str, None]:
        raise RuntimeError("secret internal error")

    monkeypatch.setitem(pathology._RULES, PathologyCode.FILE_REREAD, replace(rule, metrics=fail))
    result = detect_with_evidence(replace(SUMMARY, files_changed=("a",), checks=()), DEFAULT_SETTINGS)
    assert [finding.code for finding in result.findings] == [PathologyCode.NO_VERIFY]
    assert [(d.code, d.details["detector"]) for d in result.diagnostics] == [
        ("LEARNING_DETECTOR_FAILED", "file_reread"),
    ]
    assert "secret internal error" not in repr(result)
