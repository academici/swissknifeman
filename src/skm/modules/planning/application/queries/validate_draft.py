"""``planning.validate_draft`` (planning §8, C10): validate saved or submitted draft document."""

from __future__ import annotations

import contextlib
import copy
from functools import cache
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.source_reader import require_plan
from skm.modules.planning.application.validation_context import build_validation_context
from skm.modules.planning.domain import draft as draft_rules
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.identity import assign_missing_ids, iter_entities
from skm.modules.planning.domain.material import MaterialKind
from skm.modules.planning.domain.specification import SPECIFICATION_URN, from_document
from skm.modules.planning.domain.validation.findings import Severity
from skm.modules.planning.domain.validation.pipeline import validate
from skm.modules.planning.generated.queries import ValidateDraft
from skm.modules.planning.generated.settings import PlanningSettings
from skm.modules.planning.generated.views import (
    ValidationReportView,
    ValidationReportViewCounts,
    ValidationReportViewFindingsItem,
    ValidationReportViewGraphVariant1,
    ValidationReportViewRuleFailuresItem,
    ValidationReportViewSchemaIssuesItem,
)
from skm.modules.planning.ports import DraftRepository
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle", "scope_of"]

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}


@cache
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


class _SyntheticIdGenerator:
    def __init__(self, taken: set[UUID]) -> None:
        self._seq = 0
        self._taken = taken

    def new_id(self) -> UUID:
        while True:
            self._seq += 1
            candidate = UUID(f"0195f0ff-ffff-7000-8000-{self._seq:012x}")
            if candidate not in self._taken:
                self._taken.add(candidate)
                return candidate


def _taken_entity_ids(doc: JsonObject) -> set[UUID]:
    taken: set[UUID] = set()
    for _kind, _pos, ent in iter_entities(doc):
        raw_id = ent.get("id")
        if isinstance(raw_id, str):
            with contextlib.suppress(ValueError):
                taken.add(UUID(raw_id))
    return taken


def scope_of(query: ValidateDraft) -> ScopeRef:
    return ScopeRef(ScopeKind.PLAN, ScopeId(query.plan_id))


def handle(query: ValidateDraft, ctx: QueryContext, uow: UnitOfWork) -> ValidationReportView:
    plan = require_plan(uow, query.plan_id)
    draft = uow.repo(DraftRepository).get(DraftId(query.draft_id))
    draft_rules.require_in_plan(draft, plan.id)
    if draft.workspace_id != plan.workspace_id:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "draft not found",
            details={"kind": "draft", "ref": str(query.draft_id)},
        )
    draft_rules.require_edit_version(draft, query.expected_edit_version)

    try:
        min_sev = Severity(query.min_severity)
    except ValueError as err:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid min_severity",
            details={"field": "min_severity"},
        ) from err

    stale = draft.base_revision_id != plan.current_revision_id
    is_open = draft.state is DraftState.OPEN

    if query.document is None:
        source_kind = "saved"
        candidate_doc = copy.deepcopy(draft.document)
    else:
        source_kind = "submitted"
        raw_submitted = cast("JsonObject", copy.deepcopy(dict(query.document)))
        candidate_doc, _ = assign_missing_ids(
            raw_submitted, _SyntheticIdGenerator(_taken_entity_ids(raw_submitted))
        )

    raw_issues = _schemas().validate(SPECIFICATION_URN, candidate_doc)
    if raw_issues:
        schema_issues = tuple(
            ValidationReportViewSchemaIssuesItem(
                pointer=issue.pointer,
                message=issue.message,
                schema_pointer=issue.schema_pointer,
            )
            for issue in raw_issues
        )
        return ValidationReportView(
            draft_id=draft.id,
            edit_version=draft.edit_version,
            source=source_kind,
            document_digest=None,
            schema_issues=schema_issues,
            findings=(),
            rule_failures=(),
            counts=ValidationReportViewCounts(error=0, warning=0, info=0),
            publishable=False,
            graph=None,
            stale=stale,
        )

    normalized_doc = normalize_document(candidate_doc)
    digest = specification_digest(normalized_doc)
    spec, _ = from_document(normalized_doc)
    default_scope = ScopeRef(ScopeKind.PROJECT, ScopeId(plan.project_id))
    for material in spec.materials:
        if material.kind is MaterialKind.FILE_VERSION and material.file_version_id is not None:
            artifacts.require_version_read(
                uow,
                ctx.actor,
                ctx.clock,
                material.file_version_id,
                default_scope=default_scope,
            )
    settings = ctx.config.section(PlanningSettings)
    vctx = build_validation_context(
        uow,
        ctx,
        plan,
        spec=spec,
        document=normalized_doc,
        settings=settings,
        now=ctx.clock.now(),
    )
    report = validate(vctx)
    counts = report.counts()
    plugin_failures_block = settings.validation.external_failure.value == "error"
    has_errors = report.has_errors(plugin_failures_block=plugin_failures_block)

    graph_view: ValidationReportViewGraphVariant1 | None = None
    try:
        compiled = compile_execution_graph(spec)
        graph_view = ValidationReportViewGraphVariant1(
            tasks=len(compiled.tasks),
            edges=len(compiled.edges),
        )
    except SkmError:
        graph_view = None

    min_rank = _SEVERITY_RANK[min_sev]
    findings = tuple(
        ValidationReportViewFindingsItem(
            code=f.code,
            severity=f.severity.value,
            message=f.message,
            entity_key=f.entity_key,
            entity_id=f.entity_id,
            pointer=f.pointer,
            details=dict(f.details),
        )
        for f in report.findings
        if _SEVERITY_RANK[f.severity] >= min_rank
    )
    rule_failures = tuple(
        ValidationReportViewRuleFailuresItem(
            rule=rf.rule,
            error_type=rf.error_type,
            message=rf.message,
            plugin=rf.plugin,
        )
        for rf in report.rule_failures
    )
    publishable = is_open and not stale and not has_errors

    return ValidationReportView(
        draft_id=draft.id,
        edit_version=draft.edit_version,
        source=source_kind,
        document_digest=digest,
        schema_issues=(),
        findings=findings,
        rule_failures=rule_failures,
        counts=ValidationReportViewCounts(
            error=counts[Severity.ERROR],
            warning=counts[Severity.WARNING],
            info=counts[Severity.INFO],
        ),
        publishable=publishable,
        graph=graph_view,
        stale=stale,
    )


SPEC = QuerySpec(
    name="planning.validate_draft",
    dto=ValidateDraft,
    result=ValidationReportView,
    permission="plan.read",
    scope_of=scope_of,
    handler=handle,
)
