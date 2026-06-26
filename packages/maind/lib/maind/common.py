"""Общие утилиты maind: окружение (Env), atomic JSON, JSON-БД, backup.

Дословно общий с swissknifeman/brain код (die/warn/now_iso/confirm/sanitize +
ядро Env, parse_args, run_cmd, atomic/safe JSON) вынесен в общий core; HTTP-клиент
вынесен в `maind.http`, управляемый markdown-блок — в `maind.blocks` (реэкспорт ниже
для обратной совместимости импортов `from .common import ...`)."""
import copy
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Общий core (подключается через PYTHONPATH лаунчером/test.sh). Реэкспорт для
# модулей пакета, которые исторически берут эти имена из .common.
from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, confirm,
    detect_project_type, die, find_monorepo_root, now_iso, parse_args,
    run_cmd, safe_load_json, sanitize, warn,
)
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


# ── файловые помощники ──────────────────────────────────────────────────────
def backup_file(path):
    """Копия <path>.bak, если файл существует. Возвращает путь бэкапа или None."""
    path = Path(path)
    if not path.exists():
        return None
    bak = path.with_name(path.name + ".bak")
    shutil.copy2(path, bak)
    return bak


# managed_block/upsert_block/content_hash — в maind.blocks (реэкспорт выше).
# http_get_json/http_post_json/ping — в maind.http (реэкспорт выше).


# ── JSON-хранилища (atomic write — из core; устойчивое чтение — здесь) ───────
def load_json_db(path, default):
    """Читает JSON-БД. Битый файл → бэкап .corrupt.<date> + warn + копия default.
    Версия новее DB_VERSION → die. default не мутируется (возвращается deepcopy)."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        db = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_name(f"{path.name}.corrupt.{date.today().isoformat()}")
        path.rename(backup)
        warn(f"{path} повреждён → сохранён в {backup} (начинаю заново)")
        return copy.deepcopy(default)
    if isinstance(db, dict) and db.get("version", 1) > DB_VERSION:
        die(f"{path} записан более новой версией maind — обновите репозиторий (git pull)")
    return db
