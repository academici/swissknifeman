#!/usr/bin/env bash
# managed by maind — SessionEnd feature-log (DOES NOT block). Commits NEW HEAD-commit
# project to shared memory (maind fleet log), so that the optimizer agent sees «what changed».
# Source: <maind>/templates/health/feature-log-hook.sh — edit there and `maind sync
# --only feature-log-hook --all --mode update`, and not in the copy of the project.
# Launcher maind: env MAIND_BIN → PATH (command -v). No machine-specific path
# in the artifact - the generated hook is the same on any machine. Not found → quiet no-op.
MAIND="${MAIND_BIN:-}"
[ -n "$MAIND" ] || MAIND="$(command -v maind 2>/dev/null)"
[ -n "$MAIND" ] && [ -x "$MAIND" ] || exit 0
command -v git >/dev/null 2>&1 || exit 0
HEAD="$(git rev-parse --short HEAD 2>/dev/null)" || exit 0
LAST_FILE=".claude/.maind-feature-log.last"
[ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE" 2>/dev/null)" = "$HEAD" ] && exit 0  # already pledged
SUBJECT="$(git log -1 --pretty=format:%s 2>/dev/null)"
[ -n "$SUBJECT" ] || exit 0
"$MAIND" fleet log "$SUBJECT (#$HEAD)" --project "{{PROJECT}}" >/dev/null 2>&1 || true
printf '%s' "$HEAD" > "$LAST_FILE" 2>/dev/null || true
exit 0
