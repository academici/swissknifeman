#!/usr/bin/env bash

MEM_die() { echo "memory: $*" >&2; exit 1; }

require() { local b; for b in "$@"; do command -v "$b" >/dev/null 2>&1 || MEM_die "needed $b"; done; }

expandtilde() {
  case "$1" in
    "~"/*) printf '%s' "$HOME/${1#\~/}" ;;
    "~")   printf '%s' "$HOME" ;;
    *)     printf '%s' "$1" ;;
  esac
}

# Value of KEY from the committed carrier <project>/.swissknifeman/hooks.env (provider key first).
read_hooks_env() {
  local key="$1" dir="${2:-}" f v
  f="$dir/.swissknifeman/hooks.env"
  [ -n "$dir" ] && [ -f "$f" ] || return 1
  v="$(grep -E "^${key}__CLAUDE_CODE=" "$f" | head -1 | cut -d= -f2- | tr -d ' \r')"
  [ -n "$v" ] || v="$(grep -E "^${key}=" "$f" | head -1 | cut -d= -f2- | tr -d ' \r')"
  [ -n "$v" ] || return 1
  printf '%s' "$v"
}

read_mode() {
  local dir="$1" f m
  m="$(read_hooks_env MEMORY_MODE "${CLAUDE_PROJECT_DIR:-}")" || m=""
  [ -n "$m" ] && { printf '%s' "$m"; return; }
  for f in "${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.claude/memory.env.ini}" "$dir/env.ini"; do
    [ -n "$f" ] && [ -f "$f" ] || continue
    m="$(grep -E '^[[:space:]]*MODE[[:space:]]*=' "$f" | head -1 \
         | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]#].*$//' | tr -d "\"'")"
    [ -n "$m" ] && { printf '%s' "$m"; return; }
  done
  printf 'off'
}

config_file() {
  local dir="$1" f
  for f in "${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.claude/memory.config.json}" "$dir/config.json"; do
    [ -n "$f" ] && [ -f "$f" ] && { printf '%s' "$f"; return; }
  done
}

cfg() {
  [ -n "${MEM_CONFIG:-}" ] && [ -f "$MEM_CONFIG" ] || { printf ''; return; }
  jq -r "$1 // empty" "$MEM_CONFIG" 2>/dev/null
}

# --- brains -------------------------------------------------------------------
brain_default() {
  local b=""
  b="$(read_hooks_env MEMORY_BRAIN "${CLAUDE_PROJECT_DIR:-}")" || b=""
  if [ -z "$b" ] && [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -f "$CLAUDE_PROJECT_DIR/.swissknife.json" ]; then
    b="$(jq -r '.memory_brain // empty' "$CLAUDE_PROJECT_DIR/.swissknife.json" 2>/dev/null)"
  fi
  [ -n "$b" ] || b="$(cfg '.default_brain')"
  printf '%s' "$b"
}

brain_exists()  { [ -n "$(cfg ".brains[\"$1\"]")" ]; }
brain_members() { cfg ".brains[\"$1\"].members[]"; }
brain_store()   { expandtilde "$(cfg ".brains[\"$1\"].store")"; }
brain_am_url()  { cfg ".brains[\"$1\"].agentmemory.url"; }
brain_am_ns()   { local v; v="$(cfg ".brains[\"$1\"].agentmemory.namespace")"; printf '%s' "${v:-$1}"; }

# An owner's registry file: its own state file (the XDG state directory of swissknifeman, or $SKM_HOME/state), else the
# legacy ~/.swissknifeman/<name> while only that one exists (not under SKM_HOME). Same ladder as aicore.state.locations.
mem_state_file() {
  local owner="$1" name="$2" base new
  if [ -n "${SKM_HOME:-}" ]; then printf '%s' "$SKM_HOME/state/$owner/$name"; return; fi
  base="${XDG_STATE_HOME:-}"; case "$base" in /*) ;; *) base="$HOME/.local/state" ;; esac
  new="$base/swissknifeman/$owner/$name"
  if [ ! -f "$new" ] && [ -f "$HOME/.swissknifeman/$name" ]; then printf '%s' "$HOME/.swissknifeman/$name"; else printf '%s' "$new"; fi
}
MEM_TOPO="$(mem_state_file maind topology.json)"
MEM_PROJDB="$(mem_state_file skiller projects.json)"

topo_node_path() { [ -f "$MEM_TOPO" ] && jq -r ".nodes[\"$1\"].path // empty" "$MEM_TOPO" 2>/dev/null; }

resolve_member_path() {
  local m="$1" p base
  case "$m" in
    brain|swissknifeman|projects_base)
      p="$(topo_node_path "$m")"; [ -n "$p" ] && { printf '%s' "$p"; return; } ;;
  esac
  case "$m" in
    /*)    printf '%s' "$m"; return ;;
    "~"/*) expandtilde "$m"; return ;;
  esac
  if [ -f "$MEM_PROJDB" ]; then
    p="$(jq -r --arg n "$m" '.projects[].path | select(test("/"+$n+"$"))' "$MEM_PROJDB" 2>/dev/null | head -1)"
    [ -n "$p" ] && { printf '%s' "$p"; return; }
  fi
  base="$(topo_node_path projects_base)"
  [ -n "$base" ] && printf '%s' "$base/$m" || printf '%s' "$m"
}
