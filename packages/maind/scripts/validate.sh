#!/usr/bin/env bash
# Structural maind validation for CI and local use.
# Checks Python compilation, Bash syntax, JSON, required files, command frontmatter,
# and the package test suite.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/6] python compile"
python3 -m compileall -q lib tests || err "py_compile"

echo "[2/6] bash syntax"
for f in bin/maind install.sh scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done

echo "[3/6] JSON configs"
for f in package.json .claude-plugin/plugin.json configs/config.schema.json configs/registry.example.json; do
  [[ -f "$f" ]] && { python3 -m json.tool "$f" >/dev/null || err "broken JSON: $f"; }
done

echo "[4/6] required files"
for f in bin/maind lib/maind/__init__.py lib/maind/cli.py \
         config/memory/iii-config.yaml .env.example \
         .claude-plugin/plugin.json \
         commands/maind.md commands/onboard.md commands/sync.md \
         configs/config.schema.json configs/registry.example.json config.example.toml \
         README.md LICENSE; do
  [[ -e "$f" ]] || err "no file: $f"
done
grep -q '^workers:' config/memory/iii-config.yaml || err "iii-config.yaml without workers:"

echo "[5/6] slash-commands (frontmatter)"
python3 - <<'PY' || err "broken frontmatter in commands/*.md"
import glob, sys
bad = []
for f in sorted(glob.glob("commands/*.md")):
    lines = open(f, encoding="utf-8").read().replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        bad.append(f"{f}: no opening ---"); continue
    fm, closed = {}, False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True; break
        if ":" in ln:
            k, v = ln.split(":", 1); fm[k.strip()] = v.strip()
    if not closed:
        bad.append(f"{f}: frontmatter not closed"); continue
    if not fm.get("description"):
        bad.append(f"{f}: empty/no description")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[6/6] tests"
if [[ -n "${SKM_VALIDATE_SKIP_TESTS:-}" ]]; then
  echo "  skipped (SKM_VALIDATE_SKIP_TESTS: the caller ran them)"
else
  scripts/test.sh
fi

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: FAILURE" >&2; exit 1; fi
