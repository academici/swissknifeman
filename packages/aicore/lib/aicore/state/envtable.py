"""The SKM environment variables: the one table of their names (stdlib only, no imports from aicore).

Installing SKM on a machine exports three variables through a managed snippet of the shell profile
(:mod:`aicore.state.shellenv`); the agent's Bash, the project launcher and the skills read them:

``SKM_HOME``        the machine home (``config/``, ``state/``, ``cache/``, ``workspaces/`` and the module data)
``SKM_WORKSPACES``  the folder that holds the workspaces (one git repository each)
``SKM_WORKSPACE``   the code of the active workspace

The names are fixed here and nowhere else: the installers, the doctors and the hook libraries of the harness take them
from this table (the hooks are stdlib copies pinned to it by a test). ``SKM_WORKSPACES_ROOT`` is the older name of the
workspaces folder; it stays the stronger override, ``SKM_WORKSPACES`` is read when it is not set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

ENV_HOME = "SKM_HOME"
ENV_WORKSPACES = "SKM_WORKSPACES"
ENV_WORKSPACE = "SKM_WORKSPACE"
# The older name of the workspaces folder: read first, never exported.
ENV_WORKSPACES_ROOT = "SKM_WORKSPACES_ROOT"


@dataclass(frozen=True)
class EnvVariable:
    """One exported variable: its ``name``, what it holds and the older names that take precedence when set."""

    name: str
    meaning: str
    older: Tuple[str, ...] = ()
    kind: str = "path"  # "path" (an absolute path) or "code" (a workspace code)


TABLE: Tuple[EnvVariable, ...] = (
    EnvVariable(ENV_HOME, "the machine home"),
    EnvVariable(ENV_WORKSPACES, "the folder of the workspaces", (ENV_WORKSPACES_ROOT,)),
    EnvVariable(ENV_WORKSPACE, "the code of the active workspace", kind="code"),
)

NAMES: Tuple[str, ...] = tuple(item.name for item in TABLE)
