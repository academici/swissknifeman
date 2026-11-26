"""Block types, ladder order, budget classes, and trust taxonomy (context §4.1, §4.4)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from typing import Literal

__all__ = [
    "ALWAYS_MANDATORY_TYPES",
    "ASSEMBLER_VERSION",
    "BLOCK_SPECS",
    "LADDER_ORDER",
    "ROUND_TYPES",
    "BlockSpec",
    "BlockType",
    "BudgetClass",
    "Mandatory",
    "TrustLevel",
    "canonical_json_digest",
    "ladder_key",
]

ASSEMBLER_VERSION: Final[int] = 1


class BlockType(StrEnum):
    RESUME_NOTE = "resume_note"
    SYSTEM_CONSTRAINTS = "system_constraints"
    ROLE_CONTRACT = "role_contract"
    RUN_RULES = "run_rules"
    RUNTIME_NOTES = "runtime_notes"
    TASK_CONTRACT = "task_contract"
    ACCEPTANCE = "acceptance"
    REQUIREMENTS = "requirements"
    DECISIONS = "decisions"
    DECISION_ANSWERS = "decision_answers"
    REVIEW_FEEDBACK = "review_feedback"
    PREVIOUS_ATTEMPT = "previous_attempt"
    CANDIDATE_DIFF = "candidate_diff"
    FINDINGS_UNDER_REVIEW = "findings_under_review"
    CONTEXT_MAP = "context_map"
    STEERING = "steering"
    SKILLS = "skills"
    SKILL_INDEX = "skill_index"
    MATERIALS = "materials"
    REPO_INSTRUCTIONS = "repo_instructions"
    RESEARCH = "research"
    MEMORY = "memory"
    HISTORY = "history"
    RESULT_CONTRACT = "result_contract"


class BudgetClass(StrEnum):
    CORE = "core"
    TASK = "task"
    SUPPORTING = "supporting"
    RETRIEVAL = "retrieval"


class TrustLevel(StrEnum):
    SYSTEM = "system"
    OPERATOR = "operator"
    PROJECT = "project"
    REPOSITORY = "repository"
    MODEL = "model"
    EXTERNAL = "external"
    THIRD_PARTY = "third_party"
    MEMORY = "memory"


type Mandatory = Literal["always", "when_present", "role_required", "never"]


@dataclass(frozen=True, slots=True)
class BlockSpec:
    type: BlockType
    budget_class: BudgetClass
    mandatory: Mandatory
    default_trust: TrustLevel
    round_kind: bool


BLOCK_SPECS: Final[Mapping[BlockType, BlockSpec]] = MappingProxyType(
    {
        BlockType.RESUME_NOTE: BlockSpec(
            BlockType.RESUME_NOTE, BudgetClass.CORE, "when_present", TrustLevel.SYSTEM, True
        ),
        BlockType.SYSTEM_CONSTRAINTS: BlockSpec(
            BlockType.SYSTEM_CONSTRAINTS, BudgetClass.CORE, "always", TrustLevel.SYSTEM, False
        ),
        BlockType.ROLE_CONTRACT: BlockSpec(
            BlockType.ROLE_CONTRACT, BudgetClass.CORE, "always", TrustLevel.SYSTEM, False
        ),
        BlockType.RUN_RULES: BlockSpec(
            BlockType.RUN_RULES, BudgetClass.CORE, "always", TrustLevel.SYSTEM, False
        ),
        BlockType.RUNTIME_NOTES: BlockSpec(
            BlockType.RUNTIME_NOTES, BudgetClass.CORE, "when_present", TrustLevel.SYSTEM, False
        ),
        BlockType.TASK_CONTRACT: BlockSpec(
            BlockType.TASK_CONTRACT, BudgetClass.TASK, "always", TrustLevel.PROJECT, False
        ),
        BlockType.ACCEPTANCE: BlockSpec(
            BlockType.ACCEPTANCE, BudgetClass.TASK, "always", TrustLevel.PROJECT, False
        ),
        BlockType.REQUIREMENTS: BlockSpec(
            BlockType.REQUIREMENTS, BudgetClass.TASK, "when_present", TrustLevel.PROJECT, False
        ),
        BlockType.DECISIONS: BlockSpec(
            BlockType.DECISIONS, BudgetClass.TASK, "when_present", TrustLevel.PROJECT, False
        ),
        BlockType.DECISION_ANSWERS: BlockSpec(
            BlockType.DECISION_ANSWERS, BudgetClass.CORE, "when_present", TrustLevel.PROJECT, True
        ),
        BlockType.REVIEW_FEEDBACK: BlockSpec(
            BlockType.REVIEW_FEEDBACK, BudgetClass.TASK, "when_present", TrustLevel.MODEL, True
        ),
        BlockType.PREVIOUS_ATTEMPT: BlockSpec(
            BlockType.PREVIOUS_ATTEMPT, BudgetClass.TASK, "never", TrustLevel.SYSTEM, True
        ),
        BlockType.CANDIDATE_DIFF: BlockSpec(
            BlockType.CANDIDATE_DIFF, BudgetClass.TASK, "role_required", TrustLevel.REPOSITORY, False
        ),
        BlockType.FINDINGS_UNDER_REVIEW: BlockSpec(
            BlockType.FINDINGS_UNDER_REVIEW, BudgetClass.TASK, "role_required", TrustLevel.MODEL, False
        ),
        BlockType.CONTEXT_MAP: BlockSpec(
            BlockType.CONTEXT_MAP, BudgetClass.SUPPORTING, "never", TrustLevel.MODEL, False
        ),
        BlockType.STEERING: BlockSpec(
            BlockType.STEERING, BudgetClass.SUPPORTING, "never", TrustLevel.THIRD_PARTY, False
        ),
        BlockType.SKILLS: BlockSpec(
            BlockType.SKILLS, BudgetClass.SUPPORTING, "never", TrustLevel.THIRD_PARTY, False
        ),
        BlockType.SKILL_INDEX: BlockSpec(
            BlockType.SKILL_INDEX, BudgetClass.SUPPORTING, "never", TrustLevel.SYSTEM, False
        ),
        BlockType.MATERIALS: BlockSpec(
            BlockType.MATERIALS, BudgetClass.SUPPORTING, "always", TrustLevel.PROJECT, False
        ),
        BlockType.REPO_INSTRUCTIONS: BlockSpec(
            BlockType.REPO_INSTRUCTIONS, BudgetClass.SUPPORTING, "never", TrustLevel.REPOSITORY, False
        ),
        BlockType.RESEARCH: BlockSpec(
            BlockType.RESEARCH, BudgetClass.RETRIEVAL, "never", TrustLevel.EXTERNAL, False
        ),
        BlockType.MEMORY: BlockSpec(
            BlockType.MEMORY, BudgetClass.RETRIEVAL, "never", TrustLevel.MEMORY, False
        ),
        BlockType.HISTORY: BlockSpec(
            BlockType.HISTORY, BudgetClass.SUPPORTING, "never", TrustLevel.SYSTEM, True
        ),
        BlockType.RESULT_CONTRACT: BlockSpec(
            BlockType.RESULT_CONTRACT, BudgetClass.CORE, "always", TrustLevel.SYSTEM, False
        ),
    }
)

LADDER_ORDER: Final[Mapping[BlockType, int]] = MappingProxyType(
    {block_type: idx for idx, block_type in enumerate(BlockType)}
)

ALWAYS_MANDATORY_TYPES: Final[frozenset[BlockType]] = frozenset(
    (
        BlockType.SYSTEM_CONSTRAINTS,
        BlockType.ROLE_CONTRACT,
        BlockType.RUN_RULES,
        BlockType.TASK_CONTRACT,
        BlockType.ACCEPTANCE,
        BlockType.RESULT_CONTRACT,
    )
)

ROUND_TYPES: Final[frozenset[BlockType]] = frozenset(
    (
        BlockType.RESUME_NOTE,
        BlockType.DECISION_ANSWERS,
        BlockType.REVIEW_FEEDBACK,
        BlockType.PREVIOUS_ATTEMPT,
        BlockType.HISTORY,
    )
)


def ladder_key(block_type: BlockType, source_ref: str) -> tuple[int, str]:
    """Canonical ladder key: ``BlockType`` order 1..24, then ``source_ref``."""
    return (LADDER_ORDER[block_type], source_ref)


def _canonical_json_value(value: object) -> object:
    if isinstance(value, str) or value is None or isinstance(value, int | bool):
        return value
    if isinstance(value, float):
        raise TypeError("canonical JSON values must not use floats")
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        if not all(isinstance(k, str) for k in mapping):
            raise TypeError("canonical JSON object keys must be strings")
        return {k: _canonical_json_value(v) for k, v in sorted(cast("Mapping[str, object]", mapping).items())}
    if isinstance(value, tuple | list):
        return tuple(_canonical_json_value(v) for v in cast("tuple[object, ...] | list[object]", value))
    raise TypeError("value is not canonical JSON data")


def canonical_json_digest(value: object) -> str:
    """Return ``sha256:<hex>`` of compact sorted UTF-8 canonical JSON v1 bytes."""
    raw = json.dumps(
        _canonical_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return f"sha256:{sha256(raw).hexdigest()}"
