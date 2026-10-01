# Plan authority resolver

`task.plan_authority` is the P5 runtime implementation of the frozen
`decision-request` and `authority-frame` v1 contracts. It is stdlib-only and never
imports or calls a model client.

`load_frame()` loads `packages/task/configs/authority-frame.json` (or the explicit
`TASK_AUTHORITY_FRAME` path), validates its deny-by-default form, and pins the
SHA-256 of its exact bytes. A missing or invalid file raises `AuthorityFrameError`;
there is no fallback frame.

`evaluate(request)` is the explicit diagnostic evaluator and returns a typed
`Verdict`: `delegated`, `approval_required`, or `denied`. Enforced `authorize()`
requires `DurableAuthorityStore`; until a real repository analyzer is installed it
routes every constructive action to approval. Caller-created `ObservedAction` values
are diagnostic and cannot delegate. The `constructive` class is the only delegable class. Aggregation is
durable across restarts and serialized over `(plan_id, item_id, decision_class)`.

`auto_answer_clarification()` answers only the closed question classes
`plan_carrier`, `repository_config`, `frozen_contract`, and `git_revision`; each
needs a named source record and emits provenance plus the mandatory reclassification.
`apply_response()` recomputes policy/action digests immediately before application,
rejects mismatches with `action_version + 1`, rejects missing clarification
reclassification/provenance, and in enforced mode makes every owner response
single-use through `DurableAuthorityStore`. `ResponseStore` and `CommitmentStore`
remain explicitly diagnostic-only compatibility helpers.

For a rollout observation without side effects:

```bash
PYTHONPATH=packages/task/lib python3 -m task.plan_authority --shadow < request.json
```

The output is `would_verdict` and never records a commitment. The plan-local durable
store uses an inter-process lock and atomic replace with file/directory fsync. It is
still writable by the local agent principal and is a workflow/replay guard, not an
authentication root.

Item execution additionally supports an optional exact `Authority` field:
`[OWNER-GATE:GATE-ID] branch=\`branch\`; scope=\`finite-scope\``. The Task Contract compiler discovers
it without caller transition kwargs; known legacy durable-owner-authorization prose without this
machine gate returns `AUTHORITY_CONTRACT_GAP`. The migration diagnostic deliberately recognizes
only the published English/Russian legacy phrases and never decides or grants authority from prose.
The default boundary is `provider-proof`. It requires an exact `provider-attestation/v1`
verified by a provider-owned verifier and independent nonce consumer. Capability preflight runs
before owner-message capture and returns `AUTHORITY_PROVIDER_UNAVAILABLE` when that channel is
absent. A fresh session cannot add a missing capability. Current Codex/Claude adapters do not
provide this strict channel; strict execution remains fail-closed.

Bounded local development can explicitly declare:

```markdown
**Authority:** [OWNER-GATE:GATE-ID] branch=`source-edit`; scope=`two migration sources`; boundary=`owner-session`; effect=`local-source`; environment=`corex_test`
```

`environment` accepts `checkout` or a named `*_test` target. Production DDL, deploy, release,
fleet and secret operations require a separate `provider-proof` item. Local validation must
use the declared target; known live commands/non-test targets are rejected. This is a workflow
guard for declared work, not a shell sandbox or authentication proof.

`materialize_owner_invocation()` captures the exact owner invocation in the current provider
session. An `owner-session` grant carries unsigned `workflow-guard` provenance, the original
message digest and a one-time activation key. It binds the item, gate, branch, scope, Files,
Validation, Implementation Rules and included/excluded scope. Additive same-session messages
preserve the original invocation; explicit revoke/stop/cancel or another Task invocation
invalidate it. A matching retry reuses its Decision Log entry. Changing the bound declaration,
switching sessions, revocation or terminal item status closes the grant. Activation is persisted
last, after carrier/view/bundle validation. No local grant satisfies `provider-proof`.
An altered scope, branch or item, discontinuous Decision Log, revocation or ambiguous grant fails
closed. Generated bundles carry the gate plus digest-qualified grant/message/revocation paths.

External/calendar waits use `waiting-external`, a durable checkpoint and a complete observation
window/predicate/continuation record. Calendar admission preserves the original start; it permits
continuation only after actual observed time and the external predicate, while terminal Acceptance
still requires its original evidence. The terminal lease returns `WAITING_EXTERNAL` for a pause.
