<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-audit.md
Canonical SHA-256: sha256:c56c955b46a6a907b46f5306de2bee25daa30ce809a91efd99a84846989b2de8
Adapter: task.codex-command/1.0.17
-->
## Native Codex launch-block — required only at a real user-facing boundary

This generated runtime is the Codex provider projection. `$ task:…` runs inside the **current**
Codex session; never copy Claude Code slash syntax. Continue ready work of the requested scope in
this session: an item, a phase or a failed test is not a session boundary.

Only when the owner asks for a new session, print `**Native Codex command:**` and one fenced `bash`
line that pins the repository cwd, the model and effort mapped from the next item's route, approval
policy and sandbox (never put the command in a table cell):

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:<command> <arguments>'
```

Current Codex mapping: economy=gpt-5.6-luna, implementation=gpt-6-sol, frontier=gpt-6-astra; low=low, medium=medium, high=high, xhigh=xhigh.

## Codex Task root — provider-specific

The Task package root is the installed Codex plugin:

```bash
export TASK_CODEX_PLUGIN_ROOT="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')"
```

`plan.py` means `python3 "$TASK_CODEX_PLUGIN_ROOT/scripts/plan.py"`. Declare the route with
`--actor codex/<model>/<reasoning effort>` from this session's settings.

Invocation payload: `$ARGUMENTS`. `plan.py` is `python3 <Task package root>/scripts/plan.py`.

**Goal:** one independent verdict (GREEN / ATTENTION / RED) on a plan design or a finished phase.

**Steps**
1. `plan.py check <plan>` and `plan.py show <plan>`; read the target phase and items with
   `plan.py show <plan> <ref>`.
2. `design`: judge whether each detailed item is executable from its context pack
   (`plan.py context <plan> <item> --stdout`): scope, reads, exact checks, decisions, dependencies.
3. `Pn`: compare the phase's product diff with item scope, recorded checks and deliverables; rerun
   only checks whose inputs changed.
4. Write the verdict to `@plan/artifacts/audit/<Pn|design>-<YYYY-MM-DD>.md`: verdict, findings
   (severity, evidence `path:line`, owning item), recommendations.
5. `plan.py log <plan> <Pn> --type note --summary "audit <verdict>: <file>"` (`design`: the first target phase).

**Rules**
- Runs only on explicit owner invocation; one reviewer, one pass, no subagents unless asked.
- Read-only over product code and plan JSON; the verdict file and the note are the only writes.
- A finding names its owning item; fixing it is `plan-run` work (`plan.py reopen` by the owner).
- Severity follows demonstrated impact; uncertainty is reported as a question, not a defect.

**Done when** the verdict file exists, the note is logged, and the report gives the verdict and
`plan.py next <plan>`.
