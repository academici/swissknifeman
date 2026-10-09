---
disable-model-invocation: true
description: "Deprecated alias of /planner:plan-close. Close or archive planner plan work with plan.py; ordinary execution already closes inline."
argument-hint: "<PLAN> <Pn.m|archive>"
model: sonnet
effort: low
---
> `/task:plan-close` is deprecated and will be removed in the next minor release: use `/planner:plan-close`. Say this to the user once, then follow the instructions below; `<Planner package root>` is the root of the enabled planner plugin.

Invocation payload: `$ARGUMENTS`. `plan.py` is `python3 <Planner package root>/scripts/plan.py`.

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
