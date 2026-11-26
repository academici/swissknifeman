"""Unit tests for agent profile parsing, golden inheritance matrix, trust and role validation (P09.02.b)."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.modules.extensions.domain.agent_profile import (
    TRUSTED_FULL_ACCESS,
    check_profile_trust,
    default_profile_key,
    parse_agent_profile,
    require_role,
)
from skm.modules.extensions.domain.keys import SemVer
from skm.modules.extensions.domain.pack import PackTrust
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES_PROFILES_DIR = ROOT / "tests/fixtures/corpus/examples" / "agent-profiles"
CORE_PROFILES_DIR = ROOT / "resources" / "packs" / "core" / "agent-profiles"

EXPECTED_PROFILE_ROLES: dict[str, str] = {
    "scout": "scout",
    "executor": "executor",
    "executor-transparent": "executor",
    "reviewer": "reviewer",
    "security": "reviewer",
    "triager": "triager",
    "advisor": "advisor",
    "advisor-critic": "advisor",
    "plan-auditor": "advisor",
    "researcher": "researcher",
    "registrar": "registrar",
}

GOLDEN_CONTEXT_MATRIX: dict[str, tuple[bool, str, list[str], str, list[str]]] = {
    "scout": (False, "constraints", ["Constraints", "Security", "Read only"], "allowlist", []),
    "executor": (False, "full", [], "auto", []),
    "executor-transparent": (True, "full", [], "auto", []),
    "reviewer": (
        False,
        "constraints",
        ["Constraints", "Conventions", "Testing", "Security"],
        "allowlist",
        ["code-review", "review-checklist"],
    ),
    "security": (
        False,
        "constraints",
        ["Constraints", "Conventions", "Testing", "Security"],
        "allowlist",
        ["code-review", "review-checklist", "security-review"],
    ),
    "triager": (False, "none", [], "allowlist", []),
    "advisor": (False, "constraints", ["Constraints", "Decisions"], "allowlist", []),
    "advisor-critic": (False, "constraints", ["Constraints", "Decisions"], "allowlist", []),
    "plan-auditor": (False, "constraints", ["Constraints", "Decisions"], "allowlist", []),
    "researcher": (False, "none", [], "allowlist", ["research-method"]),
    "registrar": (False, "none", [], "none", []),
}


def _load_profile_doc(directory: Path, key: str) -> dict[str, Any]:
    path = directory / f"{key}.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("directory", [EXAMPLES_PROFILES_DIR, CORE_PROFILES_DIR], ids=["examples", "core"])
def test_parse_all_eleven_profiles_and_schema_validation(directory: Path) -> None:
    schema_reg = SchemaRegistry.load_default()
    files = sorted(directory.glob("*.toml"))
    assert {f.stem for f in files} == set(EXPECTED_PROFILE_ROLES)

    for path in files:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        assert schema_reg.validate("urn:skm:extensions:agent-profile:v1", doc) == ()
        profile = parse_agent_profile(doc)
        expected_role = EXPECTED_PROFILE_ROLES[path.stem]
        assert profile.key == path.stem
        assert profile.version == SemVer.parse("2.0.0")
        assert profile.role == expected_role
        assert profile.result_schema == f"urn:skm:execution:role-result:{expected_role}:v1"
        assert profile.isolation == "worktree"
        expected_policy = (
            "workspace-contained" if profile.key in {"executor", "executor-transparent"} else "read-only"
        )
        assert profile.permissions.policy_profile == expected_policy
        assert (profile.llm is False) == (profile.key == "registrar")
        assert profile.limits.timeout_seconds > 0
        assert profile.limits.idle_timeout_seconds > 0
        assert "shared/work_policy" in profile.prompt.blocks["task_contract"]


@pytest.mark.parametrize("directory", [EXAMPLES_PROFILES_DIR, CORE_PROFILES_DIR], ids=["examples", "core"])
def test_golden_inheritance_and_context_matrix(directory: Path) -> None:
    for key, (
        inherit_user_global,
        repo_instructions,
        sections,
        skills_mode,
        skills_include,
    ) in GOLDEN_CONTEXT_MATRIX.items():
        doc = _load_profile_doc(directory, key)
        profile = parse_agent_profile(doc)
        ctx = profile.context
        assert ctx["inherit_user_global"] is inherit_user_global, key
        assert ctx["repo_instructions"] == repo_instructions, key
        assert list(cast("list[str]", ctx.get("repo_instruction_sections", []))) == sections, key
        expected_skills_mode = (
            "auto"
            if directory == EXAMPLES_PROFILES_DIR and key in {"advisor", "advisor-critic", "plan-auditor"}
            else skills_mode
        )
        assert ctx["skills_mode"] == expected_skills_mode, key
        assert list(cast("list[str]", ctx.get("skills_include", []))) == skills_include, key


def test_constraints_without_named_sections_rejected() -> None:
    base = _load_profile_doc(CORE_PROFILES_DIR, "reviewer")

    empty_sections = copy.deepcopy(base)
    empty_sections["context"]["repo_instruction_sections"] = []
    with pytest.raises(ValidationFailed) as exc_empty:
        parse_agent_profile(empty_sections)
    assert exc_empty.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_empty.value.details == {"reason": "constraints_without_sections", "key": "reviewer"}

    wildcard_sections = copy.deepcopy(base)
    wildcard_sections["context"]["repo_instruction_sections"] = ["Constraints", "*"]
    with pytest.raises(ValidationFailed) as exc_wild:
        parse_agent_profile(wildcard_sections)
    assert exc_wild.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_wild.value.details == {"reason": "constraints_without_sections", "key": "reviewer"}


def test_invalid_result_schema_urn_rejected_by_schema() -> None:
    schema_reg = SchemaRegistry.load_default()
    doc = _load_profile_doc(CORE_PROFILES_DIR, "security")
    doc["result_schema"] = "urn:skm:invalid:schema"
    errors = schema_reg.validate("urn:skm:extensions:agent-profile:v1", doc)
    assert len(errors) >= 1


def test_check_profile_trust_enforces_third_party_boundaries() -> None:
    transparent_doc = _load_profile_doc(CORE_PROFILES_DIR, "executor-transparent")
    transparent_profile = parse_agent_profile(transparent_doc)

    check_profile_trust(transparent_profile, PackTrust.BUILTIN)
    check_profile_trust(transparent_profile, PackTrust.OPERATOR)

    with pytest.raises(PreconditionFailed) as exc_inherit:
        check_profile_trust(transparent_profile, PackTrust.THIRD_PARTY)
    assert exc_inherit.value.code is ErrorCode.EXTENSION_INCOMPATIBLE
    assert exc_inherit.value.details == {
        "reason": "inherit_user_global_third_party",
        "key": "executor-transparent",
    }

    trusted_doc = _load_profile_doc(CORE_PROFILES_DIR, "executor")
    trusted_doc["permissions"]["policy_profile"] = TRUSTED_FULL_ACCESS
    trusted_profile = parse_agent_profile(trusted_doc)

    check_profile_trust(trusted_profile, PackTrust.OPERATOR)
    with pytest.raises(PreconditionFailed) as exc_full:
        check_profile_trust(trusted_profile, PackTrust.THIRD_PARTY)
    assert exc_full.value.code is ErrorCode.EXTENSION_INCOMPATIBLE
    assert exc_full.value.details == {
        "reason": "trusted_full_access_third_party",
        "key": "executor",
    }


def test_default_profile_key_and_require_role_and_key_rules() -> None:
    assert default_profile_key("reviewer") == "reviewer"
    assert default_profile_key("plan_auditor") == "plan-auditor"

    security = parse_agent_profile(_load_profile_doc(CORE_PROFILES_DIR, "security"))
    require_role(security.role, key=security.key, expected="reviewer")

    with pytest.raises(PreconditionFailed) as exc_role:
        require_role(security.role, key=security.key, expected="executor")
    assert exc_role.value.code is ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH
    assert exc_role.value.details == {"key": "security", "role": "reviewer", "expected": "executor"}

    for key in EXPECTED_PROFILE_ROLES:
        assert "/" not in key
