"""Phase readiness certificates, bound to semantic inputs rather than execution state.

The material table is documented in docs/plan-structure.md. Keep its exclusions here
shared by recording and status; a claim must not invalidate its own certificate.
"""
from __future__ import annotations

import copy
from typing import Callable, Iterable

from planner import integration
from planner.integration import plugins

from . import lifecycle, ops, schema, settings, store
from .model import PlanError
from .query import revision_of

READY = ("ready", "ready_with_advisories")
VERDICTS = (*READY, "not_ready")


def _without(doc: dict, fields: Iterable[str]) -> dict:
    return {k: copy.deepcopy(v) for k, v in doc.items() if k not in fields}


def _plan_part(plan: store.Plan) -> dict:
    return _without(plan.plan, ops.OWNED_FIELDS["plan"] | {"pause", "phases", "readiness", "settings"})


def _brief_part(plan: store.Plan) -> dict:
    return _without(plan.brief, {"$schema"})


def _phase_part(plan: store.Plan, phase_id: str) -> dict:
    return _without(plan.phases[phase_id], ops.OWNED_FIELDS["phase"] | {"readiness"})


def _items_part(plan: store.Plan, phase_id: str) -> dict:
    result = {}
    for key in lifecycle.phase_items(plan, phase_id):
        doc = _without(plan.items[key], ops.OWNED_FIELDS["item"])
        if isinstance(doc.get("artifacts"), list):
            doc["artifacts"] = [a for a in doc["artifacts"] if not (
                isinstance(a, dict) and a.get("role") == "input"
                and str(a.get("path", "")).startswith("@plan/inputs/"))]
            if not doc["artifacts"]:
                doc.pop("artifacts")
        if isinstance(doc.get("rag"), dict):
            doc["rag"] = _without(doc["rag"], {"status", "captures"})
            if not doc["rag"]:
                doc.pop("rag")
        result[key] = doc
    return result


def _units_part(plan: store.Plan, items: dict) -> dict:
    return {key: _without(doc, ops.OWNED_FIELDS["unit"]) for key, doc in sorted(plan.units.items())
            if key.split("/", 1)[0] in items}


def _reaches(doc: dict, targets: set[str]) -> bool:
    return doc.get("global") is True or bool(targets.intersection(doc.get("applies_to") or []))


def _decisions_part(plan: store.Plan, targets: set[str], items: dict) -> dict:
    explicit = {ref for item in items.values() for ref in item.get("decisions", [])}
    return {key: _without(doc, {"$schema"}) for key, doc in sorted(plan.decisions.items())
            if key in explicit or _reaches(doc, targets)}


def _documents_part(plan: store.Plan, targets: set[str], items: dict) -> dict:
    explicit = set()
    for item in items.values():
        for read in item.get("reads", []):
            ref = read.get("ref", "").split("#", 1)[0]
            path = read.get("path", "")
            if ref.startswith("knowledge/"):
                explicit.add(ref.removeprefix("knowledge/"))
            if path.startswith("@plan/knowledge/") and path.endswith(".json"):
                explicit.add(path.removeprefix("@plan/knowledge/").removesuffix(".json"))
    return {key: copy.deepcopy(doc) for key, doc in sorted(plan.documents.items())
            if not key.startswith(("audit-", "readiness-")) and (key in explicit or _reaches(doc, targets))}


def semantic_digest(plan: store.Plan, phase_id: str) -> str:
    lifecycle._need_phase(plan, phase_id)
    items = _items_part(plan, phase_id)
    targets = {phase_id, *items}
    return revision_of({"plan": _plan_part(plan), "brief": _brief_part(plan),
                        "phase": _phase_part(plan, phase_id), "items": items,
                        "units": _units_part(plan, items), "decisions": _decisions_part(plan, targets, items),
                        "documents": _documents_part(plan, targets, items)})


def policy_digest(plan: store.Plan) -> str:
    return revision_of({"settings": plan.plan.get("settings", {}), "planner_version": plugins.planner_version()})


def status(plan: store.Plan, phase_id: str | None = None) -> dict:
    if phase_id is not None:
        phase = lifecycle._need_phase(plan, phase_id)
        if phase.get("design") != "detailed":
            raise PlanError("PHASE_NOT_DETAILED", f"{phase_id} is a skeleton; detail it before readiness")
    rows = []
    policy = policy_digest(plan)
    for key in ([phase_id] if phase_id else lifecycle.phase_order(plan)):
        phase = plan.phases[key]
        if phase.get("design") != "detailed":
            continue
        digest = semantic_digest(plan, key)
        certificate = phase.get("readiness")
        if "readiness" in phase:
            registry = schema.load_registry()
            node, owner = registry.resolve(schema.SCHEMA_URN_PREFIX + "phase:v1#/$defs/readiness", "")
            problems = list(schema.validate_node(registry, node, owner, certificate))
            if problems:
                raise PlanError("SCHEMA_INVALID", f"{key} readiness certificate is invalid", problems)
        changed = [name for name, value in (("digest", digest), ("policy", policy))
                   if certificate and certificate.get("policy_digest" if name == "policy" else name) != value]
        state = "missing" if not certificate else "stale" if changed else certificate["status"]
        rows.append({"id": key, "status": state, "digest": digest, "policy_digest": policy,
                     "certificate": copy.deepcopy(certificate), "changed": changed})
    result = {"$schema": schema.SCHEMA_URN_PREFIX + "read-readiness:v1",
              "plan": plan.plan.get("id", plan.root.name), "phases": rows}
    store.check_doc(result, "read-readiness", "readiness status")
    return result


def gate(plan: store.Plan, phase_id: str) -> dict | None:
    policy = plan.plan.get("settings")
    if not isinstance(policy, dict) or policy.get("design_audit") != "required":
        return None
    row = status(plan, phase_id)["phases"][0]
    return row if row["status"] not in READY else None


def require(plan: store.Plan, phase_id: str) -> None:
    row = gate(plan, phase_id)
    if row is None:
        return
    if row["status"] == "missing":
        raise PlanError("READINESS_REQUIRED", f"{phase_id} needs a readiness certificate; run plan-audit")
    if row["status"] == "stale":
        raise PlanError("READINESS_STALE", f"{phase_id} readiness changed: {', '.join(row['changed'])}; run plan-audit")
    raise PlanError("READINESS_NOT_READY", f"{phase_id} audit is not ready; resolve its findings and run plan-audit")


def _external_checks(plan: store.Plan) -> list:
    config = settings.for_plan(plan)
    if not integration.available() or not config.get("checks.external"):
        return []
    project = settings.project_root_of(plan.root.parent)
    payload = plugins.build_input(plan_id=plan.plan["id"], short_id=plan.plan["short_id"], plan_dir=plan.root,
                                  plans_root=plan.root.parent, project_root=project)
    failure = "error" if config.get("checks.external_failure") == "error" else "warning"
    return plugins.run_checks(payload, project=project, failure=failure)


def _counts(issues: list) -> dict:
    return {"errors": sum(i.level == "error" for i in issues), "warnings": sum(i.level == "warning" for i in issues)}


def record(plan, phase_id: str, *, verdict: str, audit: str, actor: dict,
           findings: Iterable[dict] = (), external: Callable | None = None) -> dict:
    """Validate and record under the lifecycle lock; external checks see the same fresh snapshot."""
    from . import check

    with lifecycle._mutation(plan) as (p, lock):
        phase = lifecycle._need_phase(p, phase_id)
        if phase.get("design") != "detailed":
            raise PlanError("PHASE_NOT_DETAILED", f"{phase_id} is a skeleton; detail it before readiness")
        if not audit.startswith("knowledge/") or audit.removeprefix("knowledge/") not in p.documents:
            raise PlanError("REF_UNKNOWN", f"unknown audit document {audit!r}")
        internal = [i for i in check.check(p) if check.owner_phase(p, i) in {None, phase_id}]
        outside = [i for i in (external or _external_checks)(p) if check.owner_phase(p, i) in {None, phase_id}]
        structural = {**_counts(internal), "external": _counts(outside)}
        if verdict in READY and (structural["errors"] or structural["external"]["errors"]):
            raise PlanError("READINESS_STRUCTURAL_ERRORS", f"{phase_id} has structural or external check errors")
        certificate = {"status": verdict, "digest": semantic_digest(p, phase_id), "policy_digest": policy_digest(p),
                       "validator_version": plugins.planner_version(), "checked_at": store.now(),
                       "structural": structural,
                       "audit": {"ref": audit, "verdict": {"ready": "GREEN", "ready_with_advisories": "ATTENTION",
                                                           "not_ready": "RED"}.get(verdict, verdict)},
                       "findings": list(findings), "actor": dict(actor),
                       "independent": actor.get("provider") != p.plan.get("authoring", {}).get("provider")}
        doc = {**copy.deepcopy(phase), "readiness": certificate}
        store.check_doc(doc, "phase", phase_id)
        if verdict in READY and any(f["blocking"] or f["severity"] in {"blocker", "major"} for f in certificate["findings"]):
            raise PlanError("READINESS_BLOCKING_FINDINGS", f"{phase_id} has blocking or Major+ audit findings")
        event = store.new_event("readiness_recorded", f"{phase_id} readiness {verdict}", actor, phase=phase_id)
        lifecycle._commit(p, [("phase", phase_id, doc)], [event], lock)
    return certificate
