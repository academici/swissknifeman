"""Worker capacity, fenced stage lifecycle and stop-mode admission. No repositories or database IO."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack, nullcontext
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from skm.kernel.cancel import Cancelled, CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Forbidden, SkmError
from skm.kernel.ids import AttemptId, WorkerId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access.public import generate_secret
from skm.modules.context.public import FinalizedContext
from skm.modules.execution.domain.assignment import StageInstruction
from skm.modules.execution.domain.ids import AssignmentId, EnvironmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.host.context import (
    EnvironmentBindings,
    StageToolBinding,
    WorkerServices,
    build_stage_deps,
)
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.host.evidence import upload_evidence
from skm.modules.execution.host.heartbeat import Heartbeat
from skm.modules.execution.host.stage_client import BoundStageClient, claim_json
from skm.modules.execution.host.stages.agent_step import usage_json
from skm.modules.execution.host.stages.base import CleanupUnconfirmed, StageCapture, StageRequest
from skm.modules.execution.ports import ExecutionEnvironmentManager
from skm.modules.runtimes.public import AgentRequest, Capability, RoleId, SecretStr
from skm.platform.config import EffectiveConfig

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext
    from skm.modules.execution.host.environment import PreparedEnvironment
    from skm.modules.execution.host.stages.base import StageOutcome
    from skm.modules.execution.ports import StageDeps
    from skm.modules.runtimes.public import SessionHandle


def _config(ctx: HostContext, key: str, default: int) -> int:
    value = cast("EffectiveConfig", ctx.config).get(key)
    return default if value is None else int(cast("int", value))


def _require_fresh_config(services: WorkerServices) -> None:
    if not services.refresh_config():
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Worker config is unavailable")


def _verify_handoff(request: AgentRequest, finalized: FinalizedContext) -> None:
    actual = "sha256:" + sha256(request.rendered_prompt.encode("utf-8")).hexdigest()
    if actual != request.prompt_digest or request.prompt_digest != finalized.prompt_digest:
        raise ValueError("runtime prompt bytes or digest differ from finalized context")


def _dispatch(ctx: HostContext, services: WorkerServices, name: str, payload: JsonObject) -> JsonObject:
    key = ctx.client.new_idempotency_key()
    command = services.commands[name](payload)
    # A broken response may follow a commit. Repeat the same DTO/key, including the same step secret.
    for index in range(2):
        try:
            return cast("JsonObject", ctx.client.dispatch(command, idempotency_key=key))
        except BackendUnavailable:
            if index:
                raise
    raise RuntimeError("unreachable dispatch")


def _instruction(raw: JsonObject) -> StageInstruction:
    deadline = raw.get("not_before")
    return StageInstruction(
        kind=cast("Literal['run_stage', 'release', 'wait']", raw["kind"]),
        stage_id=cast("str | None", raw.get("stage_id")),
        stage_type=cast("str | None", raw.get("stage_type")),
        mode=None if raw.get("mode") is None else StageMode(str(raw["mode"])),
        round_no=cast("int | None", raw.get("round_no")),
        params=cast("JsonObject | None", raw.get("params")),
        input_digest=cast("str | None", raw.get("input_digest")),
        not_before=None if deadline is None else datetime.fromisoformat(str(deadline).replace("Z", "+00:00")),
        environment=cast("JsonObject | None", raw.get("environment")),
        release_reason=cast("str | None", raw.get("release_reason")),
    )


def _environment(
    ctx: HostContext, instruction: StageInstruction, attempt_id: str
) -> PreparedEnvironment | None:
    data = instruction.environment
    if not data or not data.get("environment_id"):
        return None
    locator = data.get("locator", data.get("local_locator"))
    if not isinstance(locator, str):
        locator = EnvironmentBindings(ctx.gateways.get(WorkerServices), floor=0).locator(
            attempt_id, str(data["environment_id"])
        )
    return ctx.gateways.get(ExecutionEnvironmentManager).reopen(
        EnvironmentId(UUID(str(data["environment_id"]))), locator
    )


def _reserve(ctx: HostContext, services: WorkerServices, owner: str) -> StageCapture:
    # Include immutable ownership in the directory and logical ledger owner. No cleanup by age.
    root = services.state_dir / "evidence" / owner
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return StageCapture(
        root,
        services.storage,
        owner=owner,
        max_bytes=services.capture_max_bytes,
        floor=_config(ctx, "worker.disk_min_bytes", 0),
    )


def _record(
    ctx: HostContext,
    services: WorkerServices,
    worker: BoundStageClient,
    claim: WorkerClaim,
    request: StageRequest,
    outcome: StageOutcome,
) -> JsonObject:
    if not outcome.reaped or outcome.payload.get("error_code") == "CHECK_CLEANUP_UNCONFIRMED":
        raise CleanupUnconfirmed("stage has live or unknown descendants")
    ctx.cancel.raise_if_cancelled()
    worker.flush_tool_calls()
    ctx.cancel.raise_if_cancelled()
    payload = dict(outcome.payload)
    if outcome.output_manifest and not payload.get("output_id"):
        payload["output_id"] = worker.seal_output(outcome.output_manifest, None)["output_id"]
    ctx.cancel.raise_if_cancelled()
    deps = build_stage_deps(
        ctx, claim, None, workspace_id=WorkspaceId(UUID(str(request.task["workspace_id"]))), worker=worker
    )
    staged = upload_evidence(outcome.files, deps.uploader, services.read_bytes)
    # Linearize result against heartbeat's stop decision and clear stage facts before its next tick.
    with worker.guard:
        ctx.cancel.raise_if_cancelled()
        response = _dispatch(
            ctx,
            services,
            "record_stage_result",
            {
                "claim": claim_json(claim),
                "stage_record_id": request.begin["stage_record_id"],
                "outcome_kind": outcome.kind.value,
                "outcome": payload,
                "evidence": list[JsonValue](staged),
                "usage": None if outcome.usage is None else usage_json(outcome.usage),
                "observations": list[JsonValue](cast("tuple[JsonValue, ...]", outcome.observations)),
                "diagnostics": list[JsonValue](outcome.diagnostics),
                "activity": None if outcome.activity is None else dict(outcome.activity),
            },
        )
        worker.clear_progress(assignment_finished=cast("JsonObject", response["next"])["kind"] != "run_stage")
        return response


def _bind_stage_tools(
    stack: ExitStack,
    ctx: HostContext,
    services: WorkerServices,
    request: StageRequest,
    deps: StageDeps,
    secret: SecretStr | None,
    claim: WorkerClaim,
) -> StageRequest:
    agent = request.runtime_request
    if services.stage_tools is None or agent is None or agent.role is RoleId.ADVISOR or secret is None:
        return request
    binding = StageToolBinding(
        claim,
        WorkspaceId(UUID(str(request.task["workspace_id"]))),
        UUID(str(request.task["project_id"])),
        UUID(str(request.task["run_id"])),
        UUID(str(request.begin["stage_record_id"])),
        UUID(agent.request_id),
        agent.permissions.tools,
    )
    channel = stack.enter_context(services.stage_tools(binding, secret, ctx.client))
    capabilities = deps.runtimes.get(agent.runtime_id).capabilities()

    def process_started(handle: SessionHandle) -> None:
        services.process_started(handle)
        channel.process_started(handle)

    return replace(
        request,
        runtime_request=replace(
            agent,
            stage_tool_socket=channel.path,
            extra_env={**agent.extra_env, "SKM_STAGE_SOCKET": channel.path},
            mcp_servers=(*agent.mcp_servers, channel.server)
            if capabilities.supports(Capability.MCP_SUPPORT)
            else agent.mcp_servers,
        ),
        process_started=process_started,
    )


def _stage(  # noqa: PLR0912, PLR0915 - ordered begin/finalize/handoff/result lifecycle
    ctx: HostContext,
    services: WorkerServices,
    claim: WorkerClaim,
    worker: BoundStageClient,
    heartbeat: Heartbeat,
    instruction: StageInstruction,
    task: JsonObject,
    environment: PreparedEnvironment | None,
) -> tuple[JsonObject, PreparedEnvironment | None]:
    handler = services.stages.for_stage(str(instruction.stage_type))
    if instruction.not_before is not None:
        ctx.cancel.wait(max(0, (instruction.not_before - services.clock.now()).total_seconds()))
    ctx.cancel.raise_if_cancelled()
    agent_stage = instruction.stage_type in {"agent_step", "agent_review", "advisor_consult"}
    secret = SecretStr(str(generate_secret(services.entropy.bytes))) if agent_stage else None
    admission = ExitStack()
    try:
        roots = {services.state_dir}
        if environment is not None:
            roots.update(environment.mounts.values())
        for root in sorted(roots):
            admission.enter_context(
                services.storage.reserve(
                    root,
                    owner_id=str(claim.assignment_id),
                    max_bytes=8192,
                    min_free_bytes=_config(ctx, "worker.disk_min_bytes", 0),
                    max_files=1,
                )
            )
        with worker.guard:
            begin = _dispatch(
                ctx,
                services,
                "begin_stage",
                {
                    "claim": claim_json(claim),
                    "stage_id": instruction.stage_id,
                    "round_no": instruction.round_no,
                    "input_digest": instruction.input_digest,
                    **({"runtime_token_secret": secret.reveal()} if secret is not None else {}),
                },
            )
            if begin.get("outcome") == "refused":
                worker.clear_progress(
                    assignment_finished=cast("JsonObject", begin["next"])["kind"] != "run_stage"
                )
        if begin.get("outcome") == "refused":
            return cast("JsonObject", begin["next"]), environment
        if begin.get("already_completed"):
            with worker.guard:
                ctx.cancel.raise_if_cancelled()
                result = _dispatch(
                    ctx,
                    services,
                    "record_stage_result",
                    {
                        "claim": claim_json(claim),
                        "stage_record_id": begin["stage_record_id"],
                        "outcome": begin["prior_outcome"],
                        "outcome_kind": begin.get("prior_outcome_kind", "success"),
                    },
                )
                worker.clear_progress(
                    assignment_finished=cast("JsonObject", result["next"])["kind"] != "run_stage"
                )
            return cast("JsonObject", result["next"]), environment
        capture = _reserve(ctx, services, f"{claim.attempt_id}/{begin['stage_record_id']}")
        if secret is not None:
            capture.redactor.register_secret(secret.reveal())
        request: StageRequest | None = None
        try:
            deps = build_stage_deps(
                ctx,
                claim,
                environment,
                workspace_id=WorkspaceId(UUID(str(task["workspace_id"]))),
                worker=worker,
            )
            request = StageRequest(
                instruction, begin, None, task, capture=capture, process_started=services.process_started
            )
            step = begin.get("step")
            worker.set_stage(
                str(begin["stage_record_id"]), str(step["step_id"]) if isinstance(step, dict) else None
            )
            if isinstance(step, dict):
                if services.context_inputs is None or environment is None or secret is None:
                    raise ValueError("agent stage requires context services and a prepared environment")
                stage_request = request

                def observe_runtime(final: FinalizedContext) -> Sequence[JsonObject]:
                    nonlocal request
                    request = replace(stage_request, context=final)
                    runtime_request = services.runtime_request(request, deps)
                    request = replace(request, runtime_request=runtime_request)
                    _verify_handoff(runtime_request, final)
                    runtime = deps.runtimes.get(runtime_request.runtime_id)
                    observe = getattr(runtime, "self_loaded_context", None)
                    return (
                        tuple(
                            {
                                "kind": str(source.kind),
                                "locator": source.locator,
                                "files": list(source.files),
                                "when": source.when,
                            }
                            for source in observe(runtime_request)
                        )
                        if observe is not None
                        else ()
                    )

                finalized = finalize_stage_context(
                    ctx,
                    claim,
                    begin,
                    environment,
                    services.context_inputs,
                    workspace_id=WorkspaceId(UUID(str(task["workspace_id"]))),
                    path_patterns=tuple(
                        (item.split(":", 1)[0], item.split(":", 1)[1])
                        for item in cast("list[str]", task.get("declared_write_scope", []))
                    ),
                    runtime_self_loaded=observe_runtime,
                )
                if request.runtime_request is None:
                    raise ValueError("context finalization did not prepare a runtime request")
                _verify_handoff(request.runtime_request, finalized)
                _require_fresh_config(services)
                route = cast("JsonObject", step.get("route_snapshot", {}))
                services.verify_runtime(
                    request.runtime_request, cast("str | None", route.get("executable_sha256"))
                )
                handoff = worker.report_progress(
                    {
                        "stage_record_id": begin["stage_record_id"],
                        "step_id": step["step_id"],
                        "phase": "runtime_started",
                    }
                )
                heartbeat.observe(handoff)
                if handoff.get("refusal") or handoff.get("cancel_requested"):
                    worker.clear_progress()
                    return cast(
                        "JsonObject", handoff.get("next") or {"kind": "release", "release_reason": "paused"}
                    ), environment
            ctx.cancel.raise_if_cancelled()
            live = (
                services.live(claim, capture.redactor)
                if services.live and request.runtime_request
                else nullcontext()
            )
            with ExitStack() as running, live as offer:
                bound = _bind_stage_tools(running, ctx, services, request, deps, secret, claim)
                outcome = handler.run(replace(bound, offer_live=offer), deps)
            if services.snapshot is not None and heartbeat.snapshot_requested.is_set():
                services.snapshot(request, deps, capture)
            if ctx.cancel.cancelled:
                if not outcome.reaped:
                    raise CleanupUnconfirmed("cancelled stage did not confirm cleanup")
                if ctx.cancel.reason == "shutdown":
                    raise Cancelled("shutdown")
                raise Cancelled(ctx.cancel.reason or "user_cancel")
            if instruction.stage_type == "prepare_environment" and outcome.kind is StageOutcomeKind.SUCCESS:
                mounts = cast("list[JsonObject]", outcome.payload["mounts"])
                EnvironmentBindings(services, floor=_config(ctx, "worker.disk_min_bytes", 0)).remember(
                    str(claim.attempt_id),
                    str(outcome.payload["environment_id"]),
                    str(mounts[0]["environment_locator"]),
                )
            result = _record(ctx, services, worker, claim, request, outcome)
            if instruction.stage_type == "prepare_environment" and outcome.kind is StageOutcomeKind.SUCCESS:
                mounts = cast("list[JsonObject]", outcome.payload["mounts"])
                environment = ctx.gateways.get(ExecutionEnvironmentManager).reopen(
                    EnvironmentId(UUID(str(outcome.payload["environment_id"]))),
                    str(mounts[0]["environment_locator"]),
                )
            return cast("JsonObject", result["next"]), environment
        finally:
            if (
                request is not None
                and request.runtime_request is not None
                and isinstance(request.runtime_request.secret_env, dict)
            ):
                request.runtime_request.secret_env.clear()
            capture.close()
    finally:
        secret = None
        admission.close()


def _assignment(ctx: HostContext, services: WorkerServices, response: JsonObject, worker_id: str) -> str:
    source = CancelSource(parent=ctx.cancel)
    active = replace(ctx, cancel=source.token)
    claim = WorkerClaim(
        AssignmentId(UUID(str(response["assignment_id"]))),
        AttemptId(UUID(str(response["attempt_id"]))),
        WorkerId(UUID(worker_id)),
        int(cast("int", response["fencing_token"])),
    )
    worker = BoundStageClient(
        active.client, claim, services.commands, source.token, source.cancel, concurrency=services.concurrency
    )
    heartbeat = Heartbeat(
        worker,
        source,
        every_seconds=int(cast("int", response.get("renew_every_seconds", 40))),
        tick_hook=services.tick,
        concurrency=services.concurrency,
    )
    instruction = _instruction(cast("JsonObject", response["instruction"]))
    task = cast("JsonObject", response["task"])
    task.update(
        {
            "attempt_id": str(claim.attempt_id),
            "worker_id": worker_id,
            "assignment_fencing_token": claim.fencing_token,
            "host_id": str(ctx.host_id),
            "run_id": response.get("run_id"),
            "task_id": response.get("task_id"),
            "task_key": task.get("display_key", ""),
        }
    )
    environment = None
    heartbeat.start()
    try:
        environment = _environment(ctx, instruction, str(claim.attempt_id))
        while instruction.kind == "run_stage":
            _require_fresh_config(services)
            services.tick()
            services.refresh_offers()
            next_raw, environment = _stage(
                active, services, claim, worker, heartbeat, instruction, task, environment
            )
            instruction = _instruction(next_raw)
        heartbeat.stop()
        if instruction.kind == "release":
            # Committed pre-spawn cancellation already closed the stage and allows release.
            if source.token.reason not in {None, "user_cancel"}:
                source.token.raise_if_cancelled()
            _dispatch(
                ctx,
                services,
                "release_assignment",
                {
                    "claim": claim_json(claim),
                    "reason": instruction.release_reason or "waiting",
                    "retain_environment": True,
                },
            )
        return "released"  # noqa: TRY300 - terminal release belongs to the fenced lifecycle
    except CleanupUnconfirmed:
        source.cancel("lease_lost")
        return "cleanup_unconfirmed"
    except Cancelled as error:
        if error.reason == "shutdown":
            _dispatch(
                ctx,
                services,
                "report_attempt_failure",
                {
                    "claim": claim_json(claim),
                    "error_class": "worker_shutdown",
                    "detail": "worker shutdown",
                    "worktree_dirty": True,
                    "stage_record_id": worker.progress().get("stage_record_id"),
                    "usage": worker.progress().get("usage_so_far"),
                },
            )
        return error.reason
    except SkmError as error:
        disk_low = error.details.get("reason") == "disk_low"
        if isinstance(error, BackendUnavailable) and not disk_low:
            return "backend_unavailable"
        if error.code is ErrorCode.LEASE_LOST or source.token.reason == "lease_lost":
            source.cancel("lease_lost")
            return "lease_lost"
        _dispatch(
            ctx,
            services,
            "report_attempt_failure",
            {
                "claim": claim_json(claim),
                "error_class": "disk_low" if disk_low else "runtime_error",
                "detail": "host stage failed",
                "worktree_dirty": True,
                "stage_record_id": worker.progress().get("stage_record_id"),
                "usage": worker.progress().get("usage_so_far"),
            },
        )
        return "host_failure"
    except Exception:  # noqa: BLE001 - safe infra report, never serialize exception text or secrets
        if source.token.cancelled:
            return source.token.reason or "lease_lost"
        _dispatch(
            ctx,
            services,
            "report_attempt_failure",
            {
                "claim": claim_json(claim),
                "error_class": "runtime_error",
                "detail": "host stage failed",
                "worktree_dirty": True,
                "stage_record_id": worker.progress().get("stage_record_id"),
                "usage": worker.progress().get("usage_so_far"),
            },
        )
        return "host_failure"
    finally:
        heartbeat.stop()


def _run_slot(ctx: HostContext, request: JsonObject) -> JsonObject:
    services = ctx.gateways.get(WorkerServices)
    if services.workspace_id is not None and str(services.workspace_id) != request.get("workspace_id"):
        raise Forbidden(ErrorCode.FORBIDDEN, "Worker registration belongs to a different workspace")
    reaped = services.reap()
    if services.reap_pending():
        return {"outcome": "stopped", "reason": "cleanup_unconfirmed", "assignments": 0}
    completed = 0
    maximum = int(cast("int", request.get("max_assignments", 0)))
    while not ctx.cancel.cancelled and (maximum == 0 or completed < maximum):
        try:
            fresh = services.refresh_config()
            if fresh:
                services.tick()
                services.refresh_offers()
        except BackendUnavailable:
            fresh = False
        if not fresh:
            if request.get("once"):
                return {"outcome": "stopped", "reason": "backend_unavailable", "assignments": completed}
            ctx.cancel.wait(_config(ctx, "worker.claim.poll_ms", 2000) / 1000)
            continue
        if services.reap_pending():
            return {"outcome": "stopped", "reason": "cleanup_unconfirmed", "assignments": completed}
        snapshot = services.storage.snapshot(
            services.state_dir, min_free_bytes=_config(ctx, "worker.disk_min_bytes", 0)
        )
        if snapshot.available_bytes <= 0:
            return {"outcome": "stopped", "reason": "disk_low", "assignments": completed}
        payload = {
            key: value
            for key, value in request.items()
            if key in {"workspace_id", "worker_id", "host_id", "offer", "max_wait_seconds"}
        }
        payload["reaped_steps"] = list[JsonValue](reaped)
        response = _dispatch(ctx, services, "claim_assignment", payload)
        acknowledged = {
            str(item.get("stage_record_id")) for item in cast("list[JsonObject]", response.get("reaped", []))
        }
        services.acknowledge_reap(
            tuple(item for item in reaped if str(item["stage_record_id"]) in acknowledged)
        )
        reaped = tuple(item for item in reaped if str(item["stage_record_id"]) not in acknowledged)
        if response.get("outcome") == "nothing_to_claim":
            if request.get("once"):
                break
            ctx.cancel.wait(_config(ctx, "worker.claim.poll_ms", 2000) / 1000)
            continue
        task = cast("JsonObject", response["task"])
        task["workspace_id"] = request["workspace_id"]
        reason = _assignment(ctx, services, response, str(request["worker_id"]))
        completed += 1
        if reason != "released":
            return {"outcome": "stopped", "reason": reason, "assignments": completed}
    return {"outcome": "stopped", "assignments": completed}


def run(ctx: HostContext | Sequence[HostContext], request: JsonObject) -> JsonObject:
    """Execute one slot or an explicitly constructed capacity of independent host contexts."""
    if isinstance(ctx, Sequence):
        with ctx[0].gateways.get(WorkerServices).concurrency.pool(len(ctx)) as pool:
            results = tuple(
                future.result()
                for future in [pool.submit(_run_slot, context, dict(request)) for context in ctx]
            )
        return {"outcome": "stopped", "slots": list[JsonValue](results)}
    return _run_slot(ctx, request)
