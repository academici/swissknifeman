"""Agent profile: the typed form of ``agent-profiles/<key>.toml`` (extensions §4.6).

``parse_agent_profile`` takes a document already validated by ``urn:skm:extensions:agent-profile:v1``. A
profile never grants anything: ``check_profile_trust`` refuses what its pack may not ask for, the comparison
against the ceiling lives in ``permission_guard`` with the comparator of the application layer.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.modules.extensions.domain.keys import SemVer
from skm.modules.extensions.domain.pack import PackTrust

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.extensions.domain.keys import ResourceKey

__all__ = [
    "TRUSTED_FULL_ACCESS",
    "AgentPermissions",
    "AgentProfile",
    "ContextPolicySpec",
    "PromptPlan",
    "RoleLimits",
    "check_profile_trust",
    "default_profile_key",
    "parse_agent_profile",
    "require_role",
]

TRUSTED_FULL_ACCESS: Final = "trusted-full-access"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    key: ResourceKey
    version: SemVer
    role: str
    title: str
    description: str
    result_schema: str
    model_class: str
    effort: str
    required_capabilities: frozenset[str]
    optional_capabilities: frozenset[str]
    isolation: str
    permissions: AgentPermissions
    prompt: PromptPlan
    context: JsonObject
    limits: RoleLimits
    llm: bool


@dataclass(frozen=True, slots=True)
class PromptPlan:
    blocks: Mapping[str, tuple[ResourceKey, ...]]


@dataclass(frozen=True, slots=True)
class RoleLimits:
    timeout_seconds: int
    idle_timeout_seconds: int
    max_turns: int | None
    max_output_tokens: int | None
    max_result_retries: int


@dataclass(frozen=True, slots=True)
class AgentPermissions:
    policy_profile: str
    layer: Mapping[str, JsonValue] | None


type ContextPolicySpec = JsonObject


def default_profile_key(role: str) -> ResourceKey:
    return role.replace("_", "-")


def parse_agent_profile(document: Mapping[str, object]) -> AgentProfile:
    routing = cast("Mapping[str, object]", document["routing"])
    isolation = cast("Mapping[str, str]", document["isolation"])
    permissions = cast("Mapping[str, object]", document["permissions"])
    prompt = cast("Mapping[str, list[str]]", document["prompt"])
    context = cast("JsonObject", copy.deepcopy(dict(cast("Mapping[str, object]", document["context"]))))
    limits = cast("Mapping[str, int]", document["limits"])
    sections = cast("list[str]", context.get("repo_instruction_sections", []))
    if context.get("repo_instructions") == "constraints" and (not sections or "*" in sections):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "repo_instructions = constraints needs named sections",
            details={"reason": "constraints_without_sections", "key": cast("str", document["key"])},
        )
    layer = permissions.get("layer")
    return AgentProfile(
        key=cast("str", document["key"]),
        version=SemVer.parse(cast("str", document["version"])),
        role=cast("str", document["role"]),
        title=cast("str", document["title"]),
        description=cast("str", document["description"]),
        result_schema=cast("str", document["result_schema"]),
        model_class=cast("str", routing["model_class"]),
        effort=cast("str", routing["effort"]),
        required_capabilities=frozenset(cast("list[str]", routing.get("required_capabilities", []))),
        optional_capabilities=frozenset(cast("list[str]", routing.get("optional_capabilities", []))),
        isolation=isolation["profile"],
        permissions=AgentPermissions(
            policy_profile=cast("str", permissions["policy_profile"]),
            layer=None if layer is None else copy.deepcopy(cast("dict[str, JsonValue]", layer)),
        ),
        prompt=PromptPlan({block: tuple(keys) for block, keys in prompt.items()}),
        context=context,
        limits=RoleLimits(
            timeout_seconds=limits["timeout_seconds"],
            idle_timeout_seconds=limits["idle_timeout_seconds"],
            max_turns=limits.get("max_turns"),
            max_output_tokens=limits.get("max_output_tokens"),
            max_result_retries=limits["max_result_retries"],
        ),
        llm=cast("bool", document.get("llm", True)),
    )


def check_profile_trust(profile: AgentProfile, trust: PackTrust) -> None:
    """§4.6 rule 3: what a pack of this trust may not ask for, whatever the ceiling says."""
    if trust is PackTrust.THIRD_PARTY:
        if profile.context.get("inherit_user_global") is True:
            raise PreconditionFailed(
                ErrorCode.EXTENSION_INCOMPATIBLE,
                "a third party profile cannot inherit the user's client configuration",
                details={"reason": "inherit_user_global_third_party", "key": profile.key},
            )
        if profile.permissions.policy_profile == TRUSTED_FULL_ACCESS:
            raise PreconditionFailed(
                ErrorCode.EXTENSION_INCOMPATIBLE,
                "a third party profile cannot ask for trusted-full-access",
                details={"reason": "trusted_full_access_third_party", "key": profile.key},
            )


def require_role(profile_role: object, *, key: ResourceKey, expected: str) -> None:
    """§4.6 rule 2: the resolved profile must be declared for the requested role."""
    if profile_role != expected:
        raise PreconditionFailed(
            ErrorCode.EXTENSION_PROFILE_ROLE_MISMATCH,
            f"profile {key} is declared for another role",
            details={"key": key, "role": str(profile_role), "expected": expected},
        )
