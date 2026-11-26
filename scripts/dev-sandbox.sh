#!/usr/bin/env bash
# dev-sandbox.sh — throwaway HOME and project copies for manual checks from the development worktree.
#
# Usage:
#   scripts/dev-sandbox.sh new [--name NAME] [--copy PATH]...   create a sandbox; the last stdout line is its path
#   scripts/dev-sandbox.sh run DIR -- CMD [ARGS...]             run CMD inside the sandbox environment
#   scripts/dev-sandbox.sh list                                 sandboxes in ${TMPDIR:-/tmp}
#   scripts/dev-sandbox.sh remove DIR                           delete a sandbox (marker, location and name are checked)
#
# A sandbox is ${TMPDIR:-/tmp}/skm-sandbox-<name> holding a marker (.skm-sandbox), an isolated home/ (HOME and XDG
# places), env.sh and copies of the projects given with --copy; the originals are never modified.
# Limits: provider CLIs (claude, codex, grok) are not authenticated in a sandbox; it is meant for the CLIs of the
# swissknifeman modules. Live projects are never touched, only their copies.
# This script writes only inside sandboxes, so it carries no guard block.
# Exit: 0 ok, 1 refused (SANDBOX_EXISTS | SANDBOX_INVALID | SANDBOX_COPY), 2 usage.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
PREFIX="skm-sandbox-"
MARKER_NAME=".skm-sandbox"

help_text() { sed -n '2,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }
usage() { help_text >&2; exit 2; }

tmp_root() { readlink -f "${TMPDIR:-/tmp}"; }

refuse() { echo "$1: $2" >&2; exit 1; }

# A sandbox directory is valid when it is a real directory (not a link) that holds the marker file.
require_marker() {
  local dir="$1"
  [ -d "$dir" ] && [ ! -L "$dir" ] && [ -f "$dir/$MARKER_NAME" ] && [ ! -L "$dir/$MARKER_NAME" ] \
    || refuse SANDBOX_INVALID "$dir is not a sandbox (no $MARKER_NAME marker)"
}

cmd_new() {
  local name="" copies=() dir
  while [ $# -gt 0 ]; do
    case "$1" in
      --name) [ $# -ge 2 ] || usage; name="$2"; shift 2 ;;
      --copy) [ $# -ge 2 ] || usage; copies+=("$2"); shift 2 ;;
      *) usage ;;
    esac
  done
  if [ -n "$name" ]; then
    case "$name" in
      *[!A-Za-z0-9._-]* | .* ) refuse SANDBOX_INVALID "name '$name' may hold only letters, digits, '.', '_' and '-'" ;;
    esac
    dir="$(tmp_root)/$PREFIX$name"
    [ ! -e "$dir" ] && [ ! -L "$dir" ] || refuse SANDBOX_EXISTS "$dir already exists"
    mkdir "$dir"
  else
    dir="$(mktemp -d "$(tmp_root)/${PREFIX}XXXXXX")"
  fi
  local home="$dir/home"
  mkdir -p "$home/.config" "$home/.local/state" "$home/.local/share" "$home/.cache" "$home/.local/bin" "$dir/projects"
  printf 'created=%s\nclone=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ROOT" > "$dir/$MARKER_NAME"

  local src base
  for src in "${copies[@]+"${copies[@]}"}"; do
    [ -d "$src" ] || refuse SANDBOX_COPY "--copy $src is not a directory"
    base="$(basename "$(readlink -f "$src")")"
    [ ! -e "$dir/projects/$base" ] || refuse SANDBOX_COPY "two --copy sources share the name '$base'"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude node_modules --exclude vendor --exclude .venv "$src"/ "$dir/projects/$base"/
    else
      cp -a "$src" "$dir/projects/$base"
    fi
  done

  local value key
  for key in user.name user.email; do
    value="$(git config --global "$key" 2>/dev/null || true)"
    [ -z "$value" ] || git config --file "$home/.gitconfig" "$key" "$value"
  done

  {
    printf 'export SKM_SANDBOX=%q\n' "$dir"
    printf 'export HOME=%q\n' "$home"
    echo 'export XDG_CONFIG_HOME="$HOME/.config" XDG_STATE_HOME="$HOME/.local/state" XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"'
    echo 'export SKM_HOME="$HOME/.swissknifeman-home"   # reserved for aicore.state (P4)'
    echo 'export GIT_CONFIG_GLOBAL="$HOME/.gitconfig"'
    printf 'export PATH="$HOME/.local/bin:%s/bin:$PATH"\n' "$(printf '%q' "$ROOT")"
  } > "$dir/env.sh"

  echo "enter the sandbox with: source $dir/env.sh"
  echo "$dir"
}

cmd_run() {
  [ $# -ge 3 ] && [ "$2" = "--" ] || usage
  local dir="$1"; shift 2
  require_marker "$dir"
  local rc=0
  # shellcheck disable=SC1091
  ( . "$dir/env.sh"; "$@" ) || rc=$?
  exit "$rc"
}

cmd_list() {
  [ $# -eq 0 ] || usage
  local dir created projects
  for dir in "$(tmp_root)"/${PREFIX}*; do
    [ -d "$dir" ] && [ ! -L "$dir" ] && [ -f "$dir/$MARKER_NAME" ] || continue
    created="$(sed -n 's/^created=//p' "$dir/$MARKER_NAME")"
    projects="$(ls -1 "$dir/projects" 2>/dev/null | paste -sd, -)"
    printf '%s\tcreated=%s\tprojects=%s\n' "$dir" "$created" "${projects:--}"
  done
}

cmd_remove() {
  [ $# -eq 1 ] || usage
  local arg="$1" real
  [ ! -L "$arg" ] || refuse SANDBOX_INVALID "$arg is a symlink; refusing to remove"
  [ -d "$arg" ] || refuse SANDBOX_INVALID "$arg is not a directory"
  real="$(readlink -f "$arg")"
  [ "$(dirname "$real")" = "$(tmp_root)" ] || refuse SANDBOX_INVALID "$real is not directly inside $(tmp_root)"
  case "$(basename "$real")" in
    ${PREFIX}*) ;;
    *) refuse SANDBOX_INVALID "$real is not named ${PREFIX}*" ;;
  esac
  require_marker "$real"
  rm -rf -- "$real"
  echo "removed $real"
}

[ $# -ge 1 ] || usage
command="$1"; shift
case "$command" in
  new) cmd_new "$@" ;;
  run) cmd_run "$@" ;;
  list) cmd_list "$@" ;;
  remove) cmd_remove "$@" ;;
  -h|--help|help) help_text ;;
  *) usage ;;
esac
