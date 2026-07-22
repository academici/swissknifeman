"""Общие утилиты maind: окружение (Env), atomic JSON, JSON-БД, backup.

Дословно общий с swissknifeman/brain код (die/warn/now_iso/confirm/sanitize +
ядро Env, parse_args, run_cmd, atomic/safe JSON) вынесен в общий core; HTTP-клиент
вынесен в `maind.http`, управляемый markdown-блок — в `maind.blocks` (реэкспорт ниже
для обратной совместимости импортов `from .common import ...`)."""
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые исторически берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, backup_file, confirm,
    detect_project_type, die, docs_visibility_for, find_monorepo_root,
    find_run_report, now_iso, parse_args, parse_iso, pid_alive, read_ndjson,
    read_ndjson_iter, run_cmd, safe_load_json, sanitize, warn,
)
from core import load_json_db as _core_load_json_db
# Выделенные модули — реэкспорт ради `from .common import ...` (back-compat).
from .blocks import content_hash, managed_block, upsert_block  # noqa: F401
from .http import http_get_json, http_post_json, ping  # noqa: F401

DB_VERSION = 1


@dataclass(frozen=True)
class Env(BaseEnv):
    """Контекст запуска maind: ядро (root/cmd/home) — из BaseEnv; здесь только
    path-property узла (~/.maind, root/data, config)."""

    # ── состояние пользователя (~/.maind) ──────────────────────────────────
    @property
    def state_dir(self):
        return self.home / ".maind"

    @property
    def projects_db(self):
        return self.state_dir / "projects.json"

    @property
    def agents_db(self):
        return self.state_dir / "agents.json"

    # ── runtime-данные узла (root/data, gitignored) ────────────────────────
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

    # ── конфигурация узла ──────────────────────────────────────────────────
    @property
    def memory_config(self):
        """Конфиг agent-memory демона. Env `MAIND_III_CONFIG` переопределяет путь
        (по образцу `MAIND_SKM_BIN`/`MAIND_BRAIN_BIN` в orchestrate); иначе —
        `config/memory/iii-config.yaml` в пакете."""
        override = os.environ.get("MAIND_III_CONFIG")
        if override:
            return Path(os.path.expanduser(override))
        return self.root / "config" / "memory" / "iii-config.yaml"

    @property
    def monorepo_root(self):
        """Корень монорепо — каталог с `packages/`/`core/` выше пакета. Конфиг узла
        (`config.json`) общий и лежит здесь. Fallback: сам root (standalone)."""
        return find_monorepo_root(self.root) or self.root

    @property
    def default_config(self):
        """Конфиг узла. Канонически — `config.json` в корне монорепо. Обратная
        совместимость: если его нет, но есть старый `.maind.json` (в корне или в
        пакете) — берём его (миграция без поломки существующих установок)."""
        root_cfg = self.monorepo_root / "config.json"
        if root_cfg.exists():
            return root_cfg
        for legacy in (self.monorepo_root / ".maind.json", self.root / ".maind.json"):
            if legacy.exists():
                return legacy
        return root_cfg  # путь по умолчанию для записи/подсказок — новый

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
        return self.default_config if self.default_config.is_file() else self.linked_worktree_config

    @property
    def example_config(self):
        """Шаблон конфига — `config.example.json` в корне монорепо (с legacy-fallback)."""
        root_ex = self.monorepo_root / "config.example.json"
        if root_ex.exists():
            return root_ex
        legacy = self.monorepo_root / ".maind.example.json"
        return legacy if legacy.exists() else root_ex

    @property
    def env_file(self):
        return self.root / ".env"


# die/warn/now_iso/confirm/sanitize — из общего core (реэкспорт выше).


# parse_args — из общего core (реэкспорт выше); раньше дублировался здесь
# (надмножество parse_flags с позиционными, стиль brain).


# backup_file — из общего core (реэкспорт выше); раньше дублировался здесь.
# managed_block/upsert_block/content_hash — в maind.blocks (реэкспорт выше).
# http_get_json/http_post_json/ping — в maind.http (реэкспорт выше).


# ── JSON-хранилища (atomic write + устойчивое чтение — общий core) ───────────
def load_json_db(path, default):
    """JSON-БД узла с восстановлением — общий core.load_json_db (битый → бэкап
    .corrupt.<date> + warn + deepcopy(default); version > DB_VERSION → die)."""
    return _core_load_json_db(path, default, max_version=DB_VERSION)
