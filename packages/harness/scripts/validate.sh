#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

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

fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/12] python compile"
python3 -m compileall -q lib tests || err "py_compile"

echo "[2/12] vendoring _usage.py (SCHEMA=2 run-report)"
USAGE_DST="configs/claude-code/hooks/run-report/_usage.py"
USAGE_SRC="$AICORE_LIB/aicore/usage.py"
if [[ -f "$USAGE_SRC" ]]; then
  cmp -s "$USAGE_SRC" "$USAGE_DST" \
    || err "vendor _usage.py separated from the aicore usage module — run scripts/sync-usage.sh"
else
  [[ -f "$USAGE_DST" ]] || err "no $USAGE_DST (expected vendor copy)"
fi

echo "[3/12] bash syntax"
for f in bin/harness install.sh scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done
while IFS= read -r -d '' sh; do
  bash -n "$sh" || err "bash -n $sh"
done < <(find configs/claude-code -name '*.sh' -print0)
while IFS= read -r -d '' py; do
  python3 -m py_compile "$py" || err "py_compile $py"
done < <(find configs/claude-code -name '*.py' -print0)

echo "[4/12] JSON (plugin + presets)"
python3 - <<'PY' || err "broken JSON"
import glob, json, sys
bad = []
for f in [".claude-plugin/plugin.json"] + sorted(glob.glob("configs/claude-code/**/*.json", recursive=True)):
    try:
        json.load(open(f, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        bad.append(f"{f}: {e}")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[5/12] required files"
for f in bin/harness lib/harness/__init__.py lib/harness/cli.py \
         scripts/apply-permissions.sh configs/claude-code/settings.base.json \
         .claude-plugin/plugin.json commands/harness.md \
         README.md LICENSE CLAUDE.md; do
  [[ -e "$f" ]] || err "no file: $f"
done

echo "[6/12] slash-commands (frontmatter)"
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

echo "[7/12] package import + tests"
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -c "import harness.cli" \
  || err "lib/harness not imported"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -c "
import sys
from harness.agentpacks import do_doctor
from harness.common import Env
sys.exit(do_doctor(Env('$REPO_ROOT', 'validate')))" || err "agent-packs integrity"
scripts/test.sh || err "tests"

echo "[8/12] generated provider instructions reference"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" \
  python3 scripts/generate-provider-instructions.py --check \
  || err "generated provider instructions reference"

echo "[9/12] role registry review"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -m harness.reviewroles --check \
  || err "role registry review (role-bindings.json)"

echo "[10/12] instruction drift (28 projections)"
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}" python3 -m harness.instructions --check \
  || err "instruction drift (harness instructions check)"

echo "[11/12] rules Cursor (.cursor/rules/*.mdc as directory projection)"
if [[ -n "$MONOREPO_ROOT" ]]; then
  PYTHONPATH="$REPO_ROOT/lib:$MONOREPO_ROOT" python3 scripts/render-cursor-rules.py --check \
    || err "rules Cursor disagreed with the instructions catalog"
else
  echo "  rules Cursor: core/ not found (standalone-layout) — gate skipped"
fi

echo "[12/12] execution policy (execution-policy)"
if [[ -n "$MONOREPO_ROOT" ]]; then
  PYTHONPATH="$REPO_ROOT/lib:$MONOREPO_ROOT" python3 -m harness.execpolicy --check \
    || err "execution policy (execution-policy)"
else
  echo "  execution policy: core/ not found (standalone-layout) — gate skipped"
fi

echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: FAILURE" >&2; exit 1; fi
