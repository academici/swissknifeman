"""Effective permissions from configuration (policy §5.1).

``compose_effective`` = profile ∩ ceiling ∩ restrictions of every level ∩ role layer ∩ task layer. The ceiling
always contributes ``policy.ceiling.network_allowlist`` as a host list: with ``network = allowlist`` the
default empty list forbids every host (FOUNDATION-04, K16, D-REG-13); unrestricted network needs
``policy.ceiling.network = any``. Built-in profiles are data of this module (``profiles/*.toml``); a custom
profile cannot shadow a built-in id. A profile with ``requires_host_flag`` runs only where the host sets
``policy.host.allow_unconfined``; without it ``none`` leaves every profile's isolation set.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from importlib import resources
from typing import Protocol, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.isolation import IsolationProfile
from skm.kernel.json_types import JsonValue
from skm.modules.policy.domain.commands import CommandMode, CommandsLayer
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode
from skm.modules.policy.domain.operations import AccessCapability, OperationName, TaskAuthority
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope, unrestricted_policy
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet, narrow_all
from skm.modules.policy.domain.profiles import BUILTIN_PROFILE_IDS, PolicyProfile, parse_layer, parse_profile
from skm.modules.policy.domain.tool_intent import EffectKind
from skm.platform.config.sources.document import decode_document

__all__ = [
    "SHELL_FREE_TOOLS",
    "ConfigReader",
    "builtin_profiles",
    "ceiling_layer",
    "compose_effective",
    "denylist_pattern",
    "forbidden_paths_layer",
    "resolve_profile",
    "restriction_layers",
    "task_authority_from",
]

SHELL_FREE_TOOLS = frozenset(
    {"fs.read", "fs.write", "fs.edit", "fs.delete", "web.fetch", "web.search", "mcp:*"}
)


class ConfigReader(Protocol):
    """The part of ``EffectiveConfig`` composition reads (tests pass a mapping-backed fake)."""

    def get(self, key: str) -> JsonValue | None: ...


@lru_cache(maxsize=1)
def builtin_profiles() -> Mapping[str, PolicyProfile]:
    """The three built-in profiles, parsed once from the module data."""
    folder = resources.files("skm.modules.policy").joinpath("profiles")
    result: dict[str, PolicyProfile] = {}
    for profile_id in BUILTIN_PROFILE_IDS:
        text = folder.joinpath(f"{profile_id}.toml").read_text(encoding="utf-8")
        profile = parse_profile(decode_document(text, "toml"))
        if profile.id != profile_id:
            raise ValueError(f"built-in profile file {profile_id}.toml declares id {profile.id!r}")
        result[profile_id] = profile
    return result


def _list(config: ConfigReader, key: str) -> list[JsonValue]:
    value = config.get(key)
    return cast("list[JsonValue]", value) if isinstance(value, list) else []


def resolve_profile(config: ConfigReader, profile_id: str) -> PolicyProfile:
    custom = config.get("policy.profiles")
    if isinstance(custom, Mapping) and set(custom) & set(BUILTIN_PROFILE_IDS):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "custom policy profiles cannot shadow built-in profiles",
            details={"reason": "builtin_profile_shadow"},
        )
    builtin = builtin_profiles().get(profile_id)
    if builtin is not None:
        return builtin
    documents: Mapping[str, JsonValue] = (
        cast("Mapping[str, JsonValue]", custom) if isinstance(custom, Mapping) else {}
    )
    document = documents.get(profile_id)
    if not isinstance(document, Mapping):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"unknown policy profile {profile_id!r}",
            details={"profile_id": profile_id, "reason": "unknown_profile"},
        )
    profile = parse_profile(cast("Mapping[str, object]", document))
    if profile.id != profile_id:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"policy profile {profile_id!r} declares id {profile.id!r}",
            details={"profile_id": profile_id, "reason": "profile_id_mismatch"},
        )
    return profile


def denylist_pattern(prefix: str) -> str:
    """``policy.ceiling.commands_denylist`` prefix → deny regex (§5.1)."""
    return r"(?:^|[;&|(]\s*)" + re.escape(prefix) + r"(?=\s|$|[;&|)])"


def ceiling_layer(config: ConfigReader) -> PermissionLayer:
    shell = config.get("policy.ceiling.shell") is not False
    network = config.get("policy.ceiling.network")
    return PermissionLayer(
        source="ceiling",
        commands=CommandsLayer(
            mode=None if shell else CommandMode.NONE,
            deny_patterns=tuple(
                denylist_pattern(str(item)) for item in _list(config, "policy.ceiling.commands_denylist")
            ),
        ),
        network=NetworkLayer(
            mode=NetworkMode(network) if isinstance(network, str) else NetworkMode.NONE,
            hosts=frozenset(str(host) for host in _list(config, "policy.ceiling.network_allowlist")),
        ),
        tools=None if shell else SHELL_FREE_TOOLS,
        external_effects=frozenset(
            EffectKind(str(item)) for item in _list(config, "policy.ceiling.external_effects")
        ),
        effects_need_approval=frozenset(
            EffectKind(str(item)) for item in _list(config, "policy.approval.required_for")
        ),
        allowed_isolation=frozenset(str(item) for item in _list(config, "policy.ceiling.isolation_profiles")),
    )


def _restriction_sources(config: ConfigReader, count: int) -> tuple[str, ...]:
    """``restriction:<level>:<i>`` from the provenance of an ``EffectiveConfig``; ``restriction:<i>`` else."""
    from skm.platform.config.effective import EffectiveConfig

    fallback = tuple(f"restriction:{index}" for index in range(count))
    if not isinstance(config, EffectiveConfig):
        return fallback
    labels: list[str] = []
    for item in config.provenance("policy.restrictions").trace:
        contribution = item.contribution
        if item.status in {"winner", "used"} and isinstance(contribution.value, list):
            level = contribution.layer.level.value
            labels.extend(f"restriction:{level}:{index}" for index in range(len(contribution.value)))
    return tuple(labels) if len(labels) == count else fallback


def restriction_layers(config: ConfigReader) -> tuple[PermissionLayer, ...]:
    documents = _list(config, "policy.restrictions")
    sources = _restriction_sources(config, len(documents))
    layers: list[PermissionLayer] = []
    for source, document in zip(sources, documents, strict=True):
        if not isinstance(document, Mapping):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "a restriction must be a permission layer",
                details={"source": source},
            )
        layers.append(parse_layer(cast("Mapping[str, object]", document), source=source))
    return tuple(layers)


def compose_effective(
    config: ConfigReader,
    *,
    profile_id: str | None,
    role_layer: PermissionLayer | None,
    task_layer: PermissionLayer | None,
    allow_unconfined: bool,
    interactive: bool = False,
) -> PermissionSet:
    default_key = "policy.interactive.profile" if interactive else "policy.default_profile"
    chosen = profile_id or config.get(default_key)
    if not isinstance(chosen, str):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "no policy profile is configured",
            details={"profile_id": None, "reason": "unknown_profile"},
        )
    profile = resolve_profile(config, chosen)
    if profile.requires_host_flag and not allow_unconfined:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            f"profile {profile.id} needs policy.host.allow_unconfined on this host",
            details={"reason": "unconfined_not_allowed_on_host", "profile_id": profile.id},
        )
    base = profile.permissions
    if not allow_unconfined:
        base = PermissionSet(
            fs_read=base.fs_read,
            fs_write=base.fs_write,
            commands=base.commands,
            network=base.network,
            tools=base.tools,
            operations=base.operations,
            external_effects=base.external_effects,
            effects_need_approval=base.effects_need_approval,
            allowed_isolation=base.allowed_isolation - {IsolationProfile.NONE.value},
            sources=base.sources,
        )
    return narrow_all(base, (ceiling_layer(config), *restriction_layers(config), role_layer, task_layer))


def task_authority_from(
    config: ConfigReader,
    *,
    write_scope: tuple[PathRule, ...] | None,
    delete_scope: Sequence[PathRule] = (),
) -> TaskAuthority:
    """Authority of one task: its scopes plus the configured operations and granted ∩ allowed capabilities."""
    allowed = {str(item) for item in _list(config, "policy.access_capabilities.allowed")}
    granted = {str(item) for item in _list(config, "policy.access_capabilities.granted")}
    return TaskAuthority(
        write_scope=write_scope,
        delete_scope=tuple(delete_scope),
        operations=frozenset(
            OperationName(str(item)) for item in _list(config, "policy.task_authority.operations")
        ),
        capabilities=frozenset(AccessCapability(item) for item in sorted(allowed & granted)),
    )


def forbidden_paths_layer(forbidden: Sequence[tuple[str, str]], *, source: str) -> PermissionLayer:
    """Task layer of execution: each ``(mount, pattern)`` of ``forbidden_paths`` is denied for writing."""
    deny = tuple(PathRule(PathScope.WORKTREE, pattern, mount or None) for mount, pattern in forbidden)
    return PermissionLayer(source=source, fs_write=PathPolicy(unrestricted_policy().allow, deny))
