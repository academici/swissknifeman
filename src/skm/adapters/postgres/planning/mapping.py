"""Shared row mappers and helpers of the planning PostgreSQL adapters (planning §6, §11)."""

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Final, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import to_jsonb
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import EntityId, PlanId, PrincipalId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.planning.domain.display_keys import parse_material_ref
from skm.modules.planning.domain.draft import Draft, DraftId, DraftState
from skm.modules.planning.domain.item import (
    Item,
    WorkPolicyOverride,
    work_policy_from_doc,
    work_policy_to_doc,
)
from skm.modules.planning.domain.member import MemberRef
from skm.modules.planning.domain.plan import Plan, PlanLifecycle, PlanPurpose
from skm.modules.planning.domain.reads import (
    ArtifactRead,
    ExternalSourceRead,
    MaterialRead,
    PlanEntityRead,
    Read,
    RepositoryPathRead,
    compact,
)
from skm.modules.planning.domain.review_requirement import (
    RequiredReview,
    SelfReview,
    WaivedReview,
)
from skm.modules.planning.domain.revision import RevisionMeta, RevisionOrigin
from skm.modules.planning.domain.specification import EntityKind, Specification
from skm.modules.planning.domain.unit import Unit
from skm.modules.planning.ports import SpecificationDoc

__all__ = [
    "CHECK_KEYS",
    "CRIT_KEYS",
    "DEC_KEYS",
    "ITEM_KEYS",
    "MAT_KEYS",
    "PHASE_KEYS",
    "UNIT_KEYS",
    "Row",
    "already_exists",
    "apply_ref_override",
    "build_ref_forms",
    "damaged",
    "dep_edge_rows",
    "draft_from_row",
    "field_owned",
    "member_ref_from_row",
    "not_found",
    "plan_from_row",
    "read_spec_row",
    "require_unchanged",
    "review_req_row",
    "revision_meta_from_row",
    "run",
    "topological_units",
    "work_policy_from_sql",
    "work_policy_to_sql",
    "zip_compact",
]

PHASE_KEYS: Final = (
    "id",
    "key",
    "title",
    "goal",
    "context_md",
    "design_state",
    "strategy",
    "contract",
    "scope",
    "pitfalls",
    "deliverables",
    "assurance",
    "supporting",
    "batches",
    "sections",
)
ITEM_KEYS: Final = (
    "id",
    "key",
    "phase",
    "title",
    "summary",
    "why",
    "work_kind",
    "unit_strategy",
    "route",
    "scope",
    "rules",
    "guidance_md",
    "deliverables",
    "depends_on",
    "relations",
    "implements",
    "decisions",
    "skills",
    "reads",
    "examples",
    "change_hints",
    "artifacts",
    "review",
    "authority",
    "research",
    "sections",
)
UNIT_KEYS: Final = (
    "id",
    "key",
    "title",
    "goal",
    "unit_kind",
    "work_kind",
    "mode",
    "route",
    "instructions_md",
    "command",
    "parent",
    "write_scope",
    "reads",
    "depends_on",
    "checks",
    "outputs",
    "implements",
    "sections",
)
CHECK_KEYS: Final = (
    "id",
    "key",
    "owner",
    "title",
    "kind",
    "category",
    "required",
    "rerun_after_integration",
    "definition",
    "evidence",
)
CRIT_KEYS: Final = ("id", "key", "owner", "statement", "verification_mode", "checks", "requirements")
DEC_KEYS: Final = (
    "id",
    "key",
    "title",
    "state",
    "date",
    "question",
    "options",
    "context_md",
    "decision",
    "rationale",
    "consequences",
    "applies_to",
    "global",
    "supersedes",
    "evidence",
    "origin",
    "answered_by",
    "sections",
)
MAT_KEYS: Final = (
    "id",
    "key",
    "title",
    "kind",
    "role",
    "why",
    "mount",
    "path",
    "url",
    "file_version_id",
    "retrieved_at",
    "content_digest",
    "selector",
    "required_for",
    "freshness",
    "applies_to",
    "global",
    "external_source_id",
)

type Row = tuple[object, ...]


def run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def damaged(table: str, row_id: object = None, cause: Exception | None = None) -> InternalError:
    suffix = "" if row_id is None else f" {row_id}"
    err = InternalError(ErrorCode.INTERNAL_ERROR, f"corrupt skm_planning.{table} row{suffix}")
    if cause is not None:
        err.__cause__ = cause
    return err


def not_found(kind: str, ref: object) -> NotFound:
    return NotFound(
        ErrorCode.NOT_FOUND,
        f"{kind} {ref!s} does not exist",
        details={"kind": kind, "ref": str(ref)},
    )


def already_exists(kind: str, **details: str) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS,
        f"{kind} already exists",
        details={"kind": kind, **details},
    )


def field_owned(kind: str, field: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.FIELD_OWNED,
        f"{kind}.{field} cannot be changed once created",
        details={"target": kind, "field": field},
    )


def require_unchanged(kind: str, current: object, updated: object, fields: tuple[str, ...]) -> None:
    for name in fields:
        if getattr(current, name) != getattr(updated, name):
            raise field_owned(kind, name)


def plan_from_row(row: Row) -> Plan:
    try:
        current_rev = cast("UUID | None", row[7])
        return Plan(
            id=PlanId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            project_id=ProjectId(cast("UUID", row[2])),
            alias=cast("str", row[3]),
            purpose=PlanPurpose(cast("str", row[4])),
            title=cast("str", row[5]),
            lifecycle=PlanLifecycle(cast("str", row[6])),
            current_revision_id=None if current_rev is None else RevisionId(current_rev),
            next_revision_no=cast("int", row[8]),
            row_version=cast("int", row[9]),
            created_by=PrincipalId(cast("UUID", row[10])),
            created_at=cast("datetime", row[11]),
            updated_at=cast("datetime", row[12]),
            archived_at=cast("datetime | None", row[13]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("plans", row[0], exc) from exc


def draft_from_row(row: Row) -> Draft:
    try:
        base_rev = cast("UUID | None", row[3])
        pub_rev = cast("UUID | None", row[7])
        doc = cast("SpecificationDoc", deepcopy(row[5]))
        return Draft(
            id=DraftId(cast("UUID", row[0])),
            plan_id=PlanId(cast("UUID", row[1])),
            workspace_id=WorkspaceId(cast("UUID", row[2])),
            base_revision_id=None if base_rev is None else RevisionId(base_rev),
            edit_version=cast("int", row[4]),
            document=doc,
            state=DraftState(cast("str", row[6])),
            published_revision_id=None if pub_rev is None else RevisionId(pub_rev),
            created_by=PrincipalId(cast("UUID", row[8])),
            created_at=cast("datetime", row[9]),
            updated_by=PrincipalId(cast("UUID", row[10])),
            updated_at=cast("datetime", row[11]),
            closed_at=cast("datetime | None", row[12]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("plan_drafts", row[0], exc) from exc


def revision_meta_from_row(row: Row) -> RevisionMeta:
    try:
        parent_rev = cast("UUID | None", row[4])
        restored_rev = cast("UUID | None", row[10])
        return RevisionMeta(
            id=RevisionId(cast("UUID", row[0])),
            plan_id=PlanId(cast("UUID", row[1])),
            workspace_id=WorkspaceId(cast("UUID", row[2])),
            revision_no=cast("int", row[3]),
            parent_revision_id=None if parent_rev is None else RevisionId(parent_rev),
            schema_version=cast("int", row[5]),
            content_digest=cast("str", row[6]),
            canonicalization_version=cast("int", row[7]),
            compiler_version=cast("int", row[8]),
            origin=RevisionOrigin(cast("str", row[9])),
            restored_from_revision_id=None if restored_rev is None else RevisionId(restored_rev),
            published_by=PrincipalId(cast("UUID", row[11])),
            published_at=cast("datetime", row[12]),
            change_reason=cast("str", row[13]),
        )
    except (TypeError, ValueError, ValidationFailed) as exc:
        raise damaged("plan_revisions", row[0], exc) from exc


def member_ref_from_row(row: Row) -> MemberRef:
    try:
        return MemberRef(
            entity_id=EntityId(cast("UUID", row[0])),
            entity_kind=EntityKind(cast("str", row[1])),
            display_key=cast("str", row[2]),
            position=cast("int", row[3]),
        )
    except (TypeError, ValueError) as exc:
        raise damaged("revision_members", row[0], exc) from exc


def work_policy_to_sql(policy: WorkPolicyOverride | None) -> Jsonb | None:
    """Absent ``work_policy`` is SQL ``NULL``; ``WorkPolicyOverride()`` is ``'{}'::jsonb`` (DDL ``0029``)."""
    if policy is None:
        return None
    return to_jsonb(work_policy_to_doc(policy))


def work_policy_from_sql(raw: object) -> WorkPolicyOverride | None:
    """SQL ``NULL`` is ``None`` (absent); ``{}`` is ``WorkPolicyOverride()`` (DDL ``0029``)."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("work_policy column must be a JSON object or NULL")
    return work_policy_from_doc(cast("Mapping[str, JsonValue]", raw))


def zip_compact(keys: Sequence[str], vals: Sequence[object]) -> JsonObject:
    raw = dict(zip(keys, vals, strict=True))
    return compact(cast("Mapping[str, JsonValue | None]", raw))


def topological_units(
    units: tuple[Unit, ...], spec: Specification
) -> list[tuple[Unit, UUID, UUID | None, int, str]]:
    item_positions: dict[UUID, int] = {}
    enriched: list[tuple[Unit, UUID, UUID | None, int, str]] = []
    for unit in units:
        item_key, local_key = unit.key.split("/", 1)
        item_id = UUID(str(spec.by_key(item_key).id))
        pos = item_positions.get(item_id, 0)
        item_positions[item_id] = pos + 1
        parent_id: UUID | None = None
        if unit.parent is not None:
            parent_key = unit.parent if "/" in unit.parent else f"{item_key}/{unit.parent}"
            parent_id = UUID(str(spec.by_key(parent_key).id))
        enriched.append((unit, item_id, parent_id, pos, local_key))

    by_id = {UUID(str(u[0].id)): u for u in enriched}
    ordered: list[tuple[Unit, UUID, UUID | None, int, str]] = []
    visited: set[UUID] = set()

    def visit(entry: tuple[Unit, UUID, UUID | None, int, str]) -> None:
        uid = UUID(str(entry[0].id))
        if uid in visited:
            return
        visited.add(uid)
        if entry[2] is not None and entry[2] in by_id:
            visit(by_id[entry[2]])
        ordered.append(entry)

    for entry in enriched:
        visit(entry)
    return ordered


def read_spec_row(
    ws_id: UUID,
    plan_id: UUID,
    rev_id: UUID,
    owner_id: UUID,
    purpose: str,
    pos: int,
    read: Read,
    spec: Specification,
) -> tuple[object, ...]:
    p = (ws_id, plan_id, rev_id, owner_id, purpose, pos)
    s = (read.required, read.why)
    match read:
        case RepositoryPathRead():
            mid = ("repository_path", read.mount, read.path, read.section, None, None, None, None, None)
        case MaterialRead():
            head, mat_sec = parse_material_ref(read.ref)
            mid = ("material", None, None, None, spec.by_key(head).id, mat_sec, None, None, None)
        case PlanEntityRead():
            mid = ("plan_entity", None, None, None, None, None, spec.by_key(read.ref).id, None, None)
        case ArtifactRead():
            ak = read.ref.removeprefix("artifact/")
            mid = ("artifact", None, None, None, None, None, None, ak, None)
        case ExternalSourceRead():
            mid = ("external_source", None, None, read.external_source_id, None, None, None, None, read.url)
    return (*p, *mid, *s)


def review_req_row(ws_id: UUID, plan_id: UUID, rev_id: UUID, item: Item) -> tuple[object, ...]:
    hdr = (ws_id, plan_id, rev_id, item.id)
    match item.review:
        case RequiredReview(profile, independence, reviewer, max_rounds, covers, req_ev):
            rev_json = None if reviewer is None else to_jsonb(reviewer)
            body = ("required", profile, independence, rev_json, max_rounds, to_jsonb(list(covers)))
            tail = (list(req_ev), None, None)
            return (*hdr, *body, *tail)
        case SelfReview(reason):
            return (*hdr, "self", None, None, None, None, to_jsonb([]), [], reason, None)
        case WaivedReview(reason, waived_by):
            return (*hdr, "waived", None, None, None, None, to_jsonb([]), [], reason, waived_by)


def dep_edge_rows(ws_id: UUID, plan_id: UUID, rev_id: UUID, spec: Specification) -> list[tuple[object, ...]]:
    hdr = (ws_id, plan_id, rev_id)
    edges: list[tuple[object, ...]] = []
    for pos, phase in enumerate(spec.phases):
        if phase.depends_on is None:
            if pos > 0:
                edges.append((*hdr, phase.id, spec.phases[pos - 1].id, "phase_depends_on", True))
        else:
            edges.extend(
                (*hdr, phase.id, spec.by_key(dep_key).id, "phase_depends_on", False)
                for dep_key in phase.depends_on
            )
    edges.extend(
        (*hdr, item.id, spec.by_key(dep_key).id, "item_depends_on", False)
        for item in spec.items
        for dep_key in item.depends_on
    )
    for unit in spec.units:
        item_key = unit.key.split("/", 1)[0]
        edges.extend(
            (
                *hdr,
                unit.id,
                spec.by_key(dep_ref if "/" in dep_ref else f"{item_key}/{dep_ref}").id,
                "unit_depends_on",
                False,
            )
            for dep_ref in unit.depends_on
        )
    return edges


def build_ref_forms(spec: Specification) -> JsonObject:
    pos_by_id: dict[EntityId, tuple[str, int]] = {
        e.id: (k, pos)
        for k, ents in (
            ("phase", spec.phases),
            ("item", spec.items),
            ("unit", spec.units),
            ("requirement", spec.requirements),
            ("criterion", spec.criteria),
            ("check", spec.checks),
            ("decision", spec.decisions),
            ("material", spec.materials),
        )
        for pos, e in enumerate(ents)
    }
    out: dict[str, JsonObject] = {}

    def record(
        bucket: str,
        owner_id: EntityId,
        refs: Sequence[str],
        *,
        prefix: str = "",
        local_key: bool = False,
    ) -> None:
        if not refs:
            return
        resolved: list[tuple[tuple[str, int], str]] = []
        for r in refs:
            full = f"{prefix}{r}" if prefix and "/" not in r and ":" not in r else r
            ent = spec.by_key(full)
            disp = ent.key if local_key else spec.display_key(ent)
            resolved.append((pos_by_id[ent.id], disp))
        sql_order = [disp for _, disp in sorted(resolved, key=lambda item: item[0])]
        if list(refs) != sql_order:
            out.setdefault(bucket, {})[str(owner_id)] = list(refs)

    for phase in spec.phases:
        if phase.depends_on:
            record("depends_on", phase.id, phase.depends_on)
    for item in spec.items:
        record("depends_on", item.id, item.depends_on)
        record("implements", item.id, item.implements)
        record("decisions", item.id, item.decisions)
    for unit in spec.units:
        ik = unit.key.split("/", 1)[0]
        if unit.parent is not None and "/" not in unit.parent:
            out.setdefault("parent", {})[str(unit.id)] = unit.parent
        record("depends_on", unit.id, unit.depends_on, prefix=f"{ik}/")
        record("unit_checks", unit.id, unit.checks, prefix=f"{ik}:", local_key=True)
        record("implements", unit.id, unit.implements)
    for req in spec.requirements:
        record("owners", req.id, req.owners)
    for crit in spec.criteria:
        ik = crit.owner.split("/", 1)[0]
        record("crit_checks", crit.id, crit.checks, prefix=f"{ik}:")
        record("requirements", crit.id, crit.requirements)
    for dec in spec.decisions:
        record("dec_applies", dec.id, dec.applies_to)
        record("supersedes", dec.id, dec.supersedes)
    for mat in spec.materials:
        record("mat_applies", mat.id, mat.applies_to)
    return dict(out)


def apply_ref_override(
    ref_forms: Mapping[str, JsonValue], bucket: str, target: dict[UUID, list[str]]
) -> None:
    raw = ref_forms.get(bucket)
    if isinstance(raw, Mapping):
        for uid_str, vals in raw.items():
            if isinstance(vals, list):
                target[UUID(uid_str)] = [str(x) for x in vals]
