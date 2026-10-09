<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/planner/commands/plan-close.md
Canonical SHA-256: sha256:f4637af69e4d3a46a993f2f0d7e131222f198791b8e0ca00e77bdef9a91365d5
Adapter: planner.cursor-command/1.0.18
-->
## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ planner:` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'planner:<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: economy=composer-2.5-fast, implementation=composer-2.5, frontier=claude-opus-5-thinking-high.

---
disable-model-invocation: true
description: "Close or archive planner plan work with plan.py; ordinary execution already closes inline."
argument-hint: "<PLAN> <Pn.m|archive>"
model: sonnet
effort: low
---
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
