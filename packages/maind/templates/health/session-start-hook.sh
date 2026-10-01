#!/usr/bin/env bash
# managed by maind — SessionStart healthcheck connections with the hub (DOES NOT block work).
# Quiet when connection is healthy (--strict rc=0 → exit 0, without context load); prints status
# connections (memory + maind MCP) into session context ONLY when something is unhealthy.
# Source: <maind>/templates/health/session-start-hook.sh — edit there and `maind sync
# --only health-hook --all --mode update`, and not in the copy of the project.
# Launcher maind: env MAIND_BIN → PATH (command -v). No machine-specific path
# in the artifact - the generated hook is the same on any machine. Not found → quiet no-op.
MAIND="${MAIND_BIN:-}"
[ -n "$MAIND" ] || MAIND="$(command -v maind 2>/dev/null)"
[ -n "$MAIND" ] && [ -x "$MAIND" ] || exit 0
out="$("$MAIND" health --cwd --strict 2>/dev/null)"
rc=$?
[ "$rc" -eq 0 ] && exit 0
[ -n "$out" ] && printf '%s\n' "$out"
exit 0
