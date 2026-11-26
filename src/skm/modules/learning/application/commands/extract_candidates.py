"""Extract and consolidate observations in the caller's transaction."""

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, ClassVar, Protocol, cast, override
from uuid import UUID

from skm.application_bus.context import CommandContext, SubscriberContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.events import DomainEvent
from skm.kernel.ids import AttemptId, ProjectId, RunId, ScopeId, TaskId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.knowledge.public import EvidenceRef, LessonKind
from skm.modules.learning.domain.activity import (
    ActivityRecord,
    ActivityRecordId,
    ActivitySummary,
    ConfidenceSettings,
    ConsolidationSettings,
    DetectorSettings,
    LearningSettings,
    Thresholds,
)
from skm.modules.learning.domain.candidate import (
    Candidate,
    CandidateId,
    CandidateState,
    ConfidenceTier,
    Signal,
    SignalId,
)
from skm.modules.learning.domain.consolidation import (
    ConsolidationAction,
    classify_consolidation,
    fingerprint,
    rule_identity,
    shortlist,
)
from skm.modules.learning.domain.detectors import (
    Detector,
    Observation,
    PathologyHistoryEntry,
    extract_with_evidence,
)
from skm.modules.learning.domain.events import CANDIDATE_STREAM_KIND, candidate_extracted_payload
from skm.modules.learning.domain.pathology import PathologyCode, detect
from skm.modules.learning.domain.recompute import recompute
from skm.modules.learning.domain.review import CandidateProposal, CandidateProposalId
from skm.modules.learning.generated.commands import ExtractCandidates
from skm.modules.learning.generated.results import ExtractCandidatesResult
from skm.modules.learning.generated.settings import LearningSettings as SettingsView
from skm.modules.learning.ports import (
    ActivityRecordRepository,
    CandidateProposalRepository,
    CandidateRepository,
    SignalRepository,
)
from skm.modules.workspace import public as workspace
from skm.platform.config import ConfigLoader, ConfigStore, PackConfigSource, ScopeTree
from skm.platform.config.effective import EffectiveConfig
from skm.platform.logging.redaction import Redactor

from .review_candidate import CandidateStateChanged

type ExtractionContext = CommandContext | SubscriberContext


@dataclass(frozen=True, slots=True)
class CandidateExtracted(DomainEvent):
    event_type: ClassVar[str] = "urn:skm:learning:event:candidate-extracted:v1"
    stream_kind: ClassVar[str] = CANDIDATE_STREAM_KIND
    candidate_id: CandidateId
    workspace_id: WorkspaceId
    project_id: ProjectId
    detector: Detector
    pathology_code: PathologyCode | None
    consolidation: ConsolidationAction
    conflicts_with_id: CandidateId | None

    @override
    def stream_id(self) -> UUID:
        return self.candidate_id

    @override
    def scope_workspace_id(self) -> WorkspaceId:
        return self.workspace_id

    @override
    def payload(self) -> JsonObject:
        return candidate_extracted_payload(
            self.candidate_id,
            self.project_id,
            self.detector,
            self.pathology_code,
            self.consolidation,
            self.conflicts_with_id,
        )


class ActivityStorage(ActivityRecordRepository, Protocol):
    """Storage reads that retain lineage in addition to the port's aggregate views."""

    def lock_project(self, project_id: ProjectId) -> None: ...
    def get(self, activity_id: ActivityRecordId) -> ActivityRecord: ...
    def by_source(self, workspace_id: WorkspaceId, source_key: str) -> ActivityRecordId | None: ...
    def history_entries(
        self, scope_id: ScopeId, *, window: int, observed_at: datetime, activity_id: ActivityRecordId
    ) -> tuple[ActivityRecord, ...]: ...
    def recent_for_project(self, project_id: ProjectId, *, window: int) -> tuple[ActivityRecord, ...]: ...


class CandidateStorage(CandidateRepository, Protocol):
    def next_display_key(self, project_id: ProjectId) -> str: ...
    def updated_at(self, candidate_id: CandidateId) -> datetime: ...


def project_ref(project_id: str) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(project_id)))


def settings_for(config: EffectiveConfig) -> LearningSettings:
    settings = config.section(SettingsView)
    detectors = asdict(settings.detectors)
    detectors["extra_runner_patterns"] = tuple(detectors["extra_runner_patterns"])
    return LearningSettings(
        detectors=DetectorSettings(**detectors),
        confidence=ConfidenceSettings(**asdict(settings.confidence)),
        thresholds=Thresholds(**asdict(settings.thresholds)),
        consolidation=ConsolidationSettings(**asdict(settings.consolidation)),
    )


def project_settings(uow: UnitOfWork, config: EffectiveConfig, project_id: ProjectId) -> LearningSettings:
    effective = ConfigLoader(config.registry, uow.repo(PackConfigSource)).effective(
        uow.repo(ConfigStore), uow.repo(ScopeTree), project_ref(str(project_id))
    )
    return settings_for(effective)


def _new_candidate(
    activity: ActivityRecord,
    obs: Observation,
    candidate_id: CandidateId,
    display_key: str,
    target_id: CandidateId | None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        workspace_id=activity.workspace_id,
        project_id=activity.project_id,
        scope_id=activity.scope_id,
        display_key=display_key,
        detector=obs.detector,
        pathology_code=obs.pathology_code,
        kind=LessonKind(obs.kind),
        trigger=obs.trigger,
        action=obs.action,
        review_hint=obs.review_hint,
        meta=obs.meta,
        evidence=tuple(EvidenceRef(e.kind, e.id) for e in obs.evidence),
        fingerprint=fingerprint(*rule_identity(obs)),
        state=CandidateState.OBSERVED,
        s_total=0,
        n_total=0,
        known_outcome_total=0,
        unknown_outcome_total=0,
        independent_known_total=0,
        independent_success_total=0,
        exposed_total=0,
        exposure_unknown_total=0,
        tests_total=0,
        tests_passed=0,
        days_since=0,
        support_score=0,
        freshness=0,
        stale=False,
        review_status="unreviewed",
        confidence=0,
        confidence_tier=ConfidenceTier.NONE,
        curated_ready=False,
        conflicts_with_id=target_id,
        proposed_update=None,
        lesson_id=None,
        recomputed_at=None,
        row_version=1,
    )


def _consolidate(
    activity: ActivityRecord,
    grouped: dict[str, list[Observation]],
    settings: LearningSettings,
    ctx: ExtractionContext,
    uow: UnitOfWork,
) -> ExtractCandidatesResult:
    candidates = cast("CandidateStorage", uow.repo(CandidateRepository))
    signals = uow.repo(SignalRepository)
    proposals = uow.repo(CandidateProposalRepository)
    project_sessions = signals.count_activities_for_project(activity.project_id)
    now = ctx.clock.now()
    created: list[str] = []
    signaled: list[str] = []
    for key, observations in grouped.items():
        obs = observations[0]
        exact = candidates.by_fingerprint(activity.scope_id, key)
        matches = ()
        if exact is None:
            refs = candidates.shortlist_pool(activity.scope_id, limit=2000)
            plausible = (
                ref
                for ref in refs
                if ref["trigger"] == obs.trigger
                or _text_similarity(obs, ref, settings.consolidation.shortlist_threshold)
            )
            matches = shortlist(
                obs,
                (candidates.get(CandidateId(UUID(str(ref["candidate_id"])))) for ref in plausible),
                threshold=settings.consolidation.shortlist_threshold,
            )
        decision = classify_consolidation(obs, matches, exact=exact, settings=settings.consolidation)
        if exact is None:
            candidate = _new_candidate(
                activity,
                obs,
                CandidateId(ctx.ids.new_id()),
                candidates.next_display_key(activity.project_id),
                decision.conflicts_with_id,
            )
            candidates.add(candidate)
            created.append(str(candidate.id))
            uow.record(
                CandidateExtracted(
                    candidate.id,
                    activity.workspace_id,
                    activity.project_id,
                    obs.detector,
                    obs.pathology_code,
                    decision.action,
                    decision.conflicts_with_id,
                )
            )
        else:
            candidate = exact
        if decision.conflicts_with_id is not None and decision.action in (
            ConsolidationAction.UPDATE,
            ConsolidationAction.CONFLICT,
        ):
            proposals.add(
                CandidateProposal(
                    CandidateProposalId(ctx.ids.new_id()),
                    activity.scope_id,
                    decision.conflicts_with_id,
                    candidate.id,
                    activity.id,
                    activity.source_key,
                    activity.observed_at,
                    now,
                    LessonKind(obs.kind),
                    obs.trigger,
                    obs.action,
                    key,
                    f"{obs.detector.value}:v1",
                    decision.action.value,
                )
            )
        signal = Signal.from_observations(
            id=SignalId(ctx.ids.new_id()),
            candidate_id=candidate.id,
            activity=activity,
            observations=tuple(observations),
        )
        if not signals.add(signal):
            continue
        signaled.append(str(candidate.id))
        current = replace(candidate, state=decision.state)
        if candidate.state != current.state:
            uow.record(
                CandidateStateChanged(
                    candidate.id, activity.workspace_id, candidate.state, current.state, "reobserved"
                )
            )
        refs = tuple(EvidenceRef(e.kind, e.id) for o in observations for e in o.evidence)
        current = replace(current, evidence=tuple(dict.fromkeys((*candidate.evidence, *refs)))[-50:])
        updated, transition = recompute(
            current,
            signals.for_candidate(candidate.id),
            now=now,
            project_sessions=project_sessions,
            t=settings,
        )
        candidates.save(updated, expected_version=candidate.row_version)
        if transition.reason is not None:
            uow.record(
                CandidateStateChanged(
                    candidate.id, activity.workspace_id, current.state, updated.state, transition.reason
                )
            )
    return ExtractCandidatesResult(activity_record_id=str(activity.id), created=created, signaled=signaled)


def _text_similarity(obs: Observation, ref: JsonObject, threshold: float) -> bool:
    from skm.modules.learning.domain.tokens import jaccard

    return jaccard(f"{obs.trigger} {obs.action}", f"{ref['trigger']} {ref['action']}") >= threshold


def extract(
    cmd: dict[str, Any],
    ctx: ExtractionContext,
    uow: UnitOfWork,
    *,
    config: EffectiveConfig,
    source_refs: tuple[JsonObject, ...] = (),
) -> ExtractCandidatesResult:
    scope = project_ref(cmd["project_id"])
    project_id = ProjectId(scope.id)
    workspace_id = workspace.workspace_of_project(uow, project_id)
    records = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
    records.lock_project(project_id)
    raw = cast("JsonObject", cmd["summary"])
    identity = {key: raw[key] for key in ("schema", "source_kind", "source_key", "outcome", "observed_at")}
    redactor = Redactor()
    source_key = cast("str", identity["source_key"])
    if redactor.text(source_key) != source_key:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Activity identity contains restricted text")
    summary = ActivitySummary.from_json(cast("JsonObject", redactor.document(raw)) | identity)
    if summary.observed_at.utcoffset() is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Activity observation requires a timezone")
    if (existing := records.by_source(workspace_id, summary.source_key)) is not None:
        if records.get(existing).project_id != project_id:
            raise NotFound(ErrorCode.NOT_FOUND, "Activity not found")
        return ExtractCandidatesResult(activity_record_id=str(existing), created=[], signaled=[])

    settings = settings_for(config)
    record_id = ActivityRecordId(ctx.ids.new_id())
    window = settings.detectors.pathology_window
    prior = records.history_entries(
        scope.id, window=window - 1, observed_at=summary.observed_at, activity_id=record_id
    )
    history = tuple(
        PathologyHistoryEntry(EvidenceRef(r.source_kind.value, r.source_key), r.pathology_codes)
        for r in reversed(prior)
    )
    current = PathologyHistoryEntry(
        EvidenceRef(summary.source_kind.value, summary.source_key),
        tuple(finding.code for finding in detect(summary, settings)),
    )
    extracted = extract_with_evidence(summary, (*history, current), settings, source_refs=source_refs)
    for diagnostic in extracted.diagnostics:
        ctx.log.warning("learning.detector_failed", code=diagnostic.code, details=diagnostic.details)
    evidence = extracted.evidence
    if metadata := summary.source_metadata():
        # Retain source metadata once, under the activity reference in the evidence bundle.
        first, *remaining = evidence
        primary, *lineage = first.source_refs
        evidence = (
            replace(first, source_refs=(primary | {"source_metadata": metadata}, *lineage)),
            *remaining,
        )
    record = ActivityRecord.from_summary(
        summary,
        id=record_id,
        workspace_id=workspace_id,
        project_id=project_id,
        scope_id=scope.id,
        pathology_codes=extracted.pathology_codes,
        detector_evidence=evidence,
        run_id=RunId(UUID(cmd["run_id"])) if "run_id" in cmd else None,
        task_id=TaskId(UUID(cmd["task_id"])) if "task_id" in cmd else None,
        attempt_id=AttemptId(UUID(cmd["attempt_id"])) if "attempt_id" in cmd else None,
    )
    if not records.add(record):
        existing = records.by_source(workspace_id, summary.source_key)
        if existing is None or records.get(existing).project_id != project_id:
            raise NotFound(ErrorCode.NOT_FOUND, "Activity not found")
        return ExtractCandidatesResult(activity_record_id=str(existing), created=[], signaled=[])
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in extracted.observations:
        key = fingerprint(*rule_identity(observation))
        if grouped[key] and rule_identity(grouped[key][0]) != rule_identity(observation):
            raise Conflict(ErrorCode.ID_CONFLICT, "Candidate fingerprint collision")
        grouped[key].append(observation)
    return _consolidate(record, grouped, settings, ctx, uow)


def handle(cmd: dict[str, Any], ctx: CommandContext, uow: UnitOfWork) -> ExtractCandidatesResult:
    return extract(cmd, ctx, uow, config=ctx.config)


SPEC = CommandSpec(
    name="learning.extract_candidates",
    dto=cast("type[dict[str, Any]]", ExtractCandidates),
    result=ExtractCandidatesResult,
    permission="system.internal",
    scope_of=lambda cmd: project_ref(cmd["project_id"]),
    handler=handle,
    internal=True,
    allowed_kinds=frozenset({PrincipalKind.SERVICE}),
    idempotency=IdempotencyMode.FORBIDDEN,
)
