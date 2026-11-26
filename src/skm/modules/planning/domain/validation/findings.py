"""Findings, rule failures and the validation report (planning §5.7).

``FindingCode`` and ``DEFAULT_SEVERITY`` restate ``schemas/planning/data/finding-codes.json``; the catalog
stays the source of truth and a test keeps the two equal. A finding is a fact about the user's plan; a
``RuleFailure`` is a fact about the validator itself and is never shown as a finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.kernel.ids import EntityId

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonValue
    from skm.modules.planning.domain.compile_graph import ExecutionGraph


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingCode(StrEnum):
    DUPLICATE_ID = "duplicate_id"
    DUPLICATE_KEY = "duplicate_key"
    KEY_PREFIX_MISMATCH = "key_prefix_mismatch"
    ENTITY_KIND_CHANGED = "entity_kind_changed"
    SELF_REFERENCE = "self_reference"
    REF_UNKNOWN = "ref_unknown"
    ARTIFACT_DUPLICATE = "artifact_duplicate"
    ARTIFACT_PATH_MISMATCH = "artifact_path_mismatch"
    PLAN_RELATION_UNRESOLVED = "plan_relation_unresolved"
    DEPENDENCY_CYCLE = "dependency_cycle"
    BATCH_FOREIGN = "batch_foreign"
    BATCH_MULTIPLE = "batch_multiple"
    BATCH_UNASSIGNED = "batch_unassigned"
    BATCH_ORDER_CONFLICT = "batch_order_conflict"
    MOUNT_UNKNOWN = "mount_unknown"
    WRITE_SCOPE_OVERLAP = "write_scope_overlap"
    WRITE_SCOPE_OVERLAP_CROSS_ITEM = "write_scope_overlap_cross_item"
    WRITE_SCOPE_UNCOVERED = "write_scope_uncovered"
    WRITE_SCOPE_EMPTY = "write_scope_empty"
    WRITE_SCOPE_NO_TESTS = "write_scope_no_tests"
    FORBIDDEN_PATH_CONFLICT = "forbidden_path_conflict"
    INCOMPLETE = "incomplete"
    PHASE_SKELETON = "phase_skeleton"
    CONTEXT_DEFAULT = "context_default"
    RESEARCH_QUESTION_MISSING = "research_question_missing"
    CRITERION_UNLINKED = "criterion_unlinked"
    CRITERION_CHECK_MISMATCH = "criterion_check_mismatch"
    REQUIREMENT_UNIMPLEMENTED = "requirement_unimplemented"
    CRITERION_MISSING = "criterion_missing"
    REVIEW_REVIEWER_UNSET = "review_reviewer_unset"
    UNIT_COMMAND_MISSING = "unit_command_missing"
    CHECK_CADENCE = "check_cadence"
    CHECK_DUPLICATE_COMMAND = "check_duplicate_command"
    CHECK_MANUAL_RERUN_AFTER_INTEGRATION = "check_manual_rerun_after_integration"
    DECISION_FIELDS = "decision_fields"
    DECISION_SUPERSEDED_ORPHAN = "decision_superseded_orphan"
    SCOPE_AMBIGUOUS = "scope_ambiguous"
    CONTEXT_UNBOUND = "context_unbound"
    BRIEF_DUPLICATE = "brief_duplicate"
    CONTEXT_HEAVY = "context_heavy"
    EXECUTION_PROMPT_HEAVY = "execution_prompt_heavy"
    MATERIAL_UNAVAILABLE = "material_unavailable"
    MATERIAL_STALE = "material_stale"
    ROUTE_UNKNOWN_RUNTIME = "route_unknown_runtime"
    ROUTE_UNKNOWN_MODEL = "route_unknown_model"
    SKILL_UNKNOWN = "skill_unknown"


_E, _W, _I = Severity.ERROR, Severity.WARNING, Severity.INFO

DEFAULT_SEVERITY: Final[Mapping[FindingCode, Severity]] = MappingProxyType(
    {
        FindingCode.DUPLICATE_ID: _E,
        FindingCode.DUPLICATE_KEY: _E,
        FindingCode.KEY_PREFIX_MISMATCH: _E,
        FindingCode.ENTITY_KIND_CHANGED: _E,
        FindingCode.SELF_REFERENCE: _E,
        FindingCode.REF_UNKNOWN: _E,
        FindingCode.ARTIFACT_DUPLICATE: _E,
        FindingCode.ARTIFACT_PATH_MISMATCH: _E,
        FindingCode.PLAN_RELATION_UNRESOLVED: _W,
        FindingCode.DEPENDENCY_CYCLE: _E,
        FindingCode.BATCH_FOREIGN: _E,
        FindingCode.BATCH_MULTIPLE: _E,
        FindingCode.BATCH_UNASSIGNED: _I,
        FindingCode.BATCH_ORDER_CONFLICT: _E,
        FindingCode.MOUNT_UNKNOWN: _E,
        FindingCode.WRITE_SCOPE_OVERLAP: _E,
        FindingCode.WRITE_SCOPE_OVERLAP_CROSS_ITEM: _I,
        FindingCode.WRITE_SCOPE_UNCOVERED: _W,
        FindingCode.WRITE_SCOPE_EMPTY: _W,
        FindingCode.WRITE_SCOPE_NO_TESTS: _W,
        FindingCode.FORBIDDEN_PATH_CONFLICT: _E,
        FindingCode.INCOMPLETE: _E,
        FindingCode.PHASE_SKELETON: _I,
        FindingCode.CONTEXT_DEFAULT: _W,
        FindingCode.RESEARCH_QUESTION_MISSING: _W,
        FindingCode.CRITERION_UNLINKED: _E,
        FindingCode.CRITERION_CHECK_MISMATCH: _E,
        FindingCode.REQUIREMENT_UNIMPLEMENTED: _W,
        FindingCode.CRITERION_MISSING: _I,
        FindingCode.REVIEW_REVIEWER_UNSET: _I,
        FindingCode.UNIT_COMMAND_MISSING: _E,
        FindingCode.CHECK_CADENCE: _W,
        FindingCode.CHECK_DUPLICATE_COMMAND: _W,
        FindingCode.CHECK_MANUAL_RERUN_AFTER_INTEGRATION: _E,
        FindingCode.DECISION_FIELDS: _E,
        FindingCode.DECISION_SUPERSEDED_ORPHAN: _W,
        FindingCode.SCOPE_AMBIGUOUS: _E,
        FindingCode.CONTEXT_UNBOUND: _W,
        FindingCode.BRIEF_DUPLICATE: _W,
        FindingCode.CONTEXT_HEAVY: _W,
        FindingCode.EXECUTION_PROMPT_HEAVY: _W,
        FindingCode.MATERIAL_UNAVAILABLE: _E,
        FindingCode.MATERIAL_STALE: _W,
        FindingCode.ROUTE_UNKNOWN_RUNTIME: _W,
        FindingCode.ROUTE_UNKNOWN_MODEL: _W,
        FindingCode.SKILL_UNKNOWN: _W,
    }
)

PLUGIN_CODE: Final = re.compile(r"x_[a-z0-9]+_[a-z0-9_]+")  # a plugin's code: ``x_<publisher>_<name>``


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: Severity
    message: str
    entity_key: str | None
    entity_id: EntityId | None
    pointer: str | None
    details: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class RuleFailure:
    rule: str
    error_type: str
    message: str
    plugin: str | None


def finding(
    code: FindingCode,
    message: str,
    *,
    key: str | None = None,
    entity_id: EntityId | None = None,
    pointer: str | None = None,
    severity: Severity | None = None,
    details: Mapping[str, JsonValue] | None = None,
) -> Finding:
    """A finding of a catalog ``code``; its severity is the catalog's unless a setting lowers it."""
    return Finding(
        code.value,
        DEFAULT_SEVERITY[code] if severity is None else severity,
        message,
        key,
        entity_id,
        pointer,
        MappingProxyType(dict(details or {})),
    )


def pointer_of(*parts: str | int) -> str:
    """A JSON pointer (RFC 6901) to ``parts``, escaping ``~`` and ``/`` inside names."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def doc_entity_id(entity: Mapping[str, object]) -> EntityId | None:
    """The ``id`` of a document entity; ``None`` when it has none (or one that is not a UUID)."""
    raw = entity.get("id")
    try:
        return EntityId(UUID(raw)) if isinstance(raw, str) else None
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    findings: tuple[Finding, ...]
    rule_failures: tuple[RuleFailure, ...]
    graph: ExecutionGraph | None

    def has_errors(self, *, plugin_failures_block: bool) -> bool:
        """Blocks: an error finding, a failed built-in rule, or (by setting) a failed plugin rule."""
        if any(found.severity is Severity.ERROR for found in self.findings):
            return True
        return any(failure.plugin is None or plugin_failures_block for failure in self.rule_failures)

    def counts(self) -> Mapping[Severity, int]:
        counts = dict.fromkeys(Severity, 0)
        for found in self.findings:
            counts[found.severity] += 1
        return MappingProxyType(counts)
