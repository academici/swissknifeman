"""Append a note from the current assignment-token step binding."""

from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.execution.application._worker_dtos import RecordStepNote, RecordStepNoteResult
from skm.modules.execution.application._worker_protocol import lock_fenced_context, locked_stage, step_scope
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.step_note import NoteKind, StepNote, Urgency
from skm.modules.execution.ports import AssignmentRepository, StepRepository


def handle(cmd: RecordStepNote, ctx: Any, uow: UnitOfWork) -> RecordStepNoteResult:
    grant = ctx.actor.grant
    if grant is None or grant.kind != "assignment" or grant.step_id != UUID(cmd["step_id"]):
        raise error_for(ErrorCode.FORBIDDEN, "note requires the exact assignment-token step binding")
    from skm.modules.workspace import public as workspace

    worker = workspace.worker_for_principal(uow, ctx.actor.principal_id)
    if worker is None:
        raise error_for(ErrorCode.FORBIDDEN, "unregistered worker")
    assignment = uow.repo(AssignmentRepository).get(grant.assignment_id)
    lease = uow.repo(AssignmentRepository).lease(assignment.id)
    if lease is None:
        raise error_for(ErrorCode.LEASE_LOST, "assignment no longer has a lease")
    raw = {
        "assignment_id": str(assignment.id),
        "attempt_id": str(assignment.attempt_id),
        "worker_id": str(worker.worker_id),
        "fencing_token": lease.fencing_token,
    }
    fenced = lock_fenced_context(uow, ctx, raw, assignment_token=True)
    step = uow.repo(StepRepository).get(grant.step_id)
    stage = locked_stage(uow, fenced, step.stage_record_id)
    if (
        stage.state not in ACTIVE_STAGE_STATES
        or step.state is not StepState.STARTED
        or grant.scope_id != fenced.run.id
    ):
        raise error_for(ErrorCode.FORBIDDEN, "step note binding is terminal or outside the run")
    note = StepNote(
        ctx.ids.new_id(),
        step.id,
        NoteKind(cmd["kind"]),
        cmd["text"],
        tuple(cmd.get("options", ())),
        cmd.get("why_blocked"),
        Urgency(cmd.get("urgency", "normal")),
        fenced.now,
    )
    uow.repo(StepRepository).add_note(
        note,
        assignment_id=assignment.id,
        fencing_token=lease.fencing_token,
        created_by=ctx.actor.principal_id,
    )
    return RecordStepNoteResult(note_id=str(note.id), recorded_at=fenced.now.isoformat())


SPEC = CommandSpec(
    name="execution.record_step_note",
    dto=RecordStepNote,
    result=RecordStepNoteResult,
    permission="step.note",
    scope_of=None,
    scope_resolver=step_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
