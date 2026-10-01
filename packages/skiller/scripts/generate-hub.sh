#!/usr/bin/env bash
# generate-hub.sh — generates in the target project the root «hub» skills:
# source reading priorities + search rules + (where needed) skill index.
#
# Thin launcher: all the logic is in lib/skiller/hub.py (importable and testable,
# see tests/test_hub.py), only resolve here PYTHONPATH, as in bin/skiller.
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

# Root monorepo (two levels above the package) gives the package `core`; in standalone-
# directory layout core is not nearby - the path is not added (the same technique as in
# bin/skiller: core not yet PYTHONPATH, therefore resolve on bash-side).
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""

exec env PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m skiller.hub "$REPO_ROOT" "$@"
