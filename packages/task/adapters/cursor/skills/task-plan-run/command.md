<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:a921400e7a4555c463850b57038b33ee7765b2573fb32b4618a189b55ed703d9
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
description: "Execute authorized Task plan items with the attested current-session route."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
---
Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/execution-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory execution context.

Execute `$ARGUMENTS` by the canonical `task:plan-exec` lifecycle. `plan-run` inherits the current
provider-attested route; it never pins model or effort and it never substitutes config or prose for
route evidence. Use `plan-work.py prepare --command plan-run` with the plan, item, actor and
session to validate carriers internally and return compact context plus one `route-run-receipt/v1`.
Reuse route/context evidence until `route_change_boundary()` proves change.

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

Activate only for explicit owner Task invocation; use the
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

After GREEN acceptance, persist evidence and the terminal journal event, run
`task.plan_reconcile.reconcile_terminal()` to regenerate and verify changed views,
and close the item in this invocation. If it is the last item of a GREEN phase and no audit is
explicitly admitted by `phase_audit_policy`, create the phase closure in this invocation too. Compute
Next only from that post-closure state and dependencies. Never render a launch for `plan-close` of
this result or for another `plan-run`/`plan-exec` of the current item.

For an installed terminal-admission adapter, arm the lease only after this command's run receipt,
refresh it only after material progress or typed owner-wait, and use its check verdict before a
terminal response. It is repository-owned admission evidence, not a claim that an unconfigured
provider transport is intercepted.

An open durable run is not a response boundary: use commentary for partial progress and continue
the authorized work. Before final, the enabled Stop adapter runs `check-open` against the current
provider session even without a lease/request payload. `TASK_OPEN_RUN_FINAL_FORBIDDEN` requires
continuing or persisting a legitimate terminal block/checkpoint; a green subset of tests is not
an exception. An explicit owner stop remains binding. The check does not itself close any run.

At every actual final after closure, render the shared receipt fragment through worktree-local
`plan-delivery.py --plan-dir <plan-dir> --subject <subject> --kind terminal --render-final`
(or the same command with `--verify <receipt>`). This delivery rule applies even without an optional
terminal-admission lease. A lease controls transport admission, not whether Next is reported.
