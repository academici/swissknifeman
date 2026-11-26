"""``planning.import_specification`` (planning §7.7): import a portable specification into a draft."""

from __future__ import annotations

import copy
import fnmatch
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from functools import cache
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import EntityId, FileVersionId, PlanId, ProjectId, RevisionId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.source_reader import require_revision_in_plan
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import document_bytes, normalize_document
from skm.modules.planning.domain.events import DraftOpened, PlanCreated
from skm.modules.planning.domain.identity import (
    assign_missing_ids,
    display_key_of,
    iter_entities,
    missing_existing_ids,
)
from skm.modules.planning.domain.plan import Plan
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.domain.validation.findings import Severity, pointer_of
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.commands import (
    ImportSpecification,
    ImportSpecificationDefsExportMeta,
    ImportSpecificationDefsExportMetaSourceVariant1,
    ImportSpecificationMaterialRebindItem,
)
from skm.modules.planning.generated.results import (
    ImportSpecificationResult,
    ImportSpecificationResultCounts,
    ImportSpecificationResultIdMapItem,
)
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import DraftRepository, PlanCounters, PlanRepository, RevisionRepository
from skm.modules.workspace import public as workspace
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "permissions_of", "scope_of"]

_MASK = "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}redacted\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"
_UNALLOCATED_VID = FileVersionId(UUID(int=0))


@cache
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def scope_of(cmd: ImportSpecification) -> ScopeRef:
    if cmd.mode == "new_draft" and cmd.plan_id is not None:
        return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))
    return ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id))


def permissions_of(cmd: ImportSpecification) -> tuple[str, ...]:
    return ("plan.edit",) if cmd.mode == "new_draft" else ("plan.create",)


def _schema_invalid(pointer: str, message: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        message,
        details={
            "issues": [{"pointer": pointer, "message": message, "schema_pointer": ""}],
            "applied": False,
        },
    )


def _validate_export_meta(cmd: ImportSpecification, meta: ImportSpecificationDefsExportMeta) -> None:
    src = meta.source
    expected_base: UUID | None = (
        src.revision_id
        if isinstance(src, ImportSpecificationDefsExportMetaSourceVariant1)
        else src.base_revision_id
    )

    if cmd.mode == "new_draft":
        if src.plan_id != cmd.plan_id:
            raise _schema_invalid(
                "/export_meta/source/plan_id", "export_meta.source.plan_id must match plan_id"
            )
        if expected_base != cmd.source_base_revision_id:
            raise _schema_invalid(
                "/export_meta/source",
                "export_meta source revision/base_revision_id must match source_base_revision_id",
            )


def _validate_dto_and_meta(cmd: ImportSpecification) -> None:
    if cmd.mode == "new_plan":
        if cmd.plan_id is not None or cmd.source_base_revision_id is not None:
            raise _schema_invalid("", "plan_id and source_base_revision_id are forbidden for new_plan")
        if cmd.title is not None and not (1 <= len(cmd.title.strip()) <= 300):
            raise _schema_invalid("/title", "title must be 1..300 characters after strip")
    elif cmd.mode == "new_draft":
        if cmd.plan_id is None:
            raise _schema_invalid("/plan_id", "plan_id is required for new_draft")
        if cmd.title is not None:
            raise _schema_invalid("/title", "title is forbidden for new_draft")
    else:
        raise _schema_invalid("/mode", "mode must be new_plan or new_draft")

    if cmd.export_meta is not None:
        _validate_export_meta(cmd, cmd.export_meta)


def _float_pointers(value: object, *path: str | int) -> Iterator[str]:
    if isinstance(value, float):
        yield pointer_of(*path)
    elif isinstance(value, Mapping):
        for name, member in cast("Mapping[str, object]", value).items():
            yield from _float_pointers(member, *path, name)
    elif isinstance(value, list | tuple):
        for index, member in enumerate(cast("list[object] | tuple[object, ...]", value)):
            yield from _float_pointers(member, *path, index)


def _require_canonical(document: JsonObject) -> None:
    pointers = list(_float_pointers(document))
    if pointers:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the document holds a float",
            details={
                "issues": [
                    {"pointer": p, "message": "a float has no canonical JSON form", "schema_pointer": ""}
                    for p in pointers
                ],
                "applied": False,
            },
        )


def _require_schema(document: JsonObject) -> None:
    try:
        _schemas().require_valid(SPECIFICATION_URN, document)
    except ValidationFailed as error:
        raise ValidationFailed(
            error.code, error.message, details={**error.details, "applied": False}
        ) from error


def _require_size(document: JsonObject, limit: int) -> None:
    if document_bytes(document) > limit:
        raise _schema_invalid("", f"document exceeds {limit} bytes")


def _iter_strings(value: JsonValue, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield pointer or "/", value
    elif isinstance(value, dict):
        for k, v in value.items():
            esc = k.replace("~", "~0").replace("/", "~1")
            yield from _iter_strings(v, f"{pointer}/{esc}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _iter_strings(item, f"{pointer}/{idx}")


def _require_portable_safety(ctx: CommandContext, document: JsonObject) -> None:
    rules = artifacts.build_safety_rules(ctx.config)
    report = artifacts.scan_document(document, rules)
    findings: list[JsonValue] = [f.to_json() for f in report.findings if str(f.level) == "block"]
    for pointer, text in _iter_strings(document):
        if not text:
            continue
        base = text.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        folded = unicodedata.normalize("NFKC", base).casefold()
        trimmed = folded.rstrip(". ")
        if not trimmed or any(ch.isspace() for ch in trimmed):
            continue
        candidates = {folded, trimmed}
        for glob in rules.secret_name_globs:
            if any(fnmatch.fnmatchcase(c, glob.casefold()) for c in candidates if c):
                findings.append(
                    {
                        "rule": "CS-SECRET-NAME",
                        "level": "block",
                        "detail": f"the file name is a secret file name ({glob}): {_MASK}",
                        "line": None,
                        "pointer": pointer,
                    }
                )
                break
    if report.verdict() == "block" or findings:
        raise ValidationFailed(
            ErrorCode.CONTENT_UNSAFE,
            "the content failed the content-safety rules",
            details={"reason": "portable_document_blocked", "findings": findings},
        )


def _apply_material_rebind(
    uow: UnitOfWork,
    ctx: CommandContext,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    proposed: JsonObject,
    rebinds: Sequence[ImportSpecificationMaterialRebindItem] | None,
) -> None:
    if not rebinds:
        return
    raw_materials = proposed.get("materials")
    if not isinstance(raw_materials, list):
        raise _schema_invalid("/material_rebind", "document has no materials to rebind")
    by_key: dict[str, dict[str, Any]] = {}
    for item in raw_materials:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            k = str(item["key"])
            by_key[k] = item
            by_key[f"material/{k}"] = item

    default_scope = ScopeRef(ScopeKind.PROJECT, ScopeId(project_id))
    seen_keys: set[str] = set()
    for idx, entry in enumerate(rebinds):
        target = by_key.get(entry.material_key)
        if target is None or target.get("kind") != "file_version":
            raise _schema_invalid(
                f"/material_rebind/{idx}/material_key",
                f"unknown file_version material key: {entry.material_key}",
            )
        canonical_key = str(target["key"])
        if canonical_key in seen_keys:
            raise _schema_invalid(
                f"/material_rebind/{idx}/material_key",
                f"duplicate material_rebind for {canonical_key}",
            )
        seen_keys.add(canonical_key)
        vid = FileVersionId(entry.file_version_id)
        try:
            artifacts.file_id_of_version(uow, workspace_id, vid)
        except NotFound:
            artifacts.require_version_read(
                uow,
                ctx.actor,
                ctx.clock,
                _UNALLOCATED_VID,
                default_scope=default_scope,
                reported_version_id=vid,
            )
            raise
        artifacts.require_version_read(uow, ctx.actor, ctx.clock, vid, default_scope=default_scope)
        view = artifacts.get_file_version(uow, vid)
        target["file_version_id"] = str(view.file_version_id)


def _workspace_plan_ids(uow: UnitOfWork, workspace_id: WorkspaceId, project_id: ProjectId) -> set[PlanId]:
    plans_repo = uow.repo(PlanRepository)
    scopes_repo = uow.repo(ScopeRegistry)
    projects: set[ProjectId] = {project_id}
    plan_ids: set[PlanId] = set()
    after: ScopeId | None = None
    while True:
        batch = scopes_repo.list_scopes(after=after, limit=500)
        if not batch:
            break
        for node in batch:
            if node.workspace_id == workspace_id:
                if node.kind is ScopeKind.PLAN:
                    plan_ids.add(PlanId(UUID(str(node.id))))
                elif node.kind is ScopeKind.PROJECT:
                    projects.add(ProjectId(UUID(str(node.id))))
        if len(batch) < 500:
            break
        after = batch[-1].id
    for proj_id in projects:
        plan_ids.update(plans_repo.project_plan_refs(proj_id).values())
        rev_req = plans_repo.find_review_requests_plan(proj_id)
        if rev_req is not None:
            plan_ids.add(rev_req.id)
    return plan_ids


def _collect_foreign_entity_ids(
    uow: UnitOfWork,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    target_plan_id: PlanId | None,
    export_meta: ImportSpecificationDefsExportMeta | None,
) -> set[EntityId]:
    plans_repo = uow.repo(PlanRepository)
    candidate_plans = _workspace_plan_ids(uow, workspace_id, project_id)
    if export_meta is not None:
        candidate_plans.add(PlanId(export_meta.source.plan_id))
    if target_plan_id is not None:
        candidate_plans.discard(target_plan_id)

    revs_repo = uow.repo(RevisionRepository)
    drafts_repo = uow.repo(DraftRepository)
    foreign: set[EntityId] = set()
    for pid in candidate_plans:
        try:
            plan = plans_repo.get(pid)
        except NotFound:
            continue
        if plan.workspace_id != workspace_id:
            continue
        foreign.update(revs_repo.identities(pid).keys())
        for d in drafts_repo.list_for_plan(pid, state=None):
            for _kind, _idx, ent in iter_entities(d.document):
                raw_id = ent.get("id")
                if isinstance(raw_id, str):
                    try:
                        foreign.add(EntityId(UUID(raw_id)))
                    except ValueError:
                        continue
    return foreign


def _resolve_identities(
    uow: UnitOfWork,
    ctx: CommandContext,
    cmd: ImportSpecification,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    target_plan_id: PlanId | None,
    proposed: JsonObject,
) -> tuple[JsonObject, tuple[ImportSpecificationResultIdMapItem, ...]]:
    if not cmd.keep_ids:
        remapped = copy.deepcopy(proposed)
        id_map: list[ImportSpecificationResultIdMapItem] = []
        for kind, _index, entity in iter_entities(remapped):
            raw_old = entity.get("id")
            old_uuid: UUID | None = None
            if isinstance(raw_old, str):
                try:
                    old_uuid = UUID(raw_old)
                except ValueError as err:
                    raise _schema_invalid("/id", "invalid entity UUID") from err
            new_uuid = ctx.ids.new_id()
            entity["id"] = str(new_uuid)
            id_map.append(
                ImportSpecificationResultIdMapItem(
                    entity_kind=kind.value,
                    key=display_key_of(kind, entity),
                    old_id=old_uuid,
                    new_id=new_uuid,
                )
            )
        return remapped, tuple(id_map)

    if cmd.mode == "new_draft" and cmd.source_base_revision_id is not None:
        base_doc = uow.repo(RevisionRepository).get_document(RevisionId(cmd.source_base_revision_id))
        pointers = missing_existing_ids(base_doc, proposed)
        if pointers:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "an existing entity lost its id",
                details={
                    "issues": [
                        {"pointer": p, "message": "existing entity id required", "schema_pointer": ""}
                        for p in pointers
                    ],
                    "applied": False,
                },
            )

    foreign_ids = _collect_foreign_entity_ids(uow, workspace_id, project_id, target_plan_id, cmd.export_meta)
    conflicting: list[str] = []
    for _kind, _index, entity in iter_entities(proposed):
        raw_id = entity.get("id")
        if isinstance(raw_id, str):
            try:
                eid = EntityId(UUID(raw_id))
            except ValueError as err:
                raise _schema_invalid("/id", "invalid entity UUID") from err
            if eid in foreign_ids and str(eid) not in conflicting:
                conflicting.append(str(eid))
    if conflicting:
        entity_ids_json: list[JsonValue] = [*sorted(conflicting)]
        raise Conflict(
            ErrorCode.ID_CONFLICT,
            "an entity id belongs to another plan; retry with keep_ids=false",
            details={"entity_ids": entity_ids_json, "hint": "keep_ids=false"},
        )

    with_ids, _ = assign_missing_ids(proposed, ctx.ids)
    return with_ids, ()


def _prepare_target_plan(
    uow: UnitOfWork,
    cmd: ImportSpecification,
    project_id: ProjectId,
    settings: PlanningSettings,
) -> tuple[Plan | None, RevisionId | None]:
    if cmd.mode == "new_plan" or cmd.plan_id is None:
        return None, None
    plan = uow.repo(PlanRepository).lock(PlanId(cmd.plan_id))
    if plan.project_id != project_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "plan not found",
            details={"kind": "plan", "ref": str(cmd.plan_id)},
        )
    plan_rules.require_editable(plan)
    open_drafts = uow.repo(DraftRepository).count_open(plan.id)
    limit = settings.drafts.max_open
    if open_drafts >= limit:
        raise Conflict(
            ErrorCode.ALREADY_EXISTS,
            "the plan has as many open drafts as it may have",
            details={"open_drafts": open_drafts, "limit": limit},
        )
    base_rev_id: RevisionId | None = None
    if cmd.source_base_revision_id is not None:
        base_rev_id = RevisionId(cmd.source_base_revision_id)
        meta = uow.repo(RevisionRepository).get_meta(base_rev_id)
        require_revision_in_plan(meta, plan.id)
    return plan, base_rev_id


def handle(cmd: ImportSpecification, ctx: CommandContext, uow: UnitOfWork) -> ImportSpecificationResult:
    _validate_dto_and_meta(cmd)
    project_id = ProjectId(cmd.project_id)
    workspace.require_active_project(uow, project_id)
    project = workspace.get_project(uow, project_id)
    workspace_id = WorkspaceId(project.workspace_id)
    settings = ctx.config.section(PlanningSettings)

    plan, base_revision_id = _prepare_target_plan(uow, cmd, project_id, settings)
    target_plan_id = None if plan is None else plan.id

    proposed = cast("JsonObject", copy.deepcopy(dict(cmd.document)))
    if cmd.mode == "new_plan":
        proposed.pop("design_brief_id", None)
    _require_canonical(proposed)
    _require_schema(proposed)
    _apply_material_rebind(uow, ctx, workspace_id, project_id, proposed, cmd.material_rebind)
    with_ids, id_map = _resolve_identities(uow, ctx, cmd, workspace_id, project_id, target_plan_id, proposed)
    _require_schema(with_ids)
    _require_canonical(with_ids)
    _require_size(with_ids, settings.drafts.max_document_bytes)
    _require_portable_safety(ctx, with_ids)
    document = normalize_document(with_ids)

    now = ctx.clock.now()
    actor_id = ctx.actor.principal_id
    if plan is None:
        effective_title = cmd.title if cmd.title is not None else str(document["title"])
        plan_no = uow.repo(PlanCounters).allocate_plan_no(workspace_id, project_id)
        plan = plan_rules.new_plan(
            PlanId(ctx.ids.new_id()),
            project,
            f"{settings.aliases.prefix}{plan_no}",
            effective_title,
            actor_id,
            now,
        )
        uow.repo(ScopeRegistry).create(
            ScopeId(plan.id), ScopeKind.PLAN, parent=ScopeId(project_id), workspace_id=plan.workspace_id
        )
        uow.repo(PlanRepository).add(plan)
        uow.record(
            PlanCreated(
                plan_id=plan.id,
                workspace_id=plan.workspace_id,
                project_id=plan.project_id,
                alias=plan.alias,
                title=plan.title,
                purpose=plan.purpose,
            )
        )

    draft = draft_rules.open_draft(
        draft_rules.DraftId(ctx.ids.new_id()),
        plan,
        base_revision_id,
        document,
        actor_id,
        now,
    )
    uow.repo(DraftRepository).add(draft)
    uow.record(
        DraftOpened(
            plan_id=plan.id,
            workspace_id=plan.workspace_id,
            draft_id=draft.id,
            base_revision_id=base_revision_id,
            source="import",
            edit_version=draft.edit_version,
        )
    )

    val_ctx = build_validation_context(uow, ctx, plan, document=document, settings=settings, now=now)
    report = validate(val_ctx)
    counts = report.counts()
    stale = draft.base_revision_id != plan.current_revision_id
    return ImportSpecificationResult(
        plan_id=plan.id,
        alias=plan.alias,
        draft_id=draft.id,
        edit_version=draft.edit_version,
        base_revision_id=draft.base_revision_id,
        stale=stale,
        id_map=id_map,
        counts=ImportSpecificationResultCounts(
            error=counts[Severity.ERROR],
            warning=counts[Severity.WARNING],
            info=counts[Severity.INFO],
        ),
    )


SPEC = CommandSpec(
    name="planning.import_specification",
    dto=ImportSpecification,
    result=ImportSpecificationResult,
    permission="plan.read",
    permissions_of=permissions_of,
    scope_of=scope_of,
    idempotency=IdempotencyMode.REQUIRED,
    handler=handle,
)
