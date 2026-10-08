#!/usr/bin/env bash
#
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"                 # packages/harness
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"           # swissknifeman root

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

# Until the code moves into aicore, fall back to the legacy core location.
SRC="$AICORE_LIB/aicore/usage.py"
[[ -f "$SRC" ]] || SRC="$MONOREPO_ROOT/core/usage.py"
DST="$REPO_ROOT/configs/claude-code/hooks/run-report/_usage.py"

[[ -f "$SRC" ]] || { echo "Error: not found $SRC" >&2; exit 1; }

cp "$SRC" "$DST"
echo "sync-usage: $SRC → $DST"
