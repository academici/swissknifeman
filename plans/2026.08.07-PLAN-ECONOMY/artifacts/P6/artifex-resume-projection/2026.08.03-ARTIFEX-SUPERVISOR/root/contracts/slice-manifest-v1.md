# Slice Manifest Contract v1

## Status, authority, and version

`slice-manifest-v1` is frozen at `1.0.0`. It owns the immutable compilation result
that maps one detailed, ready plan item to one bounded supervisor slice. It owns the
slice key set, dependency/readiness graph, source pins, compile refusals, and
pending-only supersession. It does not own plan status, Task Contract predicates,
execution-policy ceilings, provider argv/results, worker acceptance, or authority
classification.

Normative upstream references are additive and remain owned by their sources:

- `task-contract/v1`: goal, scope, public acceptance, route, capabilities,
  portability, and the pre-mutation verdict; a slice pins its content hash and never
  recomputes a competing predicate;
- `supervisor-run-v1` `1.0.0`: run/slice/attempt/idempotency identity and durable
  dispatch/recovery ordering;
- `execution-policy-v1` `1.0`: the fleet parallel ceiling and role/delegation policy;
- Artifex acceptance rubric v1, SHA-256
  `12d602038c54f5b9b07616e5a9f718be28c5192d29770a5862a21f79351577aa`.

Consumers pin both `manifest_version` and `content_hash`. A major change adds,
removes, or renames a required key, lifecycle, operation, or refusal outcome; a minor
change adds an optional evidence field without changing an old outcome; a patch
clarifies prose or diagnostics only.

## Closed top-level manifest

<!-- declared-set: manifest_keys -->
```text
schema_version
manifest_version
slice_id
plan_id
item_id
revision
content_hash
supersedes
lifecycle
source_hashes
task_contract
run
scope
dependencies
route
references
budgets
execution
```

`schema_version` is `slice-manifest-v1`; `manifest_version` is `1.0.0`.
`slice_id` is stable for one plan/item/revision. `revision` starts at 1.
`content_hash` is SHA-256 of canonical JSON for the complete manifest with
`content_hash` omitted: sorted keys, UTF-8, no insignificant whitespace, Unicode
preserved. `supersedes` is null on revision 1 and the prior manifest content hash on
a legal replan revision.

Every nested object is closed:

- `source_hashes`: exactly `repository_root`, `base_commit`, `plan`, `phase`,
  `item`, `handoff`, `task_contract`, `execution_policy`; every value is a lowercase
  64-hex digest observed before dispatch;
- `task_contract`: exactly `schema_version`, `content_hash`, `pre_mutation`,
  `public_acceptance_ids`; schema is `task-contract/v1`, the content hash equals
  `source_hashes.task_contract`, `pre_mutation` must be literal `allow`, and the
  ordered non-empty acceptance IDs are references, not copied predicates;
- `run`: exactly `contract_id`, `contract_version`, `contract_hash`, `run_id`,
  `attempt`, `idempotency_key`; contract identity is `supervisor-run-v1/1.0.0`,
  attempt is positive, and both hashes follow its frozen identity rules;
- `scope`: exactly `required_reads`, `files`, `validation`, `deliverables`,
  `evidence_refs`; all arrays are non-empty, ordered, duplicate-free. Paths are
  repo-relative execution inputs, and evidence refs equal the Task Contract public
  acceptance IDs without reinterpreting them;
- each `dependencies` row is exactly `item_id`, `required_lifecycle`,
  `manifest_hash`; lifecycle is `accepted`, the dependency exists, is terminally
  accepted at that exact manifest hash, and the whole graph is acyclic;
- `route`: exactly `model_class`, `effort`, `exec`, `capabilities`; class/effort and
  capability support are copied from the Task Contract. `exec` is the plan's exact
  `manual|plan-exec`; `plan-design` is never dispatchable. A manual-derived route
  (`frontier` or effort above `medium`) cannot carry `plan-exec`; the compiler does
  not fall back from `manual` to `plan-exec`;
- `references`: exactly authority/output contract ID, version, and hash pairs. P1.3
  and P1.4 own their semantics; the manifest only pins the versions used by a worker;
- `budgets`: exactly `max_attempts`, `max_auto_fix_attempts`,
  `max_parallel_workers`, `timeout_seconds`, `token_limit`,
  `token_limit_unknown_reason`. Numeric ceilings are positive, auto-fix does not
  exceed total attempts, and parallelism cannot exceed the live execution-policy
  fleet cap. A null token limit requires a non-empty unknown reason and never means
  zero or unlimited;
- `execution`: exactly `operations`, `writer_mode`, `worktree_mode`,
  `integration_mode`. The three mode values are fixed below.

## Lifecycle, operations, and ownership

<!-- declared-set: lifecycle -->
```text
pending
dispatched
observed
accepted
refused
superseded
```

The manifest is frozen after compilation. Lifecycle is an observation in the
supervisor journal, not a mutable status field in the file; the field records the
state at which this immutable revision was emitted. Only `pending` may be superseded.
`dispatched`, `observed`, `accepted`, `refused`, and `superseded` revisions are never
rewritten or recompiled in place.

<!-- declared-set: operations -->
```text
compile_slice
supersede_pending
dispatch_worker
validate_result
integrate_owned_delta
project_plan_bookkeeping
```

These IDs are the stable operation vocabulary P1.3 classifies. P1.2 assigns no
AUTO/AUTO-FIX/OWNER result. `writer_mode` is `one-writer`, `worktree_mode` is
`current-or-owned-linked`, and `integration_mode` is `serialized`. Parallel workers
are legal only for independently proven read-only work or distinct owned linked
worktrees; integration and plan projection are always serialized.

## Deterministic compilation

Compilation proceeds in this order and the first refusal wins:

1. require the closed schema and a detailed, ready, non-skeleton plan item;
2. verify the Task Contract hash and literal pre-mutation `allow` without re-running
   or translating its reason codes;
3. resolve the complete dependency graph, reject unknown/non-accepted/hash-drifted
   predecessors, then produce a lexical tie-broken topological order;
4. require a resolved route/Exec pair and only `native|adapted` capabilities;
5. preserve the ordered Task Contract reads/files/validation/deliverables/evidence,
   rejecting missing, absolute, home-rooted, parent-escaping, temporary, or URL inputs;
6. compare every source pin to the current pre-dispatch digest;
7. apply budget, execution-policy, one-writer, worktree, and serialized-integration
   ceilings;
8. canonicalize and hash the manifest, then append the durable dispatch intent before
   any worker or public side effect.

The compiler never parses a prose worker result, derives expected outcomes from a
fixture, or treats an absent capability/hash/value as a default. Sorted graph traversal
is a determinism rule, not an authorization rule.

## Closed compile refusals

<!-- declared-set: refusal_reasons -->
```text
UNKNOWN_SCHEMA_VERSION
UNKNOWN_MANIFEST_KEY
MANIFEST_HASH_MISMATCH
SKELETON_ITEM
TASK_CONTRACT_BLOCKED
TASK_CONTRACT_HASH_MISMATCH
DEPENDENCY_UNKNOWN
DEPENDENCY_NOT_TERMINAL
DEPENDENCY_HASH_MISMATCH
DEPENDENCY_CYCLE
ROUTE_UNRESOLVED
ROUTE_EXEC_MISMATCH
SLICE_INPUT_MISSING
SLICE_INPUT_EXTERNAL
SOURCE_DRIFT
CAPABILITY_UNSUPPORTED
BUDGET_INVALID
PARALLEL_CEILING_EXCEEDED
WRITER_MODE_UNSAFE
REPLAN_NON_PENDING
REPLAN_SUPERSEDES_REQUIRED
```

`TASK_CONTRACT_BLOCKED` carries the exact upstream `block:<CODE>` as diagnostic data;
it does not re-mint `ROUTE_UNDERSHOOT`, `AUTHORITY_BOUNDARY`, portability, conflict,
slice, or cold-start predicates. `SLICE_INPUT_*` applies to the compiler's materialized
ordered bundle after the upstream contract allowed. `SOURCE_DRIFT` compares pins only;
it never repairs them. Unknown states or capabilities fail closed.

## Pending-only replan

A replan is legal only when the prior manifest lifecycle is `pending`, the new
revision is greater than 1, and `supersedes` equals the exact content hash of the prior
pending revision. The supervisor appends a `supersede_pending` event before publishing
the new hash. The old manifest and all journal events remain. A dispatched or terminal
slice is reconciled under `supervisor-run-v1`; it is never recompiled to erase an
attempt, dependency, source drift, or acceptance result.

## Executable conformance carrier

`artifacts/P1/slice-manifest-cases-v1.json` contains one neutral base manifest,
independent field mutations and dependency graphs. The validator
`artifacts/P1/validate-slice-manifest.py` evaluates fields and graphs without branching
on fixture IDs, verifies the closed declared sets above, loads the live
`execution-policy.json` only for its existing fleet ceiling, and reports every tested
allow/refusal count. A green fixture bank proves contract form and total named cases;
it does not prove a future runtime obeyed the contract.
