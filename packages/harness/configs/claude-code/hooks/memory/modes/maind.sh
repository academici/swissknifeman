#!/usr/bin/env bash
#

# Partner lookup (also the hook-side copy of aicore.util.partners): MAIND_BIN (deprecated) -> SKM_MAIND_BIN
# -> SKM_MAIND_ROOT/bin/maind -> PATH. Not found: the mode is skipped by its caller (fail-open).
_maind_bin() {
  if [ -n "${MAIND_BIN:-}" ] && [ -x "$MAIND_BIN" ]; then
    echo "MAIND_BIN_DEPRECATED: MAIND_BIN is deprecated; set SKM_MAIND_BIN" >&2
    printf '%s' "$MAIND_BIN"; return
  fi
  [ -n "${SKM_MAIND_BIN:-}" ] && [ -x "$SKM_MAIND_BIN" ] && { printf '%s' "$SKM_MAIND_BIN"; return; }
  [ -n "${SKM_MAIND_ROOT:-}" ] && [ -x "$SKM_MAIND_ROOT/bin/maind" ] && { printf '%s' "$SKM_MAIND_ROOT/bin/maind"; return; }
  local p; p="$(command -v maind 2>/dev/null)" && [ -n "$p" ] && { printf '%s' "$p"; return; }
  return 1
}

_maind_dir() { printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}"; }

mode_remember() { # brain type text
  local bin; bin="$(_maind_bin)" \
    || { echo "memory(maind): bin maind not found (set SKM_MAIND_ROOT or put maind on PATH)"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory remember --type "$2" "$3" )
}

mode_recall() { # brain query
  local bin; bin="$(_maind_bin)" || { echo "memory(maind): bin maind not found"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory recall "$2" )
}

mode_members() { # Shared-memory members are project peers by namespace.
  echo "mode maind: general - by namespace'project am (see maind projects status / graph --project)"
}

mode_status() { # brain
  local bin; bin="$(_maind_bin)" || { echo "memory(maind): bin maind not found"; return 1; }
  ( cd "$(_maind_dir)" && "$bin" memory status )
}

mode_sync() { mode_status "$1"; }
