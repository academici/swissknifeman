#!/usr/bin/env bash
# validate.sh — package structural checks analyst (CI + locally).
# Checks: compilation Python, syntax bash, validity JSON, presence of key
# files, frontmatter slash-commands, and runs tests (scripts/test.sh).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/6] python compile"
python3 -m compileall -q lib tests || err "py_compile"

echo "[2/6] bash syntax"
for f in bin/analyst scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done

echo "[3/6] JSON configs"
for f in .claude-plugin/plugin.json; do
  [[ -f "$f" ]] && { python3 -m json.tool "$f" >/dev/null || err "broken JSON: $f"; }
done

echo "[4/6] required files"
for f in bin/analyst lib/analyst/__init__.py lib/analyst/cli.py lib/analyst/common.py \
         .claude-plugin/plugin.json commands/analyst.md README.md LICENSE; do
  [[ -e "$f" ]] || err "no file: $f"
done

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
