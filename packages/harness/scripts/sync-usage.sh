#!/usr/bin/env bash
#
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"                 # packages/harness
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"           # swissknifeman root

SRC="$MONOREPO_ROOT/core/usage.py"
DST="$REPO_ROOT/configs/claude-code/hooks/run-report/_usage.py"

[[ -f "$SRC" ]] || { echo "Ошибка: не найден $SRC" >&2; exit 1; }

cp "$SRC" "$DST"
echo "sync-usage: $SRC → $DST"
