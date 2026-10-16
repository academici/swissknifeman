<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/planner/commands/plan-close.md
Canonical SHA-256: sha256:71622dd35042f16da2401737a4aaddb5fea75687b7ea9a560f2162394f406925
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
