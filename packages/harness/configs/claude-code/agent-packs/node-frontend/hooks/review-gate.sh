#!/usr/bin/env bash
#
#
#
#

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

STDIN="$(cat 2>/dev/null || true)"
if printf '%s' "$STDIN" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

MODE="warn"
CMD="vendor/bin/pint --parallel --test -q"
CFG="$PROJECT_DIR/.claude/review-gate.env.ini"
if [[ -f "$CFG" ]]; then
  while IFS='=' read -r key val; do
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    val="$(printf '%s' "$val" | sed -E 's/^[[:space:]]*//; s/[[:space:]]*$//; s/^"//; s/"$//')"
    case "$key" in
      REVIEW_GATE_MODE) [[ -n "$val" ]] && MODE="$val" ;;
      REVIEW_GATE_CMD)  [[ -n "$val" ]] && CMD="$val" ;;
    esac
  done < <(grep -vE '^[[:space:]]*[#;]' "$CFG" 2>/dev/null || true)
fi

[[ "$MODE" == "off" ]] && exit 0

FIRST_BIN="$(printf '%s' "$CMD" | awk '{print $1}')"
if [[ "$FIRST_BIN" == */* ]]; then
  [[ -x "$PROJECT_DIR/$FIRST_BIN" || -x "$FIRST_BIN" ]] || exit 0
else
  command -v "$FIRST_BIN" >/dev/null 2>&1 || exit 0
fi

OUT="$(bash -c "$CMD" 2>&1)"
RC=$?
[[ $RC -eq 0 ]] && exit 0

TRIM="$(printf '%s' "$OUT" | tail -n 40)"

if [[ "$MODE" == "strict" ]]; then
  printf 'review-gate (strict): quality check failed - fix before completion.\n$ %s\n%s\n' "$CMD" "$TRIM" >&2
  exit 2
fi

printf 'review-gate (warn): quality control failed (not blocking).\n$ %s\n%s\n' "$CMD" "$TRIM" >&2
exit 0
