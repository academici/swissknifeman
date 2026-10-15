#!/usr/bin/env bash
# lint.sh — the CI lint step, runnable locally (ruff F + B, config in ruff.toml).
# Usage: scripts/lint.sh [ruff args...] [PATH...]   e.g. scripts/lint.sh --statistics
#   An argument that names an existing file or directory is a path to check (e.g. packages/brain/lib): with any path
#   given only those paths are checked; without one the default list below is. Other arguments go to ruff.
#
# ruff is a development tool, not a runtime dependency (packages stay stdlib-only). It is fetched on demand at the
# pinned version, so nothing is installed into the repository. Needs: python3 >= 3.9 and one of
#   - pipx            (apt install pipx | python3 -m pip install --user pipx), or
#   - ruff==$RUFF_VERSION already on PATH (any install method).
# SKM_LINT_ANY_VERSION=1 lets a ruff of another version on PATH run (a warning names it): for a machine where pipx is
# not available (an executor under snap confinement); CI never sets it, so the pinned version still decides there.
# The pinned version and the default path list live only here; scripts/ci-matrix.py calls this script per module.
set -euo pipefail

RUFF_VERSION="0.15.19"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATHS=(packages/aicore/lib packages/aicore/tests
  packages/skiller/lib packages/skiller/tests
  packages/harness/lib packages/harness/tests
  packages/maind/lib packages/maind/tests
  packages/planner/lib packages/planner/tests
  packages/orch/lib packages/orch/tests packages/orch/scripts
  bridges)

cd "$ROOT"
FLAGS=()
GIVEN=()
for arg in "$@"; do
  if [ -e "$arg" ]; then GIVEN+=("$arg"); else FLAGS+=("$arg"); fi
done
[ "${#GIVEN[@]}" -eq 0 ] || PATHS=("${GIVEN[@]}")
if command -v ruff >/dev/null 2>&1 && [ "$(ruff --version | awk '{print $2}')" = "$RUFF_VERSION" ]; then
  exec ruff check ${FLAGS[@]+"${FLAGS[@]}"} "${PATHS[@]}"
elif [ -n "${SKM_LINT_ANY_VERSION:-}" ] && command -v ruff >/dev/null 2>&1; then
  echo "LINT_VERSION_DRIFT: ruff $(ruff --version | awk '{print $2}') is not the pinned $RUFF_VERSION; the result is advisory" >&2
  exec ruff check ${FLAGS[@]+"${FLAGS[@]}"} "${PATHS[@]}"
elif command -v pipx >/dev/null 2>&1; then
  exec pipx run "ruff==$RUFF_VERSION" check ${FLAGS[@]+"${FLAGS[@]}"} "${PATHS[@]}"
fi
echo "LINT_TOOL_MISSING: need pipx or ruff==$RUFF_VERSION on PATH." >&2
echo "  install pipx:  sudo apt install pipx   (or: python3 -m pip install --user pipx)" >&2
echo "  or ruff:       python3 -m pip install --user ruff==$RUFF_VERSION" >&2
exit 2
