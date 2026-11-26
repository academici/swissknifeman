#!/usr/bin/env bash
# e2e-workspace-plans.sh — end-to-end check of planning a project whose plans live in the portable workspace
# (PLAN6, contract knowledge/workspace-contract): a temporary git project gets the launcher
# (`swissknifeman project init`), the workspace is created and the project is attached (marker
# plans_store=workspace, no plans/ in the checkout). Through the launcher a plan is created, designed, started,
# finished and committed. Checks: `planner plans` sees the plan; the plan folder is under
# $SKM_WORKSPACES_ROOT/axioma/projects/<code>/plans/; the checkout has no plans/; the source commit has the trailer Plan;
# the workspace commit has Plan-Source-Commit; `project context --json` reports plans_store.kind == workspace.
#
# It runs only in temporary folders: HOME, SKM_HOME and SKM_WORKSPACES_ROOT are set to a throwaway directory, so
# neither the real HOME nor the real workspace is touched. Exit 0 and the line "e2e-workspace-plans: OK" when
# everything held; otherwise "e2e-workspace-plans: FAIL ..." and exit 1.
set -euo pipefail

HUB="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
say() { echo "e2e-workspace-plans: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home" SKM_HOME="$WORK/skm" SKM_WORKSPACES_ROOT="$WORK/wss"
export SKM_AICORE_EVENTS__DELIVERY=off
WS_ROOT="$SKM_WORKSPACES_ROOT/axioma"   # the workspace axioma
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_PROJECT_ROOT
unset SKM_LAUNCHER_ACTIVE SKM_LAUNCHER_PID SKM_LAUNCHER_PROJECT_ROOT SKM_LAUNCHER_PATH SKM_LAUNCHER_PROTOCOL SKM_INVOCATION_CWD
# The partners as scripts/test-integration.sh wires them from the hub layout.
export AICORE_ROOT="$HUB/packages/aicore"
export PLANNER_ROOT="$HUB/packages/planner"
export PLANNER_PLAN_PY="$PLANNER_ROOT/scripts/plan.py"
mkdir -p "$HOME" "$WORK/bin"
# The launcher execs `swissknifeman` from PATH: put the umbrella of this checkout there.
ln -s "$HUB/bin/swissknifeman" "$WORK/bin/swissknifeman"
export PATH="$WORK/bin:$PATH"

PROJECT="$WORK/project"
ACTOR="claude-code/claude-opus-5-5/high"
git init -q "$PROJECT"
cd "$PROJECT"
git config user.email e2e@example.invalid
git config user.name e2e
echo base > base.txt
git add base.txt
git commit -q -m "chore: base"

swissknifeman project init >/dev/null || fail "project init"
launch() { python3 -I .swissknifeman/launcher.py "$@"; }
planner() { launch planner "$@"; }

swissknifeman workspace init --code axioma >/dev/null || fail "workspace init"
swissknifeman workspace project attach --project "$PROJECT" --yes >/dev/null || fail "workspace project attach"
grep -q '"plans_store": "workspace"' .swissknifeman/project.json || fail "the marker does not say plans_store=workspace"
[ ! -e plans ] || fail "attach created plans/ in the checkout"

planner new --codename E2E --title "Workspace plans" --repository e2e --actor "$ACTOR" --message "end-to-end check" \
  >/dev/null || fail "planner new"
PLANS_DIR="$(ls -d "$WS_ROOT"/projects/*/plans 2>/dev/null | head -1)"
[ -n "$PLANS_DIR" ] || fail "no plans folder under $WS_ROOT/projects/*/"
PLAN_ID="$(ls "$PLANS_DIR" | grep -v '^\.' | head -1)"
[ -n "$PLAN_ID" ] || fail "no plan folder in $PLANS_DIR"
[ -f "$PLANS_DIR/$PLAN_ID/plan.json" ] || fail "no plan.json in the workspace plan folder"
[ ! -e plans ] || fail "planner new created plans/ in the checkout"

planner add-phase "$PLAN_ID" --title "One" >/dev/null || fail "add-phase"
planner set "$PLAN_ID" P1 --json '{"goal": "g"}' >/dev/null || fail "set phase"
planner add-item "$PLAN_ID" P1 --title "Feature" --json '{"summary": "s", "why": "w", "scope": {"include": ["feature.txt"],
  "exclude": []}, "deliverables": ["d"], "task_files": [{"path": "feature.txt", "change": "any"}],
  "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}' >/dev/null || fail "add-item"
planner design-done "$PLAN_ID" P1 --actor "$ACTOR" >/dev/null || fail "design-done"
planner start "$PLAN_ID" P1.1 --actor "$ACTOR" >/dev/null || fail "start"
echo "the feature" > feature.txt
planner finish "$PLAN_ID" P1.1 --status done --check V1=0 --notes "e2e" --actor "$ACTOR" >/dev/null || fail "finish"
planner commit "$PLAN_ID" P1.1 --role executor --leave-outside --actor "$ACTOR" --json > "$WORK/commit.json" \
  || fail "commit: $(cat "$WORK/commit.json" 2>/dev/null)"

planner plans --json | grep -q "$PLAN_ID" || fail "planner plans does not list $PLAN_ID"
[ ! -e plans ] || fail "the checkout got a plans/ folder"
git log -1 --format=%B | grep -q '^Plan:' || fail "the source commit has no Plan trailer"
git -C "$WS_ROOT" log -1 --format=%B | grep -q '^Plan-Source-Commit: ' \
  || fail "the workspace commit has no Plan-Source-Commit trailer"
SOURCE_SHA="$(git rev-parse HEAD)"
git -C "$WS_ROOT" log -1 --format=%B | grep -q "^Plan-Source-Commit: $SOURCE_SHA" \
  || fail "Plan-Source-Commit does not name the source commit $SOURCE_SHA"
git ls-files --error-unmatch feature.txt >/dev/null 2>&1 || fail "feature.txt was not committed in the source repository"

launch project context --json > "$WORK/context.json" || fail "project context"
python3 - "$WORK/context.json" "$WS_ROOT" <<'PY' || fail "project context does not report the workspace store"
import json, os, sys
doc = json.load(open(sys.argv[1]))
assert doc["plans_store"]["kind"] == "workspace", doc["plans_store"]
assert doc["plans_store"]["reason"] == "marker-workspace", doc["plans_store"]
root = os.path.realpath(sys.argv[2])
assert os.path.realpath(doc["plans_root"]).startswith(os.path.join(root, "projects") + os.sep), doc["plans_root"]
PY

echo "e2e-workspace-plans: OK"
