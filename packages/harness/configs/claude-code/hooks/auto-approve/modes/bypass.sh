#!/usr/bin/env bash
HOOK_NAME="auto-approve(bypass)"

if [ "$HOOK_TOOL" = "ExitPlanMode" ]; then
  HOOK_CMD="ExitPlanMode"
  emit_allow "bypass: план подтверждён автоматически"
fi

[ "$HOOK_TOOL" = "Bash" ] || fallthrough
prepare_bash || fallthrough
run_bash_analysis bypass
