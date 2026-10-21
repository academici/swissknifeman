#!/usr/bin/env bash
# install.sh — sets CLI maind.
#
# Creates a symlink <bin-dir>/maind -> <repo>/bin/maind. The node registries (registry.json,
# agents.json) live in the swissknifeman state directory and are created by the CLI on first write.
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--with-memory] [--with-service] [--no-shell-env]
#
#   --bin-dir DIR   where to put the symlink (default ~/.local/bin)
#   --force         replace someone else's file/symlink without question
#   --with-memory   npm install at the root maind (memory daemon @agentmemory/agentmemory)
#   --with-service  register memory daemon as systemd --user service
#                   (maind service install — autorun + auto-restart)
#   --no-shell-env  do not add the SKM environment snippet (SKM_HOME, SKM_WORKSPACES, SKM_WORKSPACE) to the shell profile
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
SHELL_ENV_ENABLED=true

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,19p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --with-memory) WITH_MEMORY=true; shift ;;
    --with-service) WITH_SERVICE=true; shift ;;
    --no-shell-env) SHELL_ENV_ENABLED=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI not found or not executable" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 not found - CLI will require it at startup" >&2

mkdir -p "$BIN_DIR"

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

# ── SKM environment variables in the shell profile ───────────────────────
# SKM_HOME, SKM_WORKSPACES and SKM_WORKSPACE for the shell and the agent's Bash: a managed, idempotent snippet written by
# `aicore shell-env install` (the names are one table in aicore). aicore is looked up like the locator of the other modules
# (AICORE_ROOT, then _vendor/aicore, then the sibling aicore) but its absence only skips the step: maind installs alone.
if [[ "$SHELL_ENV_ENABLED" == true && "${SKM_NO_SHELL_ENV:-}" != 1 ]]; then
  _aicore_cli=""
  for _aicore_dir in "${AICORE_ROOT:-}" "$REPO_ROOT/_vendor/aicore" "$REPO_ROOT/../aicore"; do
    if [[ -n "$_aicore_dir" && -x "$_aicore_dir/bin/aicore" ]]; then _aicore_cli="$_aicore_dir/bin/aicore"; break; fi
  done
  if [[ -z "$_aicore_cli" ]]; then
    echo "INFO: aicore not found - the SKM environment snippet was not added to the shell profile"
  else
    "$_aicore_cli" shell-env install || \
      echo "WARN: the SKM environment snippet was not added to the shell profile (see above); retry: aicore shell-env install" >&2
  fi
  unset _aicore_cli _aicore_dir
fi

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

# ── fleet registry from the example (only when no registry source exists yet) ───────
# registry.json lives in the swissknifeman state directory (<machine home>/state: SKM_HOME or
# ~/.local/share/swissknifeman, with the old XDG state folder while it is the only one, as aicore.state).
# A legacy node file (config.json in the ROOT monorepo, two levels above the package) is still a
# source until `swissknifeman upgrade`; it is never copied or replaced here.
# Settings (code graph policy, memory ports, ...) are the [maind] table of config.toml, see
# config.example.toml.
# The monorepo root is looked up only when this package sits in a hub checkout (a folder packages/<id>); from a plugin
# cache copy the parents are not ours and are never read.
CFG_ROOT="$REPO_ROOT"
# --- checkout root ---
if [ "$(basename "$(dirname "$REPO_ROOT")")" = packages ]; then
  CFG_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"
fi
# --- end checkout root ---
if [[ -n "${SKM_HOME:-}" ]]; then
  STATE_DIR="$SKM_HOME/state"
else
  # the machine home is ~/.local/share/swissknifeman; the old XDG state folder is kept while the new one does not exist
  STATE_DIR="$HOME/.local/share/swissknifeman/state"
  _old_state="${XDG_STATE_HOME:-}"
  [[ "$_old_state" == /* ]] || _old_state="$HOME/.local/state"
  if [[ ! -e "$STATE_DIR" && -e "$_old_state/swissknifeman" ]]; then
    STATE_DIR="$_old_state/swissknifeman"
  fi
fi
REGISTRY="$STATE_DIR/maind/registry.json"
if [[ ! -f "$REGISTRY" && ! -f "$CFG_ROOT/config.json" && ! -f "$CFG_ROOT/.maind.json" \
      && ! -f "$REPO_ROOT/.maind.json" && ! -d "$HOME/.maind" \
      && -f "$REPO_ROOT/configs/registry.example.json" ]]; then
  mkdir -p "$STATE_DIR/maind"
  cp "$REPO_ROOT/configs/registry.example.json" "$REGISTRY"
  chmod 600 "$REGISTRY"
  echo "Created $REGISTRY from example — edit projects/namespaces for yourself"
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
