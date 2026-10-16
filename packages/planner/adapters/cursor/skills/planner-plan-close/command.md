<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/planner/commands/plan-close.md
Canonical SHA-256: sha256:71622dd35042f16da2401737a4aaddb5fea75687b7ea9a560f2162394f406925
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
