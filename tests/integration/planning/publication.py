"""Shared helpers of the publish-revision suites: planning settings, contexts and file uploads.

Every suite runs over the artifacts upload harness (``integration.artifacts.test_upload_flow``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import Harness, add_file_dto, dispatch_new
from skm.application_bus.context import CommandContext
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import FileVersionId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.generated import commands as art_cmds
from skm.modules.planning.generated.settings import PlanningSettings

if TYPE_CHECKING:
    from skm.kernel.actor import Actor
    from skm.kernel.ids import PlanId
    from skm.kernel.json_types import JsonValue

__all__ = [
    "MAT_LATEST_ID",
    "MAT_PINNED_ID",
    "StaticPlanningConfig",
    "default_planning_settings",
    "make_prepare_ctx",
    "req_meta",
    "strict_planning_settings",
    "two_file_materials",
    "upload_next_version",
    "upload_v1",
]


MAT_LATEST_ID = "01900000-0000-7000-8000-000000000201"
MAT_PINNED_ID = "01900000-0000-7000-8000-000000000202"


def two_file_materials(fv_1_id: FileVersionId, fv_2_id: FileVersionId) -> list[JsonValue]:
    """A ``latest_at_publish`` input on ``fv_1_id`` (P1) and a pinned reference on ``fv_2_id`` (P1.1)."""
    return [
        {
            "id": MAT_LATEST_ID,
            "key": "api-guide",
            "title": "API Guide",
            "kind": "file_version",
            "file_version_id": str(fv_1_id),
            "role": "input",
            "required_for": ["execution"],
            "freshness": {"policy": "latest_at_publish"},
            "selector": {"kind": "line_range", "from": 1, "to": 20},
            "applies_to": ["P1"],
        },
        {
            "id": MAT_PINNED_ID,
            "key": "ref-notes",
            "title": "Reference Notes",
            "kind": "file_version",
            "file_version_id": str(fv_2_id),
            "role": "reference",
            "freshness": {"policy": "pinned"},
            "applies_to": ["P1.1"],
        },
    ]


class StaticPlanningConfig:
    """A config view that only serves the planning section."""

    def __init__(self, settings: PlanningSettings) -> None:
        self._settings = settings

    def section(self, view_type: type[Any]) -> Any:
        assert view_type is PlanningSettings
        return self._settings


def default_planning_settings() -> PlanningSettings:
    return PlanningSettings.from_json(
        {
            "validation": {
                "require_acceptance_links": False,
                "warn_unknown_skills": False,
                "warn_unknown_models": False,
                "external_checks": True,
                "external_failure": "warn",
                "code_suffixes": [".py", ".sql"],
                "heavy_check_markers": ["docker", "e2e"],
                "heavy_text_bytes": 4096,
            },
            "references": {"max_supersede_chain": 8},
            "design_audit": "none",
            "defaults": {"route_class": "implementation", "route_effort": "high", "review_mode": "required"},
            "drafts": {"max_document_bytes": 8388608, "max_open": 20},
            "aliases": {"prefix": "PLAN"},
            "display": {"tree_depth": 3},
        }
    )


def strict_planning_settings() -> PlanningSettings:
    """Acceptance links required, external checks off: the read-facade and service-review defaults."""
    return PlanningSettings.from_json(
        {
            "validation": {
                "require_acceptance_links": True,
                "warn_unknown_skills": False,
                "warn_unknown_models": False,
                "external_checks": False,
                "external_failure": "warn",
                "code_suffixes": [".py"],
                "heavy_check_markers": [],
                "heavy_text_bytes": 16384,
            },
            "references": {"max_supersede_chain": 8},
            "design_audit": "none",
            "defaults": {"route_class": "implementation", "route_effort": "high", "review_mode": "required"},
            "drafts": {"max_document_bytes": 8388608, "max_open": 20},
            "aliases": {"prefix": "PLAN"},
            "display": {"tree_depth": 3},
        }
    )


def req_meta(h: Harness, seq: int) -> RequestMeta:
    return RequestMeta(f"req_{seq:026d}", Surface.CLI, None, h.clock.now())


def make_prepare_ctx(
    uow: UnitOfWork, h: Harness, plan_id: PlanId, *, actor: Actor | None = None, seq: int = 900
) -> CommandContext:
    """A plan-scoped command context for calling ``publication_candidate.prepare`` directly."""
    scope = ScopeRef(ScopeKind.PLAN, ScopeId(plan_id))
    return CommandContext(
        actor=h.owner if actor is None else actor,
        meta=req_meta(h, seq),
        scope=scope,
        scope_chain=uow.repo(ScopeRegistry).ancestors(scope.id),
        clock=h.clock,
        ids=SequentialIds(),
        entropy=DeterministicEntropy(),
        config=cast("Any", StaticPlanningConfig(default_planning_settings())),
        log=cast("Any", object()),
        gateways=GatewayTable({}, "control_plane_gateway"),
    )


def upload_v1(
    h: Harness,
    data: bytes,
    *,
    filename: str = "spec.txt",
    title: str | None = None,
    ws: WorkspaceId | None = None,
    proj: ProjectId | None = None,
) -> tuple[UUID, FileVersionId]:
    """Upload a new text file; the title defaults to ``filename``, the target to the harness project."""
    target_ws = h.ws if ws is None else ws
    target_proj = h.proj if proj is None else proj
    staged = h.client.upload_blob(target_ws, [data], size=len(data), media_type="text/plain")
    dto = replace(
        add_file_dto(target_ws, target_proj, staged),
        title=filename if title is None else title,
        original_filename=filename,
    )
    res = dispatch_new(h.client, dto)
    return UUID(str(res.file_id)), FileVersionId(UUID(str(res.file_version_id)))


def upload_next_version(
    h: Harness, file_id: UUID, expected_row_version: int, data: bytes, *, filename: str = "spec-v2.txt"
) -> FileVersionId:
    staged = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    blob_ref = art_cmds.AddFileVersionDefsStagedBlobRef(
        staged.staged_blob_id, staged.workspace_id, staged.digest, staged.size, staged.media_type
    )
    res = dispatch_new(
        h.client,
        artifacts.AddFileVersion(
            file_id=file_id,
            expected_row_version=expected_row_version,
            blob=blob_ref,
            original_filename=filename,
            declared_media_type="text/plain",
            source=art_cmds.AddFileVersionDefsVersionSource(kind="upload"),
        ),
    )
    return FileVersionId(UUID(str(res.file_version_id)))
