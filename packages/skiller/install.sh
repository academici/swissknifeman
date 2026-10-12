#!/usr/bin/env bash
# install.sh installs the skiller CLI (formerly swissknifeman).
#
# It creates <bin-dir>/skiller -> <repo>/bin/skiller. connect/vendor/update
# maintain the project registry (projects.json) in the skiller state directory.
#
# The umbrella install.sh owns the `swissknifeman` alias, so rerunning this
# installer never replaces the root router. Standalone installs expose `skiller` only.
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--codex-plugin NAME] [--no-codex-plugins] [--no-grok-plugins]
#
#   --bin-dir DIR   link destination (default: ~/.local/bin)
#   --force         replace a foreign file or link without prompting
#   --codex-plugin  install additional Codex plugin NAME (repeatable)
#   --no-codex-plugins  skip the base core and host command Codex plugins
#   --no-grok-plugins   skip the host Grok plugins
#
# Next - from any consuming project:
#   skiller connect    # Claude Code (plugin marketplace)
#   skiller vendor     # Cursor and other agents (copying skills)
#   skiller update     # update connection of the current project
#   skiller topology   # local environment map (init|show) — is offered during installation
#
# Has the repository moved? Just restart./install.sh from a new location.
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

# --- aicore locator ---
# Finds the aicore foundation: $AICORE_ROOT, then <module>/_vendor/aicore, then the sibling <module>/../aicore.
# Canonical copy: packages/aicore/scripts/aicore-locator.sh; copies must stay identical.
_aicore_ok() { [ -f "$1/unit.json" ] && grep -q '"id": *"aicore"' "$1/unit.json"; }
if [ -n "${AICORE_ROOT:-}" ]; then
  _aicore_ok "$AICORE_ROOT" || { echo "AICORE_NOT_FOUND: AICORE_ROOT=$AICORE_ROOT is not an aicore checkout" >&2; exit 2; }
elif _aicore_ok "$REPO_ROOT/_vendor/aicore"; then
  AICORE_ROOT="$REPO_ROOT/_vendor/aicore"
elif _aicore_ok "$REPO_ROOT/../aicore"; then
  AICORE_ROOT="$(cd "$REPO_ROOT/../aicore" && pwd)"
else
  echo "AICORE_NOT_FOUND: no aicore in \$AICORE_ROOT, $REPO_ROOT/_vendor/aicore or $REPO_ROOT/../aicore; set AICORE_ROOT" >&2
  exit 2
fi
export AICORE_ROOT
AICORE_LIB="$AICORE_ROOT/lib"
unset -f _aicore_ok
# --- end aicore locator ---

CLI="$REPO_ROOT/bin/skiller"
BIN_DIR="$HOME/.local/bin"
FORCE=false
CODEX_PLUGIN_EXTRAS=()
CODEX_PLUGINS_ENABLED=true
CODEX_PLUGIN_EXPLICIT=false
GROK_PLUGINS_ENABLED=true
MARKETPLACE="swissknifeman"

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,19p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --codex-plugin)
      CODEX_PLUGIN_EXTRAS+=("$2")
      CODEX_PLUGIN_EXPLICIT=true
      shift 2 ;;
    --no-codex-plugins) CODEX_PLUGINS_ENABLED=false; shift ;;
    --no-grok-plugins) GROK_PLUGINS_ENABLED=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: install.sh now installs CLI skiller." >&2
      echo "Vending skills to the project: cd <project> && skiller vendor [...]" >&2
      echo "Connection Claude Code:    cd <project> && skiller connect" >&2
      exit 1 ;;
  esac
done

[[ -x "$CLI" ]] || { echo "ERROR: $CLI not found or not executable" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || \
  echo "WARN: python3 not found - CLI will require it at startup" >&2

mkdir -p "$BIN_DIR"
# The project registry is created by skiller on first connect (<state>/skiller/projects.json).

# We install a symlink, silently replacing YOURS (old clone or former name swissknifeman);
# we don't touch someone else's file without --force/confirmation.
install_link() {  # $1 — name in BIN_DIR
  local link="$BIN_DIR/$1"
  if [[ -e "$link" || -L "$link" ]]; then
    local current; current="$(readlink -f "$link" 2>/dev/null || true)"
    if [[ "$current" == */bin/skiller || "$current" == */bin/swissknifeman ]]; then
      : # our symlink (possibly from an old clone/name) — silently replace
    elif [[ "$FORCE" == true ]]; then
      : # explicit permission
    elif [[ -t 0 ]]; then
      read -r -p "$link already exists and is not similar to skiller. Replace? [y/N] " answer
      [[ "$answer" =~ ^[yY] ]] || { echo "Canceled."; exit 1; }
    else
      echo "ERROR: $link already exists - restart with --force" >&2
      exit 1
    fi
  fi
  ln -sfn "$CLI" "$link"
  echo "Installed: $link -> $CLI"
}

install_link skiller          # main CLI (alias swissknifeman — umbrella install.sh)

# Local Environment Map (~/.swissknifeman/topology.json) — machine-specific
# (path to Brain-volta, swissknifeman and project database), is therefore created
# interactive, rather than sitting silently. We suggest setting it up immediately if available. TTY.
if [[ ! -f "$HOME/.swissknifeman/topology.json" && -t 0 ]]; then
  read -r -p "Configure local environment map (skiller topology init)? [y/N] " ans
  [[ "$ans" =~ ^[yY] ]] && "$CLI" topology init || true
fi

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

echo "Check: skiller doctor"

# Host repository (configs/skiller-host.json): the Git root above this package; its
# marketplace serves Codex and Grok. SKILLER_MARKETPLACE_ROOT overrides the marketplace.
HOST_ROOT="$(git -C "$REPO_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$HOST_ROOT" ]] || HOST_ROOT="$REPO_ROOT"
MARKETPLACE_ROOT="${SKILLER_MARKETPLACE_ROOT:-$HOST_ROOT}"

host_python() {  # stdin: python reading the host through skiller modules
  PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}" python3 - "$REPO_ROOT"
}

# Basic `core` + host command plugins — machine bootstrap Codex: after installing the
# umbrella, command plugins should work in any project without manual link/plugin add.
# We take the list from the CORE-policy and the host config, do not duplicate it in shell.
# Profile plugins remain explicit: installing them globally here would bloat
# all Codex-sessions regardless of the project.
if [[ "$CODEX_PLUGINS_ENABLED" == false && "$CODEX_PLUGIN_EXPLICIT" == false ]]; then
  echo "Codex plugins: pass (--no-codex-plugins)"
elif ! command -v codex >/dev/null 2>&1; then
  if [[ "$CODEX_PLUGIN_EXPLICIT" == true ]]; then
    echo "ERROR: codex CLI not found — native install was not attempted" >&2
    exit 1
  fi
  echo "INFO: codex CLI not found - basic Codex-plugins not installed"
else
  [[ -f "$MARKETPLACE_ROOT/.agents/plugins/marketplace.json" ]] || {
    echo "ERROR: Codex marketplace not generated: $MARKETPLACE_ROOT/.agents/plugins/marketplace.json" >&2
    exit 1
  }

  policy_plugins=""
  if [[ "$CODEX_PLUGINS_ENABLED" == true ]]; then
    policy_plugins="$(host_python <<'PY'
from skiller.config import CORE_PLUGIN, default_command_plugins

for plugin in (CORE_PLUGIN, *default_command_plugins()):
    print(plugin)
PY
    )" || {
      echo "ERROR: could not read core plugins from skiller.config" >&2
      exit 1
    }
  fi

  CODEX_PLUGINS=()
  declare -A seen_codex_plugins=()
  while IFS= read -r plugin; do
    [[ -n "$plugin" && -z "${seen_codex_plugins[$plugin]:-}" ]] || continue
    CODEX_PLUGINS+=("$plugin")
    seen_codex_plugins["$plugin"]=1
  done <<< "$policy_plugins"
  for plugin in "${CODEX_PLUGIN_EXTRAS[@]}"; do
    [[ -n "$plugin" && -z "${seen_codex_plugins[$plugin]:-}" ]] || continue
    CODEX_PLUGINS+=("$plugin")
    seen_codex_plugins["$plugin"]=1
  done

  codex plugin marketplace add "$MARKETPLACE_ROOT"
  for plugin in "${CODEX_PLUGINS[@]}"; do
    codex plugin add "$plugin@$MARKETPLACE"
  done
  echo "Codex plugins installed: ${CODEX_PLUGINS[*]}"
fi

# Grok loads plugin slash commands from the installed plugin's commands/ directory.
# Install each host Grok plugin (machine_plugins.grok) by path, then its holds. Do not
# install marketplace `core`: its source is the host root, and `grok plugin install`
# copies the whole directory. Profile plugins stay explicit so they do not bloat every
# Grok session. A second run exits 1 with "already configured" / "already installed";
# that is success.
if [[ "$GROK_PLUGINS_ENABLED" == false ]]; then
  echo "Grok plugins: pass (--no-grok-plugins)"
elif ! command -v grok >/dev/null 2>&1; then
  echo "INFO: grok CLI not found - host grok plugins not installed"
else
  grok_rows="$(host_python <<'PY'
import sys
from pathlib import Path
from skiller.host import load_host

for plugin in load_host(Path(sys.argv[1])).machine_plugins.get("grok", ()):
    print(f"plugin\t{plugin.name}\t{plugin.path}")
    for hold in plugin.holds:
        print(f"hold\t{plugin.name}\t{hold}")
PY
  )" || {
    echo "ERROR: could not read host grok plugins from skiller.host" >&2
    exit 1
  }

  GROK_KINDS=()
  GROK_PATHS=()
  GROK_LABELS=()
  while IFS=$'\t' read -r kind name relative; do
    [[ -n "$kind" ]] || continue
    path="$HOST_ROOT/$relative"
    if [[ "$kind" == plugin ]]; then
      [[ -f "$path/.claude-plugin/plugin.json" ]] || {
        echo "ERROR: Grok plugin $name not found: $path" >&2
        exit 1
      }
      GROK_LABELS+=("$name")
    else
      [[ -f "$path/.grok-plugin/plugin.json" ]] || {
        echo "ERROR: Grok plugin $name hold not found: $path" >&2
        exit 1
      }
      GROK_LABELS+=("$(basename "$path")")
    fi
    GROK_KINDS+=("$kind")
    GROK_PATHS+=("$path")
  done <<< "$grok_rows"

  grok_tolerate() {
    local label="$1"
    shift
    local out rc
    set +e
    out="$("$@" 2>&1)"
    rc=$?
    set -e
    if [[ "$rc" -eq 0 ]]; then
      return 0
    fi
    case "$out" in
      *"already configured"*|*"already installed"*)
        return 0
        ;;
    esac
    echo "ERROR: grok ${label} failed" >&2
    printf '%s\n' "$out" >&2
    exit 1
  }

  if [[ ${#GROK_PATHS[@]} -eq 0 ]]; then
    echo "INFO: no host grok plugins"
  else
    grok_tolerate "marketplace add" grok plugin marketplace add "$MARKETPLACE_ROOT"
    # Grok qualifies a plugin command as /<plugin>:<name> only when that bare
    # name also exists elsewhere. A hold plugin reserves those names, so it is
    # installed right after the plugin it covers.
    for i in "${!GROK_PATHS[@]}"; do
      if [[ "${GROK_KINDS[$i]}" == plugin ]]; then
        grok_tolerate "plugin install" grok plugin install "${GROK_PATHS[$i]}" --trust
      else
        grok_tolerate "hold install" grok plugin install "${GROK_PATHS[$i]}" --trust
      fi
    done
    echo "Grok plugins installed: ${GROK_LABELS[*]}"
  fi
fi
