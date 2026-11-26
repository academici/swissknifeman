"""Redacted activity inputs, evidence limits and pure learning settings."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, NewType, Self, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import AttemptId, ProjectId, RunId, ScopeId, TaskId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.learning.generated.documents import activity_summary_from_json

from .evidence import DetectorEvidence, ExposedLessonRef

if TYPE_CHECKING:
    from .pathology import PathologyCode

ActivityRecordId = NewType("ActivityRecordId", UUID)


class SourceKind(StrEnum):
    ATTEMPT = "attempt"
    CLIENT_SESSION = "client_session"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CheckRun:
    command: str | None
    ok: bool
    origin: Literal["agent_shell", "check_execution"]
    check_key: str | None


@dataclass(frozen=True, slots=True)
class ErrorLoop:
    tool: str
    length: int
    snippet: str


@dataclass(frozen=True, slots=True)
class RereadEntry:
    path: str
    count: int


@dataclass(frozen=True, slots=True)
class WorkflowRelaunch:
    name: str
    count: int
    statuses: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class AgentUsage:
    label: str
    input_tokens: int | None
    cache_read_tokens: int | None
    messages: int | None


@dataclass(frozen=True, slots=True)
class ActivitySummary:
    source_kind: SourceKind
    source_key: str
    outcome: Outcome
    observed_at: datetime
    task_outcome: Outcome | None = None
    exposure_coverage: ExposureCoverage = "unknown"
    exposed_lesson_refs: tuple[ExposedLessonRef, ...] | None = None
    tools_total: int | None = None
    reads_total: int | None = None
    reads_unique: int | None = None
    top_rereads: tuple[RereadEntry, ...] | None = None
    error_loops: tuple[ErrorLoop, ...] | None = None
    files_changed: tuple[str, ...] | None = None
    checks: tuple[CheckRun, ...] | None = None
    retrieval_calls: int | None = None
    retrieval_result_chars: int | None = None
    retrieval_repeated_queries: int | None = None
    usage_input: int | None = None
    usage_cache_read: int | None = None
    usage_cache_write: int | None = None
    cache_hit: float | None = None
    agents: tuple[AgentUsage, ...] | None = None
    context_window_tokens: int | None = None
    protected_writes: tuple[str, ...] | None = None
    workarounds: tuple[str, ...] | None = None
    workflow_relaunches: tuple[WorkflowRelaunch, ...] | None = None
    adapter_id: str | None = None
    adapter_version: str | None = None
    parser_version: str | None = None
    source_format: str | None = None
    metric_coverage: Mapping[str, MetricCoverage] | None = None

    def __post_init__(self) -> None:
        refs = self.exposed_lesson_refs
        if self.exposure_coverage == "complete" and (refs is None or len(refs) > MAX_EXPOSURE_REFS):
            object.__setattr__(self, "exposure_coverage", "unknown")

    @classmethod
    def from_json(cls, data: JsonObject) -> Self:
        """Decode a redacted summary. Source authority is established by the caller."""
        try:
            wire = cast("JsonObject", activity_summary_from_json(data))
        except (ValueError, TypeError) as exc:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid activity summary") from exc
        task_outcome = cast("str | None", wire.get("task_outcome"))
        return cls(
            source_kind=SourceKind(wire["source_kind"]),
            source_key=cast("str", wire["source_key"]),
            outcome=Outcome(wire["outcome"]),
            observed_at=datetime.fromisoformat(cast("str", wire["observed_at"])),
            task_outcome=Outcome(task_outcome) if task_outcome is not None else None,
            exposure_coverage=cast("ExposureCoverage", wire.get("exposure_coverage", "unknown")),
            exposed_lesson_refs=_read_array(
                wire.get("exposed_lesson_refs"),
                lambda item: ExposedLessonRef(
                    UUID(cast("str", item["id"])),
                    cast("str", item["version"]),
                    cast("str", item["content_digest"]),
                ),
            ),
            tools_total=cast("int | None", wire.get("tools_total")),
            reads_total=cast("int | None", wire.get("reads_total")),
            reads_unique=cast("int | None", wire.get("reads_unique")),
            top_rereads=_read_array(
                wire.get("top_rereads"),
                lambda item: RereadEntry(cast("str", item["path"]), cast("int", item["count"])),
            ),
            error_loops=_read_array(
                wire.get("error_loops"),
                lambda item: ErrorLoop(
                    cast("str", item["tool"]),
                    cast("int", item["length"]),
                    cast("str", item.get("snippet", "")),
                ),
            ),
            files_changed=_optional_tuple(wire.get("files_changed")),
            checks=_read_array(
                wire.get("checks"),
                lambda item: CheckRun(
                    cast("str | None", item["command"]),
                    cast("bool", item["ok"]),
                    cast("Literal['agent_shell', 'check_execution']", item["origin"]),
                    cast("str | None", item.get("check_key")),
                ),
            ),
            retrieval_calls=cast("int | None", wire.get("retrieval_calls")),
            retrieval_result_chars=cast("int | None", wire.get("retrieval_result_chars")),
            retrieval_repeated_queries=cast("int | None", wire.get("retrieval_repeated_queries")),
            usage_input=cast("int | None", wire.get("usage_input")),
            usage_cache_read=cast("int | None", wire.get("usage_cache_read")),
            usage_cache_write=cast("int | None", wire.get("usage_cache_write")),
            cache_hit=cast("float | None", wire.get("cache_hit")),
            agents=_read_array(
                wire.get("agents"),
                lambda item: AgentUsage(
                    cast("str", item["label"]),
                    cast("int | None", item["input_tokens"]),
                    cast("int | None", item["cache_read_tokens"]),
                    cast("int | None", item["messages"]),
                ),
            ),
            context_window_tokens=cast("int | None", wire.get("context_window_tokens")),
            protected_writes=_optional_tuple(wire.get("protected_writes")),
            workarounds=_optional_tuple(wire.get("workarounds")),
            workflow_relaunches=_read_array(
                wire.get("workflow_relaunches"),
                lambda item: WorkflowRelaunch(
                    cast("str", item["name"]),
                    cast("int", item["count"]),
                    cast("dict[str, int]", item["statuses"]),
                ),
            ),
            adapter_id=cast("str | None", wire.get("adapter_id")),
            adapter_version=cast("str | None", wire.get("adapter_version")),
            parser_version=cast("str | None", wire.get("parser_version")),
            source_format=cast("str | None", wire.get("source_format")),
            metric_coverage=cast("dict[str, MetricCoverage] | None", wire.get("metric_coverage")),
        )

    def source_metadata(self) -> JsonObject:
        data: JsonObject = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "parser_version": self.parser_version,
            "source_format": self.source_format,
            "metric_coverage": dict(self.metric_coverage) if self.metric_coverage is not None else None,
        }
        return {key: value for key, value in data.items() if value is not None}

    def to_json(self) -> JsonObject:
        data: JsonObject = {
            "schema": ACTIVITY_SCHEMA,
            "source_kind": self.source_kind.value,
            "source_key": self.source_key,
            "outcome": self.outcome.value,
            "observed_at": self.observed_at.isoformat(),
            "task_outcome": self.task_outcome.value if self.task_outcome is not None else None,
            "exposure_coverage": self.exposure_coverage,
            "tools_total": self.tools_total,
            "reads_total": self.reads_total,
            "reads_unique": self.reads_unique,
            "retrieval_calls": self.retrieval_calls,
            "retrieval_result_chars": self.retrieval_result_chars,
            "retrieval_repeated_queries": self.retrieval_repeated_queries,
            "usage_input": self.usage_input,
            "usage_cache_read": self.usage_cache_read,
            "usage_cache_write": self.usage_cache_write,
            "cache_hit": self.cache_hit,
            "context_window_tokens": self.context_window_tokens,
            **self.source_metadata(),
        }
        for key, items in (
            ("files_changed", self.files_changed),
            ("protected_writes", self.protected_writes),
            ("workarounds", self.workarounds),
        ):
            data[key] = list(items) if items is not None else None
        for key, records in (
            ("top_rereads", self.top_rereads),
            ("error_loops", self.error_loops),
            ("checks", self.checks),
            ("agents", self.agents),
        ):
            data[key] = (
                [cast("JsonObject", asdict(item)) for item in records] if records is not None else None
            )
        if self.exposed_lesson_refs is not None:
            data["exposed_lesson_refs"] = [
                {"id": str(ref.id), "version": ref.version, "content_digest": ref.content_digest}
                for ref in self.exposed_lesson_refs
            ]
        if self.workflow_relaunches is not None:
            data["workflow_relaunches"] = [
                {"name": item.name, "count": item.count, "statuses": dict(item.statuses)}
                for item in self.workflow_relaunches
            ]
        return {key: value for key, value in data.items() if value is not None}

    @property
    def summary_digest(self) -> str:
        return digest(self.to_json())


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    id: ActivityRecordId
    workspace_id: WorkspaceId
    project_id: ProjectId
    scope_id: ScopeId
    source_kind: SourceKind
    source_key: str
    run_id: RunId | None
    task_id: TaskId | None
    attempt_id: AttemptId | None
    outcome: Outcome
    observed_at: datetime
    pathology_codes: tuple[PathologyCode, ...]
    summary_digest: str
    task_outcome: Outcome | None
    exposure_coverage: Literal["complete", "unknown"]
    exposed_lesson_refs: tuple[ExposedLessonRef, ...]
    detector_evidence: tuple[DetectorEvidence, ...]

    def __post_init__(self) -> None:
        validate_detector_evidence(self.detector_evidence)

    @classmethod
    def from_summary(  # noqa: PLR0913
        cls,
        summary: ActivitySummary,
        *,
        id: ActivityRecordId,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        scope_id: ScopeId,
        pathology_codes: tuple[PathologyCode, ...],
        detector_evidence: tuple[DetectorEvidence, ...],
        run_id: RunId | None = None,
        task_id: TaskId | None = None,
        attempt_id: AttemptId | None = None,
    ) -> Self:
        return cls(
            id,
            workspace_id,
            project_id,
            scope_id,
            summary.source_kind,
            summary.source_key,
            run_id,
            task_id,
            attempt_id,
            summary.outcome,
            summary.observed_at,
            pathology_codes,
            summary.summary_digest,
            summary.task_outcome,
            summary.exposure_coverage,
            summary.exposed_lesson_refs or (),
            detector_evidence,
        )

    @property
    def evidence_dependency(self) -> EvidenceDependency:
        if self.exposure_coverage != "complete" or len(self.exposed_lesson_refs) > MAX_EXPOSURE_REFS:
            return "unknown"
        return "exposed" if self.exposed_lesson_refs else "independent"


ACTIVITY_SCHEMA = "urn:skm:learning:activity-summary:v1"
MAX_EXPOSURE_REFS = 2000
MAX_DETECTOR_EVIDENCE_BYTES = 65_536
type ExposureCoverage = Literal["complete", "unknown"]
type MetricCoverage = Literal["complete", "partial", "unknown"]
type EvidenceDependency = Literal["independent", "exposed", "unknown"]


def _optional_tuple(items: JsonValue) -> tuple[str, ...] | None:
    return tuple(cast("list[str]", items)) if items is not None else None


def _read_array[T](items: JsonValue, parse: Callable[[JsonObject], T]) -> tuple[T, ...] | None:
    return tuple(parse(item) for item in cast("list[JsonObject]", items)) if items is not None else None


def canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    ).encode("utf-8")


def digest(value: JsonValue) -> str:
    return "sha256:" + sha256(canonical_json(value)).hexdigest()


def detector_evidence_json(bundle: DetectorEvidence) -> JsonObject:
    return {
        "detector_version": bundle.detector_version,
        "input_schema_version": bundle.input_schema_version,
        "relevant_metrics": bundle.relevant_metrics,
        "thresholds": bundle.thresholds,
        "source_refs": list(bundle.source_refs),
        "coverage": bundle.coverage,
        "decision": bundle.decision,
        "severity": bundle.severity,
        "population": bundle.population,
        "exclusions": bundle.exclusions,
        "alternative_explanations": list(bundle.alternative_explanations),
        "suggested_investigation": bundle.suggested_investigation,
    }


def detector_evidence_from_json(data: JsonObject) -> DetectorEvidence:
    """Restore a schema-validated evidence object for diagnostic replay."""
    bundle = DetectorEvidence(
        detector_version=cast("str", data["detector_version"]),
        input_schema_version=cast("str", data["input_schema_version"]),
        relevant_metrics=cast("JsonObject", data["relevant_metrics"]),
        thresholds=cast("JsonObject", data["thresholds"]),
        source_refs=tuple(cast("list[JsonObject]", data["source_refs"])),
        coverage=cast("JsonObject", data["coverage"]),
        decision=cast("str", data["decision"]),
        severity=cast("str | None", data["severity"]),
        population=cast("JsonObject", data["population"]),
        exclusions=cast("JsonObject", data["exclusions"]),
        alternative_explanations=tuple(cast("list[str]", data["alternative_explanations"])),
        suggested_investigation=cast("str", data["suggested_investigation"]),
    )
    validate_detector_evidence((bundle,))
    return bundle


def validate_detector_evidence(evidence: tuple[DetectorEvidence, ...]) -> None:
    try:
        size = len(canonical_json([detector_evidence_json(bundle) for bundle in evidence]))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Detector evidence must be JSON") from exc
    if size > MAX_DETECTOR_EVIDENCE_BYTES:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "Detector evidence exceeds the byte limit",
            details={"max_bytes": MAX_DETECTOR_EVIDENCE_BYTES, "size_bytes": size},
        )


@dataclass(frozen=True, slots=True)
class DetectorSettings:
    pathology_window: int = 5
    pathology_min_hits: int = 2
    similar_command: float = 0.6
    workflow_relaunch_min: int = 3
    reread_min_total: int = 10
    reread_ratio_max: float = 0.4
    error_loop_info_len: int = 3
    error_loop_attention_len: int = 5
    noop_min_tools: int = 20
    cache_hit_low: float = 0.4
    cache_miss_min_tokens: int = 200_000
    retrieval_in_share: float = 0.25
    retrieval_repeated_min: int = 2
    chars_per_token: float = 4.0
    static_min_msgs: int = 3
    static_window_share: float = 0.7
    static_max_tools: int = 15
    fanout_min_agents: int = 8
    fanout_max_files: int = 5
    extra_runner_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.pathology_min_hits <= self.pathology_window:
            raise ValueError("Pathology hits must fit within the activity window")


@dataclass(frozen=True, slots=True)
class ConfidenceSettings:
    alpha: float = 1.0
    beta: float = 1.0
    volume_k: float = 20.0
    decay_lambda: float = 0.95


@dataclass(frozen=True, slots=True)
class Thresholds:
    candidate_min_n: int = 15
    candidate_min_n_floor: int = 3
    candidate_min_conf: float = 0.6
    curated_min_n: int = 50
    curated_min_conf: float = 0.8
    curated_min_passrate: float = 0.95
    deprecate_conf: float = 0.4

    def __post_init__(self) -> None:
        if not 0 <= self.deprecate_conf < self.candidate_min_conf <= self.curated_min_conf <= 1:
            raise ValueError("Support thresholds must preserve exit < entry <= curation")
        if not 1 <= self.candidate_min_n_floor <= self.candidate_min_n <= self.curated_min_n:
            raise ValueError("Count thresholds must preserve floor <= entry <= curation")


@dataclass(frozen=True, slots=True)
class ConsolidationSettings:
    shortlist_threshold: float = 0.4
    trigger_high: float = 0.6
    action_high: float = 0.6
    action_low: float = 0.2


@dataclass(frozen=True, slots=True)
class LearningSettings:
    detectors: DetectorSettings = DetectorSettings()
    confidence: ConfidenceSettings = ConfidenceSettings()
    thresholds: Thresholds = Thresholds()
    consolidation: ConsolidationSettings = ConsolidationSettings()


DEFAULT_SETTINGS = LearningSettings()
