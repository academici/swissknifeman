#!/usr/bin/env bash
# ============================================================================
# auto-approve — PreToolUse hook-переключатель для Claude Code.
#
# Регистрируется на матчеры Bash и ExitPlanMode. Режим работы выбирается в
# env.ini (рядом) и вызывает один из modes/*.sh. Смена режима => перезапуск сессии.
#
# Адаптировано и объединено из:
#   - https://github.com/oryband/claude-code-auto-approve     (AST-разбор, allow/deny)
#   - https://github.com/yigitkonur/auto-approve-claude-plan  (auto-approve ExitPlanMode)
#   - https://github.com/froggeric/claude-smart-approval      (разбор компаунд-команд)
# Подробнее об источниках — CREDITS.md.
# ============================================================================

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

. "$HOOK_DIR/lib/common.sh"  2>/dev/null || exit 0
. "$HOOK_DIR/lib/analyze.sh" 2>/dev/null || exit 0

require jq
read_input

MODE="$(read_mode "$HOOK_DIR")"
case "$MODE" in
  strict|permissive|bypass) ;;
  *) fallthrough;;   # off / неизвестно => обычный permission-флоу
esac

. "$HOOK_DIR/modes/$MODE.sh"
