"""Register one consumed piece of worker evidence as a file version of the fenced attempt."""

from typing import Any
from uuid import UUID

from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts


def register(uow: UnitOfWork, ctx: Any, fenced: Any, item: Any, *, consumed: Any = None) -> Any:
    consumed = consumed or artifacts.consume_staged_blob(
        uow,
        ref=item["staged_blob"],
        workspace_id=fenced.run.workspace_id,
        request_id=ctx.meta.request_id,
        now=fenced.now,
    )
    safety = artifacts.scan_document({"filename": item["filename"]}, artifacts.build_safety_rules(ctx.config))
    role = item["role"]
    origin = {"patch": artifacts.FileOrigin.PATCH, "transcript": artifacts.FileOrigin.TRANSCRIPT}.get(
        role, artifacts.FileOrigin.EVIDENCE
    )
    registered = artifacts.register_file_version(
        uow,
        workspace_id=fenced.run.workspace_id,
        project_id=fenced.run.project_id,
        title=f"{role} for attempt {fenced.attempt.id}",
        origin=origin,
        staged=consumed,
        original_filename=item["filename"],
        media_type=item["media_type"],
        source=artifacts.VersionSource("generated", f"attempt:{fenced.attempt.id}", fenced.now),
        classification=artifacts.Classification(ctx.config.get("artifacts.default_classification"))
        if safety.verdict() == "ok"
        else artifacts.Classification.RESTRICTED,
        safety=safety,
        created_by=ctx.actor.principal_id,
        ids=ctx.ids,
        now=fenced.now,
    )
    return UUID(str(registered["file_version_id"]))
