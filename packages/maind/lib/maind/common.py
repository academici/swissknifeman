"""maind environment (Env) and the node JSON database helper.

Shared primitives (die/warn/atomic JSON/HTTP/blocks, ...) live in ``aicore``; modules
import them from there directly."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aicore.util.env import BaseEnv
from aicore.util.io import load_json_db as _core_load_json_db
from aicore.util.repo import find_monorepo_root

DB_VERSION = 1


@dataclass(frozen=True)
class Env(BaseEnv):
    """Launch context maind: core (root/cmd/home) — from BaseEnv; here only
    path-property node (~/.maind, root/data, config)."""

    # ── user state (~/.maind) ──────────────────────────────────
    @property
    def state_dir(self):
        return self.home / ".maind"

    @property
    def projects_db(self):
        return self.state_dir / "projects.json"

    @property
    def agents_db(self):
        return self.state_dir / "agents.json"

    # ── runtime-node data (root/data, gitignored) ────────────────────────
    @property
    def data_dir(self):
        return self.root / "data"

    @property
    def graph_db(self):
        return self.data_dir / "graph.db"

    @property
    def memory_pidfile(self):
        return self.data_dir / "agentmemory.pid"

    @property
    def memory_log(self):
        return self.data_dir / "agentmemory.log"

    # ── node configuration ──────────────────────────────────────────────────
    @property
    def memory_config(self):
        """Config agent-memory demon. Env `MAIND_III_CONFIG` overrides path
        (according to the example `MAIND_SKM_BIN`/`MAIND_BRAIN_BIN` in orchestrate); otherwise -
        `config/memory/iii-config.yaml` in the package."""
        override = os.environ.get("MAIND_III_CONFIG")
        if override:
            return Path(os.path.expanduser(override))
        return self.root / "config" / "memory" / "iii-config.yaml"

    @property
    def monorepo_root(self):
        """Monorepo root - directory with `packages/`/`core/` above package. Node config
        (`config.json`) is generic and can be found here. Fallback: himself root (standalone)."""
        return find_monorepo_root(self.root) or self.root

    @property
    def default_config(self):
        """Node config. Canonically - `config.json` at the root of the monorepo. Reverse
        compatibility: if it is not there, but the old one is there `.maind.json` (in the root or
        package) — take it (migration without breaking existing installations)."""
        root_cfg = self.monorepo_root / "config.json"
        if root_cfg.exists():
            return root_cfg
        for legacy in (self.monorepo_root / ".maind.json", self.root / ".maind.json"):
            if legacy.exists():
                return legacy
        return root_cfg  # default path for entry/hints - new

    @property
    def linked_worktree_config(self):
        """Read-only config fallback from this repository's primary worktree.

        An isolated linked worktree intentionally has no copied machine-local
        ``config.json``.  It may read the primary worktree's carrier only when
        both worktrees resolve to the same Git common directory.  Writers keep
        using ``default_config`` and therefore never mutate the primary carrier.
        """
        if self.default_config.exists():
            return None
        try:
            result = subprocess.run(
                ["git", "-C", str(self.monorepo_root), "rev-parse", "--git-common-dir"],
                check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        common_dir = Path(result.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = self.monorepo_root / common_dir
        common_dir = common_dir.resolve()
        if common_dir.name != ".git":
            return None
        primary_root = common_dir.parent
        candidate = primary_root / "config.json"
        if not candidate.is_file() or candidate == self.default_config:
            return None
        try:
            primary_common = subprocess.run(
                ["git", "-C", str(primary_root), "rev-parse", "--git-common-dir"],
                check=True, capture_output=True, text=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
        primary_common = Path(primary_common)
        if not primary_common.is_absolute():
            primary_common = primary_root / primary_common
        return candidate if primary_common.resolve() == common_dir else None

    @property
    def config_read_path(self):
        """Read carrier, keeping ``default_config`` as the isolated write target."""
        return (self.default_config if self.default_config.is_file()
                else self.linked_worktree_config or self.default_config)

    @property
    def example_config(self):
        """Config template - `config.example.json` at the root of the monorepo (with legacy-fallback)."""
        root_ex = self.monorepo_root / "config.example.json"
        if root_ex.exists():
            return root_ex
        legacy = self.monorepo_root / ".maind.example.json"
        return legacy if legacy.exists() else root_ex

    @property
    def env_file(self):
        return self.root / ".env"


# ── JSON-storage (persistent read with recovery - aicore) ───────────
def load_json_db(path, default):
    """JSON-Node database with recovery - aicore.util.io.load_json_db (broken → backup
    .corrupt.<date> + warn + deepcopy(default); version > DB_VERSION → die)."""
    return _core_load_json_db(path, default, max_version=DB_VERSION)
