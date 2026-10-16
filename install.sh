#!/usr/bin/env bash
# install.sh — umbrella monorepo installer.
# Thin wrapper over `swissknifeman install --profile full`: every module of the hub is
# installed by its own installer (provides.install) or gets cli symlinks, then the root
# `swissknifeman` symlink. Profiles and the logic live in the umbrella (configs/install-profiles.json).
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--no-codex-plugins] [--no-grok-plugins]
#   --bin-dir DIR   where to put symlinks (default ~/.local/bin)
#   --force         overwrite other people's symlinks without asking
#   --no-codex-plugins  do not install basic Codex-plugins core + planner
#   --no-grok-plugins   do not install the Grok planner plugin
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
args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) [[ $# -ge 2 ]] || { echo "ERROR: --bin-dir needs a value" >&2; exit 1; }; BIN_DIR="$2"; shift 2 ;;
    --force)   args+=(--force); shift ;;
    --no-codex-plugins) args+=(--option skiller=--no-codex-plugins); shift ;;
    --no-grok-plugins) args+=(--option skiller=--no-grok-plugins); shift ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,12p'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 1 ;;
  esac
done

# Stop before touching the machine when a required program is missing (bash 4+, python3 3.9+, git, writable
# config/state dirs); recommended items only warn. SKM_SKIP_ENV_CHECK=1 skips the check.
if [[ "${SKM_SKIP_ENV_CHECK:-}" != 1 && -x "$REPO_ROOT/scripts/check-env.sh" ]]; then
  "$REPO_ROOT/scripts/check-env.sh" --quiet --bin-dir "$BIN_DIR" || {
    echo "ERROR: install stopped: fix the required items above (scripts/check-env.sh) or set SKM_SKIP_ENV_CHECK=1" >&2
    exit 1
  }
fi

exec "$REPO_ROOT/bin/swissknifeman" install --profile full --bin-dir "$BIN_DIR" ${args[@]+"${args[@]}"}
