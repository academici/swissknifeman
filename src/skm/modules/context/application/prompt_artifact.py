"""Publish one staged prompt under the finalizer's live manifest owner guard and transaction."""

from skm.application_bus.context import CommandContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import FileVersionId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.context.domain.manifest import ContextManifest


def publish_staged_prompt(
    uow: UnitOfWork, ctx: CommandContext, manifest: ContextManifest, ref: JsonObject, expected_digest: str
) -> FileVersionId:
    staged = artifacts.consume_staged_blob(
        uow, ref=ref, workspace_id=manifest.workspace_id, request_id=ctx.meta.request_id, now=ctx.clock.now()
    )
    if staged.digest.value != expected_digest:
        raise error_for(ErrorCode.BLOB_DIGEST_MISMATCH, "staged prompt digest differs from final render")
    safety = artifacts.scan_document({"filename": "prompt.txt"}, artifacts.build_safety_rules(ctx.config))
    registered = artifacts.register_file_version(
        uow,
        workspace_id=manifest.workspace_id,
        project_id=manifest.project_id,
        title=f"Prompt for {manifest.id}",
        origin=artifacts.FileOrigin.EVIDENCE,
        staged=staged,
        original_filename="prompt.txt",
        media_type="text/plain",
        source=artifacts.VersionSource("generated", manifest.owner_ref, ctx.clock.now()),
        classification=artifacts.Classification(ctx.config.get("artifacts.default_classification"))
        if safety.verdict() == "ok"
        else artifacts.Classification.RESTRICTED,
        safety=safety,
        created_by=ctx.actor.principal_id,
        ids=ctx.ids,
        now=ctx.clock.now(),
    )
    from uuid import UUID

    return FileVersionId(UUID(str(registered["file_version_id"])))
