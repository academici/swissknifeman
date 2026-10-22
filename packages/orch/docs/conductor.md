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
orch conduct [--config FILE] resume --run RUN [--retry ITEM ...] [--raise-limit KEY=N ...] [--frozen] [--quiet | --json-lines]
orch conduct settle --run RUN --item REF --outcome done|done_with_deviations|blocked --reason TEXT
orch conduct answer --run RUN --item REF --question ID (--option ID | --text TEXT) [--by WHO]
orch conduct questions [--run RUN] [--json]
orch conduct prompt explain [--run RUN] --item REF --step STEP [--json]
orch conduct prompt diff [--run RUN] --item REF --step STEP [--against RUN:ITEM:STEP] [--json]
orch conduct timeline [--run RUN] [--item REF] [--json]
orch conduct status [--run RUN] [--json]
orch conduct observe [--run RUN] [--follow]
orch conduct gates [--json] [--clear [PROVIDER]]
```

`prompt diff` compares two prompt manifests (`prompt explain`): the step against its previous attempt (`executor.2`
against `executor.1`; a first attempt is `PROMPT_BASELINE_MISSING`) or against `--against RUN:ITEM:STEP`. Blocks are
matched by kind and origin (a block without an origin by kind and order); the answer names each block `added`,
`removed`, `changed` (another digest) or `same` with its tokens on both sides, and the token totals; a missing manifest is
`PROMPT_MANIFEST_MISSING`. `timeline` reads `progress.jsonl` and gives every step of a piece as an interval (`start`,
`end`, `duration_s`, `verdict`, `status`: `done`, `stopped`, `interrupted` when the run ended or was resumed while the
step was open (the resumed step is an interval of its own), `open` while it runs, without an end); gui-orch shows it as
its `timeline` view. With `state.json` at hand a `checks.N` interval also carries `checks` (`--json`): one entry per result
row with `id`, `seconds`, `green`, `skipped`, `skip_reason`, `reused` (plus `executed`, `context`, and for a reused row
`reused_from` and `original_seconds`); the text output prints them under the interval, `  - V3 12.4 s green`,
`  - V5 skipped (fail_fast)`, `  - V2 reused (40 s)`.

For an agent that picks its own pieces (ask the source for ready lanes → `run --items` → `status`/`observe` → `resume`/`settle`) see [agent-mode.md](agent-mode.md).

Exit codes: 0 the run finished, 1 it stopped (or a command was refused; `CODE: message` on stderr), 2 usage,
130 interrupted (Ctrl-C, SIGTERM or SIGHUP: the role and check processes of the run are killed with their groups; `resume` continues).

## Ownership of a run

`run` and `resume` hold local exclusive `flock` locks for the entire command: first the checkout lock under
`<runs root>/checkouts/<sha256(realpath(git toplevel))[:16]>.lock`, then `<run>/lease.lock`. Separate worktrees
have independent checkout locks. Ownership starts before reading `run.json` or `state.json` on resume and before
the first state save of a new run. A second conductor is refused with `WORKTREE_BUSY` or `RUN_BUSY`.
`settle` and `release` take the run lease for their updates; a busy run keeps its state unchanged.

`lease.json` shows the owner's pid, host, start time and command; the checkout's adjacent `.json` also names its run.
These are display metadata: only the kernel lock proves ownership. Metadata is removed before unlocking. Lock
files are never deleted, and their descriptors cannot survive exec into a role. Locks are local to one host;
there is no heartbeat or cross-machine ownership protocol.

If the conductor dies while the journal says `running`, `status`, `status --json` and `runs` report
`orphaned` / `RUN_ORPHANED` when a separate lock probe succeeds. The probe writes nothing. Runs without the
`run.json.lease` flag keep their legacy status. Resume first stops surviving process groups of unfinished roles,
using each agent's atomic `process.json` (`pid`, `pgid`, Linux `/proc` `start_ticks`, `started_at`). It checks process
identity before signalling, sends SIGTERM, allows 10 seconds, then sends SIGKILL if needed. No new role starts
while that group remains alive. Each stopped group produces an `info` event `ROLE_ORPHAN_KILLED`.
Unfinished agents whose process died or whose group was stopped receive `result.json` with error code `ORPHANED`
and an `orch.agent.failed` event with class `orphaned`. An existing result is preserved, and resume does not emit
the failure again. A reused pid is never signalled; the old agent is closed as orphaned.

`answer` can update questions while the conductor owns the run. All updates of an item's `questions.json` use
`questions.lock` for their read-modify-write, including merging answers before a conductor save. A lock held for
10 seconds gives `QUESTIONS_LOCKED`. `observe`, `status`, `runs` and prompt explanation do not take run ownership; their
probe opens `lease.lock` read-only, and where it cannot open it at all (a read-only context) the run is not called
orphaned: `status --json` says `lease: {"lock": "unavailable"}`.
`prune --apply` skips busy leases with a reason, rereads eligibility under the lease, then renames an eligible old
terminal or orphaned run to `<runs root>/.pruning-<id>` before removing it. The latest run is retained.

## A piece that rewrites the orchestrator: `--frozen`

A piece that refactors `orch` changes the code of the process that conducts it. `run --frozen` (and `resume --frozen`) takes a snapshot of
the committed state (`git archive HEAD`) of the orchestrator checkout the command was started from (`packages/orch`, `aicore`, `planner`
and `bridges`) under `~/.cache/skm-frozen-runs/run-<time>-<pid>`, starts the same command from it with `--project` naming the project, and
removes the snapshot when the command ends. The install roots (`SKM_ORCH_ROOT`, `AICORE_ROOT`, `PLANNER_ROOT`, `PLANNER_PLAN_PY`) point
into the snapshot, `PYTHONPATH` is dropped, and the check commands of the pieces do not inherit roots outside the project, so they test the
project's own code. The snapshot freezes only the code of the conductor: the options and instructions of the run are its
own records (`options.json`, `instructions.json`) either way, and the work source stays live (the work-source plugin is the
one the configuration registers, and every claim, brief and register asks the plan as it is now). `resume --frozen` takes a
new snapshot of the orchestrator from the current commit: that is how a mechanism fix reaches a run stopped on purpose. Outside a checkout that holds the sources the flag is `FROZEN_UNAVAILABLE`.

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
  `.swissknifeman/orch-artifacts/<run>/<input_id>/`, never in `plans/`: local records, not committed.
- The changes stay in the tree: `commit` is a no-op unless `--commit`; then it commits the changed paths
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
`run.json` also holds `catalog_digests` `{launch, models, capabilities}`: the digests of the effective launch catalog
(with the `[orch.launch]` overlays), the model catalog and the capability records the run started with, computed as the
dry run of a launch plan computes them (`orch.bindings.catalog_digests`); `conduct status --json` shows them. A resume
runs on the catalogs of now and names those that changed with one info `CATALOG_CHANGED` (no stop; `--frozen` keeps the
options and instructions of the run, not its catalogs); a run recorded before the field resumes as before. This records
provenance; it is not full reproducibility (the environment of the roles is not recorded).

## Recovery after a crash

Before work starts, `state.json` saves a `started` step with `started_at`, `role`, `route`,
`base_head` (null outside git), and the claim's `attempt_id` as `attempt`. For `checks.N`,
`dirty_before` is the sorted list of porcelain paths (at most 500); other steps store null.
Successful work replaces it with the existing `done` result shape. A `Stop` saves only
`status: stopped`, `code`, and `ended`; resume repeats that step normally. Result readers
use only `done` records, so an unfinished step never counts as success.

Resume takes ownership, stops orphaned role groups, applies any `--retry` requests, then
reconciles `started` steps before the loop starts. Closed items (`done`, `done_with_deviations`,
`blocked`, or `abandoned`) discard their `started` and `stopped` records without repeating work;
their `done` results stay intact. A retry still requires a blocked item and removes its unfinished
steps before reconciliation. The rule uses the key's prefix before the first dot:

| Step | Recovery (L10) |
| --- | --- |
| `brief`, `prepare` | repeat |
| `scout`, `research.N`, `review.N`, `triage.N`, `advice.N` | repeat the read-only role without an interruption correction |
| `executor.N` | repeat with an interruption note naming `base_head` and up to 200 sorted dirty paths; keep partial changes and the retry count |
| `checks.N` | repeat; compare the current porcelain paths with `dirty_before`, and emit `CHECK_CHANGED_TREE` if they differ; a run that changed the tree is repeated once on it (`checks/<n>-rerun`, `CHECKS_MUTATED` when that changes it again); a command check whose green evidence of this run is there for the same candidate (HEAD and dirty digest), command, directory and fingerprint is not run again (`checks.reuse`) |
| `research-save.N` | repeat the idempotent save for that research number |
| `close`, `register` | recover a successful registration receipt of this attempt; otherwise repeat the idempotent call |
| `commit` | recover a successful commit receipt of this attempt only when its workspace part is complete; otherwise repeat commit |
| any other key | stop with `STAGE_RECOVERY_UNKNOWN`; settle the item, or use `--retry` if it is blocked |

Each decision emits `info` with `reason_code: STAGE_INTERRUPTED`, the item and stage,
and message `repeated`, `repeated with interruption note`, `repeated after tree change`,
or `no recovery rule`. The executor's note is appended once to that step's correction
and cleared after its result is done. Recovery never resets, stashes, or rolls back the
tree. Old state files without started records keep their previous resume behaviour.

Closing receipts live in `journal.run_dir(item.orch_run, project=project)/receipts/`, the work-source run,
not the conductor's item folder. `register.json` closes `register` (or a model registrar's `close`) only for
`recorded` or `no-op` with a matching attempt. `register` keeps `{outcome, gate}`; recovered `close` keeps
`{by: closer, answer: ...}`, as required by the subsequent registration step. `ATTEMPT_CONFLICT` on a repeat
stops with `REGISTER_REFUSED` and leaves the step unfinished.
An ad-hoc item retried after `blocked` may register a new outcome under the same attempt; a different outcome
after `done` remains `ATTEMPT_CONFLICT`.
Malformed fields used by the recovered result also require a repeat; recovery checks them against the live
work-source response contract before recording `done`.

Before a closing source call, `register-request.json` or `commit-request.json` durably records `attempt_id`,
the request parameters and their canonical JSON SHA-256 digest. After the call, the request also records the
SHA-256 of the unmodified response before the receipt is published. Recovery requires both digests and the
request's run, reference and attempt to match, including responses with an explicit `attempt`. The request's
mtime must be at least the step's `started_at` and the saved state's publication time. The latter conservatively
fences retries within the same second; a later state save can require an idempotent repeat. Thus a crash before
the new source request is written cannot reuse a prior blocked-registration receipt. A new request also clears
the old response digest. Commit responses may include the optional
work-source/v1 `attempt` field.

`commit.json` closes only for `committed` or `no-op` and this attempt. For a plan in the workspace,
`workspace_commit.status` must be `committed`, `no-op`, `skipped-legacy`, or `skipped-no-git`.
`nothing`, `failed`, `locked`, or missing workspace completion repeat commit; a live response with an incomplete
workspace part stops with `COMMIT_REFUSED` for resume. Repeating after the source commit completes the workspace
part without a second source commit. The durable commit request retains the source SHA for this attempt across
repeats. If the repeated answer names only a workspace commit, the step still returns the source SHA for
handoffs and group review. Without a known source SHA, `sha` is null and `message` names the workspace commit.
The result remains `{outcome, sha[, message]}`. Git history is never proof
that a step completed.

Each closing recovery emits `info` reason `STAGE_INTERRUPTED` with exactly one of `closed from receipt`,
`repeated: receipt missing`, `repeated: receipt refused`, `repeated: receipt of another attempt`, or
`repeated: workspace part incomplete`. These info reasons are not Stops or Beacons. Leases, receipts and
reconciliation provide local durability on one host; they do not provide Engine Port workflow replay,
durable timers, signals, compensation, multi-day execution or recovery across machines.

## The cycle of one piece of work

Every step has a key and is recorded in `state.json` before it starts and once it closes; the work source is reached only through
`orch.py source …` and the roles only through the launch catalog.

| Step | Who | What |
| --- | --- | --- |
| claim | work source | `source claim` with a submission of this run. `--batch` (default) takes every piece of `--items A B C` in progress at the start (each piece is started under its own run, one after another, and a dependency that is in progress counts as met: `source claim --batch`, for the planner `start --in-progress-deps`) and the first prompt of the shared session lists them; `--no-batch` claims one at a time; The claim names the executor of `--options` (its provider, model or the model of its class, and its effort; the configured default executor without one), so a route of the work that pins another provider needs no copy in the plan's `orchestration`. `--ready` asks the source for its next ready lane (`lane` of the claim answer) and runs that lane as a batch too, or one piece at a time with `--no-batch`. In a batch a stop gives no piece back on its own: all stay in progress and `resume` goes on (`release` frees one by hand; `--no-batch` gives back a piece nobody worked on, as before). A piece whose executor round began counts as worked on, however the round ended |
| `brief` | work source | `source brief`; the execution-input is read from the artifact store; the base revision is recorded |
| `prepare` | orch | writes `launch-plan.json` for the scenario. The conductor omits stages it skips; public `source prepare` binds the pack as stored |
| `scout` | context-scout (economy) | when the pack has a scout or condense stage; the result is a cached context map; its optional closing ```` ```json write-set ```` block (`scout-write-set`: `paths`, `tests`) is taken out of the map into the executor's "Expected paths" section, a missing or invalid block is ignored with a `RESULT_HEALED` beacon, and the hint never widens `scope.write_set`. The cache key ignores `provenance`, `digest`, the `input_id` digest suffix and `lessons[].ts` (a timestamp, not scope, an instruction or a dependency). A change of goal, scope, reads, route, role text or a selected skill misses |
| `research.N`, `research-save.N` | researcher, work source | with `orch.research.policy = required` (every piece) or `conditional`, the default (a piece whose input says `research.need = required`); `off` never (see [Research](research.md)): the researcher (`implementation`, read-only, network allowed) asks the allowed sources of `[orch.research.sources]` with the one command `python3 …/orch.py research query` and returns a closed `research-result` (`query`, `claims` each with `sources`, `contradictions`, `unknowns`, `sources_used`; a statement without a source belongs to `unknowns`); `research-save.N` then has the work source keep it (`source research`: a plan keeps `research/<item>-<n>.json` and declares it as an input of the item, a file input keeps `research-<n>.json` in its artifacts) and, when the source cannot, the conductor keeps it in the artifacts of the piece and prints `RESEARCH_NOT_SAVED`; no source configured stops the run with `RESEARCH_NO_SOURCES` before any work |
| `executor.N` | executor | the execution-input, the context map, the run rules, the repository rules of an isolated role and, for a correction, its package; returns a closed `stage-report`; the conductor then reads the changed paths from git |
| `checks.N` | deterministic | every `acceptance`/`impact` command check of the cadences asked for, with a check-evidence file per check; the item checks run cheapest first (the red ones of the round before ahead, then by their time in earlier rounds), `checks.parallel` at a time, and with `checks.fail_fast` none starts after a red one (`skipped`, `skip_reason` `fail_fast`); the `phase` checks run only when every item check is green (else `skipped`, `skip_reason` `phase_after_red`); a green check with the same candidate is reused (`reused`, no new run) |
| `review.N` | reviewer (default `grok/grok-4.7/high`) | read-only, the diff against the base and the check results; returns `review-findings` |
| `triage.N` | triager | reproduces every finding; returns `triage-result` (confirmed with a correction package, or rejected with a reason) |
| `advice.N`, `triage.N-a` | advisor (`frontier`), triager | with `orch.advisor.enabled`: one opinion on a problem the work cannot solve alone, returned as `advice` (see [The advisor](#the-advisor-p104)); `triage.N-a` is the triage of review round N repeated with the advice, which then stands for the round |
| `close` | registrar (economy) | only when a layer of the options names the registrar in `stages`: a model runs the one `source register` command the conductor built (the launch catalog allows it exactly `python3 *orch.py source register *`) and answers with its output; it never sees the task |
| `register` | work source | `source register` with the report, the status and the evidence; a repeat is a no-op, so after a closer it only confirms the record, and when the closer failed it records the result and `close` says `conductor` and why |
| `commit` | work source | `source commit` with the changed paths and the artifact folder, when the pack's `git_action` is `commit` |

Red checks get `limits.check_fixes` corrections; confirmed findings `limits.corrections` corrections within
`limits.review_rounds` rounds (2 rounds and 1 correction by default, as in the `full` pack). `check_fixes` and
`corrections` are **targets**: past one, a further round runs while the last correction made progress (the set of red
checks changed or fewer failures show; fewer findings to correct, not other ones), up to `limits.ceiling_factor` times
the target (2 by default). Every round past a target prints a `LIMIT_OVER` beacon and leaves a plan note.
`review_rounds` is a **wall** (D24): a review is the safety net of finished work, not a loop. The findings of the last
round are corrected once without another review (`review.final_correction`, default true), the acceptance checks of
that correction still run, and the piece carries `review_debt` with a `REVIEW_DEBT` beacon that the observer report
lists for the look after the plan. A final correction that changes no product file leaves the findings open as plan notes (`review_debt.corrected: false`) instead of calling them corrected; a spent run-wide budget (`review_rounds_batch`, `findings_batch`, `corrections_batch`) still wins over the wall. A correction that changed nothing, or a ceiling, registers the piece `blocked` with
an escalation (`CHECKS_RED`, `REVIEW_LIMIT` when `final_correction` is false). A finding that
did not reproduce is never a reason for a correction; a confirmed review finding corrected together with red checks is
sent to the executor once, in that one round.

The reviewer of a piece comes from, strongest first: an explicit `reviewer` of the run (a layer that sets it: the
configuration `[orch.conductor] reviewer`, a work-source layer such as the plan's `orchestration.options.reviewer`,
`--options`); else the `review_route` of the execution-input (the plan item's `review.reviewer`), which completes the
default reviewer when it is partial (only a class or an effort keeps the default provider; another provider or a class
lets the model catalog pick the model); else the default `grok/grok-4.7/high`. The shipped default is no explicit choice:
`run --dry-run` shows its source as `default`. `route explain` and `review-verdict.json` (`reviewer_source`) name
`plan:review.reviewer` when the plan chose. `review_rounds_max` of the input lowers `limits.review_rounds` of the piece
(never raises it; `options.json` names the source `plan:review.rounds_max`) and is a wall: no round goes past it on
progress. `review_mode: requested` does not turn on a review the run policy does not have: the policy decides, and the
piece gets one info `REVIEW_REQUESTED_POLICY_OFF` instead of silence. A group review (`review.strategy` groups/single)
runs on the reviewer of the run when one is set; else on the `review_route` the pieces of the group share, and when they
differ on the one of the strongest class (`CLASS_RANK`), announced by `GROUP_REVIEW_ROUTE_CONFLICT` with every piece's route.

Review rounds are tiered by severity (`review.correct_min_severity`, default `Major`; `review.pre_final`, default
`true`). Round 1 looks for everything. Only confirmed findings of that severity or higher go to a correction; the
others are not corrected: they travel as `note` issues ("deferred minor finding…")
in the registered report, so the cleanup of the phase can fix them together. After a correction the next round is a
pre-final audit (when `review.pre_final` is on): the reviewer is told to report findings of that severity or higher
only. A round with no confirmed finding at the floor ends the review.

The executor sees only its prompt: the execution-input, the context map, `rules` and the correction package. It never
sees the plan or the plan's command line. It runs the tests of what it changed; the conductor runs the acceptance
checks outside the executor's sandbox. With the default `checks.executor_runs_checks: false` the prompt names each check by id
and expectation but carries no command (`withheld`), tells the executor not to start containers or call docker, and says that
a proof its sandbox cannot give is an `open_issues` entry of kind `pending`, not a `blocked` escalation. With `checks.self_check` the prompt adds a *Ready to hand over* section: narrow tests in the repository's test files while working, a negative example for every new rule, and each self-check command once on the final tree before the report; a correction asks for them again. A completion report that does not list every self-check command in `self_check`, or lists a red one without a deviation naming the failure, goes back to the executor once per piece before any acceptance check (`RESULT_INCOMPLETE`, admission saved in `self_check_returned` before the round, so a resume replays it); the second report reaches the checks as it is. The acceptance checks stay the conductor's; under SKM_CHECK_RUN `affected-tests.py` keeps to its own receipts (`conductor.json`, reused across runs; tier all: those of the run), so a green written by a self-check is never acceptance evidence (accident prevention: an open-access role can write the git directory). With `true` the
executor gets the commands and runs them itself. A gap that needs the owner is `blocked` with one `escalation` issue per
missing thing; `done_with_deviations` needs a `deviation` issue. `done_pending_checks` is for work that is complete while
acceptance checks could not run in the executor's environment (a container, the docker socket, `.git`, the network): it needs a
`pending` issue naming them. It is not an escalation and never a registered status: the checks stage runs the checks as after
any `done`, red ones are corrected or block the piece as usual, and when they are green the piece is registered `done` with
the evidence of the checks and one `note` issue instead of the `pending` ones. When the conductor ran no check at all
(every one skipped by `checks.cadence` or `checks.kinds`) nothing proves the work, and the piece is blocked with `CHECKS_NOT_RUN`.
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

**The write set is a fence by module, and runtime artifacts are no product.** Right after an executor round, in this order:
(1) *runtime artifacts*: the new **untracked** files under `scope.runtime_paths` (default `.swissknifeman/orch-artifacts/**`,
`.swissknifeman/orch/**`, `**/tests/evidence/**`; logs and evidence of a run) are moved (`os.replace`) to
`<artifacts of the piece>/stray/<original path>`, said as `RUNTIME_ARTIFACT_RELOCATED` and as a `note` issue, kept in
`state.relocated`, and never counted in `changed_paths` or the commit; the artifact folder of the piece, the plan folder and
the conductor reports are not touched. A **tracked** file under them that the round changed is history and cannot be moved:
the piece is blocked with `OUTSIDE_RUNTIME_ARTIFACT` (restore it from git). (2) *Modules*: the module of a path is
`packages/<id>`, `bridges/<id>` or `hub` (`scripts/`, `configs/`, the rest of the repository root); the modules of the piece
are those its `write_set` patterns name up to the first `*`, `?` or `[` (`packages/orch/**` names `packages/orch`; a module
id that is itself a pattern, `packages/*/x`, names every module of the root; a pattern that starts with a glob names the hub).
`CHANGELOG.md` and `docs/**` are allowed to every piece and make no module of it, and neither does a granted `extra_paths`
directory. A path outside the write set that belongs to another module blocks the piece with `OUTSIDE_MODULE`
(`scope.outside_module: block`, default; `deviation` keeps the paths as a deviation as before; `scope.outside: block` still
stops with the stricter `OUTSIDE_WRITE_SET`). **Checks** that change the tree: the checks run again once on the changed tree
(`checks/<n>-rerun/`, the evidence files are overwritten, so the evidence proves the candidate that is committed); a second
change is `CHECKS_MUTATED`. The product files they changed (`state.checks_changed`) belong to the candidate and are committed like the
executor's, under the same module rule (`OUTSIDE_MODULE`); their ownership is recorded (and merged with the earlier record)
before the rerun starts, so a failed rerun or a retry that finds the formatter idempotent loses none of it. A runtime
artifact (`scope.runtime_paths`) is no product and no mutation: an untracked one is moved to `<artifacts>/stray/` right
after each pass (`state.relocated["checks.<n>"]`, `RUNTIME_ARTIFACT_RELOCATED`), so a log rewritten on every run neither
triggers the rerun nor `CHECKS_MUTATED` and the tree stays clean; a tracked one stops with `OUTSIDE_RUNTIME_ARTIFACT`.
The commit lists the records of the piece's artifact folder file by file (tracked or not ignored); the `stray/` subfolder is
never committed, also when the source names a tracked artifacts folder.

**A result outside its contract** goes through three steps: healing by rule (`heal.py`: one honest reading of a form
mismatch, such as a string exit, a differently spelled status or a GREEN verdict with a Major finding; every mend is
said in a `RESULT_HEALED` line and, for a stage-report, a `note` issue); a repair by the `report-fixer` role (an economy
model that rewrites only the result block from the role's own answer, `limits.repairs` times, default 1;
`RESULT_REPAIRED`); and only then a repeat of the whole role within `limits.retries` per step. A triage that rejects a
Blocker or Major finding without a reproduction that ran is outside the contract.

**A rejection of a Blocker or Major finding stands only when the conductor reran it** (`stages/triage.py`,
`checks.run_reproduction`). The command of the rejection is model text, so it is run read-only
(`ro-run.py --protect <project>`, Landlock; stdin `/dev/null`, ceiling `limits.triage_repro_timeout_s`, default 600 s,
log `<piece folder>/triage/<round>/<finding>.log`), and only after a line with a marker of this very call, printed inside the
guard before the command starts, is in the log. A trivial command (a standalone `true`, `:`, `exit 0`, `echo …`,
`printf …`; `is_trivial_reproduction`) is not run: the finding is confirmed again (`TRIAGE_REPRO_TRIVIAL`). A command with
an unquoted shell operator (`;` `&&` `|` `>`), a substitution or a second line (`echo checking; python3 repro.py`) is not
trivial and goes to the guarded rerun; an operator in quotes or escaped is plain text (`echo '|'`, `printf '%s' '>'` stay
trivial). The line is read as Bash reads it: `#` starts a comment only at the start of a word, so `echo checking#phase;
python3 repro.py` is compound, while `echo ok # note` and `echo '#'` stay trivial. Another exit than the one the triager reported confirms it again
(`TRIAGE_REPRO_MISMATCH`). When the guard cannot be had (Landlock missing or too old, the project in a writable root of
`ro-run.py`, a failed start) or the rerun times out, the rejection cannot be proven and the finding is confirmed again
whatever the exit (`TRIAGE_REPRO_UNVERIFIED`, fail closed). The restored entry carries the command, the observed exit and
`the conductor reran the rejection: <why>`, and the finding goes to the correction as any confirmed one. The result of the step
keeps `verified: [{finding, outcome: kept|restored, reason}]`. Confirmed and Minor findings are not rerun.

Both the heal and the repair keep the meaning of the result or move it toward caution (`domain/semantics.py`). Statuses
rank `done` > `done_with_deviations` > `done_pending_checks` > `blocked`, verdicts `GREEN` > `ATTENTION` > `RED`; neither
step raises one, drops an issue, finding, question or check row, lowers a severity, changes an escalation or a blocker
into another kind, or sets a deviation outcome to `accepted`. So the heal makes a `done_with_deviations` without a
deviation carry a `follow_up` deviation, a `done_pending_checks` without a pending issue carry one (the conductor's
checks then decide: green closes it, none run blocks it with `CHECKS_NOT_RUN`), and an escalation in a report that is not
blocked makes the report `blocked`; a deviation without an outcome is a `follow_up`; a verdict `ATTENTION` or `RED`
without findings is not healed into `GREEN` but goes to the repair and, failing that, to a repeat of the reviewer. The
repair is compared with the heal of the role's own block. A finding is matched by its content, not by its id or severity
(its normalized place and failure scenario; findings with the same content are compared one by one), so a severity moved
from one finding to another at the same place is drift. A deviation is matched by its text, impact and class together (blanks and case ignored): a
deviation accepted that was not accepted before is drift even when the total of accepted deviations stays, also for
deviations of the same (or blank) text that differ in impact or class, and a reworded one counts as new. A deviation with
none of the three is matched only by its place among such ones, so an unclear identity never authorizes an acceptance. A block that raises the status or the verdict, lowers a severity, loses a finding, question, escalation,
pending issue or check row, or turns a confirmed finding of a triage into a rejected one is refused with
`REPAIR_SEMANTIC_DRIFT`; the next repair, then a repeat of the role, follows, and a role that never gives a faithful
block ends in `ROLE_OUTPUT_INVALID`. An answer with no block that parses has nothing to compare: the fixer's block is
taken and the step records `repaired_from_text`.

### Stops

The conductor stops only on:

| Code | When |
| --- | --- |
| `RUN_BUSY`, `WORKTREE_BUSY` | another conductor owns the run or checkout; wait for it or stop it before retrying |
| `QUESTIONS_LOCKED` | the item's questions lock could not be acquired within 10 seconds |
| `CONDUCTOR_CRASHED` | an unexpected exception in the conductor loop; exit 1, stopped state and `run.end`; the redacted traceback is written to `<run>/crash.txt` when that write succeeds. If the artifact cannot be written, the stop still names `CONDUCTOR_CRASHED` and says `crash.txt unavailable` (it does not claim the file exists); fix the cause, then resume |
| `STAGE_RECOVERY_UNKNOWN` | a started step has no recovery rule; settle the item or retry it |
| `REVIEW_LIMIT` | a batch limit refused a round while a confirmed Blocker finding is open | the finding ids and the limit |
| `DEPENDENCY_BLOCKED` | with `on_blocked: report` the run went on after a blocked piece, and a later piece of the run depends on it (`depends_on` of its claim): it is not started, stays in progress and the run ends here after the others; `resume --retry` the blocked piece, then `resume` |
| `DISK_LOW` | less than `limits.disk_min_gb` (default 5) GB free under the project or the temporary directory when the run starts or resumes, or before the checks of a round; the run stops (resumable): free the space, then `resume` |
| `RUN_TIMEOUT` | the active time of the run passed `limits.run_timeout_s` (default 0: off); the current role is cancelled; raise the limit, then resume |
| `TOKEN_BUDGET` | accounted fresh tokens reached `tokens_hard_max` of the piece or `run_tokens_hard_max` of the run, or the step reached the run policy's `budgets.stage_tokens_max`; checked before **every** model call (a repeat, a repair, a fallback route, a group review), so no new call starts; done steps stay saved; resume with `--raise-limit KEY=N` (`stage_tokens_max` is raised in the policy) |
| `TOKEN_BUDGET_UNMETERED` | a model attempt reported no usage while `tokens_hard_max` or `run_tokens_hard_max` is in force and `limits.unmetered` is `stop` (the default): unknown usage is not zero, so no further call starts; set `limits.unmetered` to `charge` in the `--options` file of the run (or the configuration) and resume: each attempt without usage then costs `limits.unmetered_charge_tokens` |
| `BRIEF_TOO_LARGE` | the execution-input of the piece (the embedded context pack and the files it reads included) is larger than `budgets.brief_max_bytes` of the run policy (the `full` pack: 1048576); checked once the options are resolved, before the first role, and again when the input is rebuilt; split the item or raise the budget in the policy |
| `ITEM_BLOCKED` | a piece is blocked and `on_blocked` is `stop` (or it left changes in the tree) |
| `QUESTION_ANSWERED_NOT_RETRIED` | a resume skips a blocked piece with an answer awaiting consumption and no piece starts in this pass; exit 1; use `orch conduct resume --run RUN --retry ITEM` |
| `OUTSIDE_MODULE` | the executor (an escalation of the blocked piece, `ITEM_BLOCKED`) or the checks (the run stops) changed files of another module than the write set names, `CHANGELOG.md`, `docs/**` and the granted `extra_paths` aside; add the paths to the item's `task_files`, or set them aside and retry; `scope.outside_module: deviation` (invocation only) reports them as a deviation instead |
| `OUTSIDE_RUNTIME_ARTIFACT` | the executor (blocked piece) or the checks (the run stops) changed a **tracked** file under `scope.runtime_paths` (`.swissknifeman/orch-artifacts/**`, `tests/evidence/**`, …): runtime artifacts are history, not product; restore the file from git |
| `CHECKS_MUTATED` | the checks changed the tree again when they ran a second time on the tree their first run had changed: they are not idempotent (resumable); make the check change nothing on a tree it has already changed |
| `GROUP_REVIEW_BLOCKER` | the group review of a batch found a **Blocker**; the run stops (resumable) and a resume stops again at once until the group is settled: run the follow-up (`orch conduct run --input <run folder>/group-review-<n>.followup.json --commit`), then `orch conduct settle --run <R> --group <n> --followup-run <F> --reason …` (see "The review strategy of a batch") |
| `GROUP_REVIEW_FAILED` | the group review failed (the role failed or its reply has no readable `## Findings` section) and a piece of the group has `review_mode: requested`, which no other review covers; a resume repeats the review once (two attempts in all); a group without a requested piece only gets the beacon |
| `GROUP_UNKNOWN`, `GROUP_FOLLOWUP_MISMATCH`, `GROUP_FOLLOWUP_NOT_DONE` | refusals of `settle --group`, exit 1, the state of the run is not changed: the run has no such blocked group; the follow-up run did not run `group-review-<n>.followup.json` of this run (or does not exist); it is not finished with its one piece done and committed |
| `ROUTE_UNDERSHOOT` | the executor route is below the class or effort the work requires |
| `SANDBOX_UNAVAILABLE` | `instructions.sandbox` is `require` and a Claude Code role with Bash is on the route, or a Codex route carries `--sandbox`, and the sandbox cannot start (`orch.py doctor`, `orch.sandbox`); the run stops before any work |
| `PROVIDER_UNAVAILABLE`, `TRANSPORT_UNSUPPORTED`, `LAUNCH_UNKNOWN` | a role cannot start: checked for every required role before any work of a piece (an optional scout or report-fixer is skipped instead); a route with `transport: acp` stops with `TRANSPORT_UNSUPPORTED`. Wrapped commands check the provider after `--` as well as the launcher |
| `LAUNCH_REFUSED` | the role/provider pair is explicitly refused in the launch catalog; the message is `<role>/<provider>: <reason>`. Required roles stop before work; optional scout/report-fixer roles are skipped |
| `ROLE_FAILED`, `ROLE_OUTPUT_EMPTY`, `ROLE_OUTPUT_INVALID` | a role kept failing after healing, repair and `limits.retries` |
| `PROVIDER_AUTH`, `PROVIDER_AUTHZ` | the provider refused the credentials or the operation (class `authentication`, `authorization`): never repeated, log in or fix the access, then resume |
| `PROVIDER_QUOTA` | the usage limit is exhausted (class `quota`, `rate_limit`) and the reset is further than `limits.provider_wait_max_s` or unknown, with no admissible `fallback_routes` entry; or the provider of a role is gated on this machine (see Capacity gates). The message names the reset time (UTC) and says `resume after` it |
| `PROVIDER_REFUSED` | the provider refused the request (class `invalid_request`, `content_policy`): a repeat would be refused again |
| `PROVIDER_CONTEXT` | the request does not fit the context window (class `context_limit`); a signal to replan or split the item; the prompt is not rebuilt automatically |
| `MODEL_UNAVAILABLE` | the model is not available to the account (class `model_unavailable`), repeated within `limits.retries` first |
| `TIMEOUT` | a role was silent for `stage_idle_timeout_s` (default 5400: a hang, not a long run), or it ran past its wall: `stage_timeout_s` when set, else `limits.role_timeout_s` of its role (the executor and the bounded-implementer have none by default; see the limits table); then the retry rule of the step applies |
| `WORKTREE_DIRTY` | changes outside the conductor reports before new work (`run --adopt` takes over changes inside the write set of the first piece; `[orch.conductor] foreign_untracked = "keep"` lets untracked files of someone else stay: they are fingerprinted in `state.foreign`, announced as `FOREIGN_KEPT`, and never counted as a piece's work while their content stays the same) |
| `CLAIM_BLOCKED`, `BRIEF_REFUSED`, `PREPARE_REFUSED`, `REGISTER_REFUSED`, `COMMIT_REFUSED`, `WORK_SOURCE_*` | the work source refused or is unavailable |
| `OPTIONS_INVALID`, `POLICY_UNKNOWN`, `MODEL_CATALOG_UNAVAILABLE` | the run options, the pack or the model catalog are unusable |
| `POLICY_STAGE_UNSUPPORTED` | a required stage of the run policy (`required` and `on_unavailable: refuse`) names a role the conductor does not run (`bounded-implementer` in `frontend-bounded`). The run stops before any role of the piece. `run --dry-run` lists the same reason under `unavailable`. Resume after choosing a scenario the conductor runs (`full`, `solo`, `scout-solo`, `review-only`), or run the plan natively |
| `OPTIONS_UNTRUSTED` | a layer of the work source (plan, phase, item, overlay, input file) loosens the isolation set below it: `instructions.sandbox`, `sandbox_domains`, `isolate_roles`, `scope.fence`, `scope.outside`, `scope.outside_module`, `scope.runtime_paths` or `scope.extra_paths` (see "Isolation floor") |
| `OPTIONS_UNSAFE_PATH` | an `extra_paths` entry (`--allow-path`) is the root, a system folder, HOME or an ancestor of it, the project or an ancestor, a secrets folder under HOME, or lies in `.git` (after `~` and symlinks are resolved) |
| `STATE_CORRUPT` | a JSON file of the run folder is not JSON; it names the file |
| `RUN_INVALID`, `STATE_INVALID` | `run.json` or `state.json` does not match its records/v1 schema (see *Run records*) when the run is loaded or saved: `CODE: <path>: <JSON pointer>: <message>` for the first three problems, then `settle or release the items of this run, or start a new run`. A file is never rewritten by a read; a state that would not match is not saved |
| `QUESTIONS_INVALID` | `questions.json` of a piece is not JSON or does not match records/v1 `questions`: the run stops, `orch conduct answer` writes nothing and exits 1, `orch conduct questions` lists the other pieces and exits 1. The file is left as it is, so an answer in it is not lost |
| `RECORD_INVALID` | another run record (`options.json`, `routes.json` of a piece) does not match its records/v1 schema; same message shape. A lease record that does not match only makes its owner `unknown` in a busy message |
| `STUBS_INVALID` | a stub file cannot be used (a symlink, not a regular file, over 32 KiB, not UTF-8, a bad header or mode); the run stops before any role starts and names the file and the `STUB_*` code |

With `on_blocked = "report"` a blocked piece that changed nothing is registered, its records are committed and the
run goes on; a blocked piece with changes stops the run, because its partial work would leak into the next piece.

### Beacons: long and costly runs are reported, not cut

The informational limits report long or costly work through `info` lines with a stable `reason_code`;
`orch conduct status` shows the latest one of the running step. Explicit hard limits are listed under Stops:

| Code | When | What it says |
| --- | --- | --- |
| `RUN_ORPHANED` | status/runs find a journal still running and a free lease for a run marked `lease: true` | the conductor no longer owns the run; resume stops unfinished role groups before continuing |
| `QUESTION_ANSWERED_NOT_RETRIED` | a resume skips a blocked piece with a saved answer (open with a resolution, or legacy answered); other work may still proceed | `answers of ITEM wait: orch conduct resume --run RUN --retry ITEM`; also a Stop when no piece starts |
| `STAGE_SLOW` | every `limits.stage_warn_s` (default 2700) of one role run | how long it runs, its last command and the processes of its session (a test run, a build) |
| `STAGE_IDLE` | every `limits.stage_idle_warn_s` (default 600) without output | the same; `no child process` means the model call itself is silent |
| `CHECK_SLOW` | every `limits.check_warn_s` (default 900) of one check; the time a check spends stopped (`SIGSTOP`, state `T`) is not counted, for the beacon and for `check_timeout_s` | the check id and its processes, each with its age, `ps` state and CPU share (`S` at 0 % is asleep, for example on a stdin nobody writes; `R` or a share of the CPU is at work) |
| `DISK_LOW` | a check runs and the free space went under `limits.disk_min_gb` (every `check_warn_s`; the check is not cut) | the file system and the free space |
| `RUN_SLOW` | every `limits.run_warn_s` (default 7200; 0 off) of the **active** time of the run (segments of its processes: a resume a day later does not count the day) | active time, closed and left pieces, the current step; one plan note per threshold; never stops the run |
| `BUDGET_OVER` | once, when the fresh tokens of a piece pass `limits.tokens_max` | the tokens used |
| `BUDGET_OVER` (`block …`) | a class of the blocks of a role prompt is past its `limits.prompt_*_tokens` (see Prompt manifest) | `block <kind> <origin> <tokens>`: the heaviest block of the class; the prompt is not changed |
| `LIMIT_OVER` | a round past a target of `limits.*` | the target, the ceiling and why it goes on |
| `REVIEW_DEBT` | the last review round the wall allows had confirmed findings; they were corrected without a further review | the round and the findings; `review_debt` in the piece state; the observer lists it for the look after the plan |
| `RESULT_INCOMPLETE` | a completion report without the self-check (`checks.self_check`) goes back to the executor once, before the checks | the commands it did not show |
| `CONCURRENT_RUN` | at run start or resume, another run of the project holds its lease | the live runs and their pids; parallel runs slow each other's checks, nothing is stopped |
| `ANSWER_SCHEMA_IGNORED` | `resume --retry` hands over an answer whose question's `answer_schema` is outside the closed profile of the validator (a keyword such as `format`, or a `$ref` outside the schema), so the answer was not checked | the question and why; `answer_schema_ignored` in its entry; `orch conduct answer` says the same on stderr. An answer an applicable `answer_schema` rejects is `ANSWER_INVALID` and is not written |
| `LIMIT_OVER` (`batch: …`) | a round past `limits.review_rounds_batch`, `corrections_batch` or `findings_batch` (whole run, default 0 = none; same target and ceiling rule, counted from the state of every piece) | the target and why it goes on; when the ceiling refuses more rounds, an open **Blocker** stops the run with `REVIEW_LIMIT`, other confirmed findings become plan notes (no correction) |
| `RESULT_HEALED`, `RESULT_REPAIRED`, `REPAIR_FAILED` | a role result was mended | what was mended |
| `REPAIR_SEMANTIC_DRIFT` | the report-fixer's block changed the meaning of the role's own block (a raised status or verdict, a lowered severity, a lost finding, question, escalation or check row) and was refused | `kept the role's answer: <violations>`; the next repair or a repeat of the role follows |
| `TRIAGE_REPRO_TRIVIAL` | the triager rejected a Blocker or Major finding with a reproduction command that proves nothing (`true`, `:`, `exit 0`, `echo …`, `printf …`); the finding is confirmed again | `<finding>: the command … proves nothing` |
| `TRIAGE_REPRO_MISMATCH` | the conductor reran the reproduction of such a rejection read-only and observed another exit than the one reported; the finding is confirmed again | `<finding>: reported exit <a>, the conductor observed <b>` |
| `TRIAGE_REPRO_UNVERIFIED` | the rerun could not be made read-only (Landlock missing or too old, `ro-run.py` refused or failed before the command started, the project lies in a writable root) or ran past `limits.triage_repro_timeout_s`; the finding is confirmed again whatever the exit (fail closed) | `<finding>: the rerun was not made read-only (<unavailable\|timeout>; log <path>)` |
| `REVIEW_MODE_NONE_SKIPPED` | `review.strategy` named a mode and the plan gives some pieces `review_mode: none`; no group reads them | the pieces left out |
| `GROUP_REVIEW_RESOLVED` | `settle --group` accepted the follow-up run of a group with a Blocker; the next resume goes on | group, follow-up run, its commit and the reason |
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
| `SKILL_PATH_INVALID` | a skill file or its selection sidecar fails path, size, UTF-8, schema or auto-digest checks | role, skill name/id and exclusion reason; the skill is left out whole and listed in the prompt manifest |
| `RULES_PATH_INVALID` | a repository rule carrier fails containment, size or UTF-8 checks | role, carrier and reason; its rules are skipped |
| `CHECK_CHANGED_TREE` | the checks of a round changed files of the project (their evidence and logs aside); the first change only: the checks run once more on the changed tree (a second change is the stop `CHECKS_MUTATED`) | the paths; the checks run again, and the evidence of that run proves the candidate |
| `RUNTIME_ARTIFACT_RELOCATED` | an executor round left new untracked files under `scope.runtime_paths` (logs, evidence); they were moved to `<artifacts of the piece>/stray/` and are not committed | the paths and where each went (the report gets a `note` issue) |
| `QUESTION_OWNER_ONLY` | a blocking question has kind `approval` or `credential`, in any questions mode | question id and kind; it stays open for the owner even with a default or under `deny` |
| `ADVICE_HELD` | advice needs the owner, meets an effective gate or falls below the confidence threshold; also a recommendation outside a question's options | source `advisor` (needs_owner, model category or invalid option), `code` (security/public-api/scope-expansion with paths), or `confidence` (actual and minimum); all applicable gate reasons are named |
| `ISOLATION_PARTIAL` | the provider CLI does not know its isolation flag, or `instructions.sandbox` is `prefer` and the provider sandbox cannot start (once per run) | roles are isolated by the environment only; the commands of Claude Code roles run under the filesystem guard only |
| `POLICY_STAGE_SKIPPED` | a stage of the run policy names a role the conductor does not run, and the stage is not a refusing required stage (once per run). The conductor's preparation binds a copy without that stage, rewriting a dependency on it, so a missing manifest does not become `ROLE_UNKNOWN`. Public `source prepare` and `orch prepare` of the original policy still check every stage | the scenario and the stage; the run continues |

A person who runs the conductor sees them on stderr; an observer agent reads them from the journal and decides whether
the run is healthy (a long test run is) or needs a look. The executor and the bounded-implementer have no wall by default
(`stage_timeout_s` sets one for every role); the auxiliary roles have `limits.role_timeout_s` and a check has
`check_timeout_s` (7200). Silence stops work too: a role whose stream has not grown for `stage_idle_timeout_s` (5400) or a
check whose log has not grown for `check_idle_timeout_s` (3600) is hung; 0 turns either off.

### Provider availability

`aicore.providers.available.<provider>.enabled = false` (machine, `--config` file or flags; the project layer cannot set it,
`CONFIG_LAYER_FORBIDDEN`) switches a provider off for routing, whatever `providers.selection` rolled out into the project. A route
on it is `PROVIDER_DISABLED: aicore.providers.available.<id>.enabled = false (<layer>)`: `run --dry-run` lists it under
`unavailable`, route choice moves the role to the first admissible `fallback_routes` entry (`ROUTE_FALLBACK`), and without one
the preflight stops the run with `PROVIDER_UNAVAILABLE` before any work (an optional scout or report-fixer is skipped). A role
is routable when the provider is enabled, its CLI is found, the transport and sandbox work and no capacity gate is open.

### Route explain

`orch.py route explain --role R [--plan P --item I | --run RUN --item I] [--scenario S] [--json]` shows why a role runs where it does, without
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

`--run RUN --item I` selects exactly that run; an unknown run or item never falls back to the newest run.
The additive `used` object comes only from its `routes.json`, whitelisted to `provider`, `model`, `effort`, `class`
(`null` when no route was recorded). `available_now` holds the current candidate's whitelisted `route`, `available`
and `stop`; current configuration and gates can change it without changing history. Existing `selected` and
`candidates` still describe availability now. Without `--run`, `--plan`/`--item` retains the newest-run lookup.

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
by the decision of `retry.decide`. The claim tells the work source where its actor comes from: `--actor-source options` with the `--actor-field`s the executor stage of `--options` names (provider, model, effort; a provider alone keeps the plan's model, as the stage merge does) and `--actor-class` for a class named without a model (the source resolves its model on the provider of the merged actor), else `default`. An explicit executor of the run wins over the executor a plan pins, as it does at execution; the source answers a replaced plan value as `actor_override`, which the run prints as info `ACTOR_OVERRIDE` and keeps in `state.claims` and the `run.json` of the source run (a repeated claim of a closed piece, as a group review makes, keeps the record). `run --dry-run` shows what a run would do (`claim_actor`: the actor a real run hands to `source claim --actor`, with a warning when it is not the routed executor, since the source refuses a piece whose route pins another one; `batch`: whether the pieces are one batch, the default for several; `ready`: whether `--ready` picks them): `fallback_routes`, the `gates` in force, the
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
- `approval` and `credential` questions always stay open for the owner in all four modes
  (`QUESTION_OWNER_ONLY`); neither a default nor advisor advice answers them, and `deny` does not close them.
- The question is saved in `state.questions[<item>]` and in `<run>/<item>/questions.json` with its binding
  `{run, item, step, input_digest, input_part_digest}` (the full input digest and `contracts.required_digest` of its
  substantive part), its `status` (`open`, `answered`, `applied`,
  `assumed`, `denied`, `stale`) and, once answered, `resolution {value, by, at}`. Beacons: `QUESTION_QUEUED`,
  `QUESTION_DENIED`, `QUESTION_DEFAULT`, `QUESTION_ANSWERED`, `QUESTION_OPEN` (retry without an answer), `QUESTION_STALE`.
  Every automatic resolution adds `authority {mode, gate, code_categories, confidence}`: mode `defaults` or `advisor`,
  the effective gate and code categories at the decision, and the advisor's confidence (`null` for defaults).
- `orch conduct answer` writes only the resolution into `questions.json`, under `questions.lock` of the item (both in
  the item folder of the run); `QUESTION_UNKNOWN` (`<item> has no questions in run <id>`, refused before anything is
  written, so a mistyped `--item` leaves no folder), `QUESTION_NOT_OPEN`, `ANSWER_INVALID` (a decision takes one of its
  options, a clarification may take `--text`); it never touches the run.
  `orch conduct questions [--run R] [--json]` lists the open ones with their age; one older than `limits.question_warn_s`
  (default 1800, 0 off) is `OVERDUE`, in the observer report too.
- `resume --run R --retry ITEM` merges the answers into the state. New bindings compare `input_part_digest` over
  `goal`, `scope`, `acceptance`, `constraints`, `decisions`, `route`, `result_contract` and `escalation`. Changes to
  provenance, lessons or other context, including the source's blocked registration, preserve the answer.
  Legacy records without that field still compare the full `input_digest`. A changed substantive part produces
  `QUESTION_STALE`: the answer is kept as `stale_resolution`, the question gets
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

The human gate: `[orch.advisor] human_gate` (default `security`, `destructive`, `public-api`, `scope-expansion`)
can be set only by defaults, the machine or the caller (invocation and flags). A project or environment attempt is
`CONFIG_LAYER_FORBIDDEN`; projects can add categories through `human_gate_extra`. Extra gates accumulate from every
layer's history: neither `[]` nor `_unset` removes a lower layer's category. `min_confidence` defaults to `medium`;
the strictest value across all layers wins (`high` > `medium` > `low`), including defaults and values before `_unset`.

Advice is held if `needs_owner: true`, its model category belongs to the effective gate, a category computed by code
belongs to the gate, or its confidence is below the effective minimum. Code examines changed paths **and** the write set
using `conductor.risk.patterns`: `security` for `security` patterns, `public-api` for `public_cli` or `schema` patterns,
and `scope-expansion` for changes outside the write set. For code categories, builtin patterns and patterns established
by trusted machine, invocation or flag history form a retained floor; effective project/environment patterns may add
matches. Empty arrays, replacement arrays and leaf/parent `_unset` cannot erase that floor. Heuristic risk scoring
still uses the effective configurable patterns, weights and critical features; the retained floor applies only to
code categories and their owner hold. Existing human-gate, confidence, needs-owner and scope-expansion gates still apply.
Risk weights do not disable these gates. A model's `other`
category cannot hide a security path. `ADVICE_HELD` names the source (`advisor`, `code` with matching paths, or
`confidence` with actual and required levels). It is handled as `queue`: the piece is
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

Without `--retry`, a blocked piece's saved answer stays pending. The conductor emits
`QUESTION_ANSWERED_NOT_RETRIED` with the retry command; if no piece starts during that pass it stops with the same
code and exit 1. If other work starts, the message is only a beacon. `orch conduct answer` leaves the question
`open` with a `resolution` on disk; resume with retry merges and consumes it (`answered` records are also recognized).

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

The run names itself to the check: `SKM_CHECK_RUN` (the run id), `SKM_CHECK_ITEM` (the piece reference) and `SKM_CHECK_ROUND`
(the number of the round), so a test runner can keep a result only inside one run. `SKM_TEST_JOBS` is the jobs budget the
check may use: the budget of the owner (its own `SKM_TEST_JOBS`, else the CPUs) divided by the checks that run together
(`checks.parallel`, never more of them than the budget), never more than the owner gave; `jobs.txt` in the folder of the round's logs
reports the requested budget, how many checks run together and the share of each. The orchestrator names no script of a
project: whatever the check runs reads these variables.

A green check is kept for the next round of the same run only when its evidence file carries a fingerprint of everything it
read: the candidate, the check as written and its directory, the environment (values are hashed, never stored), the programs
(path, size, time) and the data files (content: fixtures, configuration) that its command line (quoted names with spaces
included) or an environment value names and the candidate does not carry, that is files outside the project and git-ignored
files inside it. The shell expansions of the line are followed as bash would expand them in the directory of the check with
the environment of the check: unquoted globs (`*`, `?`, `[...]`, `**`, also in the value of `NAME=...`/`--option=...`, in a
quoted script such as `bash -c '...'` and through a variable that holds one), brace lists and ranges (`{a,b}`, `{1..3}`); every
file they match is an input, so a file that is added, removed or changed misses. When the inputs cannot be established they are
an unknown input and nothing is reused (a miss, never a guess): an existing folder that the line names or that a glob reaches,
wherever it lies (the project root `.`, a tracked, untracked or git-ignored folder of the project, a partner root or a folder
below it, any other folder outside the project; a literal argument, a path in a quoted script, an entry of a `a:b` list, a
variable the line uses, including a `*_ROOT` one), because its listing and the files below it, git-ignored ones included, are
not fingerprinted (`grep -r x data`, `find .`, `ls dir`); a glob or brace word with an unset variable, a path or an argument
built by a command (`$(...)`, backticks), more matches than the limit, a range that cannot be read, a line with unbalanced
quotes or brackets, a name built from an unset variable or a file that cannot be read. The same holds for the forms the shell
does not expand itself: a `case` whose branch pattern spells a path, a glob or a variable; a `PATH`-like `a:b` list of
patterns; a quoted pattern that holds a glob character with an existing folder in front of it (`'/dir/*.txt'`, also a `:` list
of them); and any quoted glob in a line that runs `find`, `fd` or `fdfind` (`-name '*.txt'`). Only the folders of the
evidence and the logs of the checks (output) are exempt. What stays reusable: the working directory itself (implicit
context), a folder that only the environment holds (`HOME`, `TMPDIR`, a variable the line does not use) and a partner root
that only the environment points to (not named by the line), whose state (HEAD and dirty digest) is fingerprinted, and the
files the line names (a literal file, a glob that matches files), whose content is fingerprinted when it is outside the
candidate. The fingerprint covers what the line or the environment names; what a program reads without the line naming it is
opaque to it. The fingerprint also holds the Python of the conductor and the state of the partner roots outside the
project. A damaged evidence file, another run, another candidate or any difference in the fingerprint runs the check again, as
does a check that changed files of the project or the files it reads outside it while it ran, an input that cannot be read, and
every check that starts after an earlier check of the round changed the tree or committed (the candidate, HEAD included, was
taken at the start of the round). A reused row keeps `reused_from` (the evidence it stands for)
and `original_seconds`; the evidence file is not rewritten. When a prior evidence file does not prove the check, the row
carries `reuse_miss`: the component that differs (`candidate.head`, `candidate.dirty_digest`, `command`, `cwd`,
`fingerprint=<short hash>`, `run`, `subject`, `unknown inputs`), never an environment value. A first run, with no
evidence file, has no `reuse_miss`. The folder of the evidence and the logs of the checks is not part of
the candidate.

A correction is built from the latest red acceptance. Both the full executor prompt and the resumed delta say that
this correction is the only current assignment and that earlier correction instructions are historical. The goal, the
scope, the authority and the acceptance contract stay in force. The focus includes a bounded sample of failure headers and
child logs the sampled check log names (`full output:`, `child log:`); the full log path stays the authority. Checks that
were red earlier and green later are listed as historical, not as work. A completion report that changes no product
file and no execution input does not start acceptance again (`CORRECTION_INEFFECTIVE`, not fixed), unless the report
carries evidence of an environment fix (`class` `environment` or `test_env`) or a confirmed nondeterministic failure
(the issue says nondeterministic and names evidence). That proof is accepted once for the same red command checks.
The pre-executor baseline and the exceptional no-diff admission are saved before execution and acceptance respectively, so resume preserves them. Journal-only input changes do not count as a correction.
Conductor runtime paths are not a product change. An unknown git state is not treated as a no-diff.

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

With `auto` the rules decide (`review.strategist: rules`, the default; the strategist is a model call only when `review.strategist: model` names it, one small call on the economy route of the
triager that sees every piece (title, goal, write set, route) and the choice the rules would make, and answers a mode, the groups
(in order, at most four pieces each) and the reviewer's effort). An answer that is not a partition of the batch in order or a
failed call falls back to the rules (`policies/review_strategy.py`), which `rules` uses on its own: neighbours that work on the
same folders are read together, a piece on the foundation or a `frontier` piece is read alone, security wording raises the
effort to `high`. Naming a mode in `review.strategy` skips the strategist. The plan is kept in `state.review_strategy` and
`review-strategy.json` of the run (a resume keeps it) and announced as `REVIEW_STRATEGY` with the effort the group review
will run at (an effort named by `reviewer` wins over the plan's).

In `groups`, `single` and `none` a piece has no review of its own. After the last piece of a group the conductor reads the
commits of the group once (`review_batch`: production code only, the same as `batch-review.py`), with the reviewer of the run
(`reviewer`, grok by default) at the effort of the plan, and keeps the reply in `group-review-<n>.md` of the run folder
(`state.group_reviews`).
The reserved reviewer of a last piece with `review.mode: none|self` does not override the group's requested review routes;
an explicit configuration or invocation reviewer still wins.
The reply must hold a `## Findings` section with `[Blocker|Major|Minor] file:line - defect` lines (a
list marker, a number, bold or backticks around them are read too) or the word `none`. The beacon `GROUP_REVIEW` gives the
counts; a reply that is neither is `GROUP_REVIEW_FAILED` (`format: malformed` in `state.group_reviews`), never a clean review, and
so is a group without a commit. Blocker and Major findings are corrected in a commit of their own: the conductor writes
`group-review-<n>.followup.json` (an execution-input with `provenance: review_followup`, the files the findings name as scope,
and as acceptance the command checks of the reviewed pieces, once each — `cd DIR && CMD` for a check with its own `cwd`, the
`cadence: phase` checks left out — so the correction is tested like the pieces were) and the beacon names the command, `orch conduct run --input <that file> --commit` (the executor corrects them, the conductor
checks and commits; native correction inside the run is not built, because the pieces of the group are already registered and
committed in the work source).

A group review with a **Blocker** does not end in `finished`: the run stops with `GROUP_REVIEW_BLOCKER` (resumable;
`state.group_reviews[n].blocking`), and a resume stops again with the same code until the group is settled. The stop names the way
out: run the follow-up (`orch conduct run --input <run folder>/group-review-<n>.followup.json --commit`; the file is written by
hand at that path when the findings named no file to build one from), then
`orch conduct settle --run <R> --group <n> --followup-run <F> --reason <text>` under the lease of run R. The follow-up run F is
read without a lease and is accepted only when it ran exactly that file of this run (`source.kind: file` and the same path), is
`finished`, its one piece is `done` or `done_with_deviations`, and it committed (`GROUP_UNKNOWN`, `GROUP_FOLLOWUP_MISMATCH`,
`GROUP_FOLLOWUP_NOT_DONE` otherwise, exit 1, nothing changed). `state.group_reviews[n].resolved` then holds
`{followup_run, commit, reason, at}`, the beacon `GROUP_REVIEW_RESOLVED` is printed and the next resume goes on; no run writes into the state
of another. Major findings are not a stop: the follow-up is announced as above.

A group review that fails (the role failed, or the reply has no readable `## Findings`) while a piece of the group has
`review_mode: requested` stops the run with `GROUP_REVIEW_FAILED` (those pieces have no review of their own); a resume repeats the review once
(`state.group_reviews[n].attempts`, at most 2); after the second failure the stop stays: a resume raises `GROUP_REVIEW_FAILED` again
without a third reviewer call and is no waiver, and only a review that reads (a repeated review below the cap) ends it. Without a requested piece it stays a
beacon. An empty production diff or a group without a commit is not repeated and not a stop.

A forced `review.strategy` (`groups`, `single`, `each`) takes no piece whose plan gives it `review_mode: none`: it is in no group,
and `REVIEW_MODE_NONE_SKIPPED` names it.

## Run options

`schemas/conductor/v1/run-options.schema.json`, closed:

| Key | Meaning |
| --- | --- |
| `stages` | `[{role, provider?, model_class?, model?, effort?}]`, roles `context-scout`, `executor`, `bounded-implementer`, `reviewer`, `triager`, `registrar` (naming it turns the closing stage on) |
| `reviewer` | `PROVIDER/MODEL[/CONTEXT][/EFFORT]` |
| `rules` | short rules for the executor |
| `skills` | `[{role, names}]`; `names: ["auto"]` asks the skills bridge (`[orch.conductor] skills_bridge`, a command run as a process with `--select --role R --provider P --project DIR --paths <write set files>`) for the skills of the role from the write set of the piece: the answer (`skills[].name`, `path`, `reason`) is kept in the state of the piece, an isolated role gets the text of the `SKILL.md` at the path the bridge names, beacon `SKILLS_SELECTED`; no bridge stops the piece `SKILLS_BRIDGE_UNAVAILABLE`, a failing one `SKILLS_SELECT_FAILED`; `auto` is not listed with other names |
| `instructions` | `isolate_roles` (default every role; a listed role starts without the project instructions and customizations of its provider: for Claude Code `--safe-mode` plus no `CLAUDE.md`/project memory, which cuts the start-up context from ≈16 K to ≈6 K tokens and drops the plugins, MCP servers, user skills and hooks; grok was probed and does not read the repository `CLAUDE.md`); `module_rules` (default `["module-folders", "module-boundaries", "engineering-invariants"]`: the instruction sections, by the last part of their `## <scope>.<name>` heading, that a role still gets from the CLAUDE.md or AGENTS.md of the root and of every folder on the way to a write-set path, as a short Repository rules block). An isolated role gets the text of its `skills` in the prompt, because its provider loads none by name; `sandbox` (`off` \| `prefer` default \| `require`: the provider sandbox for shell commands, see Sandboxes) and `sandbox_domains` (default `[]`: the domains a sandboxed Claude Code role may reach); `file_tools_rule` (default `true`: a `## File tools` run-rules block in the executor prompt that says to read and change files with Read/Grep/Edit/Write and not with Bash `cat`/`sed`/heredocs, added only when the route offers Read and Edit; measured before the rule: P10.2 81 Bash calls and 1 Edit, a heredoc edit 55–120 s of model time) |
| `session` | `executor`: `handoff` (default), `shared` or `per-item`. `handoff`: each piece of the run starts a fresh Claude Code session and its correction rounds resume it; the prompt of every piece carries the `## Run batch` block that names all pieces and, for each piece already done, a bounded `### Handoff of` (commit, summary, open issues, changed paths from its `register-report.json`) — a later piece does not re-read the transcript of the earlier ones on every turn (measured: a shared session carried 229K→372K tokens of context into the second piece, 18.5M cache-read tokens for one step). The piece of the kept session is `executor_session_item` of the run state. `shared`: the executor of every piece of the run, and of every correction round of a piece, resumes the Claude Code session of the previous executor (`claude -p --resume`), so the later pieces start with what the earlier ones learned, and the prompt of the first one carries a `run_rules` block `## Run batch` that names all pieces; the later ones are told that the session is resumed. Checks, review, register and commit stay per piece. `per-item`: a fresh session per executor step. `--batch` / `--no-batch` of `run` set it (`handoff` / `per-item`), and `--no-batch` also claims the pieces one at a time (layer `invocation:--batch`, above `--options`). Shared executors run without `--no-session-persistence` (the launch catalog sets it; a session that is not saved cannot be resumed), so their sessions stay in the provider's own store. A session that failed is forgotten and a fresh one starts. The session id is kept in `executor_session` of the run state, with `executor_session_item`, `executor_session_task_digest` and `executor_session_answers` (see *Resumed sessions*). Claude Code resumes with `--resume`; a Codex executor resumes its thread through the `resume_argv` of its launch catalog entry (`codex -a never exec resume <thread> --json -c sandbox_mode="…" --model … -`); Grok always starts fresh. |
| `scope` | `outside`: `deviation` (default) or `block`, for paths changed outside `scope.write_set`; `fence`: `project` (default: the executor may change any file of the project, `scope.write_set` is the expected change and a path outside it is reported by the executor as a `deviation`, not a block; the filesystem guard still confines it to the project) or `plan` (the write set is a fence: a path outside it makes the executor stop with `blocked`); `extra_paths`: directories outside the project the executor may also change (absolute or `~/…`; named in its prompt and granted to every writing role: `--rw` on its `ro-run.py` guard, for Claude Code also `--add-dir` and, under the provider sandbox, `sandbox.filesystem.allowWrite`, for Codex `--add-dir`); `outside_module`: `block` (default) or `deviation`, for paths of another module than the write set names (`OUTSIDE_MODULE`); `runtime_paths`: patterns of runtime artifacts that are set aside, never committed (see "The write set is a fence by module"). `--fence` and `--allow-path DIR` (repeatable) set them for one run. `outside: block` with `fence: project` stops the piece at the first path outside the plan. |
| `checks` | `parallel` (1–8, default 2: command checks run together, sharing the jobs budget `SKM_TEST_JOBS`), `fail_fast` (default false: every item check runs, so one round collects every independent failure; true: after a red command check no other check starts, the ones running end and the rest are `skipped` with `skip_reason` `fail_fast`; `phase` checks run only when every item check is green, else `skipped` with `phase_after_red`; the item checks run cheapest first by their time in earlier rounds), `reuse` (default true: a command check with green evidence of this run for the same candidate, command, directory and fingerprint is not run again; its row is `reused`), `overlap_review` (default false: the checks of a round run while the review of that candidate reads it; red checks drop that review and it is repeated), `kinds` (default `["acceptance","impact"]`), `cadence` (default `["item","phase"]`; `["item"]` leaves out the `cadence: phase` checks, the full pass that the planner bridge gives to the item closing a phase), `red_first` (default true: in a correction round the previously red checks run first, and the others only when those are green; false runs the checks in plan order in every round, with no red-first staging; whether the later checks start after a red one is decided by `fail_fast` alone, independently of `red_first`), `executor_runs_checks` (default false: the executor runs only the tests of the code it changed), `self_check` (default empty: a list of the project's cheap commands, e.g. the tests of the touched units and their dependents and lint, that an executor with `executor_runs_checks: false` runs once on its final tree before it reports and lists in `self_check` of its stage-report; the claim proves nothing, the conductor still runs every acceptance check) |
| `review` | `correct_min_severity` (`Blocker`/`Major`/`Minor`/`Nit`, default `Major`), `pre_final` (default `true`), `audit_scope` (`corrected` default: the round after a correction reads only the corrected findings and the diff of the paths changed since the previous review, see *Review of round 2 and later*; `full`: the whole diff every round), `final_correction` (default `true`: when no further round is allowed the findings are corrected without another review, noted in the plan and as `review_debt` of the piece with a `REVIEW_DEBT` beacon, instead of `REVIEW_LIMIT`; `review_rounds` is a wall, `ceiling_factor` does not extend it), `dynamic` (default `true`: a piece whose pack has no review gets one when its risk score reaches the threshold, see Dynamic review), `dynamic_threshold` (0–100, default 60); `strategy` (`auto` default, `each`, `groups`, `single`, `none`: how a batch is reviewed, see *The review strategy of a batch*) and `strategist` (`rules` default, `model`: who chooses it) |
| `limits` | targets `review_rounds` (0–5), `corrections` (0–3), `check_fixes` (0–3) and their `ceiling_factor` (1–5, default 2); `retries` (0–5, per step); `repairs` (0–3, default 1); `provider_wait_max_s` (default 900: the longest wait for a provider limit to reset); hard token limits `tokens_hard_max` (of the piece) and `run_tokens_hard_max` (of the run), 0 off (see Hard token limits and resume), with `unmetered` (`stop` default, or `charge`) and `unmetered_charge_tokens` (50000) for an attempt that reports no usage while one is in force; beacons `tokens_max`, `stage_warn_s` (2700), `stage_idle_warn_s` (600), `check_warn_s` (900); wall-clock ceilings: `role_timeout_s` (a map role → seconds for a streaming role: `context-scout` 900, `triager` 1800, `report-fixer` 600, `registrar` 600, `reviewer` 3600, `advisor` 1800, `researcher` 2700; the `executor` and the `bounded-implementer` have none; a layer names only the walls it changes, 0 removes one; the group review uses the `reviewer` wall), `stage_timeout_s` (0, off; when set it replaces the wall of every role), `check_timeout_s` (7200, 0 off); silence ceilings: `stage_idle_timeout_s` (5400), `check_idle_timeout_s` (3600). Disk: `disk_min_gb` (5, 0 off: a run or the checks of a round do not start with less free space under the project and the temporary directory, `DISK_LOW`), `triage_repro_timeout_s` (600, 0 none: the ceiling in seconds on the read-only rerun of the reproduction of a rejected Blocker or Major finding; past it the finding is confirmed again, `TRIAGE_REPRO_UNVERIFIED`). Run-wide: `run_warn_s` (7200: a beacon when a run is longer) and `run_timeout_s` (0, off: a ceiling for the whole run); batch targets `review_rounds_batch`, `corrections_batch`, `findings_batch` (0, off: the totals of all pieces of a run); `question_warn_s` (1800: a beacon for a question waiting that long); `skill_tokens_max` (5000: the budget of the skills of one role); prompt blocks `prompt_core_tokens` (12000), `prompt_supporting_tokens` (30000) and `prompt_retrieval_tokens` (50000). |
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
`off < prefer < require`, `scope.fence` along `project < plan`, `scope.outside` and `scope.outside_module` along `deviation < block`;
`instructions.sandbox_domains` and `scope.extra_paths` may only repeat or shrink what the layers below allow;
`instructions.isolate_roles` and `scope.runtime_paths` may only grow. A layer that loosens one of them stops the run with `OPTIONS_UNTRUSTED` (the
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

### Hard token limits and resume

`limits.tokens_hard_max` limits accounted fresh input and output tokens of one piece;
`limits.run_tokens_hard_max` limits their total across the whole run, including the strategist and group reviews.
Both are integers ≥ 0, default 0 (unlimited). `tokens_max` remains an informational `BUDGET_OVER` target;
when both it and `tokens_hard_max` are positive, `tokens_max` must not exceed the hard limit (`OPTIONS_INVALID`).

The run cap accepts only machine/project configuration, invocation `--config` and the run's `--options`.
A work-source layer (plan, phase, item or input) that names it, including 0, gets `OPTIONS_INVALID`:
`run_tokens_hard_max is a run limit; set it in the configuration or --options`.
`run.json.limits_run.run_tokens_hard_max` freezes `{value, source, file?}` at start, so later configuration or options
edits cannot replace the run cap. Cache reads do not count toward either limit.

Admission checks run before **every** model call: each model step, each attempt of a role (a repeat after a failure or
a rejected answer, a fallback route, a wait for a provider reset), each report-fixer repair, the strategist and the
group reviewer; and after saving each done step. At `used >= limit` the run stops with `TOKEN_BUDGET`, the piece is
stopped, and done steps stay saved; it is not registered as blocked. Once the boundary of accounted usage is reached, no
new model call starts. One call can still cross the limit: admission never interrupts a running one. The run policy's `budgets.stage_tokens_max` (> 0) is that check on the known fresh tokens of one logical step
(the piece and the step key): every attempt, repair and fallback of that step, kept across an interrupt and a resume,
and separate when two steps overlap (each with its own amount and step label). A new step key starts at zero. Replaying
a receipt replaces that attempt and does not count it twice. The shipped value 0 does not apply. A run saved before this
record resumes a step from the receipts or agent usage that name it, or from zero when they do not. It stops with
`TOKEN_BUDGET` naming the step. Deterministic steps (checks, register, commit) are not model calls and are not checked.

Missing usage (`usage_incomplete`) is not zero. While a hard limit is in force, `limits.unmetered` says what an attempt
without usage does: `stop` (default) stops the piece with `TOKEN_BUDGET_UNMETERED` at the next admission (after the
attempt that reported none); `charge` charges `limits.unmetered_charge_tokens` (default 50000) per attempt as fresh input
tokens of the piece, the run and the step, counted apart in `tokens.charged`, once per attempt even when its receipt is
read again. Under `stop` the unknown usage is kept at run scope (`state.usage_unmetered`: the pieces whose attempt reported
none and that no charge accounted for): with `run_tokens_hard_max` in force it stops every later admission of the run,
whatever piece the attempt belonged to; a piece limit alone consults the piece only. The `BUDGET_UNMETERED` beacon stays. With both hard limits 0 nothing is stopped or charged: the beacon is
all. `unmetered` is not a `--raise-limit` key; to continue a piece stopped with `TOKEN_BUDGET_UNMETERED`, set it to
`charge` in the `--options` file of the run (a resume reads the file again) or in `[orch.conductor.limits]`, then
`resume`. Attempts that already ran under `stop` are not charged afterwards.

```bash
orch conduct resume --run RUN --raise-limit tokens_hard_max=500000
orch conduct resume --run RUN --raise-limit tokens_hard_max=800000 --raise-limit run_tokens_hard_max=2000000
orch conduct resume --run RUN --raise-limit tokens_hard_max=0
```

`--raise-limit KEY=N` is repeatable and accepts only these two keys. N must exceed the effective value;
0 explicitly removes the limit. Raises overlay the options for this run; they do not rewrite the piece's
`options.json` or repeat its done executor. `state.limit_raises[]` records `{key, from, to, at, by: invocation}`, and a
raise of `tokens_hard_max` also names its `item` (the stopped piece) and holds for that piece only, while
`run_tokens_hard_max` is run-wide (an older record without `item` holds for every piece, as it did);
each raise emits `info` reason `LIMIT_RAISED`. Without a raise, a still-exhausted run immediately stops again
before a model call. No `--retry` is needed. `BUDGET_EXHAUSTED` remains a retry code, and a provider context-limit
failure remains `PROVIDER_CONTEXT`, a signal to replan.

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
`lingered`; written however the run ends) and `usage.json` (`input`, `cached`, `output` of all its attempts and
`usage_complete`, the report-fixer apart from the role it mended). The prompts and the streams stay in `prompts/` and `streams/`; the folder points at them. A
folder without `result.json` is a role still running or one that died with the process. The `stage.end` lines and the
`STAGE_SLOW`/`STAGE_IDLE` beacons carry the optional field `agent`; the observer report lists the tokens by agent run.

Usage is normalized by the provider's payload shape. With an integer `cached_input_tokens` (Codex),
`input = max(0, input_tokens - cached_input_tokens)` and `cached = cached_input_tokens`: Codex's input already includes
cache reads. Otherwise (Claude/Grok), `input = input_tokens + cache_creation_input_tokens` and
`cached = cache_read_input_tokens`. `output = output_tokens` in both forms; booleans, negative values and non-integers
are ignored. Fresh tokens are `input + output`; cache reads stay separate. Item and run totals use receipts keyed by
agent id and attempt stream (`state.items[ref].usage_by_agent`), so reading the same receipt again does not add tokens.

Each attempt records `usage_complete`: `true` when its JSONL stream supplied terminal `result`/`turn.completed` usage
with nonzero fresh input or output, `false` when a running JSONL attempt has no terminal usage or reports 0/0, and
`null` for text transport (scout) or a process that never started. Partial assistant-message usage is still counted
after a timeout, cancellation or an exit without a result, but it does not make the attempt complete. An agent's
`usage.json` is `false` if any of its attempts was incomplete, otherwise `true` if measured and `null` if none was
metered. The first incomplete attempt sets `state.items[ref].usage_incomplete = true` and emits one `info` event with
reason code `BUDGET_UNMETERED`: `<ref>: a model attempt reported no usage; token limits cannot see it`.
This flag survives later measured attempts and resume. Text transport alone does not mark the item incomplete.

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
target counted as its common parts with the largest provider and provider--family variant one route can take, text that looks like a secret, not UTF-8, unknown header field, mode or version, a header that names another target, text in a `disable` file) stops the
run with `STUBS_INVALID` before any role starts. `[orch.stubs]` (machine, invocation or flags only): `enabled` (true) and
`layers` (`["machine", "project"]`; leave `project` out on a machine that runs repositories it does not trust).
`orch stubs list` shows the effective stubs of every role and the files of its variants; `orch stubs show ROLE`
shows the common block and where each part comes from.

Provider and model-family variants are extra parts of the same target, supplied by the owner:
`orch/roles/<role>@<provider>.md` and `orch/roles/<role>@<provider>--<family>.md` in either allowed layer.
Provider and family names match `[a-z0-9][a-z0-9.-]*`; a family cannot contain `--`. For example:

```markdown
<!-- skm-stub:v1 target=orch.role.executor@codex--gpt-6-sol mode=append -->
Explain the targeted test results in the stage report.
```

The effective text joins the four common slots once, then the provider parts, then the provider--family parts.
Each variant slot has its own `replace`, `append` and `disable` resolution across machine and project layers.
`orch stubs show executor --provider codex --model gpt-6-sol` prints this effective block and the selected origins;
`--provider codex` alone includes only the common and provider parts. `publish` creates only the four common slots;
create variant files explicitly. Disabling stubs, excluding a layer and the file safety rules apply to variants too.

The actual route selects the variants. A model's family is its exact inventory id, else the first inventory entry
whose pattern fully matches the model, else the model name itself. When the snapshot has variant parts, the first resolution of each `provider/model`
is saved in `instructions.json.variant_resolution` and reused on resume even if the model catalog changes.
Variant parts keep their `variant` and literal `body` in the frozen snapshot; the target's `text` contains only
the common text. Resolved families sit outside the snapshot digest; without variant files the snapshot and its digest
retain their previous format. On provider fallback, including a gate discovered just before launch, the conductor
rebuilds the same `stub` block for the new route and rewrites the attempt's prompt and manifest before calling it.
The heading, block position and authority remain the same.

### Prompt manifest

`conduct prompt explain --step STEP` accepts only `^[a-z][a-z0-9-]*(\.[0-9]+(-q[0-9]+)?)?$`.
The resolved manifest must stay inside the item's directory (and the item inside the run); traversal and symlink
escapes return exit 1 with `PROMPT_PATH_INVALID`. This read-only command never starts a provider.

A prompt is built from blocks `Block(kind, origin, text)` (`conductor/prompts.py`); `render(blocks)` joins their texts into
the prompt byte for byte (a separator belongs to the block it follows). Every model role step writes
`<item>/prompts/<step>.manifest.json` (`prompt-manifest/v1`) beside `<step>.md`: `step`, `role`, `route` (`provider`,
`model`, `effort`), `blocks` (`kind`, `origin`, `sha256`, `tokens` estimated by `aicore.content.budget`, `id` for a skill),
`excluded` (`id`, `reason`: the skills the checks of P9.2 left out, see Skill checks), `estimated_tokens` and `prompt_sha256` of the whole prompt.
The `tokens` of the blocks add up to `estimated_tokens` within one token per block. Kinds: `role_text`, `input`,
`repository_rules`, `skill`, `skill_names`, `context_map`, `expected_paths`, `verification`, `run_rules`, `answers`,
`correction`, `progress`, `result_contract`, `research` (the result of the research stage, see [Research](research.md)), the blocks of a delta prompt (`resumed`, `interrupted`, `changed`, see *Resumed sessions*), and for the roles that review, triage and close: `candidate`, `review_scope`,
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

### Resumed sessions

A correction round of an executor whose session goes on does not send the whole prompt (the role text, the execution-input,
the rules, the skills, the scout map: 56–115 KB) to a session that holds it already. `prompts.executor_resumed` builds the
**delta prompt** from the blocks `resumed` (`## Continuation`: the task, the rules and the result contract of the latest full prompt
still apply; earlier correction instructions in the session are historical, and the correction section of this message is the
only current focus), `answers` (only the answers the session has not seen: `executor_session_answers`), `correction` (the red checks,
the confirmed findings, the deviation to fix), `interrupted` (the note of an interrupted round), `changed` (the paths the
earlier round changed), `progress` and `result_contract`. A round that asks nothing the session lacks (the first round of a
piece, a repeat of it) has no delta prompt and is sent in full.

The delta prompt goes only if all three conditions hold for the attempt: (1) its command line continues the session
(`--resume`, or the `resume_argv` of the route); (2) the session received the full prompt of this very piece
(`state.executor_session_item` is the piece: in `shared` mode the first round of the next piece is sent in full into the
continued session); (3) the `task_digest` of the full prompt now equals `state.executor_session_task_digest`, the digest of
the last full prompt the session received. `task_digest` is the sha256 of the canonical JSON `[kind, origin, text]` of the
blocks that carry the task and the instructions — every block but `correction`, `answers`, `interrupted`, `changed`,
`progress` (it names the round) and the `## Run batch` note (it describes the batch, not the task) — so a rebuilt input
(`INPUT_REBUILT`: write set, acceptance, rules), other skills, stubs, repository rules or scout map send the whole prompt.
Any other doubt does the same: the delta prompt is an optimisation, never the only copy of the task.

An attempt that continued a session and ended with an error or without a session (a lost transcript, a provider that
refused the id) forgets the session (the fields above go with it) and emits the info `SESSION_RESUME_FAILED` (`item`,
`stage`, the route with its provider). The next attempt of the step starts a fresh session with the **whole** prompt and no
`--resume`. `prompts/<step>.md` always holds the full prompt of the step, `prompts/<step>.resumed.md` the delta one when it
was sent; the manifest of the step lists the blocks that were sent, with `resumed_session: true` for a delta prompt and the
`task_digest` of the full one (both optional fields of `prompt-manifest/v1`).

A Codex executor resumes with `resume_argv` of its entry in the launch catalog (`launch-catalog.json` 1.6.0):
`codex -a never exec resume {session} --json -c sandbox_mode="{write_sandbox}" --model … -c model_reasoning_effort=… -`.
`codex exec resume` has no `--sandbox`, so the mode of the first round (`danger-full-access` for `[orch.launch] access =
open`, `workspace-write` for `confined`) is passed as a `-c` override; the model and the effort are those of the first
round and `-a never` stays before `exec`. The thread id comes from `thread.started`. A route started from
`[orch.conductor.argv]` (a command line of the user) has no `resume_argv` and starts fresh.

### Review of round 2 and later

With `review.audit_scope: corrected` (default) the diff block of the reviewer in round N>1 is the diff against the base of
the paths changed since review N-1 only, headed "Diff against the base of the paths changed since review N-1 (the full
diff was reviewed in round 1; read other files as needed)", plus the files named by the `location` of the findings still to
be fixed: a later report that does not name an earlier confirmed finding is no proof that it was fixed, so every confirmed
finding of every earlier round (at any severity) stays in the scope list of the round (`F1 (review 1)`) and its file in the
diff. Each review stores the tree it started from in `state.items[ref].review_marks[N]` (`{path: sha256}` of the dirty tree
without the conductor reports, the artifact folder and the plan folder). Round 1, `audit_scope: full` and a run without
marks (made before they existed) get the whole diff, as before.

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

Skill names in run options match `^[a-z0-9][a-z0-9_:-]*(?:[./][a-z0-9][a-z0-9_:-]*)*$`:
`bucket:name` and `core/context-economy` are valid; traversal segments and absolute paths are refused as
`OPTIONS_INVALID`. Named files belong to the project's `.claude/skills` or `.agents/skills` root. Every resolved
component must stay inside that root, including the root itself; a symlink cannot grant a directory outside it.
An absent named file is still left to the provider as before. Auto files may be outside the project: the bridge's
path must be absolute, canonical, have no symlink components, and name `SKILL.md`. Orch does not locate the partner's
skill library. It compares SHA-256 of the exact file bytes with `skill_md_sha256` of the selected row; the separate
directory `digest` is not a file checksum. Old rows without `skill_md_sha256` are excluded (`digest_missing`).

Reads are strict UTF-8 and capped before opening: `SKILL.md` at 64 KiB, `selection.json` at 16 KiB, and rule carriers
(`CLAUDE.md`/`AGENTS.md`) at 256 KiB. A bounded descriptor read also catches a file growing after stat and refuses
symlink replacement. A present sidecar must validate against aicore `skill-selection/v1`; an absent sidecar retains
the default policy. A named sidecar belongs to the same skill root; an auto sidecar belongs to the selected skill's
directory. A rule carrier belongs to the project. Invalid carriers emit `RULES_PATH_INVALID` and contribute no rules.
Invalid skills emit `SKILL_PATH_INVALID`, with a manifest exclusion reason `outside` (also missing/unreadable or
nonregular auto files), `symlink`, `too_large`, `not_utf8`, `digest_missing`, `digest_mismatch` or `selection_invalid`.
These file checks run again on later reads, even when `skills_checked` already holds a verdict.

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

Each policy exclusion is listed in `manifest.excluded` of the step (`id`, `reason`) and is a beacon `SKILL_EXCLUDED` with the detail
(for example the missing tool or the size). A skill left out is not named in the prompt either. If two kept skills are a pair
of `conflicts` (by id, by name, or by the folder of a `<bucket>/<folder>` entry), the role does not start: the piece stops
`PROMPT_CONFLICT` with the pair. The verdict is made once per piece and kept in the state (`skills_checked`). Contradictions
between the texts of skills ("must" against "never") are not detected: that cannot be done deterministically.

`limits.skill_tokens_max` defaults to 5000 (0 disables the token ceiling only in trusted configuration or invocation
options). A work-source layer may keep or lower an enabled ceiling, or enable one when the trusted value is 0;
disabling or raising it is `OPTIONS_UNTRUSTED`. Byte caps apply independently of the token ceiling.

`orch conduct prompt explain --item REF --step STEP [--run RUN] [--json]` prints the blocks of one step as a table (kind,
origin, tokens, the start of the digest) and what was left out; the default run is the latest. `MANIFEST_UNKNOWN` (exit 1)
means the step wrote none, `RUN_UNKNOWN` that there is no such run. The observer lists the five heaviest blocks by role.

## Files: what is committed

| Path | Git | Content |
| --- | --- | --- |
| `.swissknifeman/state/orch/conductor/<run>/` (`projects/<code>/local/state/orch/conductor/<run>/` of the workspace when the project marker names one) | ignored | `run.json`, `state.json`, `progress.jsonl`; per piece `input.json`, `options.json`, `routes.json`, `prompts/` (`<step>.md`, `<step>.resumed.md` (the delta prompt, when it was sent) and `<step>.manifest.json`), `streams/` (raw role streams with token logs), `agents/<agent_run_id>/`, `reports/`, `checks/<n>/V#.log`, `register-report.json`; after a `resume --retry` `attempts/<n>/` holds the streams, reports, prompts and checks of the steps that retry repeated, and `state.json` the record `items.<ref>.attempts[]` (`n`, `retried_at`, per step `verdict`, `role`, `route`, `ended`, `report_status`, `files`); the observer report lists them under "Retried pieces" |
| `.swissknifeman/state/orch/conductor/cache/scout/` | ignored | context maps keyed by the content of the brief (without `provenance` and `digest`, which move with every write to the plan journal), the route, the role text, the names and texts of the selected skills and the stub; written whole (`durable_replace`), a hit only for a non-empty UTF-8 file |
| `.swissknifeman/state/orch/runs/<run>/` | ignored | the orch run journal of `source …` |
| artifact folder of the piece (`artifacts_dir` of the brief; the planner: `plans/<plan>/artifacts/<item>/`) | committed | `stage-report.json` (closed), `review-verdict.json` (selector, rounds, sessions, findings with the triage's reproductions, the stream path in state), `evidence/V#.json` (check-evidence) |
| `.swissknifeman/orch/reports/<run>/` | ignored | `observer.json`, `observer.md` (written when the run ends, after its last commit) |
| `.swissknifeman/orch-artifacts/<run>/<item>/` | ignored | local records: the artifact folder of a source without `artifacts_dir` (a workspace plan, the file source); never in a commit of the piece. The planner bridge copies the evidence of a workspace plan item into `<plan>/artifacts/<item>/<run>/evidence/` at register and the item refers to it there; files tracked before the folder was ignored stay in the index |
| the plan (JSON) | committed | through the work source's own commit |

### Run records

The documents the conductor keeps in a run folder are closed by `schemas/records/v1` (`urn:swissknifeman:orch:records:<kind>:v1`,
`orch.conductor.records`): each is checked before it is written (`durable_replace`, `0600`) and after it is read, and
`orch.py validate <kind> FILE` checks one by hand. A new document carries `"$schema": "<its $id>"`; a document written
before records/v1 has no tag and is read as v0: the tag is added in memory and the document is checked (its file is not
rewritten, the next write under the lease writes v1), so runs started earlier resume. A tag of another kind or value is
`unknown or conflicting record tag`. `state` validation costs about 1 ms on the largest characterization state, so every
`RunStore.save` checks it. A step marked `done` is replayed by a resume, so it must carry the result its reader takes
(checks: one row `{id, green, …}` per check; executor: `report`; review: `findings`, a conductor/v1 `review-findings`
document; triage: `triage`, a conductor/v1 `triage-result` document; brief:
`input_path`; register: `outcome` and `gate`; commit: `outcome`; any other key: some `result`); a started or stopped
step carries none. `skills_auto` and `skills_checked` hold the choice of each role, kept once per piece.

| Kind | File | Written by | Error |
| --- | --- | --- | --- |
| `run` | `<run>/run.json` | `RunStore.create`, `RunStore.save_run` (the lane of a `--ready` batch) | `RUN_INVALID` |
| `state` | `<run>/state.json` | `RunStore.save`, `RunStore.next_agent`, under the lock of the run store | `STATE_INVALID` |
| `questions` | `<run>/<item>/questions.json` | the conductor and `orch conduct answer`, under `questions.lock` (taken before the run-store lock) | `QUESTIONS_INVALID` |
| `item-options` | `<run>/<item>/options.json` | the options of the piece: `scenario`, `options` (a run-options document of `conductor/v1`: `skills` as `[{role, names}]`, a layer that gives the same options again), `sources`, `digest`, `claim_route` | `RECORD_INVALID` |
| `item-routes` | `<run>/<item>/routes.json` | the route of each role, rewritten by a fallback, a retry or a reviewer upgrade | `RECORD_INVALID` |
| `lease` | `<run>/lease.json`, `<runs root>/checkouts/<sha16>.json` | the owner of the run lease or the checkout lock (`pid`, `host`, `started_at`, `command`, `run`) | owner `unknown` |

The other runtime documents (risk, review strategy, process, agent records, review verdict, provider gates, observer
report, prompt diff, conformance report) get their kinds in a later item; the five that already publish a short tag
(`"schema": "<name>/v1"`) keep it as their carrier.

Role streams never go into the artifact folder; a review verdict there is short and points at the stream in state.
The shared gitignore policy (`packages/aicore/configs/gitignore-policy.json`, entries `swissknifeman-state`,
`orch-conductor-reports` and `orch-artifacts`) states the same for every connected project, and `orch.py doctor` warns
when the runtime folder, the reports folder or the local artifact folder is not ignored (`orch.conductor-gitignore`,
`orch.conductor-reports`, `orch.conductor-artifacts`, `check-result/v1` with `--json`). `conduct prune` warns when the
local artifact folder of a run it removes holds evidence (`local_evidence`): the file source keeps it only there.

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
- **Extra paths reach every writer.** `scope.extra_paths` (`--allow-path`) is granted to the `executor` and the
  `bounded-implementer` on every provider: a route under the Landlock guard gets `--rw P` (grok, and Claude Code when the
  sandbox does not apply); a Claude Code role also gets `--add-dir P` for its file tools (`--add-dir` takes several values, so
  the conductor puts a flag after the last one), and when the provider sandbox replaces the guard the sandbox block adds
  `"filesystem": {"allowWrite": [P…]}` (absolute or `~` paths; the provider merges it with the user's settings, and
  `allowUnsandboxedCommands: false`, `failIfUnavailable` and the network allowlist stay as they are); a Codex role gets `--add-dir P`
  right after `exec`. Every path passed `OPTIONS_UNSAFE_PATH` first; no role but a writer gets one, and without extra paths the
  command line does not change.
- **Access.** `[orch.launch] access` (default `open`) decides the sandbox of the Codex roles that write (executor,
  bounded-implementer, registrar): `open` runs them with `--sandbox danger-full-access` (no provider sandbox: they reach Docker
  and everything else the user reaches, and the sandbox probe is not needed for them), `confined` with `--sandbox
  workspace-write`. The catalog states it as `{write_sandbox}`; read-only roles keep `read-only` in both modes. Claude Code and
  Grok roles are the same in both modes (their write guard `ro-run.py --rw {cwd}` confines writes to the project and does not
  keep them from Docker). Project and environment layers can only tighten the setting: a project `_unset` or an
  environment `open` cannot remove earlier confinement. The machine, invocation and flags may reopen it explicitly.
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
           "created": "2026-10-17T09:00:00Z", "items": ["P1.1"], "resumes": 0, "owner": null}]}
```

`status` and `reason_code` are those of `conduct status` (from the journal), `created` is the time of the first journal
line (`null` before any line), `items` are the pieces of work seen in the journal (else those of `run.json`), `resumes`
counts the `run.resume` lines. A project without runs gives `{"runs": []}`; a run whose `run.json` cannot be read is
`{"run_id": "cnd-...", "status": "unreadable", "owner": null}` and never an error. `--limit` is at least 1. Without `--json` one line
per run is printed. Exit 0; the project is required as for every other `conduct` verb.

`owner` is `{pid, host, started_at, command}` only while the run lease is held, otherwise `null`; stale metadata
alone never implies ownership. `status --json` adds the same metadata as `lease`, plus `limits`, `beacons` and
per-item `tokens`, `usage_incomplete`, `routes`. Existing journal fields retain their meaning. Missing item usage
is `null`, routes are `{}`, and missing limits are `{}`. Routes expose only `provider`, `model`, `effort`, `class`.
`limits.items` maps item refs to `tokens_max` and effective `tokens_hard_max`; `run_tokens_hard_max` retains
`{value, source, file?}` provenance, with an invocation source when raised. `limit_raises` preserves the raise history,
including an explicit zero removing a hard limit. `beacons` contains the last info event per code, in journal order,
for `BUDGET_OVER`, `BUDGET_UNMETERED`, `STAGE_INTERRUPTED`, `ROLE_ORPHAN_KILLED`, `LIMIT_RAISED`.
JSON display values are redacted before safe shortening; argv and environment from route snapshots are excluded.

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

The observer only reads: the journal and state of the run and the `orch.*` and `planner.*` events of the
project's aicore event journal. Event counts use UTC, from the run start through `state.ended` or the last progress
line, inclusive. Only events whose subject or correlation id matches the conductor run id or an item's `orch_run`
are counted, including agent, provider, review and deviation events. At the end of every run (also a stopped one) the conductor
writes `observer.json` and `observer.md`: repeats and resumes, red checks per check id, review findings by severity,
triage confirmed and rejected, idle time between stages, seconds and tokens by role, scout cache hits, the heaviest prompt blocks by role and the prompt budget classes against their limits (`prompt_budgets_by_role`: largest tokens of a step, limit, steps, steps over; from the prompt manifests), the outcome of
each piece and proposals to improve the run options. `orch conduct observe --follow` prints the notable lines of a run
that is still going from another terminal; `orch conduct observe` writes the report again. Follow exits 0 only after
the latest start/resume segment has ended. Without that final `run.end`, two consecutive free-lease probes give
exit 3 and a resume hint; an unavailable probe keeps waiting. The observer never writes run state or progress.
Silence alone never returns success (`idle_exit_s` remains accepted by the Python helper but no longer ends follow).
Appending progress after a torn line first restores its newline, so the next event remains readable.
`state.ended` keeps the precise UTC end of a completed segment, including fractions of a second; it is cleared by
the next loop. A running segment uses the latest progress line even if an earlier end remains in an older state save.

**Checks by command.** `checks_by_command` (and the table *Checks by command* in `observer.md`) aggregates the command
rows of `state.items.*.steps.checks.*.result[]` (and of earlier attempts) by command: `runs` (every row), `executed` /
`invocations` (rows that started a process), `seconds` (elapsed time of those runs, not CPU time), `red` (executed rows that
failed), `skipped`, `reused` (with `saved_s` and the evidence in `reused_from`), `retried` (an executed check that an
earlier round of the same item had already executed), `ids`, `contexts` (`local`, `standalone`, `partner`, `installed`, from
the command text) and `items`. A skipped row (`fail_fast`, `phase_after_red`) and a reused row ran nothing: they are never
counted in `red` or `red_checks`, even when an older journal names them in a `red …` verdict. The same suite in different
contexts is not a duplicate. The old fields of the report stay as they were; `check_findings` holds what the proposals use
(`duplicate_modules`, `phase_after_red`, `executor_runs_checks`).

Proposals about checks: *item X runs the tests of M twice* (validate.sh of a module without `SKM_VALIDATE_SKIP_TESTS=1` and
the full `test.sh` or `affected-tests.py --run`, or a full `test.sh` and its `-p` subset, in one round and one context),
*phase checks of X ran after a red item check* (needs the cadence of the checks from the item's `input.json`), and
*`checks.executor_runs_checks` is true*. A red check never asks the executor to rerun unchanged acceptance or full suites:
the proposal names concrete new or failing diagnostics or a faster local variant, and the conductor keeps the named
acceptance checks and the phase gates.

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

The `report-fixer` role runs on the conductor's provider by default (an economy model: Claude Code haiku, Codex `gpt-6-luna`, grok);
a `stages` entry `{"role": "report-fixer", "provider": …, "model_class": …}` moves it, and `limits.repairs: 0` turns it off.

`[orch.conductor]` (`configs/config.schema.json`): `provider` (default `claude-code`), `reviewer`
(`grok/grok-4.7/high`), `registrar` (`orch/conductor`), `rules`, `on_blocked`, `questions` (`queue` default, `deny`, `defaults`, `advisor`), `risk` (weights, patterns and `diff_lines` of the dynamic review), `limits.tokens_max`,
`limits.stage_timeout_s`, `limits.check_timeout_s`, `limits.unmetered`, `limits.unmetered_charge_tokens`, `limits.role_timeout_s`, and `argv.<role>`: the command line of a role instead of the
launch catalog entry (`{model}`, `{effort}`, `{cwd}`, `{orch}` are filled in). `argv` is machine-wide: a project file
cannot set it. The tests use it to put fake providers in place of the real CLIs.

Every launch role/provider pair has exactly one entry or refusal in `configs/launch-catalog.json`:

| Role | claude-code | codex | grok |
| --- | --- | --- | --- |
| scout | ✓ | ✓ | ✓ |
| executor | ✓ | ✓ | ✓ |
| bounded-implementer | ✓ | ✓ | ✓ |
| reviewer | ✓ | ✓ | ✓ |
| triager | ✓ | ✓ | ✓ |
| registrar | ✓ | ✓ | refused: plan writes outside checkout |
| report-fixer | ✓ | ✓ | ✓ |
| researcher | ✓ | refused: read-only has no network | ✓ |
| advisor | ✓ | refused: read-only has no network | ✓ |

**File format.** The file states only what is specific. `defaults` hold the fields every entry shares (`transport`, `model_set`);
each role under `roles` holds the fields its providers share (`model_class`, `effort`, `transport`, `timeout_s`) and a
`providers` object with, per provider, its `argv` and only the fields that differ from the role (a `timeout_s` of one
provider, say). An `@name` item of an `argv` stands for the named list under `parts` (`@@` is a literal `@`); a part cannot
name another part and every part must be used. The sandbox and the tool restrictions of a role stay in its own `argv`, never
inside a shared part. `launch.expand_catalog` resolves the file into `launch` -> role -> provider -> entry, which is what every
reader sees (`orch.py launch list|show|argv`); a file already in that resolved form (a `launch` object) is accepted as it is.
`tests/golden/launch-catalog-resolved.json` pins the resolved catalog: a change to a command line, a sandbox flag, a class, an
effort or a timeout of any entry fails `test_launch_compact` until the snapshot is updated as the review of that change.
A machine or a project changes single fields without editing the file: `[orch.launch.entries]` (see
[configuration](configuration.md)).

`refusals: {role: {provider: reason}}` is optional for older catalogs. Each reason is a non-empty string of at most
300 characters; a pair cannot appear in both `launch` and `refusals`. Lookup of a refused pair returns
`LAUNCH_REFUSED: <role>/<provider>: <reason>`, while a pair in neither section keeps `LAUNCH_UNKNOWN`.
Required roles stop before work; optional roles (`context-scout`, `report-fixer`) are skipped. Dry-run marks such
roles `available: false` with the code and reason in `unavailable`, omitting them from `routes` because no argv
exists. `route explain` names the refused provider and reason too. The existing registrar.codex entry (sandbox
`{write_sandbox}`) remains an explicit exception to the read-only sandbox checks.

Grok's `executor` and `bounded-implementer` launch entries use jsonl under `scripts/ro-run.py --rw {cwd}`
(implementation/high, 3600 s and economy/medium, 1800 s respectively). The `reviewer`, `triager`, `researcher`,
`advisor` and `report-fixer` also use jsonl and the same wrapper. All read stdin through `--prompt-file /dev/stdin`, select `--model` and `--effort`,
use `bypassPermissions` and emit `--output-format streaming-messages-json`. A sanitized real stream fixture pins
the existing parser's text, terminal result, errors and token usage; no live model call is needed by the tests.
ACP routes are still refused. Preflight checks the provider after `--` without starting it and caches command
availability for the process: a missing Grok CLI gives `available: false` and `PROVIDER_UNAVAILABLE` in the dry-run,
and stops a required route before claim.

Ordinary Codex scout, and every other Codex role whose launch class is `economy` and whose route does not name a model,
uses `gpt-6-luna` (effort `low` for scout). `gpt-5.6-luna` stays in the inventory and is not the preferred selector.
An explicit executor, reviewer or owner model is kept. Implementation stays `gpt-6-sol` and frontier stays `gpt-6-astra`.
The Grok `scout` uses text transport, `--output-format plain`, `--disable-web-search`, economy/low and 300 s.
The `triager` and `researcher` use implementation/medium and 1800 s; the `advisor` uses frontier/high and 1800 s.
The `reviewer` and `triager` use `--protect {cwd} --rw {cwd}/vendor`; the `scout`, `researcher`, `advisor` and
`report-fixer` use `--protect {cwd}` with no checkout grant. Researcher/advisor keep `run_terminal_command` and
`web_search` to query research sources. `research query` prints results and passes the project cwd to source
commands; configured source processes inherit Landlock, and writes outside its writable areas fail.
All these protected roles disallow `search_replace,write,spawn_subagent,scheduler_create,scheduler_delete,workflow,image_gen,image_edit,image_to_video,reference_to_video`;
the report-fixer also disallows `run_terminal_command`. Landlock permits default writes to `/tmp`, `/var/tmp`,
`/dev` and `~/.grok`; the reviewer and triager also grant the checkout's real `vendor` directory for test caches. Runtime
`--rw` grants for authorized `scope.extra_paths` still apply.

`ro-run.py --protect DIR` is repeatable and fails before starting the provider (exit 3) when the real protected path
is inside a default writable root (`RO_RUN_PROTECT_OVERLAP: <DIR> is inside writable <root>`), an in-checkout
`--rw` path is a symlink or resolves outside it (`RO_RUN_RW_ESCAPE: <path>`), or Landlock ABI is below 3
(`LANDLOCK_ABI_TOO_OLD: <abi>`). This includes checkouts under `/tmp` and symlinked vendor grants. ABI 3 supplies
TRUNCATE protection; calls without `--protect` keep their existing writable rules.

Claude Code roles never use `--bare` (it does not read the subscription login) and
start with `--permission-prompts none`, so a request that would ask for permission is denied instead of waiting.

## Plan engines without `orchestration.options`

The planner declares `orchestration.options` as an extension slot and keeps no copy of this contract: the planner
bridge supplies `run-options` to it (`extends` in its `bridge.json`), so `set` and `check` validate the options by
this schema. A plan engine without the slot refuses the fields with `unexpected property`; a planner that does not find
the bridge refuses the options with `EXTENSION_UNAVAILABLE` and still keeps `orchestration.scenario`. The planner
bridge then reads the scenario and the options from orchestration overlay documents (`add-document`, id
`orchestration-<scope>`, section `orchestration` holding `{"scenario"?, "options"?}`, applying to a phase, an item or,
with `global`, the plan). A field of the same level wins over an overlay.
