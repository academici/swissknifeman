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

Item execution additionally supports an optional exact `Authority` field:
`[OWNER-GATE:GATE-ID] branch=\`branch\`; scope=\`finite-scope\``. The Task Contract compiler discovers
it without caller transition kwargs; known legacy durable-owner-authorization prose without this
machine gate returns `AUTHORITY_CONTRACT_GAP`. The migration diagnostic deliberately recognizes
only the published English/Russian legacy phrases and never decides or grants authority from prose.
`materialize_owner_invocation()` captures the current provider's user message itself and appends
the existing brief owner-message / accepted exact item Decision Log grant carriers. It accepts no
caller evidence or authority override; the provider CLI route fallback cannot mint a grant.
An altered scope, branch or item, discontinuous Decision Log, revocation or ambiguous grant fails
closed. Generated bundles carry the gate plus digest-qualified grant/message/revocation paths.

External/calendar waits use `waiting-external`, a durable checkpoint and a complete observation
window/predicate/continuation record. Calendar admission preserves the original start; it permits
continuation only after actual observed time and the external predicate, while terminal Acceptance
still requires its original evidence. The terminal lease returns `WAITING_EXTERNAL` for a pause.
