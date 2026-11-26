"""Bind the built-in worker stages to admitted run inputs and host-local Git and check adapters."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

from skm.adapters.git.commit import ExcludeRules, GitOutputSealer, git_output_sealer
from skm.adapters.git.fingerprint import output_digest
from skm.adapters.git.host_inputs import capture_checkout
from skm.adapters.git.output_writer import PreSealSnapshot
from skm.adapters.git.runner import GitRunner
from skm.adapters.git.status import changed_paths, decode_path
from skm.bootstrap.host_services import read_runtime_transcript, worker_concurrency, worker_schema_issues
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import AttemptId, RepositoryId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.environment import EnvironmentKind, attempt_branch
from skm.modules.execution.domain.output import DiffStats, OutputManifest, manifest_to_json
from skm.modules.execution.host.environment import EnvironmentMount, EnvironmentSpec, PreparedEnvironment
from skm.modules.execution.host.isolation import IsolationSpec
from skm.modules.execution.host.stages.advisor_consult import AdvisorConsultStage
from skm.modules.execution.host.stages.agent_review import AgentReviewStage
from skm.modules.execution.host.stages.agent_step import AgentStepStage
from skm.modules.execution.host.stages.integrate import IntegrateStage
from skm.modules.execution.host.stages.prepare_environment import PrepareEnvironmentStage
from skm.modules.execution.host.stages.run_checks import RunChecksStage
from skm.modules.runtimes.public import ProcessOwner
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock

if TYPE_CHECKING:
    from skm.modules.execution.domain.ids import ExternalEffectId
    from skm.modules.execution.host.stages.base import StageRequest
    from skm.modules.execution.host.stages.registry import HostStage
    from skm.modules.execution.ports import ExecutionEnvironmentManager, StageDeps
    from skm.modules.workspace.public import ListProjectRepositoriesView, MountView
    from skm.platform.config.bootstrap import BootstrapConfig

__all__ = ["builtin_worker_stages", "seal_worker_snapshot"]


def _attempt(request: StageRequest) -> AttemptId:
    return AttemptId(UUID(str(request.task["attempt_id"])))


def _environment(deps: StageDeps) -> PreparedEnvironment:
    if deps.environment is None:
        raise ValueError("stage requires a prepared environment")
    return deps.environment


def _receipt(state_dir: Path, request: StageRequest) -> Path:
    return state_dir / "sealed-outputs" / f"{_attempt(request)}.json"


def _snapshot_manifest(
    sealer: GitOutputSealer,
    request: StageRequest,
    env: PreparedEnvironment,
    previous: dict[str, str],
    writers: dict[str, PreSealSnapshot],
) -> JsonObject:
    attempt = str(_attempt(request))
    scope = [p.split(":", 1) for p in cast("list[str]", request.task["declared_write_scope"])]
    parts: list[OutputManifest] = []
    for entry in env.baseline:
        patterns = [pattern for mount, pattern in scope if mount == entry.mount]
        parts.append(
            sealer.seal(
                env.mounts[entry.mount],
                attempt_id=attempt,
                output_no=writers[entry.mount].output_no,
                writer=writers[entry.mount],
                mount=entry.mount,
                repository_id=entry.repository_id,
                baseline=entry.commit_sha,
                write_scope=patterns,
                read_only=not patterns,
                previous=previous.get(entry.mount),
            )
        )
    mounts = tuple(m for part in parts for m in part.mounts)
    paths = tuple(p for part in parts for p in part.changed_paths)
    return manifest_to_json(
        OutputManifest(
            "skm-output-v2",
            mounts,
            paths,
            output_digest(mounts, paths),
            (),
            tuple(p for part in parts for p in part.excluded_paths),
            None,
            DiffStats(
                len(paths),
                sum(p.diff_stats.insertions for p in parts),
                sum(p.diff_stats.deletions for p in parts),
            ),
            not paths,
        )
    )


def seal_worker_snapshot(
    git: GitRunner,
    state_dir: Path,
    manager: ExecutionEnvironmentManager,
    request: StageRequest,
    deps: StageDeps,
) -> str | None:
    """Record the pre-seal tuple, then confirm exactly the manifest accepted by the fenced server."""
    sealer = git_output_sealer(git, state_dir=state_dir / "snapshots")
    prepared = _environment(deps)
    env = manager.reopen(prepared.environment_id, prepared.locator)
    path = _receipt(state_dir, request)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    step = cast("JsonObject", request.begin["step"])
    step_id = UUID(str(step["step_id"]))
    fence = int(cast("int", request.task["assignment_fencing_token"]))
    stage = request.begin["stage_record_id"]
    with FileLock(path.with_suffix(".lock")).hold(timeout_seconds=1):
        deps.cancel.raise_if_cancelled()
        prior: dict[str, Any] = json.loads(path.read_bytes()) if path.exists() else {}
        replay = prior.get("stage") == stage
        if not replay and prior.get("confirmed") is False:
            raise PreconditionFailed(
                ErrorCode.CHECKOUT_BUSY, "previous output still awaits seal confirmation"
            )
        seq = int(prior.get("seq", 0)) + (0 if replay else 1)
        writers = {
            mount: PreSealSnapshot(_attempt(request), step_id, seq, mount, capture_checkout(root), fence)
            for mount, root in env.mounts.items()
        }
        if replay:
            manifest = prior["manifest"]
        else:
            signal = deps.worker.report_progress({"stage_record_id": stage, "step_id": str(step_id)})
            if signal.get("refusal") or signal.get("cancel_requested"):
                raise PreconditionFailed(ErrorCode.LEASE_LOST, "snapshot requires an active assignment")
            previous = {m["mount"]: m["head_commit"] for m in prior["manifest"]["mounts"]} if prior else {}
            review = request.begin.get("review")
            if isinstance(review, dict) and review.get("reviewer_with_fix") is True:
                if previous.keys() != env.mounts.keys():
                    raise ValueError("review fix requires the previous sealed output on every mount")
                exclude = ExcludeRules()
                if not any(
                    not exclude.excludes(decode_path(path.path_bytes))
                    for mount, root in env.mounts.items()
                    for path in changed_paths(git, root, previous[mount], mount=mount)
                ):
                    return None
            manifest = _snapshot_manifest(sealer, request, env, previous, writers)
            prior = {"stage": stage, "seq": seq, "manifest": manifest, "confirmed": False}
            atomic_write(path, json.dumps(prior).encode(), mode=0o600, private=True)
        mounts = cast("list[dict[str, str]]", manifest["mounts"])
        for entry in mounts:
            writers[entry["mount"]].verify(git, entry["head_commit"])
        sealed = deps.worker.seal_output(manifest, None)
        if sealed["seq"] != seq:
            raise PreconditionFailed(ErrorCode.CHECKOUT_MISMATCH, "sealed output sequence changed")
        output_id = UUID(str(sealed["output_id"]))
        for entry in mounts:
            writers[entry["mount"]].confirm(
                git,
                entry["head_commit"],
                output_id=output_id,
                manifest_digest=str(sealed["manifest_digest"]),
            )
        if prior.get("confirmed") is not True:
            prior["confirmed"] = True
            atomic_write(path, json.dumps(prior).encode(), mode=0o600, private=True)
        return str(output_id)


def builtin_worker_stages(
    bootstrap: BootstrapConfig,
    manager: ExecutionEnvironmentManager,
    repositories_for_project: Callable[[UUID], ListProjectRepositoriesView],
    *,
    checkout_root: Callable[[MountView], Path] | None = None,
) -> tuple[HostStage, ...]:
    git = GitRunner()

    def located(mount: MountView, locator: str) -> str:
        from skm.modules.workspace.public import checkout_id_from_locator

        if checkout_root is not None:
            return str(checkout_root(mount))
        if checkout_id_from_locator(locator) is not None:
            raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "Machine checkout storage is unavailable")
        return locator

    def seal_snapshot(request: StageRequest, deps: StageDeps) -> str | None:
        return seal_worker_snapshot(git, bootstrap.state_dir, manager, request, deps)

    def environment(request: StageRequest, _deps: StageDeps) -> EnvironmentSpec:
        params = request.instruction.params or {}
        if params.get("baseline_strategy", "integration_branch_head") != "integration_branch_head":
            raise PreconditionFailed(
                ErrorCode.CAPABILITY_UNAVAILABLE, "This baseline requires a pinned range"
            )
        project = UUID(str(request.task["project_id"]))
        branch = "refs/heads/" + str(request.task["integration_branch"])
        repositories = repositories_for_project(project)
        mounts: list[EnvironmentMount] = []
        for item in repositories.items:
            binding = item.binding
            if binding is None or not binding.local_locator:
                raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "Missing registered checkout")
            if binding.state != "active":
                raise PreconditionFailed(ErrorCode.CHECKOUT_MISMATCH, "Checkout binding is inactive")
            mounts.append(
                EnvironmentMount(
                    item.mount_name,
                    RepositoryId(item.repository.repository_id),
                    located(item, binding.local_locator),
                    branch,
                )
            )
        if not mounts:
            raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "Project has no registered mounts")
        attempt = _attempt(request)
        return EnvironmentSpec(
            attempt,
            EnvironmentKind.GIT_WORKTREE,
            tuple(mounts),
            attempt_branch(attempt),
            bootstrap.worktrees_root,
            None,
            None,
        )

    def marks(request: StageRequest, deps: StageDeps) -> Mapping[str, Mapping[str, str]]:
        result: dict[str, dict[str, str]] = {mount: {} for mount in _environment(deps).mounts}
        for entry in json.loads(_receipt(bootstrap.state_dir, request).read_bytes())["manifest"][
            "changed_paths"
        ]:
            result[entry["mount"]][entry["path_bytes"]] = entry["fingerprint"]
        return result

    def owner(request: StageRequest, kind: Literal["check", "git_effect"], unit_id: UUID) -> ProcessOwner:
        return ProcessOwner(
            UUID(str(request.task["host_id"])),
            UUID(str(request.task["worker_id"])),
            _attempt(request),
            UUID(str(request.begin["stage_record_id"])),
            kind,
            unit_id,
            secrets.token_hex(24),
            str(bootstrap.state_dir / "identities"),
        )

    def isolation(raw: JsonObject, cwd: Path, request: StageRequest, deps: StageDeps) -> IsolationSpec:
        roots = tuple(_environment(deps).mounts.values())
        return IsolationSpec(
            cwd,
            roots,
            (),
            (),
            True,
            "none",
            (),
            {},
            None,
            (),
            owner(request, "check", UUID(str(raw["check_execution_id"]))),
        )

    def ownership(effect: ExternalEffectId, request: StageRequest, _deps: StageDeps) -> JsonObject:
        unit = owner(request, "git_effect", effect)
        return {
            "kind": "pgroup_best_effort",
            "ref": f"pgroup:{effect}",
            "owner": {key: str(value) for key, value in asdict(unit).items()},
        }

    def verify(env: PreparedEnvironment) -> None:
        manager.reopen(env.environment_id, env.locator)

    def tips(request: StageRequest, deps: StageDeps) -> Mapping[str, str]:
        ref = "refs/heads/" + str(request.task["integration_branch"])
        return {
            mount: git.run(path, ["rev-parse", "--verify", ref]).stdout.strip()
            for mount, path in _environment(deps).mounts.items()
        }

    concurrency = worker_concurrency()
    agents = tuple(
        cls(
            concurrency=concurrency,
            validate_result=worker_schema_issues,
            seal_snapshot=seal_snapshot,
            read_transcript=read_runtime_transcript,
        )
        for cls in (AgentStepStage, AgentReviewStage, AdvisorConsultStage)
    )
    return cast(
        "tuple[HostStage, ...]",
        (
            PrepareEnvironmentStage(manager, spec=environment, patch_files=lambda _: ()),
            *agents,
            RunChecksStage(
                isolation=isolation,
                read_capture=Path.read_bytes,
                verify_environment=verify,
                candidate_marks=marks,
                environment_manager=manager,
                current_tips=tips,
            ),
            IntegrateStage(ownership=ownership),
        ),
    )
