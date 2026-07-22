"""Frozen D86 instruction catalog, semantic validation, and public operations.

The semantic gate is deliberately independent from P2 observation.  Invalid catalog,
fragment, parity, extension, or compatibility input never reaches artifact planning.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from typing import Mapping

from core.provider import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel
from core.provider_artifact import (
    ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource, ArtifactTarget,
    canonical_json_bytes, plan_artifact_render, sha256_digest,
)
from core.provider_lock import (
    ArtifactActionKind, ArtifactLock, ArtifactPlan, DriftObservation, apply_plan,
    parse_lock, plan_artifact_lock,
)


CONTRACT_VERSION = "1.0.0"
CATALOG_VERSION = "1.0.0"
PROVIDERS = ("claude-code", "codex")
SCOPES = ("root", "skiller", "harness", "maind", "analyst", "task")
TARGETS = {
    "root": {"claude-code": "CLAUDE.md", "codex": "AGENTS.md"},
    "skiller": {"claude-code": "packages/skiller/CLAUDE.md", "codex": "packages/skiller/AGENTS.md"},
    "harness": {"claude-code": "packages/harness/CLAUDE.md", "codex": "packages/harness/AGENTS.md"},
    "maind": {"claude-code": "packages/maind/CLAUDE.md", "codex": "packages/maind/AGENTS.md"},
    "analyst": {"claude-code": "packages/analyst/CLAUDE.md", "codex": "packages/analyst/AGENTS.md"},
    "task": {"claude-code": "packages/task/CLAUDE.md", "codex": "packages/task/AGENTS.md"},
}
COMMON_IDS = {
    "root": ("root.ecosystem-identity", "root.repository-layout", "root.package-boundaries",
             "root.cli-routing", "root.shared-core", "root.marketplace",
             "root.engineering-invariants", "root.plan-lifecycle",
             "root.development-validation", "root.reference-provenance",
             "root.decision-verification"),
    "skiller": ("skiller.identity", "skiller.distribution-channels",
                "skiller.configuration-ownership", "skiller.core-policy",
                "skiller.layout-and-generation", "skiller.module-boundaries",
                "skiller.engineering-invariants", "skiller.validation-release"),
    "harness": ("harness.identity", "harness.semantic-source", "harness.layout",
                "harness.command-surface", "harness.agent-pack-lifecycle",
                "harness.engineering-invariants", "harness.cross-package-boundaries",
                "harness.validation-release"),
    "maind": ("maind.identity", "maind.three-planes", "maind.layout",
              "maind.module-boundaries", "maind.orchestration",
              "maind.engineering-invariants", "maind.validation-release"),
    "analyst": ("analyst.identity-human-gate", "analyst.layer-boundary", "analyst.layout",
                "analyst.module-boundaries", "analyst.data-lifecycle", "analyst.privacy",
                "analyst.engineering-invariants", "analyst.validation-release"),
    "task": ("task.identity", "task.command-catalog", "task.plan-protocol", "task.layout",
             "task.schema-ownership", "task.engineering-invariants",
             "task.validation-release"),
}
EXTENSION_IDS = {
    ("root", "claude-code"): ("root.claude-code.native-surfaces",
                              "root.claude-code.context-budget",
                              "root.claude-code.research-routing"),
    ("root", "codex"): ("root.codex.bootstrap", "root.codex.launch-and-hook-integrity",
                        "root.codex.fresh-agent-execution"),
    ("skiller", "claude-code"): ("skiller.claude-code.marketplace-connect",
                                 "skiller.claude-code.vendor-targets",
                                 "skiller.claude-code.agent-hub"),
    ("harness", "claude-code"): ("harness.claude-code.config-surfaces",
                                 "harness.claude-code.lifecycle-surfaces",
                                 "harness.claude-code.settings-precedence"),
    ("maind", "claude-code"): ("maind.claude-code.plugin-and-mcp",
                               "maind.claude-code.workspace-trust"),
    ("analyst", "claude-code"): ("analyst.claude-code.capture-surfaces",
                                 "analyst.claude-code.plugin"),
    ("task", "claude-code"): ("task.claude-code.slash-projection",
                              "task.claude-code.model-pins"),
}
for _scope in SCOPES:
    for _provider in PROVIDERS:
        EXTENSION_IDS.setdefault((_scope, _provider), ())

DIAGNOSTIC_CODES = frozenset({
    "INSTRUCTION_SCOPE_INVALID", "INSTRUCTION_TARGET_SET_MISMATCH",
    "INSTRUCTION_SEMANTIC_ID_MISSING", "INSTRUCTION_SEMANTIC_ID_DUPLICATE",
    "INSTRUCTION_SEMANTIC_ORDER_INVALID", "INSTRUCTION_EXTENSION_ID_INVALID",
    "INSTRUCTION_EXTENSION_CONFLICT", "INSTRUCTION_TARGET_MISSING",
    "INSTRUCTION_OWNERSHIP_CONFLICT", "INSTRUCTION_BOUNDARY_INVALID",
    "INSTRUCTION_PROVENANCE_INVALID", "INSTRUCTION_STALE_SOURCE",
    "INSTRUCTION_MANAGED_DRIFT", "INSTRUCTION_PARITY_MISMATCH",
    "INSTRUCTION_COMPATIBILITY_MISMATCH", "INSTRUCTION_WRITE_FORBIDDEN",
})
OBSERVATION_CODES = frozenset({
    "semantic-invalid", "semantic-conflict", "missing", "clean", "stale-source",
    "managed-drift", "boundary-invalid", "provenance-invalid", "ownership-conflict",
    "write-forbidden",
})
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_TAG = re.compile(r"^<!-- instruction:([a-z][a-z0-9.-]*) -->$", re.M)
_SECTION_FIELDS = {
    "id", "scope_id", "kind", "provider_id", "order", "intent", "obligations",
    "sources", "compatibility_assertions",
}
_DIAGNOSTIC_FIELDS = (
    "severity", "code", "scope_id", "provider_id", "target_path", "artifact_id",
    "observation", "semantic_id", "expected", "observed", "next_action", "message",
)


@dataclass(frozen=True)
class InstructionDiagnostic:
    severity: str
    code: str
    scope_id: str | None
    provider_id: str | None
    target_path: str | None
    artifact_id: str | None
    observation: str | None
    semantic_id: str | None
    expected: str | None
    observed: str | None
    next_action: str | None
    message: str | None

    def __post_init__(self) -> None:
        if self.severity != "error" or self.code not in DIAGNOSTIC_CODES:
            raise ValueError("unknown instruction diagnostic")
        if self.observation is not None and self.observation not in OBSERVATION_CODES:
            raise ValueError("unknown instruction observation")

    def as_dict(self) -> dict[str, str | None]:
        return {field: getattr(self, field) for field in _DIAGNOSTIC_FIELDS}


class InstructionValidationError(ValueError):
    """Internal convenience surface; public operations return the diagnostics."""

    def __init__(self, diagnostics: tuple[InstructionDiagnostic, ...]):
        self.diagnostics = _ordered_diagnostics(diagnostics)
        super().__init__(", ".join(item.code for item in self.diagnostics))


@dataclass(frozen=True)
class InstructionRequest:
    contract_version: str
    catalog_version: str
    operation_id: str
    scope_ids: tuple[str, ...]
    provider_ids: tuple[str, ...]
    target_root: str
    config_provenance: tuple[tuple[str, str], ...]
    authorization_provenance: tuple[tuple[str, str], ...]
    authorized_target_paths: tuple[str, ...] = ()
    observed_hashes: tuple[tuple[str, str], ...] = ()
    preimage_destination: str | None = None


@dataclass(frozen=True)
class InstructionProjection:
    scope_id: str
    provider_id: str
    target_path: str
    common_ids: tuple[str, ...]
    extension_ids: tuple[str, ...]
    result: object


@dataclass(frozen=True)
class InstructionTargetResult:
    artifact_id: str
    scope_id: str
    provider_id: str
    target_path: str
    ordered_semantic_ids: tuple[str, ...]
    observation: str
    action: str
    source_hash: str
    render_hash: str
    marker_ids: tuple[str, ...]
    block_ids: tuple[str, ...]
    diagnostics: tuple[InstructionDiagnostic, ...]
    changed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id, "scope_id": self.scope_id,
            "provider_id": self.provider_id, "target_path": self.target_path,
            "ordered_semantic_ids": list(self.ordered_semantic_ids),
            "observation": self.observation, "action": self.action,
            "source_hash": self.source_hash, "render_hash": self.render_hash,
            "marker_ids": list(self.marker_ids), "block_ids": list(self.block_ids),
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "changed": self.changed,
        }


@dataclass(frozen=True)
class InstructionOperationResult:
    request: InstructionRequest
    targets: tuple[InstructionTargetResult, ...]
    diagnostics: tuple[InstructionDiagnostic, ...]
    green: bool
    artifact_plan: ArtifactPlan | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "request": {
                "contract_version": self.request.contract_version,
                "catalog_version": self.request.catalog_version,
                "operation_id": self.request.operation_id,
                "scope_ids": list(self.request.scope_ids),
                "provider_ids": list(self.request.provider_ids),
                "target_root": self.request.target_root,
                "config_provenance": dict(self.request.config_provenance),
                "authorization_provenance": dict(self.request.authorization_provenance),
                "authorized_target_paths": list(self.request.authorized_target_paths),
                "observed_hashes": dict(self.request.observed_hashes),
                "preimage_destination": self.request.preimage_destination,
            },
            "targets": [item.as_dict() for item in self.targets],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "green": self.green,
        }


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def catalog_path() -> Path:
    return package_root() / "configs/common/instructions/catalog.json"


def contract_path() -> Path:
    return repository_root() / "plans/2026.07.19-DUAL-PROVIDER/root/contracts/provider-instruction-contract.md"


def compatibility_path() -> Path:
    return package_root() / "tests/fixtures_data/instruction-compatibility-v1.json"


def load_catalog(path: Path | None = None) -> dict[str, object]:
    try:
        value = json.loads((path or catalog_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstructionValidationError((_diag(
            "INSTRUCTION_PROVENANCE_INVALID", observation="provenance-invalid",
            expected="canonical catalog JSON", observed=type(error).__name__,
            next_action="restore the frozen catalog"),)) from error
    diagnostics = validate_catalog(value)
    if diagnostics:
        raise InstructionValidationError(diagnostics)
    return value


def validate_catalog(value: object) -> tuple[InstructionDiagnostic, ...]:
    """Validate D86 exact inventories, records, fragments, conflicts, and fixture."""
    diagnostics: list[InstructionDiagnostic] = []
    if not isinstance(value, dict) or set(value) != {
            "contract_version", "catalog_version", "capability_requirements", "scopes"}:
        return (_diag("INSTRUCTION_SCOPE_INVALID", expected="D86 catalog envelope",
                      observed=_shape(value)),)
    if value["contract_version"] != CONTRACT_VERSION or value["catalog_version"] != CATALOG_VERSION:
        diagnostics.append(_diag(
            "INSTRUCTION_PROVENANCE_INVALID", observation="provenance-invalid",
            expected=f"{CONTRACT_VERSION}/{CATALOG_VERSION}",
            observed=f"{value['contract_version']}/{value['catalog_version']}",
            next_action="use the frozen contract and catalog versions"))
    scopes = value["scopes"]
    if not isinstance(scopes, list):
        return _ordered_diagnostics(tuple(diagnostics) + (_diag(
            "INSTRUCTION_TARGET_SET_MISMATCH", expected="six ordered scope records",
            observed=_shape(scopes)),))
    scope_ids = tuple(item.get("id") if isinstance(item, dict) else None for item in scopes)
    if len(set(scope_ids)) != len(scope_ids):
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", expected="unique scope IDs",
                                 observed=_display(scope_ids)))
    if scope_ids != SCOPES:
        diagnostics.append(_diag("INSTRUCTION_TARGET_SET_MISMATCH",
                                 expected=_display(SCOPES), observed=_display(scope_ids)))
    records_by_id: dict[str, dict] = {}
    normalized_by_kind: dict[tuple[str, str | None], dict[tuple[str, ...], str]] = {}
    for scope_index, scope_id in enumerate(SCOPES):
        if scope_index >= len(scopes) or not isinstance(scopes[scope_index], dict):
            continue
        scope = scopes[scope_index]
        if scope.get("id") != scope_id:
            continue
        if set(scope) != {"id", "claude_target", "codex_target", "sections"}:
            diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                     expected="scope record fields", observed=_shape(scope)))
            continue
        observed_targets = (scope["claude_target"], scope["codex_target"])
        expected_targets = (TARGETS[scope_id]["claude-code"], TARGETS[scope_id]["codex"])
        if observed_targets != expected_targets:
            diagnostics.append(_diag("INSTRUCTION_TARGET_SET_MISMATCH", scope_id=scope_id,
                                     expected=_display(expected_targets),
                                     observed=_display(observed_targets)))
        sections = scope["sections"]
        if not isinstance(sections, list):
            diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                     expected="ordered semantic records", observed=_shape(sections)))
            continue
        raw_ids = tuple(record.get("id") if isinstance(record, dict) else None for record in sections)
        duplicate_ids = sorted({item for item in raw_ids if item is not None and raw_ids.count(item) > 1})
        for semantic_id in duplicate_ids:
            diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ID_DUPLICATE", scope_id=scope_id,
                                     semantic_id=semantic_id, expected="unique ID",
                                     observed="duplicate"))
        for record in sections:
            if not isinstance(record, dict) or set(record) != _SECTION_FIELDS:
                diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                         expected="semantic record fields",
                                         observed=_shape(record)))
                continue
            semantic_id = record["id"]
            if not isinstance(semantic_id, str):
                diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                         observed=_shape(semantic_id)))
                continue
            if semantic_id in records_by_id and semantic_id not in duplicate_ids:
                diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ID_DUPLICATE",
                                         scope_id=scope_id, semantic_id=semantic_id))
            records_by_id[semantic_id] = record
            _validate_record(record, scope_id, diagnostics, normalized_by_kind)
        _validate_inventory(scope_id, sections, diagnostics)
        _validate_fragments(scope_id, sections, diagnostics)
        _validate_conflicts(scope_id, sections, diagnostics)
    _validate_compatibility_fixture(records_by_id, diagnostics)
    return _ordered_diagnostics(tuple(diagnostics))


def plan_instructions(request: InstructionRequest, *,
                      catalog: dict[str, object] | None = None) -> InstructionOperationResult:
    request_diagnostics = _validate_request(request, {"plan"})
    if request_diagnostics:
        return InstructionOperationResult(request, (), request_diagnostics, False)
    try:
        value = load_catalog() if catalog is None else catalog
        semantic_diagnostics = validate_catalog(value)
    except InstructionValidationError as error:
        semantic_diagnostics = error.diagnostics
        value = None
    if semantic_diagnostics:
        return InstructionOperationResult(request, (), semantic_diagnostics, False)
    return _observe(request, value)


def check_instructions(request: InstructionRequest, *,
                       catalog: dict[str, object] | None = None) -> InstructionOperationResult:
    request_diagnostics = _validate_request(request, {"check"})
    if request_diagnostics:
        return InstructionOperationResult(request, (), request_diagnostics, False)
    planned = plan_instructions(replace(request, operation_id="plan"), catalog=catalog)
    return replace(planned, request=request)


def apply_instructions(request: InstructionRequest, *,
                       catalog: dict[str, object] | None = None) -> InstructionOperationResult:
    diagnostics = _validate_request(request, {"apply", "update"}, write=True)
    if diagnostics:
        return InstructionOperationResult(request, (), diagnostics, False)
    fresh = plan_instructions(replace(request, operation_id="plan"), catalog=catalog)
    if fresh.artifact_plan is None:
        return replace(fresh, request=request)
    writable = tuple(action for action in fresh.artifact_plan.actions
                     if action.action is not ArtifactActionKind.NOOP)
    if (any(action.action not in {ArtifactActionKind.CREATE, ArtifactActionKind.UPDATE}
            for action in writable)
            or tuple(action.target_path for action in writable) != request.authorized_target_paths):
        return _write_refusal(request, fresh, "authorized missing/create or stale-source/update targets")
    if not writable:
        return replace(fresh, request=request, green=True)
    try:
        apply_plan(Path(request.target_root), fresh.artifact_plan)
    except (OSError, TypeError, ValueError) as error:
        return _write_refusal(request, fresh, type(error).__name__)
    return _completed_write(request, fresh, writable)


def repair_instructions(request: InstructionRequest, *,
                        catalog: dict[str, object] | None = None) -> InstructionOperationResult:
    diagnostics = _validate_request(request, {"repair"}, write=True)
    if diagnostics:
        return InstructionOperationResult(request, (), diagnostics, False)
    probe = plan_instructions(replace(request, operation_id="plan"), catalog=catalog)
    if probe.artifact_plan is None:
        return replace(probe, request=request)
    drift = tuple(action for action in probe.artifact_plan.actions
                  if action.observation is DriftObservation.MANAGED_DRIFT)
    observed = dict(request.observed_hashes)
    if (not drift or tuple(action.target_path for action in drift) != request.authorized_target_paths
            or request.preimage_destination != "adjacent-backup"
            or any(observed.get(action.target_path) != action.observed_hash for action in drift)):
        return _write_refusal(request, probe, "explicit drift hashes and adjacent-backup pre-image")
    value = load_catalog() if catalog is None else catalog
    repaired_probe = _observe(replace(request, operation_id="plan"), value,
                              repairs=tuple(action.artifact_id for action in drift))
    if repaired_probe.artifact_plan is None or any(
            action.action not in {ArtifactActionKind.NOOP, ArtifactActionKind.REPAIR}
            for action in repaired_probe.artifact_plan.actions):
        return _write_refusal(request, repaired_probe, "managed-drift repair only")
    try:
        apply_plan(Path(request.target_root), repaired_probe.artifact_plan)
    except (OSError, TypeError, ValueError) as error:
        return _write_refusal(request, repaired_probe, type(error).__name__)
    writable = tuple(action for action in repaired_probe.artifact_plan.actions
                     if action.action is ArtifactActionKind.REPAIR)
    return _completed_write(request, repaired_probe, writable)


def plan(root: Path, *, repairs: tuple[str, ...] = (),
         catalog: dict[str, object] | None = None) -> tuple[tuple[InstructionProjection, ...], ArtifactPlan]:
    """Backward-compatible convenience wrapper; explicit catalogs are still validated."""
    value = load_catalog() if catalog is None else catalog
    diagnostics = validate_catalog(value)
    if diagnostics:
        raise InstructionValidationError(diagnostics)
    request = default_request("plan", root)
    result = _observe(request, value, repairs=repairs)
    if result.artifact_plan is None:
        raise InstructionValidationError(result.diagnostics)
    projections = _projections(value, request.scope_ids, request.provider_ids)
    return projections, result.artifact_plan


def check(root: Path, *, catalog: dict[str, object] | None = None):
    return plan(root, catalog=catalog)


def apply(root: Path, artifact_plan: ArtifactPlan, *, authorized_targets: tuple[str, ...]) -> ArtifactPlan:
    writable = tuple(action for action in artifact_plan.actions
                     if action.action is not ArtifactActionKind.NOOP)
    if (any(action.action not in {ArtifactActionKind.CREATE, ArtifactActionKind.UPDATE}
            for action in writable)
            or tuple(action.target_path for action in writable) != authorized_targets):
        raise InstructionValidationError((_diag(
            "INSTRUCTION_WRITE_FORBIDDEN", observation="write-forbidden",
            expected="authorized create/update set", observed=_display(authorized_targets)),))
    return apply_plan(_absolute_root(root), artifact_plan)


def repair(root: Path, artifact_plan: ArtifactPlan, *, authorized_targets: tuple[str, ...]) -> ArtifactPlan:
    writable = tuple(action for action in artifact_plan.actions
                     if action.action is not ArtifactActionKind.NOOP)
    if (not writable or any(action.action is not ArtifactActionKind.REPAIR for action in writable)
            or tuple(action.target_path for action in writable) != authorized_targets):
        raise InstructionValidationError((_diag(
            "INSTRUCTION_WRITE_FORBIDDEN", observation="write-forbidden",
            expected="authorized repair set", observed=_display(authorized_targets)),))
    return apply_plan(_absolute_root(root), artifact_plan)


def default_request(operation_id: str, root: Path) -> InstructionRequest:
    return InstructionRequest(
        CONTRACT_VERSION, CATALOG_VERSION, operation_id, SCOPES, PROVIDERS,
        str(_absolute_root(root)), (("source", "explicit-test-config"),),
        (("authority", "synthetic-temp-root"),),
    )


def operator_reference(catalog: dict[str, object] | None = None) -> str:
    value = load_catalog() if catalog is None else catalog
    diagnostics = validate_catalog(value)
    if diagnostics:
        raise InstructionValidationError(diagnostics)
    lines = ["# Provider instructions", "", "Generated from the validated D86 catalog.", "",
             "| Scope | Claude target | Codex target | Common IDs | Claude extensions | Codex extensions |",
             "|:--|:--|:--|--:|--:|--:|"]
    for scope_id in SCOPES:
        lines.append(
            f"| `{scope_id}` | `{TARGETS[scope_id]['claude-code']}` | "
            f"`{TARGETS[scope_id]['codex']}` | {len(COMMON_IDS[scope_id])} | "
            f"{len(EXTENSION_IDS[(scope_id, 'claude-code')])} | "
            f"{len(EXTENSION_IDS[(scope_id, 'codex')])} |")
    lines += ["", "The frozen inventory contains 49 common and 18 provider-extension IDs "
              "(67 total) across exactly 12 targets.", "",
              "## Public API", "",
              "`InstructionRequest` carries contract/catalog versions, operation ID, explicit "
              "ordered scope/provider IDs, an absolute target root, and config/authorization "
              "provenance. `InstructionTargetResult` carries artifact/scope/provider/path, "
              "ordered semantic IDs, observation/action, source/render hashes, marker/block "
              "IDs, ordered structured diagnostics, and `changed`. "
              "`InstructionOperationResult` adds aggregate diagnostics and `green`.", "",
              "The public operations are `plan_instructions`, `check_instructions`, "
              "`apply_instructions`, and `repair_instructions`; their serialized result is "
              "available through `as_dict()` without reinterpretation.", "",
              "`plan` and `check` are no-write. `apply` requires explicit authorization "
              "for a missing create or stale-source update; `repair` requires explicit "
              "managed-drift hashes and an adjacent recoverable pre-image. Existing unmarked "
              "or unlocked files are ownership conflicts.", ""]
    return "\n".join(lines)


def _observe(request: InstructionRequest, value: dict[str, object], *,
             repairs: tuple[str, ...] = ()) -> InstructionOperationResult:
    root = Path(request.target_root)
    projections = _projections(value, request.scope_ids, request.provider_ids)
    projection_diagnostics = _validate_projection_semantics(value, projections)
    if projection_diagnostics:
        return InstructionOperationResult(request, (), projection_diagnostics, False)
    lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
    lock_bytes = lock_path.read_bytes() if lock_path.is_file() else None
    codecs = {item.result.provenance.artifact_id: _codec(item.scope_id, item.provider_id)
              for item in projections}
    artifact_plan = plan_artifact_lock(
        root, tuple(item.result for item in projections), lock_bytes=lock_bytes,
        repair_artifact_ids=repairs, managed_block_codecs=codecs)
    artifact_plan = _instruction_observation_corrections(root, artifact_plan, lock_bytes)
    artifact_plan = _preserve_unselected_lock(artifact_plan, lock_bytes)
    actions_by_id = {action.artifact_id: action for action in artifact_plan.actions}
    target_results = tuple(
        _target_result(projection, actions_by_id[projection.result.provenance.artifact_id])
        for projection in projections)
    diagnostics = _ordered_diagnostics(tuple(
        diagnostic for target in target_results for diagnostic in target.diagnostics))
    green = not diagnostics and all(item.observation == "clean" for item in target_results)
    return InstructionOperationResult(request, target_results, diagnostics, green, artifact_plan)


def _validate_projection_semantics(value: dict[str, object],
                                   projections: tuple[InstructionProjection, ...]
                                   ) -> tuple[InstructionDiagnostic, ...]:
    """Validate rendered IDs, common parity, extensions, and compatibility before P2."""
    diagnostics = []
    records = {record["id"]: record for scope in value["scopes"]
               for record in scope["sections"]}
    by_scope = {scope_id: tuple(item for item in projections if item.scope_id == scope_id)
                for scope_id in SCOPES}
    for scope_id, scoped in by_scope.items():
        if not scoped:
            continue
        for projection in scoped:
            rendered = projection.result.managed_bytes.decode("utf-8")
            common_found = tuple(re.findall(r"<!-- semantic:([^ ]+) -->", rendered))[
                :len(projection.common_ids)]
            if common_found != COMMON_IDS[scope_id]:
                diagnostics.append(_diag(
                    "INSTRUCTION_PARITY_MISMATCH", scope_id=scope_id,
                    provider_id=projection.provider_id,
                    target_path=projection.target_path,
                    artifact_id=projection.result.provenance.artifact_id,
                    observation="semantic-invalid", expected=_display(COMMON_IDS[scope_id]),
                    observed=_display(common_found)))
            if projection.extension_ids != EXTENSION_IDS[(scope_id, projection.provider_id)]:
                diagnostics.append(_diag(
                    "INSTRUCTION_EXTENSION_ID_INVALID", scope_id=scope_id,
                    provider_id=projection.provider_id,
                    target_path=projection.target_path,
                    observed=_display(projection.extension_ids)))
            for semantic_id in projection.common_ids + projection.extension_ids:
                missing = tuple(assertion for assertion in records[semantic_id]["compatibility_assertions"]
                                if assertion not in rendered)
                if missing:
                    diagnostics.append(_diag(
                        "INSTRUCTION_COMPATIBILITY_MISMATCH", scope_id=scope_id,
                        provider_id=projection.provider_id,
                        target_path=projection.target_path,
                        artifact_id=projection.result.provenance.artifact_id,
                        observation="semantic-invalid", semantic_id=semantic_id,
                        expected=_display(missing), observed="rendered assertion missing"))
        if len(scoped) == 2:
            left, right = scoped
            if left.common_ids != right.common_ids:
                diagnostics.append(_diag(
                    "INSTRUCTION_PARITY_MISMATCH", scope_id=scope_id,
                    expected=_display(left.common_ids), observed=_display(right.common_ids)))
            for semantic_id in COMMON_IDS[scope_id]:
                obligation = tuple(tuple(record.items()) for record in records[semantic_id]["obligations"])
                if not obligation:
                    diagnostics.append(_diag(
                        "INSTRUCTION_PARITY_MISMATCH", scope_id=scope_id,
                        semantic_id=semantic_id, expected="common obligation", observed="empty"))
    return _ordered_diagnostics(tuple(diagnostics))


def _projections(value: dict[str, object], scope_ids: tuple[str, ...],
                 provider_ids: tuple[str, ...]) -> tuple[InstructionProjection, ...]:
    by_scope = {scope["id"]: scope for scope in value["scopes"]}
    return tuple(_projection(value, by_scope[scope_id], provider_id)
                 for scope_id in scope_ids for provider_id in provider_ids)


def _projection(value: dict[str, object], scope: dict, provider: str) -> InstructionProjection:
    scope_id = scope["id"]
    target = TARGETS[scope_id][provider]
    common_ids = COMMON_IDS[scope_id]
    extension_ids = EXTENSION_IDS[(scope_id, provider)]
    base = catalog_path().parent / ("root" if scope_id == "root" else f"packages/{scope_id}")
    common, extension = base / "common.md", base / f"{provider}.md"
    sources = tuple(sorted((
        _source("instruction.contract", contract_path()),
        _catalog_source(value),
        _source(f"instruction.fragment.{scope_id}.common", common),
        _source(f"instruction.fragment.{scope_id}.{provider}", extension),
    )))
    blocks = (f"instructions.{scope_id}.{provider}.common",
              f"instructions.{scope_id}.{provider}.extension")
    markers = (f"swissknifeman:instructions:{scope_id}:{provider}:common",
               f"swissknifeman:instructions:{scope_id}:{provider}:extension")
    requirements = tuple(CapabilityRequirement(CapabilityId(item["id"]), tuple(
        SupportLevel(level) for level in item["accepted_levels"]))
        for item in value["capability_requirements"])
    identity = ArtifactAdapterIdentity(
        f"harness.instruction.{provider}", "1.0.0", ProviderId(provider), "1.0.0",
        requirements)
    semantic = {
        "instruction_contract_version": CONTRACT_VERSION,
        "catalog_version": CATALOG_VERSION, "scope_id": scope_id, "provider_id": provider,
        "artifact_kind": "instruction-projection",
        "semantic_sections": {"common": common_ids, "provider_extension": extension_ids},
        "marker_ids": markers, "block_ids": blocks,
        "capabilities": ("instructions.project",), "registry": "explicit",
    }
    result = plan_artifact_render(ArtifactRenderRequest(
        f"harness.instruction-projection.{scope_id}.{provider}", sources,
        ArtifactTarget(target, ("managed-blocks", blocks)), identity, (), semantic,
        lambda _request: _managed(
            scope_id, provider, common.read_text(encoding="utf-8"),
            extension.read_text(encoding="utf-8"), common_ids, extension_ids),
        contract_version="1.1.0"))
    return InstructionProjection(scope_id, provider, target, common_ids, extension_ids, result)


def _validate_record(record: dict, scope_id: str, diagnostics: list[InstructionDiagnostic],
                     normalized_by_kind: dict) -> None:
    semantic_id = record["id"]
    kind, provider = record["kind"], record["provider_id"]
    if record["scope_id"] != scope_id or kind not in {"common", "provider-extension"}:
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                 semantic_id=semantic_id, expected=scope_id,
                                 observed=str(record["scope_id"])))
    if kind == "common" and provider is not None:
        diagnostics.append(_diag("INSTRUCTION_EXTENSION_ID_INVALID", scope_id=scope_id,
                                 provider_id=str(provider), semantic_id=semantic_id))
    if kind == "provider-extension":
        prefix = f"{scope_id}.{provider}." if provider in PROVIDERS else ""
        if provider not in PROVIDERS or not semantic_id.startswith(prefix):
            diagnostics.append(_diag("INSTRUCTION_EXTENSION_ID_INVALID", scope_id=scope_id,
                                     provider_id=provider if isinstance(provider, str) else None,
                                     semantic_id=semantic_id))
    obligations = record["obligations"]
    if not isinstance(obligations, list) or not obligations:
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                 semantic_id=semantic_id, expected="structured obligations",
                                 observed=_shape(obligations)))
    else:
        seen: set[tuple[str, ...]] = set()
        for obligation in obligations:
            if (not isinstance(obligation, dict)
                    or set(obligation) != {"modality", "subject", "action", "object", "boundary"}
                    or obligation.get("modality") not in {"must", "must-not", "may"}
                    or any(not isinstance(obligation.get(field), str)
                           or not _IDENTIFIER.fullmatch(obligation[field])
                           for field in ("subject", "action", "object", "boundary"))):
                diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                         provider_id=provider, semantic_id=semantic_id,
                                         expected="normalized obligation fields",
                                         observed=_shape(obligation)))
                continue
            normalized = tuple(obligation[field] for field in
                               ("modality", "subject", "action", "object", "boundary"))
            if normalized in seen:
                diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ID_DUPLICATE",
                                         scope_id=scope_id, provider_id=provider,
                                         semantic_id=semantic_id,
                                         observed="duplicate normalized obligation"))
            seen.add(normalized)
            owner_key = (kind, provider)
            previous = normalized_by_kind.setdefault(owner_key, {}).get(normalized)
            if previous is not None and previous != semantic_id:
                diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ID_DUPLICATE",
                                         scope_id=scope_id, provider_id=provider,
                                         semantic_id=semantic_id, expected=previous,
                                         observed="equivalent obligation under another ID"))
            normalized_by_kind[owner_key][normalized] = semantic_id
    sources = record["sources"]
    expected_fragment = _fragment_relative(scope_id, provider)
    if (not isinstance(sources, list) or len(sources) != 1
            or not isinstance(sources[0], dict)
            or set(sources[0]) != {"source_id", "path", "sha256"}
            or sources[0].get("path") != expected_fragment
            or not isinstance(sources[0].get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", sources[0]["sha256"])):
        diagnostics.append(_diag("INSTRUCTION_PROVENANCE_INVALID", scope_id=scope_id,
                                 provider_id=provider, semantic_id=semantic_id,
                                 observation="provenance-invalid",
                                 expected=expected_fragment, observed=_display(sources)))
    else:
        source_path = repository_root() / expected_fragment
        expected_hash = sha256_digest(source_path.read_bytes()).removeprefix("sha256:")
        if sources[0]["sha256"] != expected_hash:
            diagnostics.append(_diag("INSTRUCTION_PROVENANCE_INVALID", scope_id=scope_id,
                                     provider_id=provider, semantic_id=semantic_id,
                                     observation="provenance-invalid",
                                     expected=expected_hash, observed=sources[0]["sha256"]))
    if (not isinstance(record["intent"], str) or not record["intent"].strip()
            or not isinstance(record["compatibility_assertions"], list)
            or not record["compatibility_assertions"]
            or any(not isinstance(item, str) or not item
                   for item in record["compatibility_assertions"])):
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", scope_id=scope_id,
                                 provider_id=provider, semantic_id=semantic_id,
                                 expected="non-empty intent and assertions"))


def _validate_inventory(scope_id: str, sections: list, diagnostics: list) -> None:
    common = tuple(item["id"] for item in sections
                   if isinstance(item, dict) and item.get("kind") == "common")
    _compare_ids(scope_id, None, COMMON_IDS[scope_id], common, diagnostics)
    for provider in PROVIDERS:
        extension = tuple(item["id"] for item in sections
                          if isinstance(item, dict)
                          and item.get("kind") == "provider-extension"
                          and item.get("provider_id") == provider)
        _compare_ids(scope_id, provider, EXTENSION_IDS[(scope_id, provider)],
                     extension, diagnostics, extension=True)
    expected_all = set(COMMON_IDS[scope_id]).union(
        *[set(EXTENSION_IDS[(scope_id, provider)]) for provider in PROVIDERS])
    for record in sections:
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            semantic_id = record["id"]
            if semantic_id not in expected_all:
                code = ("INSTRUCTION_EXTENSION_ID_INVALID"
                        if record.get("kind") == "provider-extension"
                        else "INSTRUCTION_SEMANTIC_ORDER_INVALID")
                diagnostics.append(_diag(code, scope_id=scope_id,
                                         provider_id=record.get("provider_id"),
                                         semantic_id=semantic_id,
                                         expected="frozen D86 ID set", observed="extra ID"))
    for owner, expected in [(None, COMMON_IDS[scope_id])] + [
            (provider, EXTENSION_IDS[(scope_id, provider)]) for provider in PROVIDERS]:
        owned = [item for item in sections if isinstance(item, dict)
                 and item.get("kind") == ("common" if owner is None else "provider-extension")
                 and item.get("provider_id") == owner]
        observed_orders = tuple(item.get("order") for item in owned)
        expected_orders = tuple(range(1, len(expected) + 1))
        if observed_orders != expected_orders:
            diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ORDER_INVALID",
                                     scope_id=scope_id, provider_id=owner,
                                     expected=_display(expected_orders),
                                     observed=_display(observed_orders)))


def _compare_ids(scope_id: str, provider_id: str | None, expected: tuple[str, ...],
                 observed: tuple[str, ...], diagnostics: list, extension: bool = False) -> None:
    missing = tuple(item for item in expected if item not in observed)
    for semantic_id in missing:
        diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ID_MISSING", scope_id=scope_id,
                                 provider_id=provider_id, semantic_id=semantic_id,
                                 expected="present", observed="missing"))
    if not missing and set(observed) == set(expected) and observed != expected:
        diagnostics.append(_diag("INSTRUCTION_SEMANTIC_ORDER_INVALID", scope_id=scope_id,
                                 provider_id=provider_id, expected=_display(expected),
                                 observed=_display(observed)))
    if extension and any(not item.startswith(f"{scope_id}.{provider_id}.") for item in observed):
        diagnostics.append(_diag("INSTRUCTION_EXTENSION_ID_INVALID", scope_id=scope_id,
                                 provider_id=provider_id, expected=f"{scope_id}.{provider_id}.*",
                                 observed=_display(observed)))


def _validate_fragments(scope_id: str, sections: list, diagnostics: list) -> None:
    by_id = {item.get("id"): item for item in sections if isinstance(item, dict)}
    for provider in (None,) + PROVIDERS:
        expected_ids = COMMON_IDS[scope_id] if provider is None else EXTENSION_IDS[(scope_id, provider)]
        path = repository_root() / _fragment_relative(scope_id, provider)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            diagnostics.append(_diag("INSTRUCTION_PROVENANCE_INVALID", scope_id=scope_id,
                                     provider_id=provider, observation="provenance-invalid",
                                     expected=path.as_posix(), observed=type(error).__name__))
            continue
        found = tuple(_TAG.findall(text))
        if found != expected_ids:
            code = ("INSTRUCTION_SEMANTIC_ID_MISSING"
                    if any(item not in found for item in expected_ids)
                    else "INSTRUCTION_SEMANTIC_ORDER_INVALID")
            diagnostics.append(_diag(code, scope_id=scope_id, provider_id=provider,
                                     expected=_display(expected_ids), observed=_display(found)))
        for semantic_id in expected_ids:
            record = by_id.get(semantic_id)
            if not isinstance(record, dict):
                continue
            body = _fragment_body(text, semantic_id)
            missing = tuple(item for item in record.get("compatibility_assertions", ())
                            if item not in body)
            if missing:
                diagnostics.append(_diag("INSTRUCTION_COMPATIBILITY_MISMATCH",
                                         scope_id=scope_id, provider_id=provider,
                                         semantic_id=semantic_id,
                                         observation="semantic-invalid",
                                         expected=_display(missing),
                                         observed="fragment assertion missing"))


def _validate_conflicts(scope_id: str, sections: list, diagnostics: list) -> None:
    common = [item for item in sections if isinstance(item, dict) and item.get("kind") == "common"]
    extensions = [item for item in sections if isinstance(item, dict)
                  and item.get("kind") == "provider-extension"]
    for extension in extensions:
        for candidate in common:
            for left in extension.get("obligations", ()):
                for right in candidate.get("obligations", ()):
                    conflict = _conflict_class(left, right)
                    if conflict:
                        diagnostics.append(_diag(
                            "INSTRUCTION_EXTENSION_CONFLICT", scope_id=scope_id,
                            provider_id=extension.get("provider_id"),
                            semantic_id=extension.get("id"),
                            observation="semantic-conflict",
                            expected=f"{candidate.get('id')} remains authoritative",
                            observed=conflict,
                            next_action="revise the extension or supersede D86"))


def _conflict_class(extension: object, common: object) -> str | None:
    if not isinstance(extension, dict) or not isinstance(common, dict):
        return None
    exact = all(extension.get(field) == common.get(field)
                for field in ("modality", "subject", "action", "object", "boundary"))
    if exact:
        return "equivalent obligation under another ID"
    same_predicate = all(extension.get(field) == common.get(field)
                         for field in ("subject", "action", "object"))
    if same_predicate:
        modalities = {extension.get("modality"), common.get("modality")}
        if modalities == {"must", "must-not"}:
            return "opposite modality"
        if (extension.get("modality") == "may" and common.get("modality") == "must-not"
                and _boundary_broader_or_equal(extension.get("boundary"), common.get("boundary"))):
            return "broader permission"
        if (extension.get("modality") == common.get("modality") == "must"
                and _boundary_narrower(extension.get("boundary"), common.get("boundary"))):
            return "narrower required coverage"
    if (extension.get("subject") == common.get("subject")
            and extension.get("action") == common.get("action")
            and (_boundaries_overlap(extension.get("boundary"), common.get("boundary")))):
        return "common-owner replacement or shadow"
    return None


def _validate_compatibility_fixture(records: dict[str, dict],
                                    diagnostics: list[InstructionDiagnostic]) -> None:
    try:
        fixture = json.loads(compatibility_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        diagnostics.append(_diag("INSTRUCTION_COMPATIBILITY_MISMATCH",
                                 observation="semantic-invalid",
                                 expected="independent P5.6 fixture",
                                 observed=type(error).__name__))
        return
    if (not isinstance(fixture, dict)
            or set(fixture) != {"contract_version", "fixture_version", "provenance", "records"}
            or fixture.get("contract_version") != CONTRACT_VERSION
            or not isinstance(fixture.get("records"), list)):
        diagnostics.append(_diag("INSTRUCTION_COMPATIBILITY_MISMATCH",
                                 observation="semantic-invalid",
                                 expected="P5.6 compatibility fixture schema",
                                 observed=_shape(fixture)))
        return
    fixture_records = fixture["records"]
    fixture_ids = tuple(item.get("id") for item in fixture_records if isinstance(item, dict))
    expected_ids = tuple(item for scope_id in SCOPES for item in (
        COMMON_IDS[scope_id] + EXTENSION_IDS[(scope_id, "claude-code")]
        + EXTENSION_IDS[(scope_id, "codex")]))
    if fixture_ids != expected_ids:
        diagnostics.append(_diag("INSTRUCTION_COMPATIBILITY_MISMATCH",
                                 observation="semantic-invalid",
                                 expected=_display(expected_ids), observed=_display(fixture_ids)))
    for item in fixture_records:
        if not isinstance(item, dict) or set(item) != {"id", "provider_ids", "assertions"}:
            diagnostics.append(_diag("INSTRUCTION_COMPATIBILITY_MISMATCH",
                                     observation="semantic-invalid",
                                     expected="record-level compatibility fixture",
                                     observed=_shape(item)))
            continue
        record = records.get(item["id"])
        if record is None:
            continue
        provider_ids = PROVIDERS if record["kind"] == "common" else (record["provider_id"],)
        if (tuple(item["provider_ids"]) != provider_ids
                or tuple(item["assertions"]) != tuple(record["compatibility_assertions"])):
            diagnostics.append(_diag("INSTRUCTION_COMPATIBILITY_MISMATCH",
                                     scope_id=record["scope_id"],
                                     provider_id=record["provider_id"],
                                     semantic_id=record["id"],
                                     observation="semantic-invalid",
                                     expected=_display(item),
                                     observed="catalog compatibility record differs"))


def _validate_request(request: object, operations: set[str], *,
                      write: bool = False) -> tuple[InstructionDiagnostic, ...]:
    if not isinstance(request, InstructionRequest):
        return (_diag("INSTRUCTION_SCOPE_INVALID", expected="InstructionRequest",
                      observed=_shape(request)),)
    diagnostics = []
    if request.contract_version != CONTRACT_VERSION or request.catalog_version != CATALOG_VERSION:
        diagnostics.append(_diag("INSTRUCTION_PROVENANCE_INVALID",
                                 observation="provenance-invalid",
                                 expected=f"{CONTRACT_VERSION}/{CATALOG_VERSION}",
                                 observed=f"{request.contract_version}/{request.catalog_version}"))
    if request.operation_id not in operations:
        diagnostics.append(_diag("INSTRUCTION_WRITE_FORBIDDEN" if write else "INSTRUCTION_SCOPE_INVALID",
                                 observation="write-forbidden" if write else "semantic-invalid",
                                 expected=_display(tuple(sorted(operations))),
                                 observed=request.operation_id))
    if (not request.scope_ids or len(set(request.scope_ids)) != len(request.scope_ids)
            or any(item not in SCOPES for item in request.scope_ids)
            or tuple(item for item in SCOPES if item in request.scope_ids) != request.scope_ids):
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID", expected="explicit ordered D86 scope subset",
                                 observed=_display(request.scope_ids)))
    if (not request.provider_ids or len(set(request.provider_ids)) != len(request.provider_ids)
            or any(item not in PROVIDERS for item in request.provider_ids)
            or tuple(item for item in PROVIDERS if item in request.provider_ids) != request.provider_ids):
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID",
                                 expected="explicit ordered provider subset",
                                 observed=_display(request.provider_ids)))
    try:
        _absolute_root(Path(request.target_root))
    except (TypeError, ValueError):
        diagnostics.append(_diag("INSTRUCTION_SCOPE_INVALID",
                                 expected="absolute target_root", observed=request.target_root))
    if (not request.config_provenance
            or any(not isinstance(pair, tuple) or len(pair) != 2
                   or not all(isinstance(value, str) and value for value in pair)
                   for pair in request.config_provenance)):
        diagnostics.append(_diag("INSTRUCTION_PROVENANCE_INVALID",
                                 observation="provenance-invalid",
                                 expected="non-empty config provenance",
                                 observed=_display(request.config_provenance)))
    if (not request.authorization_provenance
            or any(not isinstance(pair, tuple) or len(pair) != 2
                   or not all(isinstance(value, str) and value for value in pair)
                   for pair in request.authorization_provenance)):
        diagnostics.append(_diag("INSTRUCTION_WRITE_FORBIDDEN" if write else "INSTRUCTION_PROVENANCE_INVALID",
                                 observation="write-forbidden" if write else "provenance-invalid",
                                 expected="non-empty authorization provenance",
                                 observed=_display(request.authorization_provenance)))
    return _ordered_diagnostics(tuple(diagnostics))


def _target_result(projection: InstructionProjection, action,
                   *, changed: bool = False) -> InstructionTargetResult:
    observation = action.observation.value
    code = {
        "missing": "INSTRUCTION_TARGET_MISSING",
        "ownership-conflict": "INSTRUCTION_OWNERSHIP_CONFLICT",
        "boundary-invalid": "INSTRUCTION_BOUNDARY_INVALID",
        "provenance-invalid": "INSTRUCTION_PROVENANCE_INVALID",
        "stale-source": "INSTRUCTION_STALE_SOURCE",
        "managed-drift": "INSTRUCTION_MANAGED_DRIFT",
    }.get(observation)
    diagnostics = ()
    if code:
        diagnostics = (_diag(
            code, scope_id=projection.scope_id, provider_id=projection.provider_id,
            target_path=projection.target_path,
            artifact_id=projection.result.provenance.artifact_id,
            observation=observation, expected="clean",
            observed=action.diagnostic,
            next_action=action.action.value),)
    elif observation != "clean":
        diagnostics = (_diag(
            "INSTRUCTION_WRITE_FORBIDDEN", scope_id=projection.scope_id,
            provider_id=projection.provider_id, target_path=projection.target_path,
            artifact_id=projection.result.provenance.artifact_id,
            observation="write-forbidden", expected="known P2 observation",
            observed=observation, next_action="refuse"),)
    block_ids = projection.result.provenance.managed_boundary[1]
    marker_ids = tuple(block_id.replace("instructions.", "swissknifeman:instructions:", 1)
                       .replace(".common", ":common").replace(".extension", ":extension")
                       .replace(".", ":", 2) for block_id in block_ids)
    return InstructionTargetResult(
        projection.result.provenance.artifact_id, projection.scope_id,
        projection.provider_id, projection.target_path,
        projection.common_ids + projection.extension_ids, observation,
        action.action.value, projection.result.provenance.source_hash,
        projection.result.provenance.rendered_hash, marker_ids, block_ids,
        diagnostics, changed)


def _completed_write(request: InstructionRequest, fresh: InstructionOperationResult,
                     writable: tuple) -> InstructionOperationResult:
    writable_by_path = {action.target_path: action for action in writable}
    targets = tuple(replace(
        target, changed=target.target_path in writable_by_path,
        diagnostics=(), observation=(
            writable_by_path[target.target_path].observation.value
            if target.target_path in writable_by_path else "clean"),
        action=(writable_by_path[target.target_path].action.value
                if target.target_path in writable_by_path else "noop"))
        for target in fresh.targets)
    return InstructionOperationResult(request, targets, (), True, fresh.artifact_plan)


def _write_refusal(request: InstructionRequest, result: InstructionOperationResult,
                   observed: str) -> InstructionOperationResult:
    diagnostic = _diag("INSTRUCTION_WRITE_FORBIDDEN", observation="write-forbidden",
                       expected="fresh explicitly authorized write plan", observed=observed,
                       next_action="refuse")
    return InstructionOperationResult(request, result.targets,
                                      _ordered_diagnostics(result.diagnostics + (diagnostic,)),
                                      False, result.artifact_plan)


def _preserve_unselected_lock(plan_value: ArtifactPlan,
                              lock_bytes: bytes | None) -> ArtifactPlan:
    if plan_value.next_lock is None or lock_bytes is None:
        return plan_value
    try:
        existing = parse_lock(lock_bytes)
    except ValueError:
        return plan_value
    selected = {action.artifact_id for action in plan_value.actions}
    records = tuple(record for record in existing.records
                    if record.artifact_id not in selected) + plan_value.next_lock.records
    return replace(plan_value, next_lock=ArtifactLock(1, records))


def _instruction_observation_corrections(root: Path, plan_value: ArtifactPlan,
                                         lock_bytes: bytes | None) -> ArtifactPlan:
    """Apply D86's ownership-before-boundary classification over the generic P2 codec."""
    try:
        lock = ArtifactLock(1, ()) if lock_bytes is None else parse_lock(lock_bytes)
    except ValueError:
        return plan_value
    records = {record.artifact_id: record for record in lock.records}
    changed = False
    actions = []
    for action in plan_value.actions:
        target = root / action.target_path
        if (action.observation is DriftObservation.BOUNDARY_INVALID
                and (target.exists() or target.is_symlink())
                and action.artifact_id not in records):
            action = replace(action, observation=DriftObservation.OWNERSHIP_CONFLICT,
                             action=ArtifactActionKind.REFUSE,
                             diagnostic="unmanaged-target")
            changed = True
        actions.append(action)
    return replace(plan_value, actions=tuple(actions), next_lock=None) if changed else plan_value


def _source(source_id: str, path: Path) -> ArtifactSource:
    return ArtifactSource(source_id, path.relative_to(repository_root()).as_posix(),
                          sha256_digest(path.read_bytes()))


def _catalog_source(value: dict[str, object]) -> ArtifactSource:
    path = catalog_path()
    raw = path.read_bytes()
    content = raw if json.loads(raw) == value else canonical_json_bytes(value)
    return ArtifactSource("instruction.catalog",
                          path.relative_to(repository_root()).as_posix(),
                          sha256_digest(content))


def _fragment_relative(scope_id: str, provider_id: str | None) -> str:
    leaf = provider_id or "common"
    middle = "root" if scope_id == "root" else f"packages/{scope_id}"
    return f"packages/harness/configs/common/instructions/{middle}/{leaf}.md"


def _fragment_body(text: str, semantic_id: str) -> str:
    marker = f"<!-- instruction:{semantic_id} -->"
    start = text.find(marker)
    if start < 0:
        return ""
    next_start = text.find("<!-- instruction:", start + len(marker))
    return text[start:] if next_start < 0 else text[start:next_start]


def _managed(scope: str, provider: str, common: str, extension: str,
             common_ids: tuple[str, ...], extension_ids: tuple[str, ...]) -> bytes:
    return (_block(scope, provider, "common", common, common_ids)
            + _block(scope, provider, "extension", extension, extension_ids))


def _block(scope: str, provider: str, kind: str, text: str,
           ids: tuple[str, ...]) -> bytes:
    begin = f"<!-- swissknifeman:instructions:{scope}:{provider}:{kind}:begin -->\n"
    end = f"<!-- swissknifeman:instructions:{scope}:{provider}:{kind}:end -->\n"
    body = "".join(f"<!-- semantic:{item} -->\n" for item in ids) + text
    return (begin + body.rstrip() + "\n" + end).encode("utf-8")


def _codec(scope: str, provider: str):
    def extract(raw: bytes, _ids: tuple[str, ...]) -> bytes:
        return b"".join(raw[start:end] for start, end in _spans(raw, scope, provider))

    def replace_blocks(raw: bytes, managed: bytes, _ids: tuple[str, ...]) -> bytes:
        parts = _split_blocks(managed, scope, provider)
        if not raw:
            return parts[0] + b"\n" + parts[1]
        spans = _spans(raw, scope, provider)
        return (raw[:spans[0][0]] + parts[0] + raw[spans[0][1]:spans[1][0]]
                + parts[1] + raw[spans[1][1]:])

    return extract, replace_blocks


def _spans(raw: bytes, scope: str, provider: str) -> tuple[tuple[int, int], ...]:
    spans = []
    for kind in ("common", "extension"):
        begin = f"<!-- swissknifeman:instructions:{scope}:{provider}:{kind}:begin -->".encode()
        end = f"<!-- swissknifeman:instructions:{scope}:{provider}:{kind}:end -->".encode()
        if raw.count(begin) != 1 or raw.count(end) != 1:
            raise ValueError("boundary-invalid")
        start, stop = raw.index(begin), raw.index(end)
        if stop < start:
            raise ValueError("boundary-invalid")
        stop += len(end)
        if stop < len(raw) and raw[stop:stop + 1] == b"\n":
            stop += 1
        spans.append((start, stop))
    if spans[0][0] >= spans[1][0] or spans[0][1] > spans[1][0]:
        raise ValueError("boundary-invalid")
    return tuple(spans)


def _split_blocks(managed: bytes, scope: str, provider: str) -> tuple[bytes, bytes]:
    spans = _spans(managed, scope, provider)
    if spans[0][0] != 0 or spans[1][1] != len(managed):
        raise ValueError("boundary-invalid")
    return (managed[spans[0][0]:spans[0][1]],
            managed[spans[1][0]:spans[1][1]])


def _boundary_broader_or_equal(left: object, right: object) -> bool:
    return left == right or (isinstance(left, str) and left.endswith(".all"))


def _boundary_narrower(left: object, right: object) -> bool:
    return (left != right and isinstance(left, str) and isinstance(right, str)
            and right.endswith(".all") and left.startswith(right[:-3]))


def _boundaries_overlap(left: object, right: object) -> bool:
    return (left == right or _boundary_broader_or_equal(left, right)
            or _boundary_broader_or_equal(right, left)
            or _boundary_narrower(left, right) or _boundary_narrower(right, left))


def _absolute_root(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("target root must be explicit and absolute")
    return root


def _diag(code: str, *, scope_id: str | None = None,
          provider_id: str | None = None, target_path: str | None = None,
          artifact_id: str | None = None, observation: str | None = "semantic-invalid",
          semantic_id: str | None = None, expected: str | None = None,
          observed: str | None = None, next_action: str | None = "refuse",
          message: str | None = None) -> InstructionDiagnostic:
    return InstructionDiagnostic(
        "error", code, scope_id, provider_id, target_path, artifact_id, observation,
        semantic_id, expected, observed, next_action, message)


def _ordered_diagnostics(values: tuple[InstructionDiagnostic, ...]) -> tuple[InstructionDiagnostic, ...]:
    scope_order = {value: index for index, value in enumerate(SCOPES)}
    provider_order = {value: index for index, value in enumerate(PROVIDERS)}
    semantic_order = {
        semantic_id: index for index, semantic_id in enumerate(
            item for scope_id in SCOPES for item in (
                COMMON_IDS[scope_id] + EXTENSION_IDS[(scope_id, "claude-code")]
                + EXTENSION_IDS[(scope_id, "codex")]))}
    return tuple(sorted(values, key=lambda item: (
        scope_order.get(item.scope_id, len(SCOPES)),
        provider_order.get(item.provider_id, len(PROVIDERS)),
        item.target_path or "",
        semantic_order.get(item.semantic_id, 10_000),
        item.code,
        item.observed or "",
    )))


def _display(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _shape(value: object) -> str:
    if isinstance(value, Mapping):
        return _display(tuple(sorted(value)))
    return type(value).__name__
