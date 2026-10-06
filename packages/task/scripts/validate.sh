#!/usr/bin/env bash
# validate.sh — package structural checks task (CI + locally). Checks: compilation Python (lib/tests/scripts),
# syntax bash (scripts/*.sh), required files, frontmatter slash-commands
# (description/model/effort — task kicks the model/effort each command), unittest
# (including the plan engine tests/engine), and - for selected plans or the fleet -
# `scripts/plan.py check` on every directory that holds a plan.json (layout v4).
# Directories without plan.json are skipped; absence of plans/ is not an error.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plan_targets=()
fleet=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan) [[ $# -ge 2 ]] || { echo "--plan requires path" >&2; exit 2; }
      plan_targets+=("$(realpath "$2")"); shift 2 ;;
    --fleet) fleet=true; shift ;;
    -h|--help) echo "validate.sh [--plan PATH ...] [--fleet] — package; selected plans or CI/release fleet"; exit 0 ;;
    *) echo "Unknown parameter: $1" >&2; exit 2 ;;
  esac
done
cd "$REPO_ROOT"
fail=0
err() { echo "  FAIL: $*" >&2; fail=1; }

echo "[1/6] python compile"
python3 -m compileall -q lib tests scripts || err "py_compile"

echo "[2/6] bash syntax"
for f in scripts/*.sh; do
  bash -n "$f" || err "bash -n $f"
done

echo "[3/6] required files"
for f in .claude-plugin/plugin.json lib/task/__init__.py lib/task/plan/__init__.py \
         scripts/plan.py schemas/plan/v1/item.schema.json commands/design.md; do
  [[ -e "$f" ]] || err "no file: $f"
done

echo "[4/6] slash-commands (frontmatter: description/model/effort)"
python3 - <<'PY' || err "broken frontmatter in commands/*.md"
import glob, sys

VALID_MODELS = {"opus", "sonnet", "haiku"}
VALID_EFFORTS = {"low", "medium", "high", "xhigh"}
bad = []
for f in sorted(glob.glob("commands/*.md")):
    lines = open(f, encoding="utf-8").read().replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        bad.append(f"{f}: no opening ---")
        continue
    fm, closed = {}, False
    for ln in lines[1:]:
        if ln.strip() == "---":
            closed = True
            break
        if ":" in ln:
            k, v = ln.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    if not closed:
        bad.append(f"{f}: frontmatter not closed")
        continue
    if not fm.get("description"):
        bad.append(f"{f}: empty/no description")
    # plan-run.md intentionally WITHOUT model/effort — inherits the session, the only exception is
    if f not in {"commands/plan-run.md", "commands/review.md", "commands/plan-audit.md"}:
        if fm.get("model") not in VALID_MODELS:
            bad.append(f"{f}: model «{fm.get('model')}» not from {sorted(VALID_MODELS)}")
        if fm.get("effort") not in VALID_EFFORTS:
            bad.append(f"{f}: effort «{fm.get('effort')}» not from {sorted(VALID_EFFORTS)}")
    elif fm.get("model") or fm.get("effort"):
        bad.append(f"{f}: model/effort must remain inherited or explicitly reviewer-selected")
for b in bad:
    print("  FAIL:", b, file=sys.stderr)
sys.exit(1 if bad else 0)
PY

echo "[5/6] tests (incl. plan engine) + plan.py check on selected plans"
# lib/ — package task; MONOREPO_ROOT (two levels above the package) — to optional
# was imported core (command_render / session_context use it with a fallback).
MONOREPO_ROOT="$(cd "$REPO_ROOT/../.." 2>/dev/null && pwd || true)"
[ -d "$MONOREPO_ROOT/core" ] || MONOREPO_ROOT=""
PYTHONPATH="$REPO_ROOT/lib${MONOREPO_ROOT:+:$MONOREPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest discover -s tests -p "test_*.py" || err "unittest"

if $fleet && [[ -n "$MONOREPO_ROOT" && -d "$MONOREPO_ROOT/plans" ]]; then
  plan_targets+=("$MONOREPO_ROOT/plans")
fi
PYTHONPATH="$REPO_ROOT/lib${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest discover -s tests/engine -p "test_*.py" || err "engine unittest"

# Named bridges carry their own tests; an empty or missing bridges/ directory is skipped.
for bridge_tests in bridges/*/tests; do
  [[ -d "$bridge_tests" ]] || continue
  PYTHONPATH="$REPO_ROOT/lib${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m unittest discover -s "$bridge_tests" -t "$bridge_tests" -p "test_*.py" || err "bridge unittest $bridge_tests"
done

# A target is a plan directory (holds plan.json) or a plans/ root of such directories.
plan_dirs=()
for plan_target in ${plan_targets[@]+"${plan_targets[@]}"}; do
  if [[ -f "$plan_target/plan.json" ]]; then
    plan_dirs+=("$plan_target")
  else
    found=false
    for d in "$plan_target"/*/ "$plan_target"/archive/*/; do
      [[ -f "${d}plan.json" ]] && { plan_dirs+=("${d%/}"); found=true; }
    done
    $found || echo "  skipped (no plan.json, layout v2 or empty): $plan_target"
  fi
done
for plan_dir in ${plan_dirs[@]+"${plan_dirs[@]}"}; do
  python3 scripts/plan.py check "$plan_dir" || err "plan.py check $plan_dir"
done
if [[ ${#plan_targets[@]} -eq 0 ]]; then
  echo "  plan check not requested; --plan PATH for the task, --fleet for CI/release"
fi

# P0.7 — parity of provider projections of teams was maintained only by unit-tests; gate
# of the generator also covers claude-golden and publication-lock.

echo "[5b/6] publication version ↔ umbrella ↔ manifests"
if [[ -n "$MONOREPO_ROOT" ]]; then
  python3 "$REPO_ROOT/scripts/check-publication-version.py" "$MONOREPO_ROOT" \
    || err "publication version drift — bump plugin_version + render-provider-commands"
fi

echo "[6/6] provider command projections (render-provider-commands --check)"
if [[ -n "$MONOREPO_ROOT" ]]; then
  python3 scripts/render-provider-commands.py --check --root "$MONOREPO_ROOT" \
    || err "team projections diverged from canon - python3 packages/task/scripts/render-provider-commands.py --write --root ."
else
  echo "  command projections: monorepo root not found (standalone-layout) — gate skipped"
fi


echo ""
if [[ "$fail" -eq 0 ]]; then echo "validate: OK"; else echo "validate: FAILURE" >&2; exit 1; fi
