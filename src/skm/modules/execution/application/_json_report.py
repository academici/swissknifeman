"""Retain a generated JSON report as a file version bound to the current attempt, in the caller's UoW."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.ports import EvidenceBindingRepository

__all__ = ["retain_json_document", "retain_json_report"]


def retain_json_report(
    uow: UnitOfWork, ctx: Any, state: Any, document: JsonObject, *, title: str, filename: str, source_ref: str
) -> FileVersionId:
    version_id = retain_json_document(
        uow,
        ctx,
        (state.run.workspace_id, state.run.project_id),
        document,
        title=title,
        filename=filename,
        source_ref=source_ref,
        origin=artifacts.FileOrigin.REPORT,
    )
    uow.repo(EvidenceBindingRepository).bind(
        "attempt", state.attempt.id, (version_id,), artifacts.BindingRole.EVIDENCE
    )
    return version_id


def retain_json_document(
    uow: UnitOfWork,
    ctx: CommandContext,
    scope: tuple[WorkspaceId, ProjectId],
    document: JsonObject,
    *,
    title: str,
    filename: str,
    source_ref: str,
    origin: artifacts.FileOrigin,
) -> FileVersionId:
    """Scan and retain a generated JSON document in the caller's unit of work."""
    workspace_id, project_id = scope
    data = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    safety = artifacts.scan_document(document, artifacts.build_safety_rules(ctx.config))
    classification = artifacts.Classification(ctx.config.get("artifacts.default_classification"))
    if safety.verdict() != "ok":
        classification = artifacts.Classification.RESTRICTED
    store = ctx.gateways.get(artifacts.BlobStore)
    coordination = ctx.gateways.get(artifacts.BlobCoordination)
    staged = store.stage(workspace_id, (data,))
    with coordination.hold(
        workspace_id,
        artifacts.ContentDigest(staged.digest),
        str(ctx.config.get("artifacts.blobs.backend")),
    ):
        location = store.promote(staged, expected_digest=staged.digest)
        recorded = artifacts.record_staged_blob(
            artifacts.RecordStagedBlob(
                workspace_id=workspace_id,
                digest=staged.digest,
                size=staged.size_bytes,
                media_type="application/json",
                detected_media_type="application/json",
                backend_id=str(location["backend_id"]),
                storage_key=str(location["storage_key"]),
            ),
            ctx,
            uow,
        )
        now = ctx.clock.now()
        consumed = artifacts.consume_staged_blob(
            uow,
            ref=recorded.to_json(),
            workspace_id=workspace_id,
            request_id=ctx.meta.request_id,
            now=now,
        )
        ref = artifacts.register_file_version(
            uow,
            workspace_id=workspace_id,
            project_id=project_id,
            title=title,
            origin=origin,
            staged=consumed,
            original_filename=filename,
            media_type="application/json",
            source=artifacts.VersionSource(kind="generated", ref=source_ref, captured_at=now),
            classification=classification,
            safety=safety,
            created_by=ctx.actor.principal_id,
            ids=ctx.ids,
            now=now,
        )
    return FileVersionId(UUID(str(ref["file_version_id"])))
