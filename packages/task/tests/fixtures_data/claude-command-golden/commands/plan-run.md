---
description: "Execute authorized Task plan items with the attested current-session route."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
---
Read `runtime/plan-protocol/SKILL.md` from the configured Task package root (the same
root that contains `lib/task/`) before using the plan schema. Its adjacent `references/` and
`snippets/` are delivered on demand with Task; a separate CORE skill is not required.

Execute `$ARGUMENTS` by the canonical `task:plan-exec` lifecycle. `plan-run` inherits the current
provider-attested route; it never pins model or effort and it never substitutes config or prose for
route evidence. Capture five v2 carriers once, admit the Routing group or ready subset of a recommended group, persist one
`route-run-receipt/v1`, then reuse route/context evidence until `route_change_boundary()` proves change.

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

Activate only for explicit owner plan intent or an exact cited local workflow policy; use the
shared [intent routing canon](../references/intent-routing.md). An exact current owner `plan-run`
is intent to execute the declared item. Before protected writes, an item-declared finite `Authority`
gate may be materialized through `task_contract.materialize_owner_invocation(plan_dir, item_id)`:
the builder captures the live provider user message itself, appends its brief/Decision Log carriers,
and regenerates their bundle. It cannot widen scope, Files, environment or release/fleet authority.
Ungated prose is `AUTHORITY_CONTRACT_GAP`; route metadata or caller-supplied grants never authorize.
Run read-only environment preflight autonomously. A real environment failure records `NO-GO`
with repair evidence and a continuation, rather than repeating an already attested owner question.
Persist external/calendar waits as `waiting-external` with observation start, `resume_at`, evidence
fingerprint, runnable-after predicate and exact continuation in a durable checkpoint. Resume the same
run/evidence chain only after the actual time and predicate evidence; do not restart the observation
or close a production window using a fixture clock. An unchanged finite scope needs no renewed grant.

Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` for transient change-impact selection: focused validation and one
commit are normal; declared hard risk widens validation/review; foreign baseline is non-gating unless
its closure intersects; audit is read-only; only changed projections are generated once; one semantic
Next is rendered by `plan_delivery`. A declared Validation carrier needs current GREEN evidence, not
another run at each lifecycle transition: reuse it while relevant product/test/tool/config inputs and
environment are unchanged, rerun the affected delta after change, and rerun a live check at its live
boundary. Follow the complete close and delivery gates from `plan-exec`.

After GREEN acceptance, persist evidence and the terminal journal event, regenerate changed views,
and close the item in this invocation. If it is the last item of a GREEN phase and no audit is
explicitly admitted by `phase_audit_policy`, create the phase closure in this invocation too. Compute
Next only from that post-closure state and dependencies. Never render a launch for `plan-close` of
this result or for another `plan-run`/`plan-exec` of the current item.

For an installed terminal-admission adapter, arm the lease only after this command's run receipt,
refresh it only after material progress or typed owner-wait, and use its check verdict before a
terminal response. It is repository-owned admission evidence, not a claim that an unconfigured
provider transport is intercepted.

At every actual final after closure, render the shared receipt fragment through worktree-local
`plan-delivery.py --plan-dir <plan-dir> --subject <subject> --kind terminal --render-final`
(or the same command with `--verify <receipt>`). This delivery rule applies even without an optional
terminal-admission lease. A lease controls transport admission, not whether Next is reported.
