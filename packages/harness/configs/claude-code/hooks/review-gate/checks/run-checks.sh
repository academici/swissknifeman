#!/usr/bin/env bash
# run-checks.sh — диспетчер review-gate: единственный `check_command` в
# config.json. Прогоняет набор проверок из `config.json:checks[]`
# (`{"name","mode"}`), применяет глобальный downgrade (`REVIEW_GATE_MODE=warn`
# понижает strict→warn; апгрейд warn→strict запрещён — класс проверки знает
# про свой ложный фон больше, чем машина) и защиту от петли (третий подряд
# strict-отказ ТОЙ ЖЕ проверки в этой сессии+агенте → разовое понижение до
# warn + systemMessage-строка `[DOWNGRADE]`).
#
# Контракт с review-gate.sh (единственный писатель CHECK/MODE/…):
#   exit 0 — все проверки чисты.
#   exit 1 — есть нарушения, но эффективно ВСЕ warn (никогда не блокирует).
#   exit 2 — есть хотя бы одно эффективно strict-нарушение (блокирует).
# stdout — по строке на нарушение: "[STRICT|WARN] <check>: <сообщение>";
# понижение петлёй добавляет "[DOWNGRADE] <check>: <причина>".
#
# Требует REVIEW_GATE_DIR (свой каталог хука, экспортирует review-gate.sh).
set -uo pipefail

DIR="${REVIEW_GATE_DIR:?REVIEW_GATE_DIR не экспортирован review-gate.sh}"
CHECKS_DIR="$DIR/checks"
CONFIG="$DIR/config.json"
MODE="${REVIEW_GATE_MODE:-warn}"
SESSION="${REVIEW_GATE_SESSION:-nosession}"
AGENT="${REVIEW_GATE_AGENT_ID:-noagent}"
# REVIEW_GATE_STATE_DIR — override для тестов (изоляция от реального /tmp машины);
# продакшн-дефолт не меняется.
STATE_DIR="${REVIEW_GATE_STATE_DIR:-${XDG_RUNTIME_DIR:-/tmp}/review-gate}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[WARN] dispatcher: jq недоступен на этой машине — набор проверок пропущен (деградация, не тихий exit 0)"
  exit 1
fi

if [ ! -f "$CONFIG" ]; then
  echo "[WARN] dispatcher: $CONFIG не найден — набор проверок пропущен"
  exit 1
fi

mapfile -t NAMES < <(jq -r '.checks[]?.name // empty' "$CONFIG" 2>/dev/null)
[ "${#NAMES[@]}" -gt 0 ] || exit 0   # пустой набор — чисто (unconfigured отдельно ловит doctor)

overall=0   # 0 чисто, 1 warn, 2 strict
for name in "${NAMES[@]}"; do
  script="$CHECKS_DIR/$name.sh"
  state_file="$STATE_DIR/${SESSION}.${AGENT}.${name}"

  if [ ! -x "$script" ]; then
    echo "[WARN] dispatcher: неизвестная проверка в checks[]: '$name' (нет исполняемого $script)"
    [ "$overall" -lt 1 ] && overall=1
    continue
  fi

  cfg_mode="$(jq -r --arg n "$name" '.checks[] | select(.name==$n) | (.mode // "warn")' "$CONFIG" 2>/dev/null | head -1)"
  case "$cfg_mode" in strict|warn) ;; *) cfg_mode=warn ;; esac

  out="$("$script" 2>&1)"; rc=$?
  if [ "$rc" -eq 0 ]; then
    rm -f "$state_file" 2>/dev/null || true
    continue
  fi

  intended_strict=0
  [ "$cfg_mode" = strict ] && [ "$MODE" != warn ] && intended_strict=1

  eff_mode=warn
  if [ "$intended_strict" -eq 1 ]; then
    prev=0
    if [ -f "$state_file" ]; then
      prev="$(cat "$state_file" 2>/dev/null || echo 0)"
      case "$prev" in ''|*[!0-9]*) prev=0 ;; esac
    fi
    next=$((prev + 1))
    mkdir -p "$STATE_DIR" 2>/dev/null || true
    tmp="$(mktemp "$STATE_DIR/.tmp.XXXXXX" 2>/dev/null || printf '%s.tmp' "$state_file")"
    if [ "$next" -ge 3 ]; then
      echo "[DOWNGRADE] $name: гейт понижен: проверка $name не проходит 3-й раз, чиню вручную (счётчик: $state_file)"
      printf '0\n' > "$tmp" && mv -f "$tmp" "$state_file"
      eff_mode=warn
    else
      printf '%s\n' "$next" > "$tmp" && mv -f "$tmp" "$state_file"
      eff_mode=strict
    fi
  else
    rm -f "$state_file" 2>/dev/null || true
  fi

  tag="WARN"; [ "$eff_mode" = strict ] && tag="STRICT"
  while IFS= read -r line; do
    [ -n "$line" ] && echo "[$tag] $name: $line"
  done <<< "$out"

  if [ "$eff_mode" = strict ]; then
    overall=2
  else
    [ "$overall" -lt 1 ] && overall=1
  fi
done

exit "$overall"
