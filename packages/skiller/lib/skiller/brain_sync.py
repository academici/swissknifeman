"""BRAIN docs-sync — синхронизация файлов между Brain-валтом и проектом.

До этого блок brain в integrate печатал ТОЛЬКО подсказку (настраивалось со стороны
волта). Здесь — минимальный детерминированный слой (stdlib-only): pull glob-паттернов
из BRAIN в проект и генерация bash-скрипта `.claude/sync-brain.sh` (двусторонняя
обёртка над rsync-подобной копией через shell, чтобы разработчик мог гонять синк вне
Claude Code).

Конфиг brain — из `.swissknife.json::memory_brain` (см. common.CONFIG_KEYS):
  строка          → путь к волту, без правил синка (доку-sync выключен, только
                    memory-хук в integrate — back-compat);
  объект {path,    → doc-sync: path + sync{direction, on_integrate, patterns}.
          sync?}

BrainSync нормализует обе формы: строка превращается в {"path": <строка>}.
"""
import shutil
from pathlib import Path

from core import atomic_write_text

# Дефолтные glob-паттерны doc-sync, если в конфиге patterns не заданы. docs/ —
# основная документация; README — точка входа. Относительны корня BRAIN/проекта.
DEFAULT_PATTERNS = ("docs/**/*.md", "README.md")
# Направление по умолчанию, если sync.direction не указан: pull (BRAIN → проект) —
# самое безопасное (в проект тянем готовую доку, из проекта в волт не пишем молча).
DEFAULT_DIRECTION = "pull"
DIRECTIONS = ("push", "pull", "bidirectional")


def normalize_brain_config(brain_config):
    """Привести конфиг brain к каноничному словарю {"path": str, "sync": {...}}.

    Строка → {"path": строка} (back-compat: путь без правил синка). Объект берётся
    как есть. None/пусто → {}. Возвращает НОВЫЙ словарь (вход не мутируется)."""
    if not brain_config:
        return {}
    if isinstance(brain_config, str):
        return {"path": brain_config}
    if isinstance(brain_config, dict):
        return dict(brain_config)
    return {}


class BrainSync:
    """Синхронизатор файлов проект↔BRAIN по glob-паттернам.

    project_path — корень потребляющего проекта; brain_config — значение
    `memory_brain` из .swissknife.json (строка-путь ИЛИ объект {path, sync?})."""

    def __init__(self, project_path, brain_config):
        self.project_path = Path(project_path)
        cfg = normalize_brain_config(brain_config)
        self.brain_path = Path(cfg["path"]) if cfg.get("path") else None
        sync = cfg.get("sync") or {}
        self.direction = sync.get("direction") or DEFAULT_DIRECTION
        self.on_integrate = bool(sync.get("on_integrate", False))
        self.patterns = list(sync.get("patterns") or DEFAULT_PATTERNS)

    # --- pull (BRAIN → проект) -------------------------------------------------
    def sync_pull(self):
        """Скопировать файлы из BRAIN в проект по self.patterns. Для каждого glob
        (относительно корня BRAIN) — mkdir каталога назначения + copy2 с сохранением
        относительного пути. Возвращает список скопированных файлов (пути в проекте).

        Идемпотентно (перезапись), НЕ удаляет лишнее в проекте (safety: pull только
        добавляет/обновляет). Если brain_path не задан или не существует — [] (мягко)."""
        if not self.brain_path or not self.brain_path.is_dir():
            return []
        copied = []
        for pattern in self.patterns:
            for src in sorted(self.brain_path.glob(pattern)):
                if not src.is_file():
                    continue
                rel = src.relative_to(self.brain_path)
                dst = self.project_path / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(dst)
        return copied

    # --- генерация shell-скрипта -----------------------------------------------
    def generate_sync_script(self, script_path=None):
        """Сгенерировать `.claude/sync-brain.sh` — bash-обёртка ручного синка
        BRAIN↔проект (rsync). Записывает атомарно; возвращает Path скрипта.

        Скрипт умеет pull/push по аргументу (по умолчанию — self.direction) и знает
        зашитый путь к BRAIN и паттерны из конфига. chmod 755 навешивает вызывающий
        (integrate) — здесь только контент."""
        if script_path is None:
            script_path = self.project_path / ".claude" / "sync-brain.sh"
        script_path = Path(script_path)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(script_path, self._render_script())
        return script_path

    def _render_script(self):
        """Тело bash-скрипта синка. Паттерны и путь к BRAIN — из конфига."""
        brain = str(self.brain_path) if self.brain_path else ""
        patterns = " ".join(_shell_quote(p) for p in self.patterns)
        default_dir = self.direction if self.direction in DIRECTIONS else DEFAULT_DIRECTION
        return _SCRIPT_TEMPLATE.format(
            brain=_shell_quote(brain),
            patterns=patterns,
            default_dir=default_dir,
        )


def _shell_quote(s):
    """Заключить строку в одинарные кавычки для безопасной подстановки в bash."""
    return "'" + str(s).replace("'", "'\\''") + "'"


# Шаблон генерируемого .claude/sync-brain.sh. Синхронизирует по glob-паттернам через
# rsync (сохраняя относительный путь). Аргумент 1 — направление (pull|push), дефолт
# зашит из конфига. Комментарии/сообщения на русском.
_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
# Сгенерировано skiller (brain_sync) — синхронизация документации проект↔BRAIN.
# Правь конфиг .swissknife.json::memory_brain, затем `skiller integrate` перегенерит.
set -euo pipefail

BRAIN={brain}
PROJECT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
PATTERNS=({patterns})
DIRECTION="${{1:-{default_dir}}}"

if [[ -z "$BRAIN" ]]; then
  echo "BRAIN не задан в .swissknife.json::memory_brain — нечего синхронизировать" >&2
  exit 1
fi

pull() {{  # BRAIN → проект
  for pat in "${{PATTERNS[@]}}"; do
    ( cd "$BRAIN" && find . -path "./$pat" -type f -print0 2>/dev/null ) \\
      | while IFS= read -r -d '' rel; do
          mkdir -p "$PROJECT/$(dirname "$rel")"
          cp -p "$BRAIN/$rel" "$PROJECT/$rel"
        done
  done
  echo "pull готов: BRAIN → проект"
}}

push() {{  # проект → BRAIN
  for pat in "${{PATTERNS[@]}}"; do
    ( cd "$PROJECT" && find . -path "./$pat" -type f -print0 2>/dev/null ) \\
      | while IFS= read -r -d '' rel; do
          mkdir -p "$BRAIN/$(dirname "$rel")"
          cp -p "$PROJECT/$rel" "$BRAIN/$rel"
        done
  done
  echo "push готов: проект → BRAIN"
}}

case "$DIRECTION" in
  pull) pull ;;
  push) push ;;
  bidirectional) pull; push ;;
  *) echo "неизвестное направление: $DIRECTION (pull|push|bidirectional)" >&2; exit 2 ;;
esac
"""
