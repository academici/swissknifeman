<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:b93cfe5909174190d3bc1875f88a76793e573ad43fd4c0d4a2d0825df237bcc2
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

**Goal:** finish the requested items (or the ready batch from `next`) with green acceptance checks,
one commit per item, inside the item's scope.

**Steps**
1. `plan.py next <plan>` — without item ids, run the batch it names; with ids, run those.
   `--review` is a flag, never an item id.
2. `plan.py start <plan> <items…> --actor <provider>/<model>/<effort> --session auto`.
   A route refusal (`ROUTE_UNDERSHOOT`) stops before any product write; a stronger route is fine.
3. Read only `context/<item>.md` and the files its Reads section lists; get more state with
   `plan.py show <plan> <ref>`. Never read or edit the generated Markdown views.
4. Implement Scope include only. Use the item's rules, guidance and decisions.
5. When reality changes the plan, an assumption or a blocker appears:
   `plan.py log <plan> <item> --type deviation|blocker|difficulty|assumption|note --summary "…"`.
6. Run each Validation check once per relevant change; keep long output in a file.
7. `plan.py finish <plan> <item> --status done --check V1=0 … --notes "…"`
   (`done_with_deviations` with `--deviation`, `blocked` with `--escalation`). The last item closes its phase.
8. One scoped commit (plan JSON + product files), then the next item of the batch.

**Units (optional)**
- Split an item only into independent pieces that own separate files and checks; `plan.py unit <plan> <item> add --title … --json …`.
- Hand a piece out: `plan.py unit <plan> <item> <U#> dispatch --agent <provider>/<model>`, then give its
  `phases/<Pn>/<Pn.m>/<U#>/brief.md` to a native subagent of your own provider; parallel-safe units are listed in the pack.
- You stay the integrator: review every returned diff, rerun its checks, then `unit … <U#> accept|rework|reject --notes …`.
- `finish` is refused while a unit is `dispatched` or `returned`. Python starts no agent; `plan.py stats` shows the numbers.

**Rules**
- Run under the session route; never switch the model. The item route is the minimum.
- Change plan state only through `plan.py`; JSON is the source of truth.
- Owner gates: `plan.py grant` only with the owner's explicit message quoted in `--note`.
- Hard risk (security, schema/public API, data, concurrency, publishing) widens checks and is named in the
  final report with a `task:review` recommendation; no review runs by default.
- `--review`: after the last green item, one `task:review` pass over the scope diff; fix a confirmed
  finding in its open item, report findings of closed items as recommendations.
- Stop only at an owner gate, a missing decision, an external wait or exhausted context; existing dirty
  changes belong to the owner.

**Done when** every requested item is finished with recorded checks, committed, and the final report
states the result and the exact `plan.py next <plan>` line.
