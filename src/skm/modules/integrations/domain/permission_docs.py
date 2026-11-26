"""Pure domain permission document serializers for ``ProjectionInputs`` (integrations §4.11, §5.1)."""

from __future__ import annotations

from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.bundle import normalize_desired_map
from skm.modules.integrations.domain.desired_inputs import tool_admits

__all__ = ["build_permission_request_doc", "serialize_permission_set"]


def _rule_doc(rule: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"scope": rule.scope.value, "pattern": rule.pattern}
    if rule.mount is not None:
        out["mount"] = rule.mount
    return out


def serialize_permission_set(perms: Any, *, digest: str) -> JsonObject:
    """Serialize a ``PermissionSet``-shaped object into a canonical JSON mapping."""
    cmds = perms.commands
    allow_rules = (
        tuple(
            {
                "program": r.program,
                "subcommands": None if r.subcommands is None else tuple(sorted(r.subcommands)),
            }
            for r in sorted(cmds.allow, key=lambda item: item.program)
        )
        if cmds.mode.value == "allowlist"
        else ()
    )
    ops_doc = {
        k.value: {
            "deny": v.deny,
            "requires": tuple(sorted(i.value for i in v.requires)),
            "capabilities": tuple(sorted(i.value for i in v.capabilities)),
            "warn": v.warn,
            "risk": None if v.risk is None else v.risk.value,
        }
        for k, v in sorted(perms.operations.items(), key=lambda kv: kv[0].value)
    }
    return normalize_desired_map(
        {
            "digest": digest,
            "fs_read": tuple(
                {"allow": tuple(_rule_doc(r) for r in p.allow), "deny": tuple(_rule_doc(r) for r in p.deny)}
                for p in perms.fs_read
            ),
            "fs_write": tuple(
                {"allow": tuple(_rule_doc(r) for r in p.allow), "deny": tuple(_rule_doc(r) for r in p.deny)}
                for p in perms.fs_write
            ),
            "commands": {
                "mode": cmds.mode.value,
                "allow": allow_rules,
                "deny_patterns": tuple(cmds.deny_patterns),
                "ask_patterns": tuple(cmds.ask_patterns),
                "inline_interpreters": tuple(sorted(cmds.inline_interpreters)),
                "trust_inline_interpreters": cmds.trust_inline_interpreters,
            },
            "network": {
                "mode": perms.network.mode.value,
                "hosts": tuple(tuple(sorted(g)) for g in perms.network.hosts),
            },
            "tools": tuple(tuple(sorted(g)) for g in perms.tools),
            "operations": ops_doc,
            "external_effects": tuple(sorted(i.value for i in perms.external_effects)),
            "effects_need_approval": tuple(sorted(i.value for i in perms.effects_need_approval)),
            "allowed_isolation": tuple(sorted(perms.allowed_isolation)),
        }
    )


def _req_paths(field: str, merged: Any) -> JsonObject:
    if merged is None:
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, f"unprovable path policy ({field})")
    return {"allow": [_rule_doc(i) for i in merged.allow], "deny": [_rule_doc(i) for i in merged.deny]}


def _req_commands(cmds: Any) -> JsonObject:
    progs = sorted(r.program for r in cmds.allow if r.subcommands is None)
    subs: JsonObject = {
        r.program: cast("JsonValue", sorted(r.subcommands)) for r in cmds.allow if r.subcommands is not None
    }
    return {
        "mode": cmds.mode.value,
        "programs": cast("list[JsonValue]", progs),
        "subcommands": subs,
        "deny_patterns": list[JsonValue](cmds.deny_patterns),
        "ask_patterns": list[JsonValue](cmds.ask_patterns),
        "inline_interpreters": list[JsonValue](sorted(cmds.inline_interpreters)),
        "trust_inline_interpreters": cmds.trust_inline_interpreters,
    }


def _req_network(net: Any) -> JsonObject:
    if net.mode.value != "allowlist":
        return {"mode": net.mode.value}
    names = sorted({n for g in net.hosts for n in g})
    hosts = names if len(net.hosts) == 1 else [n for n in names if net.allows(n, None)]
    return {"mode": "allowlist", "hosts": list[JsonValue](hosts)}


def _req_op(name: str, rule: Any) -> JsonObject:
    if rule.deny:
        return {"decision": "deny"}
    req_vals = {r.value for r in rule.requires}
    if "intent" in req_vals:
        return {"decision": "intent"}
    conds = [
        c
        for c, ok in (
            ("task_authority", "task_authority" in req_vals),
            ("capability", bool(rule.capabilities)),
            ("ask", "ask" in req_vals),
        )
        if ok
    ]
    if len(conds) > 1 or len(rule.capabilities) > 1:
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, f"operation {name} has no single proof")
    if conds == ["capability"]:
        return {"decision": "capability", "capability": next(iter(rule.capabilities)).value}
    fallback = "warn" if rule.warn else "allow"
    return {"decision": conds[0] if conds else fallback}


def build_permission_request_doc(
    perms: Any,
    *,
    merged_fs_read: Any,
    merged_fs_write: Any,
) -> dict[str, JsonValue]:
    """Build a ``policy.public.is_subset`` request document from a ``PermissionSet``."""
    if not perms.tools:
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "unbounded tool set cannot be proven")
    tnames = sorted(
        {
            n
            for g in perms.tools
            for n in g
            if all(any(tool_admits(p, n) for p in other) for other in perms.tools)
        }
    )
    return {
        "fs": {
            "read": _req_paths("fs_read", merged_fs_read),
            "write": _req_paths("fs_write", merged_fs_write),
        },
        "commands": _req_commands(perms.commands),
        "network": _req_network(perms.network),
        "tools": {"allow": list[JsonValue](tnames)},
        "operations": {k.value: _req_op(k.value, v) for k, v in sorted(perms.operations.items())},
        "effects": {
            "allow": list[JsonValue](sorted(i.value for i in perms.external_effects)),
            "need_approval": list[JsonValue](sorted(i.value for i in perms.effects_need_approval)),
        },
        "allowed_isolation": list[JsonValue](sorted(perms.allowed_isolation)),
    }
