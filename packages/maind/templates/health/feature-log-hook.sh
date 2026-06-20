#!/usr/bin/env bash
# managed by maind — SessionEnd feature-log (НЕ блокирует). Фиксирует НОВЫЙ HEAD-коммит
# проекта в общую память (maind fleet log), чтобы агент-оптимизатор видел «что менялось».
# Источник: <maind>/templates/health/feature-log-hook.sh — правьте там и `maind sync
# --only feature-log-hook --all --mode update`, а не в копии проекта.
MAIND="{{MAIND_BIN}}"
[ -x "$MAIND" ] || exit 0
command -v git >/dev/null 2>&1 || exit 0
HEAD="$(git rev-parse --short HEAD 2>/dev/null)" || exit 0
LAST_FILE=".claude/.maind-feature-log.last"
[ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE" 2>/dev/null)" = "$HEAD" ] && exit 0  # уже залогировано
SUBJECT="$(git log -1 --pretty=format:%s 2>/dev/null)"
[ -n "$SUBJECT" ] || exit 0
"$MAIND" fleet log "$SUBJECT (#$HEAD)" --project "{{PROJECT}}" >/dev/null 2>&1 || true
printf '%s' "$HEAD" > "$LAST_FILE" 2>/dev/null || true
exit 0
