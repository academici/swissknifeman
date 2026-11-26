# Execution mode

The requested items (or the ready batch from `plan.py next`) are one ordered workset.

1. `plan.py start` once for the workset; it checks phase design, dependencies, gates, open decisions
   and the minimum route, then writes the context packs.
2. Per item: read its pack and listed reads, implement Scope include, run its acceptance checks,
   `plan.py finish` with the recorded exits, then one scoped commit with
   `plan.py commit <plan> <item> --role executor` (`plan.py commits` lists them; never `git add -A`,
   `--no-verify`, amend or push).
3. Continue with the next ready item of the workset in the same session; an item's green result
   is not a stopping point.
4. Log friction only when reality changes the plan, an assumption or a blocker
   (`plan.py log --type …`); keep it to one line with impact and next step.
5. A failed check is repair work for the executor, not a reason to stop or to finish as done.
   `blocked` (with `--escalation`) is for a real owner/external dependency.
6. Broad suites run once in the last item of a phase; earlier items run their affected checks.
7. The final report gives the outcome per item and the exact `plan.py next <plan>` line.

## Parallel lanes

Integrator = one session in the main tree; lane agent = one executor in its own worktree.
1. Integrator takes lanes from `plan.py next <plan> --parallel N`, runs `start`, commits the claim (`Plan-Op: claim`).
2. `git config gc.auto 0` and `maintenance.auto false`; `git worktree add -b plan/<PLANn>/<item> <path> HEAD` per lane.
3. Lane agent runs plan-run in its worktree: finish, commit as usual.
4. Integrator merges one branch at a time (`--no-ff`); a product-file conflict means `git merge --abort`, a `blocker` log, re-run later.
5. After each merge re-run the item's acceptance checks; red → `git revert -m 1`, never `reset --hard`.
6. After the round: `plan.py reconcile <plan>`, then commit (`Plan-Op: reconcile`); remove worktrees and merged branches.
A lane agent never calls `reconcile` and never edits phase.json or plan.json.

Reviewer selection: see the planner package's references/reviewer-selection.md.
