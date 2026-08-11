# Plan authority resolver

`task.plan_authority` is the P5 runtime implementation of the frozen
`decision-request` and `authority-frame` v1 contracts. It is stdlib-only and never
imports or calls a model client.

`load_frame()` loads `packages/task/configs/authority-frame.json` (or the explicit
`TASK_AUTHORITY_FRAME` path), validates its deny-by-default form, and pins the
SHA-256 of its exact bytes. A missing or invalid file raises `AuthorityFrameError`;
there is no fallback frame.

`evaluate(request)` returns a typed `Verdict`: `delegated`, `approval_required`, or
`denied`. `authorize()` is the sole adapter boundary and records a delegated request
only in a supplied item-lifetime `CommitmentStore`. The `constructive` class is the
only delegable class. Its scope, frozen-contract, closed-set, reversibility, and
decision-record predicates are derived from typed `action` fields and evaluated over
the aggregation key `(plan_id, item_id, decision_class)`.

`auto_answer_clarification()` answers only the closed question classes
`plan_carrier`, `repository_config`, `frozen_contract`, and `git_revision`; each
needs a named source record and emits provenance plus the mandatory reclassification.
`apply_response()` recomputes policy/action digests immediately before application,
rejects mismatches with `action_version + 1`, rejects missing clarification
reclassification/provenance, and makes a response single-use through `ResponseStore`.

For a rollout observation without side effects:

```bash
PYTHONPATH=packages/task/lib python3 -m task.plan_authority --shadow < request.json
```

The output is `would_verdict` and never records a commitment. P5.4 owns durable
requests, append-only auto-answer events, and persistent response/commitment stores.
