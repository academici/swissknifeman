#!/usr/bin/env bash
# e2e-work-source.sh — end-to-end check of the work-source port of orch served by the planner-orch bridge plugin:
# orch.py source claim (and its repeat), brief (a content-addressed artifact), prepare (a valid launch-plan) and
# register through the evidence gate close a plan item; the project journal holds orch.run.started and
# orch.run.finished; a registration without evidence is refused with REGISTER_EVIDENCE_MISSING, and a run whose item
# was taken over by another session is refused with REGISTER_STALE_OWNER.
#
# It registers the plugin in the machine configuration, so it must run in a throwaway HOME:
# scripts/dev-sandbox.sh run DIR -- bash scripts/e2e-work-source.sh. It writes only inside that HOME and a
# temporary folder. Exit 0 and the line "e2e work source: OK" when everything held; otherwise
# "e2e work source: FAIL ..." and exit 1.
set -euo pipefail

HUB="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
say() { echo "e2e work source: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
if [ -z "$real_home" ] || [ "$(readlink -f "${HOME:-/}")" = "$(readlink -f "$real_home")" ]; then
  echo "SKM_DEV_GUARD: e2e-work-source.sh changes the machine configuration; run it with a throwaway HOME (scripts/dev-sandbox.sh)" >&2
  exit 3
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# The partners of the bridge, as scripts/test-bridges.sh wires them from the hub layout.
export PLANNER_ROOT="$HUB/packages/planner"
export PLANNER_PLAN_PY="$PLANNER_ROOT/scripts/plan.py"
export SKM_ORCH_ROOT="$HUB/packages/orch"
export AICORE_ROOT="$HUB/packages/aicore"
export SKM_AICORE_EVENTS__DELIVERY=off
export PYTHONPATH="$SKM_ORCH_ROOT/lib:$AICORE_ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
aicore() { python3 -m aicore "$@"; }
plan() { python3 "$PLANNER_PLAN_PY" "$@"; }
orch() { python3 "$SKM_ORCH_ROOT/scripts/orch.py" "$@"; }
field() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$@"; }

aicore config set aicore.plugins.planner-orch.manifest "$HUB/bridges/planner-orch/extension.json" --machine >/dev/null
aicore config set aicore.plugins.planner-orch.trusted true --machine >/dev/null

# A git project with a plan of three detailed items, one acceptance check each.
PROJECT="$WORK/project"
mkdir -p "$PROJECT/plans"
git init -q "$PROJECT"
cd "$PROJECT"
ACTOR="claude-code/claude-opus-5-5/high"
plan new --plans-root plans --codename WS --title "Work source" --repository e2e --owner e2e --actor "$ACTOR" \
  --message "end-to-end check" --date 2026.10.07 >/dev/null || fail "plan new"
PLAN_ID="$(ls plans | head -1)"
[ -n "$PLAN_ID" ] || fail "no plan was created"
SHORT="$(field "plans/$PLAN_ID/plan.json" short_id)"
plan add-phase "$PLAN_ID" --title "One" >/dev/null || fail "add-phase"
plan set "$PLAN_ID" P1 --json '{"goal": "g"}' >/dev/null || fail "set phase"
for n in 1 2 3; do
  plan add-item "$PLAN_ID" P1 --title "Item $n" --json '{"summary": "s", "why": "w", "scope": {"include": ["x"],
    "exclude": []}, "deliverables": ["d"], "task_files": [{"path": "lib/x'"$n"'.py", "change": "any"}],
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}' >/dev/null || fail "add-item $n"
done
plan batches "$PLAN_ID" P1 --json '[{"id": "B1", "items": ["P1.1"], "mode": "recommended"},
  {"id": "B2", "items": ["P1.2"], "mode": "recommended"}, {"id": "B3", "items": ["P1.3"], "mode": "recommended"}]' \
  >/dev/null || fail "batches"
plan design-done "$PLAN_ID" P1 --actor "$ACTOR" >/dev/null || fail "design-done"
status_of() { plan --output json get "$PLAN_ID" "$1" | python3 -c 'import json, sys; print(json.load(sys.stdin)["data"]["doc"]["status"])'; }
evidence() {  # evidence <item> <exit>: a check-evidence file of V1, repository-relative path on stdout
  mkdir -p ev
  printf '{"$schema": "urn:swissknifeman:task:plan:check-evidence:v1", "evidence_id": "ev-%s", "check_id": "V1", "subject": "%s.%s", "procedure": {"cmd": "true"}, "candidate": {"head": "0123456"}, "exit": %s, "started_at": "2026-10-11T00:00:00Z", "finished_at": "2026-10-11T00:00:01Z", "producer": {"kind": "executor"}}\n' \
    "$1" "$SHORT" "$1" "$2" > "ev/$1-V1.json"
  echo "ev/$1-V1.json"
}
echo '{"summary": "did the work"}' > "$WORK/report.json"

# 1. The next ready item: claim, repeat, brief, prepare, register with passing evidence.
orch source claim --plan "$PLAN_ID" --actor "$ACTOR" > "$WORK/claim.json" || fail "source claim"
[ "$(field "$WORK/claim.json" status)" = claimed ] || fail "claim: $(cat "$WORK/claim.json")"
[ "$(field "$WORK/claim.json" ref)" = P1.1 ] || fail "claim took $(field "$WORK/claim.json" ref), expected P1.1"
RUN="$(field "$WORK/claim.json" run_id)"
ATTEMPT="$(field "$WORK/claim.json" attempt_id)"
orch source claim --plan "$PLAN_ID" --actor "$ACTOR" > "$WORK/claim-again.json" || fail "repeated claim"
[ "$(field "$WORK/claim-again.json" attempt_id)" = "$ATTEMPT" ] || fail "the repeated claim changed the attempt"
[ "$(field "$WORK/claim-again.json" run_id)" = "$RUN" ] || fail "the repeated claim changed the run"
say "ok: claimed P1.1 as $RUN; a repeat is the same run and attempt"

orch source brief --run "$RUN" > "$WORK/brief.json" || fail "source brief"
python3 - "$WORK/brief.json" "$PROJECT" <<'EOF' || fail "the brief blob is missing"
import json, sys
from aicore.state import blobs
answer = json.load(open(sys.argv[1]))
assert blobs.blob_path(answer["input_ref"], project=sys.argv[2]).is_file(), answer
EOF
say "ok: the brief is stored as $(field "$WORK/brief.json" artifact_id)"

orch source prepare --run "$RUN" --provider claude-code --binding claude-only > /dev/null || fail "source prepare"
RUN_DIR="$PROJECT/.swissknifeman/state/orch/runs/$RUN"
orch validate launch-plan "$RUN_DIR/launch-plan.json" --quiet || fail "launch-plan.json is not valid"
say "ok: launch-plan.json is valid"

orch source register --run "$RUN" --report "$WORK/report.json" --status done --evidence "V1=$(evidence P1.1 0)" \
  --actor "$ACTOR" > "$WORK/register.json" || fail "source register: $(cat "$WORK/register.json")"
[ "$(field "$WORK/register.json" outcome)" = recorded ] || fail "register: $(cat "$WORK/register.json")"
[ "$(status_of P1.1)" = done ] || fail "P1.1 is $(status_of P1.1), expected done"
[ -f "$RUN_DIR/receipts/register.json" ] || fail "no registration receipt in the run"
types="$(aicore events list --project "$PROJECT" --type 'orch.*' --json | python3 -c '
import json, sys
print(" ".join(e["type"] for e in json.load(sys.stdin)["events"]))')"
case " $types " in *" orch.run.started "*" orch.run.finished "*) ;; *) fail "journal types: $types" ;; esac
say "ok: P1.1 is done; the journal holds $types"

# 2. A registration without evidence is refused and writes nothing.
orch source claim --plan "$PLAN_ID" --item P1.2 --actor "$ACTOR" > "$WORK/claim2.json" || fail "claim P1.2"
RUN2="$(field "$WORK/claim2.json" run_id)"
set +e
orch source register --run "$RUN2" --report "$WORK/report.json" --status done --actor "$ACTOR" > "$WORK/register2.json"
code=$?
set -e
[ "$code" = 1 ] || fail "register without evidence exited $code, expected 1"
[ "$(field "$WORK/register2.json" reason_code)" = REGISTER_EVIDENCE_MISSING ] || fail "register2: $(cat "$WORK/register2.json")"
[ "$(status_of P1.2)" = in_progress ] || fail "P1.2 changed to $(status_of P1.2)"
say "ok: a registration without evidence is refused with REGISTER_EVIDENCE_MISSING"

# 3. Another session takes the item over: the old run registers nothing.
orch source claim --plan "$PLAN_ID" --item P1.3 --actor "$ACTOR" > "$WORK/claim3.json" || fail "claim P1.3"
RUN3="$(field "$WORK/claim3.json" run_id)"
plan start "$PLAN_ID" P1.3 --actor "$ACTOR" --session other-session --take-over --no-scout >/dev/null || fail "take-over"
set +e
orch source register --run "$RUN3" --report "$WORK/report.json" --status done --evidence "V1=$(evidence P1.3 0)" \
  --actor "$ACTOR" > "$WORK/register3.json"
code=$?
set -e
[ "$code" = 1 ] || fail "register after the take-over exited $code, expected 1"
[ "$(field "$WORK/register3.json" reason_code)" = REGISTER_STALE_OWNER ] || fail "register3: $(cat "$WORK/register3.json")"
[ "$(status_of P1.3)" = in_progress ] || fail "P1.3 changed to $(status_of P1.3)"
say "ok: the run that lost its item is refused with REGISTER_STALE_OWNER"

echo "e2e work source: OK"
