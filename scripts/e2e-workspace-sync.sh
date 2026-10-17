#!/usr/bin/env bash
# e2e-workspace-sync.sh — end-to-end check of `workspace sync` between two machines (PLAN6 P4, contract
# knowledge/workspace-contract#sync). Machine A and machine B are two SKM_HOME and two workspace roots on one bare remote:
#   A: a temporary project with two plans, workspace init, migrate apply, connect the bare remote, sync --push.
#   B: workspace clone, project scan, the planner sees the plans of A.
# Then: A and B change different plans and both converge without a conflict; A and B append to the log.jsonl of one plan and
# the union driver merges it; A and B change the same item file: B gets WORKSPACE_CONFLICT with the ref of the item, the
# working tree and HEAD of B stay as they were, `--resolve <path>=remote` (in parts) merges and `--push` publishes it, A pulls
# it and both machines are at the same commit.
#
# It runs only in temporary folders: HOME, SKM_HOME and SKM_WORKSPACE_ROOT are set to a throwaway directory per machine, so
# neither the real HOME nor a real workspace is touched. Exit 0 and the line "e2e-workspace-sync: OK" when everything held;
# otherwise "e2e-workspace-sync: FAIL ..." and exit 1.
set -euo pipefail

HUB="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
say() { echo "e2e-workspace-sync: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export SKM_AICORE_EVENTS__DELIVERY=off
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_PROJECT_ROOT SKM_HOME SKM_WORKSPACE_ROOT
unset SKM_LAUNCHER_ACTIVE SKM_LAUNCHER_PID SKM_LAUNCHER_PROJECT_ROOT SKM_LAUNCHER_PATH SKM_LAUNCHER_PROTOCOL SKM_INVOCATION_CWD
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export AICORE_ROOT="$HUB/packages/aicore"
export PLANNER_ROOT="$HUB/packages/planner"
export PLANNER_PLAN_PY="$PLANNER_ROOT/scripts/plan.py"
mkdir -p "$WORK/bin"
ln -s "$HUB/bin/swissknifeman" "$WORK/bin/swissknifeman"
export PATH="$WORK/bin:$PATH"

A="$WORK/a/project"
B="$WORK/b/project"
REMOTE="$WORK/remote.git"
URL="file://$REMOTE"
ACTOR="claude-code/claude-opus-5-5/high"

machine() {  # machine a|b: the environment and the checkout of that machine
  export HOME="$WORK/home-$1" SKM_HOME="$WORK/skm-$1" SKM_WORKSPACE_ROOT="$WORK/ws-$1"
  mkdir -p "$HOME"
  cd "$WORK/$1/project"
}
launch() { python3 -I .swissknifeman/launcher.py "$@"; }
planner() { launch planner "$@"; }
ws() { swissknifeman workspace "$@"; }
json() { python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1]))
for key in sys.argv[2].split("."):
    d = d[int(key)] if isinstance(d, list) else d[key]
print(json.dumps(d) if isinstance(d, (dict, list)) else d)' "$@"; }
head_of() { git -C "$1" rev-parse HEAD; }

# ----------------------------------------------------------------------------------------------- machine A: the project
mkdir -p "$A" "$WORK/b"
git init -q "$A"
machine a
git config user.email e2e@example.invalid
git config user.name e2e
echo base > base.txt
git add base.txt
git commit -q -m "chore: base"
swissknifeman project init >/dev/null || fail "A: project init"
swissknifeman config set --machine aicore.plugins.workspace-planner.manifest "$HUB/bridges/workspace-planner/extension.json" \
  >/dev/null || fail "A: config set manifest"
swissknifeman config set --machine aicore.plugins.workspace-planner.trusted true >/dev/null || fail "A: config set trusted"

for CODE in SYNCA SYNCB; do
  planner new --codename "$CODE" --title "Sync $CODE" --repository e2e --actor "$ACTOR" --message "sync e2e" \
    >/dev/null || fail "A: planner new $CODE"
done
PLAN_A="$(ls plans | grep -- '-SYNCA$' | head -1)"
PLAN_B="$(ls plans | grep -- '-SYNCB$' | head -1)"
[ -n "$PLAN_A" ] && [ -n "$PLAN_B" ] || fail "A: the two plans were not created: $(ls plans)"
for PLAN in "$PLAN_A" "$PLAN_B"; do
  planner add-phase "$PLAN" --title "One" >/dev/null || fail "A: add-phase $PLAN"
  planner set "$PLAN" P1 --json '{"goal": "g"}' >/dev/null || fail "A: set phase $PLAN"
  planner add-item "$PLAN" P1 --title "Feature" --json '{"summary": "base", "why": "w", "scope": {"include": ["f.txt"],
    "exclude": []}, "deliverables": ["d"], "task_files": [{"path": "f.txt", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}' >/dev/null \
    || fail "A: add-item $PLAN"
done

ws init >/dev/null || fail "A: workspace init"
ws migrate apply --project "$A" --json > "$WORK/apply.json" || fail "A: migrate apply: $(cat "$WORK/apply.json")"
PROJECT_ID="$(json "$WORK/apply.json" project_id)"
case "$PROJECT_ID" in prj_*) ;; *) fail "unexpected project id '$PROJECT_ID'" ;; esac
git init -q --bare -b main "$REMOTE"
ws connect --remote "$URL" --json > "$WORK/connect.json" || fail "A: connect: $(cat "$WORK/connect.json")"
[ "$(json "$WORK/connect.json" classification)" = "empty" ] || fail "A: the new remote is not classified empty"

# connect pushed nothing; the first sync commits the migrated plans and pushes them (the remote and the branch are printed)
ws sync --push > "$WORK/a-push.txt" || fail "A: sync --push: $(cat "$WORK/a-push.txt")"
grep -q "pushing to $URL branch main" "$WORK/a-push.txt" || fail "A: the push did not print the remote and the branch first"
[ "$(git -C "$REMOTE" rev-parse main)" = "$(head_of "$SKM_WORKSPACE_ROOT")" ] || fail "A: the remote is not at the workspace HEAD"
git -C "$SKM_WORKSPACE_ROOT" log -1 --format=%B | grep -q '^Workspace-Device: dev_' || fail "A: no Workspace-Device trailer"
[ -f "$SKM_HOME/state/workspace/audit.jsonl" ] && [ -f "$SKM_HOME/state/workspace/sync.json" ] \
  || fail "A: sync wrote no audit.jsonl or sync.json"
if grep -rqE '(/home/|/Users/|[A-Za-z]:\\)' "$SKM_WORKSPACE_ROOT/projects/$PROJECT_ID/project.json" "$SKM_WORKSPACE_ROOT/workspace.json"; then
  fail "A: a portable document holds an absolute path"
fi

# ---------------------------------------------------------------------------------------------- machine B: clone and scan
git clone -q "$A" "$B"
machine b
git config user.email e2e@example.invalid
git config user.name e2e
swissknifeman project init >/dev/null || fail "B: project init"
ws clone "$URL" --json > "$WORK/clone.json" || fail "B: clone: $(cat "$WORK/clone.json")"
[ "$(head_of "$SKM_WORKSPACE_ROOT")" = "$(git -C "$REMOTE" rev-parse main)" ] || fail "B: the clone is not at the remote HEAD"
cp -a "$A/.swissknifeman/project.json" "$B/.swissknifeman/project.json"
ws project scan "$WORK/b" --json > "$WORK/scan.json" || fail "B: project scan"
[ "$(json "$WORK/scan.json" bound.0.project_id)" = "$PROJECT_ID" ] || fail "B: scan did not bind $PROJECT_ID"
planner plans --json > "$WORK/b-plans.json" || fail "B: planner plans"
grep -q "$PLAN_A" "$WORK/b-plans.json" && grep -q "$PLAN_B" "$WORK/b-plans.json" || fail "B: the planner does not see the plans of A"
[ ! -e plans ] || fail "B: a plans/ folder appeared in the checkout"

settle() {  # both machines sync until they hold the same commit
  machine a; ws sync --push >/dev/null || fail "A: settle push"
  machine b; ws sync --push >/dev/null || fail "B: settle push"
  machine a; ws sync --push >/dev/null || fail "A: settle pull"
  [ "$(head_of "$WORK/ws-a")" = "$(head_of "$WORK/ws-b")" ] || fail "the machines are not at the same commit"
  [ "$(git -C "$REMOTE" rev-parse main)" = "$(head_of "$WORK/ws-a")" ] || fail "the remote is not at the common commit"
}
item_file() { echo "$WORK/ws-$1/projects/$PROJECT_ID/plans/$2/phases/P1/P1.1.json"; }

# --------------------------------------------------------------------------------- different plans: no conflict
machine a
planner set "$PLAN_A" P1.1 --json '{"summary": "A edits plan A"}' >/dev/null || fail "A: set item of plan A"
machine b
planner set "$PLAN_B" P1.1 --json '{"summary": "B edits plan B"}' >/dev/null || fail "B: set item of plan B"
machine a; ws sync --push >/dev/null || fail "A: sync after editing plan A"
machine b; ws sync --push --json > "$WORK/b-merge.json" || fail "B: sync with a change of A: $(cat "$WORK/b-merge.json")"
[ "$(json "$WORK/b-merge.json" pull.status)" = "merged" ] || fail "B: the pull of a different plan was not a merge"
machine a; ws sync --push >/dev/null || fail "A: sync after the merge of B"
settle
grep -q 'A edits plan A' "$(item_file b "$PLAN_A")" || fail "B lacks the edit of A"
grep -q 'B edits plan B' "$(item_file a "$PLAN_B")" || fail "A lacks the edit of B"

# ------------------------------------------------------------------------------ log.jsonl of one plan: union, no conflict
machine a
planner log "$PLAN_A" P1.1 --type note --summary "note from A" >/dev/null || fail "A: planner log"
machine b
planner log "$PLAN_A" P1.1 --type note --summary "note from B" >/dev/null || fail "B: planner log"
machine a; ws sync --push >/dev/null || fail "A: sync log"
machine b; ws sync --push --json > "$WORK/b-log.json" || fail "B: the log.jsonl of one plan conflicted: $(cat "$WORK/b-log.json")"
settle
for NAME in a b; do
  LOG="$WORK/ws-$NAME/projects/$PROJECT_ID/plans/$PLAN_A/log.jsonl"
  grep -q 'note from A' "$LOG" && grep -q 'note from B' "$LOG" || fail "$NAME: log.jsonl lost a note"
  python3 -I -c 'import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    if line.strip():
        json.loads(line)' "$LOG" || fail "$NAME: log.jsonl is not valid JSON lines after the merge"
done

# ------------------------------------------------------------------------------------ the same item: a typed conflict
machine a
planner set "$PLAN_A" P1.1 --json '{"summary": "item edited on A"}' >/dev/null || fail "A: set the shared item"
machine b
planner set "$PLAN_A" P1.1 --json '{"summary": "item edited on B"}' >/dev/null || fail "B: set the shared item"
machine a; ws sync --push >/dev/null || fail "A: sync the shared item"
machine b
ws sync --commit >/dev/null || fail "B: commit the shared item"
HEAD_B="$(head_of "$SKM_WORKSPACE_ROOT")"
TREE_B="$(git -C "$SKM_WORKSPACE_ROOT" ls-tree -r HEAD | sha256sum)"
FILE_B="$(sha256sum "$(item_file b "$PLAN_A")")"
if ws sync --pull --json > "$WORK/conflict.json" 2> "$WORK/conflict.err"; then fail "B: a conflicting pull succeeded"; fi
grep -q '^WORKSPACE_CONFLICT' "$WORK/conflict.err" || fail "B: no WORKSPACE_CONFLICT: $(cat "$WORK/conflict.err")"
python3 -I - "$WORK/conflict.json" "$PLAN_A" "$PROJECT_ID" <<'PY' || fail "B: the conflict report is not as expected"
import json, sys
doc = json.load(open(sys.argv[1]))
rows = {row["ref"]: row for row in doc["conflicts"]}
assert "P1.1" in rows, doc["conflicts"]
assert rows["P1.1"]["plan"] == sys.argv[2] and rows["P1.1"]["project_id"] == sys.argv[3], rows["P1.1"]
assert rows["P1.1"]["path"].endswith("/phases/P1/P1.1.json"), rows["P1.1"]
assert "log" not in rows, "log.jsonl must merge by union, not conflict"
assert doc["error"]["code"] == "WORKSPACE_CONFLICT"
PY
[ "$(head_of "$SKM_WORKSPACE_ROOT")" = "$HEAD_B" ] || fail "B: HEAD moved on a conflict"
[ "$(sha256sum "$(item_file b "$PLAN_A")")" = "$FILE_B" ] || fail "B: the working tree changed on a conflict"
[ -z "$(git -C "$SKM_WORKSPACE_ROOT" status --porcelain)" ] || fail "B: the working tree is dirty after a conflict"
[ ! -e "$SKM_WORKSPACE_ROOT/.git/MERGE_HEAD" ] || fail "B: a merge was left in progress"
ws sync --push > /dev/null 2>&1 && fail "B: a push went through on top of an unresolved conflict" || true

COUNT="$(json "$WORK/conflict.json" conflicts | python3 -I -c 'import json, sys; print(len(json.load(sys.stdin)))')"
ARGS=()
while IFS= read -r CONFLICT_PATH; do ARGS+=(--resolve "$CONFLICT_PATH=remote"); done < <(
  python3 -I -c 'import json, sys
for row in json.load(open(sys.argv[1]))["conflicts"]:
    print(row["path"])' "$WORK/conflict.json")
if [ "$COUNT" -gt 1 ]; then  # decisions in parts: the first one leaves the rest remaining and git untouched
  ws sync "${ARGS[@]:0:2}" --json > "$WORK/part.json" || fail "B: a partial resolution failed"
  REMAINING="$(python3 -I -c 'import json, sys; print(len(json.load(open(sys.argv[1]))["resolution"]["remaining"]))' "$WORK/part.json")"
  [ "$REMAINING" -ge 1 ] || fail "B: a partial resolution left nothing remaining"
  [ "$(head_of "$SKM_WORKSPACE_ROOT")" = "$HEAD_B" ] || fail "B: a partial resolution moved HEAD"
fi
ws sync "${ARGS[@]}" --push --json > "$WORK/resolved.json" || fail "B: resolve and push: $(cat "$WORK/resolved.json")"
[ "$(json "$WORK/resolved.json" push.status)" = "pushed" ] || fail "B: the resolved merge was not pushed"
grep -q 'item edited on A' "$(item_file b "$PLAN_A")" || fail "B: --resolve remote did not take the side of A"
[ -z "$(git -C "$SKM_WORKSPACE_ROOT" status --porcelain)" ] || fail "B: the working tree is dirty after the resolution"
git -C "$SKM_WORKSPACE_ROOT" log --merges -1 --format=%s | grep -q '^skm(workspace): merge origin/main (resolved ' \
  || fail "B: no merge commit for the resolution"
machine a; ws sync >/dev/null || fail "A: pull the resolution"
[ "$(head_of "$WORK/ws-a")" = "$(head_of "$WORK/ws-b")" ] || fail "the machines are not at the same commit after the resolution"
grep -q 'item edited on A' "$(item_file a "$PLAN_A")" || fail "A: lost its own edit"
planner plans --json | grep -q "$PLAN_A" || fail "A: the planner lost the plan after the merges"
machine b; planner plans --json | grep -q "$PLAN_A" || fail "B: the planner lost the plan after the merges"
ws doctor >/dev/null || fail "B: workspace doctor after the merges"

echo "e2e-workspace-sync: OK"
