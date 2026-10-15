---
disable-model-invocation: true
description: "Close or archive planner plan work with plan.py; ordinary execution already closes inline."
argument-hint: "<PLAN> <Pn.m|archive>"
model: sonnet
effort: low
---
Project CLI: `plan.py` means `python3 -I .swissknifeman/launcher.py planner`, run from the project root (the launcher binds the project; without one, run `swissknifeman project init` once). Never locate or run a Swiss Knife Man package script.
Owner rules: run `plan.py overlays planner:plan-close` first and follow any rules it prints as additions to this command; they never override the plan, its checks or safety rules.
Invocation payload: `$ARGUMENTS`.

**Goal:** record a missing outcome, reopen a finished item, or archive a done plan.

**Steps**
1. `plan.py show <plan>` — see item and phase state.
2. Missing outcome: `plan.py finish <plan> <item> --status … --check V1=0 … --notes "…"`; the last item
   closes its phase. Owner amendment: `plan.py reopen <plan> <item> --reason "…"`.
3. Archive: `plan.py archive <plan>` (a plan that is not done needs `--force --reason "…"` from the owner).
4. One scoped commit; report `plan.py next <plan>`.

**Rules**
- Record only checks that actually ran green; never fabricate an outcome.
- `plan-run` closes its own items; use this command only for leftovers, reopen or archive.
