---
disable-model-invocation: true
description: "Execute ready planner plan items with plan.py under the current session route."
argument-hint: "<PLAN> [Pn.m ...] [--review] [--reviewer <provider/model>] [--review-effort high]"
---
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:plan-run` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Invocation payload: `$ARGUMENTS`.

**Goal:** finish the requested items (or the ready batch from `next`) with green acceptance checks, inside the
item's scope, committed in order: the implementation before any review, corrections after it, the rest at the end.

**Steps**
1. `plan.py next <plan>` — without item ids, run the batch it names; with ids, run those.
   Review flags are options, never item ids. Read `references/reviewer-selection.md` when requested.
   `--reviewer` requests a fresh read-only review of each selected item before `finish`;
   a recorded requested review or an explicit owner message also uses the normal review path.
   **A review runs only when the plan JSON records it** (`review.mode: requested` with its reviewer, or a review
   item of the phase); one that no document declares is not run, like a subagent when the registration command is
   given. A phase item that is itself the review of the phase needs no further review. Batches are a
   recommendation: starting several items together without a recorded batch is a conscious choice, not an error.
2. `plan.py start <plan> <items…> --actor <provider>/<model>/<effort> --session auto`.
   A route refusal (`ROUTE_UNDERSHOOT`) stops before any product write; a stronger route is fine.
3. Read `plan.py context <plan> <item> --stdout` as JSON and the supporting files it names; get more state with
   `plan.py show <plan> <ref>`. Never read or edit the generated Markdown views.
4. Implement Scope include only. Use the item's rules, guidance and decisions.
5. When reality changes the plan, an assumption or a blocker appears:
   `plan.py log <plan> <item> --type deviation|blocker|difficulty|assumption|note --summary "…"`.
6. Run each Validation check once per relevant change; keep long output in a file.
   When the checks are GREEN, commit the implementation **before any review**:
   `plan.py commit <plan> <item> --role executor --paths-only --path <product file>…` (exactly the files you changed;
   the plan files wait for step 8). Then, for a requested item review, use the review-only runner below with the exact
   selected reviewer route. Read only its compact final JSON and receipt. A finding returns at most
   `policy.corrections_max` owning corrections (default 1), with affected checks, and a re-review while
   fewer than `policy.review_rounds_max` rounds (default 2) are complete. No recursive reviewer fixes.
   Commit each green correction on its own: `plan.py commit <plan> <item> --role fix --paths-only --path <file>…
   --trailer "Plan-Findings: <finding keys>"`, so the fix commit holds only the fix.
7. `plan.py finish <plan> <item> --status done --check V1=0 … --notes "…" --review-receipt <path>`
   (`done_with_deviations` with `--deviation`, `blocked` with `--escalation`). The last item closes its phase.
8. The final commit: `plan.py commit <plan> <item> --role executor` (plan JSON and whatever of the item's files the
   earlier commits did not take; `--path` for an extra file, logged as a deviation). Report the printed shas
   (implementation, fixes, final), then the next item of the batch.

**Review intent**

| Source | Action |
|:--|:--|
| Command flag `--reviewer` / `--review` | Explicit opt-in, with the command's existing item or scope shape; record the requested review in the plan before running it. |
| Owner message in the session asking for review, in ordinary words or with a selector | Normalize into the plan for unfinished items of this invocation: `plan.py set <plan> <item> --json '{"review":{"mode":"requested","reviewer":{...},"reason":"owner request: <quote>"}}'` (D13), then use the normal path. |
| `item.review.mode: requested` in the plan | Conductor reviews per item when run policy enables it; otherwise it announces `REVIEW_REQUESTED_POLICY_OFF`. Interactive plan-run uses the review-only runner below. |
| None of the above | Self-check plus affected tests. |

**Interactive review runner**

Use the orchestrator's review-only runner after GREEN item checks. Build a run-options JSON file
with `reviewer` set to the exact selected `provider/model[/context][/effort]`; keep its path as
`<reviewer-options.json>`. Record the review request in the plan first; there is no unrecorded
run-only review of a plan item. Use the parent of the first commit of the item (the implementation commit of step 6)
as `<base>`, so the diff of the review is not empty and holds the corrections too.

```sh
python3 -I .swissknifeman/launcher.py orch input adhoc --review <base>..WORKTREE --plan <plan> --item <item> --goal "<item summary>" > "$TMPDIR/review-<item>.json"
python3 -I .swissknifeman/launcher.py orch conduct run --input "$TMPDIR/review-<item>.json" --options <reviewer-options.json> > "$TMPDIR/review-<item>.result.json"
```

Read only the final JSON line (`run`, `receipt`, `verdict`, `open`, compact `findings`) and the
`review-receipt.json` it names. Raw reviewer streams and transcripts stay in the run directory;
never load them into the owner/executor session. The runner performs review and triage once,
without executor work, acceptance commands, correction rounds, advisor or commit. Pass its receipt
to `plan.py finish <plan> <item> … --review-receipt <path>`. A receipt with open confirmed defects
is review evidence, not a claim that those defects were fixed: correct them within the existing
bounded rounds and refresh the receipt for the resulting candidate before closing.

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
