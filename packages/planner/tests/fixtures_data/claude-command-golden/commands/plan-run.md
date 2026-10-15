---
disable-model-invocation: true
description: "Execute ready planner plan items with plan.py under the current session route."
argument-hint: "<PLAN> [Pn.m ...] [--review] [--reviewer <provider/model>] [--review-effort high]"
---
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:plan-run` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Invocation payload: `$ARGUMENTS`.

**Goal:** finish the requested items (or the ready batch from `next`) with green acceptance checks,
one commit per item, inside the item's scope.

**Steps**
1. `plan.py next <plan>` — without item ids, run the batch it names; with ids, run those.
   Review flags are options, never item ids. Read `references/reviewer-selection.md` when requested.
   `--reviewer` requests a fresh read-only review of each selected item before `finish`;
   an omitted reviewer flag never starts a review.
2. `plan.py start <plan> <items…> --actor <provider>/<model>/<effort> --session auto`.
   A route refusal (`ROUTE_UNDERSHOOT`) stops before any product write; a stronger route is fine.
3. Read `plan.py context <plan> <item> --stdout` as JSON and the supporting files it names; get more state with
   `plan.py show <plan> <ref>`. Never read or edit the generated Markdown views.
4. Implement Scope include only. Use the item's rules, guidance and decisions.
5. When reality changes the plan, an assumption or a blocker appears:
   `plan.py log <plan> <item> --type deviation|blocker|difficulty|assumption|note --summary "…"`.
6. Run each Validation check once per relevant change; keep long output in a file.
   With `--reviewer`, run the selected native read-only reviewer after GREEN checks; record its
   verdict and actual session in an artifact and a `plan.py log --type note` event, then
   `plan.py commit <plan> <item> --role reviewer`. A finding returns at most `policy.corrections_max` owning
   corrections (context pack `policy`, or `plan.py config show`; default 1) and affected checks, committed with
   `--role fix` after they rerun, then a re-review while fewer than `policy.review_rounds_max` rounds (default 2)
   are complete; no recursive reviewer fixes.
7. `plan.py finish <plan> <item> --status done --check V1=0 … --notes "…"`
   (`done_with_deviations` with `--deviation`, `blocked` with `--escalation`). The last item closes its phase.
8. One scoped commit: `plan.py commit <plan> <item> --role executor` (plan JSON + product files of the item;
   `--path` for an extra file, logged as a deviation). Report the printed sha, then the next item of the batch.

**Units (optional)**
- Represent preparation, implementation, review and checks as units with dependencies and optional parents; `plan.py unit <plan> <item> add --title … --json …`.
- Hand a piece out: `plan.py unit <plan> <item> <U#> dispatch --agent <provider>/<model>`, then give a native subagent of
  your own provider its `phases/<Pn>/<Pn.m>/<U#>/brief.json` and the executor handoff in the planner package's
  `references/executor-handoff.md`; record its report yourself with `unit … return`. Use `unit … next` for ready work.
- You stay the integrator: review every returned diff, rerun its checks, then `unit … <U#> accept|rework|reject --notes …`;
  after `accept`, commit it with `plan.py commit <plan> <item>/<U#> --role executor`.
- `finish` is refused until every unit is `accepted` or explicitly `rejected`. Python starts no agent; `plan.py stats` shows the numbers.

**Rules**
- Run under the session route; never switch the model. The item route is the minimum.
- Declare `--actor` from the runtime's observed session model and effort (its settings or environment); never infer them from prompt text or defaults, and ask the owner when one cannot be observed.
- Change plan state only through `plan.py`; JSON is the source of truth.
- Never `git add -A`, `--no-verify`, amend or push in plan-run; a refusal `OUTSIDE_SCOPE` lists foreign dirty
  paths — leave them (owner work) with `--leave-outside` or extend with `--path`.
- Owner gates: `plan.py grant` only with the owner's explicit message quoted in `--note`.
- Hard risk (security, schema/public API, data, concurrency, publishing) widens checks and is named in the
  final report with a `planner:review` recommendation; no review runs by default.
- `--review`: after the last green item, one `planner:review` pass over the scope diff; fix a confirmed
  finding in its open item, report findings of closed items as recommendations.
- Parallel lanes: take them from `plan.py next <plan> --parallel N`; one worktree and branch per lane after a committed claim; integrate lanes one at a time, re-run the item's acceptance checks, then `plan.py reconcile <plan>`.
- The context pack is complete; do not trim it. Irrelevant or stale pack content is a design defect: `plan.py log <plan> <item> --type difficulty` with `plan.py context <plan> <item> --budget` numbers.
- Stop only at an owner gate, a missing decision, an external wait or exhausted context; existing dirty
  changes belong to the owner.

**Done when** every requested item is finished with recorded checks, committed, and the final report
states the result and the exact `plan.py next <plan>` line.
