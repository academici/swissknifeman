# Supervisor Run Contract v1

## Status, authority, and version

`supervisor-run-v1` is frozen at `1.0.0`. It owns durable supervisor-run identity,
the event journal, public-boundary ordering, replay, and recovery outcomes. It does
not own the six plan statuses, Task Contract predicates, the per-plan Task journal,
slice compilation, authority classification, provider envelopes, or economy rules.

Normative inputs:

- Artifex acceptance rubric v1, SHA-256
  `12d602038c54f5b9b07616e5a9f718be28c5192d29770a5862a21f79351577aa`;
- donor execution-state-machine-v1, SHA-256
  `73826b67750c461819cffe8d21336b7cc8de73c620867f8e13037223a8460df6`;
- historical artifex-run-folder v1, SHA-256
  `2dcb90a010995a98c68c6300925a699263dc9f795b0636729c37e3728f55c764`.

The donor item machine remains authoritative for plan-item lifecycle. This contract
records supervisor observations about a slice attempt and only terminally projects an
accepted result into the existing plan close protocol. It never edits a plan status as
part of replay and never treats a snapshot, worker, provider session, or Task journal
row as run authority.

## Immutable run identity and layout

One run occupies `runs/<run-id>/` and contains:

```text
run.json                 immutable identity and frozen input hashes
events.jsonl             canonical append-only replay authority
snapshot.json            atomic derived cache; disposable
writer.lock              exclusive writer identity
slices/<slice-id>/       immutable manifests and minimized evidence
backups/                  declared preimages needed by a rollback contract
```

`run.json` is a closed object with `schema_version`, `contract_version`, `run_id`,
`repository_root_hash`, `base_commit`, `plan_id`, `plan_hash`, `mandate_hash`,
`acceptance_hash`, `created_at`, and `redaction_policy_hash`. Every value is fixed
before the first intent. A mismatch on reopen is `RUN_IDENTITY_MISMATCH`; a missing
load-bearing hash is `INPUT_HASH_MISSING`. Neither condition may be repaired from
`snapshot.json`.

`slice_id` is stable across retries of the same compiled slice. `attempt` starts at 1
and increases only after a terminal no-effect or verified rollback. The idempotency key
is `sha256(run_id + "\0" + slice_id + "\0" + decimal_attempt + "\0" +
operation_hash)` and is reused for every observation or reconciliation of that attempt.
An already observed key with a different operation or payload is
`IDEMPOTENCY_COLLISION`; an identical duplicate is `DUPLICATE_EVENT` and cannot advance
state or accounting twice.

## Closed supervisor state and event sets

These names describe the supervisor attempt/run control plane, not plan-item statuses.

<!-- declared-set: states -->
```text
CREATED
READY
INTENT_DURABLE
BOUNDARY_ACTIVE
OBSERVED
VALIDATING
ACCEPTED
ROLLED_BACK
OWNER_ATTENTION
PROVIDER_UNAVAILABLE
BUDGET_EXHAUSTED
INCIDENT
COMPLETED
ABORTED
```

<!-- declared-set: events -->
```text
freeze_run
dispatch_ready
append_intent
boundary_started
append_observation
validation_green
validation_red
reconcile_preimage
reconcile_postimage
reconcile_partial
reconcile_third_state
source_drift
journal_invalid
provider_unavailable
budget_exhausted
owner_decision_continue
owner_decision_abort
finish_run
```

<!-- declared-set: refusal_reasons -->
```text
UNKNOWN_SCHEMA_VERSION
UNKNOWN_RECORD_KEY
UNKNOWN_STATE
UNKNOWN_EVENT
ILLEGAL_TRANSITION
RUN_IDENTITY_MISMATCH
INPUT_HASH_MISSING
SOURCE_DRIFT
LOCK_HELD
LOCK_IDENTITY_AMBIGUOUS
SEQUENCE_GAP
HASH_MISMATCH
CHAIN_MISMATCH
TRUNCATED_RECORD
REORDERED_RECORD
DUPLICATE_EVENT
IDEMPOTENCY_COLLISION
OBSERVATION_WITHOUT_INTENT
POSTIMAGE_THIRD_STATE
PARTIAL_UNRECOGNIZED
BACKUP_MISSING
BACKUP_HASH_MISMATCH
ORPHAN_IDENTITY_AMBIGUOUS
REDACTION_VIOLATION
BUDGET_LIMIT
OWNER_DECISION_REQUIRED
```

The machine form is `artifacts/P1/supervisor-run-cases-v1.json::state_rules`.
For every declared state it lists all legal events and one state-specific
`otherwise` refusal. The validator expands the full state/event cartesian product;
each cell must resolve exactly once. A state or event outside the declared set has its
dedicated refusal and is never absorbed by `ILLEGAL_TRANSITION`.

Load-bearing legal path:

```text
CREATED --freeze_run--> READY
READY --append_intent--> INTENT_DURABLE
INTENT_DURABLE --boundary_started--> BOUNDARY_ACTIVE
BOUNDARY_ACTIVE --append_observation--> OBSERVED
OBSERVED --validation_green--> ACCEPTED
ACCEPTED --dispatch_ready--> READY
ACCEPTED --finish_run--> COMPLETED
```

`validation_red` never accepts. It enters `ROLLED_BACK` only after exact preimage
restoration is verified; otherwise the evidence event is `reconcile_third_state` and
the next state is `INCIDENT`. `owner_decision_continue` is a recorded authority input,
not an inferred choice; P1.3 owns whether such a decision is legally available.

## Canonical journal record and append protocol

Each non-empty UTF-8 line of `events.jsonl` is one closed JSON object with exactly:

```text
schema_version seq prev_hash record_hash ts run_id slice_id attempt event
state_before state_after idempotency_key input_hashes evidence redaction
```

`schema_version` is `supervisor-run-event-v1`; `seq` begins at 1 and increments by
one; the first `prev_hash` is 64 zeroes. `input_hashes`, `evidence`, and `redaction`
are closed JSON objects defined by the producing P1.2/P1.4 contracts; until those
contracts exist they may be empty but may not be omitted or contain raw provider data.
`slice_id` and `idempotency_key` are null only for run-level `freeze_run` and
`finish_run`. `attempt` is null for the same run-level events and otherwise is an
integer greater than zero.

`record_hash` is SHA-256 of canonical UTF-8 JSON for the same record with
`record_hash` omitted: keys sorted, no insignificant whitespace, Unicode preserved,
and JSON numbers limited to integers. Replayers stream lines, reject a blank line,
invalid UTF-8, malformed/truncated JSON, unknown key/version/event/state, a sequence
gap, reordered record, bad previous hash, bad record hash, or an illegal transition
at the first offending byte/record. They never skip a tail or continue from snapshot.

One writer owns a run. Before replay or append it atomically creates `writer.lock`
with run ID, process identity, and a random nonce, then verifies that same identity
after acquisition. An existing lock is `LOCK_HELD`; an unverifiable or apparently
stale owner is `LOCK_IDENTITY_AMBIGUOUS`, not permission to delete the lock. Removal is
allowed only by the exact owner after the final append or by a separately authorized
reconcile action.

For every provider, filesystem, Git, validation, or plan-bookkeeping boundary:

1. verify the lock, immutable run/input/source hashes, authority, and remaining budget;
2. append `append_intent` with operation/preimage/approved-postimage/rollback hashes;
3. flush, `fsync`, close, reopen, stream-verify the complete chain and exact tail;
4. perform exactly one named boundary;
5. append a minimized `append_observation`, then repeat flush/close/reopen/verify;
6. execute independent validation against the observed postimage;
7. append `validation_green` or `validation_red`, durably verify it, and only then
   expose acceptance, rollback, owner attention, or a terminal failure.

An `append_observation` without a durable matching intent is
`OBSERVATION_WITHOUT_INTENT`. A worker/provider statement, zero exit, session ID, or
filesystem timestamp is evidence only and cannot synthesize an intent or acceptance.

## Snapshot and plan-journal projection

`snapshot.json` is rebuilt exclusively by replaying a verified `events.jsonl`. It is
written to a same-directory temporary file, flushed and fsynced, atomically renamed,
and followed by a parent-directory fsync where supported. A missing, stale, malformed,
or hash-mismatched snapshot is discarded. It never repairs or truncates the journal.

`packages/task/lib/task/journal.py` remains the owner of the per-plan execution
history. The supervisor writes or triggers a Task journal row only at the existing
plan-command boundary, with `run_id` linkage, after its own accepted evidence is
durable. Crash recovery replays `events.jsonl`; it does not infer run state from a Task
journal row and does not duplicate a terminal row already written by the worker.

## Resume and exact reconciliation

Resume acquires the writer lock, verifies `run.json`, stream-verifies the entire event
chain, rebuilds state, checks source/input hashes, and reconciles every intent without
a terminal validation outcome before dispatching new work.

| Observed boundary state | Required evidence | Outcome | Retry/public call |
|:--|:--|:--|:--|
| exact approved postimage | approved postimage hash and matching idempotency identity | enter `VALIDATING`; rerun validation only | public call forbidden |
| exact preimage / proven no effect | preimage hash, no owned live process, no external effect | append no-effect observation, enter `ROLLED_BACK` | new attempt allowed only within P1.3/P1.5 authority and budget |
| recognized partial | exact partial classifier plus verified whole-slice backup | restore the whole slice, verify preimage, enter `ROLLED_BACK` | no retry before verified rollback |
| any other postimage | observed digest differs from every frozen class | `POSTIMAGE_THIRD_STATE` → `INCIDENT` | forbidden |
| partial without valid backup | missing/mismatched backup or unknown partial | `BACKUP_MISSING`, `BACKUP_HASH_MISMATCH`, or `PARTIAL_UNRECOGNIZED` → `INCIDENT` | forbidden |

An exact owned orphan may be stopped only when the frozen authority contract permits
that signal and the process/session identity matches durable evidence. Ambiguous or
foreign identity is `ORPHAN_IDENTITY_AMBIGUOUS` → `OWNER_ATTENTION`; no replacement
worker starts. Source/plan/mandate/acceptance drift before any intent refuses the
pending dispatch as `SOURCE_DRIFT`; after intent it enters `INCIDENT`. Recompilation is
a later explicit P1.2 transition and never changes an in-flight attempt in place.

Every crash cut in the append protocol has one result: before durable intent, no
boundary is authorized; after intent/before boundary, reconcile exact preimage; during
or after boundary/before observation, inspect pre/post/partial/third state; after
observation/before validation, validate the recorded postimage; after validation/before
projection, replay the verified decision and idempotently perform only missing plan
bookkeeping.

## Retention and redaction

Committed or durable evidence may contain typed state/event/reason names, stable IDs,
hashes, counts, exit classes, bounded diagnostics, and explicit unknown reasons. It may
not contain credentials, environment values, raw prompts, transcripts, private
reasoning, raw tool/provider payloads, cookies, authorization headers, or filesystem
contents beyond declared minimized artifacts. Minimization occurs before append;
`REDACTION_VIOLATION` prevents the line from becoming durable and enters `INCIDENT` if
the prohibited payload crossed a public boundary. Hashes of secrets are also forbidden.

Retention is by whole run and follows repository/owner policy. Deleting an accepted
run before all consumers and audits release its hashes is an owner boundary. Redaction
never rewrites `events.jsonl`; an exposed secret requires incident handling and key
rotation outside this contract.

## Compatibility, SemVer, and consumers

- major: add/remove/rename a state, event, refusal reason, required record key, hash
  algorithm, canonicalization rule, or recovery outcome;
- minor: add an optional evidence object defined by a later contract without changing
  replay or an existing outcome;
- patch: clarify prose or diagnostics without changing machine cases.

Unknown major/minor schema versions fail closed. Consumers pin both version and content
hash. P1.2 consumes run/slice/attempt/input identities; P1.3 consumes owner/budget and
reconcile boundaries; P1.4 carries minimized observations; P1.5 derives counters;
P2 implements store/replay; P3 binds provider activity; P4 proves fault/security
behaviour; P5 uses accepted run evidence; P6 may promote only without weakening this
contract.

The executable conformance carrier is
`artifacts/P1/validate-supervisor-run.py`; the independent expected cases are
`artifacts/P1/supervisor-run-cases-v1.json`; the live-driver ownership verdict is
`research/10-harness-run-gap-crosswalk.md`.
