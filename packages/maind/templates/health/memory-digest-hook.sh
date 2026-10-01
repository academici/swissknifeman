#!/usr/bin/env bash
# managed by maind — SessionStart: inject project memory DIGEST into context Claude Code
# via additionalContext. Replaces native auto-loading MEMORY.md, when MODE=maind
# (native turns off autoMemoryEnabled:false). The demon lay down / empty → quiet no-op.
# v2 (2026-07-12, P1.2): digest now project-only default + byte-budget (P1.1) —
# template version bump makes existing copies stale for `maind sync`.
# Source: <maind>/templates/health/memory-digest-hook.sh — edit THERE and
# `maind sync --only memory-hook --all --mode update`, is not in the project copy.
# Launcher maind: env MAIND_BIN → PATH (command -v). No machine-specific path
# in the artifact - the generated hook is the same on any machine. Not found → quiet no-op.
MAIND="${MAIND_BIN:-}"
[ -n "$MAIND" ] || MAIND="$(command -v maind 2>/dev/null)"
[ -n "$MAIND" ] && [ -x "$MAIND" ] || exit 0
digest="$("$MAIND" memory digest 2>/dev/null)"
[ -n "$digest" ] || exit 0
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg c "$digest" \
    '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
else
  printf '%s\n' "$digest"          # fallback: flat stdout also falls into context
fi
exit 0
