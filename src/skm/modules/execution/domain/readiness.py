"""Deterministic readiness and freshness (execution §§4.3, 5.12).

The caller supplies observations and immutable identities; this module performs no
lookups. Runtime availability belongs to admission and never to the freshness digest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import EntityId, PlanId, PrincipalId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.path_globs import globs_overlap
from skm.modules.execution.domain.ids import ReadinessReportId
from skm.modules.execution.domain.work_policy import work_policy_from_json

if TYPE_CHECKING:
    from typing import Literal

    from skm.modules.execution.domain.contracts import BudgetEstimate, ReadinessAudit
    from skm.modules.execution.domain.work_policy import EffectiveWorkPolicy

READINESS_VALIDATOR_VERSION: Final = 2
PROGRESSIVE_MODE: Final = "progressive_per_phase"
RULES: Final = (
    "R01_graph",
    "R02_detail",
    "R03_criteria_linked",
    "R04_requirements_covered",
    "R05_checkouts",
    "R06_materials",
    "R07_capabilities",
    "R08_write_scopes",
    "R09_budget",
    "R10_verifiers",
    "R11_policy",
    "R12_semantic",
    "R13_gates",
    "R15_design_research",
)


class ReadinessStatus(StrEnum):
    READY = "ready"
    READY_WITH_ADVISORIES = "ready_with_advisories"
    NOT_READY = "not_ready"


@dataclass(frozen=True, slots=True)
class ReadinessInputs:
    requirements: str
    dependencies: str
    write_scopes: str
    criteria: str
    capability_requirements: str
    policy: str
    config: str
    resources: str
    materials: str


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    """Material inputs captured together by the application in its transaction.

    Routing here is requirements, never online workers, installations or quotas.
    Resource facts include both versioned resources and the selected pack versions.
    Config is the prospective frozen document, after authorized run overrides.
    """

    revision: JsonObject
    graph: JsonObject
    selection: JsonObject | None
    compiled_keys: tuple[str, ...]
    satisfied: JsonObject
    capability_requirements: JsonObject
    policy_digest: str
    config_snapshot: JsonObject
    resource_pins: JsonObject
    materials: JsonObject
    start_request: JsonObject
    work_policies: Mapping[str, EffectiveWorkPolicy]


def snapshot_readiness_inputs(snapshot: ReadinessSnapshot) -> ReadinessInputs:
    """Hash the exact material closure of a preview without invocation identities."""
    revision = cast("dict[str, Any]", snapshot.revision)
    graph = cast("dict[str, Any]", snapshot.graph)
    return ReadinessInputs(
        requirements=canonical_digest(
            {
                "requirements": revision.get("requirements", []),
                "criteria": revision.get("criteria", []),
                "implements": {
                    str(item["key"]): item.get("implements", []) for item in revision.get("items", [])
                },
            }
        ),
        dependencies=canonical_digest(
            {
                "edges": graph.get("edges", []),
                "batch_groups": graph.get("batch_groups", []),
                "selection": snapshot.selection,
                "compiled_keys": list(snapshot.compiled_keys),
                "satisfied": snapshot.satisfied,
            }
        ),
        write_scopes=canonical_digest(
            {
                str(task["task_key"]): {
                    "write_scope": task.get("write_scope"),
                    "change_hints": task.get("change_hints", []),
                }
                for task in graph.get("tasks", [])
            }
        ),
        criteria=canonical_digest(revision.get("checks", [])),
        capability_requirements=canonical_digest(snapshot.capability_requirements),
        policy=snapshot.policy_digest,
        config=canonical_digest(
            {
                "registry_digest": snapshot.config_snapshot.get("registry_digest"),
                "values": snapshot.config_snapshot.get("values"),
                "start_request": snapshot.start_request,
                "work_policies": {
                    key: policy.digest for key, policy in sorted(snapshot.work_policies.items())
                },
            }
        ),
        resources=canonical_digest(snapshot.resource_pins),
        materials=canonical_digest(snapshot.materials),
    )


@dataclass(frozen=True, slots=True)
class ReadinessScope:
    kind: Literal["plan", "phases", "selection"]
    phase_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadinessFinding:
    code: str
    severity: Literal["error", "advisory"]
    entity_id: EntityId | None
    message: str
    rule_id: str


@dataclass(frozen=True, slots=True)
class ReadinessCheckResult:
    rule_id: str
    outcome: Literal["passed", "failed", "advisory", "skipped"]
    findings_count: int


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    id: ReadinessReportId
    workspace_id: WorkspaceId
    project_id: ProjectId
    plan_id: PlanId
    revision_id: RevisionId
    revision_digest: str
    status: ReadinessStatus
    scope: ReadinessScope
    inputs: ReadinessInputs
    inputs_digest: str
    policy_digest: str
    results: tuple[ReadinessCheckResult, ...]
    findings: tuple[ReadinessFinding, ...]
    assumptions: tuple[str, ...]
    structural_counts: Mapping[str, int]
    start_request: JsonObject | None
    work_policies: Mapping[str, EffectiveWorkPolicy] | None
    estimate: BudgetEstimate
    audit: ReadinessAudit | None
    supersedes_report_id: ReadinessReportId | None
    validator_version: int
    created_by: PrincipalId
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RevisionVisa:
    id: UUID
    workspace_id: WorkspaceId
    plan_id: PlanId
    revision_id: RevisionId
    readiness_report_id: ReadinessReportId
    selection: JsonObject | None
    signed_by: PrincipalId
    reason: str
    signed_at: datetime


def readiness_inputs_digest(inputs: ReadinessInputs, validator_version: int) -> str:
    return canonical_digest({"inputs": asdict(inputs), "validator_version": validator_version})


def canonical_digest(value: object) -> str:
    """Canonical material JSON, excluding clocks, generation and runtime observations."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_start_request(
    overrides: JsonObject, selection: JsonObject | None, *, mode: JsonValue = None
) -> JsonObject:
    normalized: JsonObject | None = None
    if selection is not None:
        normalized = {
            "task_keys": list[JsonValue](sorted(set(cast("list[str]", selection.get("task_keys") or [])))),
            "phases": list[JsonValue](sorted(set(cast("list[str]", selection.get("phases") or [])))),
            **({"stop_after": selection["stop_after"]} if selection.get("stop_after") is not None else {}),
        }
    request: JsonObject = {"overrides": dict(overrides), "selection": normalized}
    if mode == PROGRESSIVE_MODE:
        if normalized is None or not any(
            normalized.get(field) for field in ("task_keys", "phases", "stop_after")
        ):
            raise error_for(
                ErrorCode.SCHEMA_INVALID, "progressive execution requires selected phases or tasks"
            )
        request["mode"] = PROGRESSIVE_MODE
    return request


def changed_inputs(report: ReadinessReport, inputs: ReadinessInputs) -> tuple[str, ...]:
    """Parts whose current material inputs differ; legacy previews never admit a start."""
    parts = [name for name in asdict(inputs) if getattr(report.inputs, name) != getattr(inputs, name)]
    if report.validator_version != READINESS_VALIDATOR_VERSION:
        parts.append("validator_version")
    if report.start_request is None:
        parts.append("start_request")
    if report.work_policies is None:
        parts.append("work_policies")
    return tuple(parts)


def design_research_refs(item: JsonObject) -> tuple[str, ...] | None:
    """Read the opt-in design-research section. An empty tuple means invalid evidence."""
    sections = cast("list[JsonObject]", item.get("sections") or [])
    design = next((section for section in sections if section["id"] == "design-research"), None)
    if design is None:
        return None
    lines = [line.strip() for line in str(design["text"]).splitlines() if line.strip()]
    if len(lines) > 16:
        return ()
    refs: list[str] = []
    for line in lines:
        prefix, _, ref = line.removeprefix("- ").partition(":")
        try:
            if prefix != "research-query" or str(UUID(ref)) != ref or ref in refs:
                return ()
        except ValueError:
            return ()
        refs.append(ref)
    return tuple(refs)


def evaluate_readiness(inputs: JsonObject) -> ReadinessReport:  # noqa: PLR0912, PLR0915 -- ordered readiness rules
    """Evaluate readiness from supplied spec and server observations.

    ``material_inputs`` contains the nine independently hashed freshness parts.
    ``checks`` and ``tasks`` are normalized revision documents; observation facts
    use explicit booleans. An absent required policy/capability observation fails
    closed. The application owns binding these observations to the pinned revision.
    """
    data = cast("dict[str, Any]", inputs)
    findings: list[ReadinessFinding] = []
    assumptions: list[str] = list(data.get("assumptions", []))
    tasks = data.get("tasks", [])
    checks = data.get("checks", [])
    criteria = data.get("criteria", [])
    requirements = data.get("requirements", [])
    results: list[ReadinessCheckResult] = []

    def add(rule: str, code: str, message: str, *, error: bool = True, entity: Any = None) -> None:
        findings.append(
            ReadinessFinding(
                code,
                "error" if error else "advisory",
                None if entity is None else EntityId(UUID(str(entity))),
                message,
                rule,
            )
        )

    if not tasks:
        add("R01_graph", "NO_TASKS", "the execution graph is empty")
    if _cyclic(tasks, data.get("edges", [])):
        add("R01_graph", "DEPENDENCY_CYCLE", "execution dependencies form a cycle")
    for phase in data.get("phases", []):
        if phase.get("design_state", phase.get("detail_state", phase.get("state"))) != "detailed":
            add("R02_detail", "PHASE_SKELETON", "phase must be detailed", entity=phase.get("id"))
    if data.get("require_acceptance_links", True):
        check_refs = {str(check[name]) for check in checks for name in ("id", "key") if name in check}
        check_refs.update(
            f"{check['owner']}:{check['key']}" for check in checks if "owner" in check and "key" in check
        )
        linked = {str(ref) for check in checks for ref in check.get("criterion_ids", [])}
        linked.update(
            str(ref)
            for task in tasks
            if task.get("review") == "required"
            for ref in task.get("criterion_ids", task.get("criteria", []))
        )
        for criterion in criteria:
            review_verified = criterion.get("verification_mode") == "review" and any(
                task.get("review") == "required" and task.get("task_key") == criterion.get("owner")
                for task in tasks
            )
            if (
                str(criterion.get("id")) not in linked
                and str(criterion.get("key")) not in linked
                and not criterion.get("verified_by")
                and not set(map(str, criterion.get("checks", []))) & check_refs
                and not review_verified
            ):
                add(
                    "R03_criteria_linked",
                    "CRITERION_UNVERIFIED",
                    "criterion has no check or review",
                    entity=criterion.get("id"),
                )
    covered = {str(ref) for item in data.get("items", []) for ref in item.get("implements", [])}
    for requirement in requirements:
        rid = str(requirement.get("id"))
        rkey = str(requirement.get("key"))
        has_criteria = any(
            {rid, rkey} & set(map(str, c.get("requirements", c.get("requirement_ids", [])))) for c in criteria
        )
        if not {rid, rkey} & covered or not has_criteria:
            add(
                "R04_requirements_covered",
                "REQUIREMENT_UNCOVERED",
                "requirement lacks implementation or criteria",
                error=bool(data.get("require_coverage", False)),
                entity=requirement.get("id"),
            )
    for check in checks:
        if check.get("kind") in {"command", "shell"} and not check.get("checkout_bound", False):
            add("R05_checkouts", "CHECKOUT_UNBOUND", "checkout availability requires a host", error=False)
            assumptions.append("checkout binding must be checked on the selected host")
    for material in data.get("materials", []):
        if "execution" not in material.get("required_for", []):
            continue
        if material.get("available") is not True:
            add("R06_materials", "FILE_VERSION_NOT_READY", "required material is unavailable")
        elif material.get("fresh") is not True:
            add("R06_materials", "MATERIAL_STALE", "required material is stale")
    for role, routed in data.get("routing", {}).items():
        if routed.get("available") is not True:
            add("R07_capabilities", "CAPABILITY_UNAVAILABLE", f"no admissible route for {role}")
    for role in set(data.get("required_roles", [])) - set(data.get("routing", {})):
        add("R07_capabilities", "CAPABILITY_UNAVAILABLE", f"route observation missing for {role}")
    for overlap in data.get("write_scope_overlaps", []):
        add("R08_write_scopes", "WRITE_SCOPE_OVERLAP", str(overlap), error=False)
    if data.get("estimate_over", False):
        add(
            "R09_budget",
            "BUDGET_ESTIMATE_OVER",
            "estimate exceeds a configured hard budget",
            error=bool(data.get("block_on_over", False)),
        )
    for check in checks:
        if check.get("kind") == "manual" and not check.get("verifier_available", False):
            add("R10_verifiers", "NO_VERIFIER", "manual check needs an available verifier", error=False)
    if data.get("policy_live_ok") is not True:
        add("R11_policy", "POLICY_DENIES", "current policy does not permit execution")
    policies = data.get("work_policies")
    if not isinstance(policies, dict) or "@default" not in policies:
        add("R11_policy", "POLICY_DENIES", "complete work policy preview is required")
    parsed_policies: dict[str, EffectiveWorkPolicy] = {}
    if isinstance(policies, dict):
        policy_documents = cast("dict[str, JsonObject]", policies)
        for key, value in policy_documents.items():
            parsed_policies[key] = work_policy_from_json(value)
        if set(data.get("compiled_keys", [])) - set(policy_documents):
            add("R11_policy", "POLICY_DENIES", "work policies must cover every compiled task")
    audit = data.get("audit")
    if audit is not None:
        verdict = audit.get("verdict")
        if verdict in {"red", "attention"}:
            add(
                "R12_semantic",
                "SEMANTIC_AUDIT_" + verdict.upper(),
                "semantic audit requires attention",
                error=verdict == "red",
            )
        for item in audit.get("checklist", []):
            if item.get("outcome") in {"concern", "blocker"}:
                add(
                    "R12_semantic",
                    "SEMANTIC_" + str(item["item_id"]).upper(),
                    str(item.get("note", "")),
                    error=item["outcome"] == "blocker",
                )
    for task in tasks:
        if task.get("gate_required") and task.get("gate_supported") is not True:
            add("R13_gates", "GATE_UNSUPPORTED_BY_WORKFLOW", "required gate has no applicable workflow stage")
    designs = tuple(
        (item, refs) for item in data.get("items", []) if (refs := design_research_refs(item)) is not None
    )
    for item, refs in designs:
        if not refs or any(ref not in data.get("design_research_evidence", {}) for ref in refs):
            add(
                "R15_design_research",
                "DESIGN_RESEARCH_EVIDENCE_REQUIRED",
                "design research must cite available, policy-admitted research evidence",
                entity=item.get("id"),
            )
    for rule in RULES:
        subset = [finding for finding in findings if finding.rule_id == rule]
        outcome = (
            "failed" if any(f.severity == "error" for f in subset) else "advisory" if subset else "passed"
        )
        if (rule == "R12_semantic" and audit is None) or (rule == "R15_design_research" and not designs):
            outcome = "skipped"
        results.append(ReadinessCheckResult(rule, outcome, len(subset)))
    material_inputs = ReadinessInputs(**data["material_inputs"])
    status = readiness_status(tuple(findings))
    return ReadinessReport(
        id=ReadinessReportId(UUID(data["id"])),
        workspace_id=WorkspaceId(UUID(data["workspace_id"])),
        project_id=ProjectId(UUID(data["project_id"])),
        plan_id=PlanId(UUID(data["plan_id"])),
        revision_id=RevisionId(UUID(data["revision_id"])),
        revision_digest=data["revision_digest"],
        status=status,
        scope=ReadinessScope(
            data.get("scope", {}).get("kind", "plan"), tuple(data.get("scope", {}).get("phase_keys", []))
        ),
        inputs=material_inputs,
        inputs_digest=readiness_inputs_digest(material_inputs, READINESS_VALIDATOR_VERSION),
        policy_digest=material_inputs.policy,
        results=tuple(results),
        findings=tuple(findings),
        assumptions=tuple(dict.fromkeys(assumptions)),
        structural_counts={
            "tasks": len(tasks),
            "edges": len(data.get("edges", [])),
            "checks": len(checks),
            "manual_checks": sum(c.get("kind") == "manual" for c in checks),
            "roles": len(data.get("routing", {})),
            "gates": sum(bool(t.get("gate_required")) for t in tasks),
        },
        start_request=data.get("start_request"),
        work_policies=parsed_policies or None,
        estimate=data.get("estimate", {}),
        audit=audit,
        supersedes_report_id=None
        if data.get("supersedes_report_id") is None
        else ReadinessReportId(UUID(data["supersedes_report_id"])),
        validator_version=READINESS_VALIDATOR_VERSION,
        created_by=PrincipalId(UUID(data["created_by"])),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def readiness_status(findings: tuple[ReadinessFinding, ...]) -> ReadinessStatus:
    if any(f.severity == "error" for f in findings):
        return ReadinessStatus.NOT_READY
    return ReadinessStatus.READY_WITH_ADVISORIES if findings else ReadinessStatus.READY


def freshness(report: ReadinessReport, inputs: ReadinessInputs) -> bool:
    return not changed_inputs(report, inputs)


def require_fresh(
    report: ReadinessReport,
    inputs: ReadinessInputs,
    *,
    now: datetime,
    max_age_seconds: int,
    start_request: JsonObject,
    revision_digest: str,
) -> None:
    stale = list(changed_inputs(report, inputs))
    if report.inputs_digest != readiness_inputs_digest(report.inputs, report.validator_version):
        stale.append("inputs_digest")
    if report.policy_digest != report.inputs.policy:
        stale.append("policy_digest")
    if report.revision_digest != revision_digest:
        stale.append("revision_digest")
    if (now - report.created_at).total_seconds() > max_age_seconds:
        stale.append("age")
    if report.start_request != start_request:
        stale.append("start_request_changed")
    expected_scope = "selection" if start_request.get("mode") == PROGRESSIVE_MODE else "plan"
    if stale or report.status is ReadinessStatus.NOT_READY or report.scope.kind != expected_scope:
        raise error_for(
            ErrorCode.READINESS_REQUIRED,
            "a fresh readiness preview for this execution scope is required",
            details={
                "stale_parts": list[JsonValue](stale),
                "reason": "start_request_changed" if "start_request_changed" in stale else "readiness_stale",
            },
        )


def write_scope_overlaps(
    tasks: Sequence[Mapping[str, JsonValue]], edges: Sequence[Mapping[str, JsonValue]]
) -> list[str]:
    """R08 facts: tasks whose declared write scopes may share a path while neither depends on the other.

    ``tasks`` and ``edges`` are the compiled execution graph (``write_scope`` as ``{mount, pattern}``
    entries, edges as ``dependent`` <- ``prerequisite``). Only overlaps that can be named are reported:
    gate tasks write nothing and an unknown (``None``) scope is serialized by the scheduler instead.
    """
    scopes: dict[str, list[tuple[str, str]]] = {}
    for task in tasks:
        raw = task.get("write_scope")
        if isinstance(raw, list):
            scopes[str(task.get("task_key"))] = [
                (str(entry.get("mount")), str(entry.get("pattern")))
                for entry in raw
                if isinstance(entry, dict)
            ]
    prerequisites: dict[str, set[str]] = {}
    for edge in edges:
        prerequisites.setdefault(str(edge.get("dependent")), set()).add(str(edge.get("prerequisite")))
    keys = sorted(scopes)
    before = {key: _prerequisites_of(key, prerequisites) for key in keys}
    overlaps: list[str] = []
    for index, first in enumerate(keys):
        for second in keys[index + 1 :]:
            if first in before[second] or second in before[first]:
                continue
            shared = sorted(
                {
                    f"{mount}:{pattern}"
                    for mount, pattern in scopes[first]
                    for other_mount, other_pattern in scopes[second]
                    if mount == other_mount and globs_overlap(pattern, other_pattern)
                }
            )
            if shared:
                overlaps.append(f"{first} and {second} may both write {', '.join(shared)}")
    return overlaps


def _prerequisites_of(key: str, prerequisites: Mapping[str, set[str]]) -> set[str]:
    """Every task ``key`` transitively depends on."""
    found: set[str] = set()
    pending = list(prerequisites.get(key, ()))
    while pending:
        current = pending.pop()
        if current not in found:
            found.add(current)
            pending.extend(prerequisites.get(current, ()))
    return found


def _cyclic(tasks: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bool:
    keys = {str(task.get("task_key", task.get("id"))) for task in tasks}
    dependencies: dict[str, set[str]] = {key: set() for key in keys}
    for edge in edges:
        dependent = str(edge.get("dependent", edge.get("dependent_key")))
        prerequisite = str(edge.get("prerequisite", edge.get("prerequisite_key")))
        dependencies.setdefault(dependent, set()).add(prerequisite)
        dependencies.setdefault(prerequisite, set())
    while dependencies:
        leaves = {key for key, refs in dependencies.items() if not refs}
        if not leaves:
            return True
        dependencies = {key: refs - leaves for key, refs in dependencies.items() if key not in leaves}
    return False
