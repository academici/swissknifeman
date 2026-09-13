---
description: "Execute declared plan item(s) through the shared Task lifecycle."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
model: sonnet
effort: medium
---
Execute the admitted Routing group or ready subset of a recommended group for `$ARGUMENTS`. The pinned route is a minimum;
provider-attested overshoot is recorded and undershoot stops before mutation.
Activation follows explicit owner plan intent or an exact cited local workflow policy in the
shared [intent routing canon](../references/intent-routing.md).

## Shared lifecycle

`task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` is advisory impact selection. It owns no carrier or enum: admission
stays in `task.plan_admission`/`task_contract`, route proof in `route_evidence`, recovery in
`plan_repair`/`plan_blocking`, review in `review_policy`/`plan_gates`, projection in
`plan_projection`, context in `plan_continuity`, and semantic Next/delivery in `plan_delivery`.
Commands must not copy those algorithms. Choose any safe order consistent with their data
dependencies, Scope and Acceptance; recommended Next is not exclusive execution authority.

1. Capture exactly the v2 five-carrier context once with `task.plan_context.capture()` and consume
   contiguous terminal-marked chunks. Missing or changed input is `PLAN_CONTEXT_TRUNCATED` or
   `PLAN_CONTEXT_DIGEST_MISMATCH` before journal mutation.
   The ordered carriers are `plans/<PLAN-ID>/plan.md` → `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md` →
   `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md` → `plans/<PLAN-ID>/bundles/<Pn.m>.json` →
   `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md`.
2. Capture provider route and call `batch_admission`; unknown route is `ROUTE-UNVERIFIABLE`, not an
   item attempt. Start one route-run receipt and reuse it until `route_change_boundary()` proves a change.
   Before journal or product mutation, compile `task.plan_evidence.compile_graph()` from the item
   spec and bundle, then pass it to `task_contract.pre_mutation()`. A real digest-input/write
   collision is `SELF_INVALIDATING_EVIDENCE_ANCHOR`: split product and closure anchors; otherwise
   collapse them into one anchor.
   After normal admission and before the first product write, call
   `plan_recovery.start(plan_dir, item_id, command=command, actor=actor, session_id=session_id,
   contract=contract, batch_receipt=batch_receipt)` and retain its durable run ID/attempt.
   An interrupted resume reuses that run without appending a second start; an independent ready
   successor may proceed only after recovery preflight proves its dependencies satisfied.
   If journal start survived interruption before state projection, regenerate that owning state
   before recapture; reuse the journal identity. After terminal evidence and any inline phase closure,
   call `plan_recovery.materialize_next_ready(plan_dir, item_id)` before delivery so a newly ready
   successor receives its generated bundle.
3. Implement only Scope Included. Ordinary low-risk work uses a self-check and affected tests;
   bounded integration adds the necessary package/integration check. Independent review requires a
   concrete item risk—security/auth, destructive migration, irreversible external action,
   payment/accounting, concurrency/shared state, public API/schema, low-confidence impact, or release
   authority—or an explicit owner requirement. Uncertainty gathers evidence; it does not default to
   full review.
4. A foreign baseline stays visible but non-gating unless ownership/dependency closure intersects.
   Audit is read-only: it returns one owning continuation for a product finding and never starts a
   second audit/full replay without a new material hypothesis.
5. After GREEN acceptance, persist evidence and the terminal journal event, generate changed terminal
   projections once, and close the item in this invocation. If this is the last item, phase gates are
   GREEN, and no audit was explicitly admitted, create its phase closure before deriving Next. Derive and validate
   one semantic Next through `plan_delivery` from the resulting state and dependencies; never emit
   `plan-close` for the current result or repeat `plan-exec`/`plan-run` for the current item. Use one
   scoped commit. A second bookkeeping commit requires a real session/ownership boundary or
   digest-input collision.

Have current GREEN evidence for every declared Validation carrier. Evidence remains current only
while its relevant product/test/tool/config inputs and environment are unchanged; rerun the affected
delta after change and rerun a live gate at its live boundary. A closure/bookkeeping-only delta needs
one regeneration and structural check and does not invalidate independent product evidence. An
explicit Validation/security/release carrier remains binding until transparently amended through the
existing contract rules; do not silently skip it.

Close only with green evidence, `task_contract` allow at both write sites, generated views/lint, and
`plan-delivery --kind terminal`. For a terminal phase use `plan_assurance.evaluate()` through
`phase_audit_policy`: GREEN evidence direct-closes by default. An `audit-phase` Next requires an
explicit residual-risk question and fresh owner consent bound to the phase, candidate fingerprint,
and audit run; legacy `required`/`auto`/`light`, Routing Review, item count, integration seams, or risk
prose alone are advisory. Missing or RED evidence remains repair work for the current executor in
this invocation, never audit admission or a routine handoff to the repository owner. Ask the owner
only at a concrete authority or product-decision boundary.
Batch handoff retains its Batch, Context, and one provider-native launch block for the actual
post-closure successor.

## Terminal admission

After route/run admission, an applicable provider adapter may arm `terminal-admission-lease/v1`
through the worktree-local `plan-terminal-admission.py`; it refreshes only on material progress or
a typed `waiting-owner` or `waiting-external` decision. External waits preserve the observation
checkpoint and suppress terminal admission until actual time/predicate evidence allows continuation.
At a Stop boundary the adapter passes the typed P1.3 continuity
decision, rebuilt terminal receipt and in-memory proposed final fragment to
`terminal_admission.evaluate()`. `final_allowed=true` requires exact identity and byte-exact
`plan_delivery.required_final_message(receipt)`; no lease is `NOT_APPLICABLE`. The reducer stores
only hashes and reason codes. Providers render its verdict but never decide terminality.
