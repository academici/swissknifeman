"""maind environment (Env) and the node JSON database helper.

Shared primitives (die/warn/atomic JSON/HTTP/blocks, ...) live in ``aicore``; modules
import them from there directly."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aicore.state import backup as _backup
from aicore.state import data_dir as _data_dir
from aicore.state import find_project_root
from aicore.state import resolve_with_legacy
from aicore.state import state_dir as _state_dir
from aicore.util.env import BaseEnv
from aicore.util.io import load_json_db as _core_load_json_db
from aicore.util.repo import find_monorepo_root

DB_VERSION = 1


@dataclass(frozen=True)
class Env(BaseEnv):
    """Launch context maind: core (root/cmd/home) — from BaseEnv; here only
    path-property node (state and data in the aicore.state places, the legacy node file)."""

    # ── machine state (aicore.state; legacy ~/.maind) ──────────────────────
    @property
    def state_dir(self):
        """``<state>/maind`` (registry.json, agents.json, memory-backups/). An existing
        legacy ``~/.maind`` is used, with one warning, until the new place exists."""
        return resolve_with_legacy(_state_dir("maind", home=self.home),
                                   [self.home / ".maind"], home=self.home)

    @property
    def registry_file(self):
        """Fleet registry written by maind (``projects.write_registry``)."""
        return self.state_dir / "registry.json"

    @property
    def agents_db(self):
        return self.state_dir / "agents.json"

    # ── runtime-node data (aicore.state; legacy <module>/data) ───────────────
    @property
    def data_dir(self):
        """``<data>/maind`` (graph.db, graphs/, agentmemory.pid and .log). An existing
        legacy ``<module>/data`` is used, with one warning, until the new place exists."""
        return resolve_with_legacy(_data_dir("maind", home=self.home),
                                   [self.root / "data"], home=self.home)

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
        """Monorepo root - directory with `packages/`/`core/` above package. Only the lookup of
        the legacy node file uses it. Fallback: himself root (standalone)."""
        return find_monorepo_root(self.root) or self.root

    @property
    def legacy_node_config(self):
        """Legacy node file; removed by ``swissknifeman upgrade``. `config.json` at the root of the
        monorepo; the older `.maind.json` (in the root or the package) is taken when it is missing.
        It still serves as the settings and registry source until a ``[maind]`` table or a
        registry.json exists. Returns the path where it would be (it may not exist)."""
        root_cfg = self.monorepo_root / "config.json"
        if root_cfg.exists():
            return root_cfg
        for legacy in (self.monorepo_root / ".maind.json", self.root / ".maind.json"):
            if legacy.exists():
                return legacy
        return root_cfg

    @property
    def linked_worktree_config(self):
        """Read-only config fallback from this repository's primary worktree.

        An isolated linked worktree intentionally has no copied machine-local
        ``config.json``.  It may read the primary worktree's carrier only when
        both worktrees resolve to the same Git common directory.  Writers keep
        using ``legacy_node_config`` and therefore never mutate the primary carrier.
        """
        if self.legacy_node_config.exists():
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
        if not candidate.is_file() or candidate == self.legacy_node_config:
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
        """Read carrier of the legacy node file, keeping ``legacy_node_config`` as the isolated
        write target."""
        return (self.legacy_node_config if self.legacy_node_config.is_file()
                else self.linked_worktree_config or self.legacy_node_config)

    @property
    def example_config(self):
        """Registry template shipped with the module (``configs/registry.example.json``)."""
        return self.root / "configs" / "registry.example.json"

    @property
    def env_file(self):
        return self.root / ".env"


def save_backup(path, *, project=None):
    """Copy ``path`` into the aicore.state backup tree (``<project>/.swissknifeman/backups/<stamp>/``,
    rotated) before the file is replaced. ``project`` defaults to the project root of the file."""
    path = Path(path)
    root = project if project is not None else find_project_root(path.parent)
    return _backup(path, project=root)


# ── JSON-storage (persistent read with recovery - aicore) ───────────
def load_json_db(path, default):
    """JSON-Node database with recovery - aicore.util.io.load_json_db (broken → backup
    .corrupt.<date> + warn + deepcopy(default); version > DB_VERSION → die)."""
    return _core_load_json_db(path, default, max_version=DB_VERSION)
