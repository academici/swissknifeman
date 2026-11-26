"""``planning.save_draft`` (planning §7.3): replace, merge-patch or batch-edit an open draft.

The draft is locked alone (no plan lock after a draft lock, §7.10), state and version are checked before any
work on the document. Anything refused leaves the draft as it was: a schema-invalid result, a float, an
oversized result, a changed owned field, a batch that fails at any operation. A semantically invalid document
is saved; its findings only come back in the result and block a publication later (I6).

A full document and a root merge patch replace entity arrays as a whole, so they could lose an identity by
leaving out one ``id``. Such an entity is refused before ids are issued (§5.2), and its old id is never
guessed. An explicit other id and the ``remove`` + ``add`` of a batch stay deliberate rebuilds.

The findings come from ``build_validation_context``, the same context ``validate_draft`` and the
publication preview use, so a saved draft reports exactly what would block or warn its publication.
Extension namespaces are stored as they are: no plugin registers one yet.
"""

import copy
from collections.abc import Iterable, Iterator, Mapping
from functools import cache
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import PlanId, ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain import plan as plan_rules
from skm.modules.planning.domain.canonical import document_bytes, normalize_document, specification_digest
from skm.modules.planning.domain.changes import (
    AddChange,
    DraftChange,
    ItemDefaults,
    MoveChange,
    PatchChange,
    RekeyChange,
    RemoveChange,
    ReplaceTextChange,
    apply_changes,
    merge_patch,
)
from skm.modules.planning.domain.draft import Draft
from skm.modules.planning.domain.events import DraftSaved
from skm.modules.planning.domain.identity import assign_missing_ids, missing_existing_ids
from skm.modules.planning.domain.item import Effort, ModelClass
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.domain.specification import (
    SPECIFICATION_URN,
    EntityKind,
)
from skm.modules.planning.domain.validation.findings import Severity, ValidationReport, pointer_of
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.commands import (
    SaveDraft,
    SaveDraftDefsDraftChange,
    SaveDraftDefsDraftChangeVariant1,
    SaveDraftDefsDraftChangeVariant2,
    SaveDraftDefsDraftChangeVariant3,
    SaveDraftDefsDraftChangeVariant4,
    SaveDraftDefsDraftChangeVariant5,
)
from skm.modules.planning.generated.results import (
    SaveDraftResult,
    SaveDraftResultAssignedIdsItem,
    SaveDraftResultCounts,
    SaveDraftResultFindingsItem,
    SaveDraftResultRuleFailuresItem,
)
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.ports import DraftRepository, PlanRepository
from skm.modules.workspace import public as workspace
from skm.platform.schema.registry import SchemaRegistry

__all__ = ["SPEC", "handle", "scope_of"]


@cache
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def scope_of(cmd: SaveDraft) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(cmd.plan_id))


def _domain_change(change: SaveDraftDefsDraftChange) -> DraftChange:
    match change:
        case SaveDraftDefsDraftChangeVariant1():
            return PatchChange(change.target, cast("JsonObject", dict(change.merge_patch)))
        case SaveDraftDefsDraftChangeVariant2():
            kind = "plan_relation" if change.kind == "plan_relation" else EntityKind(change.kind)
            return AddChange(kind, cast("JsonObject", dict(change.entity)), change.after)
        case SaveDraftDefsDraftChangeVariant3():
            return RemoveChange(change.target, bool(change.cascade))
        case SaveDraftDefsDraftChangeVariant4():
            return MoveChange(change.target, change.after, change.before)
        case SaveDraftDefsDraftChangeVariant5():
            return RekeyChange(change.target, change.new_key)
        case _:
            return ReplaceTextChange(
                change.target, change.pointer, change.expected_text_digest, change.old_text, change.new_text
            )


def _item_defaults(settings: PlanningSettings) -> ItemDefaults:
    defaults = settings.defaults
    return ItemDefaults(
        ModelClass(defaults.route_class.value),
        Effort(defaults.route_effort.value),
        ReviewMode(defaults.review_mode.value),
    )


def _patched_root(draft: Draft, patch: JsonObject) -> JsonObject:
    """RFC 7396 at the root: the only owned member is ``schema``; leaving it as it is changes nothing."""
    if "schema" in patch and patch["schema"] != draft.document.get("schema"):
        raise ValidationFailed(
            ErrorCode.FIELD_OWNED, "field is owned", details={"target": "plan", "field": "schema"}
        )
    return cast("JsonObject", merge_patch(draft.document, patch))


def _require_existing_ids(draft: Draft, proposed: JsonObject) -> None:
    pointers = missing_existing_ids(draft.document, proposed)
    if pointers:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "an existing entity lost its id",
            details={
                "issues": [
                    {"pointer": pointer, "message": "existing entity id required", "schema_pointer": ""}
                    for pointer in pointers
                ],
                "applied": False,
            },
        )


def _proposed_document(
    cmd: SaveDraft, draft: Draft, settings: PlanningSettings
) -> tuple[JsonObject, tuple[str, ...]]:
    """The new document before ids are issued, and the notes of a batch."""
    if cmd.changes is not None:
        changes = [_domain_change(change) for change in cmd.changes]
        outcome = apply_changes(draft.document, changes, defaults=_item_defaults(settings))
        return outcome.document, outcome.notes
    if cmd.document is not None:
        proposed = cast("JsonObject", copy.deepcopy(cmd.document))
    else:
        proposed = _patched_root(draft, cast("JsonObject", dict(cmd.merge_patch or {})))
    _require_existing_ids(draft, proposed)
    return proposed, ()


def _require_schema(document: JsonObject) -> None:
    try:
        _schemas().require_valid(SPECIFICATION_URN, document)
    except ValidationFailed as error:
        raise ValidationFailed(
            error.code, error.message, details={**error.details, "applied": False}
        ) from error


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
    """Canonical JSON has no floats (§5.6), but the schema passes one in ``extensions`` or as an integer."""
    pointers = list(_float_pointers(document))
    if pointers:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the document holds a float",
            details={
                "issues": [
                    {
                        "pointer": pointer,
                        "message": "a float has no canonical JSON form",
                        "schema_pointer": "",
                    }
                    for pointer in pointers
                ],
                "applied": False,
            },
        )


def _require_size(document: JsonObject, limit: int) -> None:
    if document_bytes(document) > limit:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "the document is too large",
            details={
                "issues": [
                    {"pointer": "", "message": f"document exceeds {limit} bytes", "schema_pointer": ""}
                ],
                "applied": False,
            },
        )


def _findings(report: ValidationReport) -> Iterable[SaveDraftResultFindingsItem]:
    for found in report.findings:
        yield SaveDraftResultFindingsItem(
            code=found.code,
            severity=found.severity.value,
            message=found.message,
            entity_key=found.entity_key,
            entity_id=found.entity_id,
            pointer=found.pointer,
            details=found.details,
        )


def _rule_failures(report: ValidationReport) -> Iterable[SaveDraftResultRuleFailuresItem]:
    for failure in report.rule_failures:
        yield SaveDraftResultRuleFailuresItem(
            rule=failure.rule, error_type=failure.error_type, message=failure.message, plugin=failure.plugin
        )


def handle(cmd: SaveDraft, ctx: CommandContext, uow: UnitOfWork) -> SaveDraftResult:
    drafts = uow.repo(DraftRepository)
    draft = drafts.lock(draft_rules.DraftId(cmd.draft_id))
    draft_rules.require_in_plan(draft, PlanId(cmd.plan_id))
    draft_rules.require_open(draft)
    draft_rules.require_edit_version(draft, cmd.expected_edit_version)
    plan = uow.repo(PlanRepository).get(draft.plan_id)
    plan_rules.require_editable(plan)
    workspace.require_active_project(uow, plan.project_id)
    settings = ctx.config.section(PlanningSettings)

    proposed, notes = _proposed_document(cmd, draft, settings)
    with_ids, assigned = assign_missing_ids(proposed, ctx.ids)
    _require_schema(with_ids)
    _require_canonical(with_ids)
    _require_size(with_ids, settings.drafts.max_document_bytes)
    document = normalize_document(with_ids)

    saved = draft_rules.save(
        draft, document, cmd.expected_edit_version, ctx.actor.principal_id, ctx.clock.now()
    )
    drafts.save(saved, expected_edit_version=cmd.expected_edit_version)

    report = validate(build_validation_context(uow, ctx, plan, document=document, settings=settings))
    counts = report.counts()
    digest = specification_digest(document)
    uow.record(
        DraftSaved(
            plan_id=draft.plan_id,
            workspace_id=draft.workspace_id,
            draft_id=draft.id,
            edit_version=saved.edit_version,
            document_digest=digest,
            error_count=counts[Severity.ERROR],
            warning_count=counts[Severity.WARNING],
            info_count=counts[Severity.INFO],
        )
    )
    return SaveDraftResult(
        draft_id=draft.id,
        edit_version=saved.edit_version,
        document_digest=digest,
        assigned_ids=tuple(
            SaveDraftResultAssignedIdsItem(
                entity_kind=item.entity_kind.value, display_key=item.key, entity_id=item.entity_id
            )
            for item in assigned
        ),
        notes=notes,
        findings=tuple(_findings(report)),
        counts=SaveDraftResultCounts(
            error=counts[Severity.ERROR], warning=counts[Severity.WARNING], info=counts[Severity.INFO]
        ),
        rule_failures=tuple(_rule_failures(report)),
    )


SPEC = CommandSpec(
    name="planning.save_draft",
    dto=SaveDraft,
    result=SaveDraftResult,
    permission="plan.edit",
    scope_of=scope_of,
    idempotency=IdempotencyMode.OPTIONAL,
    handler=handle,
)
