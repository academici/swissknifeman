"""Typed specification writer: decomposes ``RevisionRecord`` into ``skm_planning`` tables (planning §11.3)."""

from collections.abc import Sequence
from copy import deepcopy
from typing import Final
from uuid import UUID

import psycopg

from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.adapters.postgres.planning.mapping import (
    already_exists,
    build_ref_forms,
    dep_edge_rows,
    read_spec_row,
    review_req_row,
    run,
    topological_units,
    work_policy_to_sql,
    zip_compact,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import EntityId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.planning.domain.check_spec import definition_to_doc
from skm.modules.planning.domain.execution_constraints import constraints_to_doc
from skm.modules.planning.domain.item import ExternalGate, Item, OwnerGate, Routine, route_to_doc
from skm.modules.planning.domain.material import MaterialKind
from skm.modules.planning.domain.phase import Phase
from skm.modules.planning.domain.reads import compact, format_timestamp, sections_to_doc
from skm.modules.planning.domain.scope import scope_to_doc
from skm.modules.planning.domain.specification import (
    EntityKind,
    SpecEntity,
    Specification,
)
from skm.modules.planning.ports import MaterialPin, RevisionRecord

__all__ = ["write_revision_record"]

_CHECK_ID_EXISTS: Final = "SELECT 1 FROM skm_planning.plan_revisions WHERE id = %s"
_CHECK_NO_EXISTS: Final = "SELECT 1 FROM skm_planning.plan_revisions WHERE plan_id = %s AND revision_no = %s"
_CHECK_IDENTITIES: Final = (
    "SELECT entity_id, plan_id, entity_kind FROM skm_planning.plan_entity_identities "
    "WHERE entity_id = ANY(%s)"
)
_INSERT_REVISION: Final = (
    "INSERT INTO skm_planning.plan_revisions ("
    "workspace_id, plan_id, id, revision_no, parent_revision_id, schema_version, content_digest, "
    "canonicalization_version, compiler_version, published_by, published_at, change_reason, "
    "origin, restored_from_revision_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_IDENTITY: Final = (
    "INSERT INTO skm_planning.plan_entity_identities "
    "(workspace_id, plan_id, entity_id, entity_kind, first_revision_id, created_at) "
    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (plan_id, entity_id) DO NOTHING"
)
_INSERT_MEMBER: Final = (
    "INSERT INTO skm_planning.revision_members "
    "(workspace_id, plan_id, revision_id, entity_id, entity_kind, display_key, position) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_REVISION_SPEC: Final = (
    "INSERT INTO skm_planning.revision_specs ("
    "workspace_id, plan_id, revision_id, title, goal, context_md, non_goals, rules, "
    "design_brief_id, brief, execution_constraints, sections, extensions) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_PHASE_SPEC: Final = (
    "INSERT INTO skm_planning.phase_specs ("
    "workspace_id, plan_id, revision_id, phase_id, entity_kind, position, title, goal, "
    "context_md, design_state, strategy, depends_on_declared, contract, scope, pitfalls, "
    "deliverables, assurance, sections) "
    "VALUES (%s, %s, %s, %s, 'phase', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_BATCH_SPEC: Final = (
    "INSERT INTO skm_planning.batch_specs "
    "(workspace_id, plan_id, revision_id, phase_id, batch_key, position, mode, note) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_ITEM_SPEC: Final = (
    "INSERT INTO skm_planning.item_specs ("
    "workspace_id, plan_id, revision_id, item_id, entity_kind, phase_id, position, title, "
    "summary, why, work_kind, unit_strategy, authority_kind, authority_gate, authority_label, "
    "authority_scope, research_need, research_question, route, scope, rules, guidance_md, "
    "deliverables, sections, work_policy) VALUES ("
    "%s, %s, %s, %s, 'item', %s, %s, %s, %s, %s, %s, %s, "
    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_UNIT_SPEC: Final = (
    "INSERT INTO skm_planning.unit_specs ("
    "workspace_id, plan_id, revision_id, unit_id, entity_kind, item_id, parent_unit_id, "
    "position, local_key, title, goal, unit_kind, work_kind, mode, route, instructions_md, "
    "command, sections, work_policy) VALUES ("
    "%s, %s, %s, %s, 'unit', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_REQUIREMENT_SPEC: Final = (
    "INSERT INTO skm_planning.requirement_specs ("
    "workspace_id, plan_id, revision_id, requirement_id, entity_kind, position, "
    "statement, priority, source_kind, source_ref) "
    "VALUES (%s, %s, %s, %s, 'requirement', %s, %s, %s, %s, %s)"
)
_INSERT_CHECK_SPEC: Final = (
    "INSERT INTO skm_planning.check_specs ("
    "workspace_id, plan_id, revision_id, check_id, entity_kind, owner_entity_id, owner_kind, "
    "local_key, position, title, kind, category, required, rerun_after_integration, "
    "definition, evidence_policy) "
    "VALUES (%s, %s, %s, %s, 'check', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_CRITERION: Final = (
    "INSERT INTO skm_planning.acceptance_criteria ("
    "workspace_id, plan_id, revision_id, criterion_id, entity_kind, owner_entity_id, "
    "owner_kind, position, statement, verification_mode) "
    "VALUES (%s, %s, %s, %s, 'criterion', %s, %s, %s, %s, %s)"
)
_INSERT_DECISION_SPEC: Final = (
    "INSERT INTO skm_planning.decision_specs ("
    "workspace_id, plan_id, revision_id, decision_id, entity_kind, position, title, state, "
    "source_date, question, options, context_md, decision, rationale, consequences, is_global, "
    "evidence, origin_kind, origin_ref, answered_by, sections) VALUES ("
    "%s, %s, %s, %s, 'decision', %s, %s, %s, %s, %s, %s, "
    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_DECISION_SUPERSESSION: Final = (
    "INSERT INTO skm_planning.decision_supersessions "
    "(workspace_id, plan_id, revision_id, decision_id, superseded_decision_id) "
    "VALUES (%s, %s, %s, %s, %s)"
)
_INSERT_DECISION_BINDING: Final = (
    "INSERT INTO skm_planning.decision_bindings "
    "(workspace_id, plan_id, revision_id, decision_id, entity_id, binding_kind) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_INSERT_MATERIAL_SPEC: Final = (
    "INSERT INTO skm_planning.material_specs ("
    "workspace_id, plan_id, revision_id, material_id, entity_kind, position, title, kind, "
    "role, required_for, freshness_policy, freshness_max_age_s, why, is_global, mount_name, "
    "path, external_url, retrieved_at, content_digest, selector) VALUES ("
    "%s, %s, %s, %s, 'material', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_FILE_BINDING: Final = (
    "INSERT INTO skm_planning.revision_file_bindings "
    "(workspace_id, plan_id, revision_id, material_id, file_version_id, role, selector) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_MATERIAL_BINDING: Final = (
    "INSERT INTO skm_planning.material_bindings "
    "(workspace_id, plan_id, revision_id, material_id, entity_id) VALUES (%s, %s, %s, %s, %s)"
)
_INSERT_REQ_LINK: Final = (
    "INSERT INTO skm_planning.entity_requirement_links "
    "(workspace_id, plan_id, revision_id, entity_id, requirement_id, relation) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)
_INSERT_DEP_EDGE: Final = (
    "INSERT INTO skm_planning.dependency_edges ("
    "workspace_id, plan_id, revision_id, dependent_entity_id, prerequisite_entity_id, "
    "dependency_kind, implicit) VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_ENTITY_RELATION: Final = (
    "INSERT INTO skm_planning.entity_relations ("
    "workspace_id, plan_id, revision_id, source_entity_id, target_entity_id, "
    "relation, position, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_BATCH_MEMBER: Final = (
    "INSERT INTO skm_planning.batch_members "
    "(workspace_id, plan_id, revision_id, phase_id, batch_key, item_id, position) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_ENTITY_CHECK: Final = (
    "INSERT INTO skm_planning.entity_check_bindings "
    "(workspace_id, plan_id, revision_id, entity_id, check_id, binding_role) "
    "VALUES (%s, %s, %s, %s, %s, 'gate')"
)
_INSERT_CRITERION_CHECK: Final = (
    "INSERT INTO skm_planning.criterion_check_bindings "
    "(workspace_id, plan_id, revision_id, criterion_id, check_id) VALUES (%s, %s, %s, %s, %s)"
)
_INSERT_REVIEW_REQ: Final = (
    "INSERT INTO skm_planning.review_requirements ("
    "workspace_id, plan_id, revision_id, owner_entity_id, owner_kind, mode, profile_key, "
    "independence, reviewer, max_rounds, covers, required_evidence, reason, waived_by) "
    "VALUES (%s, %s, %s, %s, 'item', %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_PATH_SPEC: Final = (
    "INSERT INTO skm_planning.entity_path_specs ("
    "workspace_id, plan_id, revision_id, entity_id, role, position, mount_name, pattern, "
    "change, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_ARTIFACT_SPEC: Final = (
    "INSERT INTO skm_planning.artifact_specs ("
    "workspace_id, plan_id, revision_id, item_id, position, artifact_key, role, "
    "mount_name, path, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_READ_SPEC: Final = (
    "INSERT INTO skm_planning.entity_read_specs ("
    "workspace_id, plan_id, revision_id, entity_id, purpose, position, target_kind, "
    "mount_name, path, section, material_id, material_section, target_entity_id, "
    "artifact_key, external_url, required, why) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_SKILL_REQ: Final = (
    "INSERT INTO skm_planning.entity_skill_requirements ("
    "workspace_id, plan_id, revision_id, entity_id, resource_key, version_constraint, position) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_PLAN_RELATION: Final = (
    "INSERT INTO skm_planning.plan_relations ("
    "workspace_id, plan_id, revision_id, position, kind, target_plan_id, target_ref, note) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
)
_INSERT_PAYLOAD: Final = (
    "INSERT INTO skm_planning.revision_payloads "
    "(workspace_id, plan_id, revision_id, document, document_digest) "
    "VALUES (%s, %s, %s, %s, %s)"
)


def _phase_and_batch_rows(
    ws_id: UUID, plan_id: UUID, rev_id: UUID, spec: Specification
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    hdr = (ws_id, plan_id, rev_id)
    phase_rows: list[tuple[object, ...]] = []
    batch_rows: list[tuple[object, ...]] = []
    for pos, phase in enumerate(spec.phases):
        c_raw = (phase.contract.consumes, phase.contract.produces, phase.contract.boundaries)
        contract_doc = compact(
            {k: list(v) for k, v in zip(("consumes", "produces", "boundaries"), c_raw, strict=True)}
        )
        a = phase.assurance
        a_doc = (
            None
            if a is None
            else zip_compact(("impact", "seams", "live", "note"), (a.impact, list(a.seams), a.live, a.note))
        )
        p1 = (phase.id, pos, phase.title, phase.goal, phase.context_md)
        p2 = (phase.design_state.value, phase.strategy.value, phase.depends_on is not None)
        p3 = (to_jsonb(contract_doc), None if phase.scope is None else to_jsonb(scope_to_doc(phase.scope)))
        p4 = (to_jsonb(list(phase.pitfalls)), to_jsonb(list(phase.deliverables)))
        p5 = (None if a_doc is None else to_jsonb(a_doc), to_jsonb(sections_to_doc(phase.sections)))
        phase_rows.append((*hdr, *p1, *p2, *p3, *p4, *p5))
        batch_rows.extend(
            (*hdr, phase.id, batch.key, b_pos, batch.mode.value, batch.note)
            for b_pos, batch in enumerate(phase.batches)
        )
    return phase_rows, batch_rows


def _item_rows(ws_id: UUID, plan_id: UUID, rev_id: UUID, spec: Specification) -> list[tuple[object, ...]]:
    hdr = (ws_id, plan_id, rev_id)
    rows: list[tuple[object, ...]] = []
    for pos, item in enumerate(spec.items):
        phase_id = spec.by_key(item.phase).id
        match item.authority:
            case Routine():
                auth = ("routine", None, None, None)
            case OwnerGate(gate, label, scope):
                auth = ("owner_gate", gate, label, scope)
            case ExternalGate(gate, label, scope):
                auth = ("external_gate", gate, label, scope)
        sec_payload: list[JsonValue] = list(sections_to_doc(item.sections))
        if item.research is not None:
            sec_payload.append({"_research": compact({"declared": True, "notes": item.research.notes})})
        res = ("none", None) if item.research is None else (item.research.need, item.research.question)
        rt = None if item.route is None else to_jsonb(route_to_doc(item.route))
        sc = None if item.scope is None else to_jsonb(scope_to_doc(item.scope))
        i1 = (item.id, phase_id, pos, item.title, item.summary, item.why)
        i2 = (item.work_kind.value, item.unit_strategy.value, *auth, *res, rt, sc)
        i3 = (to_jsonb(list(item.rules)), item.guidance_md, to_jsonb(list(item.deliverables)))
        i4 = (to_jsonb(sec_payload), work_policy_to_sql(item.work_policy))
        rows.append((*hdr, *i1, *i2, *i3, *i4))
    return rows


def _unit_rows(ws_id: UUID, plan_id: UUID, rev_id: UUID, spec: Specification) -> list[tuple[object, ...]]:
    hdr = (ws_id, plan_id, rev_id)
    rows: list[tuple[object, ...]] = []
    for unit, item_id, parent_id, u_pos, local_key in topological_units(spec.units, spec):
        cmd_doc: JsonObject | None = (
            None
            if unit.command is None
            else {"kind": unit.command.kind, "definition": definition_to_doc(unit.command.definition)}
        )
        u_sec = sections_to_doc(unit.sections)
        wk = None if unit.work_kind is None else unit.work_kind.value
        rt = None if unit.route is None else to_jsonb(route_to_doc(unit.route))
        cm = None if cmd_doc is None else to_jsonb(cmd_doc)
        u1 = (unit.id, item_id, parent_id, u_pos, local_key, unit.title, unit.goal, unit.unit_kind.value)
        u2 = (wk, unit.mode.value, rt, unit.instructions_md, cm, to_jsonb(u_sec))
        rows.append((*hdr, *u1, *u2, work_policy_to_sql(unit.work_policy)))
    return rows


def _decision_and_material_rows(
    ws_id: UUID, plan_id: UUID, rev_id: UUID, spec: Specification, pins: tuple[MaterialPin, ...]
) -> tuple[Sequence[tuple[object, ...]], ...]:
    hdr = (ws_id, plan_id, rev_id)
    dec_rows: list[tuple[object, ...]] = []
    for pos, dec in enumerate(spec.decisions):
        d1 = (dec.id, pos, dec.title, dec.state.value, dec.date, dec.question)
        opts_j = to_jsonb([{"key": o.key, "text": o.text} for o in dec.options])
        d2 = (opts_j, dec.context_md, dec.decision, dec.rationale)
        ev_j = to_jsonb([compact({"kind": e.kind, "ref": e.ref, "note": e.note}) for e in dec.evidence])
        d3 = (to_jsonb(list(dec.consequences)), dec.is_global, ev_j)
        orig_pair = (None, None) if dec.origin is None else (dec.origin.kind, dec.origin.ref)
        d4 = (*orig_pair, dec.answered_by, to_jsonb(sections_to_doc(dec.sections)))
        dec_rows.append((*hdr, *d1, *d2, *d3, *d4))

    sup_rows = [(*hdr, dec.id, spec.by_key(k).id) for dec in spec.decisions for k in dec.supersedes]
    dec_bind_rows = [
        *[(*hdr, dec.id, spec.by_key(k).id, "applies_to") for dec in spec.decisions for k in dec.applies_to],
        *[(*hdr, spec.by_key(k).id, item.id, "cited_by") for item in spec.items for k in item.decisions],
    ]
    mat_rows: list[tuple[object, ...]] = []
    for pos, mat in enumerate(spec.materials):
        selector_sql = None if mat.selector is None else to_jsonb(mat.selector)
        if mat.kind is MaterialKind.EXTERNAL_SOURCE:
            ret_s = None if mat.retrieved_at is None else format_timestamp(mat.retrieved_at)
            ext_meta = compact(
                {
                    "_external_source_id": mat.external_source_id,
                    "_retrieved_at": ret_s,
                    "_selector": mat.selector,
                }
            )
            selector_sql = to_jsonb(ext_meta) if ext_meta else None
        m1 = (mat.id, pos, mat.title, mat.kind.value, mat.role, [s.value for s in mat.required_for])
        m2 = (mat.freshness.policy.value, mat.freshness.max_age_seconds, mat.why, mat.is_global)
        ret_dt = None if mat.retrieved_at is None else require_aware(mat.retrieved_at)
        m3 = (mat.mount, mat.path, mat.url, ret_dt, mat.content_digest, selector_sql)
        mat_rows.append((*hdr, *m1, *m2, *m3))

    file_bind_rows = _file_binding_rows(ws_id, plan_id, rev_id, pins)
    mat_bind_rows = [(*hdr, mat.id, spec.by_key(k).id) for mat in spec.materials for k in mat.applies_to]
    return dec_rows, sup_rows, dec_bind_rows, mat_rows, file_bind_rows, mat_bind_rows


def _file_binding_rows(
    ws_id: UUID,
    plan_id: UUID,
    rev_id: UUID,
    pins: Sequence[MaterialPin],
) -> list[tuple[object, ...]]:
    """Build ``skm_planning.revision_file_bindings`` rows for pinned ``file_version`` materials."""
    hdr = (ws_id, plan_id, rev_id)
    return [
        (
            *hdr,
            pin.material_id,
            pin.file_version_id,
            pin.role,
            None if pin.selector is None else to_jsonb(deepcopy(pin.selector)),
        )
        for pin in pins
    ]


def write_revision_record(conn: psycopg.Connection, record: RevisionRecord) -> None:
    """Write ``record`` into ``skm_planning`` in the normative FK order (planning §11.3)."""
    run(lambda: _write_all(conn, record))


def _write_all(conn: psycopg.Connection, record: RevisionRecord) -> None:
    meta = record.meta
    spec = record.spec
    ws_id, plan_id, rev_id = meta.workspace_id, meta.plan_id, meta.id
    hdr = (ws_id, plan_id, rev_id)
    published_at = require_aware(meta.published_at)

    if conn.execute(_CHECK_ID_EXISTS, (rev_id,)).fetchone() is not None:
        raise already_exists("revision", ref=str(rev_id))
    if conn.execute(_CHECK_NO_EXISTS, (plan_id, meta.revision_no)).fetchone() is not None:
        raise already_exists("revision", revision_no=str(meta.revision_no))

    groups: tuple[tuple[EntityKind, Sequence[SpecEntity]], ...] = (
        (EntityKind.PHASE, spec.phases),
        (EntityKind.ITEM, spec.items),
        (EntityKind.UNIT, spec.units),
        (EntityKind.REQUIREMENT, spec.requirements),
        (EntityKind.CRITERION, spec.criteria),
        (EntityKind.CHECK, spec.checks),
        (EntityKind.DECISION, spec.decisions),
        (EntityKind.MATERIAL, spec.materials),
    )
    all_entities = [(e.id, k, spec.display_key(e), pos) for k, ents in groups for pos, e in enumerate(ents)]
    id_pairs: dict[EntityId, EntityKind] = dict(record.new_identities)
    for eid, kind, _, _ in all_entities:
        id_pairs.setdefault(eid, kind)

    existing_ids: set[EntityId] = set()
    if id_pairs:
        existing = conn.execute(_CHECK_IDENTITIES, ([UUID(str(e)) for e in id_pairs],)).fetchall()
        foreign: list[JsonValue] = [*sorted(str(r[0]) for r in existing if r[1] != UUID(str(plan_id)))]
        if foreign:
            raise Conflict(
                ErrorCode.ID_CONFLICT, "an entity id belongs to another plan", details={"entity_ids": foreign}
            )
        for row in existing:
            eid = EntityId(row[0])
            existing_ids.add(eid)
            if eid in id_pairs and id_pairs[eid].value != row[2]:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    f"entity {eid} changed kind from {row[2]!r} to {id_pairs[eid].value!r}",
                )

    r1 = (meta.revision_no, meta.parent_revision_id, meta.schema_version, meta.content_digest)
    r2 = (meta.canonicalization_version, meta.compiler_version, meta.published_by, published_at)
    r3 = (meta.change_reason, meta.origin.value, meta.restored_from_revision_id)
    conn.execute(_INSERT_REVISION, (*hdr, *r1, *r2, *r3))

    phase_rows, batch_rows = _phase_and_batch_rows(ws_id, plan_id, rev_id, spec)
    dec_rows, sup_rows, dec_bind_rows, mat_rows, file_bind_rows, mat_bind_rows = _decision_and_material_rows(
        ws_id, plan_id, rev_id, spec, record.pins
    )
    rs1 = (spec.title, spec.goal, spec.context_md, to_jsonb(list(spec.non_goals)), to_jsonb(list(spec.rules)))
    rs2 = (
        spec.design_brief_id,
        None if spec.brief is None else to_jsonb(record.document.get("brief")),
        to_jsonb(constraints_to_doc(spec.execution_constraints)),
    )
    rev_sec: list[JsonValue] = list(sections_to_doc(spec.sections))
    ref_forms = build_ref_forms(spec)
    if ref_forms:
        rev_sec.append({"_ref_forms": ref_forms})
    rs3 = (to_jsonb(rev_sec), to_jsonb(dict(spec.extensions)))
    crit_rows = [
        (
            *hdr,
            c.id,
            spec.by_key(c.owner).id,
            "item" if isinstance(spec.by_key(c.owner), Item) else "unit",
            pos,
            c.statement,
            c.verification_mode.value,
        )
        for pos, c in enumerate(spec.criteria)
    ]

    with conn.cursor() as cur:
        cur.executemany(
            _INSERT_IDENTITY,
            [
                (*hdr[:2], e, k.value, rev_id, published_at)
                for e, k in id_pairs.items()
                if e not in existing_ids
            ],
        )
        cur.executemany(_INSERT_MEMBER, [(*hdr, e, k.value, d, p) for e, k, d, p in all_entities])
        cur.execute(_INSERT_REVISION_SPEC, (*hdr, *rs1, *rs2, *rs3))
        cur.executemany(_INSERT_PHASE_SPEC, phase_rows)
        cur.executemany(_INSERT_BATCH_SPEC, batch_rows)
        cur.executemany(_INSERT_ITEM_SPEC, _item_rows(ws_id, plan_id, rev_id, spec))
        cur.executemany(_INSERT_UNIT_SPEC, _unit_rows(ws_id, plan_id, rev_id, spec))
        cur.executemany(
            _INSERT_REQUIREMENT_SPEC,
            [
                (*hdr, r.id, pos, r.statement, r.priority.value, r.source.kind, r.source.ref)
                for pos, r in enumerate(spec.requirements)
            ],
        )
        cur.executemany(_INSERT_CHECK_SPEC, _check_rows(ws_id, plan_id, rev_id, spec))
        cur.executemany(_INSERT_CRITERION, crit_rows)
        cur.executemany(_INSERT_DECISION_SPEC, dec_rows)
        cur.executemany(_INSERT_DECISION_SUPERSESSION, sup_rows)
        cur.executemany(_INSERT_DECISION_BINDING, dec_bind_rows)
        cur.executemany(_INSERT_MATERIAL_SPEC, mat_rows)
        cur.executemany(_INSERT_FILE_BINDING, file_bind_rows)
        cur.executemany(_INSERT_MATERIAL_BINDING, mat_bind_rows)
        _write_links(cur, ws_id, plan_id, rev_id, spec, record.plan_relation_targets)
        cur.execute(_INSERT_PAYLOAD, (*hdr, to_jsonb(record.document), meta.content_digest))


def _check_rows(ws_id: UUID, plan_id: UUID, rev_id: UUID, spec: Specification) -> list[tuple[object, ...]]:
    hdr = (ws_id, plan_id, rev_id)
    rows: list[tuple[object, ...]] = []
    for pos, c in enumerate(spec.checks):
        owner = spec.by_key(c.owner)
        okind = "phase" if isinstance(owner, Phase) else "item"
        ev: JsonObject = {"stdout": c.evidence.stdout, "stderr": c.evidence.stderr}
        if c.evidence.report_files:
            ev["report_files"] = list(c.evidence.report_files)
        c1 = (c.id, owner.id, okind, c.key, pos, c.title, c.kind.value, c.category.value)
        c2 = (c.required, c.rerun_after_integration, to_jsonb(definition_to_doc(c.definition)), to_jsonb(ev))
        rows.append((*hdr, *c1, *c2))
    return rows


def _write_links(
    cur: psycopg.Cursor,
    ws_id: UUID,
    plan_id: UUID,
    rev_id: UUID,
    spec: Specification,
    plan_relation_targets: tuple[UUID | None, ...],
) -> None:
    hdr = (ws_id, plan_id, rev_id)
    req_links = [
        *[(*hdr, spec.by_key(k).id, req.id, "owns") for req in spec.requirements for k in req.owners],
        *[(*hdr, item.id, spec.by_key(k).id, "implements") for item in spec.items for k in item.implements],
        *[(*hdr, unit.id, spec.by_key(k).id, "implements") for unit in spec.units for k in unit.implements],
        *[
            (*hdr, crit.id, spec.by_key(k).id, "verifies")
            for crit in spec.criteria
            for k in crit.requirements
        ],
    ]
    rel_rows = [
        (*hdr, item.id, spec.by_key(rel.target).id, rel.relation, r_pos, rel.note)
        for item in spec.items
        for r_pos, rel in enumerate(item.relations)
    ]
    batch_member_rows = [
        (*hdr, phase.id, batch.key, spec.by_key(item_key).id, m_pos)
        for phase in spec.phases
        for batch in phase.batches
        for m_pos, item_key in enumerate(batch.items)
    ]
    unit_check_rows = [
        (*hdr, unit.id, spec.by_key(chk if ":" in chk else f"{unit.key.split('/', 1)[0]}:{chk}").id)
        for unit in spec.units
        for chk in unit.checks
    ]
    crit_check_rows = [
        (*hdr, crit.id, spec.by_key(r if ":" in r else f"{crit.owner.split('/', 1)[0]}:{r}").id)
        for crit in spec.criteria
        for r in crit.checks
    ]
    review_rows = [review_req_row(ws_id, plan_id, rev_id, item) for item in spec.items]
    path_rows = [
        *[
            (*hdr, item.id, "change_hint", pos, h.mount, h.pattern, h.change, h.note)
            for item in spec.items
            for pos, h in enumerate(item.change_hints)
        ],
        *[
            (*hdr, unit.id, "declared_write_scope", pos, w.mount, w.pattern, None, None)
            for unit in spec.units
            for pos, w in enumerate(unit.write_scope)
        ],
        *[
            (*hdr, unit.id, "output", pos, o.mount, o.path, None, o.note)
            for unit in spec.units
            for pos, o in enumerate(unit.outputs)
        ],
    ]
    artifact_rows = [
        (*hdr, item.id, pos, art.key, art.role, art.mount, art.path, art.note)
        for item in spec.items
        for pos, art in enumerate(item.artifacts)
    ]
    read_rows = [
        *[
            read_spec_row(ws_id, plan_id, rev_id, phase.id, "supporting", pos, r, spec)
            for phase in spec.phases
            for pos, r in enumerate(phase.supporting)
        ],
        *[
            read_spec_row(ws_id, plan_id, rev_id, item.id, "read", pos, r, spec)
            for item in spec.items
            for pos, r in enumerate(item.reads)
        ],
        *[
            read_spec_row(ws_id, plan_id, rev_id, item.id, "example", pos, r, spec)
            for item in spec.items
            for pos, r in enumerate(item.examples)
        ],
        *[
            read_spec_row(ws_id, plan_id, rev_id, unit.id, "read", pos, r, spec)
            for unit in spec.units
            for pos, r in enumerate(unit.reads)
        ],
    ]
    skill_rows = [
        (*hdr, item.id, skill.key, skill.version, pos)
        for item in spec.items
        for pos, skill in enumerate(item.skills)
    ]
    plan_rel_rows = [
        (
            *hdr,
            p,
            r.kind.value,
            plan_relation_targets[p] if p < len(plan_relation_targets) else None,
            r.target,
            r.note,
        )
        for p, r in enumerate(spec.plan_relations)
    ]

    cur.executemany(_INSERT_REQ_LINK, req_links)
    cur.executemany(_INSERT_DEP_EDGE, dep_edge_rows(ws_id, plan_id, rev_id, spec))
    cur.executemany(_INSERT_ENTITY_RELATION, rel_rows)
    cur.executemany(_INSERT_BATCH_MEMBER, batch_member_rows)
    cur.executemany(_INSERT_ENTITY_CHECK, unit_check_rows)
    cur.executemany(_INSERT_CRITERION_CHECK, crit_check_rows)
    cur.executemany(_INSERT_REVIEW_REQ, review_rows)
    cur.executemany(_INSERT_PATH_SPEC, path_rows)
    cur.executemany(_INSERT_ARTIFACT_SPEC, artifact_rows)
    cur.executemany(_INSERT_READ_SPEC, read_rows)
    cur.executemany(_INSERT_SKILL_REQ, skill_rows)
    cur.executemany(_INSERT_PLAN_RELATION, plan_rel_rows)
