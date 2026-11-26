"""Phase B context assembly, pinned prompt publication and manifest finalization before spawn."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Protocol, cast

from skm.kernel.errors import BackendUnavailable
from skm.modules.context.public import (
    ContextDraft,
    FinalizedContext,
    HostInputKind,
    ResearchBatch,
    collect_host_blocks,
    finalize,
    finalize_command,
)

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext
    from skm.kernel.ids import WorkspaceId
    from skm.kernel.json_types import JsonObject
    from skm.modules.execution.domain.lease import WorkerClaim
    from skm.modules.execution.host.environment import PreparedEnvironment


class PromptEstimator(Protocol):
    estimator_id: str

    def estimate(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class ContextInputs:
    estimator: PromptEstimator
    decode: Callable[[JsonObject], ContextDraft]
    checkout: Callable[[PreparedEnvironment], Any]
    publish_prompt: Callable[[HostContext, bytes, str], JsonObject] | None
    finalize_dto: Callable[[JsonObject], object]
    owner_claim: Callable[[WorkerClaim], Any] = lambda claim: claim
    research_query: Callable[[HostContext, JsonObject], object] | None = None
    research_limits: tuple[int, int] = (2, 3)


def finalize_stage_context(  # noqa: PLR0912 - ordered context assembly and publication
    ctx: HostContext,
    claim: WorkerClaim,
    begin: JsonObject,
    environment: PreparedEnvironment,
    inputs: ContextInputs,
    *,
    workspace_id: WorkspaceId,
    path_patterns: tuple[tuple[str, str], ...] = (),
    runtime_self_loaded: Sequence[JsonObject] | Callable[[FinalizedContext], Sequence[JsonObject]] = (),
) -> FinalizedContext:
    ctx.cancel.raise_if_cancelled()
    step = cast("JsonObject", begin["step"])
    data = cast("JsonObject", step["context"])
    raw = data.get("draft")
    if not isinstance(raw, dict):
        raise ValueError(
            "BeginStage must supply the pinned context draft; cached secrets are not recoverable"
        )
    draft = inputs.decode(raw)
    if inputs.estimator.estimator_id != data["estimator_id"]:
        raise ValueError("host and control plane must use the same estimator")
    if str(draft.manifest_id) != str(data.get("manifest_id", draft.manifest_id)):
        raise ValueError("context draft belongs to a different manifest")
    limits = data.get("host_limits")
    if not isinstance(limits, dict) or any(
        type(limits.get(key)) is not int or cast("int", limits[key]) < 0
        for key in ("max_bytes", "max_work_paths")
    ):
        raise ValueError("BeginStage must supply frozen context host limits")
    research: dict[str, ResearchBatch] = {}
    run_variables = cast("JsonObject", draft.variables.get("run", {}))
    round_no = int(cast("int", run_variables.get("round_no", 1)))
    round_limit, max_follow_up = inputs.research_limits
    query_limit = 1 if round_no == 1 else max_follow_up
    research_count = 0
    for request in draft.host_inputs:
        if request.kind is not HostInputKind.RESEARCH_QUERY:
            continue
        ctx.cancel.raise_if_cancelled()
        if round_no > round_limit or research_count >= query_limit:
            cast("Any", ctx.log).warning(
                "execution.research_follow_up_dropped", code="RESEARCH_FOLLOW_UP_DROPPED"
            )
            continue
        research_count += 1
        if request.research is None or inputs.research_query is None:
            raise ValueError("research host operation must be composed before runtime")
        manifest_scope = cast("JsonObject", raw.get("manifest") or {})
        project_id = str(draft.manifest.project_id) if draft.manifest else manifest_scope.get("project_id")
        if not isinstance(project_id, str):
            raise ValueError("pinned context draft must identify its project")
        batch = inputs.research_query(
            ctx,
            {
                "spec": cast("JsonObject", asdict(request.research)),
                "workspace_id": str(workspace_id),
                "project_id": project_id,
                "step_ref": "step:" + str(step["step_id"]),
                "mounts": {name: str(path) for name, path in environment.mounts.items()},
            },
        )
        if not isinstance(batch, ResearchBatch):
            raise TypeError("research operation must return a verified ResearchBatch")
        research[request.request_id] = batch
    # CheckoutReader is supplied by bootstrap, scoped to this attempt's mounts.
    blocks, facts = collect_host_blocks(
        draft.host_inputs,
        inputs.checkout(environment),
        inputs.estimator,
        total_max_bytes=cast("int", limits["max_bytes"]),
        max_work_paths=cast("int", limits["max_work_paths"]),
        repo_max_files=draft.repo_max_files,
        path_patterns=path_patterns,
        research=research,
        draft=draft,
    )
    finalized = finalize(draft, blocks, facts, inputs.estimator)
    ctx.cancel.raise_if_cancelled()
    content = finalized.rendered_prompt.encode("utf-8")
    if (
        finalized.prompt_digest != "sha256:" + sha256(content).hexdigest()
        or finalized.manifest.prompt_digest != finalized.prompt_digest
        or finalized.manifest.id != draft.manifest_id
        or finalized.manifest.estimator_id != inputs.estimator.estimator_id
    ):
        raise ValueError("final context bytes, digest or manifest identity changed")
    observed = runtime_self_loaded(finalized) if callable(runtime_self_loaded) else runtime_self_loaded
    if inputs.publish_prompt is None:
        from skm.modules.execution.host.context import AssignmentUploader

        prompt_blob = AssignmentUploader(ctx, workspace_id, claim).upload_blob(content)
    else:
        prompt_blob = inputs.publish_prompt(ctx, content, str(step["step_id"]))
    ctx.cancel.raise_if_cancelled()
    command = finalize_command(
        draft,
        finalized,
        blocks,
        facts,
        prompt_staged_blob=prompt_blob,
        claim=inputs.owner_claim(claim),
        store_content=data.get("store_host_content", False) is True,
        runtime_self_loaded=observed,
    )
    research_ids = {block.request_id: list(block.research_query_ids) for block in blocks}
    for row in cast("list[JsonObject]", command["host_blocks"]):
        row["research_query_ids"] = cast("Any", research_ids[str(row["request_id"])])
    # Intrinsically idempotent, but generic idempotency is FORBIDDEN for finalize_manifest.
    dto = inputs.finalize_dto(command)
    try:
        ctx.client.dispatch(dto)
    except BackendUnavailable:
        ctx.cancel.raise_if_cancelled()
        ctx.client.dispatch(dto)
    return finalized
