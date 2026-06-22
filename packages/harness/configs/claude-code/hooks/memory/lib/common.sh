#!/usr/bin/env bash
# Общая библиотека «единой памяти». Источать (source), не запускать.
# Резолв brain/участников опирается на топологию (~/.swissknifeman/topology.json)
# и реестр проектов (~/.swissknifeman/projects.json).

MEM_die() { echo "memory: $*" >&2; exit 1; }

require() { local b; for b in "$@"; do command -v "$b" >/dev/null 2>&1 || MEM_die "нужен $b"; done; }

expandtilde() {
  case "$1" in
    "~"/*) printf '%s' "$HOME/${1#\~/}" ;;
    "~")   printf '%s' "$HOME" ;;
    *)     printf '%s' "$1" ;;
  esac
}

# --- режим и конфиг: приоритет per-project → hookdir ---------------------------
read_mode() {
  local dir="$1" f m
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

# cfg <jq-filter> — против активного config.json (MEM_CONFIG выставляет memory.sh).
cfg() {
  [ -n "${MEM_CONFIG:-}" ] && [ -f "$MEM_CONFIG" ] || { printf ''; return; }
  jq -r "$1 // empty" "$MEM_CONFIG" 2>/dev/null
}

# --- brains -------------------------------------------------------------------
brain_default() {
  local b=""
  if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && [ -f "$CLAUDE_PROJECT_DIR/.swissknife.json" ]; then
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

# --- топология / проекты ------------------------------------------------------
MEM_TOPO="$HOME/.swissknifeman/topology.json"
MEM_PROJDB="$HOME/.swissknifeman/projects.json"

topo_node_path() { [ -f "$MEM_TOPO" ] && jq -r ".nodes[\"$1\"].path // empty" "$MEM_TOPO" 2>/dev/null; }

# resolve_member_path <member>: имя узла топологии → путь; абсолютный путь / ~ →
# как есть; иначе projects.json по суффиксу пути, иначе projects_base/<name>.
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
