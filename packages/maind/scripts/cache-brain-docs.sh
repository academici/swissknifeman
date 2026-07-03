#!/usr/bin/env bash
# Кэширует BRAIN-документы проекта в память maind (agent-memory), чтобы их можно было
# поднять через `maind memory recall`, не перечитывая файлы с диска при каждом запросе.
#
# ВАЖНО: команды `maind memory store` / флагов --key/--file НЕ существует (это выдумка
# из внешнего аудита) — реальная CLI-подкоманда записи это `maind memory remember` с
# флагами --project|--scope, --share, --type, --json (см. packages/maind/lib/maind/memory.py
# _cmd_remember). Ключ-топик документа (docs:brd, docs:architecture, ...) передаём через
# --type — единственный флаг, который несёт «тип факта» в текущей CLI.
#
# Использование:
#   scripts/cache-brain-docs.sh --scope project:<ns> <topic>=<path/to/file.md> [<topic>=<path> ...]
#
# Пример:
#   scripts/cache-brain-docs.sh --scope project:loqum \
#     docs:brd=docs-private/dev/BRD.md \
#     docs:architecture=docs-private/dev/Architecture_Loqum.md
#
# Вспомнить потом:
#   maind memory recall --scope project:loqum "docs:brd"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAIND_BIN="$REPO_ROOT/bin/maind"

usage() {
  echo "Использование: $0 --scope <scope> <topic>=<path> [<topic>=<path> ...]" >&2
  echo "  (или --project <id> вместо --scope)" >&2
  exit 1
}

[ $# -ge 2 ] || usage

SCOPE_ARGS=()
case "$1" in
  --scope)   SCOPE_ARGS=(--scope "$2");   shift 2 ;;
  --project) SCOPE_ARGS=(--project "$2"); shift 2 ;;
  *) usage ;;
esac

[ $# -ge 1 ] || usage

for pair in "$@"; do
  topic="${pair%%=*}"
  path="${pair#*=}"
  if [ "$topic" = "$pair" ] || [ -z "$path" ]; then
    echo "ERROR: ожидался формат <topic>=<path>, получено: $pair" >&2
    exit 1
  fi
  if [ ! -f "$path" ]; then
    echo "WARN: файл не найден, пропуск: $path" >&2
    continue
  fi
  content="$(cat -- "$path")"
  echo "→ remember ${SCOPE_ARGS[*]} --type $topic ← $path"
  "$MAIND_BIN" memory remember "${SCOPE_ARGS[@]}" --type "$topic" "$content"
done
