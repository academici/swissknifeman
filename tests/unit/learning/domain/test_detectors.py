"""Ordered check observations, relapse and diagnostic replay."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.public import EvidenceRef
from skm.modules.learning.domain.activity import (
    DEFAULT_SETTINGS,
    ActivitySummary,
    CheckRun,
    Outcome,
    SourceKind,
    WorkflowRelaunch,
    canonical_json,
    detector_evidence_from_json,
    detector_evidence_json,
)
from skm.modules.learning.domain.check_commands import is_real_check
from skm.modules.learning.domain.detectors import (
    Detector,
    PathologyHistoryEntry,
    extract_observations,
    extract_with_evidence,
    replay_detector_evidence,
)
from skm.modules.learning.domain.evidence import DetectorEvidence
from skm.modules.learning.domain.pathology import PathologyCode

SUMMARY = ActivitySummary(
    SourceKind.ATTEMPT, "attempt-1", Outcome.FAILURE, datetime(2026, 11, 10, tzinfo=UTC)
)


@pytest.mark.parametrize(
    "command",
    [
        "vendor/bin/pest 2>&1 | tail -4",
        "cd x && npm test",
        "bash scripts/validate.sh",
        "pytest || exit 1",
        "printf '%s' tests/*_test.py | xargs pytest",
        "uv run --frozen pytest -q",
        "env LANG=C LC_ALL='C.UTF-8' uv run pytest",
        "php artisan test",
        "python -m unittest",
        "pnpm run lint",
        "cargo test",
        "pytest | grep FAILED",
    ],
)
def test_real_check_in_command_position(command: str) -> None:
    assert is_real_check(command)


@pytest.mark.parametrize("diagnostic", ["grep", "rg", "ag", "find", "ls", "cat", "which", "command -v"])
def test_diagnostic_first_segment_does_not_count(diagnostic: str) -> None:
    assert not is_real_check(f"{diagnostic} vitest")
    assert not is_real_check(f"{diagnostic} vitest && vitest")


def test_env_assignments_do_not_hide_diagnostic_first_segment() -> None:
    assert not is_real_check("env LC_ALL=C grep vitest && vitest")


def test_extra_runner_and_quoted_command_names() -> None:
    assert is_real_check("run-check --suite", (r"run-check\b",))
    assert not is_real_check("echo run-check", (r"run-check\b",))
    assert not is_real_check("echo 'ok; pytest'")
    assert not is_real_check("echo scripts/validate.sh")
    assert not is_real_check("echo ignored # ; pytest")
    assert not is_real_check("echo 'unclosed; pytest")
    assert not is_real_check("grep run-check", (r".*run-check",))


def test_resolved_failure_is_ordered_grouped_by_origin_and_counted_once() -> None:
    summary = replace(
        SUMMARY,
        checks=(
            CheckRun(None, False, "check_execution", "unit"),
            CheckRun("uv run pytest", False, "agent_shell", None),
            CheckRun("uv run pytest", False, "agent_shell", None),
            CheckRun(" uv run pytest\r\n", True, "agent_shell", None),
            CheckRun(None, True, "check_execution", "unit"),
            CheckRun("grep vitest", False, "agent_shell", None),
            CheckRun("grep vitest", True, "agent_shell", None),
            CheckRun("pytest other", True, "agent_shell", None),
            CheckRun("pytest other", False, "agent_shell", None),
        ),
    )
    result = extract_observations(summary, {}, DEFAULT_SETTINGS)
    assert [(obs.check_identity, obs.tests_total, obs.tests_passed) for obs in result] == [
        (("check_execution", "unit"), 2, 1),
        (("agent_shell", "uv run pytest"), 3, 1),
    ]
    assert all(obs.evidence_basis == "diagnostic_hypothesis" for obs in result)


def test_no_pair_across_sources_or_between_similar_checks() -> None:
    fail = CheckRun("pytest -k Billing", False, "agent_shell", None)
    passed = CheckRun("pytest -k billing", True, "agent_shell", None)
    same = replace(fail, ok=True)
    planned = CheckRun(None, True, "check_execution", "pytest -k Billing")
    for checks in ((fail,), (same,), (fail, passed), (fail, planned)):
        assert not extract_observations(replace(SUMMARY, checks=checks), {}, DEFAULT_SETTINGS)


def test_overlong_workarounds_are_excluded_without_collapsing_their_wording() -> None:
    prefix = "Inspect the settings. " * 50
    assert len(prefix) >= 1000
    allowed = "Check the logs. " * 62 + "Read it."
    assert len(allowed) == 1000
    summary = replace(SUMMARY, workarounds=(prefix + "Enable TLS.", prefix + "Disable TLS.", allowed))

    observations = extract_observations(summary, {}, DEFAULT_SETTINGS)

    assert [observation.action for observation in observations] == [allowed]


@pytest.mark.parametrize("length", [500, 501])
def test_resolved_failure_trigger_must_fit_in_full(length: int) -> None:
    prefix = "check failure was followed by a pass: "
    name = "x" * (length - len(prefix))
    checks = (CheckRun(None, False, "check_execution", name), CheckRun(None, True, "check_execution", name))

    observations = extract_observations(replace(SUMMARY, checks=checks), {}, DEFAULT_SETTINGS)

    assert [observation.trigger for observation in observations] == ([prefix + name] if length == 500 else [])


def _relapse_evidence(bundles: tuple[DetectorEvidence, ...]) -> DetectorEvidence:
    return next(bundle for bundle in bundles if bundle.detector_version == "pathology:v1")


def test_workaround_relapse_and_relaunch_replay_from_json() -> None:
    summary = replace(
        SUMMARY,
        source_kind=SourceKind.CLIENT_SESSION,
        reads_total=12,
        reads_unique=4,
        workarounds=("", "Pinned the version", "Pinned the version"),
        workflow_relaunches=(WorkflowRelaunch("scan", 2, {}), WorkflowRelaunch("verify", 3, {})),
    )
    code = PathologyCode.FILE_REREAD
    history = (
        PathologyHistoryEntry(EvidenceRef("attempt", "0"), (code,)),
        *(PathologyHistoryEntry(EvidenceRef("attempt", str(i)), ()) for i in range(1, 4)),
        PathologyHistoryEntry(EvidenceRef("client_session", summary.source_key), (code,)),
    )
    single_hit = extract_with_evidence(summary, history[1:], DEFAULT_SETTINGS)
    assert _relapse_evidence(single_hit.evidence).decision == "not_fired"
    extracted = extract_with_evidence(
        summary, history, DEFAULT_SETTINGS, source_refs=({"kind": "finding", "id": "f"},)
    )
    assert [obs.detector for obs in extracted.observations] == [
        Detector.WORKAROUND,
        Detector.PATHOLOGY,
        Detector.WORKFLOW_RELAUNCH,
    ]
    replayed = []
    for bundle in extracted.evidence:
        data = cast("JsonObject", json.loads(canonical_json(detector_evidence_json(bundle))))
        saved = detector_evidence_from_json(data)
        replay = replay_detector_evidence(saved)
        assert replay.decision == bundle.decision
        replayed.extend(replay.observations)
    assert tuple(replayed) == extracted.observations
    relapse = _relapse_evidence(extracted.evidence)
    assert [ref["id"] for ref in relapse.source_refs[-5:]] == ["0", "1", "2", "3", summary.source_key]
    assert relapse.relevant_metrics["history_membership"] == [[code], [], [], [], [code]]
    assert (
        replay_detector_evidence(replace(relapse, source_refs=relapse.source_refs[:-1])).decision == "unknown"
    )
    assert (
        replay_detector_evidence(replace(relapse, detector_version="pathology:v0")).decision
        == "version_unavailable"
    )


def test_count_only_relapse_history_has_unknown_coverage_even_above_threshold() -> None:
    summary = replace(SUMMARY, reads_total=12, reads_unique=4)
    result = extract_with_evidence(summary, {PathologyCode.FILE_REREAD: 2}, DEFAULT_SETTINGS)

    assert PathologyCode.FILE_REREAD in result.pathology_codes
    assert not result.observations
    relapse = _relapse_evidence(result.evidence)
    assert relapse.coverage["history_membership"] == "missing"
    assert relapse.decision == replay_detector_evidence(relapse).decision == "unknown"


@pytest.mark.parametrize("prior_hits", [1, 2])
def test_relapse_is_unknown_when_current_metrics_could_change_the_decision(prior_hits: int) -> None:
    code = PathologyCode.FILE_REREAD
    history = (
        *(PathologyHistoryEntry(EvidenceRef("attempt", f"prior-{i}"), (code,)) for i in range(prior_hits)),
        PathologyHistoryEntry(EvidenceRef("attempt", SUMMARY.source_key), ()),
    )

    result = extract_with_evidence(replace(SUMMARY, reads_total=12), history, DEFAULT_SETTINGS)

    assert not result.observations
    relapse = _relapse_evidence(result.evidence)
    assert relapse.coverage["current_pathology_metrics"] == "missing"
    assert relapse.decision == replay_detector_evidence(relapse).decision == "unknown"


def test_missing_check_metrics_and_detector_errors_are_reported() -> None:
    unknown = extract_with_evidence(SUMMARY, {}, DEFAULT_SETTINGS)
    empty = extract_with_evidence(replace(SUMMARY, checks=()), {}, DEFAULT_SETTINGS)

    def a_decision(result: tuple[DetectorEvidence, ...]) -> str:
        return next(bundle.decision for bundle in result if bundle.detector_version == "resolved_failure:v1")

    assert a_decision(unknown.evidence) == "unknown"
    assert a_decision(empty.evidence) == "not_fired"
    settings = replace(
        DEFAULT_SETTINGS, detectors=replace(DEFAULT_SETTINGS.detectors, extra_runner_patterns=("[",))
    )
    activity = replace(
        SUMMARY, checks=(CheckRun("my-check", True, "agent_shell", None),), workarounds=("Pinned",)
    )
    failed = extract_with_evidence(activity, {}, settings)
    assert a_decision(failed.evidence) == "error"
    assert [diagnostic.code for diagnostic in failed.diagnostics] == ["LEARNING_DETECTOR_FAILED"]
    assert [observation.detector for observation in failed.observations] == [Detector.WORKAROUND]
