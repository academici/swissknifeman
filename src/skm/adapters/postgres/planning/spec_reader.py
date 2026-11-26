"""Typed specification reader: reconstructs ``SpecificationDoc`` from relational tables (planning §11.4)."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime
from typing import Final, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.planning import mapping as mp
from skm.kernel.ids import EntityId, RevisionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.planning.domain.item import work_policy_to_doc
from skm.modules.planning.domain.material import MaterialRef
from skm.modules.planning.domain.reads import compact, format_timestamp, parse_timestamp
from skm.modules.planning.domain.specification import SPECIFICATION_URN, from_document, to_document
from skm.modules.planning.ports import MaterialPin, SpecificationDoc

__all__ = [
    "load_revision_materials",
    "load_revision_pins",
    "load_typed_document",
    "revisions_for_file_version",
]

_SELECT_REV_EXISTS: Final = "SELECT 1 FROM skm_planning.plan_revisions WHERE id = %s"
_SELECT_REV_SPEC: Final = """SELECT title, goal, context_md, non_goals, rules, brief, design_brief_id,
execution_constraints, sections, extensions FROM skm_planning.revision_specs WHERE revision_id = %s"""
_SELECT_PHASES: Final = """SELECT p.phase_id, m.display_key, p.title, p.goal, p.context_md, p.design_state,
p.strategy, p.depends_on_declared, p.contract, p.scope, p.pitfalls, p.deliverables, p.assurance, p.sections
FROM skm_planning.phase_specs p
JOIN skm_planning.revision_members m ON m.revision_id = p.revision_id AND m.entity_id = p.phase_id
WHERE p.revision_id = %s ORDER BY p.position ASC"""
_SELECT_BATCHES: Final = """SELECT phase_id, batch_key, mode, note FROM skm_planning.batch_specs
WHERE revision_id = %s ORDER BY phase_id, position ASC"""
_SELECT_BATCH_MEMBERS: Final = """SELECT b.phase_id, b.batch_key, m.display_key
FROM skm_planning.batch_members b
JOIN skm_planning.revision_members m ON m.revision_id = b.revision_id AND m.entity_id = b.item_id
WHERE b.revision_id = %s ORDER BY b.phase_id, b.batch_key, b.position ASC"""
_SELECT_ITEMS: Final = """SELECT i.item_id, m.display_key, pm.display_key, i.title, i.summary, i.why,
i.work_kind, i.unit_strategy, i.authority_kind, i.authority_gate, i.authority_label, i.authority_scope,
i.research_need, i.research_question, i.route, i.scope, i.rules, i.guidance_md, i.deliverables,
i.sections, i.work_policy FROM skm_planning.item_specs i
JOIN skm_planning.revision_members m ON m.revision_id = i.revision_id AND m.entity_id = i.item_id
JOIN skm_planning.revision_members pm ON pm.revision_id = i.revision_id AND pm.entity_id = i.phase_id
WHERE i.revision_id = %s ORDER BY i.position ASC"""
_SELECT_REVIEWS: Final = """SELECT owner_entity_id, mode, profile_key, independence, reviewer, max_rounds,
covers, required_evidence, reason, waived_by FROM skm_planning.review_requirements WHERE revision_id = %s"""
_SELECT_UNITS: Final = """SELECT u.unit_id, m.display_key, u.parent_unit_id, pm.display_key, u.title, u.goal,
u.unit_kind, u.work_kind, u.mode, u.route, u.instructions_md, u.command, u.sections, u.work_policy
FROM skm_planning.unit_specs u
JOIN skm_planning.revision_members m ON m.revision_id = u.revision_id AND m.entity_id = u.unit_id
LEFT JOIN skm_planning.revision_members pm
ON pm.revision_id = u.revision_id AND pm.entity_id = u.parent_unit_id
WHERE u.revision_id = %s ORDER BY m.position ASC"""
_SELECT_REQUIREMENTS: Final = """SELECT r.requirement_id, m.display_key, r.statement, r.priority,
r.source_kind, r.source_ref FROM skm_planning.requirement_specs r
JOIN skm_planning.revision_members m ON m.revision_id = r.revision_id AND m.entity_id = r.requirement_id
WHERE r.revision_id = %s ORDER BY r.position ASC"""
_SELECT_CHECKS: Final = """SELECT c.check_id, c.local_key, om.display_key, c.title, c.kind, c.category,
c.required, c.rerun_after_integration, c.definition, c.evidence_policy FROM skm_planning.check_specs c
JOIN skm_planning.revision_members om ON om.revision_id = c.revision_id AND om.entity_id = c.owner_entity_id
WHERE c.revision_id = %s ORDER BY c.position ASC"""
_SELECT_CRITERIA: Final = """SELECT a.criterion_id, m.display_key, om.display_key, a.statement,
a.verification_mode FROM skm_planning.acceptance_criteria a
JOIN skm_planning.revision_members m ON m.revision_id = a.revision_id AND m.entity_id = a.criterion_id
JOIN skm_planning.revision_members om ON om.revision_id = a.revision_id AND om.entity_id = a.owner_entity_id
WHERE a.revision_id = %s ORDER BY a.position ASC"""
_SELECT_DECISIONS: Final = """SELECT d.decision_id, m.display_key, d.title, d.state, d.source_date,
d.question, d.options, d.context_md, d.decision, d.rationale, d.consequences, d.is_global, d.evidence,
d.origin_kind, d.origin_ref, d.answered_by, d.sections FROM skm_planning.decision_specs d
JOIN skm_planning.revision_members m ON m.revision_id = d.revision_id AND m.entity_id = d.decision_id
WHERE d.revision_id = %s ORDER BY d.position ASC"""
_SELECT_MATERIALS: Final = """SELECT ms.material_id, m.display_key, ms.title, ms.kind, ms.role,
ms.required_for, ms.freshness_policy, ms.freshness_max_age_s, ms.why, ms.is_global, ms.mount_name,
ms.path, ms.external_url, ms.retrieved_at, ms.content_digest, ms.selector,
fb.file_version_id, fb.selector AS pin_selector, fb.role AS pin_role FROM skm_planning.material_specs ms
JOIN skm_planning.revision_members m ON m.revision_id = ms.revision_id AND m.entity_id = ms.material_id
LEFT JOIN skm_planning.revision_file_bindings fb
ON fb.revision_id = ms.revision_id AND fb.material_id = ms.material_id
WHERE ms.revision_id = %s ORDER BY ms.position ASC"""
_SELECT_PINS: Final = """SELECT fb.material_id, fb.file_version_id, fb.role, fb.selector
FROM skm_planning.revision_file_bindings fb
JOIN skm_planning.material_specs ms ON ms.revision_id = fb.revision_id AND ms.material_id = fb.material_id
WHERE fb.revision_id = %s ORDER BY ms.position ASC"""
_SELECT_MAT_BINDINGS_FULL: Final = """SELECT b.material_id, b.entity_id, m.display_key
FROM skm_planning.material_bindings b
JOIN skm_planning.revision_members m ON m.revision_id = b.revision_id AND m.entity_id = b.entity_id
WHERE b.revision_id = %s ORDER BY b.material_id, m.entity_kind, m.position ASC"""
_SELECT_REVS_FOR_FILE_VERSION: Final = """SELECT r.id FROM skm_planning.revision_file_bindings fb
JOIN skm_planning.plan_revisions r ON r.id = fb.revision_id
WHERE fb.file_version_id = %s GROUP BY r.id, r.published_at ORDER BY r.published_at DESC, r.id DESC"""
_SELECT_DEPS: Final = """SELECT d.dependent_entity_id, pm.display_key, d.dependency_kind, d.implicit
FROM skm_planning.dependency_edges d JOIN skm_planning.revision_members pm
ON pm.revision_id = d.revision_id AND pm.entity_id = d.prerequisite_entity_id
WHERE d.revision_id = %s ORDER BY d.dependent_entity_id, pm.entity_kind, pm.position ASC"""
_SELECT_REQ_LINKS: Final = """SELECT l.entity_id, em.display_key, l.requirement_id, rm.display_key, l.relation
FROM skm_planning.entity_requirement_links l
JOIN skm_planning.revision_members em ON em.revision_id = l.revision_id AND em.entity_id = l.entity_id
JOIN skm_planning.revision_members rm ON rm.revision_id = l.revision_id AND rm.entity_id = l.requirement_id
WHERE l.revision_id = %s ORDER BY l.relation, em.entity_kind, em.position ASC, rm.position ASC"""
_SELECT_DEC_SUPERSESSIONS: Final = """SELECT s.decision_id, m.display_key
FROM skm_planning.decision_supersessions s JOIN skm_planning.revision_members m
ON m.revision_id = s.revision_id AND m.entity_id = s.superseded_decision_id
WHERE s.revision_id = %s ORDER BY s.decision_id, m.position ASC"""
_SELECT_DEC_BINDINGS: Final = """SELECT b.decision_id, dm.display_key, b.entity_id, em.display_key,
b.binding_kind FROM skm_planning.decision_bindings b
JOIN skm_planning.revision_members dm ON dm.revision_id = b.revision_id AND dm.entity_id = b.decision_id
JOIN skm_planning.revision_members em ON em.revision_id = b.revision_id AND em.entity_id = b.entity_id
WHERE b.revision_id = %s ORDER BY b.binding_kind, dm.position ASC, em.entity_kind, em.position ASC"""
_SELECT_MAT_BINDINGS: Final = """SELECT b.material_id, m.display_key FROM skm_planning.material_bindings b
JOIN skm_planning.revision_members m ON m.revision_id = b.revision_id AND m.entity_id = b.entity_id
WHERE b.revision_id = %s ORDER BY b.material_id, m.entity_kind, m.position ASC"""
_SELECT_RELATIONS: Final = """SELECT r.source_entity_id, tm.display_key, r.relation, r.note
FROM skm_planning.entity_relations r
JOIN skm_planning.revision_members tm ON tm.revision_id = r.revision_id AND tm.entity_id = r.target_entity_id
WHERE r.revision_id = %s ORDER BY r.source_entity_id, r.position ASC"""
_SELECT_UNIT_CHECKS: Final = """SELECT b.entity_id, c.local_key FROM skm_planning.entity_check_bindings b
JOIN skm_planning.check_specs c ON c.revision_id = b.revision_id AND c.check_id = b.check_id
WHERE b.revision_id = %s ORDER BY b.entity_id, c.position ASC"""
_SELECT_CRIT_CHECKS: Final = """SELECT b.criterion_id, m.display_key
FROM skm_planning.criterion_check_bindings b
JOIN skm_planning.revision_members m ON m.revision_id = b.revision_id AND m.entity_id = b.check_id
WHERE b.revision_id = %s ORDER BY b.criterion_id, m.position ASC"""
_SELECT_PATHS: Final = """SELECT entity_id, role, mount_name, pattern, change, note
FROM skm_planning.entity_path_specs WHERE revision_id = %s ORDER BY entity_id, role, position ASC"""
_SELECT_ARTIFACTS: Final = """SELECT item_id, artifact_key, role, mount_name, path, note
FROM skm_planning.artifact_specs WHERE revision_id = %s ORDER BY item_id, position ASC"""
_SELECT_READS: Final = """SELECT r.entity_id, r.purpose, r.target_kind, r.mount_name, r.path, r.section,
mm.display_key, r.material_section, tm.display_key, r.artifact_key, r.external_url, r.required, r.why
FROM skm_planning.entity_read_specs r
LEFT JOIN skm_planning.revision_members mm ON mm.revision_id = r.revision_id AND mm.entity_id = r.material_id
LEFT JOIN skm_planning.revision_members tm
ON tm.revision_id = r.revision_id AND tm.entity_id = r.target_entity_id
WHERE r.revision_id = %s ORDER BY r.entity_id, r.purpose, r.position ASC"""
_SELECT_SKILLS: Final = """SELECT entity_id, resource_key, version_constraint
FROM skm_planning.entity_skill_requirements WHERE revision_id = %s ORDER BY entity_id, position ASC"""
_SELECT_PLAN_RELATIONS: Final = """SELECT kind, target_ref, note FROM skm_planning.plan_relations
WHERE revision_id = %s ORDER BY position ASC"""


def _group_str(rows: Sequence[mp.Row]) -> dict[UUID, list[str]]:
    out: dict[UUID, list[str]] = defaultdict(list)
    for row in rows:
        out[cast("UUID", row[0])].append(cast("str", row[1]))
    return out


def _decode_material(
    m: mp.Row, applies_keys: list[JsonValue], applies_ids: list[JsonValue]
) -> tuple[UUID, MaterialRef]:
    mat_uid, m_kind, raw_sel, ret_at = cast("UUID", m[0]), cast("str", m[3]), m[15], m[13]
    freshness: JsonObject = mp.zip_compact(("policy", "max_age_seconds"), (m[6], m[7]))
    ext_source_id: str | None = None
    ret_str: str | None = None
    if m_kind == "file_version":
        if m[16] is None or m[18] is None:
            raise mp.damaged("revision_file_bindings", mat_uid)
        fvid: str | None = str(cast("UUID", m[16]))
        eff_role = cast("str", m[18])
        sel_val: JsonValue = deepcopy(cast("JsonValue", m[17]))
    else:
        fvid = None if m[16] is None else str(cast("UUID", m[16]))
        eff_role = cast("str", m[4])
        sel_val = deepcopy(cast("JsonValue", raw_sel))
    if m_kind == "external_source" and isinstance(raw_sel, dict):
        sel_map = cast("Mapping[str, JsonValue]", raw_sel)
        ext_source_id = cast("str | None", sel_map.get("_external_source_id"))
        saved_ret = cast("str | None", sel_map.get("_retrieved_at"))
        if ret_at is not None:
            dt_ret = cast("datetime", ret_at)
            ret_str = (
                saved_ret
                if saved_ret is not None and parse_timestamp(saved_ret) == dt_ret
                else format_timestamp(dt_ret)
            )
        if any(k in sel_map for k in ("_selector", "_external_source_id", "_retrieved_at")):
            sel_val = deepcopy(sel_map.get("_selector"))
    elif ret_at is not None:
        ret_str = format_timestamp(cast("datetime", ret_at))
    ref: MaterialRef = {
        "material_id": str(mat_uid), "key": cast("str", m[1]).removeprefix("material/"),
        "title": cast("str", m[2]), "kind": m_kind, "role": eff_role,
        "required_for": [str(stage) for stage in cast("list[str]", m[5] or [])],
        "freshness": freshness, "file_version_id": fvid,
        "mount": cast("str | None", m[10]), "path": cast("str | None", m[11]),
        "url": cast("str | None", m[12]), "retrieved_at": ret_str,
        "content_digest": cast("str | None", m[14]), "selector": sel_val,
        "why": cast("str | None", m[8]), "applies_to": applies_keys,
        "applies_to_entity_ids": applies_ids, "is_global": bool(m[9]), "external_source_id": ext_source_id,
    }  # fmt: skip
    return mat_uid, ref


def _load_reads(conn: psycopg.Connection, rev_id: RevisionId) -> dict[tuple[UUID, str], list[JsonObject]]:
    reads_by_owner: dict[tuple[UUID, str], list[JsonObject]] = defaultdict(list)
    for r in conn.execute(_SELECT_READS, (rev_id,)).fetchall():
        uid, purp, t_kind = cast("UUID", r[0]), cast("str", r[1]), cast("str", r[2])
        req_b, why_s = cast("bool", r[11]), cast("str", r[12])
        if t_kind == "repository_path":
            doc = mp.zip_compact(
                ("kind", "mount", "path", "section", "why", "required"), (t_kind, *r[3:6], why_s, req_b)
            )
        elif t_kind in ("material", "plan_entity", "artifact"):
            if t_kind == "material":
                ref = cast("str", r[6]) if r[7] is None else f"{cast('str', r[6])}#{cast('str', r[7])}"
            elif t_kind == "plan_entity":
                ref = cast("str", r[8])
            else:
                ak = cast("str", r[9])
                ref = ak if ak.startswith("artifact/") else f"artifact/{ak}"
            doc = mp.zip_compact(("kind", "ref", "why", "required"), (t_kind, ref, why_s, req_b))
        else:
            doc = mp.zip_compact(
                ("kind", "url", "why", "required", "external_source_id"), (t_kind, r[10], why_s, req_b, r[5])
            )
        reads_by_owner[(uid, purp)].append(doc)
    return reads_by_owner


def _load_phases(
    conn: psycopg.Connection,
    rev_id: RevisionId,
    deps: Mapping[UUID, list[str]],
    reads: Mapping[tuple[UUID, str], list[JsonObject]],
) -> list[JsonValue]:
    batch_items: dict[tuple[UUID, str], list[str]] = defaultdict(list)
    for bm in conn.execute(_SELECT_BATCH_MEMBERS, (rev_id,)).fetchall():
        batch_items[(cast("UUID", bm[0]), cast("str", bm[1]))].append(cast("str", bm[2]))
    batches_by_phase: dict[UUID, list[JsonObject]] = defaultdict(list)
    for b in conn.execute(_SELECT_BATCHES, (rev_id,)).fetchall():
        pid, b_key = cast("UUID", b[0]), cast("str", b[1])
        b_vals = (b_key, batch_items.get((pid, b_key), []), b[2], b[3])
        batches_by_phase[pid].append(mp.zip_compact(("key", "items", "mode", "note"), b_vals))
    phases_doc: list[JsonValue] = []
    for p in conn.execute(_SELECT_PHASES, (rev_id,)).fetchall():
        p_uid = cast("UUID", p[0])
        supp, btch = reads.get((p_uid, "supporting"), []), batches_by_phase.get(p_uid, [])
        p_obj = mp.zip_compact(
            mp.PHASE_KEYS, (str(p_uid), *p[1:7], p[8] or None, *p[9:13], supp, btch, p[13])
        )
        if cast("bool", p[7]):
            p_obj["depends_on"] = list(deps.get(p_uid, []))
        phases_doc.append(p_obj)
    return phases_doc


def _load_reviews(conn: psycopg.Connection, rev_id: RevisionId) -> dict[UUID, JsonObject]:
    reviews_by_item: dict[UUID, JsonObject] = {}
    r_keys = ("mode", "profile", "independence", "reviewer", "max_rounds", "covers", "required_evidence")
    for r in conn.execute(_SELECT_REVIEWS, (rev_id,)).fetchall():
        oid, r_mode = cast("UUID", r[0]), cast("str", r[1])
        if r_mode == "required":
            ev = list(cast("list[str]", r[7] or []))
            reviews_by_item[oid] = mp.zip_compact(
                r_keys, ("required", r[2], r[3] or "separate_session", *r[4:7], ev)
            )
        elif r_mode == "self":
            reviews_by_item[oid] = {"mode": "self", "reason": cast("str", r[8])}
        else:
            reviews_by_item[oid] = {
                "mode": "waived",
                "reason": cast("str", r[8]),
                "waived_by": cast("str", r[9]),
            }
    return reviews_by_item


def _load_items(
    conn: psycopg.Connection,
    rev_id: RevisionId,
    deps: Mapping[UUID, list[str]],
    impls: Mapping[UUID, list[str]],
    item_decisions: Mapping[UUID, list[str]],
    reads: Mapping[tuple[UUID, str], list[JsonObject]],
    hints: Mapping[UUID, list[JsonObject]],
) -> list[JsonValue]:
    reviews_by_item = _load_reviews(conn, rev_id)
    relations_by_item: dict[UUID, list[JsonObject]] = defaultdict(list)
    for rel in conn.execute(_SELECT_RELATIONS, (rev_id,)).fetchall():
        relations_by_item[cast("UUID", rel[0])].append(
            mp.zip_compact(("target", "relation", "note"), rel[1:4])
        )
    artifacts_by_item: dict[UUID, list[JsonObject]] = defaultdict(list)
    for art in conn.execute(_SELECT_ARTIFACTS, (rev_id,)).fetchall():
        artifacts_by_item[cast("UUID", art[0])].append(
            mp.zip_compact(("key", "role", "mount", "path", "note"), art[1:6])
        )
    skills_by_item: dict[UUID, list[JsonObject]] = defaultdict(list)
    for sk in conn.execute(_SELECT_SKILLS, (rev_id,)).fetchall():
        skills_by_item[cast("UUID", sk[0])].append(mp.zip_compact(("key", "version"), sk[1:3]))

    def build_item(row: mp.Row) -> JsonObject:
        item_uid, a_kind = cast("UUID", row[0]), cast("str", row[8])
        auth_obj: JsonObject = (
            {"kind": "routine"}
            if a_kind == "routine"
            else mp.zip_compact(("kind", "gate", "label", "scope"), row[8:12])
        )
        clean_sections: list[JsonValue] = []
        res_meta: Mapping[str, JsonValue] | None = None
        for sec_item in cast("list[JsonValue]", row[19] or []):
            if isinstance(sec_item, dict) and "_research" in sec_item:
                res_meta = cast("Mapping[str, JsonValue]", sec_item["_research"])
            else:
                clean_sections.append(sec_item)
        res_need, res_q = cast("str", row[12]), cast("str | None", row[13])
        res_notes = None if res_meta is None else res_meta.get("notes")
        res_obj = (
            mp.zip_compact(("need", "question", "notes"), (res_need, res_q, res_notes))
            if (res_need != "none" or res_q is not None or res_meta is not None)
            else None
        )
        links = (
            deps.get(item_uid, []), relations_by_item.get(item_uid, []), impls.get(item_uid, []),
            item_decisions.get(item_uid, []), skills_by_item.get(item_uid, []),
            reads.get((item_uid, "read"), []), reads.get((item_uid, "example"), []),
            hints.get(item_uid, []), artifacts_by_item.get(item_uid, []),
            reviews_by_item[item_uid], auth_obj, res_obj, clean_sections,
        )  # fmt: skip
        i_obj = mp.zip_compact(mp.ITEM_KEYS, (str(item_uid), *row[1:8], *row[14:19], *links))
        wp = mp.work_policy_from_sql(row[20])
        if wp is not None:
            i_obj["work_policy"] = work_policy_to_doc(wp)
        return i_obj

    return [build_item(r) for r in conn.execute(_SELECT_ITEMS, (rev_id,)).fetchall()]


def _load_units(
    conn: psycopg.Connection,
    rev_id: RevisionId,
    deps: Mapping[UUID, list[str]],
    impls: Mapping[UUID, list[str]],
    reads: Mapping[tuple[UUID, str], list[JsonObject]],
    ws_by_unit: Mapping[UUID, list[JsonObject]],
    outs: Mapping[UUID, list[JsonObject]],
    ref_forms: Mapping[str, JsonValue],
) -> list[JsonValue]:
    unit_checks = _group_str(conn.execute(_SELECT_UNIT_CHECKS, (rev_id,)).fetchall())
    mp.apply_ref_override(ref_forms, "unit_checks", unit_checks)
    p_forms = ref_forms.get("parent")
    p_map: Mapping[str, JsonValue] = (
        cast("Mapping[str, JsonValue]", p_forms) if isinstance(p_forms, Mapping) else {}
    )
    units_doc: list[JsonValue] = []
    for u in conn.execute(_SELECT_UNITS, (rev_id,)).fetchall():
        uid = cast("UUID", u[0])
        u_links = (
            cast("str | None", p_map.get(str(uid), u[3])), ws_by_unit.get(uid, []),
            reads.get((uid, "read"), []), deps.get(uid, []), unit_checks.get(uid, []),
            outs.get(uid, []), impls.get(uid, []), u[12],
        )  # fmt: skip
        u_obj = mp.zip_compact(mp.UNIT_KEYS, (str(uid), u[1], *u[4:12], *u_links))
        u_wp = mp.work_policy_from_sql(u[13])
        if u_wp is not None:
            u_obj["work_policy"] = work_policy_to_doc(u_wp)
        units_doc.append(u_obj)
    return units_doc


def _load_decisions_and_materials(
    conn: psycopg.Connection,
    rev_id: RevisionId,
    dec_applies: Mapping[UUID, list[str]],
    ref_forms: Mapping[str, JsonValue],
) -> tuple[list[JsonValue], list[JsonValue]]:
    dec_supersedes = _group_str(conn.execute(_SELECT_DEC_SUPERSESSIONS, (rev_id,)).fetchall())
    mp.apply_ref_override(ref_forms, "supersedes", dec_supersedes)
    decisions_doc: list[JsonValue] = []
    for d in conn.execute(_SELECT_DECISIONS, (rev_id,)).fetchall():
        dec_uid = cast("UUID", d[0])
        s_date = None if d[4] is None else cast("date", d[4]).isoformat()
        orig = None if d[13] is None else mp.zip_compact(("kind", "ref"), (d[13], d[14]))
        d_tail = (
            dec_applies.get(dec_uid, []), True if cast("bool", d[11]) else None,
            dec_supersedes.get(dec_uid, []), d[12], orig, d[15], d[16],
        )  # fmt: skip
        decisions_doc.append(
            mp.zip_compact(mp.DEC_KEYS, (str(dec_uid), d[1], d[2], d[3], s_date, *d[5:11], *d_tail))
        )

    mat_applies = _group_str(conn.execute(_SELECT_MAT_BINDINGS, (rev_id,)).fetchall())
    mp.apply_ref_override(ref_forms, "mat_applies", mat_applies)
    materials_doc: list[JsonValue] = []
    for row in conn.execute(_SELECT_MATERIALS, (rev_id,)).fetchall():
        mat_uid, ref = _decode_material(row, [], [])
        vals = (
            ref["material_id"], *(ref[k] for k in mp.MAT_KEYS[1:15]),
            mat_applies.get(mat_uid, []), True if ref["is_global"] else None, ref["external_source_id"],
        )  # fmt: skip
        materials_doc.append(mp.zip_compact(mp.MAT_KEYS, vals))
    return decisions_doc, materials_doc


def _load_graph_maps(
    conn: psycopg.Connection, rev_id: RevisionId, ref_forms: Mapping[str, JsonValue]
) -> tuple[dict[UUID, list[str]], ...]:
    deps: dict[UUID, list[str]] = defaultdict(list)
    for dep_row in conn.execute(_SELECT_DEPS, (rev_id,)).fetchall():
        if not cast("bool", dep_row[3]):
            deps[cast("UUID", dep_row[0])].append(cast("str", dep_row[1]))

    req_owners: dict[UUID, list[str]] = defaultdict(list)
    impls: dict[UUID, list[str]] = defaultdict(list)
    crit_reqs: dict[UUID, list[str]] = defaultdict(list)
    for rl in conn.execute(_SELECT_REQ_LINKS, (rev_id,)).fetchall():
        ent_id, ent_key = cast("UUID", rl[0]), cast("str", rl[1])
        req_id, req_key, rel = cast("UUID", rl[2]), cast("str", rl[3]), cast("str", rl[4])
        if rel == "owns":
            req_owners[req_id].append(ent_key)
        elif rel == "implements":
            impls[ent_id].append(req_key)
        elif rel == "verifies":
            crit_reqs[ent_id].append(req_key)

    dec_applies: dict[UUID, list[str]] = defaultdict(list)
    item_decisions: dict[UUID, list[str]] = defaultdict(list)
    for db_row in conn.execute(_SELECT_DEC_BINDINGS, (rev_id,)).fetchall():
        if cast("str", db_row[4]) == "applies_to":
            dec_applies[cast("UUID", db_row[0])].append(cast("str", db_row[3]))
        else:
            item_decisions[cast("UUID", db_row[2])].append(cast("str", db_row[1]))

    for bucket, target in (
        ("depends_on", deps), ("owners", req_owners), ("implements", impls),
        ("requirements", crit_reqs), ("dec_applies", dec_applies), ("decisions", item_decisions),
    ):  # fmt: skip
        mp.apply_ref_override(ref_forms, bucket, target)
    return deps, req_owners, impls, crit_reqs, dec_applies, item_decisions


def load_typed_document(conn: psycopg.Connection, revision_id: RevisionId) -> SpecificationDoc:
    """Reconstruct ``SpecificationDoc`` from relational tables without reading ``revision_payloads``."""
    return mp.run(lambda: _read_all(conn, revision_id))


def load_revision_pins(conn: psycopg.Connection, revision_id: RevisionId) -> tuple[MaterialPin, ...]:
    """Read immutable ``file_version`` pins for ``revision_id`` from ``revision_file_bindings``."""
    return mp.run(lambda: _read_pins(conn, revision_id))


def _read_pins(conn: psycopg.Connection, revision_id: RevisionId) -> tuple[MaterialPin, ...]:
    if conn.execute(_SELECT_REV_EXISTS, (revision_id,)).fetchone() is None:
        raise mp.not_found("revision", revision_id)
    return tuple(
        MaterialPin(
            material_id=EntityId(cast("UUID", row[0])),
            file_version_id=cast("UUID", row[1]),
            role=cast("str", row[2]),
            selector=deepcopy(cast("JsonValue | None", row[3])),
        )
        for row in conn.execute(_SELECT_PINS, (revision_id,)).fetchall()
    )


def load_revision_materials(conn: psycopg.Connection, revision_id: RevisionId) -> tuple[MaterialRef, ...]:
    """Read revision materials with pinned ``file_version_id`` and entity bindings (planning §5.11, §11.4)."""
    return mp.run(lambda: _read_materials(conn, revision_id))


def _read_materials(conn: psycopg.Connection, revision_id: RevisionId) -> tuple[MaterialRef, ...]:
    if conn.execute(_SELECT_REV_EXISTS, (revision_id,)).fetchone() is None:
        raise mp.not_found("revision", revision_id)
    applies_ids: dict[UUID, list[JsonValue]] = defaultdict(list)
    applies_keys: dict[UUID, list[JsonValue]] = defaultdict(list)
    for mb in conn.execute(_SELECT_MAT_BINDINGS_FULL, (revision_id,)).fetchall():
        mat_uid = cast("UUID", mb[0])
        applies_ids[mat_uid].append(str(cast("UUID", mb[1])))
        applies_keys[mat_uid].append(cast("str", mb[2]))
    return tuple(
        _decode_material(
            row,
            list(applies_keys.get(cast("UUID", row[0]), [])),
            list(applies_ids.get(cast("UUID", row[0]), [])),
        )[1]
        for row in conn.execute(_SELECT_MATERIALS, (revision_id,)).fetchall()
    )


def revisions_for_file_version(conn: psycopg.Connection, file_version_id: UUID) -> tuple[RevisionId, ...]:
    """Return revisions pinning ``file_version_id`` newest-first (planning §11.4)."""
    rows = mp.run(lambda: conn.execute(_SELECT_REVS_FOR_FILE_VERSION, (file_version_id,)).fetchall())
    return tuple(RevisionId(cast("UUID", row[0])) for row in rows)


def _read_all(conn: psycopg.Connection, revision_id: RevisionId) -> SpecificationDoc:
    rev_row = conn.execute(_SELECT_REV_SPEC, (revision_id,)).fetchone()
    if rev_row is None:
        raise mp.not_found("revision", revision_id)

    (
        title,
        goal,
        context_md,
        non_goals,
        rules,
        brief,
        design_brief_id,
        exec_constraints,
        sections,
        extensions,
    ) = rev_row
    clean_rev_sec: list[JsonValue] = []
    ref_forms: Mapping[str, JsonValue] = {}
    for sec_item in cast("list[JsonValue]", sections or []):
        if isinstance(sec_item, dict) and "_ref_forms" in sec_item:
            ref_forms = cast("Mapping[str, JsonValue]", sec_item["_ref_forms"])
        else:
            clean_rev_sec.append(sec_item)

    deps, r_owners, impls, crit_reqs, dec_applies, item_decisions = _load_graph_maps(
        conn, revision_id, ref_forms
    )
    hints: dict[UUID, list[JsonObject]] = defaultdict(list)
    ws_by_unit: dict[UUID, list[JsonObject]] = defaultdict(list)
    outs_by_unit: dict[UUID, list[JsonObject]] = defaultdict(list)
    for p in conn.execute(_SELECT_PATHS, (revision_id,)).fetchall():
        eid, p_role = cast("UUID", p[0]), cast("str", p[1])
        if p_role == "change_hint":
            hints[eid].append(mp.zip_compact(("mount", "pattern", "change", "note"), p[2:6]))
        elif p_role == "declared_write_scope":
            ws_by_unit[eid].append({"mount": cast("str", p[2]), "pattern": cast("str", p[3])})
        else:
            outs_by_unit[eid].append(mp.zip_compact(("mount", "path", "note"), (p[2], p[3], p[5])))

    reads = _load_reads(conn, revision_id)
    phases_doc = _load_phases(conn, revision_id, deps, reads)
    items_doc = _load_items(conn, revision_id, deps, impls, item_decisions, reads, hints)
    units_doc = _load_units(conn, revision_id, deps, impls, reads, ws_by_unit, outs_by_unit, ref_forms)
    req_keys = ("id", "key", "statement", "priority", "source", "owners")
    reqs_doc: list[JsonValue] = [
        mp.zip_compact(
            req_keys,
            (
                str(r[0]),
                *r[1:4],
                mp.zip_compact(("kind", "ref"), r[4:6]),
                r_owners.get(cast("UUID", r[0]), []),
            ),
        )
        for r in conn.execute(_SELECT_REQUIREMENTS, (revision_id,)).fetchall()
    ]
    checks_doc: list[JsonValue] = [
        mp.zip_compact(mp.CHECK_KEYS, (str(c[0]), *c[1:10]))
        for c in conn.execute(_SELECT_CHECKS, (revision_id,)).fetchall()
    ]
    c_chks = _group_str(conn.execute(_SELECT_CRIT_CHECKS, (revision_id,)).fetchall())
    mp.apply_ref_override(ref_forms, "crit_checks", c_chks)
    criteria_doc: list[JsonValue] = [
        mp.zip_compact(
            mp.CRIT_KEYS,
            (str(a[0]), *a[1:5], c_chks.get(cast("UUID", a[0]), []), crit_reqs.get(cast("UUID", a[0]), [])),
        )
        for a in conn.execute(_SELECT_CRITERIA, (revision_id,)).fetchall()
    ]
    decisions_doc, materials_doc = _load_decisions_and_materials(conn, revision_id, dec_applies, ref_forms)
    plan_rels_doc: list[JsonValue] = [
        mp.zip_compact(("kind", "target", "note"), pr[0:3])
        for pr in conn.execute(_SELECT_PLAN_RELATIONS, (revision_id,)).fetchall()
    ]
    top_opt = mp.zip_compact(
        ("context_md", "non_goals", "rules", "brief", "requirements", "design_brief_id"),
        (context_md, non_goals, rules, brief, reqs_doc, str(design_brief_id) if design_brief_id else None),
    )
    mid_opt = mp.zip_compact(
        ("units", "criteria", "checks", "decisions", "materials", "plan_relations"),
        (units_doc, criteria_doc, checks_doc, decisions_doc, materials_doc, plan_rels_doc),
    )
    assembled: JsonObject = {
        "schema": SPECIFICATION_URN,
        "title": cast("str", title),
        "goal": cast("str", goal),
        **top_opt,
        "phases": phases_doc,
        "items": items_doc,
        **mid_opt,
        "execution_constraints": cast("JsonValue", exec_constraints),
        **compact({"sections": clean_rev_sec}),
    }
    if isinstance(extensions, dict) and extensions:
        assembled["extensions"] = cast("JsonValue", extensions)

    spec_model, _ = from_document(assembled)
    return to_document(spec_model)
