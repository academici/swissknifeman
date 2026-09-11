---
description: "Execute manual plan item(s) using the owner session route and shared lifecycle."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
---
Execute `$ARGUMENTS` by the canonical `task:plan-exec` lifecycle. `plan-run` inherits the current
provider-attested route; it never pins model or effort and it never substitutes config or prose for
route evidence. Capture five v2 carriers once, admit the Routing group or ready subset of a recommended group, persist one
`route-run-receipt/v1`, then reuse route/context evidence until `route_change_boundary()` proves change.

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
