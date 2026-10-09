#!/usr/bin/env bash
# validate.sh — structural checks of the brain package (CI and local).
# Checks: Python compilation, bash syntax, JSON files, required files, the generated config example,
# the version sources, then the tests (scripts/test.sh).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/6] python compile"
python3 -m compileall -q lib tests || err "py_compile"

echo "[2/6] bash syntax"
for f in bin/brain scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done

echo "[3/6] JSON files"
for f in unit.json configs/config.schema.json tests/fixtures/vault/.obsidian/app.json; do
  python3 -m json.tool "$f" >/dev/null || err "broken JSON: $f"
done

echo "[4/6] required files"
for f in bin/brain lib/brain/__init__.py lib/brain/__main__.py lib/brain/cli.py lib/brain/errors.py \
         lib/brain/settings.py lib/brain/frontmatter.py lib/brain/vault.py lib/brain/catalog.py \
         lib/brain/doctor.py lib/brain/docs.py configs/config.schema.json config.example.toml unit.json README.md \
         CHANGELOG.md LICENSE; do
  [[ -e "$f" ]] || err "no file: $f"
done

echo "[5/6] config example and version"
# The aicore locator of bin/brain, reused here to find the foundation.
_aicore_ok() { [ -f "$1/unit.json" ] && grep -q '"id": *"aicore"' "$1/unit.json"; }
if [ -n "${AICORE_ROOT:-}" ]; then AICORE="$AICORE_ROOT"
elif _aicore_ok "$REPO_ROOT/_vendor/aicore"; then AICORE="$REPO_ROOT/_vendor/aicore"
elif _aicore_ok "$REPO_ROOT/../aicore"; then AICORE="$(cd "$REPO_ROOT/../aicore" && pwd)"
else echo "  FAIL: no aicore found; set AICORE_ROOT" >&2; exit 2; fi
PYTHONPATH="$AICORE/lib" python3 -m aicore config example "$REPO_ROOT" --check >/dev/null \
  || err "config.example.toml is stale: run python3 -m aicore config example packages/brain --write"
python3 - <<'PY' || err "version mismatch between unit.json and lib/brain/__init__.py"
import json, re, sys
unit = json.load(open("unit.json", encoding="utf-8"))["version"]
code = re.search(r'__version__\s*=\s*"([^"]+)"', open("lib/brain/__init__.py", encoding="utf-8").read()).group(1)
sys.exit(0 if unit == code else 1)
PY

echo "[6/6] tests"
scripts/test.sh

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: FAILURE" >&2; exit 1; fi
