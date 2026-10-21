#!/usr/bin/env bash
# install.sh — sets CLI analyst (layer of continuous learning ecosystem).
#
# Creates a symlink <bin-dir>/analyst -> <repo>/bin/analyst. Package stateless —
# per-project lessons live in .claude/analyst/ target projects; cross-project layer
# (P2+) — in ~/.swissknifeman/analyst/. There is no own installation directory.
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force]
#
#   --bin-dir DIR   where to put the symlink (default ~/.local/bin)
#   --force         replace someone else's file/symlink without question
#
# Next - from any consuming project:
#   analyst digest        # candidate-lessons from fresh run-report
#   analyst review        # review + diff against active
#   analyst promote <id>  # promotion man-gate
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/analyst"
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

LINK="$BIN_DIR/analyst"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  current="$(readlink -f "$LINK" 2>/dev/null || true)"
  if [[ "$current" == */bin/analyst ]]; then
    : # our symlink (possibly from an old clone) — silently replace
  elif [[ "$FORCE" == true ]]; then
    : # explicit permission
  elif [[ -t 0 ]]; then
    read -r -p "$LINK already exists and is not similar to analyst. Replace? [y/N] " answer
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

echo "Check: analyst doctor"
