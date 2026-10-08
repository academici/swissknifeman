#!/usr/bin/env bash
# lint.sh — the CI lint step, runnable locally (ruff F + B, config in ruff.toml).
# Usage: scripts/lint.sh [ruff args...]   e.g. scripts/lint.sh --statistics
#
# ruff is a development tool, not a runtime dependency (packages stay stdlib-only). It is fetched on demand at the
# pinned version, so nothing is installed into the repository. Needs: python3 >= 3.9 and one of
#   - pipx            (apt install pipx | python3 -m pip install --user pipx), or
#   - ruff==$RUFF_VERSION already on PATH (any install method).
# The pinned version and the path list live only here; .github/workflows/test.yml calls this script.
set -euo pipefail

RUFF_VERSION="0.15.19"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATHS=(core/ core/tests
  packages/aicore/lib packages/aicore/tests
  packages/skiller/lib packages/skiller/tests
  packages/harness/lib packages/harness/tests
  packages/maind/lib packages/maind/tests
  packages/task/lib packages/task/tests)

cd "$ROOT"
if command -v ruff >/dev/null 2>&1 && [ "$(ruff --version | awk '{print $2}')" = "$RUFF_VERSION" ]; then
  exec ruff check "$@" "${PATHS[@]}"
elif command -v pipx >/dev/null 2>&1; then
  exec pipx run "ruff==$RUFF_VERSION" check "$@" "${PATHS[@]}"
fi
echo "LINT_TOOL_MISSING: need pipx or ruff==$RUFF_VERSION on PATH." >&2
echo "  install pipx:  sudo apt install pipx   (or: python3 -m pip install --user pipx)" >&2
echo "  or ruff:       python3 -m pip install --user ruff==$RUFF_VERSION" >&2
exit 2
