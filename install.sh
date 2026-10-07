#!/usr/bin/env bash
# install.sh — umbrella monorepo installer.
# Sets CLI packages (skiller, harness, maind), delegating the installation of each of its
# own install.sh (there is a batch post-configuration), plus root
# control layer `swissknifeman` (router + setup-facade above three packages).
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--no-codex-plugins] [--no-grok-plugins]
#   --bin-dir DIR   where to put symlinks (default ~/.local/bin)
#   --force         overwrite other people's symlinks without asking
#   --no-codex-plugins  do not install basic Codex-plugins core + task
#   --no-grok-plugins   do not install the Grok task plugin
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
BIN_DIR="$HOME/.local/bin"
FORCE=false
NO_CODEX_PLUGINS=false
NO_GROK_PLUGINS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force)   FORCE=true; shift ;;
    --no-codex-plugins) NO_CODEX_PLUGINS=true; shift ;;
    --no-grok-plugins) NO_GROK_PLUGINS=true; shift ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,12p'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$BIN_DIR"

# Delegating the installation of batch CLI their own install.sh (there is a batch
# post-configuration: maind — npm/service options; skiller — topology; harness — stateless).
# `task` in the list NOT deliberately: it does not have bin/CLI/install.sh — this plugin-only
# package (only slash-commands), is delivered via marketplace/vendor skiller-channel.
fwd=(); $FORCE && fwd+=(--force); fwd+=(--bin-dir "$BIN_DIR")
echo "Installation CLI packages (bin-dir: $BIN_DIR):"
failed=()  # packages whose install.sh fell - for final status (otherwise «Done» lies)
for pkg in skiller harness maind analyst; do
  inst="$REPO_ROOT/packages/$pkg/install.sh"
  [[ -x "$inst" ]] || continue
  echo "— $pkg:"
  pkg_fwd=("${fwd[@]}")
  if [[ "$pkg" == skiller && "$NO_CODEX_PLUGINS" == true ]]; then
    pkg_fwd+=(--no-codex-plugins)
  fi
  if [[ "$pkg" == skiller && "$NO_GROK_PLUGINS" == true ]]; then
    pkg_fwd+=(--no-grok-plugins)
  fi
  "$inst" "${pkg_fwd[@]}" || { echo "  ($pkg install.sh failed - check manually)" >&2; failed+=("$pkg"); }
done

# Root control layer: symlink `swissknifeman` → bin/swissknifeman (router).
# Placed AFTER the packages - before the alias `swissknifeman` set skiller; now they
# owns an umbrella. Silently replacing our old symlink (on skiller/router); alien -
# only with --force/confirmation.
ROUTER="$REPO_ROOT/bin/swissknifeman"
LINK="$BIN_DIR/swissknifeman"
if [[ -x "$ROUTER" ]]; then
  if [[ -e "$LINK" || -L "$LINK" ]]; then
    current="$(readlink -f "$LINK" 2>/dev/null || true)"
    if [[ "$current" == */bin/swissknifeman || "$current" == */bin/skiller ]]; then
      : # our previous symlink (router or old alias→skiller) — silently replace
    elif [[ "$FORCE" == true ]]; then :;
    elif [[ -t 0 ]]; then
      read -r -p "$LINK already exists and is not similar to ours. Replace? [y/N] " a
      [[ "$a" =~ ^[yY] ]] || { echo "Skip swissknifeman."; ROUTER=""; }
    else
      echo "ATTENTION: $LINK exists - skip (restart with --force)" >&2; ROUTER=""
    fi
  fi
  [[ -n "$ROUTER" ]] && { ln -sfn "$ROUTER" "$LINK"; echo "— swissknifeman: $LINK -> $ROUTER"; }
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "ATTENTION: $BIN_DIR not in PATH — add: export PATH=\"$BIN_DIR:\$PATH\"" >&2 ;;
esac

if (( ${#failed[@]} )); then
  echo "ERROR: packages not installed: ${failed[*]} — installation is incomplete, see log above." >&2
  exit 1
fi
echo "Done. CLI: swissknifeman (router) · skiller · harness · maind · analyst"
