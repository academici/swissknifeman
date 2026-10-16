<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/plan-design.md
Canonical SHA-256: sha256:c92359c561b8de889c1eb35ff66f12b5545678c012b16acd45a5dc2497c03f9c
Adapter: planner.codex-command/1.0.18
-->
## Native Codex launch-block — required only at a real user-facing boundary

This generated runtime is the Codex provider projection. `$ planner:…` runs inside the **current**
Codex session; never copy Claude Code slash syntax. Continue ready work of the requested scope in
this session: an item, a phase or a failed test is not a session boundary.

Only when the owner asks for a new session, print `**Native Codex command:**` and one fenced `bash`
line that pins the repository cwd, the model and effort mapped from the next item's route, approval
policy and sandbox (never put the command in a table cell):

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ planner:<command> <arguments>'
```

Current Codex mapping: economy=gpt-5.6-luna, implementation=gpt-6-sol, frontier=gpt-6-astra; low=low, medium=medium, high=high, xhigh=xhigh.

## Codex planner CLI — provider-specific

`plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root; the launcher binds the
project and hands over to the installed `swissknifeman`. Declare the route with
`--actor codex/<model>/<reasoning effort>` from this session's settings.

Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:plan-design` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Invocation payload: `$ARGUMENTS`.

**Goal:** a plan whose target phase is `detailed`: every item is executable by a weaker model from its
context pack alone, and `plan.py check` passes.

**Steps**
1. New plan: `plan.py new --codename <NAME> --title "<title>" --actor <provider>/<model>/<effort>
   --message-file <owner-message.md>` — the identity (`№N`, `PLAN<N>`) comes from the command, never guessed. `--actor` is the observed session route, never inferred; ask the owner when it cannot be observed.
   Existing plan: `plan.py show <plan>` and `plan.py show <plan> <Pn>`.
2. Plan fields: `plan.py set <plan> plan --json '{"goal": …, "context": …, "rules": […]}'`;
   owner requirements: `plan.py set <plan> brief --json …`.
3. Phases and items: `plan.py add-phase <plan> --title …`, `plan.py add-item <plan> <Pn> --title … --file item.json`,
   then `plan.py set <plan> <ref> --json …` / `plan.py push <plan> <ref> <field> --json …` for refinements.
4. Questions and choices: `plan.py add-decision <plan> --title … --json '{"question": …, "options": […]}'`;
   record an answer with `plan.py decide <plan> <D#> --accept <A|text> --rationale …`.
5. Detail each target item: summary, why, scope include/exclude, reads (path, section, why, required),
   task_files, rules, guidance, examples, validation (`V#`, exact command, expect, `kind: acceptance`),
   deliverables, route (`economy|implementation|frontier` + effort), authority, depends_on/related.
   Optional units for a large item: `plan.py unit <plan> <Pn.m> add --title … --json '{"files": […], "mode": "delegate|self|either", …}'`;
   independent units need disjoint `files` and their own checks; `check` enforces it.
6. Batches: `plan.py batches <plan> <Pn> --json '[{"id": "B1", "items": […], "mode": "recommended"}]'`.
7. `plan.py check <plan>` until 0 errors, then `plan.py design-done <plan> <Pn>`;
   then read the design-done report and resolve its context warnings (bind knowledge, drop duplicate reads).

**Rules**
- Change plans only through `plan.py`; never edit the generated Markdown views.
- Spend research only where it can change a decision; long reasoning, algorithms and worked examples go
  to JSON `sections` or `knowledge/<id>.json` through `add-document`, referenced from item reads.
- Use as many items, reads and sections as the contract needs; detail a phase when its inputs are known.
- Validation names exact commands that must pass; diagnostics stay out of acceptance checks.
- Review is opt-in: items use `review: {mode: none}`; only `--review` or an owner request adds one read-only
  review item at the end of the scope. Name hard risks in the item's `why`.
- For concurrency, transactions, auth or data integrity, put the shared invariant model in
  JSON `sections` or `knowledge/<id>.json` and reference it through item reads; name enforcement, bypass and
  interfering operation/lock pairs. Use existing rules and validation fields, not new mandatory gates.
- For parallel phases keep `task_files` exact: `next --parallel` treats an item without `task_files` as conflicting with every lane.
- Bind knowledge and decisions to the items or phases that use them (`applies_to`); `global: true` only for plan-wide content.
- Design does not execute items.

**Done when** `plan.py check <plan>` reports 0 errors, the target phase is `detailed`, and the report
gives the exact `plan.py next <plan>` line.
