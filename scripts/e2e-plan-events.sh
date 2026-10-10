#!/usr/bin/env bash
# e2e-plan-events.sh — end-to-end check of the planner events: a plan is created, run and closed, the project
# journal receives planner.plan.created, item.started, item.finished, phase.closed and plan.closed, the subscriber
# brain:plan-notes writes one vault note for the closed plan, and a repeat of the same finish adds neither events
# nor a second note.
#
# It changes the machine configuration (brain.vault_path, aicore.events.delivery), so it must run in a throwaway
# HOME: scripts/dev-sandbox.sh run DIR -- bash scripts/e2e-plan-events.sh. It writes only inside that HOME.
# Exit 0 and the line "e2e plan events: OK" when everything held; otherwise "e2e plan events: FAIL ..." and exit 1.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
AICORE_ROOT="$ROOT/packages/aicore"
say() { echo "e2e plan events: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
if [ -z "$real_home" ] || [ "$(readlink -f "${HOME:-/}")" = "$(readlink -f "$real_home")" ]; then
  echo "SKM_DEV_GUARD: e2e-plan-events.sh changes the machine configuration; run it with a throwaway HOME (scripts/dev-sandbox.sh)" >&2
  exit 3
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export PYTHONPATH="$AICORE_ROOT/lib${PYTHONPATH:+:$PYTHONPATH}"
export SKM_UNITS_PATH="$ROOT/packages/brain:$ROOT/packages/planner:$AICORE_ROOT"
aicore() { python3 -m aicore "$@"; }
plan() { python3 "$ROOT/packages/planner/scripts/plan.py" "$@"; }

# The vault of the brain tests is the synthetic one; the project is a git repository with an empty plans/.
VAULT="$WORK/vault"
PROJECT="$WORK/project"
cp -r "$ROOT/packages/brain/tests/fixtures/vault" "$VAULT"
mkdir -p "$PROJECT/plans"
git init -q "$PROJECT"
aicore config set brain.vault_path "$VAULT" --machine >/dev/null
aicore config set aicore.events.delivery sync --machine >/dev/null

vault_files() { (cd "$VAULT" && find . -type f | sort); }
vault_files > "$WORK/vault-before.txt"
journal_types() { aicore events list --project "$PROJECT" --type 'planner.*' --json | python3 -c '
import json, sys
print(" ".join(e["type"] for e in json.load(sys.stdin)["events"]))'; }
new_notes() { vault_files | comm -13 "$WORK/vault-before.txt" - ; }

ACTOR="claude-code/claude-opus-5-5/high"
cd "$PROJECT"
plan new --plans-root plans --codename E2E --title "Events" --repository e2e --owner e2e --actor "$ACTOR" \
  --message "end-to-end check" --date 2026.10.07 >/dev/null || fail "plan new"
PLAN_ID="$(ls plans | head -1)"
[ -n "$PLAN_ID" ] || fail "no plan was created"
plan add-phase "$PLAN_ID" --title "One" >/dev/null || fail "add-phase"
plan set "$PLAN_ID" P1 --json '{"goal": "g"}' >/dev/null || fail "set phase"
plan add-item "$PLAN_ID" P1 --title "Only" --json '{"summary": "s", "why": "w", "scope": {"include": ["x"], "exclude": []},
  "deliverables": ["d"], "task_files": [{"path": "lib/x.py", "change": "any"}],
  "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}' >/dev/null || fail "add-item"
plan design-done "$PLAN_ID" P1 --actor "$ACTOR" >/dev/null || fail "design-done"
plan start "$PLAN_ID" P1.1 --actor "$ACTOR" --no-scout >/dev/null || fail "start"
plan finish "$PLAN_ID" P1.1 --status done --check V1=0 --attempt-id e2e-1 --notes "e2e" >/dev/null || fail "finish"

want="planner.plan.created planner.item.started planner.item.finished planner.phase.closed planner.plan.closed"
[ "$(journal_types)" = "$want" ] || fail "journal types: $(journal_types), expected: $want"
say "ok: the journal holds the five planner events"

notes="$(new_notes)"
[ "$(printf '%s\n' "$notes" | grep -c .)" = 1 ] || fail "expected exactly one new vault file, got: $notes"
note="${notes#./}"
case "$note" in *" $PLAN_ID closed "*.md) ;; *) fail "the new file is not the note of the closed plan: $note" ;; esac
grep -q "^plan: $PLAN_ID\$" "$VAULT/$note" || fail "the note does not name the plan: $note"
say "ok: one vault note for the closed plan: $note"
aicore events list --project "$PROJECT" --type brain.note.created --json | python3 -c '
import json, sys
events = json.load(sys.stdin)["events"]
sys.exit(0 if len(events) == 1 and events[0].get("causationid") else "expected one brain.note.created with a cause")' \
  || fail "brain.note.created is missing or has no cause"

aicore events status --project "$PROJECT" --json | python3 -c '
import json, sys
rows = [r for r in json.load(sys.stdin)["subscriptions"] if r["id"] == "brain:plan-notes"]
sys.exit(0 if rows and rows[0]["lag"] == 0 and rows[0]["dead_letters"] == 0 else "brain:plan-notes is not caught up")' \
  || fail "delivery is not caught up"

# The same attempt again: nothing is written, no event, no second note.
before_events="$(journal_types)"
plan finish "$PLAN_ID" P1.1 --status done --check V1=0 --attempt-id e2e-1 --notes "e2e" | grep -q "already registered" \
  || fail "the repeat of the attempt was not recognised"
[ "$(journal_types)" = "$before_events" ] || fail "the repeated finish added events: $(journal_types)"
[ "$(new_notes | grep -c .)" = 1 ] || fail "the repeated finish changed the notes: $(new_notes)"
say "ok: a repeated finish adds neither events nor notes"

echo "e2e plan events: OK"
