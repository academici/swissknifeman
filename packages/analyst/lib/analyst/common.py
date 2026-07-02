"""Общие утилиты analyst: окружение (Env) + реэкспорт общего core.

Примитивы (die/warn/now_iso/confirm/sanitize, parse_args, run_cmd, atomic/safe JSON,
поиск корня монорепо) — из общего пакета `core` (подключается лаунчером через
PYTHONPATH). Реэкспортируем ради `from .common import ...` в модулях пакета."""
import os
from dataclasses import dataclass

from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_json, atomic_write_text, confirm,
    die, find_monorepo_root, find_run_report, now_iso, parse_args, parse_iso,
    read_ndjson, run_cmd, safe_load_json, sanitize, state_dir, warn,
)


@dataclass(frozen=True)
class Env(BaseEnv):
    """Контекст запуска analyst: ядро (root/cmd/home) — из BaseEnv; здесь только
    path-property. Cross-project слой (P2+) живёт в ~/.swissknifeman/analyst; per-project
    уроки — в <project>/.claude/analyst (см. lessons.project_dir)."""

    @property
    def state_dir(self):
        """Единый cross-project слой (кластеры/suggestions). Общий state зонтика —
        ~/.swissknifeman (им владеет skiller); analyst кладёт свой подкаталог."""
        return state_dir(self.home, "analyst")

    @property
    def monorepo_root(self):
        """Корень монорепо (каталог с packages//core/). Fallback: сам root (standalone)."""
        return find_monorepo_root(self.root) or self.root

    @property
    def default_config(self):
        """Конфиг узла экосистемы (config.json в корне монорепо) — реестр проектов для
        cross-project scan (P2). В P1 не обязателен; путь по умолчанию для чтения."""
        return self.monorepo_root / "config.json"


def project_path_from_opts(env, opts):
    """Путь проекта из --cwd (текущий каталог) или дефолт (cwd). --project (по реестру
    config.json) — P2; в P1 работаем с одним проектом из cwd."""
    _ = env, opts
    return os.getcwd()
