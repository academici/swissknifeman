#!/usr/bin/env bash
# docs-sync — assemble an umbrella site from per-package docs.
# Source of truth - packages/<pkg>/docs (each package owns its own docks);
# assembly copies are copied here docs/<pkg>/ (gitignored). VitePress sees them as
# real files in srcDir → correct routing and relative links (symlinks
# VitePress resolves to real paths outside srcDir — breaks routes, so copy).
# Runs before `vitepress build|dev` (see packages/skiller/package.json).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="write"
if [ "${1:-}" = "--check" ]; then
  MODE="check"
elif [ "$#" -gt 0 ]; then
  echo "usage: $0 [--check]" >&2
  exit 2
fi

sync_pkg() {
  local src="$ROOT/packages/$1/docs" dst="$ROOT/docs/$1"
  [ -d "$src" ] || { echo "  no $src — pass"; return; }
  if [ "$MODE" = "check" ]; then
    local tmp
    tmp="$(mktemp -d)"
    cp -r "$src/." "$tmp/"
    rm -rf "$tmp/.vitepress"
    if [ ! -e "$dst" ]; then
      rm -rf "$tmp"
      echo "  docs/$1 not materialized; source tree playable"
      return
    fi
    if ! diff -qr "$tmp" "$dst" >/dev/null; then
      echo "  docs/$1 is deprecated; run bash scripts/docs-sync.sh" >&2
      rm -rf "$tmp"
      return 1
    fi
    rm -rf "$tmp"
    echo "  docs/$1 fresh"
    return
  fi
  rm -rf "$dst"
  mkdir -p "$dst"
  cp -r "$src/." "$dst/"
  rm -rf "$dst/.vitepress"   # nested per-package vitepress is not needed in the unit
  echo "  docs/$1 ← packages/$1/docs"
}
echo "docs-sync:"
sync_pkg skiller
sync_pkg harness
sync_pkg maind   # internal links maind-docks relative → work and standalone, and in the unit
sync_pkg analyst # continuous learning; internal links are relative (standalone + unit)
sync_pkg task
