"""Diagnostic observations and replay from saved metrics and thresholds."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic
from skm.modules.knowledge.public import EvidenceRef, LessonKind

from .activity import (
    ACTIVITY_SCHEMA,
    ActivitySummary,
    CheckRun,
    LearningSettings,
    SourceKind,
    validate_detector_evidence,
)
from .check_commands import is_real_check
from .evidence import DetectorEvidence
from .pathology import (
    Decision,
    PathologyCode,
    PathologyFinding,
    detect_with_evidence,
    detector_failed,
    replay_pathology,
)
from .remediations import REMEDIATIONS
from .tokens import norm


class Detector(StrEnum):
    RESOLVED_FAILURE = "resolved_failure"
    WORKAROUND = "workaround"
    PATHOLOGY = "pathology"
    WORKFLOW_RELAUNCH = "workflow_relaunch"


@dataclass(frozen=True, slots=True)
class ActivityEvidenceRef:
    kind: str
    id: str


@dataclass(frozen=True, slots=True)
class Observation:
    detector: Detector
    pathology_code: PathologyCode | None
    kind: LessonKind | Literal["gotcha"]
    trigger: str
    action: str
    evidence: tuple[ActivityEvidenceRef | EvidenceRef, ...]
    tests_total: int
    tests_passed: int
    meta: Mapping[str, JsonValue]
    review_hint: str | None
    evidence_basis: Literal["diagnostic_hypothesis"]
    check_identity: CheckIdentity | None = None


type CheckIdentity = tuple[Literal["agent_shell", "check_execution"], str]
type PathologyHistory = Mapping[PathologyCode, int]


@dataclass(frozen=True, slots=True)
class PathologyHistoryEntry:
    source_ref: EvidenceRef
    codes: tuple[PathologyCode, ...]


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    observations: tuple[Observation, ...]
    pathology_codes: tuple[PathologyCode, ...]
    evidence: tuple[DetectorEvidence, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class DetectorReplay:
    decision: Decision | Literal["version_unavailable"]
    observations: tuple[Observation, ...] = ()
    finding: PathologyFinding | None = None


_REVIEW_HINT = "Verify the cause, applicability, and exceptions before promoting."


def _observation(
    detector: Detector,
    trigger: str,
    action: str,
    refs: tuple[ActivityEvidenceRef, ...],
    *,
    code: PathologyCode | None = None,
    meta: JsonObject | None = None,
    check_identity: CheckIdentity | None = None,
    counts: tuple[int, int] = (0, 0),
) -> Observation:
    return Observation(
        detector,
        code,
        "gotcha",
        trigger,
        action,
        refs,
        *counts,
        meta if meta is not None else {},
        _REVIEW_HINT,
        "diagnostic_hypothesis",
        check_identity,
    )


def _check_metrics(checks: tuple[CheckRun, ...] | None) -> list[JsonValue] | None:
    if checks is None:
        return None
    return [
        {
            "origin": check.origin,
            "name": check.check_key if check.origin == "check_execution" else check.command,
            "ok": check.ok,
        }
        for check in checks
    ]


@dataclass(slots=True)
class _CheckCounts:
    total: int = 0
    passed: int = 0
    resolved: bool = False

    def add(self, ok: bool) -> None:
        self.resolved |= ok and self.total > self.passed
        self.total += 1
        self.passed += int(ok)


def _resolved_failures(
    metrics: JsonObject,
    thresholds: JsonObject,
    refs: tuple[ActivityEvidenceRef, ...],
) -> tuple[Observation, ...]:
    counts: dict[CheckIdentity, _CheckCounts] = {}
    patterns = tuple(cast("list[str]", thresholds["extra_runner_patterns"]))
    for check in cast("list[JsonObject]", metrics["checks"]):
        origin = cast("Literal['agent_shell', 'check_execution']", check["origin"])
        name = cast("str | None", check["name"])
        if not name or not name.strip():
            continue
        if origin == "agent_shell":
            name = norm(name)
            if not is_real_check(name, patterns):
                continue
        counts.setdefault((origin, name), _CheckCounts()).add(cast("bool", check["ok"]))
    return tuple(
        _observation(
            Detector.RESOLVED_FAILURE,
            f"check failure was followed by a pass: {identity[1]}",
            "investigate which change preceded the passing check and verify its applicability: "
            f"{identity[1]}",
            refs,
            check_identity=identity,
            counts=(count.total, count.passed),
        )
        for identity, count in counts.items()
        if count.resolved
    )


def _workarounds(
    metrics: JsonObject,
    _thresholds: JsonObject,
    refs: tuple[ActivityEvidenceRef, ...],
) -> tuple[Observation, ...]:
    texts = dict.fromkeys(text.strip() for text in cast("list[str]", metrics["workarounds"]) if text.strip())
    return tuple(
        _observation(Detector.WORKAROUND, f"the situation required a workaround: {text[:60]}", text, refs)
        for text in texts
    )


def _relapse(
    metrics: JsonObject,
    thresholds: JsonObject,
    refs: tuple[ActivityEvidenceRef, ...],
    source_refs: tuple[JsonObject, ...],
) -> tuple[Observation, ...] | None:
    window = cast("int", thresholds["pathology_window"])
    minimum = cast("int", thresholds["pathology_min_hits"])
    membership = metrics.get("history_membership")
    offset = metrics.get("history_source_offset")
    unknown_codes = metrics.get("current_unknown_codes")
    if (
        not isinstance(membership, list)
        or not isinstance(unknown_codes, list)
        or not all(isinstance(code, str) for code in unknown_codes)
        or type(offset) is not int
        or offset < 1
        or len(source_refs) - offset != len(membership)
        or len(membership) > window
    ):
        return None
    seen: set[tuple[str, str]] = set()
    hits: Counter[str] = Counter()
    for codes, ref in zip(membership, source_refs[offset:], strict=True):
        if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
            return None
        kind, ref_id = ref.get("kind"), ref.get("id")
        if not isinstance(kind, str) or not kind or not isinstance(ref_id, str) or not ref_id:
            return None
        if (kind, ref_id) in seen:
            return None
        seen.add((kind, ref_id))
        hits.update(set(cast("list[str]", codes)))

    result: list[Observation] = []
    for raw_code in cast("list[str]", metrics["pathology_codes"]):
        code = PathologyCode(raw_code)
        count = hits[code.value]
        if code in REMEDIATIONS and count >= minimum:
            result.append(
                _observation(
                    Detector.PATHOLOGY,
                    f"recurring diagnostic pattern: {code.value}",
                    REMEDIATIONS[code],
                    refs,
                    code=code,
                    meta={"hits": count, "window": window},
                )
            )
    # The newest history entry is the current activity. Unknown metrics may hide its hit.
    if (
        not result
        and membership
        and any(
            hits[code] + int(code not in cast("list[str]", membership[-1])) >= minimum
            for code in cast("list[str]", unknown_codes)
        )
    ):
        return None
    return tuple(result)


def _relaunch(
    metrics: JsonObject,
    thresholds: JsonObject,
    refs: tuple[ActivityEvidenceRef, ...],
) -> tuple[Observation, ...]:
    minimum = cast("int", thresholds["workflow_relaunch_min"])
    return tuple(
        _observation(
            Detector.WORKFLOW_RELAUNCH,
            f'workflow "{entry["name"]}" restarted {entry["count"]} times in one session',
            "stabilize the workflow script in an isolated dev loop before fan-out; "
            "do not debug it inside the main interactive session",
            refs,
            meta={"count": entry["count"]},
        )
        for entry in cast("list[JsonObject]", metrics["workflow_relaunches"])
        if cast("int", entry["count"]) >= minimum
    )


_EVALUATORS = {
    Detector.RESOLVED_FAILURE: _resolved_failures,
    Detector.WORKAROUND: _workarounds,
    Detector.WORKFLOW_RELAUNCH: _relaunch,
}
_ALTERNATIVES = {
    Detector.RESOLVED_FAILURE: ("A change fixed the failure", "The check or environment was intermittent"),
    Detector.WORKAROUND: ("The constraint was local to this activity",),
    Detector.PATHOLOGY: ("The activities shared a constraint or prior finding",),
    Detector.WORKFLOW_RELAUNCH: ("Restarts were intentional", "An external dependency was unstable"),
}


def _evaluate(
    detector: Detector,
    metrics: JsonObject,
    thresholds: JsonObject,
    source_refs: tuple[JsonObject, ...],
) -> DetectorReplay:
    if not source_refs or any(value is None for value in metrics.values()):
        return DetectorReplay("unknown")
    # Lesson provenance names the observed activity. Additional lineage remains diagnostic evidence.
    primary = source_refs[0]
    refs = (ActivityEvidenceRef(cast("str", primary["kind"]), cast("str", primary["id"])),)
    observations = (
        _relapse(metrics, thresholds, refs, source_refs)
        if detector is Detector.PATHOLOGY
        else _EVALUATORS[detector](metrics, thresholds, refs)
    )
    if observations is None:
        return DetectorReplay("unknown")
    bounded = tuple(
        obs for obs in observations if 1 <= len(obs.trigger) <= 500 and 1 <= len(obs.action) <= 1000
    )
    return DetectorReplay("fired" if bounded else "not_fired", bounded)


def extract_with_evidence(
    summary: ActivitySummary,
    history: PathologyHistory | tuple[PathologyHistoryEntry, ...],
    t: LearningSettings,
    *,
    source_refs: tuple[JsonObject, ...] = (),
) -> ExtractionResult:
    """Extract from redacted inputs and a scope history that already includes this activity.

    Ordered history entries are oldest first. A count-only history supports the repository's aggregate read
    and leaves source membership unknown in the diagnostic bundle.
    """
    pathologies = detect_with_evidence(summary, t, source_refs=source_refs)
    codes = tuple(finding.code for finding in pathologies.findings)
    settings = t.detectors
    refs: tuple[JsonObject, ...] = (
        {"kind": summary.source_kind.value, "id": summary.source_key},
        *source_refs,
    )
    history_refs: tuple[JsonObject, ...] = ()
    history_metrics: JsonObject
    if isinstance(history, tuple):
        recent = history[-settings.pathology_window :]
        history_refs = tuple({"kind": entry.source_ref.kind, "id": entry.source_ref.id} for entry in recent)
        history_metrics = {
            "history_membership": [list(entry.codes) for entry in recent],
            # Membership is aligned with the history suffix, after the primary and lineage refs.
            "history_source_offset": len(refs),
        }
    else:
        history_metrics = {
            "history_membership": None,
            "history_hits": {code.value: count for code, count in history.items()},
        }
    undetermined = {
        bundle.detector_version for bundle in pathologies.evidence if bundle.decision in ("unknown", "error")
    }
    unknown_codes = [code for code in REMEDIATIONS if f"pathology/{code.value}:v1" in undetermined]
    relaunches = summary.workflow_relaunches
    if summary.source_kind is SourceKind.ATTEMPT:
        relaunches = ()
    inputs: dict[Detector, tuple[JsonObject, JsonObject]] = {
        Detector.RESOLVED_FAILURE: (
            {"checks": _check_metrics(summary.checks)},
            {"extra_runner_patterns": list(settings.extra_runner_patterns)},
        ),
        Detector.WORKAROUND: (
            {"workarounds": list(summary.workarounds) if summary.workarounds is not None else None},
            {},
        ),
        Detector.PATHOLOGY: (
            {"pathology_codes": list(codes), "current_unknown_codes": list(unknown_codes), **history_metrics},
            {
                "pathology_window": settings.pathology_window,
                "pathology_min_hits": settings.pathology_min_hits,
            },
        ),
        Detector.WORKFLOW_RELAUNCH: (
            {
                "workflow_relaunches": [{"name": r.name, "count": r.count} for r in relaunches]
                if relaunches is not None
                else None
            },
            {"workflow_relaunch_min": settings.workflow_relaunch_min},
        ),
    }
    observations: list[Observation] = []
    evidence = list(pathologies.evidence)
    diagnostics = list(pathologies.diagnostics)
    for detector, (metrics, thresholds) in inputs.items():
        detector_refs = (*refs, *history_refs) if detector is Detector.PATHOLOGY else refs
        try:
            result = _evaluate(detector, metrics, thresholds, detector_refs)
        except Exception:  # noqa: BLE001 - isolate detector failures
            diagnostics.append(detector_failed(detector.value))
            result = DetectorReplay("error")
        observations.extend(result.observations)
        coverage: JsonObject = {
            key: "missing" if value is None else "present" for key, value in metrics.items()
        }
        coverage["exposure_coverage"] = summary.exposure_coverage
        if detector is Detector.PATHOLOGY:
            coverage["current_pathology_metrics"] = "missing" if unknown_codes else "present"
        evidence.append(
            DetectorEvidence(
                detector_version=f"{detector.value}:v1",
                input_schema_version=ACTIVITY_SCHEMA,
                relevant_metrics=metrics,
                thresholds=thresholds,
                source_refs=detector_refs,
                coverage=coverage,
                decision=result.decision,
                severity=None,
                population={"activity_count": 1},
                exclusions={"status": "unknown"},
                alternative_explanations=_ALTERNATIVES[detector],
                suggested_investigation=_REVIEW_HINT,
            )
        )
    bundles = tuple(evidence)
    validate_detector_evidence(bundles)
    return ExtractionResult(tuple(observations), codes, bundles, tuple(diagnostics))


def extract_observations(
    summary: ActivitySummary,
    history: PathologyHistory | tuple[PathologyHistoryEntry, ...],
    t: LearningSettings,
) -> tuple[Observation, ...]:
    return extract_with_evidence(summary, history, t).observations


def replay_detector_evidence(bundle: DetectorEvidence) -> DetectorReplay:
    if bundle.input_schema_version != ACTIVITY_SCHEMA:
        return DetectorReplay("version_unavailable")
    for detector in Detector:
        if bundle.detector_version == f"{detector.value}:v1":
            if bundle.decision == "error":
                return DetectorReplay("error")
            return _evaluate(detector, bundle.relevant_metrics, bundle.thresholds, bundle.source_refs)
    pathology = replay_pathology(bundle)
    return DetectorReplay(pathology.decision, finding=pathology.finding)
