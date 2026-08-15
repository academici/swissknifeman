#!/usr/bin/env bash
#

_maind_bin() {
  [ -n "${MAIND_BIN:-}" ] && [ -x "$MAIND_BIN" ] && { printf '%s' "$MAIND_BIN"; return; }
  local p; p="$(command -v maind 2>/dev/null)" && [ -n "$p" ] && { printf '%s' "$p"; return; }
  local skm; skm="$(topo_node_path swissknifeman)"
  local c
  for c in "$skm/packages/maind/bin/maind" \
           "$HOME/projects/packages/swissknifeman/packages/maind/bin/maind"; do
    [ -x "$c" ] && { printf '%s' "$c"; return; }
  done
  return 1
}

_maind_dir() { printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}"; }

mode_remember() { # brain type text
  local bin; bin="$(_maind_bin)" \
    || { echo "memory(maind): bin maind не найден (задай MAIND_BIN / PATH / топологию)"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory remember --type "$2" "$3" )
}

mode_recall() { # brain query
  local bin; bin="$(_maind_bin)" || { echo "memory(maind): bin maind не найден"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory recall "$2" )
}

mode_members() { # Shared-memory members are project peers by namespace.
  echo "режим maind: общее — по namespace'ам проекта (см. maind projects status / graph --project)"
}

mode_status() { # brain
  local bin; bin="$(_maind_bin)" || { echo "memory(maind): bin maind не найден"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory status )
}

mode_sync() { mode_status "$1"; }
