#!/usr/bin/env bash
# generate-hub.sh — generates in the target project the root «hub» skills:
# source reading priorities + search rules + (where needed) skill index.
#
# Thin launcher: all the logic is in lib/skiller/hub.py (importable and testable,
# see tests/test_hub.py), only resolve here PYTHONPATH (aicore locator), as in bin/skiller.
#
# Installation Data Sources (merge):
#   .claude/settings.local.json / settings.json -> enabledPlugins."<bucket>@swissknifeman"
#   .swissknifeman-manifest.json in .claude/skills | .cursor/skills | .ai/skills
#
# Recording modes:
#   project with Laravel Boost (yes boost.json) -> .ai/guidelines/swissknifeman-hub.md
#       (Boost will insert the fragment into CLAUDE.md when `php artisan boost:update`)
#   project without Boost -> managed-block in CLAUDE.md between markers
#       <!-- swissknifeman:hub:start --> ... <!-- swissknifeman:hub:end -->
#       (content outside markers does not change; the file is created if there is no)
#   --root-files A,B -> the same managed-block additionally to the specified root
#       files (for example AGENTS.md,GEMINI.md) — for tools outside Boost. Ignored
#       in mode Boost (there is a source - .ai/guidelines/swissknifeman-hub.md).
#
# Block shape - according to the TARGET CHANNEL (D20 plan):
#   CLAUDE.md and Boost-fragment -> short (the channel has a native listing
#       skills, the index in the block would be the second paid copy);
#   AGENTS.md/GEMINI.md etc. -> full (index - single detection).
#   --full-index                -> full form for all purposes (rollback path).
# The skill is removed from the block only after machine verification «it is also in the set
# meter, and in the native distribution channel»; unconfirmed ones remain in the block.
#
# Usage:
#   ./scripts/generate-hub.sh --target ~/projects/my-app
#   ./scripts/generate-hub.sh --target . --dry-run
#   ./scripts/generate-hub.sh --target . --root-files AGENTS.md,GEMINI.md
#   ./scripts/generate-hub.sh --target . --full-index
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//' | sed -n '2,32p'; exit "${1:-0}"; }

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage 0

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: generate-hub.sh requires python3" >&2
  exit 1
fi

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

exec env PYTHONPATH="$REPO_ROOT/lib:$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m skiller.hub "$REPO_ROOT" "$@"
