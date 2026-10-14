# Conductor

`scripts/conduct.py` takes pieces of work from the work source and drives each one through the roles of its
run-policy until it is green or stops honestly. It is shipped with orch and tuned by configuration and by the run
options of the work; it is never rewritten for a run. The conductor itself decides nothing: it branches only on exit
codes, on the verdicts of the closed role results (`schemas/conductor/v1`) and on the limits of the run options.
Models are used only for the narrow roles: context scout, executor, reviewer, triager and, when asked for, the registrar that records the result.

```text
conduct.py [--config FILE] [--project DIR] run --plan P (--items REF… | --batch [--max-items N]) [--plans-root DIR]
           [--options FILE] [--adopt] [--dry-run [--scenario S]] [--quiet | --json-lines] [--model-catalog FILE]
conduct.py [--config FILE] resume --run RUN [--retry ITEM ...] [--quiet | --json-lines]
conduct.py settle --run RUN --item REF --outcome done|done_with_deviations|blocked --reason TEXT
conduct.py status [--run RUN] [--json]
conduct.py observe [--run RUN] [--follow]
conduct.py gates [--json] [--clear [PROVIDER]]
```

Exit codes: 0 the run finished, 1 it stopped (or a command was refused; `CODE: message` on stderr), 2 usage,
130 interrupted (`resume` continues).

## The project

The project is `--project DIR`, else `SKM_PROJECT_ROOT`, else the nearest folder above the working directory that holds `.git`
or `.swissknifeman` (`aicore.state.resolve_project`; the home directory does not count through `.swissknifeman`). Without one
the commands stop with `PROJECT_CONTEXT_REQUIRED` and the hint `--project DIR`; a project that is not a git repository is
`PROJECT_NOT_GIT` for the conductor. `orch.py` takes the same global `--project`, and its run cycle (`source …`) needs a
project. A named project (`--project`, `SKM_PROJECT_ROOT`) that is not a folder is `PROJECT_CONTEXT_REQUIRED`, never replaced
by a search. The conductor tells every `orch.py` it starts the project (`--project`) and how it found it
(`--project-resolution`), so the run cycle cannot land in another repository. The roles always start in the project folder,
wherever the conductor was started. `run.json` records
`project_resolution` (`flag`, `environment`, `marker` or `git`) and `working_directory`.

## Digests of a run

`run.json` holds `config_digest`, the tagged digest of the effective `[orch]` and `[aicore.providers]` (`orch.settings.config_digest`),
and `config_layers`, `[{layer, file, present}]` of the layers behind it. Each piece of work has `options_digest`: the digest of its
merged run options, written as `digest` in `<item>/options.json`. The events carry them: `orch.run.started` has `config_digest` and
`project_resolution`, the `orch.run.stage.finished` events of the conductor have `options_digest` (event-data/v1, optional fields).
The same configuration and options give the same digests; a changed override gives another one.

## The cycle of one piece of work

Every step has a key and is recorded in `state.json` once it closes; the work source is reached only through
`orch.py source …` and the roles only through the launch catalog.

| Step | Who | What |
| --- | --- | --- |
| claim | work source | `source claim` with a submission of this run; `--batch` claims the next ready piece each time |
| `brief` | work source | `source brief`; the execution-input is read from the artifact store; the base revision is recorded |
| `prepare` | orch | `source prepare` writes the launch-plan of the scenario's pack (routes, policy decision) |
| `scout` | context-scout (economy) | when the pack has a scout or condense stage; the result is a cached context map |
| `executor.N` | executor | the execution-input, the context map, the run rules, the repository rules of an isolated role and, for a correction, its package; returns a closed `stage-report`; the conductor then reads the changed paths from git |
| `checks.N` | deterministic | every `acceptance`/`impact` command check of the cadences asked for, with a check-evidence file per check |
| `review.N` | reviewer (default `grok/grok-4.7/high`) | read-only, the diff against the base and the check results; returns `review-findings` |
| `triage.N` | triager | reproduces every finding; returns `triage-result` (confirmed with a correction package, or rejected with a reason) |
| `close` | registrar (economy) | only when a layer of the options names the registrar in `stages`: a model runs the one `source register` command the conductor built (the launch catalog allows it exactly `python3 *orch.py source register *`) and answers with its output; it never sees the task |
| `register` | work source | `source register` with the report, the status and the evidence; a repeat is a no-op, so after a closer it only confirms the record, and when the closer failed it records the result and `close` says `conductor` and why |
| `commit` | work source | `source commit` with the changed paths and the artifact folder, when the pack's `git_action` is `commit` |

Red checks get `limits.check_fixes` corrections; confirmed findings `limits.corrections` corrections within
`limits.review_rounds` rounds (2 rounds and 1 correction by default, as in the `full` pack). These limits are
**targets**: past one, a further round runs while the last correction made progress (the set of red checks changed or
fewer failures show; fewer or other findings to correct), up to `limits.ceiling_factor` times the target (2 by
default). Every round past a target prints a `LIMIT_OVER` beacon and leaves a plan note. A correction that changed
nothing, or the ceiling, registers the piece `blocked` with an escalation (`CHECKS_RED`, `REVIEW_LIMIT`). A finding that
did not reproduce is never a reason for a correction; a confirmed review finding corrected together with red checks is
sent to the executor once, in that one round.

Review rounds are tiered by severity (`review.correct_min_severity`, default `Major`; `review.pre_final`, default
`true`). Round 1 looks for everything. Only confirmed findings of that severity or higher go to a correction; the
others are not corrected: they travel as `note` issues ("deferred minor finding…")
in the registered report, so the cleanup of the phase can fix them together. After a correction the next round is a
pre-final audit (when `review.pre_final` is on): the reviewer is told to report findings of that severity or higher
only. A round with no confirmed finding at the floor ends the review.

The executor sees only its prompt: the execution-input, the context map, `rules` and the correction package. It never
sees the plan or the plan's command line. It runs the tests of what it changed; the conductor runs the acceptance
checks (their commands are listed in the prompt so the executor does not repeat them) unless
`checks.executor_runs_checks` asks it to. A gap that needs the owner is `blocked` with one `escalation` issue per
missing thing; `done_with_deviations` needs a `deviation` issue.

**What changed is read from git.** After every executor round the conductor lists the dirty paths of the tree, minus
what the work source wrote when it claimed, the artifact folder, the plan folder of the input and the conductor
reports. The union over the rounds is the `changed_paths` of the registered report and the paths of the commit (a
correction round lists only its own paths; the conductor does not lose the first round's). Paths that
`scope.write_set` does not own are, with `scope.outside: deviation` (default), listed to the reviewer, recorded as a
`deviation` and committed with the piece; with `block` the piece is blocked right after the executor
(`OUTSIDE_WRITE_SET`).

**A result outside its contract** goes through three steps: healing by rule (`heal.py`: one honest reading of a form
mismatch, such as a string exit, an escalation in a report that is not blocked, a GREEN verdict with a Major finding;
every mend is said in a `RESULT_HEALED` line and, for a stage-report, a `note` issue; a status is never raised, nothing
is invented); a repair by the `report-fixer` role (an economy model that rewrites only the result block from the role's
own answer, `limits.repairs` times, default 1; `RESULT_REPAIRED`); and only then a repeat of the whole role within
`limits.retries` per step. A triage that rejects a Blocker or Major finding without a reproduction that ran is outside
the contract.

### Stops

The conductor stops only on:

| Code | When |
| --- | --- |
| `RUN_TIMEOUT` | the active time of the run passed `limits.run_timeout_s` (default 0: off); the current role is cancelled; raise the limit, then resume |
| `ITEM_BLOCKED` | a piece is blocked and `on_blocked` is `stop` (or it left changes in the tree) |
| `ROUTE_UNDERSHOOT` | the executor route is below the class or effort the work requires |
| `SANDBOX_UNAVAILABLE` | `instructions.sandbox` is `require` and a Claude Code role with Bash is on the route, or a Codex route carries `--sandbox`, and the sandbox cannot start (`orch.py doctor`, `orch.sandbox`); the run stops before any work |
| `PROVIDER_UNAVAILABLE`, `TRANSPORT_UNSUPPORTED`, `LAUNCH_UNKNOWN` | a role cannot start: checked for every required role before any work of a piece (an optional scout or report-fixer is skipped instead); a route with `transport: acp` (today the grok `executor` entry; the conductor builds no `bounded-implementer` route) stops with `TRANSPORT_UNSUPPORTED` |
| `ROLE_FAILED`, `ROLE_OUTPUT_EMPTY`, `ROLE_OUTPUT_INVALID` | a role kept failing after healing, repair and `limits.retries` |
| `PROVIDER_AUTH`, `PROVIDER_AUTHZ` | the provider refused the credentials or the operation (class `authentication`, `authorization`): never repeated, log in or fix the access, then resume |
| `PROVIDER_QUOTA` | the usage limit is exhausted (class `quota`, `rate_limit`) and the reset is further than `limits.provider_wait_max_s` or unknown, with no admissible `fallback_routes` entry; or the provider of a role is gated on this machine (see Capacity gates). The message names the reset time (UTC) and says `resume after` it |
| `PROVIDER_REFUSED` | the provider refused the request (class `invalid_request`, `content_policy`): a repeat would be refused again |
| `PROVIDER_CONTEXT` | the request does not fit the context window (class `context_limit`); the prompt is not rebuilt yet |
| `MODEL_UNAVAILABLE` | the model is not available to the account (class `model_unavailable`), repeated within `limits.retries` first |
| `TIMEOUT` | only when a ceiling was asked for (`stage_timeout_s`, `stage_idle_timeout_s`); none by default |
| `WORKTREE_DIRTY` | changes outside the conductor reports before new work (`run --adopt` takes over changes inside the write set of the first piece) |
| `CLAIM_BLOCKED`, `BRIEF_REFUSED`, `PREPARE_REFUSED`, `REGISTER_REFUSED`, `COMMIT_REFUSED`, `WORK_SOURCE_*` | the work source refused or is unavailable |
| `OPTIONS_INVALID`, `POLICY_UNKNOWN`, `MODEL_CATALOG_UNAVAILABLE` | the run options, the pack or the model catalog are unusable |

With `on_blocked = "report"` a blocked piece that changed nothing is registered, its records are committed and the
run goes on; a blocked piece with changes stops the run, because its partial work would leak into the next piece.

### Beacons: long and costly runs are reported, not cut

Nothing is stopped for being long or for its tokens. The conductor prints `info` lines with a stable `reason_code`
instead; `conduct.py status` shows the latest one of the running step:

| Code | When | What it says |
| --- | --- | --- |
| `STAGE_SLOW` | every `limits.stage_warn_s` (default 2700) of one role run | how long it runs, its last command and the processes of its session (a test run, a build) |
| `STAGE_IDLE` | every `limits.stage_idle_warn_s` (default 600) without output | the same; `no child process` means the model call itself is silent |
| `CHECK_SLOW` | every `limits.check_warn_s` (default 900) of one check | the check id and its processes |
| `RUN_SLOW` | every `limits.run_warn_s` (default 7200; 0 off) of the **active** time of the run (segments of its processes: a resume a day later does not count the day) | active time, closed and left pieces, the current step; one plan note per threshold; never stops the run |
| `BUDGET_OVER` | once, when the fresh tokens of a piece pass `limits.tokens_max` | the tokens used |
| `LIMIT_OVER` | a round past a target of `limits.*` | the target, the ceiling and why it goes on |
| `RESULT_HEALED`, `RESULT_REPAIRED`, `REPAIR_FAILED` | a role result was mended | what was mended |
| `INPUT_REBUILT` | the plan changed during the piece | the input of the next executor round |
| `PROVIDER_WAIT` | a role failed at the provider and waits before its repeat: a usage limit that resets within `limits.provider_wait_max_s`, or a transient failure after the provider CLI had repeated the request itself (`api_retry`) | the failure class, the wait in seconds and the UTC time it ends; the wait looks at the cancel every second |
| `ROUTE_FALLBACK` | a role moved to a `fallback_routes` entry (its provider failed beyond the wait, or was gated) | role, old route → new route, the class and the reason codes (`WAIT_TOO_LONG`, `RETRY_AFTER_UNKNOWN`, `CAPACITY_GATED`) |
| `CAPACITY_GATED` | the provider of a role is gated when the routes of a piece are chosen | the gate (until, class, who set it) |
| `GATE_NOT_WRITTEN` | an exhausted quota could not be recorded as a gate (the run goes on) | why |
| `ROLE_LINGERED` | the final `result` of a role was out and its process was still alive `RESULT_GRACE_S` (30 s) later, typically a provider CLI waiting for a background task the model started (a monitor loop that never ends) | the answer is complete; the process group was stopped and the role counts as exited 0 |
| `ISOLATION_PARTIAL` | the provider CLI does not know its isolation flag, or `instructions.sandbox` is `prefer` and the provider sandbox cannot start (once per run) | roles are isolated by the environment only; the commands of Claude Code roles run under the filesystem guard only |

A person who runs the conductor sees them on stderr; an observer agent reads them from the journal and decides whether
the run is healthy (a long test run is) or needs a look. `stage_timeout_s`, `stage_idle_timeout_s` and
`check_timeout_s` still set hard ceilings when asked for; all are off by default.

### Provider availability

`aicore.providers.available.<provider>.enabled = false` (machine, `--config` file or flags; the project layer cannot set it,
`CONFIG_LAYER_FORBIDDEN`) switches a provider off for routing, whatever `providers.selection` rolled out into the project. A route
on it is `PROVIDER_DISABLED: aicore.providers.available.<id>.enabled = false (<layer>)`: `run --dry-run` lists it under
`unavailable`, route choice moves the role to the first admissible `fallback_routes` entry (`ROUTE_FALLBACK`), and without one
the preflight stops the run with `PROVIDER_UNAVAILABLE` before any work (an optional scout or report-fixer is skipped). A role
is routable when the provider is enabled, its CLI is found, the transport and sandbox work and no capacity gate is open.

### Route explain

`orch.py route explain --role R [--plan P --item I] [--scenario S] [--json]` shows why a role runs where it does, without
starting anything: the `candidates` (the `stages` of the options, the reviewer selector, `[orch.conductor]` or the launch
catalog, and the `fallback_routes` of the role) each with `available` and the `problem` that rules it out
(`PROVIDER_DISABLED`, `TRANSPORT_UNSUPPORTED`, `SANDBOX_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`, `PROVIDER_QUOTA`), the `selected`
route with the layer each of `provider`, `model_class`, `effort` and `model` came from (and `moved` when route choice took a
fallback), the `stop` when no route can start, the `aicore.providers.available` value and layer of each provider
involved, and the `gates` in force. Without `--plan` and `--item` the options are those of the configuration, the
scenario and the pack; with them they are the recorded options of the newest conductor run of that item
(`ITEM_UNKNOWN` when there is none), including the minimum class and effort the work required. A candidate or the selected
route that a run would refuse before any work (the minimum of the work, `instructions.sandbox = require`) is reported with its
code, and `stop` names it.

### Capacity gates

A provider whose account quota is known to be exhausted is not started again before its reset. `conductor/gates.py` keeps
the machine file `<state>/orch/provider-gates.json` (`provider-gates/v1`, one entry per provider: `until` UTC, `class`,
`code`, `set_by`, `set_at`): a usage limit belongs to the account, so every conductor of the machine shares it. An entry
whose `until` is in the future forbids the provider; an expired entry is ignored and dropped by the next write; of two writes
the later `until` wins. A write is a read-modify-write under `flock` on `provider-gates.lock` beside the file and an atomic
replace, so two conductors never lose each other's entry and a reader sees a whole file. `conduct.py gates [--json]` lists
the gates in force; `gates --clear [PROVIDER]` removes one or all (so does deleting the file); it needs no project.

### Provider failures

A role that fails at the provider (it exits with an error, or its stream ends in one) is not told that its answer was rejected;
`ROLE_OUTPUT_INVALID` keeps the old text. The process adapters (`process.py`) read the failure signals of the stream and
`aicore.provider.errors` classifies them into an `error/v1` record (class, scope, `retry_after_s`, evidence); `_role` then asks
`retry.decide` once, with the class, whether the role writes (`tools.filesystem` of its manifest) and whether the tree changed since
the step began, `limits.retries` and `limits.provider_wait_max_s`, `on_error` (over the conductor default `unknown` → `retry`) and
the `fallback_routes` of the role:

| Decision | What the conductor does |
| --- | --- |
| `retry` | repeats the role with its original prompt; when the provider CLI had already repeated the request (`api_retries`) and the class is transient (`provider_internal`, `transport`, `rate_limit`), only after a pause (the reset time, else full jitter `min(300, 30·2^(attempt−1))·random()`): one owner repeats a request, the conductor only bounds the time |
| `retry_after` | a `PROVIDER_WAIT` beacon, the wait (cancel is looked at every second), then the repeat |
| `fallback_route` | takes the route retry.decide names after the admission: not below the class or effort the work requires, startable here (command, transport, provider sandbox) and not gated; then a `ROUTE_FALLBACK` beacon, `routes.json` is rewritten and the next calls of the role use the new route; a route that fails the admission is a stop with the reason |
| `reconcile` | a writing role that left changes in the tree continues: the repeat prompt is the original one plus `# The previous attempt failed and left changes` (base commit, `git status --short`, `git diff --stat HEAD`, the checks closed so far). The changes are never discarded; a reconcile counts against `limits.retries` too |
| `replan` | `PROVIDER_CONTEXT` |
| `stop` | the code of the class (see Stops); the repeats of one step are bounded by `limits.retries` |

An exhausted account quota with a known reset is also written as a capacity gate when it is seen, so the next piece and the
next run do not start the provider again; a wait that is longer than `limits.provider_wait_max_s`, or a quota whose reset
is unknown, goes to a fallback route or stops (`WAIT_TOO_LONG`, `RETRY_AFTER_UNKNOWN`). The role's step result records
`error` (error/v1), `api_retries` and `decisions`.

The reviewer has a fallback by default (`fallback_routes`): a review is too dear to lose when grok cannot start (no CLI), is
gated (its quota is exhausted) or fails and the policy says `fallback_route` (`on_error`). A route that cannot start, or is
gated, is replaced when the routes of a piece are chosen (`ROUTE_FALLBACK`, `CAPACITY_GATED`); a role that fails at the provider moves
by the decision of `retry.decide`. `run --dry-run` shows what a run would do: `fallback_routes`, the `gates` in force, the
`reviewer` selector with the layer that set it, and `route_notes` (a route replaced at selection and why).

A fallback route is admitted by the same rules as a route at the start: not below the class or effort the work requires,
startable here (command, transport, provider sandbox, `instructions.sandbox: require` for a Claude Code role with Bash) and not
gated. A route taken is remembered in the state of the piece, so a resumed run starts on it, not on the route that failed.
A role is checked against the gates again when it starts: when an earlier role of the piece exhausted its provider, it moves to
a fallback route, or waits when the gate ends within `limits.provider_wait_max_s`, or stops with `PROVIDER_QUOTA` before the call.

When the provider of a role is gated as the routes of a piece are chosen, the role moves to the first admissible
`fallback_routes` entry (`CAPACITY_GATED`, `ROUTE_FALLBACK`); without one the piece stops with `PROVIDER_QUOTA` before any
work (an optional context scout is skipped instead, when its stage allows it).

### Resume

`resume --run RUN --retry ITEM` also takes back a piece that stopped as `blocked` (after the source has reopened it, for example the planner's `reopen`): the input is built again from the amended plan, and the steps from the executor round that reported `blocked` on, and the closing steps, are repeated; the earlier rounds and the work in the tree are kept (`RETRY_NOT_BLOCKED` when the piece is not blocked). `resume --run RUN` runs the same loop again. Without a retry, a plan amended while a piece runs reaches its next executor round anyway: the brief is asked again before every correction round and replaces the input when its digest changed (`INPUT_REBUILT`).

`run --adopt` starts the first piece on a tree that already holds an earlier attempt of it (all changed paths inside its
write set, else `WORKTREE_DIRTY`): the executor is told to check and finish that work, not to start over. The artifact
folder of the piece (`artifacts/<item>/…`: evidence, review verdict of the earlier attempt) and the plan folder are
always allowed: they are not counted as the role's changes and are not listed to the executor.

A piece that stops before any executor round (`WORKTREE_DIRTY` at adopt, a refused route, a failed brief or prepare) gives
its claim back to the work source (`CLAIM_RELEASED`; the source's `release` op), so a new `run` can claim it again without
`ITEM_OWNED`. A source without `release`, or a refusal, prints `CLAIM_KEPT`; then, or when a run died before it could
release, `release --run RUN --item REF [--reason TEXT]` does it by hand (`RELEASE_WORK_BEGAN` when an executor round ran:
`settle` or `resume --retry` the piece instead). `resume --run RUN` of a stopped run needs none of this: it claims
its own piece again.
`settle --run RUN --item REF --outcome … --reason …` sets the outcome of a piece by hand after it was finished or given up
outside the conductor (for example committed with the work source's own command); the journal keeps the reason. A closed step returns its recorded result and prints `stage.skip`; a
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
| `instructions` | `isolate_roles` (default every role; a listed role starts without the project instructions and customizations of its provider: for Claude Code `--safe-mode` plus no `CLAUDE.md`/project memory, which cuts the start-up context from ≈16 K to ≈6 K tokens and drops the plugins, MCP servers, user skills and hooks; grok was probed and does not read the repository `CLAUDE.md`); `module_rules` (default `["module-folders", "module-boundaries", "engineering-invariants"]`: the instruction sections, by the last part of their `## <scope>.<name>` heading, that a role still gets from the CLAUDE.md or AGENTS.md of the root and of every folder on the way to a write-set path, as a short Repository rules block). An isolated role gets the text of its `skills` in the prompt, because its provider loads none by name; `sandbox` (`off` \| `prefer` default \| `require`: the provider sandbox for shell commands, see Sandboxes) and `sandbox_domains` (default `[]`: the domains a sandboxed Claude Code role may reach) |
| `scope` | `outside`: `deviation` (default) or `block`, for paths changed outside `scope.write_set` |
| `checks` | `parallel` (1–8, default 1: command checks run together), `overlap_review` (default false: the checks of a round run while the review of that candidate reads it; red checks drop that review and it is repeated), `kinds` (default `["acceptance","impact"]`), `cadence` (default `["item","phase"]`; `["item"]` leaves out the `cadence: phase` checks, the full pass that the planner bridge gives to the item closing a phase), `red_first` (default true: in a correction round the previously red checks run first, and the others only when those are green; false runs every check in every round), `executor_runs_checks` (default false: the executor runs only the tests of the code it changed) |
| `review` | `correct_min_severity` (`Blocker`/`Major`/`Minor`/`Nit`, default `Major`), `pre_final` (default `true`), `audit_scope` (`corrected` default: the round after a correction reads only the corrected findings and the lines their correction touched; `full`), `final_correction` (default `false`: when no further round is allowed the findings are corrected without another review, noted in the plan, instead of `REVIEW_LIMIT`) |
| `limits` | targets `review_rounds` (0–5), `corrections` (0–3), `check_fixes` (0–3) and their `ceiling_factor` (1–5, default 2); `retries` (0–5, per step); `repairs` (0–3, default 1); `provider_wait_max_s` (default 900: the longest wait for a provider limit to reset); beacons `tokens_max`, `stage_warn_s` (2700), `stage_idle_warn_s` (600), `check_warn_s` (900); ceilings, all off by default: `stage_timeout_s`, `stage_idle_timeout_s`, `check_timeout_s` |
| `on_error` | `{<failure class>: {action, max?}}`, the form of the run-policy `on_error` (`action`: `stop`, `retry`, `retry_after`, `fallback_route`, `replan`, `reconcile`); layers merge by class; the conductor default is `unknown` → `retry` (see Provider failures) |
| `fallback_routes` | `[{role, provider, model_class, effort?}]`: the routes a role may move to when its provider cannot serve it; default: the reviewer (grok) moves to `claude-code`, class `frontier`, effort `high`. A layer replaces the list, so a layer that names routes drops the default for roles it does not name; `[]` switches every route, the default included, off |
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
| `.swissknifeman/orch/reports/<run>/` | ignored | `observer.json`, `observer.md` (written when the run ends, after its last commit) |
| `.swissknifeman/orch-artifacts/<run>/<item>/` | committed | the artifact folder of a source without `artifacts_dir` |
| the plan (JSON) | committed | through the work source's own commit |

Role streams never go into the artifact folder; a review verdict there is short and points at the stream in state.
The shared gitignore policy (`packages/aicore/configs/gitignore-policy.json`, entries `swissknifeman-state` and
`orch-conductor-reports`) states the same for every connected project, and `orch.py doctor` warns when the runtime
folder or the reports folder is not ignored (`orch.conductor-gitignore`, `orch.conductor-reports`, `check-result/v1`
with `--json`).

## Sandboxes

The tools of a role are confined by the provider's own sandbox, not by the conductor: Claude Code (Bash) and Codex use
bubblewrap in user and network namespaces, Claude also `socat`. It limits the **shell commands of a role and their
children**; the agent process is not limited (its model API stays reachable), and `scripts/ro-run.py` restricts only the
filesystem writes of the process. So `network` in a role manifest is intent: the dry-run says which roles it is enforced
for.

- `orch.py doctor` (`orch.sandbox`) probes it: `bwrap` and `socat` on PATH, and `bwrap --ro-bind / / --unshare-user
  --unshare-net --dev /dev --proc /proc true` (10 s, cached for the process; it changes nothing). On Ubuntu 24.04 and later
  `kernel.apparmor_restrict_unprivileged_userns = 1` stops it without an AppArmor profile for bwrap
  (`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`); the profile is a change of the machine, made by its owner.
- `instructions.sandbox`: `prefer` (default) adds `--settings '{"sandbox": {"enabled": true, "allowUnsandboxedCommands":
  false, "failIfUnavailable": true, "network": {"strictAllowlist": true, "allowedDomains": <sandbox_domains>}}}'` to every
  Claude Code role whose `--tools` include Bash (only the `sandbox` block; the provider merges it with the user's settings).
  A role whose manifest declares `network: allowed` gets no `strictAllowlist` and no `allowedDomains`. When the sandbox cannot
  start, `prefer` goes on without `--settings` and says `ISOLATION_PARTIAL` once; `require` stops with `SANDBOX_UNAVAILABLE`
  before any work; `off` adds nothing. `strictAllowlist` with no domains also blocks the network of the project's own tests: put
  the domains they need into `sandbox_domains`.
- A Codex route with `--sandbox read-only|workspace-write` is unavailable while the sandbox cannot start: `--dry-run` shows
  `available: false` and `SANDBOX_UNAVAILABLE: <reason>` in `unavailable`, a run stops with `SANDBOX_UNAVAILABLE`. Its argv is
  not rewritten.
- `conduct.py run --dry-run` also prints `sandbox: {available, reason}`, `network: {role: {declared, enforced, by}}` with `by` one
  of `claude-sandbox`, `codex-sandbox`, `claude-tools` (a Claude role without Bash has no command to confine) or `null`, and
  `warnings` for every role that declares `network: none` while nothing enforces it (the grok `reviewer`; every Claude role
  when the sandbox is off or cannot start).

## Observer

The observer only reads: the journal and state of the run and the `orch.run.*` and `planner.*` events of the
project's aicore event journal since the run started. At the end of every run (also a stopped one) the conductor
writes `observer.json` and `observer.md`: repeats and resumes, red checks per check id, review findings by severity,
triage confirmed and rejected, idle time between stages, seconds and tokens by role, scout cache hits, the outcome of
each piece and proposals to improve the run options. `conduct.py observe --follow` prints the notable lines of a run
that is still going from another terminal; `conduct.py observe` writes the report again.

## Configuration

The `report-fixer` role runs on the conductor's provider by default (an economy model: Claude Code haiku, codex luna, grok);
a `stages` entry `{"role": "report-fixer", "provider": …, "model_class": …}` moves it, and `limits.repairs: 0` turns it off.

`[orch.conductor]` (`configs/config.schema.json`): `provider` (default `claude-code`), `reviewer`
(`grok/grok-4.7/high`), `registrar` (`orch/conductor`), `rules`, `on_blocked`, `limits.tokens_max`,
`limits.stage_timeout_s`, `limits.check_timeout_s`, and `argv.<role>`: the command line of a role instead of the
launch catalog entry (`{model}`, `{effort}`, `{cwd}`, `{orch}` are filled in). `argv` is machine-wide: a project file
cannot set it. The tests use it to put fake providers in place of the real CLIs.

Grok in the conductor is the `reviewer` and the `report-fixer` only: its `executor` and `bounded-implementer` launch entries use the
`acp` transport, which the conductor does not drive. `conduct.py run --dry-run` shows such a route as `available: false` with
the reason in `unavailable` (`TRANSPORT_UNSUPPORTED: …`, or `PROVIDER_UNAVAILABLE: <command> not found`), and a run stops before
any work.

The grok `reviewer` runs under `scripts/ro-run.py` (Landlock): it may write only to temporary directories, `~/.grok` and
`{cwd}/vendor`. `{cwd}/vendor` is there because the tests of PHP projects keep their caches in it (commit `5addff330`);
the argv is not widened for anything else. Claude Code roles never use `--bare` (it does not read the subscription login) and
start with `--permission-prompts none`, so a request that would ask for permission is denied instead of waiting.

## Plan engines without `orchestration.options`

The planner declares `orchestration.options` as an extension slot and keeps no copy of this contract: the planner
bridge supplies `run-options` to it (`extends` in its `bridge.json`), so `set` and `check` validate the options by
this schema. A plan engine without the slot refuses the fields with `unexpected property`; a planner that does not find
the bridge refuses the options with `EXTENSION_UNAVAILABLE` and still keeps `orchestration.scenario`. The planner
bridge then reads the scenario and the options from orchestration overlay documents (`add-document`, id
`orchestration-<scope>`, section `orchestration` holding `{"scenario"?, "options"?}`, applying to a phase, an item or,
with `global`, the plan). A field of the same level wins over an overlay.
