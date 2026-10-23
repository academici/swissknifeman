"""The launch plan of a role process: its command line and environment from the route, the options of the piece and
the decisions of the sandbox and the isolation (the project instructions kept out, the Landlock guard, the paths
granted beside the project, the transcripts of a resumable session)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from orch.conductor import options as opts
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure import sessions
from orch.settings import ORCH_ROOT

# The environment that keeps a provider's project instructions (the repository CLAUDE.md, the project memory) out of
# a role process. Claude Code reads both by itself; grok was probed and does not read the repository CLAUDE.md; codex
# would need its own CODEX_HOME (not used by a run so far).
ISOLATION_ENV = {"claude-code": {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}}

# Arguments that start a role with no customizations at all: no CLAUDE.md, project memory, plugins, MCP servers, user
# skills or hooks (a measured start-up context of 6 K instead of 16 K tokens, and none of the developer-session rules).
ISOLATION_ARGS = {"claude-code": ["--safe-mode"]}

TRANSCRIPT_NAME_MAX = 200  # Claude Code shortens a longer folder name and appends a hash it does not publish


def writes(role: str) -> bool:
    """Whether the role may change files (``tools.filesystem`` of its manifest); a role without a manifest might."""
    try:
        manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return (manifest.get("tools") or {}).get("filesystem") == "write"


def role_argv(self, item: Item, role: str, route: dict) -> list:
    isolated = role in item.options["instructions"]["isolate_roles"]
    extra = ISOLATION_ARGS.get(route.get("provider", "")) if isolated else None
    if extra and not self.role_ports.knows(route["argv"], extra):
        extra = None
    resume = sessions.resume_args(self, item, role, route)
    argv = [arg.replace("{session}", resume[0]) for arg in route["resume_argv"]] \
        if resume and route.get("resume_argv") else list(route["argv"])  # a catalog entry that names its own resume command
    if sessions.shared_session(self, item, role, route):  # a session that is not saved cannot be resumed by the next executor
        argv = [arg for arg in argv if arg != "--no-session-persistence"]
    sandboxed = self.role_ports.sandbox_args(item, role, route)
    if sandboxed:  # the provider sandbox (bubblewrap) cannot start under the Landlock guard: it replaces the guard
        argv = strip_guard(argv)
    argv = self._extra_write_dirs(item, role, argv)
    granted = granted_paths(self, item, role)
    if granted and route.get("provider") == "codex":  # a confined Codex writes beside the project only where it is told
        argv = codex_add_dirs(argv, granted)
    # a Claude Code role reaches a directory outside the project with its file tools only when it is added; the shell
    # of a sandboxed one is granted the same paths in the sandbox block (``sandbox_args``)
    added = [part for path in granted for part in ("--add-dir", path)] if route.get("provider") == "claude-code" else []
    return argv + (extra or []) + ([] if route.get("resume_argv") else resume) + added + sandboxed


def granted_paths(self, item: Item, role: str) -> list:
    """``scope.extra_paths`` (``~`` expanded) for a role that writes, none for the others."""
    if role not in opts.WRITING_ROLES:
        return []
    return [os.path.expanduser(path) for path in self._scope_option(item, "extra_paths", [])]


def codex_add_dirs(argv: list, paths: list) -> list:
    """``argv`` of a Codex route with ``--add-dir P`` for every path, right after the ``exec`` token."""
    if "exec" not in argv:
        return argv
    at = argv.index("exec") + 1
    return argv[:at] + [part for path in paths for part in ("--add-dir", path)] + argv[at:]


def strip_guard(argv: list) -> list:
    """``argv`` without the ``ro-run.py [--rw DIR]... --`` prefix of the Landlock filesystem guard. Landlock also
    forbids ``mount`` and writes to ``/proc/<pid>/uid_map``, so the bubblewrap sandbox of Claude Code cannot start
    inside it ("bwrap: setting up uid map: Permission denied"); the sandbox confines the shell commands itself."""
    if "--" not in argv or not any(a.endswith("ro-run.py") for a in argv[:2]):
        return argv
    return argv[argv.index("--") + 1:]


def extra_write_dirs(self, item: Item, role: str, argv: list) -> list:
    """``scope.extra_paths`` for a writer (executor, bounded-implementer) started through ``ro-run.py``: one more ``--rw``
    each, before the ``--``. A route that lost the guard to the provider sandbox gets its grants from ``role_argv`` and
    ``sandbox_args``."""
    paths = list(self._scope_option(item, "extra_paths", []))
    if role not in opts.WRITING_ROLES or "--" not in argv or not any(a.endswith("ro-run.py") for a in argv[:2]):
        return argv
    if role == "executor" and self._shared_session(item, role, {"provider": "claude-code"}) \
            and "claude" in argv[argv.index("--") + 1:][:1]:
        paths.append(self._claude_transcripts())  # else the guard stops the CLI from saving the session it must resume
    if not paths:
        return argv
    at = argv.index("--")
    return argv[:at] + [part for path in paths for part in ("--rw", os.path.expanduser(path))] + argv[at:]


def transcript_folder_name(project) -> str:
    """The folder name Claude Code gives a project: every UTF-16 code unit outside [A-Za-z0-9] becomes ``-`` (a character
    outside the basic plane is two units, so two dashes)."""
    return "".join(char if char.isascii() and char.isalnum() else "-" * (2 if ord(char) > 0xFFFF else 1) for char in str(project))


def claude_transcripts(self) -> str:
    """The folder where Claude Code keeps the transcripts of this project: ``~/.claude/projects/<path with every
    character outside [A-Za-z0-9] as -``. It is the one place besides the project that a resumable session needs. A
    path whose folder name would pass ``TRANSCRIPT_NAME_MAX`` gets a name with a hash suffix that is not known here: the
    whole ``~/.claude/projects`` is then writable for the executor (the transcripts of the other projects too)."""
    root = Path.home() / ".claude" / "projects"
    name = transcript_folder_name(self.project)
    folder = root if len(name) > TRANSCRIPT_NAME_MAX else root / name
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def scope_option(item: Item, key: str, default):
    return (item.options.get("scope") or {}).get(key, default)


def role_env(self, item: Item, role: str, route: dict) -> Optional[dict]:
    """The environment of a role process. A role named in ``instructions.isolate_roles`` starts without the project
    instructions: they carry the rules of a developer's own session ("quality over speed", "fix every defect even
    beyond the scope"), which contradict the role's own scope rules; every role gets exactly the instructions of its
    own prompt."""
    extra = ISOLATION_ENV.get(route.get("provider", "")) if role in item.options["instructions"]["isolate_roles"] else None
    if not extra:
        return self.env
    base = dict(os.environ if self.env is None else self.env)
    base.update(extra)
    return base
