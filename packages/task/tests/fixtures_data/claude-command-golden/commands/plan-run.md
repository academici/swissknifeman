---
disable-model-invocation: true
description: "Execute authorized Task plan items under the current session route with inline closure."
argument-hint: "<PLAN-ID> <Pn | Pn.m [Pn.k]> [--reviewer <provider/model>] [--review-effort high]"
---
Execute `$ARGUMENTS` in the owner-authorized scope. Use the existing `plan-work` facade;
its admission/reducers own route proof, checks, review and closure through `task_contract`. Runtime code is the source
of truth. Load schema, repeat, audit or cross-session references only for a named typed boundary.

1. Call `scripts/plan-work.py prepare --plan-dir <dir> --item <Pn.m> --command plan-run
   --actor <actor> [--session-id <session>]`. For a phase invocation pass `--phase Pn`; for
   multiple items pass the admitted `--request` and returned batch receipt. Pass the owner's
   `--reviewer <provider/model[/context][/effort]> [--review-effort <effort>]` when specified.
   Prepare captures the current provider-attested route and persists its `route-run-receipt/v1`,
   base commit, run context and pre-mutation admission. A stronger class/effort is recorded as
   over; a weaker or unknown route blocks. Do not export another route or reconstruct the contract.
   Consume the selected item capsule. `PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH`
   are errors; open full carriers only for the named ambiguity. Resume reuses the same durable run.
2. Implement the declared scope and acceptance. Run fast affected checks before expensive checks;
   finish generation before checking its outputs. Existing dirty changes retain their ownership.
   For systemic risk, complete the declared invariant-model/self-check. Ordinary low-risk work
   uses self-check and affected tests. Independent review requires an explicit owner request or a
   concrete risk: security/auth, destructive migration, irreversible external action,
   payment/accounting, concurrency/shared state, public API/schema, low-confidence impact,
   or release authority. A risk does not itself authorize a phase audit.
3. Call `plan-work.py validate --plan-dir <dir> --item <Pn.m> --attempt-id <unique-id>`.
   The runtime executes the declared Validation carriers in order, owns candidate-bound logs and
   contract receipts, stops after RED and returns `qualify` or `repair`. Project check definitions
   may add dependencies, environment and timeouts through `--checks`; acceptance carriers remain
   exact. Repair the failure and rerun affected evidence; retain all immutable attempts.
4. Call `plan-work.py close --plan-dir <dir> --item <Pn.m> [--note <result>]`.
   The runtime qualifies live bytes, write sites and required review, builds terminal evidence,
   appends once, regenerates views/continuity, and verifies delivery through `plan_delivery`.
   It returns `complete`, `repair`, or `review-ready`; do not write terminal JSON or Python helpers.
   For `review-ready`, call `plan-work.py review --plan-dir <dir> --item <Pn.m>`. Supported Grok
   transport starts one separate native read-only reviewer session with the exact selected route.
   Keep the candidate stable. Consume the reducer action: GREEN returns to close; FINDINGS means
   an owning fix, affected checks and the next review candidate. No unrequested reviewer or silent
   provider fallback. Other providers use the native independent review/record boundary.
   Use `review-status`, `review-cancel`, or `review-reconcile` with plan/item for an interrupted job;
   never launch another prompt while its outcome is unknown. Active review has no elapsed deadline
   or default turn cap. A cancelled review is not GREEN. Completed-round limits stay in review_policy.

Close each GREEN item in this invocation. Continue dependency-ready items within the admitted scope;
then report the receipt's semantic Next as a recommendation. Do not execute outside that scope.
Use one scoped commit. `finalize` resumes an already appended terminal through the same reducers.
Phase acceptance uses `phase_audit_policy`; an audit requires candidate/run-bound owner consent.
`plan-close` is whole-plan-only. Future-item read-budget/bundle debt is non-gating unless it affects
this item's dependency closure. Full-plan/fleet lint remains a release check.

`task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` is advisory; it grants no authority.
The enabled terminal-admission adapter owns Stop/lease checks. Continue an open authorized run,
honor an explicit owner stop, and retain actual external-wait evidence. A fresh-session/provider
handoff uses the returned typed continuity and native launch; ordinary item transitions need none.
Exceptional repeat and review contracts are in `runtime/plan-protocol/references/` on demand.
Large logs and manifests stay in artifacts; use compact tool results.
