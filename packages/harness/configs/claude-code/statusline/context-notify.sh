#!/usr/bin/env bash
#
#
#
#
set -uo pipefail

SELF="${BASH_SOURCE[0]:-$0}"
SELF_DIR="$(cd -- "${SELF%/*}" 2>/dev/null && pwd -P)" || SELF_DIR="."

THRESHOLDS="80,90"     # threshold bands, ascending
COOLDOWN_MIN=15        # minutes between notifications (0 disables cooldown)
BAR_WIDTH=10           # bar width in characters
DEBUG=false
NOTIFY_CMD="$SELF_DIR/../hooks/notify/notify.sh"   # cross-platform delivery command

ENV_FILE="${STATUSLINE_ENV_FILE:-$SELF_DIR/env.ini}"
if [[ -f "$ENV_FILE" ]]; then
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

write_state() {
  local b="$1" ts="$2" tmp="$STATE.$$.tmp"
  printf 'BAND=%s\nLAST_NOTIFY=%s\n' "$b" "$ts" > "$tmp" 2>/dev/null || return 0
  mv -f "$tmp" "$STATE" 2>/dev/null || rm -f "$tmp" 2>/dev/null
  return 0
}

notify_detached() {
  local msg="$1" cwd="$2" payload dj mj
  [[ -x "$NOTIFY_CMD" ]] || { debug "notify: no executable $NOTIFY_CMD"; return 0; }
  dj="${cwd//\\/\\\\}"; dj="${dj//\"/\\\"}"
  mj="${msg//\\/\\\\}"; mj="${mj//\"/\\\"}"
  payload="$(printf '{"message":"%s","cwd":"%s"}' "$mj" "$dj")"
  if command -v setsid >/dev/null 2>&1; then
    ( printf '%s' "$payload" | setsid "$NOTIFY_CMD" >/dev/null 2>&1 & ) 2>/dev/null
  else
    ( printf '%s' "$payload" | "$NOTIFY_CMD" >/dev/null 2>&1 & ) 2>/dev/null
  fi
  debug "notify: sent «$msg»"
  return 0
}

input="$(cat 2>/dev/null)" || input=""

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

[[ -n "$pct_int" ]] || exit 0

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
  find "$STATE_DIR" -maxdepth 1 \( -name '*.state' -o -name '*.tmp' \) -mtime +1 -delete 2>/dev/null || true
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
  write_state 0 0
fi

if (( band > prev_band )); then
  if (( COOLDOWN_MIN == 0 || now - last_notify >= COOLDOWN_MIN * 60 )); then
    write_state "$band" "$now"
    notify_detached "Context ${pct_int}% — crossed threshold ${crossed}%. It's time /compact or /clear." "$DIR"
  else
    debug "strip $prev_band→$band when ${pct_int}% — cooldown not expired, delayed"
  fi
elif (( band < prev_band )); then
  write_state "$band" "$last_notify"
  debug "strip $prev_band→$band when ${pct_int}% — reset down"
fi

exit 0
