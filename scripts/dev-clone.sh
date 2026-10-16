#!/usr/bin/env bash
# dev-clone.sh — maintain the development clone of this repository (PLAN3 D10, D13).
#
# Usage:
#   scripts/dev-clone.sh init       mark the clone (.swissknifeman-dev), set upstream; idempotent
#   scripts/dev-clone.sh status     branch, marker, ahead/behind vs origin/main and origin/<branch>
#   scripts/dev-clone.sh sync-main  merge origin/main into the branch (clean tree required)
#
# The marker is untracked (see .gitignore); entry points refuse to run against the real HOME
# while it exists (guard block, D13). This script writes only inside the repository, so it
# carries no guard block.
# Exit: 0 ok, 1 refused (DEV_CLONE_ON_MAIN | DEV_CLONE_DIRTY | DEV_CLONE_CONFLICT), 2 usage.
set -euo pipefail

usage() { echo "usage: dev-clone.sh init|status|sync-main" >&2; exit 2; }
[ $# -eq 1 ] || usage

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
MARKER="$ROOT/.swissknifeman-dev"
BRANCH="$(git symbolic-ref --quiet --short HEAD || echo HEAD)"

# ahead/behind of HEAD relative to REF as "ahead/behind"; "n/a" when the ref is missing.
ahead_behind() {
  local counts
  if counts="$(git rev-list --left-right --count "HEAD...$1" 2>/dev/null)"; then
    printf '%s\n' "$counts" | awk '{print "ahead " $1 " / behind " $2}'
  else
    echo "n/a"
  fi
}

case "$1" in
  init)
    if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
      echo "DEV_CLONE_ON_MAIN: refusing to mark branch '$BRANCH'; check out a development branch first" >&2
      exit 1
    fi
    if [ ! -e "$MARKER" ]; then
      printf 'branch=%s\ncreated=%s\n' "$BRANCH" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER"
    fi
    upstream="n/a"
    if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
      git branch --set-upstream-to="origin/$BRANCH" "$BRANCH" >/dev/null
      upstream="origin/$BRANCH"
    fi
    echo "branch: $BRANCH"
    echo "upstream: $upstream"
    echo "marker: $MARKER"
    ;;
  status)
    changed="$(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
    untracked="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"
    echo "branch: $BRANCH"
    if [ -e "$MARKER" ]; then echo "marker: present"; else echo "marker: absent"; fi
    echo "vs origin/main: $(ahead_behind origin/main)"
    echo "vs origin/$BRANCH: $(ahead_behind "origin/$BRANCH")"
    echo "changed: $changed"
    echo "untracked: $untracked"
    ;;
  sync-main)
    if [ -n "$(git status --porcelain)" ]; then
      echo "DEV_CLONE_DIRTY: working tree is not clean; commit or stash first" >&2
      exit 1
    fi
    git fetch origin
    if ! git merge --no-edit origin/main; then
      echo "DEV_CLONE_CONFLICT: merge of origin/main stopped; resolve these files by hand:" >&2
      git diff --name-only --diff-filter=U >&2
      exit 1
    fi
    ;;
  *) usage ;;
esac
