#!/usr/bin/env bash
# memory — переключатель «единой памяти» для констелляции проектов.
# Использование: memory.sh <remember|recall|members|status|sync> [--brain B] [--type T] [текст/запрос...]
# Режим (бэкенд) — в env.ini: MODE=file|federation|agentmemory|off. Группы (brains)
# и участники — в config.json. Оба переопределяются per-project (.claude/memory.*).

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HOOK_DIR/lib/common.sh" || { echo "memory: нет lib/common.sh" >&2; exit 1; }
. "$HOOK_DIR/lib/store.sh"  || { echo "memory: нет lib/store.sh"  >&2; exit 1; }
require jq

MEM_CONFIG="$(config_file "$HOOK_DIR")"
[ -n "$MEM_CONFIG" ] || MEM_die "не найден config.json"

MODE="$(read_mode "$HOOK_DIR")"
case "$MODE" in file|federation|agentmemory|off) ;; *) MODE=off ;; esac
. "$HOOK_DIR/modes/$MODE.sh" || MEM_die "нет modes/$MODE.sh"

CMD="${1:-status}"; [ $# -gt 0 ] && shift

BRAIN=""; TYPE="project"; POS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --brain) BRAIN="$2"; shift 2 ;;
    --type)  TYPE="$2";  shift 2 ;;
    -h|--help) grep '^#' "$HOOK_DIR/memory.sh" | sed 's/^# \{0,1\}//' | sed -n '2,6p'; exit 0 ;;
    *) POS+=("$1"); shift ;;
  esac
done

[ -n "$BRAIN" ] || BRAIN="$(brain_default)"
[ -n "$BRAIN" ] || MEM_die "не задан brain (нет --brain, .swissknife.json:memory_brain и default_brain)"
brain_exists "$BRAIN" || MEM_die "brain '$BRAIN' не найден в config.json"

case "$CMD" in
  remember) [ "${#POS[@]}" -gt 0 ] || MEM_die "remember: нужен текст"; mode_remember "$BRAIN" "$TYPE" "${POS[*]}" ;;
  recall)   [ "${#POS[@]}" -gt 0 ] || MEM_die "recall: нужен запрос";  mode_recall   "$BRAIN" "${POS[*]}" ;;
  members)  mode_members "$BRAIN" ;;
  status)   mode_status  "$BRAIN" ;;
  sync)     mode_sync    "$BRAIN" ;;
  *) MEM_die "неизвестная подкоманда: $CMD (remember|recall|members|status|sync)" ;;
esac
