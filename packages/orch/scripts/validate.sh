#!/usr/bin/env bash
set -euo pipefail
ORCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ORCH_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/6] python compile"
python3 -m compileall -q lib tests scripts || err "py_compile"

echo "[2/6] bash syntax"
for script in scripts/*.sh; do
  bash -n "$script" || err "bash -n $script"
done

echo "[3/6] required files"
for path in README.md scripts/orch.py scripts/test.sh scripts/validate.sh \
            lib/orch/__init__.py lib/orch/schema.py lib/orch/contracts.py lib/orch/cli.py \
            schemas/exec/v1/defs.schema.json tests/__init__.py \
            tests/test_schema_profile.py tests/test_boundaries.py tests/test_cli_validate.py; do
  [[ -f "$path" ]] || err "no file: $path"
done

echo "[4/6] schemas load"
PYTHONPATH=lib python3 -c 'from orch.contracts import load_registry; load_registry()' \
  || err "schema registry"

echo "[5/6] fixtures"
shopt -s nullglob
for category in valid invalid; do
  directory="fixtures/exec/v1/$category"
  if [[ ! -d "$directory" ]]; then
    echo "  skipped (no directory): $directory"
    continue
  fi
  for fixture in "$directory"/*/*.json; do
    kind="$(basename "$(dirname "$fixture")")"
    status=0
    python3 scripts/orch.py validate "$kind" "$fixture" --quiet || status=$?
    expected=0
    [[ "$category" == valid ]] || expected=1
    [[ "$status" -eq "$expected" ]] || err "$fixture: exit $status, expected $expected"
  done
done

echo "[6/6] tests"
bash scripts/test.sh || err "unittest"

if [[ "$fail" -eq 0 ]]; then
  echo "validate: OK"
else
  echo "validate: FAILURE" >&2
  exit 1
fi
