#!/usr/bin/env bash
# Режим maind — делегирует «единую память» в `maind memory` (демон :4111 + ИЗОЛЯЦИЯ
# на стороне maind: scope-маркер в контенте, т.к. демон-пул один и namespace не фильтрует).
# brain ИГНОРИРУЕТСЯ: scope берётся из проекта (CLAUDE_PROJECT_DIR → match_cwd внутри maind
# по config.json) — приватный project:<id> + общие ns:<тег> + global. Источается memory.sh.
#
# Почему не agentmemory.sh: тот режим бил в неверные эндпоинты и в namespace демона,
# который демон всё равно игнорирует. maind — единый клиент со scope-моделью и изоляцией.

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

mode_members() { # brain — участники общей памяти = пиры проекта по namespace'ам
  echo "режим maind: общее — по namespace'ам проекта (см. maind projects status / graph --project)"
}

mode_status() { # brain
  local bin; bin="$(_maind_bin)" || { echo "memory(maind): bin maind не найден"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory status )
}

mode_sync() { mode_status "$1"; }
