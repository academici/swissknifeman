#!/usr/bin/env bash
# context-notify.sh — statusLine-скрипт Claude Code: печатает компактную строку
# статуса (модель · каталог · бар · N% контекста) и при ПЕРЕСЕЧЕНИИ полосы порога
# отсоединённо дёргает существующую доставку hooks/notify/notify.sh (ОС-уведомление).
#
# Контракт рантайма (first-party /docs/en/statusline, 2026-07-25):
#   • запускается на старте сессии и далее — на каждом новом сообщении ассистента,
#     после `/compact`, при смене permission-режима, vim-режима, по refreshInterval;
#   • апдейты дебаунсятся 300 мс, а скрипт МОЖЕТ БЫТЬ УБИТ на середине новым
#     апдейтом ⇒ побочный эффект отсоединён, состояние пишется атомарно (tmp+mv);
#   • ширина терминала приходит в COLUMNS/LINES (`tput cols` изнутри НЕ работает);
#   • used_percentage бывает null (начало сессии, после `/compact`) — null это НЕ 0:
#     нет процента → бар не рисуется и решение о пороге НЕ принимается;
#   • statusline не тратит контекст-токенов («runs locally and does not consume API
#     tokens») — цена этого скрипта измеряется в миллисекундах, не в токенах.
#
# Дешевизна — правило, а не пожелание: РОВНО ОДИН внешний вызов на рендер (jq одним
# выражением). git/curl/python3/сеть в горячем пути запрещены. Внешние `mkdir`/`mv`/
# `find` возможны только на редких ветках (старт сессии, смена полосы), не на рендере.
#
# Никогда не падает наружу: любая ветка ошибки → минимальная строка + exit 0.
# Диагностика — в файл при DEBUG=true (stderr пользователю не показывается).
#
# Включение: harness hooks --target <проект> --statusline context
# Kill-switch: `disableAllHooks` в settings глушит хуки И любой custom status line.
set -uo pipefail

SELF="${BASH_SOURCE[0]:-$0}"
SELF_DIR="$(cd -- "${SELF%/*}" 2>/dev/null && pwd -P)" || SELF_DIR="."

# --- дефолты; перебиваются env.ini рядом со скриптом -------------------------
THRESHOLDS="80,90"     # полосы порога, по возрастанию
COOLDOWN_MIN=15        # минут между уведомлениями (0 — без кулдауна)
BAR_WIDTH=10           # ширина бара в символах
DEBUG=false
NOTIFY_CMD="$SELF_DIR/../hooks/notify/notify.sh"   # готовая кросс-платформенная доставка

ENV_FILE="${STATUSLINE_ENV_FILE:-$SELF_DIR/env.ini}"
if [[ -f "$ENV_FILE" ]]; then
  # разбор построчно встроенными средствами (никакого `source`: env.ini — данные, не код)
  while IFS='=' read -r _k _v || [[ -n "${_k:-}" ]]; do
    _k="${_k%%#*}"; _k="${_k//[[:space:]]/}"
    [[ -n "$_k" ]] || continue
    _v="${_v%%#*}"
    _v="${_v#"${_v%%[![:space:]]*}"}"; _v="${_v%"${_v##*[![:space:]]}"}"
    _v="${_v%\"}"; _v="${_v#\"}"; _v="${_v%\'}"; _v="${_v#\'}"
    case "$_k" in
      THRESHOLDS)   [[ -n "$_v" ]] && THRESHOLDS="$_v" ;;
      COOLDOWN_MIN) [[ -n "$_v" ]] && COOLDOWN_MIN="$_v" ;;
      BAR_WIDTH)    [[ -n "$_v" ]] && BAR_WIDTH="$_v" ;;
      DEBUG)        [[ -n "$_v" ]] && DEBUG="$_v" ;;
      NOTIFY_CMD)   [[ -n "$_v" ]] && NOTIFY_CMD="$_v" ;;
    esac
  done < "$ENV_FILE"
fi
[[ "$COOLDOWN_MIN" =~ ^[0-9]+$ ]] || COOLDOWN_MIN=15
[[ "$BAR_WIDTH" =~ ^[0-9]+$ ]] && (( BAR_WIDTH > 0 && BAR_WIDTH <= 40 )) || BAR_WIDTH=10

STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/claude-statusline"

debug() {
  [[ "$DEBUG" == "true" ]] || return 0
  printf '%s %s\n' "${EPOCHSECONDS:-0}" "$*" >> "$STATE_DIR/debug.log" 2>/dev/null || true
}

# Атомарная запись состояния: скрипт могут убить на середине, частично записанное
# состояние недопустимо (tmp в том же каталоге + mv).
write_state() {
  local b="$1" ts="$2" tmp="$STATE.$$.tmp"
  printf 'BAND=%s\nLAST_NOTIFY=%s\n' "$b" "$ts" > "$tmp" 2>/dev/null || return 0
  mv -f "$tmp" "$STATE" 2>/dev/null || rm -f "$tmp" 2>/dev/null
  return 0
}

# Доставка ОТСОЕДИНЕНА: отмена рендерера не должна ни терять алерт, ни плодить сирот.
notify_detached() {
  local msg="$1" cwd="$2" payload dj mj
  [[ -x "$NOTIFY_CMD" ]] || { debug "notify: нет исполняемого $NOTIFY_CMD"; return 0; }
  dj="${cwd//\\/\\\\}"; dj="${dj//\"/\\\"}"
  mj="${msg//\\/\\\\}"; mj="${mj//\"/\\\"}"
  payload="$(printf '{"message":"%s","cwd":"%s"}' "$mj" "$dj")"
  if command -v setsid >/dev/null 2>&1; then
    ( printf '%s' "$payload" | setsid "$NOTIFY_CMD" >/dev/null 2>&1 & ) 2>/dev/null
  else
    # macOS: setsid нет — подоболочка всё равно отвязывает job от этого процесса
    ( printf '%s' "$payload" | "$NOTIFY_CMD" >/dev/null 2>&1 & ) 2>/dev/null
  fi
  debug "notify: отправлено «$msg»"
  return 0
}

input="$(cat 2>/dev/null)" || input=""

# --- ЕДИНСТВЕННЫЙ внешний вызов рендера --------------------------------------
# `// empty` (а не `// 0`): отсутствующий процент остаётся ПУСТЫМ полем, чтобы
# ниже его нельзя было спутать с нулём. Внешний `// ""` лишь удерживает форму
# @tsv (пустая колонка вместо исчезнувшей).
meta=""
if command -v jq >/dev/null 2>&1; then
  meta="$(printf '%s' "$input" | jq -r '
    [ (.model.display_name // .model.id // "-"),
      (.workspace.current_dir // .cwd // "-"),
      (((.context_window.used_percentage // empty) | tostring) // ""),
      (.session_id // "-") ] | @tsv' 2>/dev/null)" || meta=""
fi

MODEL=""; DIR=""; PCT=""; SID=""
IFS=$'\t' read -r MODEL DIR PCT SID <<<"$meta" || true
[[ -n "$MODEL" ]] || MODEL="-"
[[ -n "$DIR" ]] || DIR="${PWD:-}"
[[ -n "$SID" ]] || SID="nosession"

# --- строка статуса ----------------------------------------------------------
name="${DIR##*/}"; [[ -n "$name" ]] || name="-"
line="$MODEL · $name"

pct_int=""
if [[ "$PCT" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  pct_int="${PCT%%.*}"
  (( pct_int > 100 )) && pct_int=100
  filled=$(( pct_int * BAR_WIDTH / 100 ))
  (( filled > BAR_WIDTH )) && filled=$BAR_WIDTH
  bar=""
  for (( i = 0; i < BAR_WIDTH; i++ )); do
    if (( i < filled )); then bar+="#"; else bar+="-"; fi
  done
  line+=" · [$bar] ${pct_int}%"
fi

cols="${COLUMNS:-0}"
if [[ "$cols" =~ ^[0-9]+$ ]] && (( cols > 12 )) && (( ${#line} > cols )); then
  line="${line:0:cols-1}…"
fi
printf '%s\n' "$line"

# Процента нет (null в начале сессии / после /compact) — решение о пороге НЕ
# принимается вовсе: трактовать null как 0% значило бы «сбросить» полосу.
[[ -n "$pct_int" ]] || exit 0

# --- полоса порога -----------------------------------------------------------
band=0; crossed=0
IFS=',' read -r -a _thr <<<"$THRESHOLDS" || true
for t in "${_thr[@]:-}"; do
  t="${t//[[:space:]]/}"
  [[ "$t" =~ ^[0-9]+$ ]] || continue
  if (( pct_int >= t )); then
    band=$(( band + 1 ))
    (( t > crossed )) && crossed=$t
  fi
done

sid="${SID//[^A-Za-z0-9._-]/_}"
STATE="$STATE_DIR/$sid.state"
[[ -d "$STATE_DIR" ]] || mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

fresh=0
if [[ ! -f "$STATE" ]]; then
  fresh=1
  # Старт сессии — ЕДИНСТВЕННОЕ место уборки: состояния старше суток удаляются,
  # иначе каталог растёт вечно. На рендерах внутри сессии этой ветки нет.
  find "$STATE_DIR" -maxdepth 1 -name '*.state' -mtime +1 -delete 2>/dev/null || true
fi

prev_band=0; last_notify=0
if (( fresh == 0 )); then
  while IFS='=' read -r _k _v || [[ -n "${_k:-}" ]]; do
    case "$_k" in
      BAND) prev_band="$_v" ;;
      LAST_NOTIFY) last_notify="$_v" ;;
    esac
  done < "$STATE"
fi
[[ "$prev_band" =~ ^[0-9]+$ ]] || prev_band=0
[[ "$last_notify" =~ ^[0-9]+$ ]] || last_notify=0

now="${EPOCHSECONDS:-}"
[[ "$now" =~ ^[0-9]+$ ]] || now="$(date +%s 2>/dev/null || echo 0)"

if (( fresh == 1 )); then
  # Файл состояния обязан появиться сразу, иначе каждый рендер считался бы
  # «стартом сессии» и гонял бы уборку.
  write_state 0 0
fi

if (( band > prev_band )); then
  if (( COOLDOWN_MIN == 0 || now - last_notify >= COOLDOWN_MIN * 60 )); then
    write_state "$band" "$now"
    notify_detached "Контекст ${pct_int}% — пройден порог ${crossed}%. Пора /compact или /clear." "$DIR"
  else
    # Полосу НЕ повышаем: алерт не теряется, а откладывается до конца кулдауна.
    debug "полоса $prev_band→$band при ${pct_int}% — кулдаун не истёк, отложено"
  fi
elif (( band < prev_band )); then
  # Падение (после /compact) сбрасывает состояние вниз: новый разгон уведомит снова.
  write_state "$band" "$last_notify"
  debug "полоса $prev_band→$band при ${pct_int}% — сброс вниз"
fi

exit 0
