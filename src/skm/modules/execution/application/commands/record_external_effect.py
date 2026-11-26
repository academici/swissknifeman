"""Fenced local admissions and exact one-use policy intents in the execution transaction."""

from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RepositoryId, ToolIntentId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId
from skm.modules.execution.application._admission import require_run_admission
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._integration_inputs import accepted_inputs
from skm.modules.execution.application._primitives import attempt_effect_ids, server_context
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_dtos import WireRecord, digest, document
from skm.modules.execution.application._worker_protocol import (
    fenced_scope,
    lock_fenced_context,
    locked_stage,
    verify_current_lease,
)
from skm.modules.execution.domain.external_effect import (
    EffectKind,
    EffectState,
    ExternalEffect,
    validate_observation,
)
from skm.modules.execution.domain.ids import ExternalEffectId
from skm.modules.execution.ports import (
    EffectRepository,
    IntegrationSlotRepository,
    RunRepository,
    StageRepository,
)
from skm.modules.policy.public import EffectKind as PolicyEffectKind
from skm.modules.policy.public import effective_permissions, propose_intent, record_outcome, require_approved
from skm.modules.workspace import public as workspace


class RecordExternalEffect(WireRecord):
    SCHEMA_URN = "urn:skm:execution:command:record-external-effect:v1"


class RecordExternalEffectResult(WireRecord):
    SCHEMA_URN = "urn:skm:execution:result:record-external-effect:v1"


def _guard(uow: UnitOfWork, fenced: Any, stage: Any, identity: Any, request: Any) -> Any:
    output, _, decision = accepted_inputs(uow, fenced)
    metadata: dict[str, Any] = stage.outcome or {}
    inputs: dict[str, Any] = metadata.get("integration_inputs", {})
    targets = [t for t in inputs.get("integration_targets", ()) if t["effect_id"] == str(identity)]
    if len(targets) != 1 or inputs.get("acceptance_decision_id") != str(decision.id):
        raise error_for(ErrorCode.INVALID_REFERENCE, "effect was not selected by Begin integration")
    target = targets[0]
    if (
        str(output.id) != inputs["accepted_output_id"]
        or any(request[k] != target[k] for k in ("repository_id", "target_branch", "baseline_sha"))
        or request["output_ids"] != [o["output_id"] for o in target["outputs"]]
        or request["output_digests"] != [o["output_digest"] for o in target["outputs"]]
        or request["assignment_fencing_token"] != fenced.claim.fencing_token
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "effect request differs from accepted inputs")
    slots = uow.repo(IntegrationSlotRepository)
    slot = slots.current(
        RepositoryId(UUID(request["repository_id"])), request["target_branch"], for_update=True
    )
    now = uow.repo(RunRepository).now()
    verify_current_lease(uow, fenced.assignment, fenced.lease, fenced.claim, now)
    fenced.now = now
    if (
        slot is None
        or slot.holder_attempt_id != fenced.attempt.id
        or slot.fencing_token != request["slot_fencing_token"]
        or slot.expires_at is None
        or slot.expires_at <= now
    ):
        raise error_for(ErrorCode.LEASE_LOST, "integration slot changed or expired")
    if (
        slot.writer_host_id != fenced.worker.host_id
        or slots.hosts_for_run(fenced.run.id).get(slot.repository_id) != fenced.worker.host_id
    ):
        raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "writer host pin changed")
    return slot


def _receipt(effect: Any, value: Any) -> None:
    if not isinstance(value, dict):
        raise error_for(ErrorCode.INVALID_REFERENCE, "Git receipt is missing")
    value = cast("dict[str, Any]", value)
    request = effect.request
    fields = (
        "before_sha",
        "after_sha",
        "tree_sha",
        "target_branch",
        "output_ids",
        "commit_shas",
        "writer_epoch_sha",
    )
    if (
        any(value.get(k) != request[k] for k in fields)
        or value.get("request_digest") != effect.request_digest
        or value.get("ref") != request["after_sha"]
        or value.get("receipt_ref") != "refs/skm/effects/" + str(effect.id)
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "Git receipt differs from the immutable request")


def handle(cmd: RecordExternalEffect, ctx: Any, uow: UnitOfWork) -> RecordExternalEffectResult:
    ctx = server_context(ctx, uow)
    if cmd["kind"] != "git_commit":
        return record_intent_effect(cmd, ctx, uow)
    fenced = lock_fenced_context(uow, ctx, cmd["claim"])
    stage = uow.repo(StageRepository).started_without_result(fenced.attempt.id)
    if stage is None or stage.stage_type != "integrate" or fenced.run.status.value != "running":
        raise error_for(ErrorCode.INVALID_TRANSITION, "local effects require an active integrate stage")
    stage = locked_stage(uow, fenced, stage.id)
    repo = uow.repo(EffectRepository)
    identity = ExternalEffectId(UUID(cmd["effect_id"]))
    phase = cmd["phase"]
    if phase == "intended":
        request = cmd["request"]
        if (
            digest({"effect_id": str(identity), "kind": "git_commit", "request": request})
            != cmd["request_digest"]
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "effect request digest differs")
        _guard(uow, fenced, stage, identity, request)
        from skm.kernel.errors import NotFound

        try:
            effect = repo.get(identity, for_update=True)
        except NotFound:
            effect = ExternalEffect(
                identity,
                fenced.run.workspace_id,
                fenced.run.id,
                fenced.attempt.id,
                fenced.task.id,
                EffectKind.GIT_COMMIT,
                None,
                cmd["request_digest"],
                request,
                EffectState.INTENDED,
                None,
                fenced.now,
                fenced.now,
            )
            repo.add(effect)
    else:
        effect = repo.get(identity, for_update=True)
    if (
        effect.kind is not EffectKind.GIT_COMMIT
        or effect.intent_id is not None
        or effect.attempt_id != fenced.attempt.id
        or effect.request_digest != cmd["request_digest"]
        or (cmd.get("request") is not None and effect.request != cmd["request"])
    ):
        raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "effect identity or immutable request changed")
    admission = None
    if phase == "executing":
        _, values = effective_values(uow, fenced.run.id)
        require_run_admission(uow, ctx, fenced.run, values)
        slot = _guard(uow, fenced, stage, identity, effect.request)
        if effect.state not in {EffectState.INTENDED, EffectState.EXECUTING}:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "effect requires reconciliation before further IO")
        effect = replace(effect, state=EffectState.EXECUTING, updated_at=fenced.now)
        repo.save(effect)
        admission = {
            "admission_id": str(ctx.ids.new_id()),
            "effect_id": str(identity),
            "request_digest": effect.request_digest,
            "slot_fencing_token": slot.fencing_token,
            "server_now": fenced.now.isoformat(),
            "admit_until": min(
                fenced.lease.expires_at, slot.expires_at, fenced.now + timedelta(seconds=5)
            ).isoformat(),
        }
    elif phase == "result":
        if effect.state not in {EffectState.EXECUTING, EffectState.SUCCEEDED}:
            raise error_for(ErrorCode.INVALID_TRANSITION, "effect result requires prior admission")
        result = cmd["result"]
        receipt = result.get("git_receipt")
        if result["succeeded"]:
            _receipt(effect, receipt)
        else:
            receipt = {
                "ref": result.get("ref"),
                "response_digest": result.get("response_digest"),
                "at": fenced.now.isoformat(),
            }
            validate_observation(effect, EffectState.FAILED, receipt, result.get("error"))
        if effect.state is EffectState.SUCCEEDED and effect.receipt != receipt:
            raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "effect receipt changed")
        effect = replace(
            effect,
            state=EffectState.SUCCEEDED if result["succeeded"] else EffectState.FAILED,
            receipt=document(receipt),
            updated_at=fenced.now,
        )
        repo.save(effect)
    emit(
        uow,
        fenced.run,
        "external-effect-recorded",
        {
            "effect_id": str(identity),
            "kind": "git_commit",
            "state": effect.state.value,
            "attempt_id": str(fenced.attempt.id),
            "output_ids": effect.request["output_ids"],
            "request_digest": effect.request_digest,
        },
        cause("stage_outcome", refs=[{"kind": "stage", "id": str(stage.id)}]),
    )
    return RecordExternalEffectResult(effect_id=str(identity), state=effect.state.value, admission=admission)


def attempt_effects(uow: UnitOfWork, attempt_id: Any) -> list[Any]:
    return [uow.repo(EffectRepository).get(effect_id) for effect_id in attempt_effect_ids(uow, attempt_id)]


def validate_target(uow: UnitOfWork, fenced: Any, request: Any) -> None:
    identity = request.get("binding_identity")
    if identity is None:
        return
    if identity["host_id"] != str(fenced.worker.host_id):
        raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "effect is bound to another host")
    repository = UUID(request["repository_id"])
    mounts = [
        m for m in workspace.get_project(uow, fenced.run.project_id).mounts if m.repository_id == repository
    ]
    if len(mounts) != 1:
        raise error_for(ErrorCode.INVALID_REFERENCE, "effect repository is outside the project")
    location = workspace.resolve_checkout(
        uow, fenced.run.project_id, mounts[0].mount_name, fenced.worker.host_id, now=fenced.now
    )
    from hashlib import sha256

    if (
        location.state != "active"
        or location.is_stale
        or str(location.binding_id) != identity["binding_id"]
        or identity["repository_id"] != str(repository)
        or identity["locator_digest"] != "sha256:" + sha256(location.local_locator.encode()).hexdigest()
        or uow.repo(IntegrationSlotRepository).hosts_for_run(fenced.run.id).get(RepositoryId(repository))
        != fenced.worker.host_id
    ):
        raise error_for(
            ErrorCode.INVALID_REFERENCE, "current checkout identity differs from approved request"
        )
    if workspace.get_host(uow, fenced.worker.host_id).state != "active":
        raise error_for(ErrorCode.FORBIDDEN, "writer host requires activation")


def propose_effects(uow: UnitOfWork, ctx: Any, fenced: Any, outcome: Any) -> None:
    requests = [outcome["effect_request"]] if "effect_request" in outcome else outcome.get("effects", ())
    if not requests or len(requests) > 8:
        raise error_for(ErrorCode.SCHEMA_INVALID, "approval result requires bounded exact effect requests")
    perms = effective_permissions(
        uow,
        scope_chain=ctx.scope_chain,
        config=ctx.config,
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    existing = attempt_effects(uow, fenced.attempt.id)
    created: list[Any] = []
    states: list[str] = []
    for raw in requests:
        kind = EffectKind(raw["kind"])
        if kind is EffectKind.FS_WRITE_EXTERNAL:
            raise error_for(ErrorCode.FORBIDDEN, "unattended agents cannot request external file writes")
        if kind is EffectKind.GIT_COMMIT:
            raise error_for(ErrorCode.FORBIDDEN, "local commits require the writer admission protocol")
        args = raw["args"]
        validate_target(uow, fenced, args)
        if kind is EffectKind.GIT_PUSH and not any(
            e.kind is EffectKind.GIT_COMMIT
            and e.state is EffectState.SUCCEEDED
            and e.request["repository_id"] == args["repository_id"]
            and e.request["after_sha"] == args["after_sha"]
            for e in existing
        ):
            raise error_for(
                ErrorCode.INVALID_REFERENCE, "push candidate is not an accepted integration receipt"
            )
        matches = [
            e for e in existing if e.kind is kind and e.request == args and e.state is not EffectState.FAILED
        ]
        if matches:
            effect = matches[0]
            if effect.state is not EffectState.INTENDED:
                raise error_for(ErrorCode.OUTCOME_UNKNOWN, "effect already executed; no new proposal")
            intent = propose_intent(
                uow,
                ctx,
                scope_id=ScopeId(fenced.run.id),
                subject_ref=f"attempt:{fenced.attempt.id}",
                kind=PolicyEffectKind(kind.value),
                args=args,
                reason=str(raw.get("reason", "Integration requires approval")),
                perms=perms,
            )
            if intent.intent_id != effect.intent_id:
                raise error_for(ErrorCode.APPROVAL_MISMATCH, "effect intent is no longer active")
        else:
            intent = propose_intent(
                uow,
                ctx,
                scope_id=ScopeId(fenced.run.id),
                subject_ref=f"attempt:{fenced.attempt.id}",
                kind=PolicyEffectKind(kind.value),
                args=args,
                reason=str(raw.get("reason", "Integration requires approval")),
                perms=perms,
            )
            if intent.state == "denied":
                raise error_for(ErrorCode.FORBIDDEN, "current policy denies the requested effect")
            effect = ExternalEffect(
                ctx.ids.new_id(),
                fenced.run.workspace_id,
                fenced.run.id,
                fenced.attempt.id,
                fenced.task.id,
                kind,
                intent.intent_id,
                intent.args_digest,
                document(intent.normalized_args),
                EffectState.INTENDED,
                None,
                fenced.now,
                fenced.now,
            )
            uow.repo(EffectRepository).add(effect)
        created.append(effect)
        states.append(intent.state)
    outcome.update(
        effect_ids=[str(e.id) for e in created],
        effect_id=str(created[0].id),
        intent_id=str(created[0].intent_id),
        intent_state=states[0],
    )


def prepare_external(uow: UnitOfWork, fenced: Any, stage: Any, effect_id: Any = None) -> Any:
    metadata: Any = stage.outcome or {}
    identity: Any = effect_id or metadata["external_effect_id"]
    effect = uow.repo(EffectRepository).get(ExternalEffectId(UUID(str(identity))))
    if effect.attempt_id != fenced.attempt.id or effect.kind is EffectKind.GIT_COMMIT:
        raise error_for(ErrorCode.INVALID_REFERENCE, "integrate effect is outside the selected attempt")
    validate_target(uow, fenced, effect.request)
    packet: Any = next(
        (
            e.record.outcome["integration_inputs"]
            for e in reversed(uow.repo(StageRepository).history(fenced.attempt.id).entries)
            if e.record.outcome and "integration_inputs" in e.record.outcome
        ),
        None,
    )
    if packet is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "external effect requires the original accepted inputs")
    metadata = {"integration_inputs": packet, "external_effect_id": str(effect.id)}
    uow.repo(StageRepository).save(replace(stage, outcome=metadata))
    return {
        **document(packet),
        "external_effect": {
            "state": effect.state.value,
            "receipt": document(effect.receipt),
            "effect_id": str(effect.id),
            "kind": effect.kind.value,
            "request_digest": effect.request_digest,
            "request": document(effect.request),
        },
        "external_effects": [
            {
                "effect_id": str(e.id),
                "kind": e.kind.value,
                "state": e.state.value,
                "request": document(e.request),
            }
            for e in attempt_effects(uow, fenced.attempt.id)
            if e.kind is not EffectKind.GIT_COMMIT
        ],
    }


def record_intent_effect(cmd: Any, ctx: Any, uow: UnitOfWork) -> RecordExternalEffectResult:
    if not cmd.get("effect_id"):
        raise error_for(
            ErrorCode.INVALID_REFERENCE, "external execution requires the selected effect identity"
        )
    fenced = lock_fenced_context(uow, ctx, cmd["claim"], allow_terminal=True)
    stages = uow.repo(StageRepository)
    stage = stages.started_without_result(fenced.attempt.id)
    if stage is None or stage.stage_type != "integrate" or stage.mode.value == "reconcile":
        raise error_for(ErrorCode.INVALID_TRANSITION, "external IO requires a normal integrate stage")
    stage = locked_stage(uow, fenced, stage.id)
    repo = uow.repo(EffectRepository)
    effect = repo.get(ExternalEffectId(UUID(cmd["effect_id"])), for_update=True)
    if effect.kind is EffectKind.FS_WRITE_EXTERNAL:
        raise error_for(ErrorCode.FORBIDDEN, "unattended workers cannot execute external file writes")
    if effect.kind is EffectKind.GIT_COMMIT or cmd["kind"] != effect.kind.value:
        raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "effect kind differs from its selected intent")
    metadata: Any = stage.outcome or {}
    if (
        metadata.get("external_effect_id") != str(effect.id)
        or (effect.attempt_id, effect.run_id, effect.task_id)
        != (fenced.attempt.id, fenced.run.id, fenced.task.id)
        or effect.intent_id is None
        or effect.request_digest != cmd["request_digest"]
        or (cmd.get("request") is not None and cmd["request"] != effect.request)
    ):
        raise error_for(
            ErrorCode.INVALID_REFERENCE, "external effect differs from its selected exact request"
        )
    admission = None
    phase = cmd["phase"]
    if phase == "executing":
        if fenced.run.status.value != "running" or effect.state is not EffectState.INTENDED:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "no new IO before reconciliation or while stopped")
        _, values = effective_values(uow, fenced.run.id)
        require_run_admission(uow, ctx, fenced.run, values)
        validate_target(uow, fenced, effect.request)
        require_approved(
            uow, ctx, intent_id=ToolIntentId(effect.intent_id), args_digest=effect.request_digest
        )
        effect = replace(effect, state=EffectState.EXECUTING, updated_at=fenced.now)
        repo.save(effect)
        admission = {
            "admission_id": str(ctx.ids.new_id()),
            "effect_id": str(effect.id),
            "request_digest": effect.request_digest,
            "server_now": fenced.now.isoformat(),
            "admit_until": min(fenced.lease.expires_at, fenced.now + timedelta(seconds=5)).isoformat(),
        }
    elif phase == "result":
        result = cmd["result"]
        state = EffectState.SUCCEEDED if result["succeeded"] else EffectState.FAILED
        receipt = {
            "ref": result.get("ref"),
            "response_digest": result.get("response_digest"),
            "at": fenced.now.isoformat(),
        }
        validate_observation(effect, state, receipt, result.get("error"))
        if effect.state is state:
            stored: Any = effect.receipt or {}
            if any(stored.get(k) != receipt[k] for k in ("ref", "response_digest")):
                raise error_for(ErrorCode.IDEMPOTENCY_KEY_REUSED, "effect receipt changed")
            return RecordExternalEffectResult(effect_id=str(effect.id), state=state.value, admission=None)
        if effect.state is not EffectState.EXECUTING:
            raise error_for(ErrorCode.OUTCOME_UNKNOWN, "effect result requires its one-use admission")
        record_outcome(
            uow, ctx, intent_id=ToolIntentId(effect.intent_id), outcome=state.value, receipt=receipt
        )
        effect = replace(effect, state=state, receipt=receipt, updated_at=fenced.now)
        repo.save(effect)
    else:
        raise error_for(ErrorCode.INVALID_TRANSITION, "intent effects are created only by approval outcomes")
    emit(
        uow,
        fenced.run,
        "external-effect-recorded",
        {
            "effect_id": str(effect.id),
            "kind": effect.kind.value,
            "state": effect.state.value,
            "attempt_id": str(effect.attempt_id),
            "output_ids": [],
            "intent_id": str(effect.intent_id),
            "request_digest": effect.request_digest,
        },
        cause("stage_outcome", refs=[{"kind": "stage", "id": str(stage.id)}]),
    )
    return RecordExternalEffectResult(effect_id=str(effect.id), state=effect.state.value, admission=admission)


def complete_external(uow: UnitOfWork, fenced: Any, stage: Any, outcome: Any) -> None:
    effects = attempt_effects(uow, fenced.attempt.id)
    if not effects or any(e.state is not EffectState.SUCCEEDED for e in effects):
        raise error_for(ErrorCode.OUTCOME_UNKNOWN, "partial external vector cannot complete integration")
    metadata: Any = stage.outcome or {}
    inputs: Any = metadata.get("integration_inputs", {})
    local = [e for e in effects if e.kind is EffectKind.GIT_COMMIT]
    targets = {t["effect_id"] for t in inputs.get("integration_targets", ())}
    if not targets or {str(e.id) for e in local} != targets:
        raise error_for(
            ErrorCode.INVALID_REFERENCE, "local receipts do not cover the accepted integration targets"
        )
    output, _, decision = accepted_inputs(uow, fenced)
    if inputs.get("acceptance_decision_id") != str(decision.id):
        raise error_for(ErrorCode.INVALID_REFERENCE, "acceptance changed during external integration")
    _, values = effective_values(uow, fenced.run.id)
    local.sort(key=lambda e: (e.request["repository_id"], e.request["target_branch"]))
    receipts = [document(e.receipt) for e in local]
    commits = [sha for e in local for sha in e.request["commit_shas"]]
    if outcome.get("commit_shas", commits) != commits:
        raise error_for(ErrorCode.INVALID_REFERENCE, "external result changed accepted commits")
    outcome.update(
        integration_receipts=receipts,
        commit_shas=commits,
        output_ids=[inputs["accepted_output_id"]],
        effect_ids=[str(e.id) for e in effects],
    )
    emit(
        uow,
        fenced.run,
        "integration-completed",
        {
            "task_id": str(fenced.task.id),
            "attempt_id": str(fenced.attempt.id),
            "output_ids": outcome["output_ids"],
            "commit_shas": commits,
            "target_branch": [e.request["target_branch"] for e in local],
            "integration_receipts": receipts,
            "commit_mode": values.get("execution.integration.commit_mode", "final_only"),
            "strategy": values.get("execution.integration.strategy", "squash"),
            "excluded_paths_count": len(output.manifest.excluded_paths),
        },
        cause("stage_outcome"),
    )


SPEC = CommandSpec(
    name="execution.record_external_effect",
    dto=RecordExternalEffect,
    result=RecordExternalEffectResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
