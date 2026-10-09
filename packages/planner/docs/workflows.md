# Planner workflow template constructor

Subagent orchestration is not written from scratch for each task: canon - **4 parameterizable
script template** in `packages/planner/workflows/` + rules for filling slots (README folder).
This is a library of portable templates, NOT a code generator and NOT a new DSL - workflow script
is already quite expressive; the constructor only captures proven topologies.

## When which template

| Template | Orchestration | Slots | Take when |
|:--|:--|:--|:--|
| `wf-research-fanout.js` | N topics × research → adversarial verify (pipeline, no barrier) | `TOPICS[]`, answer schemes, model/effort | multi-topic research with verification: market, stack, RAG under plan |
| `wf-author-by-spec.js` | spec → N file tasks × author → self-check (pipeline) | `FILES[]` (file + TK + validation), pipeline-commands | Stage-3 authoring using a ready-made spec: skills, docks, commands per-file |
| `wf-audit-adversarial.js` | M finders → dedup → adversarial verify → verdicts | `DIMENSIONS[]`, severity-enum, profile constitution | audit/review of artifact by measurements: plan, code, documentation |
| `wf-dev-slice.js` | slice → impl → tests-to-green → optional review (REVIEW slot, off by default) | `SLICES[]`, gates | development by vertical slices (profile `/planner:dev`) |

Sample prototype: `wf-p5-research.js` ECOSYSTEM P5 plan - working copy of template 1.

## Slot Rules

- **Slots are only constants in the script header.** Parameterization for editing the header, not
  args-string: embedded-config instead of parsing arguments (named-workflow trap -
  the line of arguments breaks on the very first multi-line TK).
- **The supervisor holds the context, the agents return structured summaries with the schema.**
  Handoff between stages - artifact-centric: file/structure, not chat retelling.
- **Judge-panel (3+ verdicts) - slot only for high-stakes stages.** Default
  single-agent: it closes most tasks, the panel of judges is selective (fiscal,
  payments, public contracts).
- **`max-iteration` is required for any loop-until** - a loop without an upper bound is prohibited.
- In `wf-dev-slice.js` commit is performed only after green tests, interslice gates and (only when the
  `REVIEW` slot is enabled) independent review. The missing result of impl/fix/review/gate/commit stops the workflow and
  is included in the final report; a successful outcome with such an omission is impossible.

## Plans and workflows

A plan item may run a workflow template in its stage (research, authoring, audit, development). The plan
itself is driven only by `scripts/plan.py` verbs (`next, start, log, finish, check, render`) - see
[Methodology](./methodology) and [Plan structure](./plan-structure); templates never write plan JSON by hand.

## Scoped commits per operation

Every operation of an item ends with its own scoped commit: the executor after `finish`
(`plan.py commit PLAN1 P1.1 --role executor`), the reviewer after its report
(`--role reviewer`), a review correction after the affected checks rerun (`--role fix`).
The commit holds the item's plan JSON and `task_files` only; foreign dirty paths return
`OUTSIDE_SCOPE` and stay untouched with `--leave-outside`. Never `git add -A`, `--no-verify`,
amend or push in plan-run. `plan.py commits PLAN1 [P1.1]` lists the commits linked to the plan or
item by `Plan` trailers. Details: [Plan structure](./plan-structure).

## Parallel lanes

`plan.py next <plan> --parallel N` names up to N independent lanes (read-only). The integrator works in the
main tree, the lane agents in their own worktrees:

1. Claim: `plan.py start` the lane items, then one claim commit
   (`plan.py commit … --role executor --type chore --trailer "Plan-Op: claim" --leave-outside`) before branching.
2. Isolate: `git worktree add -b plan/<PLANn>/<item> <path> HEAD` per lane; set `gc.auto 0` and
   `maintenance.auto false` for the round.
3. Lane agent: `plan-run` in its worktree with its own `finish` and `commit`; it never runs `reconcile`
   and never edits `phase.json` or `plan.json` by hand.
4. Integrate one branch at a time in plan order (`git merge --no-ff`, or rebase and fast-forward);
   `log.jsonl` merges through `union`, a conflict in a product file means incomplete `task_files`:
   abort, log a `blocker`, re-run that lane later.
5. Re-run the item's acceptance checks on the merged tree; red means `git revert -m 1 <merge>`, no `reset --hard`.
6. After the round `plan.py reconcile <plan>` closes finished phases; commit its result with
   `--trailer "Plan-Op: reconcile"`.
7. Clean up with `git worktree remove` and `git branch -d`.

Integration is local: GitHub web-merge does not apply `merge=union`. Enforcement and automation belong to
the future engine; an external run contract may carry the same intent as an isolation policy (one worktree per run, sequential integration).

## Context pack scope

`plan.py context <plan> <item> --budget [--json]` reports pack size by key, unbound content, duplicate reads
and the scoped preview. `design-done` prints the same numbers per item of the phase and its context warnings;
they never block. Switch a legacy plan after clearing `context_unbound`:
`plan.py set <plan> plan --json '{"settings": {"context_pack": "scoped"}}'`.

## Scout

An optional, opt-in context map (decision D3): a weak model of the current provider reads the deterministic
context pack and answers with all useful entries of `path[:symbol] — why` plus an `Unknowns:` block. It never
writes code or decisions, and the default start makes no model call.

- Enable: `plan.py start <plan> <items> --actor P/M/E --scout` once, or `plan.py set <plan> plan --json
  '{"settings": {"scout": "auto"}}'` for every start (`--no-scout` overrides). The provider is the one in `--actor`.
- Config (owner-editable): `configs/command-routing.json` → `orchestration.scout.<provider>` holds `model`, `effort`,
  `argv` (placeholders `{model}`, `{effort}`, `{cwd}`; the prompt goes through stdin) and `timeout_s`. The catalog
  rejects unknown keys, providers and placeholders. A provider without an entry is skipped; only `claude-code`
  has one (`claude -p --model haiku --tools ""`: no tools, so no writes).
  Add other providers only after checking their `--help` for a non-interactive, read-only mode that reads stdin.
- Result: `context/<item>.scout.json` (generated, gitignored) and the JSON scout field. A timeout,
  a non-zero exit or an empty answer never blocks `start`: the pack is built without the map.
- Read the outcomes in `log.jsonl`: events of type `scout` with `data: {provider, model, outcome: ok|failed|skipped,
  seconds, lines}` (`plan.py stats` summarises them from P4.2).

## Units and subagents

Opt-in orchestration inside one item (decision D3). The item executor may split the item into units that other
agents build, and stays the integrator: it reviews and tests every returned piece and alone finishes the item.

- Split only into independent pieces: each unit owns its `files` (disjoint from every unit it has no `depends_on`
  path to; `plan.py check` and `unit … add` enforce it) and has its own checks and minimum route.
- Verbs: `plan.py unit <plan> <item> add --title T --json '{"files": […], "mode": "delegate"}'`, then
  `unit <plan> <item> <U#> dispatch --agent <provider>/<model>`, `return --notes … --changed …` (the integrator records the worker report),
  `accept|rework|reject --notes …` (the executor). `rework` sends the piece back to `dispatched` and rewrites its brief;
  every transition logs a `delegate` event. `mode: self` units are never dispatched (`UNIT_SELF`).
- `dispatch` writes `phases/<Pn>/<Pn.m>/<U#>/brief.json`: goal, owned files, reads, item rules and decisions, checks,
  and rework notes. Python starts no agent: give the brief and the planner package's `references/executor-handoff.md`
  to a native subagent of your provider (Claude Code Task tool, Codex, Cursor or Grok subagents). The worker returns
  its report to the integrator, who records `unit … return`; the worker does not run `plan.py`. Run parallel-safe
  units together (the pack's Units section lists them).
- `finish --status done|done_with_deviations` is refused with `UNITS_OPEN` while a unit is `dispatched` or `returned`.
- `plan.py stats <plan> [--json]` reads `log.jsonl` only: friction by type and item, scout outcomes and mean seconds,
  unit outcomes (accepted, reworked, rejected) and median minutes per class and model. No thresholds: turning scout or
  delegation on by default is a later owner decision based on these numbers.
- Roadmap trigger (not implemented): if units are used in at least N plans and `stats` shows an accepted share of at
  least X, consider a deterministic dispatcher that takes `units[]` as its slice source.

## Bundles

- Review profiles for `wf-audit-adversarial.js` (constitution + measurements by type
  artifact) - an artifact-review skill, when installed; conformance-finder's by stack skills -
  command `/planner:review`.
- Full cycle in which workflow templates occupy the research/exec/review stages -
  [Methodology](./methodology).

Reviewer selection: see the planner package's references/reviewer-selection.md.
