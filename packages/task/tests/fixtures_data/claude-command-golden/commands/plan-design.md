---
disable-model-invocation: true
description: "Explicit Task plan design: author or refine a plan with plan.py."
argument-hint: "<PLAN>|new <title> [Pn] [--review]"
model: opus
effort: high
---
Invocation payload: `$ARGUMENTS`. `plan.py` is `python3 <Task package root>/scripts/plan.py`.

**Goal:** a plan whose target phase is `detailed`: every item is executable by a weaker model from its
context pack alone, and `plan.py check` passes.

**Steps**
1. New plan: `plan.py new --codename <NAME> --title "<title>" --actor <provider>/<model>/<effort>
   --message-file <owner-message.md>` — the identity (`№N`, `PLAN<N>`) comes from the command, never guessed.
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
6. Batches: `plan.py batches <plan> <Pn> --json '[{"id": "B1", "items": […], "mode": "recommended"}]'`.
7. `plan.py check <plan>` until 0 errors, then `plan.py design-done <plan> <Pn>`.

**Rules**
- Change plans only through `plan.py`; never edit the generated Markdown views.
- Spend research only where it can change a decision; long reasoning, algorithms and worked examples go
  to `research/` or `artifacts/` files referenced from item reads (`@plan/...`).
- A few outcome items per phase (normally ≤ 4), ≤ 8 reads per item; detail one phase at a time when
  later phases depend on real code.
- Validation names exact commands that must pass; diagnostics stay out of acceptance checks.
- Review is opt-in: items use `review: none`; only `--review` or an owner request adds one read-only
  review item at the end of the scope. Name hard risks in the item's `why`.
- Design does not execute items.

**Done when** `plan.py check <plan>` reports 0 errors, the target phase is `detailed`, and the report
gives the exact `plan.py next <plan>` line.
