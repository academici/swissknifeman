#!/usr/bin/env bash

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HOOK_DIR/lib/common.sh" || { echo "memory: no lib/common.sh" >&2; exit 1; }
. "$HOOK_DIR/lib/store.sh"  || { echo "memory: no lib/store.sh"  >&2; exit 1; }
require jq

MEM_CONFIG="$(config_file "$HOOK_DIR")"
[ -n "$MEM_CONFIG" ] || MEM_die "not found config.json"

MODE="$(read_mode "$HOOK_DIR")"
case "$MODE" in maind|file|federation|agentmemory|off) ;; *) MODE=off ;; esac
. "$HOOK_DIR/modes/$MODE.sh" || MEM_die "no modes/$MODE.sh"

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
[ -n "$BRAIN" ] || MEM_die "not specified brain (no --brain, .swissknife.json:memory_brain and default_brain)"
brain_exists "$BRAIN" || MEM_die "brain '$BRAIN' not found in config.json"

case "$CMD" in
  remember) [ "${#POS[@]}" -gt 0 ] || MEM_die "remember: text needed"; mode_remember "$BRAIN" "$TYPE" "${POS[*]}" ;;
  recall)   [ "${#POS[@]}" -gt 0 ] || MEM_die "recall: request needed";  mode_recall   "$BRAIN" "${POS[*]}" ;;
  members)  mode_members "$BRAIN" ;;
  status)   mode_status  "$BRAIN" ;;
  sync)     mode_sync    "$BRAIN" ;;
  *) MEM_die "unknown subcommand: $CMD (remember|recall|members|status|sync)" ;;
esac
