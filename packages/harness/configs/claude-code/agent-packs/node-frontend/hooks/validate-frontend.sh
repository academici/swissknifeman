#!/usr/bin/env bash
# validate-frontend — PostToolUse-валидатор (advisory, НИКОГДА не блокирует).
#
# После Edit/Write по *.ts|*.tsx|*.vue гоняет VALIDATE_CMD (typecheck+lint) и при
# падении ВОЗВРАЩАЕТ находки в additionalContext (агент видит и сам чинит). Не exit 2.
#
# Конфиг: .claude/review-gate.env.ini → VALIDATE_MODE (off|warn), VALIDATE_CMD.
# Семантика: всегда exit 0; при провале — JSON hookSpecificOutput.additionalContext.
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

STDIN="$(cat 2>/dev/null || true)"
# реагируем только на правки исходников фронта
if ! printf '%s' "$STDIN" | grep -Eq '\.(ts|tsx|vue)"'; then
  exit 0
fi

MODE="warn"; CMD=""
CFG="$PROJECT_DIR/.claude/review-gate.env.ini"
if [[ -f "$CFG" ]]; then
  while IFS='=' read -r key val; do
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    val="$(printf '%s' "$val" | sed -E 's/^[[:space:]]*//; s/[[:space:]]*$//; s/^"//; s/"$//')"
    case "$key" in
      VALIDATE_MODE) [[ -n "$val" ]] && MODE="$val" ;;
      VALIDATE_CMD)  [[ -n "$val" ]] && CMD="$val" ;;
    esac
  done < <(grep -vE '^[[:space:]]*[#;]' "$CFG" 2>/dev/null || true)
fi
[[ "$MODE" == "off" || -z "$CMD" ]] && exit 0

FIRST_BIN="$(printf '%s' "$CMD" | awk '{print $1}')"
command -v "$FIRST_BIN" >/dev/null 2>&1 || exit 0

OUT="$(bash -c "$CMD" 2>&1)"; RC=$?
[[ $RC -eq 0 ]] && exit 0

TRIM="$(printf '%s' "$OUT" | tail -n 30)"
MSG="validate-frontend: проверка упала после правки — почини (advisory).
\$ $CMD
$TRIM"
# additionalContext через stdout JSON (PostToolUse), без блокировки.
python3 - "$MSG" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PostToolUse", "additionalContext": sys.argv[1]}}))
PY
exit 0
