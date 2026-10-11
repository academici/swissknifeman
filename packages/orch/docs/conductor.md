# Conductor

`scripts/conduct.py` takes pieces of work from the work source and drives each one through the roles of its
run-policy until it is green or stops honestly. It is shipped with orch and tuned by configuration and by the run
options of the work; it is never rewritten for a run. The conductor itself decides nothing: it branches only on exit
codes, on the verdicts of the closed role results (`schemas/conductor/v1`) and on the limits of the run options.
Models are used only for the narrow roles: context scout, executor, reviewer, triager and, when asked for, the registrar that records the result.

```text
conduct.py [--config FILE] run --plan P (--items REF… | --batch [--max-items N]) [--plans-root DIR]
           [--options FILE] [--dry-run [--scenario S]] [--quiet | --json-lines] [--model-catalog FILE]
conduct.py [--config FILE] resume --run RUN [--quiet | --json-lines]
conduct.py status [--run RUN] [--json]
conduct.py observe [--run RUN] [--follow]
```

Exit codes: 0 the run finished, 1 it stopped (or a command was refused; `CODE: message` on stderr), 2 usage,
130 interrupted (`resume` continues).

## The cycle of one piece of work

Every step has a key and is recorded in `state.json` once it closes; the work source is reached only through
`orch.py source …` and the roles only through the launch catalog.

| Step | Who | What |
| --- | --- | --- |
| claim | work source | `source claim` with a submission of this run; `--batch` claims the next ready piece each time |
| `brief` | work source | `source brief`; the execution-input is read from the artifact store; the base revision is recorded |
| `prepare` | orch | `source prepare` writes the launch-plan of the scenario's pack (routes, policy decision) |
| `scout` | context-scout (economy) | when the pack has a scout or condense stage; the result is a cached context map |
| `executor.N` | executor | the execution-input, the context map, the run rules and, for a correction, its package; returns a closed `stage-report` |
| `checks.N` | deterministic | every `acceptance`/`impact` command check, with a check-evidence file per check |
| `review.N` | reviewer (default `grok/grok-4.7/high`) | read-only, the diff against the base and the check results; returns `review-findings` |
| `triage.N` | triager | reproduces every finding; returns `triage-result` (confirmed with a correction package, or rejected with a reason) |
| `close` | registrar (economy) | only when a layer of the options names the registrar in `stages`: a model runs the one `source register` command the conductor built (the launch catalog allows it exactly `python3 *orch.py source register *`) and answers with its output; it never sees the task |
| `register` | work source | `source register` with the report, the status and the evidence; a repeat is a no-op, so after a closer it only confirms the record, and when the closer failed it records the result and `close` says `conductor` and why |
| `commit` | work source | `source commit` with the changed paths and the artifact folder, when the pack's `git_action` is `commit` |

Red checks get at most `limits.check_fixes` corrections; confirmed findings at most `limits.corrections`
corrections within `limits.review_rounds` rounds (2 rounds and 1 correction by default, as in the `full` pack). A
finding that did not reproduce is never a reason for a correction. After a limit the piece is registered `blocked`
with an escalation (`CHECKS_RED`, `REVIEW_LIMIT`).

The executor sees only its prompt: the execution-input, the context map, `rules` and the correction package. It never
sees the plan or the plan's command line. A gap that needs the owner is `blocked` with one `escalation` issue per
missing thing; `done_with_deviations` needs a `deviation` issue. A result outside its contract is repeated within
`limits.retries`.

### Stops

The conductor stops only on:

| Code | When |
| --- | --- |
| `ITEM_BLOCKED` | a piece is blocked and `on_blocked` is `stop` (or it left changes in the tree) |
| `ROUTE_UNDERSHOOT` | the executor route is below the class or effort the work requires |
| `PROVIDER_UNAVAILABLE`, `TRANSPORT_UNSUPPORTED`, `LAUNCH_UNKNOWN` | a role cannot start (an optional scout is skipped instead) |
| `BUDGET_EXHAUSTED` | the tokens of the piece passed `limits.tokens_max` |
| `ROLE_FAILED`, `TIMEOUT`, `ROLE_OUTPUT_EMPTY`, `ROLE_OUTPUT_INVALID` | a role kept failing after `limits.retries` |
| `WORKTREE_DIRTY` | changes outside the conductor reports before new work |
| `CLAIM_BLOCKED`, `BRIEF_REFUSED`, `PREPARE_REFUSED`, `REGISTER_REFUSED`, `COMMIT_REFUSED`, `WORK_SOURCE_*` | the work source refused or is unavailable |
| `OPTIONS_INVALID`, `POLICY_UNKNOWN`, `MODEL_CATALOG_UNAVAILABLE` | the run options, the pack or the model catalog are unusable |

With `on_blocked = "report"` a blocked piece that changed nothing is registered, its records are committed and the
run goes on; a blocked piece with changes stops the run, because its partial work would leak into the next piece.

### Resume

`resume --run RUN` runs the same loop again. A closed step returns its recorded result and prints `stage.skip`; a
piece that closed (done or blocked) is not claimed again; a piece that stopped half-way continues on its own working
tree. The configuration of the run is read again, so a fixed provider or a corrected `[orch.conductor.argv]` takes
effect.

## Run options

`schemas/conductor/v1/run-options.schema.json`, closed:

| Key | Meaning |
| --- | --- |
| `stages` | `[{role, provider?, model_class?, model?, effort?}]`, roles `context-scout`, `executor`, `bounded-implementer`, `reviewer`, `triager`, `registrar` (naming it turns the closing stage on) |
| `reviewer` | `PROVIDER/MODEL[/CONTEXT][/EFFORT]` |
| `rules` | short rules for the executor |
| `skills` | `[{role, names}]` |
| `limits` | `review_rounds` (0–5), `corrections` (0–3), `check_fixes` (0–3), `retries` (0–5), `tokens_max`, `stage_timeout_s`, `check_timeout_s` |
| `on_blocked` | `stop` or `report` |

Layers merge from the general to the specific: defaults → `[orch.conductor]` → the run-policy pack (the routes of its
model stages, `review.triage`, `max_rounds`, `max_corrections`, `retries_budget`) → the layers of the work source (the
plan, the phase, the item) → `--options FILE`. A value of a more specific layer wins; `rules` append without repeats;
`limits` merge by key; `skills` replace the list of each named role; `stages` merge by role, and a layer that names a
model or a model class replaces both. Every source layer is validated (`OPTIONS_INVALID` names the layer).
`<run>/<item>/options.json` records the merged options and, per key, the layer that set it.

The work source hands the layers over in its claim answer (`options`). The planner bridge reads them from
`orchestration.options` of the plan, the phase and the item, and from orchestration overlay documents (see the
bridge README) for plan engines that do not know the field yet.

## Visibility

Every event is one progress line (`conductor/v1` `progress-line`): `run.start|resume|end`, `item.start|end`,
`stage.start|end|skip`, `info`. stderr gets a readable line by default (time, item, step, role and route, what
happened, verdict, duration, tokens, stop code), the JSON line with `--json-lines`, nothing with `--quiet`. The journal
`progress.jsonl` always gets the JSON line. Every role is told to print the same kind of line
(`[orch] <UTC time> <item> <step> <what>`) into its own stream. `conduct.py status` summarises the journal: run status,
the step running now, the last step and outcome of each piece, the tokens.

## Files: what is committed

| Path | Git | Content |
| --- | --- | --- |
| `.swissknifeman/state/orch/conductor/<run>/` | ignored | `run.json`, `state.json`, `progress.jsonl`; per piece `input.json`, `options.json`, `routes.json`, `prompts/`, `streams/` (raw role streams with token logs), `reports/`, `checks/<n>/V#.log`, `register-report.json` |
| `.swissknifeman/state/orch/conductor/cache/scout/` | ignored | context maps keyed by the digest of the brief, the plan version, the route and the role text |
| `.swissknifeman/state/orch/runs/<run>/` | ignored | the orch run journal of `source …` |
| artifact folder of the piece (`artifacts_dir` of the brief; the planner: `plans/<plan>/artifacts/<item>/`) | committed | `stage-report.json` (closed), `review-verdict.json` (selector, rounds, sessions, findings with the triage's reproductions, the stream path in state), `evidence/V#.json` (check-evidence) |
| `.swissknifeman/orch/reports/<run>/` | committed | `observer.json`, `observer.md`; the artifact folder of a source without `artifacts_dir` |
| the plan (JSON) | committed | through the work source's own commit |

Role streams never go into the artifact folder; a review verdict there is short and points at the stream in state.
The shared gitignore policy (`packages/aicore/configs/gitignore-policy.json`, entries `swissknifeman-state` and
`orch-conductor-reports`) states the same for every connected project, and `orch.py doctor` warns when the runtime
folder is not ignored or the reports folder is (`orch.conductor-gitignore`, `orch.conductor-reports`,
`check-result/v1` with `--json`).

## Observer

The observer only reads: the journal and state of the run and the `orch.run.*` and `planner.*` events of the
project's aicore event journal since the run started. At the end of every run (also a stopped one) the conductor
writes `observer.json` and `observer.md`: repeats and resumes, red checks per check id, review findings by severity,
triage confirmed and rejected, idle time between stages, seconds and tokens by role, scout cache hits, the outcome of
each piece and proposals to improve the run options. `conduct.py observe --follow` prints the notable lines of a run
that is still going from another terminal; `conduct.py observe` writes the report again.

## Configuration

`[orch.conductor]` (`configs/config.schema.json`): `provider` (default `claude-code`), `reviewer`
(`grok/grok-4.7/high`), `registrar` (`orch/conductor`), `rules`, `on_blocked`, `limits.tokens_max`,
`limits.stage_timeout_s`, `limits.check_timeout_s`, and `argv.<role>`: the command line of a role instead of the
launch catalog entry (`{model}`, `{effort}`, `{cwd}`, `{orch}` are filled in). `argv` is machine-wide: a project file
cannot set it. The tests use it to put fake providers in place of the real CLIs.

## Plan engines without `orchestration.options`

The planner declares `orchestration.options` as an extension slot and keeps no copy of this contract: the planner
bridge supplies `run-options` to it (`extends` in its `bridge.json`), so `set` and `check` validate the options by
this schema. A plan engine without the slot refuses the fields with `unexpected property`; a planner that does not find
the bridge refuses the options with `EXTENSION_UNAVAILABLE` and still keeps `orchestration.scenario`. The planner
bridge then reads the scenario and the options from orchestration overlay documents (`add-document`, id
`orchestration-<scope>`, section `orchestration` holding `{"scenario"?, "options"?}`, applying to a phase, an item or,
with `global`, the plan). A field of the same level wins over an overlay.
