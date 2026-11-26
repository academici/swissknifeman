"""Translate an admitted policy view to the roots actually bound on this worker."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from skm.modules.policy.domain.permission_set import tool_allowed
from skm.modules.policy.public import permission_set_from_view, representable_paths
from skm.modules.runtimes.domain.request import (
    CommandRules,
    NetworkRules,
    PathRule,
    PathRules,
    PermissionGrant,
)

__all__ = ["runtime_permissions"]


def runtime_permissions(document: Any, mounts: Mapping[str, Path]) -> PermissionGrant:
    permissions = permission_set_from_view(document)

    def paths(kind: str) -> PathRules:
        conjunction = permissions.fs_read if kind == "read" else permissions.fs_write
        policy = representable_paths(conjunction)
        if policy is None:
            raise ValueError("runtime cannot represent path conjunction without widening")

        def rules(side: str) -> tuple[PathRule, ...]:
            result: list[PathRule] = []
            for item in getattr(policy, side):
                scope = item.scope.value
                if scope == "worktree":
                    roots = mounts.values() if item.mount is None else (mounts[item.mount],)
                elif scope in {"materials", "safe_dir", "tmp", "home"}:
                    # Runtime S-55 grants are worktree-rooted. Unbound scopes add no
                    # roots; inline context never grants a guessed host directory.
                    continue
                else:
                    raise ValueError("runtime request cannot bind an unrestricted filesystem scope")
                result.extend(PathRule(str(root), item.pattern) for root in roots)
            return tuple(result)

        return PathRules(rules("allow"), rules("deny"))

    command = permissions.commands
    if any(rule.subcommands is not None for rule in command.allow):
        raise ValueError("runtime cannot represent command subcommands without widening")
    network = document["network"]
    return PermissionGrant(
        paths("read"),
        paths("write"),
        CommandRules(
            command.mode.value,
            tuple(rule.program for rule in command.allow),
            command.deny_patterns,
            command.ask_patterns,
        ),
        NetworkRules(network["mode"], tuple(network.get("hosts", ()))),
        frozenset(
            tool for group in permissions.tools for tool in group if tool_allowed(permissions.tools, tool)
        ),
        frozenset(effect.value for effect in permissions.external_effects),
    )
