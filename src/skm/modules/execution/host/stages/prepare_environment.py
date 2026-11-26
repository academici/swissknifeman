"""Prepare the exact environment requested by the admitted assignment."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.host.environment import EnvironmentSpec, PreparedEnvironment
from skm.modules.execution.host.evidence import EvidenceFile
from skm.modules.execution.host.stages.base import StageOutcome, StageRequest
from skm.modules.execution.ports import ExecutionEnvironmentManager

if TYPE_CHECKING:
    from skm.modules.execution.ports import StageDeps


class PrepareEnvironmentStage:
    stage_type: Literal["prepare_environment"] = "prepare_environment"
    side: Literal["host"] = "host"
    params_schema_urn = "urn:skm:execution:workflow:v1#/$defs/params"

    def __init__(
        self,
        manager: ExecutionEnvironmentManager,
        *,
        spec: Callable[[StageRequest, StageDeps], EnvironmentSpec],
        patch_files: Callable[[PreparedEnvironment], tuple[EvidenceFile, ...]],
        range_manifest: Callable[[EnvironmentSpec, PreparedEnvironment, StageDeps], JsonObject] | None = None,
    ) -> None:
        self.manager, self.spec, self.patch_files, self.range_manifest = (
            manager,
            spec,
            patch_files,
            range_manifest,
        )

    def run(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        deps.cancel.raise_if_cancelled()
        spec = self.spec(request, deps)
        prepared = self.manager.prepare(spec)
        files = self.patch_files(prepared)
        patch_names: dict[str, str] = {}
        for entry in prepared.baseline:
            if entry.commit_sha != entry.source_head_sha:
                patches = [
                    f
                    for f in files
                    if f.role == "patch"
                    and f.owner == f"attempt:{spec.attempt_id}"
                    and f.path.name == f"{entry.mount}.dirty.patch"
                ]
                if len(patches) != 1:
                    raise ValueError("each dirty baseline requires one attempt-owned patch")
                patch_names[entry.mount] = patches[0].filename
        baseline: list[JsonValue] = [
            {
                "mount": b.mount,
                "repository_id": str(b.repository_id),
                "commit_sha": b.commit_sha,
                "source_head_sha": b.source_head_sha,
                "dirty_patch_file_version_id": None
                if b.dirty_patch_file_version_id is None
                else str(b.dirty_patch_file_version_id),
            }
            for b in prepared.baseline
        ]
        payload: JsonObject = {
            "environment_id": str(prepared.environment_id),
            "kind": spec.kind.value,
            "branch": prepared.branch,
            "mounts": [
                {
                    "mount": mount,
                    "local_locator": str(path),
                    "environment_locator": prepared.locator,
                    "dirty_patch_filename": patch_names.get(mount),
                }
                for mount, path in prepared.mounts.items()
            ],
            "baseline": baseline,
        }
        manifest = None
        if spec.range is not None or spec.review_target is not None:
            if self.range_manifest is None:
                raise ValueError("gate/review preparation requires an exact range sealer")
            manifest = self.range_manifest(spec, prepared, deps)
        return StageOutcome(StageOutcomeKind.SUCCESS, payload, files, output_manifest=manifest)

    def __call__(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        return self.run(request, deps)
