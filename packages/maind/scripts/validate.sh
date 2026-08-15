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

echo "[3/6] JSON конфиги"
# marketplace.json and config.example.json live at the monorepo root.
for f in package.json .claude-plugin/plugin.json; do
  [[ -f "$f" ]] && { python3 -m json.tool "$f" >/dev/null || err "битый JSON: $f"; }
done
# config.example.json is the hub configuration template at the monorepo root.
CFG_EXAMPLE="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || echo "$REPO_ROOT")/config.example.json"
[[ -f "$CFG_EXAMPLE" ]] && { python3 -m json.tool "$CFG_EXAMPLE" >/dev/null || err "битый JSON: config.example.json"; }

echo "[4/6] обязательные файлы"
for f in bin/maind lib/maind/__init__.py lib/maind/cli.py \
         config/memory/iii-config.yaml .env.example \
         .claude-plugin/plugin.json \
         commands/maind.md commands/onboard.md commands/sync.md \
         README.md LICENSE; do
  [[ -e "$f" ]] || err "нет файла: $f"
done
# config.example.json is required but lives at the monorepo root.
[[ -e "$CFG_EXAMPLE" ]] || err "нет файла: config.example.json (корень монорепо)"
grep -q '^workers:' config/memory/iii-config.yaml || err "iii-config.yaml без workers:"

echo "[5/6] slash-команды (frontmatter)"
python3 - <<'PY' || err "битый frontmatter в commands/*.md"
import glob, sys
bad = []
for f in sorted(glob.glob("commands/*.md")):
    lines = open(f, encoding="utf-8").read().replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        bad.append(f"{f}: нет открывающего ---"); continue
    fm, closed = {}, False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True; break
        if ":" in ln:
            k, v = ln.split(":", 1); fm[k.strip()] = v.strip()
    if not closed:
        bad.append(f"{f}: frontmatter не закрыт"); continue
    if not fm.get("description"):
        bad.append(f"{f}: пустой/нет description")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[6/6] тесты"
scripts/test.sh

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: ПРОВАЛ" >&2; exit 1; fi
