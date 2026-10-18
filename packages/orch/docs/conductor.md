# Conductor

`orch conduct` (`swissknifeman orch conduct`, or `python3 -I .swissknifeman/launcher.py orch conduct` in a project) takes pieces of work from the work source and drives each one through the roles of its
run-policy until it is green or stops honestly. It is shipped with orch and tuned by configuration and by the run
options of the work; it is never rewritten for a run. The conductor itself decides nothing: it branches only on exit
codes, on the verdicts of the closed role results (`schemas/conductor/v1`) and on the limits of the run options.
Models are used only for the narrow roles: context scout, executor, reviewer, triager and, when asked for, the registrar that records the result.

```text
orch conduct [--config FILE] [--project DIR] run --plan P (--items REF… | --ready [--max-items N]) [--plans-root DIR]
           [--options FILE] [--batch | --no-batch]
           [--fence project|plan] [--allow-path DIR ...] [--adopt] [--frozen] [--dry-run [--scenario S]]
           [--quiet | --json-lines] [--model-catalog FILE]
orch conduct [--config FILE] [--project DIR] run --input FILE [--commit] [--scenario S] [--options FILE] [--dry-run]
           [--quiet | --json-lines] [--model-catalog FILE]
orch conduct [--config FILE] resume --run RUN [--retry ITEM ...] [--frozen] [--quiet | --json-lines]
orch conduct settle --run RUN --item REF --outcome done|done_with_deviations|blocked --reason TEXT
orch conduct answer --run RUN --item REF --question ID (--option ID | --text TEXT) [--by WHO]
orch conduct questions [--run RUN] [--json]
orch conduct prompt explain [--run RUN] --item REF --step STEP [--json]
orch conduct status [--run RUN] [--json]
orch conduct observe [--run RUN] [--follow]
orch conduct gates [--json] [--clear [PROVIDER]]
```

For an agent that picks its own pieces (ask the source for ready lanes → `run --items` → `status`/`observe` → `resume`/`settle`) see [agent-mode.md](agent-mode.md).

Exit codes: 0 the run finished, 1 it stopped (or a command was refused; `CODE: message` on stderr), 2 usage,
130 interrupted (Ctrl-C, SIGTERM or SIGHUP: the role and check processes of the run are killed with their groups; `resume` continues).

## A piece that rewrites the orchestrator: `--frozen`

A piece that refactors `orch` changes the code of the process that conducts it. `run --frozen` (and `resume --frozen`) takes a snapshot of
the committed state (`git archive HEAD`) of the orchestrator checkout the command was started from (`packages/orch`, `aicore`, `planner`
and `bridges`) under `~/.cache/skm-frozen-runs/run-<time>-<pid>`, starts the same command from it with `--project` naming the project, and
removes the snapshot when the command ends. The install roots (`SKM_ORCH_ROOT`, `AICORE_ROOT`, `PLANNER_ROOT`, `PLANNER_PLAN_PY`) point
into the snapshot, `PYTHONPATH` is dropped, and the check commands of the pieces do not inherit roots outside the project, so they test the
project's own code. The work-source plugin stays the one the configuration registers. `resume --frozen` takes a new snapshot: that is how
a mechanism fix reaches a run stopped on purpose. Outside a checkout that holds the sources the flag is `FROZEN_UNAVAILABLE`.

## Work outside a plan: `run --input FILE`

`run --input FILE` conducts one piece of work without a plan: `FILE` is an `exec/v1` execution-input (`orch.py input adhoc`,
with `--provenance` for support work, or written by hand) served by the built-in file source
(`orch.worksource_file.FileWorkSource`, the same `work-source/v1` contract as the plugin). `--input` excludes `--plan`,
`--items`, `--ready`, `--max-items` and `--adopt`; the scenario is `--scenario`, else `default_profile`, and `--options` layers on top.
For a plan run `--scenario S` is passed to every claim (`orch source claim --scenario S`) and wins over the scenario the plan resolves for
the piece (`orchestration` of the item, phase, plan, overlays); the claim answer names it `scenario_source: invocation:--scenario`, and
an unknown scenario blocks the claim (`SCENARIO_UNKNOWN`) before the piece starts. Without the flag the plan's scenario applies.
`run.json` records `source = {kind: file, path, commit}`, the piece's reference is the `input_id`, and `resume` reads the same file
(a file that changed since the claim is `INPUT_CHANGED`: start a new run).

- Artifacts (stage-report, review verdict, check evidence, the registration receipt `register.json`) live in
  `.swissknifeman/orch-artifacts/<run>/<input_id>/`, never in `plans/`.
- The changes stay in the tree: `commit` is a no-op unless `--commit`; then it commits the changed paths and the artifact folder
  with the message `adhoc(<input_id>): <first line of the goal>` and nothing else.
- Provenance `plan_support` and `phase_support` also add a note to the plan's journal: after the registration the CLI asks the
  configured work source for the optional op `note` (`{collection, text, refs}`; the bridge of the plan engine writes it into the journal of the plan). A source without `note`, a refusal, or a plan without a phase (`refs` empty) is the
  `WORK_SOURCE_NO_NOTE` beacon; the work is registered anyway.

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
| claim | work source | `source claim` with a submission of this run. `--batch` (default) takes every piece of `--items A B C` in progress at the start (each piece is started under its own run, one after another, and a dependency that is in progress counts as met: `source claim --batch`, for the planner `start --in-progress-deps`) and the first prompt of the shared session lists them; `--no-batch` claims one at a time; `--ready` asks the source for its next ready lane (`lane` of the claim answer) and runs that lane as a batch too, or one piece at a time with `--no-batch`. In a batch a stop gives no piece back on its own: all stay in progress and `resume` goes on (`release` frees one by hand; `--no-batch` gives back a piece nobody worked on, as before). A piece whose executor round began counts as worked on, however the round ended |
| `brief` | work source | `source brief`; the execution-input is read from the artifact store; the base revision is recorded |
| `prepare` | orch | `source prepare` writes the launch-plan of the scenario's pack (routes, policy decision) |
| `scout` | context-scout (economy) | when the pack has a scout or condense stage; the result is a cached context map; its optional closing ```` ```json write-set ```` block (`scout-write-set`: `paths`, `tests`) is taken out of the map into the executor's "Expected paths" section, a missing or invalid block is ignored with a `RESULT_HEALED` beacon, and the hint never widens `scope.write_set` |
| `research.N`, `research-save.N` | researcher, work source | with `orch.research.policy = required` (every piece) or `conditional`, the default (a piece whose input says `research.need = required`); `off` never (see [Research](research.md)): the researcher (`implementation`, read-only, network allowed) asks the allowed sources of `[orch.research.sources]` with the one command `python3 …/orch.py research query` and returns a closed `research-result` (`query`, `claims` each with `sources`, `contradictions`, `unknowns`, `sources_used`; a statement without a source belongs to `unknowns`); `research-save.N` then has the work source keep it (`source research`: a plan keeps `research/<item>-<n>.json` and declares it as an input of the item, a file input keeps `research-<n>.json` in its artifacts) and, when the source cannot, the conductor keeps it in the artifacts of the piece and prints `RESEARCH_NOT_SAVED`; no source configured stops the run with `RESEARCH_NO_SOURCES` before any work |
| `executor.N` | executor | the execution-input, the context map, the run rules, the repository rules of an isolated role and, for a correction, its package; returns a closed `stage-report`; the conductor then reads the changed paths from git |
| `checks.N` | deterministic | every `acceptance`/`impact` command check of the cadences asked for, with a check-evidence file per check |
| `review.N` | reviewer (default `grok/grok-4.7/high`) | read-only, the diff against the base and the check results; returns `review-findings` |
| `triage.N` | triager | reproduces every finding; returns `triage-result` (confirmed with a correction package, or rejected with a reason) |
| `advice.N`, `triage.N-a` | advisor (`frontier`), triager | with `orch.advisor.enabled`: one opinion on a problem the work cannot solve alone, returned as `advice` (see [The advisor](#the-advisor-p104)); `triage.N-a` is the triage of review round N repeated with the advice, which then stands for the round |
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
A `deviation` issue carries `class` (`write_set`, `spec_mismatch`, `test_env`, `docs`, `dependency`, `environment`,
`other`), `impact` and `outcome` (`accepted`, `follow_up`, `owner_decision`); `severity`, `auto_fixable` and `evidence`
are optional and `next` stays free text. Healing fills a missing `class` with `other`, `outcome` with `accepted` and
`impact` with "not stated by the executor" (said in the note issue); the registration bridge writes the fields to the
`data` of the work source's journal event.

**What changed is read from git.** After every executor round the conductor lists the dirty paths of the tree, minus
what the work source wrote when it claimed, the artifact folder, the plan folder of the input and the conductor
reports. The union over the rounds is the `changed_paths` of the registered report and the paths of the commit (a
correction round lists only its own paths; the conductor does not lose the first round's). Paths that
`scope.write_set` does not own are, with `scope.outside: deviation` (default), listed to the reviewer, recorded as a
`deviation` (`class: write_set`, `outcome: accepted`, `evidence`: the paths; the paths the scout expected are named in the text) and committed with the piece; with `block` the piece is blocked right after the executor
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
| `REVIEW_LIMIT` | a batch limit refused a round while a confirmed Blocker finding is open | the finding ids and the limit |
| `DEPENDENCY_BLOCKED` | with `on_blocked: report` the run went on after a blocked piece, and a later piece of the run depends on it (`depends_on` of its claim): it is not started, stays in progress and the run ends here after the others; `resume --retry` the blocked piece, then `resume` |
| `DISK_LOW` | less than `limits.disk_min_gb` (default 5) GB free under the project or the temporary directory when the run starts or resumes, or before the checks of a round; the run stops (resumable): free the space, then `resume` |
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
| `TIMEOUT` | a role was silent for `stage_idle_timeout_s` (default 5400: a hang, not a long run), or a wall-clock `stage_timeout_s` was asked for (none by default) |
| `WORKTREE_DIRTY` | changes outside the conductor reports before new work (`run --adopt` takes over changes inside the write set of the first piece; `[orch.conductor] foreign_untracked = "keep"` lets untracked files of someone else stay: they are fingerprinted in `state.foreign`, announced as `FOREIGN_KEPT`, and never counted as a piece's work while their content stays the same) |
| `CLAIM_BLOCKED`, `BRIEF_REFUSED`, `PREPARE_REFUSED`, `REGISTER_REFUSED`, `COMMIT_REFUSED`, `WORK_SOURCE_*` | the work source refused or is unavailable |
| `OPTIONS_INVALID`, `POLICY_UNKNOWN`, `MODEL_CATALOG_UNAVAILABLE` | the run options, the pack or the model catalog are unusable |
| `OPTIONS_UNTRUSTED` | a layer of the work source (plan, phase, item, overlay, input file) loosens the isolation set below it: `instructions.sandbox`, `sandbox_domains`, `isolate_roles`, `scope.fence`, `scope.outside` or `scope.extra_paths` (see "Isolation floor") |
| `OPTIONS_UNSAFE_PATH` | an `extra_paths` entry (`--allow-path`) is the root, a system folder, HOME or an ancestor of it, the project or an ancestor, a secrets folder under HOME, or lies in `.git` (after `~` and symlinks are resolved) |
| `STATE_CORRUPT` | a JSON file of the run folder is not JSON; it names the file |
| `STUBS_INVALID` | a stub file cannot be used (a symlink, not a regular file, over 32 KiB, not UTF-8, a bad header or mode); the run stops before any role starts and names the file and the `STUB_*` code |

With `on_blocked = "report"` a blocked piece that changed nothing is registered, its records are committed and the
run goes on; a blocked piece with changes stops the run, because its partial work would leak into the next piece.

### Beacons: long and costly runs are reported, not cut

Nothing is stopped for being long or for its tokens. The conductor prints `info` lines with a stable `reason_code`
instead; `orch conduct status` shows the latest one of the running step:

| Code | When | What it says |
| --- | --- | --- |
| `STAGE_SLOW` | every `limits.stage_warn_s` (default 2700) of one role run | how long it runs, its last command and the processes of its session (a test run, a build) |
| `STAGE_IDLE` | every `limits.stage_idle_warn_s` (default 600) without output | the same; `no child process` means the model call itself is silent |
| `CHECK_SLOW` | every `limits.check_warn_s` (default 900) of one check; the time a check spends stopped (`SIGSTOP`, state `T`) is not counted, for the beacon and for `check_timeout_s` | the check id and its processes |
| `DISK_LOW` | a check runs and the free space went under `limits.disk_min_gb` (every `check_warn_s`; the check is not cut) | the file system and the free space |
| `RUN_SLOW` | every `limits.run_warn_s` (default 7200; 0 off) of the **active** time of the run (segments of its processes: a resume a day later does not count the day) | active time, closed and left pieces, the current step; one plan note per threshold; never stops the run |
| `BUDGET_OVER` | once, when the fresh tokens of a piece pass `limits.tokens_max` | the tokens used |
| `BUDGET_OVER` (`block …`) | a class of the blocks of a role prompt is past its `limits.prompt_*_tokens` (see Prompt manifest) | `block <kind> <origin> <tokens>`: the heaviest block of the class; the prompt is not changed |
| `LIMIT_OVER` | a round past a target of `limits.*` | the target, the ceiling and why it goes on |
| `LIMIT_OVER` (`batch: …`) | a round past `limits.review_rounds_batch`, `corrections_batch` or `findings_batch` (whole run, default 0 = none; same target and ceiling rule, counted from the state of every piece) | the target and why it goes on; when the ceiling refuses more rounds, an open **Blocker** stops the run with `REVIEW_LIMIT`, other confirmed findings become plan notes (no correction) |
| `RESULT_HEALED`, `RESULT_REPAIRED`, `REPAIR_FAILED` | a role result was mended | what was mended |
| `INPUT_REBUILT` | the plan changed during the piece | the input of the next executor round |
| `PROVIDER_WAIT` | a role failed at the provider and waits before its repeat: a usage limit that resets within `limits.provider_wait_max_s`, or a transient failure after the provider CLI had repeated the request itself (`api_retry`) | the failure class, the wait in seconds and the UTC time it ends; the wait looks at the cancel every second |
| `ROUTE_FALLBACK` | a role moved to a `fallback_routes` entry (its provider failed beyond the wait, or was gated) | role, old route → new route, the class and the reason codes (`WAIT_TOO_LONG`, `RETRY_AFTER_UNKNOWN`, `CAPACITY_GATED`) |
| `ROUTE_UPGRADED` | the reviewer route went up to the `suggested_model_class` of an executor `review_recommendation` (above the class of its route, admitted: startable here, not gated) | role, old route → new route, `<class> -> <class>`; a suggestion at or below the route, or a higher route that is not admitted, gives no beacon |
| `SESSION_ROUTE_CHANGED` | a piece resumes the shared executor session under another model or effort than the one that built it (the session continues, the provider cache of the old model is lost) | the old and the new route |
| `CAPACITY_GATED` | the provider of a role is gated when the routes of a piece are chosen | the gate (until, class, who set it) |
| `RESULT_SILENT_DENIAL` | a Claude role had tool calls refused without a prompt (`--permission-prompts none`) | the tools and how many calls (`Bash×2, WebFetch`), never their input; for the executor and the bounded-implementer the report also gets a `note` issue "tools denied without a prompt: …" with the way out (widen `allowedTools` in the launch catalog, or change the plan) |
| `GATE_NOT_WRITTEN` | an exhausted quota could not be recorded as a gate (the run goes on) | why |
| `ROLE_LINGERED` | the final `result` of a role was out and its process was still alive `RESULT_GRACE_S` (30 s) later, typically a provider CLI waiting for a background task the model started (a monitor loop that never ends) | the answer is complete; the process group was stopped and the role counts as exited 0 |
| `STUBS_CHANGED` | on `resume`, the stub files say something else than the snapshot of the run | the run keeps its snapshot; a new run reads the new text |
| `CHECK_CHANGED_TREE` | the checks of a round changed files of the project (their evidence and logs aside) | the paths; the evidence proves the candidate as it was before the checks |
| `ISOLATION_PARTIAL` | the provider CLI does not know its isolation flag, or `instructions.sandbox` is `prefer` and the provider sandbox cannot start (once per run) | roles are isolated by the environment only; the commands of Claude Code roles run under the filesystem guard only |

A person who runs the conductor sees them on stderr; an observer agent reads them from the journal and decides whether
the run is healthy (a long test run is) or needs a look. `stage_timeout_s` and `check_timeout_s` still set wall-clock
ceilings when asked for (off by default). Only silence stops work by default: a role whose stream has not grown for
`stage_idle_timeout_s` (5400) or a check whose log has not grown for `check_idle_timeout_s` (3600) is hung; 0 turns
either off.

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
replace, so two conductors never lose each other's entry and a reader sees a whole file. `orch conduct gates [--json]` lists
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
is unknown, goes to a fallback route or stops (`WAIT_TOO_LONG`, `RETRY_AFTER_UNKNOWN`). A quota that is still refused after the reset the provider named (`retry_after_s` 0) counts as unknown: no repeat at once, no gate, and the stop message gives the provider's own reset time as already past, not "resume after now". The role's step result records
`error` (error/v1), `api_retries` and `decisions`.

The reviewer has a fallback by default (`fallback_routes`): a review is too dear to lose when grok cannot start (no CLI), is
gated (its quota is exhausted) or fails and the policy says `fallback_route` (`on_error`). A route that cannot start, or is
gated, is replaced when the routes of a piece are chosen (`ROUTE_FALLBACK`, `CAPACITY_GATED`); a role that fails at the provider moves
by the decision of `retry.decide`. `run --dry-run` shows what a run would do (`batch`: whether the pieces are one batch, the default for several; `ready`: whether `--ready` picks them): `fallback_routes`, the `gates` in force, the
`reviewer` selector with the layer that set it, and `route_notes` (a route replaced at selection and why).

A fallback route is admitted by the same rules as a route at the start: not below the class or effort the work requires,
startable here (command, transport, provider sandbox, `instructions.sandbox: require` for a Claude Code role with Bash) and not
gated. A route taken is remembered in the state of the piece, so a resumed run starts on it, not on the route that failed.
A role is checked against the gates again when it starts: when an earlier role of the piece exhausted its provider, it moves to
a fallback route, or waits when the gate ends within `limits.provider_wait_max_s`, or stops with `PROVIDER_QUOTA` before the call.

When the provider of a role is gated as the routes of a piece are chosen, the role moves to the first admissible
`fallback_routes` entry (`CAPACITY_GATED`, `ROUTE_FALLBACK`); without one the piece stops with `PROVIDER_QUOTA` before any
work (an optional context scout is skipped instead, when its stage allows it).

### Deviations fixed inside the piece

A finished executor round that reports a `deviation` issue with `auto_fixable: true` gets one correction round before the
checks, when all of this holds: every path of its `evidence` (`path:line`; a check id `V1` is not a path, and at least one
path is needed) lies inside `scope.write_set`; the input has acceptance checks; the class is not `spec_mismatch` and the
outcome is not `owner_decision`; and the `corrections` budget (`_allowance`, shared with the review corrections: the fix
is one correction) allows one more. The round is an executor round (`executor.<n+1>`) whose prompt has the section
`# Fix this deviation` (text, impact, evidence); the acceptance checks run on its result like on any candidate. The
beacons are `DEVIATION_AUTOFIX` (the round starts) and `DEVIATION_AUTOFIX_SKIPPED` (the budget is spent: the deviation
stays as reported). When the piece ends green the deviation is registered with `outcome: accepted`, `next: fixed in correction N`
and a plan note "deviation fixed in correction N: …"; when the executor reports it again, or the piece is blocked, it is
registered as the executor reported it. That the change is safe (no public interface, no product decision, no security
boundary) is the declaration of the role (`roles/executor.md`): the conductor checks only the write set and the checks.

### Dynamic review (risk score)

A pack without review (`solo`, `scout-solo`) still gets one for a risky piece. After the executor and check rounds the
engine collects facts (`risk.py` is a pure function, no model is asked): the changed paths (git), the paths outside
the write set, the changed lines, a red check in the first round, a deviation (reported or auto-fixed) and
`review_recommendation.recommended` of the executor. `risk.score(facts, config)` adds the weights of the features
that hold, at most 100:

| Feature | Holds when | Weight |
| --- | --- | --- |
| `public_cli` | a path matches `patterns.public_cli` (`bin/**`, `**/cli.py`, `packages/*/scripts/*.py`) | 25 |
| `schema` | `patterns.schema` (`**/schemas/**`, `**/migrations/**`) | 25 |
| `security` | `patterns.security` (`**/auth/**`, `**/security/**`, `**/permissions*`, `**/*secret*`, and the code that confines the roles: `**/sandbox*`, `**/ro-run*`, `**/launch-catalog.json`, `**/roles/*.json`, `**/run-policies/**`, `**/hooks/**`, `.github/workflows/**`, `**/install.sh`) | 30, critical |
| `shared` | `patterns.shared` (`packages/aicore/**`) | 15 |
| `diff_size` | more than `diff_lines` (400) changed lines | 10 |
| `red_first` | an acceptance check was red in the first round | 10 |
| `deviation` | a deviation | 10 |
| `outside_write_set` | paths outside the write set | 15 |
| `executor_recommended` | the executor recommended a review | 30 |

`[orch.conductor.risk]` (`weights.<feature>`, `patterns.<feature>`, `diff_lines`, `critical`) changes them in any config
layer; a weight of 0 turns a feature off. A feature named in `critical` (default `["security"]`) adds the review on its
own, whatever the score: a lone sandbox change weighs 30, below the threshold, and must still be read by a reviewer;
`critical = []` leaves only the threshold. Score and features (with their evidence) go to `<run>/<item>/risk.json` and
`state.risk`; a resume reads them again. At `review.dynamic_threshold` (default 60) `state.dynamic_review` is set, the
`reviewer` and the triage role are resolved on the spot (availability, gate, preflight, `routes.json`), the beacon
`REVIEW_ADDED` and a plan note name the score and the features, and the usual review → triage → correction cycle runs
within the limits. Below the threshold nothing changes. `review.dynamic: false` (give the reason in `rules`) or
`limits.review_rounds: 0` never adds a review; a pack with a review is not scored.

### Questions of the executor (D11)

The executor asks in `stage-report.questions[]` (`id`, `revision` ≥ 1, `kind` `clarification|decision|approval|credential`,
`text`, `options[{id,label}]?`, `answer_schema?`, `default?`, `blocking`, `assumed?`, `risk?`; `blocking: false` needs
`assumed`). A question is a decision tied to a saved continuation, never a waiting process (headless roles have no
stdin). `default` (a proposal), `assumed` (what the executor went on with) and a timeout are three different things:
nothing is ever answered on a timeout.

- `blocking: false`: an `assumption` issue "question Q: text — assumed: V" goes into the registered report; the work goes on.
- `blocking: true` needs a `blocked` report (an `escalation` issue; a report that says otherwise is repaired or repeated).
  `[orch.conductor] questions` decides (default `queue`):
  `queue`: the piece is `blocked` with the escalation `QUESTION: <id> <text>` and the run stops with `ITEM_BLOCKED`;
  `deny`: blocked at once with `QUESTION_DENIED: <id> <text>`, nobody is expected to answer;
  `defaults`: a question with a `default` is answered by it **once**, by `policy`, and the round is asked again as
  `executor.<n>-q<k>`; a question without one, or one the executor asks again, is queued;
  `advisor`: the advisor role reads the question ([The advisor](#the-advisor-p104)); advice that needs no owner answers it
  with `resolution.by = advisor`, any other advice is queued with the question.
- The question is saved in `state.questions[<item>]` and in `<run>/<item>/questions.json` with its binding
  `{run, item, step, input_digest}` (the digest of the input it was asked on), its `status` (`open`, `answered`, `applied`,
  `assumed`, `denied`, `stale`) and, once answered, `resolution {value, by, at}`. Beacons: `QUESTION_QUEUED`,
  `QUESTION_DENIED`, `QUESTION_DEFAULT`, `QUESTION_ANSWERED`, `QUESTION_OPEN` (retry without an answer), `QUESTION_STALE`.
- `orch conduct answer` writes only the resolution into `questions.json` (`QUESTION_UNKNOWN`, `QUESTION_NOT_OPEN`,
  `ANSWER_INVALID`: a decision takes one of its options, a clarification may take `--text`); it never touches the run.
  `orch conduct questions [--run R] [--json]` lists the open ones with their age; one older than `limits.question_warn_s`
  (default 1800, 0 off) is `OVERDUE`, in the observer report too.
- `resume --run R --retry ITEM` merges the answers into the state. An answer is applied only while the input is the one the
  question was asked on; otherwise it is `QUESTION_STALE`: the answer is kept as `stale_resolution`, the question gets
  `revision + 1` and the executor, which is not told that answer, asks it again. The executor of every later round gets the
  section `# Answers` (question, answer, who answered).

### The advisor (P10.4)

The role `advisor` (`roles/advisor.md|json`; class `frontier`; filesystem read, shell read-only, network allowed, no write
authority; launch entry `claude-code` with `--tools Bash,Read,Grep,Glob` and the one allowed command
`python3 *orch.py research query *`) gives one opinion on one problem. It is off by default: `[orch.advisor] enabled = false`.
With `enabled = true` the conductor asks it, deterministically and at most `max_rounds` times per piece (default 2, all
triggers together; past it the problem goes on as it would without an advisor):

| Trigger | The problem (`problem_ref`) | Applied advice |
|---|---|---|
| a blocking question, with `[orch.conductor] questions = "advisor"` | `question:<id>@<revision>` | the question is answered with `resolution.by = advisor` (the id of the recommended option; free text of its option when the question has none) and the executor round is asked again with `# Answers` |
| red acceptance checks once the `check_fixes` allowance is spent (before `CHECKS_RED`) | `checks:<round>` | one more correction round whose package carries the advice (`# Advice`) |
| a Blocker or Major finding the triager rejected | `findings:<review round>` | `triage.<n>-a`: the findings are triaged again with the advice |

The advisor reads the problem and the local evidence (the report of the executor, the red checks or the findings and the
triage, the diff against the head, cut at 40 000 characters) and may ask the sources of `[orch.research.sources]`. It answers a
closed `advice` (`schemas/conductor/v1/advice.schema.json`): `problem_ref`, `options[{id, text, pros, cons}]`,
`recommendation` (an option id), `confidence` (`low|medium|high`), `sources`, `needs_owner` and the optional `category`
(`security|destructive|public-api|scope-expansion|other`). A question with options keeps its option ids; a recommendation
that is not one of them is held. The advice is kept as `advice-<n>.json` in the artifacts of the piece, and its agent run in
`agents/<id>/` has `causation` = the `problem_ref`.

The human gate: advice with `needs_owner: true`, or with a `category` of `[orch.advisor] human_gate` (default `security`,
`destructive`, `public-api`, `scope-expansion`), is never applied by the conductor. It is handled as `queue`: the piece is
`blocked` with `QUESTION: <id> <text>` and the advice (file, recommendation, confidence, why the owner decides); the
question is saved with the advice (`advice` in `questions.json`). A held question of the executor is that question; for red
checks and a rejected finding it is a new question `orch-advice-<n>` (kind `decision`, the options of the advice). `orch conduct
answer` and `resume --run R --retry ITEM` then apply the owner's choice the same way: the correction round or the repeated
triage carries the option the owner chose (`by owner`), and the closed rounds, checks and the advice are not repeated. An
approval or a credential question is the owner's by its kind and is not asked of the advisor; the policy answers a question
only once. A failed advisor (`ADVISOR_FAILED`), a spent `max_rounds` (`ADVISOR_LIMIT`) or `questions = advisor` without
`enabled` (`ADVISOR_DISABLED`) leave the problem as it would be without one. Beacons: `QUESTION_ADVISED`. One opinion only:
no panel of several models.

### Resume

`resume --run RUN --retry ITEM` also takes back a piece that stopped as `blocked` (after the source has reopened it, for example the planner's `reopen`; a piece held on advice for the owner, whose question `advice-<n>` is answered, needs no executor round that reported `blocked`): the input is built again from the amended plan, and the steps from the executor round that reported `blocked` on, and the closing steps, are repeated; the earlier rounds and the work in the tree are kept (`RETRY_NOT_BLOCKED` when the piece is not blocked). `resume --run RUN` runs the same loop again. Without a retry, a plan amended while a piece runs reaches its next executor round anyway: the brief is asked again before every correction round and replaces the input when its digest changed (`INPUT_REBUILT`).

`run --adopt` starts the first piece on a tree that already holds an earlier attempt of it (all changed paths inside its
write set, else `WORKTREE_DIRTY`): the executor is told to check and finish that work, not to start over. The artifact
folder of the piece (`artifacts/<item>/…`: evidence, review verdict of the earlier attempt) and the plan folder are
always allowed: they are not counted as the role's changes and are not listed to the executor.

A piece that stops before any executor round (`WORKTREE_DIRTY` at adopt, a refused route, a failed brief or prepare) gives
its claim back to the work source (`CLAIM_RELEASED`; the source's `release` op), so a new `run` can claim it again without
`ITEM_OWNED`. A source without `release`, or a refusal, prints `CLAIM_KEPT`; then, or when a run died before it could
release, `release --run RUN --item REF [--item REF2 …] [--reason TEXT]` does it by hand (`RELEASE_WORK_BEGAN` when an executor round ran:
`settle` or `resume --retry` the piece instead); `release --run RUN --all` gives back every piece of the run that nobody worked on and that is not
closed (a batch that stopped before any work: all of its pieces are in progress), names the pieces it kept, and prints `RELEASED_ALL`. `resume --run RUN` of a stopped run needs none of this: it claims
its own piece again.
`settle --run RUN --item REF --outcome … --reason …` sets the outcome of a piece by hand after it was finished or given up
outside the conductor (for example committed with the work source's own command); the journal keeps the reason. A closed step returns its recorded result and prints `stage.skip`; a
piece that closed (done or blocked) is not claimed again; a piece that stopped half-way continues on its own working
tree. The configuration of the run is read again, so a fixed provider or a corrected `[orch.conductor.argv]` takes
effect.

## The environment of a check

A check command tests the project, so it does not inherit the install roots of the orchestrator the conductor runs from:
`AICORE_ROOT`, `SKM_ORCH_ROOT`, `PLANNER_ROOT` and `PLANNER_PLAN_PY` are removed from its environment when they lead outside the
project (a frozen or installed copy of the orchestrator would otherwise be tested instead of the project's own code, as a
piece that adds a module to the foundation found out). Roots inside the project stay.

## One review for a batch: `scripts/batch-review.py`

The conductor reviews piece by piece (`review.*`); a batch is better read once, together: `batch-review.py RUN` takes the
commits of the run from its `state.json`, keeps their production diff (`--include`, default `.`, the whole project,
without tests, docs, fixtures, goldens and plans; `--exclude` adds more), asks one reviewer (the launch catalog route:
`--provider grok --model grok-4.7 --effort medium`; `high` costs three times the time and found one more Major in the one batch measured) for correctness and safety defects with a concrete failing scenario, and
writes the reply to `<run folder>/batch-review.md`, the raw reply to `streams/batch-review.jsonl` and the measures (route,
pieces, commits, prompt bytes, seconds, exit code) to `batch-review.json`, and prints `BATCH_REVIEW: … in N s` on stderr. The time of a review is the reasoning of the reviewer (its output
tokens, about 30-60 per second), not its reading: `--effort` and `--max-tools N` (default 12, in the prompt) shorten it; `--dry-run` shows the pieces, the prompt size and the command. A finding of Major and above is fixed in a separate
commit after the batch.

## The review strategy of a batch

A batch of several pieces is reviewed in the way chosen **before the first piece runs** (`review.strategy`, default `auto`):

| `mode` | Review |
|---|---|
| `each` | every piece on its own, as the run policy and the risk score say (`review.*`, dynamic) |
| `groups` | one review per group of neighbouring pieces, after the last piece of the group |
| `single` | one review of the whole batch after its last piece |
| `none` | no review |

With `auto` the strategist decides (`review.strategist: model`, the default): one small model call on the economy route of the
triager sees every piece (title, goal, write set, route) and the choice the rules would make, and answers a mode, the groups
(in order, at most four pieces each) and the reviewer's effort. An answer that is not a partition of the batch in order, a
failed call or `review.strategist: rules` falls back to the rules (`policies/review_strategy.py`): neighbours that work on the
same folders are read together, a piece on the foundation or a `frontier` piece is read alone, security wording raises the
effort to `high`. Naming a mode in `review.strategy` skips the strategist. The plan is kept in `state.review_strategy` and
`review-strategy.json` of the run (a resume keeps it) and announced as `REVIEW_STRATEGY` with the effort the group review
will run at (an effort named by `reviewer` wins over the plan's).

In `groups`, `single` and `none` a piece has no review of its own. After the last piece of a group the conductor reads the
commits of the group once (`review_batch`: production code only, the same as `batch-review.py`), with the reviewer of the run
(`reviewer`, grok by default) at the effort of the plan, and keeps the reply in `group-review-<n>.md` of the run folder
(`state.group_reviews`). The reply must hold a `## Findings` section with `[Blocker|Major|Minor] file:line - defect` lines (a
list marker, a number, bold or backticks around them are read too) or the word `none`. The beacon `GROUP_REVIEW` gives the
counts; a reply that is neither is `GROUP_REVIEW_FAILED` (`format: malformed` in `state.group_reviews`), never a clean review, and
so is a group without a commit. Blocker and Major findings are corrected in a commit of their own: the conductor writes
`group-review-<n>.followup.json` (an execution-input with `provenance: review_followup`, the files the findings name as scope,
and as acceptance the command checks of the reviewed pieces, once each — `cd DIR && CMD` for a check with its own `cwd`, the
`cadence: phase` checks left out — so the correction is tested like the pieces were) and the beacon names the command, `orch conduct run --input <that file> --commit` (the executor corrects them, the conductor
checks and commits; native correction inside the run is not built, because the pieces of the group are already registered and
committed in the work source).

## Run options

`schemas/conductor/v1/run-options.schema.json`, closed:

| Key | Meaning |
| --- | --- |
| `stages` | `[{role, provider?, model_class?, model?, effort?}]`, roles `context-scout`, `executor`, `bounded-implementer`, `reviewer`, `triager`, `registrar` (naming it turns the closing stage on) |
| `reviewer` | `PROVIDER/MODEL[/CONTEXT][/EFFORT]` |
| `rules` | short rules for the executor |
| `skills` | `[{role, names}]`; `names: ["auto"]` asks the skills bridge (`[orch.conductor] skills_bridge`, a command run as a process with `--select --role R --provider P --project DIR --paths <write set files>`) for the skills of the role from the write set of the piece: the answer (`skills[].name`, `path`, `reason`) is kept in the state of the piece, an isolated role gets the text of the `SKILL.md` at the path the bridge names, beacon `SKILLS_SELECTED`; no bridge stops the piece `SKILLS_BRIDGE_UNAVAILABLE`, a failing one `SKILLS_SELECT_FAILED`; `auto` is not listed with other names |
| `instructions` | `isolate_roles` (default every role; a listed role starts without the project instructions and customizations of its provider: for Claude Code `--safe-mode` plus no `CLAUDE.md`/project memory, which cuts the start-up context from ≈16 K to ≈6 K tokens and drops the plugins, MCP servers, user skills and hooks; grok was probed and does not read the repository `CLAUDE.md`); `module_rules` (default `["module-folders", "module-boundaries", "engineering-invariants"]`: the instruction sections, by the last part of their `## <scope>.<name>` heading, that a role still gets from the CLAUDE.md or AGENTS.md of the root and of every folder on the way to a write-set path, as a short Repository rules block). An isolated role gets the text of its `skills` in the prompt, because its provider loads none by name; `sandbox` (`off` \| `prefer` default \| `require`: the provider sandbox for shell commands, see Sandboxes) and `sandbox_domains` (default `[]`: the domains a sandboxed Claude Code role may reach); `file_tools_rule` (default `true`: a `## File tools` run-rules block in the executor prompt that says to read and change files with Read/Grep/Edit/Write and not with Bash `cat`/`sed`/heredocs, added only when the route offers Read and Edit; measured before the rule: P10.2 81 Bash calls and 1 Edit, a heredoc edit 55–120 s of model time) |
| `session` | `executor`: `handoff` (default), `shared` or `per-item`. `handoff`: each piece of the run starts a fresh Claude Code session and its correction rounds resume it; the prompt of every piece carries the `## Run batch` block that names all pieces and, for each piece already done, a bounded `### Handoff of` (commit, summary, open issues, changed paths from its `register-report.json`) — a later piece does not re-read the transcript of the earlier ones on every turn (measured: a shared session carried 229K→372K tokens of context into the second piece, 18.5M cache-read tokens for one step). The piece of the kept session is `executor_session_item` of the run state. `shared`: the executor of every piece of the run, and of every correction round of a piece, resumes the Claude Code session of the previous executor (`claude -p --resume`), so the later pieces start with what the earlier ones learned, and the prompt of the first one carries a `run_rules` block `## Run batch` that names all pieces; the later ones are told that the session is resumed. Checks, review, register and commit stay per piece. `per-item`: a fresh session per executor step. `--batch` / `--no-batch` of `run` set it (`handoff` / `per-item`), and `--no-batch` also claims the pieces one at a time (layer `invocation:--batch`, above `--options`). Shared executors run without `--no-session-persistence` (the launch catalog sets it; a session that is not saved cannot be resumed), so their sessions stay in the provider's own store. A session that failed is forgotten and a fresh one starts; a provider other than Claude Code always starts fresh. The session id is kept in `executor_session` of the run state. |
| `scope` | `outside`: `deviation` (default) or `block`, for paths changed outside `scope.write_set`; `fence`: `project` (default: the executor may change any file of the project, `scope.write_set` is the expected change and a path outside it is reported by the executor as a `deviation`, not a block; the filesystem guard still confines it to the project) or `plan` (the write set is a fence: a path outside it makes the executor stop with `blocked`); `extra_paths`: directories outside the project the executor may also change (absolute or `~/…`; named in its prompt and added as `--rw` to its `ro-run.py` guard). `--fence` and `--allow-path DIR` (repeatable) set them for one run. `outside: block` with `fence: project` stops the piece at the first path outside the plan. |
| `checks` | `parallel` (1–8, default 1: command checks run together), `overlap_review` (default false: the checks of a round run while the review of that candidate reads it; red checks drop that review and it is repeated), `kinds` (default `["acceptance","impact"]`), `cadence` (default `["item","phase"]`; `["item"]` leaves out the `cadence: phase` checks, the full pass that the planner bridge gives to the item closing a phase), `red_first` (default true: in a correction round the previously red checks run first, and the others only when those are green; false runs every check in every round), `executor_runs_checks` (default false: the executor runs only the tests of the code it changed) |
| `review` | `correct_min_severity` (`Blocker`/`Major`/`Minor`/`Nit`, default `Major`), `pre_final` (default `true`), `audit_scope` (`corrected` default: the round after a correction reads only the corrected findings and the lines their correction touched; `full`), `final_correction` (default `false`: when no further round is allowed the findings are corrected without another review, noted in the plan, instead of `REVIEW_LIMIT`), `dynamic` (default `true`: a piece whose pack has no review gets one when its risk score reaches the threshold, see Dynamic review), `dynamic_threshold` (0–100, default 60); `strategy` (`auto` default, `each`, `groups`, `single`, `none`: how a batch is reviewed, see *The review strategy of a batch*) and `strategist` (`model` default, `rules`: who chooses it) |
| `limits` | targets `review_rounds` (0–5), `corrections` (0–3), `check_fixes` (0–3) and their `ceiling_factor` (1–5, default 2); `retries` (0–5, per step); `repairs` (0–3, default 1); `provider_wait_max_s` (default 900: the longest wait for a provider limit to reset); beacons `tokens_max`, `stage_warn_s` (2700), `stage_idle_warn_s` (600), `check_warn_s` (900); wall-clock ceilings, off by default: `stage_timeout_s`, `check_timeout_s`; silence ceilings: `stage_idle_timeout_s` (5400), `check_idle_timeout_s` (3600). Disk: `disk_min_gb` (5, 0 off: a run or the checks of a round do not start with less free space under the project and the temporary directory, `DISK_LOW`). Run-wide: `run_warn_s` (7200: a beacon when a run is longer) and `run_timeout_s` (0, off: a ceiling for the whole run); batch targets `review_rounds_batch`, `corrections_batch`, `findings_batch` (0, off: the totals of all pieces of a run); `question_warn_s` (1800: a beacon for a question waiting that long); `skill_tokens_max` (5000: the budget of the skills of one role); prompt blocks `prompt_core_tokens` (12000), `prompt_supporting_tokens` (30000) and `prompt_retrieval_tokens` (50000). |
| `on_error` | `{<failure class>: {action, max?}}`, the form of the run-policy `on_error` (`action`: `stop`, `retry`, `retry_after`, `fallback_route`, `replan`, `reconcile`); layers merge by class; the conductor default is `unknown` → `retry` (see Provider failures) |
| `fallback_routes` | `[{role, provider, model_class, effort?}]`: the routes a role may move to when its provider cannot serve it; default: the reviewer (grok) moves to `claude-code`, class `frontier`, effort `high`. A layer replaces the list, so a layer that names routes drops the default for roles it does not name; `[]` switches every route, the default included, off |
| `on_blocked` | `stop` or `report` |

`limits.question_warn_s` (default 1800; 0 off) marks a question that waits too long for an answer (see Questions of the executor).
`limits.skill_tokens_max` (default 5000; 0 off) is the largest text of one skill that an isolated role gets in its prompt (see Skill checks).
`limits.prompt_core_tokens` (12000), `limits.prompt_supporting_tokens` (30000) and `limits.prompt_retrieval_tokens` (50000) are the
measures of the classes of prompt blocks (see Prompt manifest); 0 switches the beacon off. They only measure: nothing is cut.

Layers merge from the general to the specific: defaults → `[orch.conductor]` → the run-policy pack (the routes of its
model stages, `review.triage`, `max_rounds`, `max_corrections`, `retries_budget`) → the layers of the work source (the
plan, the phase, the item) → `--options FILE`. A value of a more specific layer wins; `rules` append without repeats;
`limits` merge by key; `skills` replace the list of each named role; `stages` merge by role, and a layer that names a
model or a model class replaces both. Every source layer is validated (`OPTIONS_INVALID` names the layer); the numeric
bounds are `minimum`/`maximum` of the schema itself, so the schema is the one statement of them.
`<run>/<item>/options.json` records the merged options and, per key, the layer that set it.

**Isolation floor.** A layer of the work source is text a model may have written (an overlay document, an input file),
so it may tighten the isolation of a run but never loosen it: `instructions.sandbox` only moves along
`off < prefer < require`, `scope.fence` along `project < plan`, `scope.outside` along `deviation < block`;
`instructions.sandbox_domains` and `scope.extra_paths` may only repeat or shrink what the layers below allow;
`instructions.isolate_roles` may only grow. A layer that loosens one of them stops the run with `OPTIONS_UNTRUSTED` (the
key, the value and the layer below that set it). Only the configuration, the run-policy pack and the invocation
(`--options`, `--allow-path`, `--fence`) may loosen them; trust is a mark the conductor sets on its own invocation layers,
never the `source` label a layer carries. Limits, review and checks keys stay free for the plan (it raises
`check_timeout_s` or picks a scenario without review legitimately). Every `extra_paths` entry is resolved (`~`,
symlinks) and refused with `OPTIONS_UNSAFE_PATH` when it is the root, a system folder, HOME or an ancestor, the project
or an ancestor, a secrets folder under HOME (`.ssh`, `.gnupg`, `.aws`, …) or inside `.git`; the canonical path is the one
the filesystem guard gets and `options.json` records.

The work source hands the layers over in its claim answer (`options`). The planner bridge reads them from
`orchestration.options` of the plan, the phase and the item, and from orchestration overlay documents (see the
bridge README) for plan engines that do not know the field yet.

## Visibility

Every event is one progress line (`conductor/v1` `progress-line`): `run.start|resume|end`, `item.start|end`,
`stage.start|end|skip`, `info`. stderr gets a readable line by default (time, item, step, role and route, what
happened, verdict, duration, tokens, stop code), the JSON line with `--json-lines`, nothing with `--quiet`. The journal
`progress.jsonl` always gets the JSON line. Every role is told to print the same kind of line
(`[orch] <item> <step> <what>`, no time: a role cannot know it; the time of a line is the receive stamp in the `<step>.jsonl.times` file next to the stream) into its own stream. `orch conduct status` summarises the journal: run status,
the step running now, the last step and outcome of each piece, the tokens and the agent runs of the current piece
(`status --json` has them as `agents: [{agent_run_id, role, step, status, tokens}]`).

### Agent runs

Every start of a model role (executor, reviewer, scout, triager, registrar, and the report-fixer that mends a result) is an agent
run with the id `agent-<run suffix>-<n>` (`n` from `state.agents`, kept across a resume) and the folder
`<run>/<item>/agents/<agent_run_id>/`: `request.json` (`role`, `route`, `step`, `attempt`, `prompt` and `causation`, `started_at`;
`parent_agent_run_id` for the report-fixer, which names the role it mended), `result.json` (`exit`, `error` — an `error/v1`
document when the failure was classified, else the code of the stop —, `decisions` of `retry.decide`, `duration_s`, `stream`,
`lingered`; written however the run ends) and `usage.json` (`input`, `cached`, `output` of all its attempts, the report-fixer
apart from the role it mended). The prompts and the streams stay in `prompts/` and `streams/`; the folder points at them. A
folder without `result.json` is a role still running or one that died with the process. The `stage.end` lines and the
`STAGE_SLOW`/`STAGE_IDLE` beacons carry the optional field `agent`; the observer report lists the tokens by agent run.

### Stubs: additional instructions of the roles

A person keeps additional instructions for a role in Markdown files, by machine and by project, without touching the
canonical role text (`roles/*.md`, digest-checked) or anything a role may do. `orch stubs publish [--scope project|machine]`
creates the empty files (never overwriting one): `<project>/.swissknifeman/stubs/` (the project layer; `projects/<code>/local/stubs/` of the workspace when the project marker names one; in the
swissknifeman checkout itself this is the place to publish them) or `~/.config/swissknifeman/stubs/` (the machine layer).
A target `orch.role.<role>` (context-scout, executor, reviewer, triager, researcher, advisor; not the registrar and the
report-fixer, whose one-command steps extra text would only blur) is fed by four slots, joined from the general to the
specific: `_all.md`, `orch/_all.md`, `orch/roles/_all.md`, `orch/roles/<role>.md`. In each slot the project file decides by
the mode of its header `<!-- skm-stub:v1 target=… mode=replace|append|disable -->`: an empty file (or comments only)
inherits the machine one, so the published empty files mask nothing; `replace` (default) takes the project text instead,
`append` after the machine text, `disable` drops the slot. Text is literal: no includes, no variables.

A run resolves every target once, when it starts: the text and the provenance of each part (layer, slot, path, sha256)
go to `<run>/instructions.json`, the digest to `run.json` (`instructions_digest`). Every prompt of the run and of its
resumes reads that snapshot; a resume whose files changed says `STUBS_CHANGED`. The block `stub` (budget class
`supporting`) stands after the role text and before the task, under a heading that says it cannot change tools, write
authority, scope, checks or the result contract; the real limits stay the launch catalog, the sandbox, the filesystem guard
and the result parser. A stub that cannot be used (symlink, not a regular file, writable by every user, over 32 KiB, over 64 KiB for one
target, text that looks like a secret, not UTF-8, unknown header field, mode or version, a header that names another target, text in a `disable` file) stops the
run with `STUBS_INVALID` before any role starts. `[orch.stubs]` (machine, invocation or flags only): `enabled` (true) and
`layers` (`["machine", "project"]`; leave `project` out on a machine that runs repositories it does not trust).
`orch stubs list` shows the effective stubs of every role, `orch stubs show ROLE` the block and where each part comes from.

### Prompt manifest

A prompt is built from blocks `Block(kind, origin, text)` (`conductor/prompts.py`); `render(blocks)` joins their texts into
the prompt byte for byte (a separator belongs to the block it follows). Every model role step writes
`<item>/prompts/<step>.manifest.json` (`prompt-manifest/v1`) beside `<step>.md`: `step`, `role`, `route` (`provider`,
`model`, `effort`), `blocks` (`kind`, `origin`, `sha256`, `tokens` estimated by `aicore.content.budget`, `id` for a skill),
`excluded` (`id`, `reason`: the skills the checks of P9.2 left out, see Skill checks), `estimated_tokens` and `prompt_sha256` of the whole prompt.
The `tokens` of the blocks add up to `estimated_tokens` within one token per block. Kinds: `role_text`, `input`,
`repository_rules`, `skill`, `skill_names`, `context_map`, `expected_paths`, `verification`, `run_rules`, `answers`,
`correction`, `progress`, `result_contract`, `research` (the result of the research stage, see [Research](research.md)), and for the roles that review, triage and close: `candidate`, `review_scope`,
`diff`, `findings`, `instruction`. `origin` is the role file, `input.json`, `questions.json`, `skill:<id>`,
`scout-cache:<rel>` or `conductor`.

The optional `budgets` of the manifest measures the prompt by class of blocks: `{core, supporting, retrieval}`, each `{tokens, limit}`
(the sum of the estimated tokens of its blocks against `limits.prompt_core_tokens`, `prompt_supporting_tokens` or
`prompt_retrieval_tokens`; 0 is no limit). **core**: `role_text`, `input`, `verification`, `result_contract`, `answers`, `correction`
and the frame of the review, triage and closing roles (`progress`, `candidate`, `review_scope`, `diff`, `findings`, `instruction`);
**supporting**: `repository_rules`, `skill`, `skill_names`, `context_map`, `expected_paths`, `focus`, `run_rules`; **retrieval**:
`research`. A class past its limit is a beacon `BUDGET_OVER` with `message`
`block <kind> <origin> <tokens>` for its heaviest block. This is a measure and a beacon only: the prompt is never cut, and the limits are for tuning from the data
(observer: Prompt budgets).

### Review focus

The reviewer prompt gets a block `focus` (`origin` `stage-report`, `risk.json` or `stage-report+risk.json`; budget class
supporting) after `candidate` when there is something to say: the `review_recommendation.focus` lines of the executor
rounds (in order, without repeats) and the features of `risk.json` (`risk <feature> (+<weight>): <evidence>`; the score
exists only for a piece whose policy has no review, see Dynamic review). It lists what to look at first and says the
review is not narrowed; without a source there is no block, and the prompt is the one it was. The manifest of `review.N`
lists the block. `suggested_model_class` of the executor raises the class of the reviewer route (the highest class
suggested by any round) when it is above the class of the route and `_admit` takes the higher route of the same provider
(command, transport, sandbox, gate): the beacon `ROUTE_UPGRADED`, `routes.json` and `state.route_overrides.reviewer` (a
resume starts from it) change. A suggestion at or below the route changes nothing: the class is never lowered; a refused
upgrade is an `info` line once and the review goes on with its route.

### Skill checks

Before the prompt of a role is built, the skills of the role (`skills` of the run options, or what `["auto"]` chose) are
checked deterministically, from what each skill declares in the `selection.json` beside its `SKILL.md` and from the tools of
the route (`--tools` of its argv; a route that names no list is not judged by tools, `--tools ""` is a role with no tools).
Nothing in the text of a skill is read for meaning, and no text is cut (the old cut at 12000 characters is gone). A skill is
left out of the prompt, in this order of checks, as:

| Reason | When |
|---|---|
| `duplicated_by_role_contract` | `replaced_by` points at a role contract (a path under `roles/`) or a schema (under `schemas/` or `*.schema.json`); a script or a hook does not replace the text |
| `interactive_in_headless` | `requires_tools` has `AskUserQuestion`: every conductor role runs headless |
| `tool_missing` | a tool of `requires_tools` is not among the `--tools` of the route |
| `over_budget` | the text is above `max_tokens` of the sidecar or above `limits.skill_tokens_max` (only for an isolated role, which gets the text in its prompt; the size is estimated by `aicore.content.budget`) |
| `persona_duplicate` | a second skill of `kind: persona` |
| `exclusive_group` | more skills of one `exclusive_group` than the group allows (one; `php-architecture` two) |

Each exclusion is listed in `manifest.excluded` of the step (`id`, `reason`) and is a beacon `SKILL_EXCLUDED` with the detail
(for example the missing tool or the size). A skill left out is not named in the prompt either. If two kept skills are a pair
of `conflicts` (by id, by name, or by the folder of a `<bucket>/<folder>` entry), the role does not start: the piece stops
`PROMPT_CONFLICT` with the pair. The verdict is made once per piece and kept in the state (`skills_checked`). Contradictions
between the texts of skills ("must" against "never") are not detected: that cannot be done deterministically.

`orch conduct prompt explain --item REF --step STEP [--run RUN] [--json]` prints the blocks of one step as a table (kind,
origin, tokens, the start of the digest) and what was left out; the default run is the latest. `MANIFEST_UNKNOWN` (exit 1)
means the step wrote none, `RUN_UNKNOWN` that there is no such run. The observer lists the five heaviest blocks by role.

## Files: what is committed

| Path | Git | Content |
| --- | --- | --- |
| `.swissknifeman/state/orch/conductor/<run>/` (`projects/<code>/local/state/orch/conductor/<run>/` of the workspace when the project marker names one) | ignored | `run.json`, `state.json`, `progress.jsonl`; per piece `input.json`, `options.json`, `routes.json`, `prompts/` (`<step>.md` and `<step>.manifest.json`), `streams/` (raw role streams with token logs), `agents/<agent_run_id>/`, `reports/`, `checks/<n>/V#.log`, `register-report.json`; after a `resume --retry` `attempts/<n>/` holds the streams, reports, prompts and checks of the steps that retry repeated, and `state.json` the record `items.<ref>.attempts[]` (`n`, `retried_at`, per step `verdict`, `role`, `route`, `ended`, `report_status`, `files`); the observer report lists them under "Retried pieces" |
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
- `orch conduct run --dry-run` also prints `sandbox: {available, reason}`, `network: {role: {declared, enforced, by}}` with `by` one
  of `claude-sandbox`, `codex-sandbox`, `claude-tools` (a Claude role without Bash has no command to confine) or `null`, and
  `warnings` for every role that declares `network: none` while nothing enforces it (the grok `reviewer`; every Claude role
  when the sandbox is off or cannot start).

## The runs of a project: `conduct runs`

`orch conduct runs [--limit N] [--json]` lists the conductor runs of the project, newest first (by the first line of
the journal, then by run id), reading only the run folders (`run.json`, `progress.jsonl`). It is additive: no existing
command and no contract changes. `--json` prints one object:

```json
{"runs": [{"run_id": "cnd-...", "status": "running|finished|blocked|...", "reason_code": null,
           "created": "2026-10-17T09:00:00Z", "items": ["P1.1"], "resumes": 0}]}
```

`status` and `reason_code` are those of `conduct status` (from the journal), `created` is the time of the first journal
line (`null` before any line), `items` are the pieces of work seen in the journal (else those of `run.json`), `resumes`
counts the `run.resume` lines. A project without runs gives `{"runs": []}`; a run whose `run.json` cannot be read is
`{"run_id": "cnd-...", "status": "unreadable"}` and never an error. `--limit` is at least 1. Without `--json` one line
per run is printed. Exit 0; the project is required as for every other `conduct` verb.

### Removing old runs: `conduct prune`

`orch conduct prune --older-than DAYS [--dry-run] [--apply] [--json]` removes what runs that ended more than `DAYS` days ago
(`DAYS` at least 1; counted from the last journal line, else the folder time) left behind: the run state folder, the observer
reports `.swissknifeman/orch/reports/<run id>` and the fallback artifacts `.swissknifeman/orch-artifacts/<run id>`. It is a
dry run unless `--apply` is given (`--dry-run` says so explicitly; both together are refused), so by default it lists
`{run_id, status, age_days, paths, removed}` per run and removes nothing. The latest run (the default of `conduct status`), a
run that is running, and a run whose `run.json` cannot be read are never listed. Not touched: an `artifacts_dir` that a work
source names itself, and the aicore event journal (its compaction changes delivery offsets and is the owner's decision). The
fallback artifacts are committed records: after `--apply` the removal shows in `git status` and is committed by the owner.

## Observer

The observer only reads: the journal and state of the run and the `orch.run.*` and `planner.*` events of the
project's aicore event journal since the run started. At the end of every run (also a stopped one) the conductor
writes `observer.json` and `observer.md`: repeats and resumes, red checks per check id, review findings by severity,
triage confirmed and rejected, idle time between stages, seconds and tokens by role, scout cache hits, the heaviest prompt blocks by role and the prompt budget classes against their limits (`prompt_budgets_by_role`: largest tokens of a step, limit, steps, steps over; from the prompt manifests), the outcome of
each piece and proposals to improve the run options. `orch conduct observe --follow` prints the notable lines of a run
that is still going from another terminal; `orch conduct observe` writes the report again.

### Debug mode

`[orch] debug` (default `false`) is set per machine (`~/.config/swissknifeman/config.toml`), per project
(`<project>/.swissknifeman/config.toml`, wins over the machine) or for one run with `run`/`resume --debug` or
`--no-debug` (wins over both; `SKM_ORCH_DEBUG` and `--config` sit in between). With it on, the run prints the beacon
`DEBUG_MODE` after `run.start` and after every resume: the layer that switched it on, the observer protocol
(`dev-skills/orch-debug/SKILL.md`) and the folder `<run>/debug/` with `journal.md`, `metrics.md` and `findings.md`
skeletons (created once; a resume keeps what the observer wrote). `run.json` records `debug`. The roles, their
prompts and the decisions of the conductor do not change: the mode tells the agent who watches the run to work as a
team-lead observer and where to keep its record.

## Configuration

The `report-fixer` role runs on the conductor's provider by default (an economy model: Claude Code haiku, codex luna, grok);
a `stages` entry `{"role": "report-fixer", "provider": …, "model_class": …}` moves it, and `limits.repairs: 0` turns it off.

`[orch.conductor]` (`configs/config.schema.json`): `provider` (default `claude-code`), `reviewer`
(`grok/grok-4.7/high`), `registrar` (`orch/conductor`), `rules`, `on_blocked`, `questions` (`queue` default, `deny`, `defaults`, `advisor`), `risk` (weights, patterns and `diff_lines` of the dynamic review), `limits.tokens_max`,
`limits.stage_timeout_s`, `limits.check_timeout_s`, and `argv.<role>`: the command line of a role instead of the
launch catalog entry (`{model}`, `{effort}`, `{cwd}`, `{orch}` are filled in). `argv` is machine-wide: a project file
cannot set it. The tests use it to put fake providers in place of the real CLIs.

Grok in the conductor is the `reviewer` and the `report-fixer` only: its `executor` and `bounded-implementer` launch entries use the
`acp` transport, which the conductor does not drive. `orch conduct run --dry-run` shows such a route as `available: false` with
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
