#!/usr/bin/env bash
# Run the dependency-free aicore unittest suite.
# Usage: scripts/test.sh [-v] (`-v` enables detailed unittest output).
# Tests run against a throwaway HOME and never touch the real one. This runner is also
# the standalone entry point of the module (no monorepo files are needed).
set -euo pipefail
if [[ $# -gt 1 || ( $# -eq 1 && "${1:-}" != "-v" ) ]]; then
  echo "ERROR: unsupported test runner arguments; usage: scripts/test.sh [-v]" >&2
  exit 2
fi
# Tests run in parallel worker processes when the foundation (aicore) is importable; plain unittest otherwise.
# SKM_TEST_JOBS=1 gives the old sequential run.
_unittest() {
  if python3 -c "import aicore.util.par_unittest" 2>/dev/null; then python3 -m aicore.util.par_unittest "$@"; else python3 -m unittest "$@"; fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: tests require python3" >&2
  exit 1
fi

# lib/ holds the aicore package; REPO_ROOT makes the tests package importable.
export PYTHONPATH="$REPO_ROOT/lib:$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
export HOME="$TEST_HOME"
export SKM_CONTRACTS_STRICT=1  # an event or progress line that breaks its schema fails the test instead of being reported
# The location tests must not see the developer's real XDG places or a sandbox override.
unset SKM_HOME SKM_WORKSPACES SKM_WORKSPACES_ROOT SKM_WORKSPACE XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_UNITS_PATH

verbose=""
[[ "${1:-}" == "-v" ]] && verbose="-v"

cd "$REPO_ROOT"
if [[ -n "$verbose" ]]; then
  _unittest discover -s tests -t . -p "test_*.py" -v
else
  out="$(_unittest discover -s tests -t . -p "test_*.py" 2>&1)" || {
    echo "$out" >&2
    echo "ERROR: tests failed" >&2
    exit 1
  }
  echo "tests: OK ($(echo "$out" | grep -oE 'Ran [0-9]+ tests' | head -1))"
fi
