#!/usr/bin/env bash
# review-gate — SubagentStop-гейт качества для memster.
#
# Когда субагент завершается, гоняем лёгкую статическую проверку (по умолчанию
# pint --test) и в зависимости от режима: тихо пропускаем / предупреждаем /
# блокируем завершение, чтобы агент починил.
#
# Адаптация harness review-gate (Stage B, off|warn|strict) под memster:
# phpstan в проекте НЕ установлен, поэтому дефолтная проверка — только Pint.
#
# Конфиг: .claude/review-gate.env.ini
#   REVIEW_GATE_MODE = off | warn | strict   (по умолчанию warn)
#   REVIEW_GATE_CMD  = команда проверки       (по умолчанию vendor/bin/pint --parallel --test -q)
#
# Семантика (только exit-коды, без хрупких JSON-полей):
#   off    → exit 0 всегда.
#   warn   → проверка упала: advisory в stderr, exit 0 (не блокирует).
#   strict → проверка упала: причина в stderr, exit 2 (блок → агент чинит).
# Защита от петли: если stop_hook_active=true (агент уже продолжен этим хуком) — exit 0.

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

# stdin несёт JSON SubagentStop. Без jq: грепаем флаг защиты от петли.
STDIN="$(cat 2>/dev/null || true)"
if printf '%s' "$STDIN" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

# --- конфиг -----------------------------------------------------------------
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

# Нет инструмента — не наказываем, тихо выходим (универсально по стекам:
# путь vendor/bin/* | bin/* проверяем на исполняемость, bare-команду — на PATH).
FIRST_BIN="$(printf '%s' "$CMD" | awk '{print $1}')"
if [[ "$FIRST_BIN" == */* ]]; then
  [[ -x "$PROJECT_DIR/$FIRST_BIN" || -x "$FIRST_BIN" ]] || exit 0
else
  command -v "$FIRST_BIN" >/dev/null 2>&1 || exit 0
fi

# --- проверка ---------------------------------------------------------------
OUT="$(bash -c "$CMD" 2>&1)"
RC=$?
[[ $RC -eq 0 ]] && exit 0

# Срезаем вывод, чтобы не топить транскрипт.
TRIM="$(printf '%s' "$OUT" | tail -n 40)"

if [[ "$MODE" == "strict" ]]; then
  printf 'review-gate (strict): проверка качества упала — почини перед завершением.\n$ %s\n%s\n' "$CMD" "$TRIM" >&2
  exit 2
fi

# warn (дефолт): advisory, не блокируем.
printf 'review-gate (warn): проверка качества упала (не блокирую).\n$ %s\n%s\n' "$CMD" "$TRIM" >&2
exit 0
