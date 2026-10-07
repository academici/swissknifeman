#!/usr/bin/env bash
#
#
#   ./install.sh [--bin-dir DIR] [--force]
#
#
#   harness mcp --target . --mcp context7
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

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/harness"
BIN_DIR="$HOME/.local/bin"
FORCE=false

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI not found or not executable" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 not found - CLI will require it at startup" >&2

mkdir -p "$BIN_DIR"

LINK="$BIN_DIR/harness"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  current="$(readlink -f "$LINK" 2>/dev/null || true)"
  if [[ "$current" == */bin/harness ]]; then
    : # Managed symlink; replace it silently.
  elif [[ "$FORCE" == true ]]; then
    : # Explicit override.
  elif [[ -t 0 ]]; then
    read -r -p "$LINK already exists and is not similar to harness. Replace? [y/N] " answer
    [[ "$answer" =~ ^[yY] ]] || { echo "Canceled."; exit 1; }
  else
    echo "ERROR: $LINK already exists - restart with --force" >&2
    exit 1
  fi
fi
ln -sfn "$CLI" "$LINK"
echo "Installed: $LINK -> $CLI"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "WARN: $BIN_DIR not in PATH. Add:"
    case "$(basename "${SHELL:-bash}")" in
      zsh)  echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc" ;;
      fish) echo "  fish_add_path $BIN_DIR" ;;
      *)    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
    esac ;;
esac

echo "Check: harness doctor"
