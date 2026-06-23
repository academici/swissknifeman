#!/usr/bin/env bash
# Observer capture-хук — ЭКСПЕРИМЕНТАЛЬНО, per-project.
# Лёгкий project-local лог намерений/результатов + алерт LOOP для post-hoc
# разбора скиллом `system/session-observer`. Дополняет сырой session-JSONL
# вычисленными алертами и компактной project-local записью.
#
# Висит на PreToolUse / PostToolUse / Stop (см. settings.observer.json — opt-in
# пресет, не глобально). Включается флагом проекта:
#   .claude/observer.env.ini → ENABLED=true   (дефолт false = no-op)
#
# НИКОГДА не блокирует (это наблюдатель, не гейт; гейт = review-gate) — exit 0.

set -uo pipefail
input=$(cat 2>/dev/null) || exit 0
command -v jq >/dev/null 2>&1 || exit 0

cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null); [ -n "$cwd" ] || cwd="$PWD"

# Toggle (per-project) — выключено по умолчанию.
EN=$(grep -E '^[[:space:]]*ENABLED' "$cwd/.claude/observer.env.ini" 2>/dev/null \
      | head -1 | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*//' | tr -d "\"'")
[ "$EN" = "true" ] || exit 0

OBS="$cwd/.claude/observer"; mkdir -p "$OBS" 2>/dev/null || exit 0
LOG="$OBS/runtime.jsonl"
EVENT=$(printf '%s' "$input" | jq -r '.hook_event_name // ""' 2>/dev/null)
TOOL=$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case "$EVENT" in
  PreToolUse)
    jq -cn --arg ts "$TS" --arg t "$TOOL" '{ts:$ts,phase:"PRE",tool:$t}' >> "$LOG" 2>/dev/null
    ;;
  PostToolUse)
    err=$(printf '%s' "$input" | jq -r '((.tool_response.is_error // false) or (.tool_response.success==false))' 2>/dev/null)
    cf="$OBS/error_count"
    if [ "$err" = "true" ]; then
      n=$(( $(cat "$cf" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cf"
      [ "$n" -ge 3 ] && jq -cn --arg ts "$TS" --arg t "$TOOL" --argjson n "$n" \
        '{ts:$ts,alert:"LOOP",tool:$t,count:$n}' >> "$LOG" 2>/dev/null
      jq -cn --arg ts "$TS" --arg t "$TOOL" '{ts:$ts,phase:"POST",tool:$t,outcome:"error"}' >> "$LOG" 2>/dev/null
    else
      echo 0 > "$cf"
      jq -cn --arg ts "$TS" --arg t "$TOOL" '{ts:$ts,phase:"POST",tool:$t,outcome:"ok"}' >> "$LOG" 2>/dev/null
    fi
    ;;
  Stop)
    [ -f "$LOG" ] || exit 0
    lines=$(wc -l < "$LOG" 2>/dev/null || echo 0)
    alerts=$(grep -c '"alert"' "$LOG" 2>/dev/null || echo 0)
    printf '# Observer summary\n- tool calls: %s\n- alerts: %s\n- разбор: скилл system/session-observer (/observe session)\n- %s\n' \
      "$lines" "$alerts" "$TS" > "$OBS/last_report.md" 2>/dev/null
    mkdir -p "$OBS/archive" 2>/dev/null
    cp "$LOG" "$OBS/archive/$(date -u +%Y%m%dT%H%M%SZ).jsonl" 2>/dev/null
    : > "$LOG"
    echo 0 > "$OBS/error_count" 2>/dev/null
    ;;
esac
exit 0
