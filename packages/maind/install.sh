#!/usr/bin/env bash
# install.sh — sets CLI maind.
#
# Creates a symlink <bin-dir>/maind -> <repo>/bin/maind and status directory ~/.maind
# (projects.json/agents.json — node registries, replenished with commands CLI).
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--with-memory] [--with-service]
#
#   --bin-dir DIR   where to put the symlink (default ~/.local/bin)
#   --force         replace someone else's file/symlink without question
#   --with-memory   npm install at the root maind (memory daemon @agentmemory/agentmemory)
#   --with-service  register memory daemon as systemd --user service
#                   (maind service install — autorun + auto-restart)
#
# Full bootstrap: ./install.sh --with-memory --with-service
# Daemon ports are configured via .env (see .env.example), so as not to conflict
# with another node. Code graph (Serena) — optional, installed separately (per-project).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/maind"
BIN_DIR="$HOME/.local/bin"
FORCE=false
WITH_MEMORY=false
WITH_SERVICE=false

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --with-memory) WITH_MEMORY=true; shift ;;
    --with-service) WITH_SERVICE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI not found or not executable" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 not found - CLI will require it at startup" >&2

mkdir -p "$BIN_DIR" "$HOME/.maind"
[[ -f "$HOME/.maind/projects.json" ]] || \
  printf '{\n  "version": 1,\n  "projects": []\n}\n' > "$HOME/.maind/projects.json"
[[ -f "$HOME/.maind/agents.json" ]] || \
  printf '{\n  "version": 1,\n  "agents": []\n}\n' > "$HOME/.maind/agents.json"

LINK="$BIN_DIR/maind"
if [[ -e "$LINK" || -L "$LINK" ]]; then
  current="$(readlink -f "$LINK" 2>/dev/null || true)"
  if [[ "$current" == */bin/maind ]]; then
    : # our symlink (possibly from an old clone) — silently replace
  elif [[ "$FORCE" == true ]]; then
    : # explicit permission
  elif [[ -t 0 ]]; then
    read -r -p "$LINK already exists and is not similar to maind. Replace? [y/N] " answer
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

# ── optional bootstrap memory daemon ─────────────────────────────────────
if [[ "$WITH_MEMORY" == true ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Installing the memory daemon (npm install in $REPO_ROOT)..."
    ( cd "$REPO_ROOT" && npm install ) || echo "WARN: npm install failed"
  else
    echo "WARN: npm not found - skipping memory daemon installation (needed Node.js)"
  fi
fi

if [[ "$WITH_SERVICE" == true ]]; then
  echo "Registration systemd --user memory daemon service..."
  "$CLI" service install || echo "WARN: maind service install failed (see output above)"
fi

# ── live node config from example (if not yet; config.json in .gitignore) ─────
# config.json — general node config in the ROOT monorepo (two levels above the package).
# Fallback on standalone-layout: if there is no monorepo root - batch directory.
CFG_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$CFG_ROOT/packages" ] || CFG_ROOT="$REPO_ROOT"
if [[ ! -f "$CFG_ROOT/config.json" && -f "$CFG_ROOT/config.example.json" ]]; then
  cp "$CFG_ROOT/config.example.json" "$CFG_ROOT/config.json"
  chmod 600 "$CFG_ROOT/config.json"
  echo "Created $CFG_ROOT/config.json from example — edit projects/policy for yourself"
  echo "  (section code_graph — ignores/code graph engine; projects[] — ecosystem nodes)"
fi

# ── code graph (optional, engine Serena via uvx) ─────────────────────────
command -v uvx >/dev/null 2>&1 || \
  echo "INFO: uvx not found in PATH — for code graph (Serena) put uv: https://docs.astral.sh/uv/"

echo ""
echo "Done. Next:"
[[ "$WITH_SERVICE" == true ]] || echo "  maind start --only memory       # increase memory (or: maind service install)"
echo "  maind onboard <path|id>         # connect the project to the ecosystem"
echo "  maind health --cwd              # check link from project directory"
echo "  maind doctor                    # environment diagnostics"
