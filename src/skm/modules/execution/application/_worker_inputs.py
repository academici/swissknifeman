"""Pinned planning and execution facts supplied to agent admission/context."""

from dataclasses import dataclass
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.context.public import ExecutionBlocks
from skm.modules.execution.application._worker_dtos import document
from skm.modules.execution.domain.finding import FindingState, logical_findings
from skm.modules.execution.domain.fix_brief import fix_brief_to_json
from skm.modules.execution.domain.work_policy import work_policy_to_json
from skm.modules.execution.ports import (
    AttemptRepository,
    DecisionRepository,
    EnvironmentRepository,
    OutputRepository,
    ReviewRepository,
    StageRepository,
    StepRepository,
)
from skm.modules.planning import public as planning


@dataclass(frozen=True)
class _FixBriefFacts:
    items: int
    unconfirmed: int
    finding_paths: tuple[str, ...]


@dataclass(frozen=True)
class _Answer:
    request_id: str
    question: str
    answer: Any
    answered_by_kind: str
    at: Any


@dataclass(frozen=True)
class _PreviousAttempt:
    attempt_no: int
    outcome: str
    reason_code: str
    changed_paths: tuple[str, ...]
    note: str
    patch_file_version_id: Any


@dataclass(frozen=True)
class _Candidate:
    output_id: Any
    manifest_digest: str
    diff_file_version_id: Any
    changed_paths: tuple[str, ...]
    base_commit: str
    head_commit: str


@dataclass(frozen=True)
class _History:
    step_ref: str
    role: str
    outcome: str
    summary: str


def task_route_and_contract(uow: UnitOfWork, fenced: Any, work_policy_digest: str) -> tuple[Any, str]:
    from skm.modules.execution.application._worker_dtos import digest

    if fenced.run.revision_id is None:
        return None, digest(
            {
                "inline_spec_file_version_id": str(fenced.run.inline_spec_file_version_id),
                "scope": document(fenced.task.declared_write_scope),
                "policy": work_policy_digest,
            }
        )
    spec = planning.get_revision_specification(uow, fenced.run.revision_id)
    graph = planning.compile_execution_graph(spec, fenced.run.revision_id)
    node = next((n for n in graph.tasks if n.entity_id == fenced.task.spec_entity_id), None)
    entity = next(
        (e for e in (*spec.items, *spec.units, *spec.phases) if e.id == fenced.task.spec_entity_id), None
    )
    check_ids: set[Any] = set() if node is None else {b.check_id for b in node.checks}
    checks = tuple(document(c) for c in spec.checks if c.id in check_ids)
    contract = digest(
        {
            "entity": str(fenced.task.spec_entity_id) if entity is None else document(entity),
            "checks": checks,
            "scope": document(fenced.task.declared_write_scope),
            "policy": work_policy_digest,
        }
    )
    return (None if node is None else node.route), contract


def task_route(uow: UnitOfWork, fenced: Any) -> Any:
    if fenced.run.revision_id is None:
        return None
    spec = planning.get_revision_specification(uow, fenced.run.revision_id)
    graph = planning.compile_execution_graph(spec, fenced.run.revision_id)
    return next((n.route for n in graph.tasks if n.entity_id == fenced.task.spec_entity_id), None)


def fix_brief(uow: UnitOfWork, fenced: Any, selected: Any) -> Any:
    identity = selected.feedback_refs.fix_brief_id
    if identity is None:
        return None
    brief = uow.repo(ReviewRepository).get_fix_brief(identity)
    if brief.task_id != fenced.task.id or brief.attempt_id != fenced.attempt.id:
        raise error_for(ErrorCode.INVALID_REFERENCE, "fix brief is outside the current attempt")
    return brief


def brief_facts(uow: UnitOfWork, fenced: Any, selected: Any) -> Any:
    brief = fix_brief(uow, fenced, selected)
    if brief is None:
        return None
    findings = task_findings(uow, fenced.task.id)
    paths = tuple(sorted({str(item.location["path"]) for item in brief.items}))
    # A red required check is confirmed feedback even when there are no review findings.
    return _FixBriefFacts(
        len(brief.items) + len(brief.checks), sum(f.state is FindingState.OPEN for f in findings), paths
    )


def task_findings(uow: UnitOfWork, task_id: Any) -> Any:
    repo = uow.repo(ReviewRepository)
    return logical_findings(
        repo.findings_for_task(task_id), {r.id: r.round_no for r in repo.for_task(task_id)}
    )


def previous_attempt(uow: UnitOfWork, fenced: Any) -> Any:
    attempts = uow.repo(AttemptRepository).list_for_task(fenced.task.id)
    older = [a for a in attempts if a.attempt_no < fenced.attempt.attempt_no]
    if not older:
        return None
    old = max(older, key=lambda a: a.attempt_no)
    output = uow.repo(OutputRepository).latest(old.id)
    paths = () if output is None else tuple(f"{p.mount}:{p.path}" for p in output.manifest.changed_paths)
    patch = None if output is None else output.manifest.patch_file_version_id
    env = uow.repo(EnvironmentRepository).for_attempt(old.id)
    if patch is None and env is not None:
        patch = next(
            (b.dirty_patch_file_version_id for b in env.baseline if b.dirty_patch_file_version_id), None
        )
    summaries = [
        f"{e.record.stage_id}: {e.record.state.value}"
        for e in uow.repo(StageRepository).history(old.id).entries
    ]
    return _PreviousAttempt(
        old.attempt_no,
        old.state.value,
        old.end_reason or "",
        paths,
        "; ".join(summaries) or f"Attempt {old.attempt_no}: {old.state.value}",
        patch,
    )


def execution_blocks(uow: UnitOfWork, fenced: Any, selected: Any, wp: Any) -> Any:
    feedback: dict[str, Any] = {}
    brief = fix_brief(uow, fenced, selected)
    if brief is not None:
        feedback["fix_brief"] = fix_brief_to_json(brief)
    if selected.feedback_refs.schema_errors_step_id is not None:
        old = uow.repo(StepRepository).get(selected.feedback_refs.schema_errors_step_id)
        if old.attempt_id != fenced.attempt.id:
            raise error_for(ErrorCode.INVALID_REFERENCE, "schema feedback belongs to another attempt")
        feedback["schema_errors"] = document(old.schema_errors)
    answers: list[_Answer] = []
    for identity in selected.feedback_refs.answer_request_ids:
        request = uow.repo(DecisionRepository).get(identity)
        if request.task_id != fenced.task.id or request.run_id != fenced.run.id:
            raise error_for(ErrorCode.INVALID_REFERENCE, "decision answer belongs to another task")
        answer = next(
            (a for a in uow.repo(DecisionRepository).answers_for(identity) if a.id == request.answer_id), None
        )
        if answer is None or request.state.value != "applied":
            raise error_for(ErrorCode.INVALID_TRANSITION, "decision feedback has no applied current answer")
        answers.append(
            _Answer(
                str(request.id),
                str(request.payload.get("text", "")),
                document(answer.value),
                str(answer.answered_by.get("kind", "owner")),
                answer.answered_at,
            )
        )
    output_id = selected.input_output_id or fenced.attempt.current_output_id
    candidate = None
    if output_id is not None:
        output = uow.repo(OutputRepository).get(output_id)
        if output.attempt_id != fenced.attempt.id:
            raise error_for(ErrorCode.INVALID_REFERENCE, "candidate belongs to another attempt")
        # Context's candidate block requires a diff artifact; sealed outputs may omit it.
        if output.manifest.patch_file_version_id is not None:
            mount = output.manifest.mounts[0]
            candidate = _Candidate(
                output.id,
                output.manifest_digest,
                output.manifest.patch_file_version_id,
                tuple(f"{p.mount}:{p.path}" for p in output.manifest.changed_paths),
                mount.base_commit,
                mount.head_commit,
            )
    findings = tuple(
        document(f) for f in task_findings(uow, fenced.task.id) if f.state is not FindingState.REJECTED
    )
    history: Any = tuple(
        _History(
            f"step:{s.id}",
            s.role.value,
            s.state.value,
            step_summary(s),
        )
        for e in uow.repo(StageRepository).history(fenced.attempt.id).entries
        for s in e.steps
        if s.finished_at is not None
    )
    return ExecutionBlocks(
        work_policy_to_json(wp),
        cast("Any", tuple(answers)),
        feedback or None,
        previous_attempt(uow, fenced),
        cast("Any", candidate),
        findings,
        None,
        (),
        history,
    )


def step_summary(step: Any) -> str:
    result: Any = step.result or {}
    return str(result.get("summary", step.error_code or step.state.value))
