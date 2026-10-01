#!/usr/bin/env bash
# generate-hub.sh — генерирует в целевом проекте корневой «хаб» скиллов:
# приоритеты чтения источников + правила поиска + (где нужно) индекс скиллов.
#
# Тонкий лаунчер: вся логика — в lib/skiller/hub.py (импортируемая и тестируемая,
# см. tests/test_hub.py), здесь только резолв PYTHONPATH, как в bin/skiller.
#
# Источники данных об установленном (объединяются):
#   .claude/settings.local.json / settings.json -> enabledPlugins."<bucket>@swissknifeman"
#   .swissknifeman-manifest.json в .claude/skills | .cursor/skills | .ai/skills
#
# Режимы записи:
#   проект с Laravel Boost (есть boost.json) -> .ai/guidelines/swissknifeman-hub.md
#       (Boost сам вставит фрагмент в CLAUDE.md при `php artisan boost:update`)
#   проект без Boost -> managed-блок в CLAUDE.md между маркерами
#       <!-- swissknifeman:hub:start --> ... <!-- swissknifeman:hub:end -->
#       (контент вне маркеров не изменяется; файл создаётся при отсутствии)
#   --root-files A,B -> тот же managed-блок дополнительно в указанные корневые
#       файлы (например AGENTS.md,GEMINI.md) — для тулз вне Boost. Игнорируется
#       в режиме Boost (там источник — .ai/guidelines/swissknifeman-hub.md).
#
# Форма блока — по КАНАЛУ-ЦЕЛИ (D20 плана):
#   CLAUDE.md и Boost-фрагмент  -> краткая (у канала есть нативный листинг
#       скиллов, индекс в блоке был бы вторым платным экземпляром);
#   AGENTS.md/GEMINI.md и пр.   -> полная (индекс — единственное обнаружение).
#   --full-index                -> полная форма всем целям (путь отката).
# Скилл убирается из блока только после машинной сверки «он есть и в наборе
# измерителя, и в нативном канале раздачи»; неподтверждённые остаются в блоке.
#
# Использование:
#   ./scripts/generate-hub.sh --target ~/projects/my-app
#   ./scripts/generate-hub.sh --target . --dry-run
#   ./scripts/generate-hub.sh --target . --root-files AGENTS.md,GEMINI.md
#   ./scripts/generate-hub.sh --target . --full-index
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '2,32p'; exit "${1:-0}"; }

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage 0

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: generate-hub.sh требует python3" >&2
  exit 1
fi

# Корень монорепо (на два уровня выше пакета) даёт пакет `core`; в standalone-
# раскладке каталога core рядом нет — путь не добавляется (тот же приём, что в
# bin/skiller: core ещё не на PYTHONPATH, поэтому резолв на bash-стороне).
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""

exec env PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m skiller.hub "$REPO_ROOT" "$@"
