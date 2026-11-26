"""Profile/config intersections and the default role visibility matrix (context §4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.blocks import BlockType, BudgetClass
from skm.modules.context.domain.request import RuntimeTarget

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Literal


type RepoInstructionsMode = Literal["none", "constraints", "full"]
type SkillsMode = Literal["none", "allowlist", "auto"]


@dataclass(frozen=True, slots=True)
class ContextPolicySpec:
    include: frozenset[BlockType]
    max_total_tokens: int | None
    budgets: Mapping[BudgetClass, int]
    inherit_user_global: bool
    repo_instructions: RepoInstructionsMode
    repo_instruction_sections: tuple[str, ...]
    skills_mode: SkillsMode
    skills_include: tuple[str, ...]
    skills_exclude: tuple[str, ...]
    skills_budget_tokens: int | None
    history_max_steps: int
    memory_top_k: int
    include_optional_materials: bool


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    include: frozenset[BlockType]
    total_limit: int
    class_limits: Mapping[BudgetClass, int | None]
    repo_mode: RepoInstructionsMode
    repo_sections: tuple[str, ...]
    repo_max_bytes: int
    repo_max_files: int
    repo_files: tuple[str, ...]
    skills_mode: SkillsMode
    skills_include: tuple[str, ...]
    skills_exclude: frozenset[str]
    skills_budget: int
    history_max_steps: int
    memory_top_k: int
    include_optional_materials: bool
    max_classification: str
    allow_third_party: bool
    block_max_tokens: int


def effective_policy(spec: ContextPolicySpec, settings: JsonObject, runtime: RuntimeTarget) -> ContextPolicy:
    """Narrow a profile with already-resolved settings, without inspecting reference text."""
    skills = _section(settings, "skills")
    repo = _section(settings, "repo_instructions")
    memory = _section(settings, "memory")
    budget = _section(settings, "budget")
    skills_mode = cast(
        "SkillsMode",
        min((spec.skills_mode, str(skills.get("max_mode", "auto"))), key=("none", "allowlist", "auto").index),
    )
    repo_mode = cast(
        "RepoInstructionsMode",
        min(
            (spec.repo_instructions, str(repo.get("mode", "full"))), key=("none", "constraints", "full").index
        ),
    )
    include = set(spec.include)
    if repo_mode == "none":
        include.discard(BlockType.REPO_INSTRUCTIONS)
    if skills_mode == "none":
        include.difference_update((BlockType.SKILLS, BlockType.SKILL_INDEX))
    if not memory.get("enabled", False):
        include.discard(BlockType.MEMORY)
    limits: dict[BudgetClass, int | None] = {}
    for cls, default in (
        (BudgetClass.CORE, 12000),
        (BudgetClass.TASK, 0),
        (BudgetClass.SUPPORTING, 30000),
        (BudgetClass.RETRIEVAL, 50000),
    ):
        if cls is BudgetClass.TASK:
            limits[cls] = None
        else:
            cfg_limit = int(cast("int", budget.get(cls.value, default)))
            limits[cls] = min(cfg_limit, spec.budgets[cls]) if cls in spec.budgets else cfg_limit
    cfg_total = int(cast("int", settings.get("max_total_tokens", 150000)))
    win_total = floor(
        runtime.context_window_tokens * float(cast("float", settings.get("window_fraction", 0.6)))
    )
    total = (
        min(cfg_total, win_total)
        if spec.max_total_tokens is None
        else min(cfg_total, spec.max_total_tokens, win_total)
    )
    cfg_skills = int(cast("int", skills.get("budget_tokens", 8000)))
    skills_budget = (
        min(cfg_skills, spec.skills_budget_tokens) if spec.skills_budget_tokens is not None else cfg_skills
    )
    return ContextPolicy(
        frozenset(include),
        total,
        MappingProxyType(limits),
        repo_mode,
        spec.repo_instruction_sections
        if repo_mode == "constraints"
        else (("*",) if repo_mode == "full" else ()),
        int(cast("int", repo.get("max_bytes", 65536))),
        int(cast("int", repo.get("max_files", 8))),
        tuple(str(f) for f in cast("list[str]", repo.get("files", ["CLAUDE.md", "AGENTS.md"]))),
        skills_mode,
        spec.skills_include,
        frozenset(spec.skills_exclude),
        skills_budget,
        min(spec.history_max_steps, int(cast("int", _section(settings, "history").get("max_steps", 3)))),
        min(spec.memory_top_k, int(cast("int", memory.get("top_k", 5)))),
        spec.include_optional_materials,
        str(settings.get("max_classification_for_runtime", "internal")),
        bool(settings.get("allow_third_party", True)),
        int(cast("int", _section(settings, "block").get("max_tokens", 40000))),
    )


def _section(settings: JsonObject, key: str) -> JsonObject:
    value = settings.get(key, {})
    return value if isinstance(value, dict) else {}


def inheritance_mode(spec: ContextPolicySpec, settings: JsonObject) -> str:
    """The host routing decision must use this intersection before constructing RuntimeTarget."""
    return (
        "inherit" if spec.inherit_user_global and settings.get("inherit_user_global", False) else "isolated"
    )


def role_policy_spec(role: str) -> ContextPolicySpec:
    """Core defaults; executor-transparent is a profile of the executor role."""
    matrix: dict[str, tuple[RepoInstructionsMode, SkillsMode, tuple[str, ...]]] = {
        "scout": ("constraints", "allowlist", ("materials", "repo_instructions", "skills")),
        "executor": (
            "full",
            "auto",
            (
                "previous_attempt",
                "context_map",
                "steering",
                "skills",
                "skill_index",
                "materials",
                "repo_instructions",
                "research",
                "history",
            ),
        ),
        "reviewer": (
            "constraints",
            "allowlist",
            ("context_map", "materials", "repo_instructions", "skills", "history"),
        ),
        "triager": ("none", "allowlist", ()),
        "advisor": (
            "constraints",
            "auto",
            ("steering", "materials", "repo_instructions", "skills", "history"),
        ),
        "researcher": ("none", "allowlist", ("materials", "research", "skills")),
        "registrar": ("none", "none", ()),
    }
    repo, skills, include = matrix["executor" if role == "executor-transparent" else role]
    return ContextPolicySpec(
        frozenset(BlockType(t) for t in include),
        None,
        MappingProxyType({}),
        role == "executor-transparent",
        repo,
        ("Constraints", "Conventions", "Testing", "Security"),
        skills,
        ("code-review",) if role == "reviewer" else (),
        (),
        6000 if role == "reviewer" else None,
        3,
        0,
        True,
    )
