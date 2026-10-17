#!/usr/bin/env bash
# e2e-workspace-migrate.sh — end-to-end check of the migration of a project's plans into the portable workspace
# (PLAN6 P3, contract knowledge/workspace-contract#migration). A temporary git project gets the launcher and plans in
# its own plans/ folder (a v4 plan made by the planner, an archived-looking legacy folder and a loose file). Then:
#   plan (dry run writes nothing) -> apply -> the planner reads the plans from the workspace -> a second apply is a
#   noop -> verify is equal -> a real second planner process that waits for the PlanLock of the old plan gets
#   PLANS_MIGRATED -> rollback -> apply again -> cleanup.
# The import mode: a second machine (a second SKM_HOME on a copy of the same workspace) migrates its own checkout of the
# project; an equal plan is skipped-equal, a plan changed on that machine is a MIGRATION_CONFLICT until --on-conflict.
#
# It runs only in temporary folders: HOME, SKM_HOME and SKM_WORKSPACE_ROOT are set to a throwaway directory, so
# neither the real HOME nor the real workspace is touched. Exit 0 and the line "e2e-workspace-migrate: OK" when
# everything held; otherwise "e2e-workspace-migrate: FAIL ..." and exit 1.
set -euo pipefail

HUB="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
say() { echo "e2e-workspace-migrate: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home" SKM_HOME="$WORK/skm" SKM_WORKSPACE_ROOT="$WORK/ws"
export SKM_AICORE_EVENTS__DELIVERY=off
unset XDG_CONFIG_HOME XDG_STATE_HOME XDG_DATA_HOME XDG_CACHE_HOME SKM_PROJECT_ROOT
unset SKM_LAUNCHER_ACTIVE SKM_LAUNCHER_PID SKM_LAUNCHER_PROJECT_ROOT SKM_LAUNCHER_PATH SKM_LAUNCHER_PROTOCOL SKM_INVOCATION_CWD
export AICORE_ROOT="$HUB/packages/aicore"
export PLANNER_ROOT="$HUB/packages/planner"
export PLANNER_PLAN_PY="$PLANNER_ROOT/scripts/plan.py"
mkdir -p "$HOME" "$WORK/bin"
ln -s "$HUB/bin/swissknifeman" "$WORK/bin/swissknifeman"
export PATH="$WORK/bin:$PATH"

# The bridge of the port workspace:plans-migrator is registered as a trusted plugin so it receives PLANNER_ROOT.
register_bridge() {
  swissknifeman config set --machine aicore.plugins.workspace-planner.manifest "$HUB/bridges/workspace-planner/extension.json" \
    >/dev/null || fail "config set manifest"
  swissknifeman config set --machine aicore.plugins.workspace-planner.trusted true >/dev/null || fail "config set trusted"
}
register_bridge

ACTOR="claude-code/claude-opus-5-5/high"
json() { python3 -I -c 'import json, sys; d = json.load(open(sys.argv[1]))
for key in sys.argv[2].split("."):
    d = d[int(key)] if isinstance(d, list) else d[key]
print(json.dumps(d) if isinstance(d, (dict, list)) else d)' "$@"; }

# ---------------------------------------------------------------------------------------------- the project (machine A)
A="$WORK/a/project"
mkdir -p "$A"
git init -q "$A"
cd "$A"
git config user.email e2e@example.invalid
git config user.name e2e
echo base > base.txt
git add base.txt
git commit -q -m "chore: base"
swissknifeman project init >/dev/null || fail "project init"
launch() { python3 -I .swissknifeman/launcher.py "$@"; }
planner() { launch planner "$@"; }

# Without a workspace marker the plans are written to <root>/plans (the legacy store).
planner new --codename MIG --title "Migration" --repository e2e --actor "$ACTOR" --message "migration e2e" \
  >/dev/null || fail "planner new"
PLAN_ID="$(ls plans | grep -v '^\.' | head -1)"
[ -f "plans/$PLAN_ID/plan.json" ] || fail "no legacy plan in plans/"
planner add-phase "$PLAN_ID" --title "One" >/dev/null || fail "add-phase"
planner set "$PLAN_ID" P1 --json '{"goal": "g"}' >/dev/null || fail "set phase"
planner add-item "$PLAN_ID" P1 --title "Feature" --json '{"summary": "s", "why": "w", "scope": {"include": ["f.txt"],
  "exclude": []}, "deliverables": ["d"], "task_files": [{"path": "f.txt", "change": "any"}],
  "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}' >/dev/null || fail "add-item"
# An old-format folder and a loose file: copied as they are, the planner never reads them.
mkdir -p plans/old-format/artifacts
printf 'old notes\n' > plans/old-format/notes.md
printf 'artifact\n' > plans/old-format/artifacts/a.txt
printf 'loose\n' > plans/README.md
planner plans --json | grep -q "$PLAN_ID" || fail "the planner does not list $PLAN_ID before the migration"

swissknifeman workspace init >/dev/null || fail "workspace init"

# ------------------------------------------------------------------------------------------------------------ plan
swissknifeman workspace migrate plan --project "$A" --json > "$WORK/plan.json" || fail "migrate plan: $(cat "$WORK/plan.json")"
[ -z "$(ls -d "$SKM_WORKSPACE_ROOT"/projects/prj_* 2>/dev/null)" ] \
  || fail "the dry run wrote into the workspace projects/"
[ ! -e .swissknifeman/project.json ] || fail "the dry run wrote the marker"
python3 -I - "$WORK/plan.json" "$PLAN_ID" <<'PY' || fail "the plan document is not as expected"
import json, sys
doc = json.load(open(sys.argv[1]))
text = json.dumps(doc)
assert not doc.get("blockers"), doc.get("blockers")
names = {row["name"]: row for row in doc["plans"]}
assert names[sys.argv[2]]["class"] == "v4", names
assert names["old-format"]["class"] == "legacy", names
assert "_root" in names and names["_root"]["class"] == "legacy", names
assert all(row["action"] == "copied" for row in doc["plans"]), doc["plans"]
PY

# ----------------------------------------------------------------------------------------------------------- apply
swissknifeman workspace migrate apply --project "$A" --json > "$WORK/apply.json" || fail "migrate apply: $(cat "$WORK/apply.json")"
[ "$(json "$WORK/apply.json" noop)" = "False" ] || fail "the first apply is a noop"
PROJECT_ID="$(json "$WORK/apply.json" project_id)"
case "$PROJECT_ID" in prj_*) ;; *) fail "unexpected project id '$PROJECT_ID'" ;; esac
PDIR="$SKM_WORKSPACE_ROOT/projects/$PROJECT_ID"
grep -q '"plans_store": "workspace"' .swissknifeman/project.json || fail "the marker does not say plans_store=workspace"
[ -f "$PDIR/plans/$PLAN_ID/plan.json" ] || fail "the plan is not in the workspace"
[ -f "$PDIR/legacy-plans/old-format/notes.md" ] || fail "the old-format folder is not in legacy-plans/"
[ -f "$PDIR/legacy-plans/_root/README.md" ] || fail "the loose file is not in legacy-plans/_root"
[ -f plans/$PLAN_ID/plan.json ] || fail "apply removed the source"
[ -n "$(ls "$PDIR"/migrations/*.json 2>/dev/null)" ] || fail "no migration report"
OP_ID="$(json "$WORK/apply.json" op_id)"
if grep -rqE '(/home/|/Users/|[A-Za-z]:\\)' "$PDIR/migrations" "$PDIR/project.json" .swissknifeman/project.json; then
  fail "a portable document holds an absolute path"
fi

# The planner now reads the plans from the workspace, not from plans/.
planner plans --json > "$WORK/plans-after.json" || fail "planner plans after apply"
grep -q "$PLAN_ID" "$WORK/plans-after.json" || fail "the planner does not see $PLAN_ID after apply"
launch project context --json > "$WORK/context.json" || fail "project context"
[ "$(json "$WORK/context.json" plans_store.kind)" = "workspace" ] || fail "project context does not report the workspace store"
case "$(json "$WORK/context.json" plans_root)" in */projects/"$PROJECT_ID"/plans) ;; *) fail "plans_root is not the workspace folder" ;; esac
# ------------------------------------------------------------------------------------------- repeat apply and verify
swissknifeman workspace migrate apply --project "$A" --json > "$WORK/apply2.json" || fail "second apply: $(cat "$WORK/apply2.json" 2>&1)"
[ "$(json "$WORK/apply2.json" noop)" = "True" ] || fail "the second apply is not a noop"
[ "$(ls "$PDIR"/migrations/*.json | wc -l)" = "1" ] || fail "the noop apply wrote a second report"
swissknifeman workspace migrate verify --project "$A" --json > "$WORK/verify.json" || fail "verify: $(cat "$WORK/verify.json")"
python3 -I - "$WORK/verify.json" <<'PY' || fail "verify is not equal"
import json, sys
doc = json.load(open(sys.argv[1]))
assert doc["all_equal"] is True, doc
PY

# --------------------------------------------------------------------------- a concurrent planner writer on the old plan
# Marker: workspace now. Rollback first, so the old folder is the store again, then migrate with a real second planner
# process that waits for the PlanLock of the old plan: it must get PLANS_MIGRATED, never write into the old folder.
swissknifeman workspace migrate rollback --project "$A" --json > "$WORK/rollback.json" || fail "rollback: $(cat "$WORK/rollback.json")"
grep -q '"plans_store": "legacy"' .swissknifeman/project.json || fail "rollback did not set plans_store=legacy"
[ ! -e "$PDIR/plans/$PLAN_ID" ] && [ ! -e "$PDIR/legacy-plans/old-format" ] || fail "rollback left the migrated folders: $(find "$PDIR" -maxdepth 3 | head -20)"
planner plans --json | grep -q "$PLAN_ID" || fail "the planner does not see the plan in plans/ after rollback"

HOLD_PY="$WORK/hold.py"
cat > "$HOLD_PY" <<'PY'
import fcntl, sys, time
handle = open(sys.argv[1] + "/.lock", "a+")
fcntl.flock(handle, fcntl.LOCK_EX)
print("HELD", flush=True)
time.sleep(float(sys.argv[2]))
PY
WRITER_PY="$WORK/writer.py"
cat > "$WRITER_PY" <<'PY'
import sys, time
sys.path.insert(0, sys.argv[1] + "/lib")
from planner.plan import store
# flock is not fair: a writer granted the lock before the switch is right; it must see PLANS_MIGRATED after it.
deadline = time.monotonic() + 40
while time.monotonic() < deadline:
    try:
        with store.PlanLock(sys.argv[2], timeout=25):
            print("GRANTED", flush=True)
    except store.PlanError as exc:
        print(exc.code, flush=True)
        break
    time.sleep(0.05)
PY
python3 -I "$HOLD_PY" "$A/plans/$PLAN_ID" 3 > "$WORK/hold.out" &
HOLD_PID=$!
for _ in $(seq 100); do grep -q HELD "$WORK/hold.out" 2>/dev/null && break; sleep 0.1; done
grep -q HELD "$WORK/hold.out" || fail "the lock holder did not start"
python3 -I "$WRITER_PY" "$PLANNER_ROOT" "$A/plans/$PLAN_ID" > "$WORK/writer.out" &
WRITER_PID=$!
sleep 0.5
kill -0 "$WRITER_PID" 2>/dev/null || fail "the writer did not wait for the lock"
swissknifeman workspace migrate apply --project "$A" --lock-timeout 20 --json > "$WORK/apply3.json" \
  || fail "apply with a waiting writer: $(cat "$WORK/apply3.json")"
wait "$WRITER_PID" || fail "the writer process failed"
wait "$HOLD_PID" || true
[ "$(tail -n 1 "$WORK/writer.out")" = "PLANS_MIGRATED" ] || fail "the waiting writer did not get PLANS_MIGRATED: $(cat "$WORK/writer.out")"
[ "$(grep -vc -e GRANTED -e PLANS_MIGRATED "$WORK/writer.out")" = "0" ] || fail "unexpected writer output: $(cat "$WORK/writer.out")"
grep -q '"plans_store": "workspace"' .swissknifeman/project.json || fail "the marker is not workspace after the second migration"
[ "$(json "$WORK/apply3.json" project_id)" = "$PROJECT_ID" ] || fail "the project id changed between migrations"
[ -f "$PDIR/plans/$PLAN_ID/plan.json" ] || fail "the plan is not in the workspace after the repeated apply"

# ------------------------------------------------------------------------------- the second machine (import mode)
# A copy of the workspace and of the checkout stands for machine B: its own SKM_HOME (so its own device), the same
# project id (the marker comes with the checkout), plans that exist in the workspace already.
B="$WORK/b/project"
mkdir -p "$WORK/b"
git clone -q "$A" "$B"
mkdir -p "$B/.swissknifeman"
cp -a "$A/.swissknifeman/project.json" "$B/.swissknifeman/project.json"
# the checkout of B still holds the plans of the old store, as before the migration, with one plan changed on B
mkdir -p "$B/plans"
cp -a "$A/plans/." "$B/plans/"
python3 -I - "$B/.swissknifeman/project.json" <<'PY'
import json, sys
path = sys.argv[1]
doc = json.load(open(path))
doc["plans_store"] = "legacy"
open(path, "w").write(json.dumps(doc, indent=2) + "\n")
PY
WS_B="$WORK/ws-b"
cp -a "$SKM_WORKSPACE_ROOT" "$WS_B"
(
  export SKM_HOME="$WORK/skm-b" SKM_WORKSPACE_ROOT="$WS_B" HOME="$WORK/home-b"
  mkdir -p "$HOME"
  cd "$B"
  register_bridge
  swissknifeman workspace migrate plan --project "$B" --json > "$WORK/b-plan.json" || fail "machine B: migrate plan"
  python3 -I - "$WORK/b-plan.json" "$PLAN_ID" <<'PY' || fail "machine B: equal plan is not skipped-equal"
import json, sys
doc = json.load(open(sys.argv[1]))
rows = {row["name"]: row for row in doc["plans"]}
assert rows[sys.argv[2]]["action"] == "skipped-equal", rows[sys.argv[2]]
PY
  # a local change on B that never reached the repository: the digests differ
  python3 -I - "$B/plans/$PLAN_ID/plan.json" <<'PY'
import json, sys
path = sys.argv[1]
doc = json.load(open(path))
doc["title"] = doc.get("title", "") + " (edited on B)"
open(path, "w").write(json.dumps(doc, indent=2) + "\n")
PY
  swissknifeman workspace migrate apply --project "$B" --json > "$WORK/b-conflict.json" 2>&1 && fail "machine B: a conflict was applied silently"
  grep -q MIGRATION_CONFLICT "$WORK/b-conflict.json" || fail "machine B: no MIGRATION_CONFLICT: $(cat "$WORK/b-conflict.json")"
  swissknifeman workspace migrate apply --project "$B" --on-conflict import-copy --json > "$WORK/b-apply.json" \
    || fail "machine B: apply import-copy: $(cat "$WORK/b-apply.json")"
  ls "$WS_B/projects/$PROJECT_ID/plans" | grep -q "^$PLAN_ID~" || fail "machine B: the changed plan was not kept as an imported copy"
  [ -f "$WS_B/projects/$PROJECT_ID/plans/$PLAN_ID/plan.json" ] || fail "machine B: the workspace plan was overwritten or removed"
  grep -q '(edited on B)' "$WS_B/projects/$PROJECT_ID/plans/$PLAN_ID/plan.json" && fail "machine B: the workspace plan was overwritten"
  grep -q '"plans_store": "workspace"' "$B/.swissknifeman/project.json" || fail "machine B: marker not switched"
) || exit 1

# ------------------------------------------------------------------------------------------------------------ cleanup
swissknifeman workspace migrate cleanup --project "$A" --confirm "$PROJECT_ID" --json > "$WORK/cleanup.json" \
  || fail "cleanup: $(cat "$WORK/cleanup.json")"
[ ! -e "$A/plans/$PLAN_ID" ] || fail "cleanup left the migrated plan folder"
[ ! -e "$A/plans/old-format" ] || fail "cleanup left the old-format folder"
[ -f "$PDIR/plans/$PLAN_ID/plan.json" ] || fail "cleanup removed the workspace copy"
swissknifeman workspace migrate cleanup --project "$A" --confirm prj_wrong --json >/dev/null 2>&1 \
  && fail "cleanup accepted a wrong project id"
planner plans --json | grep -q "$PLAN_ID" || fail "the planner lost the plan after cleanup"
swissknifeman workspace doctor --json >/dev/null || fail "workspace doctor after the migration"

echo "e2e-workspace-migrate: OK"
