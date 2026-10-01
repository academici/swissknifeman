#!/usr/bin/env bash
# install.sh installs the skiller CLI (formerly swissknifeman).
#
# It creates <bin-dir>/skiller -> <repo>/bin/skiller and the ~/.swissknifeman
# state directory. connect/vendor/update maintain projects.json.
#
# The umbrella install.sh owns the `swissknifeman` alias, so rerunning this
# installer never replaces the root router. Standalone installs expose `skiller` only.
#
# Usage:
#   ./install.sh [--bin-dir DIR] [--force] [--codex-plugin NAME] [--no-codex-plugins]
#
#   --bin-dir DIR   link destination (default: ~/.local/bin)
#   --force         replace a foreign file or link without prompting
#   --codex-plugin  install additional Codex plugin NAME (repeatable)
#   --no-codex-plugins  skip the base core and task Codex plugins
#
# Next - from any consuming project:
#   skiller connect    # Claude Code (plugin marketplace)
#   skiller vendor     # Cursor and other agents (copying skills)
#   skiller update     # update connection of the current project
#   skiller topology   # local environment map (init|show) — is offered during installation
#
# Has the repository moved? Just restart./install.sh from a new location.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$REPO_ROOT/bin/skiller"
BIN_DIR="$HOME/.local/bin"
FORCE=false
CODEX_PLUGIN_EXTRAS=()
CODEX_PLUGINS_ENABLED=true
CODEX_PLUGIN_EXPLICIT=false
MARKETPLACE="swissknifeman"

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed -n '2,18p'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir) BIN_DIR="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    --codex-plugin)
      CODEX_PLUGIN_EXTRAS+=("$2")
      CODEX_PLUGIN_EXPLICIT=true
      shift 2 ;;
    --no-codex-plugins) CODEX_PLUGINS_ENABLED=false; shift ;;
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

mkdir -p "$BIN_DIR" "$HOME/.swissknifeman"
[[ -f "$HOME/.swissknifeman/projects.json" ]] || \
  printf '{\n  "version": 1,\n  "projects": []\n}\n' > "$HOME/.swissknifeman/projects.json"

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

# Basic `core` + `task` — machine bootstrap Codex: after installing the umbrella
# TASK-commands should work in any project without manual link/plugin add.
# We take the list from the declarative CORE-policy, do not duplicate it in shell.
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
  MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"
  [[ -f "$MONOREPO_ROOT/.agents/plugins/marketplace.json" ]] || {
    echo "ERROR: Codex marketplace not generated: $MONOREPO_ROOT/.agents/plugins/marketplace.json" >&2
    exit 1
  }

  policy_plugins=""
  if [[ "$CODEX_PLUGINS_ENABLED" == true ]]; then
    policy_plugins="$(
      PYTHONPATH="$REPO_ROOT/lib:$MONOREPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 - <<'PY'
from skiller.config import CORE_PLUGIN, DEFAULT_COMMAND_PLUGINS

for plugin in (CORE_PLUGIN, *DEFAULT_COMMAND_PLUGINS):
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

  codex plugin marketplace add "$MONOREPO_ROOT"
  for plugin in "${CODEX_PLUGINS[@]}"; do
    codex plugin add "$plugin@$MARKETPLACE"
  done
  echo "Codex plugins installed: ${CODEX_PLUGINS[*]}"
fi
