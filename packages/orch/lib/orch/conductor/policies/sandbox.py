"""The sandbox of the provider roles: when a Codex or Claude Code route is confined, what a route that cannot be
confined may still do (``instructions.sandbox``), and which flags the provider CLI lists."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

from orch import sandbox
from orch.conductor.domain.item import Item
from orch.settings import ORCH_ROOT

_KNOWN: dict = {}  # (command, flags) -> whether the provider CLI lists the flags in its --help


def claude_sandbox_problem(self, item: Item, route: dict) -> Optional[str]:
    """``SANDBOX_UNAVAILABLE: ...`` when ``instructions.sandbox`` is ``require`` and a Claude Code role with Bash on
    ``route`` could not be confined (the sandbox cannot start, or the CLI does not list ``--settings``): the rule of
    the preflight, applied to a route that was not in it."""
    if self._sandbox_mode(item) != "require" or not self._claude_bash(route):
        return None
    probed = sandbox.probe()
    if not probed["available"]:
        return f"SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the sandbox cannot start ({probed['reason']})"
    if not self._knows(route["argv"], ["--settings"]):
        return "SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the claude CLI does not list --settings"
    return None


def codex_sandboxed(route: dict) -> bool:
    argv = route["argv"]
    mode = argv[argv.index("--sandbox") + 1] if "--sandbox" in argv[:-1] else None
    return route.get("provider") == "codex" and mode in ("read-only", "workspace-write")


def sandbox_mode(item: Item) -> str:
    return item.options["instructions"].get("sandbox", "prefer")


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


def sandbox_args(self, item: Item, role: str, route: dict) -> list:
    """``--settings`` with only the ``sandbox`` block for a Claude Code role with Bash (the provider merges it with
    the user's settings). A sandbox that cannot start never leaves the commands unconfined silently: ``prefer``
    says so once and goes on under the filesystem guard, ``require`` was stopped in the preflight."""
    mode = self._sandbox_mode(item)
    if mode == "off" or not self._claude_bash(route):
        return []
    probed = sandbox.probe()
    if not probed["available"]:
        if mode == "prefer" and not self._sandbox_noted and self.progress is not None:
            self._sandbox_noted = True
            self.progress.emit("info", reason_code="ISOLATION_PARTIAL",
                               message=f"sandbox unavailable: {probed['reason']}; the commands of claude-code roles "
                                       "run under the filesystem guard only")
        return []
    if not self._knows(route["argv"], ["--settings"]):
        return []
    block = {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True}
    if self.declared_network(role) != "allowed":
        block["network"] = {"strictAllowlist": True,
                            "allowedDomains": list(item.options["instructions"].get("sandbox_domains") or [])}
    return ["--settings", json.dumps({"sandbox": block}, sort_keys=True)]


def knows(self, argv: list, flags: list) -> bool:
    """Whether the provider CLI of ``argv`` lists ``flags`` in its ``--help`` (an older CLI without ``--safe-mode``
    still runs, isolated by the environment only, and the run says so once)."""
    command = next((arg for arg in argv if os.path.basename(arg) in ("claude", "codex", "grok")), None)
    if command is None:  # a test stand-in or a wrapper the conductor does not know: pass the flags as asked
        return True
    key = (command, tuple(flags))
    if key not in _KNOWN:
        try:
            text = subprocess.run([command, "--help"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            text = ""
        _KNOWN[key] = all(flag in text for flag in flags)
        if not _KNOWN[key] and self.progress is not None:
            self.progress.emit("info", reason_code="ISOLATION_PARTIAL",
                               message=f"{command} does not list {' '.join(flags)}; roles are isolated by the environment only")
    return _KNOWN[key]
