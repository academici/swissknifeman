#!/usr/bin/env bash
# typecheck.sh — pyright over the typed modules (config in pyrightconfig.json, mode basic).
# Usage: scripts/typecheck.sh [pyright args...]
# pyright is a development tool, not a runtime dependency. It must be on PATH (`pipx install pyright`) or runnable by
# pipx. Also runs through uvx or pipx. Exit 2 and TYPECHECK_TOOL_MISSING when none is there. Not a CI step yet: the first run sets the baseline.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if command -v pyright >/dev/null 2>&1; then
  exec pyright "$@"
elif command -v uvx >/dev/null 2>&1; then
  exec uvx pyright "$@"
elif command -v pipx >/dev/null 2>&1; then
  exec pipx run pyright "$@"
fi
echo "TYPECHECK_TOOL_MISSING: need pyright on PATH, uvx or pipx." >&2
echo "  install:  uv tool install pyright   (or: pipx install pyright, npm install -g pyright)" >&2
exit 2
