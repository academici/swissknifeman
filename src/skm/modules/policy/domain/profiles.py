"""Policy profiles and permission documents (policy §§4.5, 5.12 ``parse_profile``).

Documents are validated here, independently of the JSON Schema registry, so the pure core refuses what the
schemas refuse: unknown fields and enum values, a missing operation (never "allow by default"), a regular
expression that does not compile (the index is in ``details``). Every refusal is ``SCHEMA_INVALID``.
Built-in profiles are data of the policy module (``profiles/*.toml``), never extension resources.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.isolation import is_builtin_isolation_profile, is_plugin_isolation_profile

from .commands import CommandMode, CommandPolicy, CommandRule, CommandsLayer
from .network import NetworkLayer, NetworkMode, NetworkPolicy
from .operations import AccessCapability, OperationDecision, OperationName, OperationRule, rule_from_decision
from .paths import PathPolicy, PathRule, PathScope, unrestricted_policy
from .permission_set import PermissionLayer, PermissionSet
from .tool_intent import EffectKind, RiskClass

__all__ = [
    "BUILTIN_PROFILE_IDS",
    "PROFILE_SCHEMA",
    "PolicyProfile",
    "parse_layer",
    "parse_profile",
    "permission_set_from_document",
]

PROFILE_SCHEMA = "urn:skm:policy:profile:v1"
BUILTIN_PROFILE_IDS = ("workspace-contained", "read-only", "trusted-full-access")

_ID_RE = re.compile(r"[a-z][a-z0-9-]{1,40}")
_SEMVER_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_MOUNT_RE = re.compile(r"[a-z][a-z0-9_-]{0,39}")
_PATTERN_RE = re.compile(r"(?!/)(?!.*(^|/)\.\.(/|$))[^\x00]+", re.DOTALL)
_PROGRAM_RE = re.compile(r"[A-Za-z0-9_.+-]{1,64}")
_SUBCOMMAND_RE = re.compile(r"(\*|[a-z0-9][a-z0-9-]{0,63})(:[a-z0-9][a-z0-9-]{0,63})?")
_HOST_RE = re.compile(r"(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?")
_TOOL_RE = re.compile(
    r"fs\.(read|write|edit|delete)|shell\.run|web\.(fetch|search)|mcp:\*"
    r"|mcp:[a-z0-9][a-z0-9_-]{0,63}/(\*|[A-Za-z0-9_.-]{1,128})"
)
_PROFILE_KEYS = frozenset(
    {
        "schema",
        "id",
        "version",
        "description",
        "requires_host_flag",
        "allowed_isolation",
        "fs",
        "commands",
        "network",
        "tools",
        "effects",
        "operations",
    }
)
_LAYER_KEYS = frozenset(
    {"allowed_isolation", "fs", "commands", "network", "tools", "effects", "operations", "source"}
)
_COMMAND_KEYS = (
    "mode",
    "programs",
    "subcommands",
    "deny_patterns",
    "ask_patterns",
    "inline_interpreters",
    "trust_inline_interpreters",
)
_VIEW_KEYS = frozenset(
    {
        "fs_read",
        "fs_write",
        "commands",
        "network",
        "tools",
        "operations",
        "external_effects",
        "effects_need_approval",
        "allowed_isolation",
        "sources",
        "digest",
    }
)


@dataclass(frozen=True, slots=True)
class PolicyProfile:
    id: str
    version: str
    description: str
    requires_host_flag: bool
    permissions: PermissionSet


def _fail(pointer: str, reason: str, **extra: str | int) -> NoReturn:
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"policy document is invalid at {pointer or '/'}: {reason}",
        details={"pointer": pointer, "reason": reason, **extra},
    )


def _object(value: object, pointer: str, keys: frozenset[str] | tuple[str, ...]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(pointer, "expected an object")
    mapping = cast("Mapping[str, object]", value)
    unknown = sorted(set(mapping) - set(keys))
    if unknown:
        _fail(f"{pointer}/{unknown[0]}", "unknown field")
    return mapping


def _require(mapping: Mapping[str, object], pointer: str, *keys: str) -> None:
    for key in keys:
        if key not in mapping:
            _fail(f"{pointer}/{key}", "required field is missing")


def _bool(value: object, pointer: str) -> bool:
    if not isinstance(value, bool):
        _fail(pointer, "expected a boolean")
    return value


def _string(value: object, pointer: str, pattern: re.Pattern[str] | None = None, *, limit: int = 500) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        _fail(pointer, "expected a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail(pointer, "value does not match its pattern")
    return value


def _strings(value: object, pointer: str, pattern: re.Pattern[str] | None = None) -> tuple[str, ...]:
    if not isinstance(value, list):
        _fail(pointer, "expected an array")
    items = cast("list[object]", value)
    result = tuple(
        _string(item, f"{pointer}/{index}", pattern, limit=2000) for index, item in enumerate(items)
    )
    if len(set(result)) != len(result) and pattern is not None:
        _fail(pointer, "items must be unique")
    return result


def _enum[E: StrEnum](kind: type[E], value: object, pointer: str) -> E:
    if isinstance(value, str):
        for member in kind:
            if member.value == value:
                return member
    _fail(pointer, f"unknown {kind.__name__} value")


def _enums[E: StrEnum](kind: type[E], value: object, pointer: str) -> frozenset[E]:
    items = _strings(value, pointer)
    if len(set(items)) != len(items):
        _fail(pointer, "items must be unique")
    return frozenset(_enum(kind, item, f"{pointer}/{index}") for index, item in enumerate(items))


def _regexes(value: object, pointer: str) -> tuple[str, ...]:
    patterns = _strings(value, pointer)
    for index, pattern in enumerate(patterns):
        try:
            re.compile(pattern)
        except re.error as error:
            _fail(f"{pointer}/{index}", "regex does not compile", index=index, error=str(error))
    return patterns


def _isolation(value: object, pointer: str, *, allow_empty: bool) -> frozenset[str]:
    items = _strings(value, pointer)
    if not items and not allow_empty:
        _fail(pointer, "at least one isolation profile is required")
    if len(set(items)) != len(items):
        _fail(pointer, "items must be unique")
    for index, item in enumerate(items):
        if not (is_builtin_isolation_profile(item) or is_plugin_isolation_profile(item)):
            _fail(f"{pointer}/{index}", "unknown isolation profile")
    return frozenset(items)


def _path_rule(value: object, pointer: str) -> PathRule:
    mapping = _object(value, pointer, ("scope", "pattern", "mount"))
    _require(mapping, pointer, "scope", "pattern")
    scope = _enum(PathScope, mapping["scope"], f"{pointer}/scope")
    pattern = _string(mapping["pattern"], f"{pointer}/pattern", _PATTERN_RE)
    mount = None
    if "mount" in mapping:
        mount = _string(mapping["mount"], f"{pointer}/mount", _MOUNT_RE)
        if scope is not PathScope.WORKTREE:
            _fail(f"{pointer}/mount", "mount is only valid with scope worktree")
    return PathRule(scope, pattern, mount)


def _path_rules(value: object, pointer: str) -> tuple[PathRule, ...]:
    if not isinstance(value, list) or len(cast("list[object]", value)) > 200:
        _fail(pointer, "expected an array of at most 200 path rules")
    return tuple(
        _path_rule(item, f"{pointer}/{index}") for index, item in enumerate(cast("list[object]", value))
    )


def _path_policy(value: object, pointer: str, *, partial: bool) -> PathPolicy | None:
    mapping = _object(value, pointer, ("allow", "deny"))
    if not partial:
        _require(mapping, pointer, "allow", "deny")
    elif not mapping:
        return None
    deny = _path_rules(mapping.get("deny", []), f"{pointer}/deny")
    if "allow" not in mapping:
        return PathPolicy(unrestricted_policy().allow, deny)
    return PathPolicy(_path_rules(mapping["allow"], f"{pointer}/allow"), deny)


def _command_rules(mapping: Mapping[str, object], pointer: str, *, partial: bool) -> tuple[CommandRule, ...]:
    """Programs and subcommands; in a layer an empty subcommand list removes the program (§4.4), a profile
    lists at least one."""
    programs = _strings(mapping.get("programs", []), f"{pointer}/programs", _PROGRAM_RE)
    subcommands_doc = mapping.get("subcommands", {})
    if not isinstance(subcommands_doc, Mapping):
        _fail(f"{pointer}/subcommands", "expected an object")
    rules = {program: CommandRule(program, None) for program in programs}
    for program, subs in cast("Mapping[str, object]", subcommands_doc).items():
        _string(program, f"{pointer}/subcommands", _PROGRAM_RE)
        values = _strings(subs, f"{pointer}/subcommands/{program}", _SUBCOMMAND_RE)
        if not values and not partial:
            _fail(f"{pointer}/subcommands/{program}", "at least one subcommand is required")
        if program not in rules:
            rules[program] = CommandRule(program, frozenset(values))
    return tuple(rule for rule in rules.values() if rule.subcommands is None or rule.subcommands)


def _command_policy(value: object, pointer: str) -> CommandPolicy:
    mapping = _object(value, pointer, _COMMAND_KEYS)
    _require(mapping, pointer, *_COMMAND_KEYS)
    return CommandPolicy(
        mode=_enum(CommandMode, mapping["mode"], f"{pointer}/mode"),
        allow=_command_rules(mapping, pointer, partial=False),
        deny_patterns=_regexes(mapping["deny_patterns"], f"{pointer}/deny_patterns"),
        ask_patterns=_regexes(mapping["ask_patterns"], f"{pointer}/ask_patterns"),
        inline_interpreters=frozenset(
            _strings(mapping["inline_interpreters"], f"{pointer}/inline_interpreters", _PROGRAM_RE)
        ),
        trust_inline_interpreters=_bool(
            mapping["trust_inline_interpreters"], f"{pointer}/trust_inline_interpreters"
        ),
    )


def _commands_layer(value: object, pointer: str) -> CommandsLayer:
    mapping = _object(value, pointer, _COMMAND_KEYS)
    listed = "programs" in mapping or "subcommands" in mapping
    trust = mapping.get("trust_inline_interpreters")
    return CommandsLayer(
        mode=None if "mode" not in mapping else _enum(CommandMode, mapping["mode"], f"{pointer}/mode"),
        allow=_command_rules(mapping, pointer, partial=True) if listed else None,
        deny_patterns=_regexes(mapping.get("deny_patterns", []), f"{pointer}/deny_patterns"),
        ask_patterns=_regexes(mapping.get("ask_patterns", []), f"{pointer}/ask_patterns"),
        inline_interpreters=frozenset(
            _strings(mapping.get("inline_interpreters", []), f"{pointer}/inline_interpreters", _PROGRAM_RE)
        ),
        trust_inline_interpreters=None
        if trust is None
        else _bool(trust, f"{pointer}/trust_inline_interpreters"),
    )


def _network(
    value: object, pointer: str, *, partial: bool, composed: bool = False
) -> tuple[NetworkMode | None, tuple[str, ...] | None]:
    mapping = _object(value, pointer, ("mode", "hosts"))
    if not partial:
        _require(mapping, pointer, "mode", "hosts")
    mode = None if "mode" not in mapping else _enum(NetworkMode, mapping["mode"], f"{pointer}/mode")
    hosts = None if "hosts" not in mapping else _strings(mapping["hosts"], f"{pointer}/hosts", _HOST_RE)
    if hosts and mode in {NetworkMode.NONE, NetworkMode.ANY}:
        _fail(f"{pointer}/hosts", "hosts are only valid with mode allowlist")
    if not partial and not composed and mode is NetworkMode.ALLOWLIST and not hosts:
        # a profile states "no host" as mode none; only composition reaches an empty list (layer, view)
        _fail(f"{pointer}/hosts", "mode allowlist needs at least one host")
    return mode, hosts


def _tools(value: object, pointer: str, *, partial: bool) -> frozenset[str] | None:
    mapping = _object(value, pointer, ("allow",))
    if not partial:
        _require(mapping, pointer, "allow")
    if "allow" not in mapping:
        return None
    return frozenset(_strings(mapping["allow"], f"{pointer}/allow", _TOOL_RE))


def _effects(
    value: object, pointer: str, *, partial: bool
) -> tuple[frozenset[EffectKind] | None, frozenset[EffectKind] | None]:
    mapping = _object(value, pointer, ("allow", "need_approval"))
    if not partial:
        _require(mapping, pointer, "allow", "need_approval")
    allow = None if "allow" not in mapping else _enums(EffectKind, mapping["allow"], f"{pointer}/allow")
    need = (
        None
        if "need_approval" not in mapping
        else _enums(EffectKind, mapping["need_approval"], f"{pointer}/need_approval")
    )
    return allow, need


def _operation_rule(value: object, pointer: str) -> OperationRule:
    mapping = _object(value, pointer, ("decision", "capability", "risk"))
    _require(mapping, pointer, "decision")
    decision = _enum(OperationDecision, mapping["decision"], f"{pointer}/decision")
    capability = None
    if "capability" in mapping:
        capability = _enum(AccessCapability, mapping["capability"], f"{pointer}/capability")
    if (decision is OperationDecision.CAPABILITY) != (capability is not None):
        _fail(f"{pointer}/capability", "capability is given exactly for the capability decision")
    risk = None if "risk" not in mapping else _enum(RiskClass, mapping["risk"], f"{pointer}/risk")
    return rule_from_decision(decision, capability=capability, risk=risk)


def _operations(value: object, pointer: str, *, partial: bool) -> dict[OperationName, OperationRule]:
    mapping = _object(value, pointer, tuple(item.value for item in OperationName))
    if not partial:
        _require(mapping, pointer, *(item.value for item in OperationName))
    return {OperationName(key): _operation_rule(item, f"{pointer}/{key}") for key, item in mapping.items()}


def parse_profile(doc: Mapping[str, object]) -> PolicyProfile:
    """A ``urn:skm:policy:profile:v1`` document → profile; any defect is ``SCHEMA_INVALID``."""
    mapping = _object(doc, "", _PROFILE_KEYS)
    _require(mapping, "", *sorted(_PROFILE_KEYS))
    if mapping["schema"] != PROFILE_SCHEMA:
        _fail("/schema", f"expected {PROFILE_SCHEMA}")
    profile_id = _string(mapping["id"], "/id", _ID_RE)
    version = _string(mapping["version"], "/version", _SEMVER_RE)
    fs = _object(mapping["fs"], "/fs", ("read", "write"))
    _require(fs, "/fs", "read", "write")
    mode, hosts = _network(mapping["network"], "/network", partial=False)
    allow_effects, need_approval = _effects(mapping["effects"], "/effects", partial=False)
    permissions = PermissionSet(
        fs_read=(cast("PathPolicy", _path_policy(fs["read"], "/fs/read", partial=False)),),
        fs_write=(cast("PathPolicy", _path_policy(fs["write"], "/fs/write", partial=False)),),
        commands=_command_policy(mapping["commands"], "/commands"),
        network=NetworkPolicy(
            cast("NetworkMode", mode), (frozenset(hosts or ()),) if mode is NetworkMode.ALLOWLIST else ()
        ),
        tools=(cast("frozenset[str]", _tools(mapping["tools"], "/tools", partial=False)),),
        operations=_operations(mapping["operations"], "/operations", partial=False),
        external_effects=cast("frozenset[EffectKind]", allow_effects),
        effects_need_approval=cast("frozenset[EffectKind]", need_approval),
        allowed_isolation=_isolation(mapping["allowed_isolation"], "/allowed_isolation", allow_empty=False),
        sources=(f"profile:{profile_id}@{version}",),
    )
    return PolicyProfile(
        id=profile_id,
        version=version,
        description=_string(mapping["description"], "/description"),
        requires_host_flag=_bool(mapping["requires_host_flag"], "/requires_host_flag"),
        permissions=permissions,
    )


def parse_layer(doc: Mapping[str, object], *, source: str) -> PermissionLayer:
    """A ``urn:skm:policy:permission-layer:v1`` document → layer; absent fields do not narrow."""
    mapping = _object(doc, "", _LAYER_KEYS)
    label = mapping.get("source")
    if label is not None:
        source = f"{source}#{_string(label, '/source')}"
    fs = _object(mapping.get("fs", {}), "/fs", ("read", "write"))
    network = None
    if "network" in mapping:
        mode, hosts = _network(mapping["network"], "/network", partial=True)
        restricts_hosts = hosts is not None and mode in {None, NetworkMode.ALLOWLIST}
        network = NetworkLayer(mode, frozenset(hosts or ()) if restricts_hosts else None)
    allow_effects, need_approval = (
        _effects(mapping["effects"], "/effects", partial=True) if "effects" in mapping else (None, None)
    )
    return PermissionLayer(
        source=source,
        fs_read=None if "read" not in fs else _path_policy(fs["read"], "/fs/read", partial=True),
        fs_write=None if "write" not in fs else _path_policy(fs["write"], "/fs/write", partial=True),
        commands=None if "commands" not in mapping else _commands_layer(mapping["commands"], "/commands"),
        network=network,
        tools=None if "tools" not in mapping else _tools(mapping["tools"], "/tools", partial=True),
        operations=None
        if "operations" not in mapping
        else _operations(mapping["operations"], "/operations", partial=True),
        external_effects=allow_effects,
        effects_need_approval=need_approval,
        allowed_isolation=None
        if "allowed_isolation" not in mapping
        else _isolation(mapping["allowed_isolation"], "/allowed_isolation", allow_empty=True),
    )


def permission_set_from_document(doc: Mapping[str, object]) -> PermissionSet:
    """A ``PermissionSetView`` document (``urn:skm:policy:view:permission-set:v2``; every ``v1`` document is
    one) → permission set. ``allowlist`` without a host stays a policy that admits no host, never ``none``."""
    mapping = _object(doc, "", _VIEW_KEYS)
    _require(mapping, "", *sorted(_VIEW_KEYS - {"digest"}))
    mode, hosts = _network(mapping["network"], "/network", partial=False, composed=True)
    tools_doc = mapping["tools"]
    if not isinstance(tools_doc, list):
        _fail("/tools", "expected an array of tool lists")
    return PermissionSet(
        fs_read=tuple(
            cast("PathPolicy", _path_policy(item, f"/fs_read/{index}", partial=False))
            for index, item in enumerate(_array(mapping["fs_read"], "/fs_read"))
        ),
        fs_write=tuple(
            cast("PathPolicy", _path_policy(item, f"/fs_write/{index}", partial=False))
            for index, item in enumerate(_array(mapping["fs_write"], "/fs_write"))
        ),
        commands=_command_policy(mapping["commands"], "/commands"),
        network=NetworkPolicy(
            cast("NetworkMode", mode), (frozenset(hosts or ()),) if mode is NetworkMode.ALLOWLIST else ()
        ),
        tools=tuple(
            frozenset(_strings(item, f"/tools/{index}", _TOOL_RE))
            for index, item in enumerate(cast("list[object]", tools_doc))
        ),
        operations=_operations(mapping["operations"], "/operations", partial=False),
        external_effects=_enums(EffectKind, mapping["external_effects"], "/external_effects"),
        effects_need_approval=_enums(EffectKind, mapping["effects_need_approval"], "/effects_need_approval"),
        allowed_isolation=_isolation(mapping["allowed_isolation"], "/allowed_isolation", allow_empty=True),
        sources=_strings(mapping["sources"], "/sources"),
    )


def _array(value: object, pointer: str) -> list[object]:
    if not isinstance(value, list):
        _fail(pointer, "expected an array")
    return cast("list[object]", value)
