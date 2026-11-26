"""Canonical selection reasons and reasons whose source identity cannot leave the control plane."""

from __future__ import annotations

from enum import StrEnum


class IncludeReason(StrEnum):
    MANDATORY = "mandatory"
    EXPLICIT_PLAN = "explicit_plan"
    EXPLICIT_PROFILE = "explicit_profile"
    TRIGGER_PATH = "trigger_path"
    TRIGGER_DEP = "trigger_dep"
    REQUIRED = "required"
    SCOPE_GLOBAL = "scope_global"
    SCOPE_MATCH = "scope_match"
    CARRIER_FOR_WRITE_SCOPE = "carrier_for_write_scope"
    REQUIRED_MATERIAL = "required_material"
    OPTIONAL_MATERIAL = "optional_material"
    BINARY_REFERENCE = "binary_reference"
    RECENT_HISTORY = "recent_history"
    MEMORY_MATCH = "memory_match"
    EXECUTION_INPUT = "execution_input"
    DISCOVERABLE_INDEX = "discoverable_index"
    RESEARCH_RESULT = "research_result"
    EXTERNAL_MATERIAL = "external_material"
    EXTERNAL_REFERENCE = "external_reference"


class ExcludeReason(StrEnum):
    NOT_FOUND = "not_found"
    TOO_LARGE = "too_large"
    BINARY_CONTENT = "binary_content"
    ENCODING_INVALID = "encoding_invalid"
    PATH_INVALID = "path_invalid"
    CLASSIFICATION_FORBIDDEN = "classification_forbidden"
    FILE_VERSION_NOT_READY = "file_version_not_ready"
    QUARANTINED = "quarantined"
    TRUST_FORBIDDEN = "trust_forbidden"
    UNKNOWN_SKILL = "unknown_skill"
    VERSION_UNAVAILABLE = "version_unavailable"
    EXCLUDED = "excluded"
    ROLE_NOT_ALLOWED = "role_not_allowed"
    TOOL_MISSING = "tool_missing"
    KIND_NOT_PRELOADED = "kind_not_preloaded"
    DUPLICATED_BY_ROLE_CONTRACT = "duplicated_by_role_contract"
    ADAPTER_NOT_SUPPORTED = "adapter_not_supported"
    CAPABILITY_MISSING = "capability_missing"
    EXCLUSIVE_GROUP = "exclusive_group"
    OVER_SKILL_BUDGET = "over_skill_budget"
    TRIGGER_NOT_MET = "trigger_not_met"
    ROLE_NOT_APPLICABLE = "role_not_applicable"
    SCOPE_MISMATCH = "scope_mismatch"
    CONFLICT_LOWER_PRIORITY = "conflict_lower_priority"
    NO_MATCHING_SECTIONS = "no_matching_sections"
    HOST_BUDGET_EXCEEDED = "host_budget_exceeded"
    OPTIONAL_DISABLED = "optional_disabled"
    HISTORY_WINDOW = "history_window"
    TYPE_NOT_IN_POLICY = "type_not_in_policy"
    FULL_PROMPT = "full_prompt"
    OVER_BUDGET_CORE = "over_budget_core"
    OVER_BUDGET_SUPPORTING = "over_budget_supporting"
    OVER_BUDGET_RETRIEVAL = "over_budget_retrieval"
    OVER_TOTAL_BUDGET = "over_total_budget"
    SKILLS_DISABLED = "skills_disabled"
    OVER_SKILL_COUNT = "over_skill_count"
    SYMLINK_REFUSED = "symlink_refused"
    REPO_INSTRUCTIONS_MAX_FILES = "repo_instructions_max_files"
    RUNTIME_SELF_LOADED = "runtime_self_loaded"
    IN_RESUMED_SESSION = "in_resumed_session"


HIDDEN_REASONS = frozenset(
    {
        ExcludeReason.CLASSIFICATION_FORBIDDEN,
        ExcludeReason.QUARANTINED,
        ExcludeReason.TRUST_FORBIDDEN,
        ExcludeReason.VERSION_UNAVAILABLE,
        ExcludeReason.FILE_VERSION_NOT_READY,
        ExcludeReason.NOT_FOUND,
    }
)
