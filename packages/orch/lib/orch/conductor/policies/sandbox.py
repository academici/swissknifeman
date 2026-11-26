"""The sandbox of the provider roles: when a Codex or Claude Code route is confined, and what a route that cannot be
confined may still do (``instructions.sandbox``). The probes (the sandbox, the flags the provider CLI lists) are the
caller's: ``application/route_service.py`` and ``infrastructure/cli_probe.py``."""
from __future__ import annotations

import json
import os
from typing import Optional

from orch.conductor import options as opts
from orch.conductor.domain.item import Item
from orch.settings import ORCH_ROOT


def claude_confinement_required(item_options: dict, route: dict, *, access: str = "open") -> bool:
    """``instructions.sandbox`` is ``require`` and ``route`` is a Claude Code role with Bash: only then does
    :func:`claude_sandbox_problem` need the sandbox probe and the flags of the CLI."""
    return mode_of(item_options) == "require" and claude_bash(route) and access == "confined" \
        and filesystem(route.get("role") or "executor") == "write"


def claude_sandbox_problem(item_options: dict, route: dict, *, probe: Optional[dict],
                           settings_listed: Optional[bool], access: str = "open") -> Optional[str]:
    """``SANDBOX_UNAVAILABLE: ...`` when ``instructions.sandbox`` is ``require`` and a Claude Code role with Bash on
    ``route`` could not be confined (the sandbox cannot start, or the CLI does not list ``--settings``): the rule of
    the preflight, applied to a route that was not in it. ``probe`` is the result of the sandbox probe and
    ``settings_listed`` whether the CLI lists ``--settings`` (asked only when the sandbox starts); the caller probes
    when :func:`claude_confinement_required`."""
    if not claude_confinement_required(item_options, route, access=access):
        return None
    if not probe["available"]:
        return f"SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the sandbox cannot start ({probe['reason']})"
    if not settings_listed:
        return "SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the claude CLI does not list --settings"
    return None


def codex_sandboxed(route: dict) -> bool:
    argv = route["argv"]
    mode = argv[argv.index("--sandbox") + 1] if "--sandbox" in argv[:-1] else None
    return route.get("provider") == "codex" and mode in ("read-only", "workspace-write")


def sandbox_mode(item: Item) -> str:
    return mode_of(item.options)


def mode_of(item_options: dict) -> str:
    """``instructions.sandbox`` of the run options: ``off``, ``prefer`` (default) or ``require``."""
    return item_options["instructions"].get("sandbox", "prefer")


def claude_bash(route: dict) -> bool:
    """A Claude Code role that can run shell commands, the only commands the Claude sandbox confines."""
    argv = route["argv"]
    return route.get("provider") == "claude-code" and "--tools" in argv[:-1] \
        and "Bash" in argv[argv.index("--tools") + 1].split(",")


def declared_network(role: str) -> str:
    """``tools.network`` of the role manifest: what the role is meant to reach (``none`` when it has no manifest)."""
    try:
        manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "none"
    return (manifest.get("tools") or {}).get("network", "none")


def filesystem(role: str) -> str:
    """The filesystem authority of a role; an unknown role may write."""
    try:
        manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "write"
    return (manifest.get("tools") or {}).get("filesystem", "write")


def sandbox_args(item_options: dict, role: str, route: dict, *, extra_paths: list, network: str,
                 access: str = "open") -> list:
    """``--settings`` with only the ``sandbox`` block for a Claude Code role with Bash on a machine where the sandbox
    starts and whose CLI lists ``--settings`` (the caller probed both; the provider merges the block with the user's
    settings), with a write grant for ``extra_paths`` (``scope.extra_paths``) when the role writes and a domain
    allowlist unless the role's ``network`` is ``allowed``."""
    if mode_of(item_options) == "off" or not claude_bash(route) or filesystem(role) == "read" or access == "open":
        return []
    block = {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True}
    if role in opts.WRITING_ROLES:
        # the shell of a writer may change the directories ``scope.extra_paths`` grants, as its file tools do (``--add-dir``);
        # ``sandbox.filesystem.allowWrite`` takes absolute or ``~`` paths and merges with the settings of the user
        granted = [os.path.expanduser(path) for path in extra_paths]
        if granted:
            block["filesystem"] = {"allowWrite": granted}
    if network != "allowed":
        block["network"] = {"strictAllowlist": True,
                            "allowedDomains": list(item_options["instructions"].get("sandbox_domains") or [])}
    return ["--settings", json.dumps({"sandbox": block}, sort_keys=True)]
