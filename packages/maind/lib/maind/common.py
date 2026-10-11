"""General utilities maind: environment (Env), atomic JSON, JSON-DB, backup.

Verbatim common with swissknifeman/brain code (die/warn/now_iso/confirm/sanitize +
core Env, parse_args, run_cmd, atomic/safe JSON) moved to general core; HTTP-client
moved to `maind.http`, managed markdown-block - in `maind.blocks` (re-export below
for backward compatibility of imports `from .common import ...`)."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# General core (connects via PYTHONPATH launcher/test.sh). Re-export for
# package modules, which historically take these names from .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, backup_file, confirm,
    detect_project_type, die, docs_visibility_for, find_monorepo_root,
    now_iso, parse_args, parse_iso, pid_alive, read_ndjson,
    read_ndjson_iter, run_cmd, safe_load_json, sanitize, warn,
)
from core import load_json_db as _core_load_json_db
# Dedicated modules - re-export for the sake of `from .common import ...` (back-compat).
from .blocks import content_hash, managed_block, upsert_block  # noqa: F401
from .http import http_get_json, http_post_json, ping  # noqa: F401

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


# die/warn/now_iso/confirm/sanitize — from general core (re-export above).


# parse_args — from general core (re-export above); used to be duplicated here
# (superset parse_flags with positional, style brain).


# backup_file — from general core (re-export above); was previously duplicated here.
# managed_block/upsert_block/content_hash — in maind.blocks (re-export above).
# http_get_json/http_post_json/ping — in maind.http (re-export above).


# ── JSON-storage (atomic write + persistent read - general core) ───────────
def load_json_db(path, default):
    """JSON-Node database with recovery - general core.load_json_db (broken → backup
    .corrupt.<date> + warn + deepcopy(default); version > DB_VERSION → die)."""
    return _core_load_json_db(path, default, max_version=DB_VERSION)
