---
disable-model-invocation: true
description: "Execute authorized Task plan items under the current session route with inline closure."
argument-hint: "<PLAN-ID> <Pn | Pn.m [Pn.k]> [--reviewer <provider/model>] [--review-effort high]"
---
Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/execution-mode.md` from the configured Task package root.
Schema canon and snippets are on-demand references, not mandatory execution context.

Execute the admitted Routing group, or the ready subset of a recommended group, for `$ARGUMENTS`.
Activation requires an explicit owner Task invocation ([intent routing](../references/intent-routing.md)).
Run under the session's provider-attested route; never switch the model manually. The plan's Routing row sets
the minimum class/effort: a stronger model or higher effort is admitted and recorded as `over`, any
pool model covering the class is valid, a weaker one stops before mutation. The durable start binds
the route to `route-run-receipt/v1`; do not build a second route contract in the prompt.

`--reviewer <provider>/<exact-model-id>` is owner authorization to automatically review every
implementation item in the requested phase/workset before close. It selects only the reviewer,
not the executor; `--review-effort` defaults to high. Pass this selection to each item's `prepare`.
Selection accepts `provider/model[/context][/effort]`, with an optional trailing slash:
`grok/grok-4.7/500k/`, `grok/grok-4.7/high/`, `grok/grok-4.7/hight/`, or
`grok/grok-4.7/500k/high/`. Context and effort may appear in either order; `hight` means high,
and k/m mean decimal token counts. Parse via `task.review_packet`; preserve the original invocation
for route capture. A suffix sets effort unless a separate conflicting flag is supplied.
Context is a minimum required window, not a token-spend budget. The runner verifies provider
context evidence; unknown/insufficient capacity is a typed boundary, not a retry or fabricated success.
Selection is durable and survives resume without rewriting frozen specifications. Existing
`owner-review` requirements remain binding; conflicting selectors stop before product writes.
The root acts as orchestrator: it may launch a separate reviewer and consume its verdict, but it
may not act as that reviewer. No second owner command is needed on the supported Grok transport.
For a phase argument `Pn`, visit its dependency-ready admitted batches in order; never widen to
another phase. Pass `--phase Pn` to prepare so route capture retains the actual phase invocation
rather than inventing a different item-list command. Batch admission still owns each workset.

`prepare` is phase-scoped: only the phases of the requested items must be detailed; other phases may
stay skeletons or backlog. An undetailed target phase returns a typed refusal before the durable
start. Whole-plan design finish and GREEN design audit gate execution only when plan.md declares
`**Design Audit:** required`.

## Continuous execution

After each GREEN item, close the item and any directly closable GREEN phase in this invocation,
then compute Next from the resulting state. Continue a compatible ready successor inside the
owner-authorized admitted scope. Local reversible repair stays in this invocation.
If the owner requested only the completed scope, stop product writes and persist lifecycle
`scope-complete` with its checkpoint: the reducer retains `continue-root` with reason
`authorized-scope-complete`. A chat final reports the successor as a recommendation; it grants no
execution authority. Never invent work when the objective is done.
An explicit request for a new session updates lifecycle to `owner-requested-new-session`; persist a
fresh post-close checkpoint and render exactly one native launch for that successor. A routine
item/phase transition or test failure is not a session boundary. A real external wait keeps its
time/predicate gate visible. Design-only/review-only requests remain separate deliverables.
Stop only at a real owner/external boundary, a missing decision, or exhausted context.

## Shared lifecycle

`task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` is advisory impact selection. It owns no carrier or enum: admission
stays in `task.plan_admission`/`task_contract`, route proof in `route_evidence`, recovery in
`plan_repair`/`plan_blocking`, review in `review_policy`/`plan_gates`, projection in
`plan_projection`, context in `plan_continuity`, and semantic Next/delivery in `plan_delivery`.
Commands must not copy those algorithms. Choose any safe order consistent with their data
dependencies, Scope and Acceptance; recommended Next is not exclusive execution authority.

1. Call `scripts/plan-work.py prepare --plan-dir <dir> --item <Pn.m> --command plan-run
   --actor <actor> --session-id <session>` once. It owns recovery, route capture, snapshot validation,
   batch/authority admission, evidence graph, generated carriers, `task_contract.pre_mutation()` and
   durable start. Consume its compact execution capsule;
   full plan/phase/bundle/state are internal runtime inputs.
   With automatic review append `--reviewer <provider/model> [--review-effort <effort>]`; carry it
   across every requested item, not only the first. Retain the pre-implementation commit for review base.
   `PLAN_CONTEXT_TRUNCATED` and `PLAN_CONTEXT_DIGEST_MISMATCH` still block before product writes.
   For an explicitly granted separate repeat of a terminal solo item, pass
   `--repeat-admission <plan-owned JSON>`: the owner decision carries the exact marker
   `[REPEAT-ADMISSION:<digest>]` and `task.plan_repeat.build()` builds the contract (history, current
   admitted design scope, new run identity; standard route/authority/input gates stay). Without the grant a
   terminal item is not re-executed.
2. Retain the returned run identity and route-run receipt. A retry reuses the durable start;
   a changed route or scope needs fresh admission. Open full carriers only for a named ambiguity
   or diagnostic. A real `SELF_INVALIDATING_EVIDENCE_ANCHOR` requires separate anchors; routine
   bookkeeping does not. Do not repeat preflight merely because the workflow advances a step.
3. Implement only Scope Included. Ordinary low-risk work uses a self-check and affected tests;
   bounded integration adds the necessary package/integration check. Independent review requires a
   concrete item risk (security/auth, destructive migration, irreversible external action,
   payment/accounting, concurrency/shared state, public API/schema, low-confidence impact, or release
   authority) or an explicit owner requirement, and then it is a separate read-only review item of the
   plan (`Review Pn`), or an explicitly declared `owner-review: <provider/model>` carrier.
   Automatic owner review uses a fresh read-only reviewer session: prepare a bounded `review-packet`
   and call `review-run` once from this root for the selected Grok route. The durable prepare selection
   admits transport launch, not self-certification. Wait for the real receipt and keep product bytes
   stable until it returns. GREEN closes and continues. FINDINGS returns one owning correction:
   fix in scope, rerun affected checks, prepare the changed candidate and call one second review.
   Consume the shared reducer action; never start a third completed round, replace the reviewer,
   reset budgets or recursively delegate fix/re-review. Systemic repair addresses the shared model
   before that second review. An incomplete attempt is not a verdict: diagnose/repair the transport
   and retry at most once for that candidate. Budget exhaustion, missing capability or a true decision
   boundary persists the exact checkpoint; do not ask the owner between normal items or rounds.
   Other providers need an independently routed native review session and `review-record`; unavailable
   launch capability is explicit, never a silent Grok fallback. A standalone requested review remains
   a separate deliverable. Uncertainty gathers evidence; it does not
   default to full review. Never fabricate evidence or bypass those boundaries; existing dirty changes
   belong to the owner.
   For `risk-class: concurrency|transaction|auth|data-integrity`, compare the design's
   `invariant-model` against all affected paths/drivers and write the declared `self-check` before
   packet preparation. Record every known risk as fixed or deferred with an accepted owner D# or
   owning item and justification. Repeated systemic findings require a revised shared model and
   owning design question before another local patch. See the review-mode reference for exact
   carriers, verdict grammar and bounded exits.
4. A foreign baseline stays visible but non-gating unless ownership/dependency closure intersects.
   Audit is read-only: it returns one owning continuation for a product finding and never starts a
   second audit/full replay without a new material hypothesis.
5. After GREEN acceptance, persist evidence and the terminal journal event, then call
   `scripts/plan-work.py finalize --plan-dir <dir> --item <Pn.m>` once to converge changed terminal
   projections, the selected successor bundle, freshness and delivery receipt. Close the item in this
   invocation. If this is the last item, phase gates are GREEN, and no audit was explicitly admitted,
   create its phase closure before deriving Next. Derive and validate one semantic Next through
   `plan_delivery` from the resulting state and dependencies; never emit `plan-close` for the current
   result or repeat `plan-run` for the current item. Use one scoped commit. A second bookkeeping
   commit requires a real session/ownership boundary or digest-input collision.

Have current GREEN evidence for every declared Validation carrier. Evidence remains current only
while its relevant product/test/tool/config inputs and environment are unchanged; rerun the affected
delta after change and rerun a live gate at its live boundary. A closure/bookkeeping-only delta needs
one regeneration and structural check and does not invalidate independent product evidence. An
explicit Validation/security/release carrier remains binding until transparently amended through the
existing contract rules; never skip it silently.

Validation economy: run this item's affected commands. Broad suites (full root/package/DB/mutation/
replay) run once in the phase's review or last item, not in every item and not again in a replay;
a replay proves reproducibility (byte equality plus an environment witness) and does not repeat
behavioral suites. Write large logs/JSON to a file and read status, counts and the first few
diagnostics; never paste bulk output into the context.

Close only with green evidence, `task_contract` allow at both write sites, generated views/lint, and
`plan-delivery --kind terminal`. For a terminal phase use `plan_assurance.evaluate()` through
`phase_audit_policy`: GREEN evidence direct-closes by default. An `audit-phase` Next requires an
explicit residual-risk question and fresh owner consent bound to the phase, candidate fingerprint,
and audit run; legacy `required`/`auto`/`light`, Routing Review, item count, integration seams, or risk
prose alone are advisory. Missing or RED evidence remains repair work for the current executor in
this invocation, never audit admission or a routine handoff to the repository owner. Ask the owner
only at a concrete authority or product-decision boundary.
Batch handoff retains its Batch and Context; a fresh-session boundary carries one provider-native
launch block for the actual post-closure successor.

## Terminal admission

While the durable run is open, report partial progress through commentary and continue authorized
work. The enabled Stop adapter invokes `plan-terminal-admission.py check-open --project-root <cwd>
--provider-session <session>` before the optional lease check, including when the Stop payload has
no Task context. `TASK_OPEN_RUN_FINAL_FORBIDDEN` is repaired by continuing work or persisting a
legitimate terminal block/checkpoint; it never authorizes fabricated closure. Respect owner stop.

After route/run admission, an applicable provider adapter may arm `terminal-admission-lease/v1`
through the worktree-local `plan-terminal-admission.py`; it refreshes only on material progress or
a typed `waiting-owner` or `waiting-external` decision. External waits preserve the observation
checkpoint and suppress terminal admission until actual time/predicate evidence allows continuation.
At a Stop boundary the adapter passes the typed P1.3 continuity
decision, rebuilt terminal receipt and in-memory proposed final fragment to
`terminal_admission.evaluate()`. `final_allowed=true` requires exact identity and byte-exact
`plan_delivery.required_final_message(receipt)`; no lease is `NOT_APPLICABLE`. The reducer stores
only hashes and reason codes. Providers render its verdict but never decide terminality.

At final, always report the exact semantic Next from the receipt. Render the byte-exact shared final
fragment only for a terminal-admission lease, cross-session/provider handoff, owner/external wait,
or release/public boundary. Same-session local closure uses the internal receipt and a concise result.
