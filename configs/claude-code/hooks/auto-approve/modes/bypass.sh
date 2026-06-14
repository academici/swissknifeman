#!/usr/bin/env bash
# Режим BYPASS (максимальная автономия): авто-подтверждение диалога плана
# (ExitPlanMode) И одобрение любых команд, кроме катастрофичных (deny_hard).
# Самый агрессивный режим — только для доверенных проектов/контейнеров.
HOOK_NAME="auto-approve(bypass)"

if [ "$HOOK_TOOL" = "ExitPlanMode" ]; then
  HOOK_CMD="ExitPlanMode"
  emit_allow "bypass: план подтверждён автоматически"
fi

[ "$HOOK_TOOL" = "Bash" ] || fallthrough
prepare_bash || fallthrough
run_bash_analysis bypass
