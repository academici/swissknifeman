#!/usr/bin/env bash
# install.sh — installs the gui CLI (the local control plane of Swiss Knife Man).
#
# Creates the symlink <bin-dir>/gui -> <module>/bin/gui, installs the locked Python packages of the backend
# (`gui deps ensure`: requirements.lock, sha256-checked, no virtual environment) and, when npm is available,
# builds the frontend (npm ci && npm run build in frontend/). Without npm the backend still installs and
# `gui open` answers FRONTEND_NOT_BUILT until the frontend is built.
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force]
#
#   --bin-dir DIR   where to put the symlink (default ~/.local/bin)
#   --force         replace someone else's file/symlink without question
#
# Next:
#   gui open        # the GUI in the browser (starts the backend when none runs)
set -euo pipefail
# --- swissknifeman dev-clone guard (PLAN3 D13; removed at cutover) ---
_skm_guard_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
while [ "$_skm_guard_dir" != "/" ] && [ ! -e "$_skm_guard_dir/.swissknifeman-dev" ]; do _skm_guard_dir="$(dirname "$_skm_guard_dir")"; done
if [ -e "$_skm_guard_dir/.swissknifeman-dev" ] && [ "${SKM_DEV_ALLOW_LIVE:-}" != "1" ]; then
  _skm_real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
  if [ -z "$_skm_real_home" ] || [ "$(readlink -f "${HOME:-/}")" = "$(readlink -f "$_skm_real_home")" ]; then
    echo "SKM_DEV_GUARD: $_skm_guard_dir is a development clone; run inside scripts/dev-sandbox.sh or set SKM_DEV_ALLOW_LIVE=1" >&2
    exit 3
  fi
fi
unset _skm_guard_dir _skm_real_home
# --- end dev-clone guard ---

MODULE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$MODULE_ROOT/bin/gui"
FRONTEND="$MODULE_ROOT/frontend"
BIN_DIR="$HOME/.local/bin"
FORCE=false

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,16p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI not found or not executable" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: gui requires python3 (3.11 or newer)" >&2; exit 1; }

mkdir -p "$BIN_DIR"
LINK="$BIN_DIR/gui"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  current="$(readlink -f "$LINK" 2>/dev/null || true)"
  if [[ "$current" == */bin/gui ]]; then
    : # our symlink (possibly from an old clone): replace silently
  elif [[ "$FORCE" == true ]]; then
    : # explicit permission
  elif [[ -t 0 ]]; then
    read -r -p "$LINK already exists and is not the gui CLI. Replace? [y/N] " answer
    [[ "$answer" =~ ^[yY] ]] || { echo "Canceled."; exit 1; }
  else
    echo "ERROR: $LINK already exists - restart with --force" >&2
    exit 1
  fi
fi
ln -sfn "$CLI" "$LINK"
echo "Installed: $LINK -> $CLI"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "WARN: PYTHON_TOO_OLD: gui needs Python 3.11 or newer; the CLI is linked but will refuse to run" >&2
  exit 0
fi

# The locked third-party packages of the backend are required: without them `gui serve` cannot start.
"$CLI" deps ensure

if command -v npm >/dev/null 2>&1; then
  if (cd "$FRONTEND" && npm ci --no-audit --no-fund && npm run build); then
    echo "Frontend built: $FRONTEND/dist"
  else
    echo "WARN: FRONTEND_NOT_BUILT: the frontend build failed (Node 22.22+ is needed); retry with:" >&2
    echo "  npm --prefix $FRONTEND ci && npm --prefix $FRONTEND run build" >&2
  fi
else
  echo "WARN: FRONTEND_NOT_BUILT: npm not found; the backend is installed, build the frontend later with:" >&2
  echo "  npm --prefix $FRONTEND ci && npm --prefix $FRONTEND run build" >&2
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "WARN: $BIN_DIR is not in PATH; add it to your shell profile" ;;
esac

echo "Next: gui open"
