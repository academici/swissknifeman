"""General utilities analyst: environment (Env) + re-export general core.

Primitives (die/warn/now_iso/confirm/sanitize, parse_args, run_cmd, atomic/safe JSON,
search for monorepo root) — from the general package `core` (is connected by the launcher via
PYTHONPATH). We re-export for `from .common import ...` in package modules."""
import os
from dataclasses import dataclass

from aicore.state import resolve_with_legacy
from aicore.state import state_dir as aicore_state_dir
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, confirm,
    die, find_monorepo_root, now_iso, parse_args, parse_iso,
    read_ndjson, run_cmd, safe_load_json, sanitize, state_dir, warn,
)


@dataclass(frozen=True)
class Env(BaseEnv):
    """Launch context analyst: core (root/cmd/home) — from BaseEnv; here only
    path-property. Cross-project layer (P2+) lives in the machine state directory (see state_dir); per-project
    lessons - in <project>/.claude/analyst (see lessons.project_dir)."""

    @property
    def state_dir(self):
        """Single cross-project layer (clusters/suggestions): the analyst folder under the machine state
        directory (``aicore.state``; under ``SKM_HOME`` when set). An existing legacy
        ``~/.swissknifeman/analyst`` is used, with one warning, until it is moved."""
        return resolve_with_legacy(aicore_state_dir("analyst", home=self.home),
                                   [state_dir(self.home, "analyst")], home=self.home)

    @property
    def monorepo_root(self):
        """Root monorepo (directory with packages//core/). Fallback: himself root (standalone)."""
        return find_monorepo_root(self.root) or self.root

    @property
    def default_config(self):
        """Ecosystem node config (config.json at the root of the monorepo) — project registry for
        cross-project scan (P2). B P1 is optional; default reading path."""
        return self.monorepo_root / "config.json"


def project_path_from_opts(env, opts):
    """Project path from --cwd (current directory) or default (cwd). --project (by registry
    config.json) — P2; in P1 working with one project from cwd."""
    _ = env, opts
    return os.getcwd()
