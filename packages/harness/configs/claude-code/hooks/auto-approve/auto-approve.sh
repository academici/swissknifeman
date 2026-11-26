#!/usr/bin/env bash
# ============================================================================
#
#
#   - https://github.com/yigitkonur/auto-approve-claude-plan  (auto-approve ExitPlanMode)
# ============================================================================

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

. "$HOOK_DIR/lib/common.sh"   2>/dev/null || exit 0
. "$HOOK_DIR/lib/analyze.sh"  2>/dev/null || exit 0
. "$HOOK_DIR/lib/safedirs.sh" 2>/dev/null || exit 0

require jq
read_input

MODE="$(read_mode "$HOOK_DIR")"
case "$MODE" in
  strict|permissive|bypass) ;;
  *) fallthrough;;   # off or unknown: use the normal permission flow
esac

. "$HOOK_DIR/modes/$MODE.sh"
