#!/usr/bin/env bash
# e2e-plan-note.sh VAULT PROJECT — end-to-end check of the subscriber brain:plan-notes.
#
# Emits a planner.plan.closed event into the journal of PROJECT, lets aicore deliver it to `brain note`, and checks
# the whole chain on the vault VAULT: one new note per event, nothing else touched, delivery caught up, a replay
# from the start does not duplicate, a failing vault is retried by the cursor, brain.note.created is announced.
# Exit 0: everything held (the paths of the written notes are printed, one per line). Any other exit: a check failed
# (a line "e2e-plan-note: FAIL ..." names it) or the call is wrong.
#
# It must run in a throwaway HOME (the machine configuration is changed: brain.vault_path, aicore.events.delivery),
# for example inside scripts/dev-sandbox.sh of the development clone, and it writes only to VAULT, PROJECT and HOME.
# VAULT is a vault or a copy of one; PROJECT is a directory (git init is run in it when it has no .git).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

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

say() { echo "e2e-plan-note: $*" >&2; }
fail() { say "FAIL $*"; exit 1; }

[ $# -eq 2 ] || { echo "usage: e2e-plan-note.sh VAULT PROJECT" >&2; exit 2; }
[ -d "$1" ] || { echo "e2e-plan-note: VAULT is not a directory: $1" >&2; exit 2; }
VAULT="$(cd "$1" && pwd)"
mkdir -p "$2"
PROJECT="$(cd "$2" && pwd)"

# Refuse the real home directory (the same test as the development-clone guard of bin/brain).
real_home="$(python3 -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null || true)"
if [ -z "$real_home" ] || [ "$(readlink -f "${HOME:-/}")" = "$(readlink -f "$real_home")" ]; then
  echo "SKM_DEV_GUARD: e2e-plan-note.sh changes the machine configuration; run it with a throwaway HOME (scripts/dev-sandbox.sh)" >&2
  exit 3
fi

WORK="$(mktemp -d)"
NOTES_DIR=""
cleanup() {
  [ -n "$NOTES_DIR" ] && [ -d "$NOTES_DIR" ] && chmod u+w "$NOTES_DIR" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

export PYTHONPATH="$AICORE_LIB${PYTHONPATH:+:$PYTHONPATH}"
export SKM_UNITS_PATH="${SKM_UNITS_PATH:-$REPO_ROOT:$AICORE_ROOT}"
FIXTURE="$REPO_ROOT/tests/fixtures/events/planner.plan.closed/valid-full.json"
SUBSCRIPTION="brain:plan-notes"
aicore() { python3 -m aicore "$@"; }

[ -d "$PROJECT/.git" ] || git init -q "$PROJECT"

# --- machine configuration: the vault, and no background delivery (the checks deliver by hand) ---
aicore config set brain.vault_path "$VAULT" --machine >/dev/null
aicore config set aicore.events.delivery off --machine >/dev/null

snapshot() { (cd "$VAULT" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum) > "$1"; }
paths_of() { sed 's/^[0-9a-f]\{64\}  //' "$1"; }
snapshot "$WORK/before.sum"

data_file() { # data_file OUT PLAN_ID: the data of the valid-full fixture with another plan id
  python3 - "$FIXTURE" "$1" "$2" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["data"]
data["plan_id"] = sys.argv[3]
json.dump(data, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
}
emit_closed() { # emit_closed PLAN_ID: prints the event id; the call returns after the delivery attempt
  data_file "$WORK/data.json" "$1"
  aicore events emit --source planner --type planner.plan.closed --subject "$1" --data-file "$WORK/data.json" \
    --project "$PROJECT" --delivery sync --json 2> "$WORK/emit.err" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])' || { cat "$WORK/emit.err" >&2; fail "emit"; }
}
status_field() { # status_field EXPRESSION: a Python expression over the row of brain:plan-notes ("row")
  aicore events status --project "$PROJECT" --json | python3 -c '
import json, sys
row = [r for r in json.load(sys.stdin)["subscriptions"] if r["id"] == sys.argv[1]][0]
value = eval(sys.argv[2])
print(" ".join(map(str, value)) if isinstance(value, tuple) else value)' "$SUBSCRIPTION" "$1"
}
new_files() { # new_files: the files in the vault that were not in the first snapshot
  snapshot "$WORK/now.sum"
  { diff <(paths_of "$WORK/before.sum") <(paths_of "$WORK/now.sum") || true; } | sed -n 's/^> //p'
}
note_event_id() { sed -n 's/^event_id: //p' "$VAULT/$1" | head -1; }

# --- 1. one event: one note, caught up -----------------------------------------------------------------------------
id1="$(emit_closed E2E-PLAN)"
[ -n "$id1" ] || fail "emit gave no event id"
created="$(new_files)"
[ "$(printf '%s\n' "$created" | grep -c .)" = 1 ] || fail "expected exactly one new file after the first event, got: $created"
note1="${created#./}"
case "$note1" in *.md) ;; *) fail "the new file is not a note: $note1" ;; esac
[ "$(note_event_id "$note1")" = "$id1" ] || fail "frontmatter event_id of $note1 is not $id1"
NOTES_DIR="$VAULT/$(dirname "$note1")"
[ "$(status_field 'row["lag"], row["pending"], row["dead_letters"]')" = "0 None 0" ] \
  || fail "delivery is not caught up after the first event: $(status_field 'row')"
say "ok: one note for the first event: $note1"

# --- 2. replay from the start: the cursor delivers again, the note is not duplicated -------------------------------
aicore events replay "$SUBSCRIPTION" --from-start --project "$PROJECT" >/dev/null || fail "replay from the start"
[ "$(new_files | grep -c .)" = 1 ] || fail "a replay from the start changed the set of notes: $(new_files)"
[ "$(status_field 'row["lag"], row["pending"], row["dead_letters"]')" = "0 None 0" ] || fail "delivery is not caught up after the replay"
say "ok: replay from the start gave no second note"

# --- 3. the vault cannot be written: the cursor stands, the next delivery writes the note (R06) --------------------
if [ "$(id -u)" = 0 ]; then
  say "skip: running as root, a read-only notes folder is not enforced; emitting the second event normally"
  id2="$(emit_closed E2E-PLAN-2)"
else
  chmod a-w "$NOTES_DIR"
  id2="$(emit_closed E2E-PLAN-2)"
  [ "$(new_files | grep -c .)" = 1 ] || fail "a note appeared in a read-only folder"
  [ "$(status_field 'row["pending"]["event_id"], row["pending"]["attempts"], row["lag"]')" = "$id2 1 1" ] \
    || fail "the cursor did not stand on the failed event: $(status_field 'row')"
  if aicore events deliver --project "$PROJECT" >/dev/null 2>&1; then fail "a delivery to a read-only vault folder succeeded"; fi
  [ "$(status_field 'row["pending"]["attempts"]')" = 2 ] || fail "the failed delivery was not counted: $(status_field 'row')"
  chmod u+w "$NOTES_DIR"
  aicore events deliver --project "$PROJECT" >/dev/null || fail "the delivery after the folder became writable"
  say "ok: a failed delivery was retried by the cursor"
fi
[ "$(status_field 'row["lag"], row["pending"], row["dead_letters"]')" = "0 None 0" ] || fail "delivery is not caught up at the end"

# --- 4. the result: exactly two notes, only in the notes folder, nothing else in the vault changed ---------------
created="$(new_files)"
[ "$(printf '%s\n' "$created" | grep -c .)" = 2 ] || fail "expected exactly two new files, got: $created"
snapshot "$WORK/now.sum"
changed="$(comm -23 <(sort "$WORK/before.sum") <(sort "$WORK/now.sum") | wc -l)"
[ "$changed" = 0 ] || fail "$changed files that existed before were changed or removed"
ids=""
while IFS= read -r file; do
  file="${file#./}"
  [ "$(dirname "$file")" = "$(dirname "$note1")" ] || fail "a note is outside the notes folder: $file"
  ids="$ids $(note_event_id "$file")"
done <<< "$created"
[ "$(printf '%s\n' $ids | sort | tr '\n' ' ')" = "$(printf '%s\n' "$id1" "$id2" | sort | tr '\n' ' ')" ] \
  || fail "the notes do not carry the event ids $id1 $id2 (found:$ids)"

# --- 5. brain.note.created in the journal with the causation -----------------------------------------------------------
aicore events list --project "$PROJECT" --type brain.note.created --json | python3 -c '
import json, sys
events = json.load(sys.stdin)["events"]
want = sorted(sys.argv[1:])
got = sorted(e.get("causationid", "") for e in events)
sys.exit(0 if got == want else "brain.note.created causation ids %s, expected %s" % (got, want))' "$id1" "$id2" \
  || fail "brain.note.created events"
say "ok: two notes, nothing else changed, brain.note.created announced with causation"

printf '%s\n' "$VAULT/$note1"
while IFS= read -r file; do
  [ "${file#./}" = "$note1" ] || printf '%s\n' "$VAULT/${file#./}"
done <<< "$created"
