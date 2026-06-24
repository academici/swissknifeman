"""Канонический детектор типа проекта — единый источник истины монорепо.

До вынесения сюда тип определялся ТРЕМЯ расходящимися Python-копиями
(`skiller.config.autodetect`, `maind.onboard._infer_type`, `maind.config._infer_type`)
с разными таксономиями плюс 4-й декларативной копией в `pack.json:stack.detect`. Здесь —
одна упорядоченная таблица маркеров (специфичное → общее). Функция НЕ бросает (битый JSON
манифеста → деградация к более грубому маркеру) и всегда возвращает реальный id из
PROJECT_TYPES (дефолт `standalone`, НИКОГДА `unknown` — sentinel отсутствующего пути
остаётся у вызывающего ради back-compat записей `config.json`).

`id == имя файла профиля skiller` (`profiles/<id>.json`) — не менять без миграции профилей;
строки `php-package`/`node-package` несущие (maind `language_by_type`, `codegraph`), их не
переименовывать. stdlib-only."""
import json
from pathlib import Path

# Упорядочено специфичное → общее; id == имя профиля skiller.
PROJECT_TYPES = (
    "obsidian-vault",
    "laravel-project",
    "php-package",
    "dart-flutter",
    "python-backend",
    "node-frontend",
    "node-package",
    "standalone",
)

# Язык код-графа (Serena) по типу. Источник для maind.constants.language_by_type.
LANGUAGE_BY_TYPE = {
    "laravel-project": "php",
    "php-package": "php",
    "dart-flutter": "dart",
    "python-backend": "python",
    "node-frontend": "typescript",
    "node-package": "typescript",
}

# package.json-проект → frontend, если есть UI-фреймворк/сборщик (иначе node-package:
# библиотека/CLI/бэкенд-node).
_FRONTEND_DEP_HINTS = (
    "vue", "nuxt", "react", "svelte", "@angular/core",
    "@inertiajs/vue3", "@inertiajs/react", "vite",
)
_FRONTEND_CONFIG_FILES = (
    "vite.config.ts", "vite.config.js", "vue.config.js",
    "nuxt.config.ts", "nuxt.config.js", "svelte.config.js",
)


def _load_json(path):
    """Безопасно прочитать JSON; любой сбой → {} (детектор не должен падать)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _is_node_frontend(path):
    """package.json-проект: frontend (UI-фреймворк/сборщик) vs node-package."""
    if any((path / name).is_file() for name in _FRONTEND_CONFIG_FILES):
        return True
    pkg = _load_json(path / "package.json")
    deps = {}
    for key in ("dependencies", "devDependencies"):
        section = pkg.get(key)
        if isinstance(section, dict):
            deps.update(section)
    return any(hint in deps for hint in _FRONTEND_DEP_HINTS)


def detect_project_type(path):
    """Тип проекта по маркерам в каталоге (специфичное → общее). Всегда возвращает id
    из PROJECT_TYPES; дефолт `standalone`. Не бросает: несуществующий путь или битый
    манифест деградируют к более грубому ответу. `unknown` НЕ возвращается — это
    sentinel вызывающего (maind) для отсутствующего пути."""
    p = Path(path)
    if (p / ".obsidian").is_dir():
        return "obsidian-vault"
    composer = (p / "composer.json").is_file()
    if composer and (p / "artisan").is_file():
        return "laravel-project"
    if composer:
        return "php-package"
    if (p / "pubspec.yaml").is_file():
        return "dart-flutter"
    # python раньше node: package.json часто лишь сборочный тулинг python-проекта.
    if ((p / "pyproject.toml").is_file() or (p / "requirements.txt").is_file()
            or (p / "setup.py").is_file()):
        return "python-backend"
    if (p / "package.json").is_file():
        return "node-frontend" if _is_node_frontend(p) else "node-package"
    return "standalone"
