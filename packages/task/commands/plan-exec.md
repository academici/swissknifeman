---
description: "Execute declared plan item(s) through the shared Task lifecycle."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
model: sonnet
effort: medium
---
Execute the admitted Routing group or ready subset of a recommended group for `$ARGUMENTS`. The pinned route is a minimum;
provider-attested overshoot is recorded and undershoot stops before mutation.

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
3. Implement only Scope Included. Select focused validation by default; bounded integration adds
   affected-package validation; security/auth, destructive migration, irreversible external action,
   payment/accounting, concurrency/shared state, public API/schema, low-confidence impact, or release
   authority widen to focused + affected-package + integration and independent review.
4. A foreign baseline stays visible but non-gating unless ownership/dependency closure intersects.
   Audit is read-only: it returns one owning continuation for a product finding and never starts a
   second audit/full replay without a new material hypothesis.
5. Generate only changed terminal projections once, persist one semantic Next through `plan_delivery`,
   and use one scoped commit. A second bookkeeping commit requires a real session/ownership boundary or digest-input collision.

Run every declared Validation carrier. Close only with green evidence, `task_contract` allow at both
write sites, generated views/lint, and `plan-delivery --kind terminal`. For a terminal phase use
`plan_assurance.evaluate()` through `phase_audit_policy` to choose `audit-phase` or `close`; Routing
Review and item count do not manufacture phase risk. Batch handoff retains
its Batch, Context, and one provider-native launch block.

## Terminal admission

After route/run admission, an applicable provider adapter may arm `terminal-admission-lease/v1`
through the worktree-local `plan-terminal-admission.py`; it refreshes only on material progress or
a typed `waiting-owner` decision. At a Stop boundary the adapter passes the typed P1.3 continuity
decision, rebuilt terminal receipt and in-memory proposed final fragment to
`terminal_admission.evaluate()`. `final_allowed=true` requires exact identity and byte-exact
`plan_delivery.required_final_message(receipt)`; no lease is `NOT_APPLICABLE`. The reducer stores
only hashes and reason codes. Providers render its verdict but never decide terminality.
