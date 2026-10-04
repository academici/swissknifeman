# Execution mode

Treat the explicit admitted item list/range as one ordered workset.  Admission binds its
membership and order, then checks only the current ready frontier.  A producer's durable
terminal evidence advances the completed prefix before its consumer is admitted.

For each frontier item:

1. validate the request and route;
2. run `task.plan_recovery.prepare()` so deterministic state/bundle projections exist
   before the five-carrier snapshot;
3. persist or resume exactly one durable start with the current batch receipt, implement
   Scope, and obtain current Validation evidence;
4. persist terminal evidence with the same receipt advanced by the completed prefix, then
   run `task.plan_reconcile.reconcile_terminal()`;
5. continue the next compatible remaining workset member in the same invocation.

The reconciliation reducer is resume-safe and invokes the existing journal, state,
decision/status, bundle and delivery owners.  Its stage failure is local repair work, not
a reason to report success or ask the owner a procedural question.  Do not start a future
consumer until its actual inputs/authority are ready, and do not expand beyond the bound
workset.

Final is allowed only after the whole requested workset is accepted, the owner stops, or a
reproduced narrow boundary prevents its remaining member.  `check-open` also rejects a
terminal response when a session-bound batch receipt still has unstarted remaining work.
Run an item's affected checks only; broad suites run once in the phase's review/last item.
Keep large logs/JSON in files and read status, counts and a few diagnostics.
Read `../SKILL.md` or `plan-layout-v2.md` only for a named schema/detail needed during
recovery or mutation.

Execution owns implementation, adversarial self-check for a declared systemic risk, and affected
tests. `plan-run ... --reviewer provider/model` authorizes automatic independent review of every
requested implementation item. Pass the selection and `--review-effort` (default high) to each
`prepare`; its durable request adds a close requirement without editing frozen item specs.
The same root may orchestrate `review-packet` and one Grok `review-run`; transport creates a fresh
read-only reviewer session. The root cannot record its own reviewer verdict. Keep product stable
while the reviewer runs. GREEN closes and continues; FINDINGS gets one in-scope correction, affected
tests and one second review. No manual owner handoff between those steps, no nested reviewer/fixer
recursion or third completed round. A standalone review request still ends with its review artifact.
Product/item closure stays pending until current GREEN exists. Unchanged evidence is reused.
A repeated systemic class/area changes tactics to a
shared invariant model, and review/transport budget exhaustion is an explicit bounded exit.
Read review mode only when this declared carrier or a returned finding applies.
