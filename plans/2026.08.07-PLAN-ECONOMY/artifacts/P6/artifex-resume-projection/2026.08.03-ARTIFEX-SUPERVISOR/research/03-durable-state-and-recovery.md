# Durable state and recovery

## Storage choice

Prototype uses one plan-local run directory:

```text
runs/<run-id>/
  run.json                 # immutable run identity and frozen inputs
  events.jsonl             # canonical hash-chained append-only journal
  snapshot.json            # atomic derived cache, never authority
  owner-queue.json         # derived ordered view
  slices/<slice-id>/...    # manifests, minimized provider evidence, validation results
  backups/...              # permission-restricted declared preimages when needed
```

No SQLite or external workflow engine is required. One exclusive writer owns journal appends;
readers may rebuild state by replay. Every JSON object uses a versioned schema, canonical encoding,
previous-record hash and stable event/run/slice/attempt IDs.

## Durable boundary protocol

For every worker dispatch, command, write, merge or plan-bookkeeping boundary:

1. validate frozen input/source/plan hashes and authority;
2. append `intent` with exact operation and idempotency key;
3. flush, `fsync`, close, reopen and verify chain/tail;
4. perform the one named public boundary;
5. append minimized `observation` with exit class and postimage references;
6. flush/reopen/verify again;
7. run independent deterministic validation;
8. append `accepted`, `rolled_back`, `owner_attention` or terminal failure.

Snapshot replacement is temp-file → flush/fsync → atomic rename → parent-directory durability where
supported. Snapshot mismatch never repairs the journal; it is discarded and rebuilt.

## Resume/reconcile algorithm

1. Acquire exclusive run lock and verify immutable run identity.
2. Stream-verify JSONL schema, sequence and hash chain; reject torn/reordered/unknown records.
3. Rebuild state and compare any snapshot.
4. Re-hash plan, mandate, slice and source inputs. Pending slices may be recompiled only through an
   explicit replan; in-flight/accepted slice drift refuses.
5. For every durable intent without terminal acceptance, inspect the declared side effect:
   - exact approved postimage → fresh validation, then accept;
   - exact preimage/no effect → record no-effect and retry only within budget;
   - recognized partial → whole-slice rollback, verify preimage, then retry/escalate;
   - any other state → incident/OWNER, no write.
6. Reconcile provider session/process identity. Orphan process is stopped only when the run mandate
   gives exact authority; otherwise freeze the slice and ask owner.
7. Continue the next ready slice only after all incomplete intents are reconciled.

## Required crash/fault matrix

- process death after every append and before/after every provider/public CLI boundary;
- duplicate event/dispatch/result delivery;
- truncated, reordered, unknown-version or hash-corrupted journal;
- stale snapshot and missing snapshot;
- source/plan/mandate drift;
- timeout, quota, approval denial, malformed output and output over cap;
- backup missing, rollback failure and third-state postimage;
- worktree conflict, foreign dirty delta and rejected integration;
- disk full/fsync/write failure and concurrent supervisor lock attempt.

RAG:✅ durable principles from Temporal/SQLite sources in findings/01; exact file/state design is internal and must be frozen by P1.1.
