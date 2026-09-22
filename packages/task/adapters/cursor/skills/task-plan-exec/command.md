<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-exec.md
Canonical SHA-256: sha256:6ae5cf6c1db923a06372e0288222be13f94e4810b08c115838027b18d54ca111
Adapter: task.cursor-command/1.0.16
-->
## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ task:` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: economy=composer-2.5-fast, implementation=composer-2.5, frontier=claude-opus-5-thinking-high.

---
disable-model-invocation: true
description: "Execute authorized Task plan items using declared routing and inline closure."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
model: sonnet
effort: medium
---
Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/execution-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory execution context.

Execute the admitted Routing group or ready subset of a recommended group for `$ARGUMENTS`.
Undershoot stops before mutation; bounded pinned work also rejects unrequested expensive overshoot.
Activation requires an explicit owner Task invocation, as defined in the
shared [intent routing canon](../references/intent-routing.md).

## Continuous execution

After each GREEN item, close the item and any directly closable GREEN phase in this invocation,
then compute Next from the resulting state. Continue a compatible ready successor inside the
owner-authorized admitted scope in this root. Local reversible repair stays in this invocation.
If the owner requested only the completed scope, stop product writes and persist lifecycle
`scope-complete` with its checkpoint: the reducer retains `continue-root` with reason
`authorized-scope-complete`. A chat final reports the successor as a recommendation; it grants no
execution authority and does not require a new process. Never invent work when the objective is done.
An explicit request for a new session updates lifecycle to `owner-requested-new-session`; persist a
fresh post-close checkpoint and render exactly one native launch for that successor. A routine
item/phase transition or test failure does not imply a session boundary. A real external wait keeps
its time/predicate gate visible. Design-only/review-only requests remain separate deliverables.

## Shared lifecycle

`task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` is advisory impact selection. It owns no carrier or enum: admission
stays in `task.plan_admission`/`task_contract`, route proof in `route_evidence`, recovery in
`plan_repair`/`plan_blocking`, review in `review_policy`/`plan_gates`, projection in
`plan_projection`, context in `plan_continuity`, and semantic Next/delivery in `plan_delivery`.
Commands must not copy those algorithms. Choose any safe order consistent with their data
dependencies, Scope and Acceptance; recommended Next is not exclusive execution authority.

1. Call `scripts/plan-work.py prepare --plan-dir <dir> --item <Pn.m> --command plan-exec
   --actor <actor> --session-id <session>` once. It owns recovery, route capture, snapshot validation,
   batch admission, evidence graph, `task_contract.pre_mutation()` and durable start. Consume its
   compact execution capsule; full plan/phase/bundle/state are internal runtime inputs.
   `PLAN_CONTEXT_TRUNCATED` and `PLAN_CONTEXT_DIGEST_MISMATCH` still block before product writes.
2. Retain the returned run identity and route-run receipt. A retry reuses the durable start;
   a changed route or scope needs fresh admission. Open full carriers only for a named ambiguity
   or diagnostic. A real `SELF_INVALIDATING_EVIDENCE_ANCHOR` requires separate anchors; routine
   bookkeeping does not. Do not repeat preflight merely because the workflow advances a step.
3. Implement only Scope Included. Ordinary low-risk work uses a self-check and affected tests;
   bounded integration adds the necessary package/integration check. Independent review requires a
   concrete item risk—security/auth, destructive migration, irreversible external action,
   payment/accounting, concurrency/shared state, public API/schema, low-confidence impact, or release
   authority—or an explicit owner requirement. Uncertainty gathers evidence; it does not default to
   full review.
4. A foreign baseline stays visible but non-gating unless ownership/dependency closure intersects.
   Audit is read-only: it returns one owning continuation for a product finding and never starts a
   second audit/full replay without a new material hypothesis.
5. After GREEN acceptance, persist evidence and the terminal journal event, then call
   `scripts/plan-work.py finalize --plan-dir <dir> --item <Pn.m>` to converge changed terminal projections, the
   selected successor bundle, freshness and delivery receipt. Close the item in this invocation. If this is the last item, phase gates are
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
