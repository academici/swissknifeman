"""PostgreSQL row <-> domain codecs for assignments, leases, environments, outputs, and step notes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import DictRow, process_identity_from_json
from skm.kernel.ids import (
    AttemptId,
    FileVersionId,
    HostId,
    RepositoryId,
    RunId,
    TaskId,
    WorkerId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.assignment import Assignment, AssignmentState, WorkerRequirements
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
)
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.ids import (
    AssignmentId,
    EnvironmentId,
    ExternalEffectId,
    OutputId,
    StageRecordId,
    StepId,
)
from skm.modules.execution.domain.lease import Lease
from skm.modules.execution.domain.output import (
    ChangedPath,
    DiffStats,
    Output,
    OutputManifest,
    OutputMount,
    OutputSource,
)
from skm.modules.execution.domain.step_note import NoteKind, StepNote, Urgency

__all__: list[str] = []


def step_note_from_row(r: DictRow) -> StepNote:
    urg = Urgency(str(r["urgency"])) if r["urgency"] is not None else Urgency.NORMAL
    return StepNote(
        id=as_uuid(r["id"]),
        step_id=StepId(as_uuid(r["step_id"])),
        kind=NoteKind(str(r["kind"])),
        text=str(r["text"]),
        options=tuple(cast("JsonObject", thaw_json(o)) for o in (r["options"] or ())),
        why_blocked=r["why_blocked"],
        urgency=urg,
        recorded_at=r["created_at"],
    )


def assignment_from_row(r: DictRow) -> Assignment:
    req = WorkerRequirements(
        capabilities=frozenset(str(x) for x in (r["required_capabilities"] or ())),
        required_host_id=None if r["required_host_id"] is None else HostId(as_uuid(r["required_host_id"])),
        required_labels=frozenset(str(x) for x in (r["required_labels"] or ())),
        environment_kind=EnvironmentKind(str(r["environment_kind"])),
        isolation_profiles=frozenset(str(x) for x in (r["required_isolation_profiles"] or ())),
    )
    return Assignment(
        id=AssignmentId(as_uuid(r["id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        workspace_id=WorkspaceId(as_uuid(r["workspace_id"])),
        state=AssignmentState(str(r["state"])),
        available_at=r["available_at"],
        requirements=req,
        priority=int(r["priority"]),
        last_fencing_token=int(r["last_fencing_token"]),
        reconcile_effect_id=(
            None if r["reconcile_effect_id"] is None else ExternalEffectId(as_uuid(r["reconcile_effect_id"]))
        ),
        reap_stage_record_id=(
            None if r["reap_stage_record_id"] is None else StageRecordId(as_uuid(r["reap_stage_record_id"]))
        ),
        reap_step_id=None if r["reap_step_id"] is None else StepId(as_uuid(r["reap_step_id"])),
        created_at=r["created_at"],
        row_version=int(r["row_version"]),
    )


def lease_from_row(r: DictRow) -> Lease:
    return Lease(
        assignment_id=AssignmentId(as_uuid(r["assignment_id"])),
        worker_id=WorkerId(as_uuid(r["worker_id"])),
        fencing_token=int(r["fencing_token"]),
        expires_at=r["expires_at"],
        last_heartbeat_at=r["last_heartbeat_at"],
        process_identity=process_identity_from_json(r["process_identity"]),
        offered_runtimes=frozenset(r["offered_runtimes"]),
    )


def environment_from_row(r: DictRow) -> ExecutionEnvironment:
    entries = tuple(
        BaselineEntry(
            mount=str(b["mount"]),
            repository_id=RepositoryId(as_uuid(b["repository_id"])),
            commit_sha=str(b["commit_sha"]),
            source_head_sha=str(b.get("source_head_sha", b["commit_sha"])),
            dirty_patch_file_version_id=(
                None
                if b.get("dirty_patch_file_version_id") is None
                else FileVersionId(as_uuid(b["dirty_patch_file_version_id"]))
            ),
        )
        for b in r["baseline"]
    )
    return ExecutionEnvironment(
        id=EnvironmentId(as_uuid(r["id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        host_id=HostId(as_uuid(r["host_id"])),
        kind=EnvironmentKind(str(r["kind"])),
        baseline=entries,
        branch=str(r["branch"]),
        local_locator=str(r["local_locator"]),
        state=EnvironmentState(str(r["state"])),
        created_at=r["created_at"],
        discarded_at=r["discarded_at"],
        removed_at=r["removed_at"],
    )


def _paths_from_json(items: Sequence[Any]) -> tuple[ChangedPath, ...]:
    return tuple(
        ChangedPath(
            mount=str(p["mount"]),
            path=str(p["path"]),
            path_bytes=str(p["path_bytes"]),
            change=cast("Literal['added', 'modified', 'deleted', 'renamed']", str(p["change"])),
            old_path=p.get("old_path"),
            old_path_bytes=p.get("old_path_bytes"),
            fingerprint=str(p["fingerprint"]),
        )
        for p in items
    )


def output_from_row(r: DictRow) -> Output:
    m = cast("Mapping[str, Any]", r["manifest"])
    ds = cast("Mapping[str, Any]", m["diff_stats"])
    manifest = OutputManifest(
        algorithm=cast("Literal['skm-output-v2']", str(m["algorithm"])),
        mounts=tuple(
            OutputMount(
                mount=str(mt["mount"]),
                repository_id=RepositoryId(as_uuid(mt["repository_id"])),
                object_format=cast("Literal['sha1', 'sha256']", str(mt["object_format"])),
                base_commit=str(mt["base_commit"]),
                head_commit=str(mt["head_commit"]),
                tree_sha=str(mt["tree_sha"]),
            )
            for mt in m["mounts"]
        ),
        changed_paths=_paths_from_json(m["changed_paths"]),
        tree_digest=str(m["tree_digest"]),
        outside_write_scope=_paths_from_json(m["outside_write_scope"]),
        excluded_paths=_paths_from_json(m["excluded_paths"]),
        patch_file_version_id=(
            None
            if m.get("patch_file_version_id") is None
            else FileVersionId(as_uuid(m["patch_file_version_id"]))
        ),
        diff_stats=DiffStats(int(ds["files"]), int(ds["insertions"]), int(ds["deletions"])),
        empty=bool(m["empty"]),
    )
    return Output(
        id=OutputId(as_uuid(r["id"])),
        attempt_id=AttemptId(as_uuid(r["attempt_id"])),
        task_id=TaskId(as_uuid(r["task_id"])),
        run_id=RunId(as_uuid(r["run_id"])),
        seq=int(r["seq"]),
        source=OutputSource(str(r["source"])),
        manifest=manifest,
        manifest_digest=str(r["manifest_digest"]),
        sealed_at=r["sealed_at"],
        produced_by_step_id=(
            None if r["produced_by_step_id"] is None else StepId(as_uuid(r["produced_by_step_id"]))
        ),
    )
