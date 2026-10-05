# Execution mode

The requested items (or the ready batch from `plan.py next`) are one ordered workset.

1. `plan.py start` once for the workset; it checks phase design, dependencies, gates, open decisions
   and the minimum route, then writes the context packs.
2. Per item: read its pack and listed reads, implement Scope include, run its acceptance checks,
   `plan.py finish` with the recorded exits, then one scoped commit.
3. Continue with the next ready item of the workset in the same session; an item's green result
   is not a stopping point.
4. Log friction only when reality changes the plan, an assumption or a blocker
   (`plan.py log --type …`); keep it to one line with impact and next step.
5. A failed check is repair work for the executor, not a reason to stop or to finish as done.
   `blocked` (with `--escalation`) is for a real owner/external dependency.
6. Broad suites run once in the last item of a phase; earlier items run their affected checks.
7. The final report gives the outcome per item and the exact `plan.py next <plan>` line.

Optional `--reviewer provider/model[/context][/effort]` requests a fresh read-only reviewer on that
exact native route; without an explicit review request no review runs. `plan-run` accepts
`--review-effort`; review/audit accept `--effort`. See the Task package's
`references/reviewer-selection.md` for route parsing, native session independence and the bounded
two-completed-round/one-owning-correction policy. JSON and `plan.py` remain the state API;
reviewer flags do not restore `plan-work`, launch agents from Python or execute check commands.
