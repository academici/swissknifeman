# Configuration

orch reads the `[orch]` section of the layered swissknifeman configuration. The schema is
[`configs/config.schema.json`](../configs/config.schema.json), the commented sample is
[`config.example.toml`](../config.example.toml) (generated; do not edit it by hand). Values come from
`aicore.config`; orch never reads `config.toml` itself.

## Layers

From the lowest to the highest: schema defaults, the machine file, the project file
(`projects/<code>/local/config.toml` of the project's workspace when the project marker names one, else `<project>/.swissknifeman/config.toml`), environment variables, the `--config FILE` of the invocation, flags.
The project is the git repository or the folder with `.swissknifeman` that contains the working directory.
Environment variables are `SKM_ORCH_<KEY>` with `__` between path segments, for example `SKM_ORCH_ENGINE=cao` or
`SKM_ORCH_CAPABILITIES__STALE=refuse`.

`orch.py --config FILE <verb> …` adds the invocation layer. The option goes before the verb. `FILE` has the same
format as the other layers: `schema_version = 1` and an `[orch]` table.

## Keys

| Key | Type | Default | Layers | Meaning |
| --- | --- | --- | --- | --- |
| `engine` | `native`, `cao`, `claude-only` | `native` | all | engine used when nothing more specific applies |
| `engine_by_role` | table: role id → engine | empty | all | engine of a role |
| `default_profile` | string | `solo` | all | run-policy used when a scenario names none |
| `debug` | boolean | `false` | all | debug mode of conductor runs: the `DEBUG_MODE` beacon with the observer protocol and a journal in `<run>/debug/` (`run --debug`/`--no-debug` for one run; see [conductor](conductor.md#debug-mode)) |
| `work_source` | string | `planner-orch` | all | id of the plugin of the extension point `orch:work-source` |
| `capabilities.stale` | `warn`, `refuse` | `warn` | all | what preparation does with a capability record past its freshness date |
| `profiles.dirs` | array of paths | empty | defaults, machine, invocation, flags | extra folders with run-policy packs |
| `events.enabled` | boolean | `true` | all | whether `orch.run.*` events are emitted |
| `conductor.provider` | string | `claude-code` | all | provider of every conductor role whose stage names none |
| `conductor.reviewer` | selector | `grok/grok-4.7/high` | all | reviewer of the conductor (`PROVIDER/MODEL[/CONTEXT][/EFFORT]`) |
| `conductor.registrar` | actor | `orch/conductor` | all | who registers outcomes in the work source |
| `conductor.rules` | array of strings | empty | all | executor rules of every run (the first run-options layer) |
| `conductor.on_blocked` | `stop`, `report` | `stop` | all | what a blocked piece of work does to the run |
| `conductor.foreign_untracked` | `refuse`, `keep` | `refuse` | all | untracked files already in the tree at the start of new work: stop with `WORKTREE_DIRTY`, or keep them out of every piece (a tree shared with another session); tracked changes always stop |
| `conductor.session_executor` | `shared`, `handoff`, `per-item` | `shared` | all | one session for all pieces of a run (`shared`, Claude Code `--resume`), a fresh executor session per piece with the handoff of the earlier pieces (`handoff`) or a fresh one per step; the first run-options layer, so a plan, `--options` and `--batch` / `--no-batch` override it |
| `conductor.questions` | `queue`, `deny`, `defaults`, `advisor` | `queue` | all | what a blocking question of the executor does: blocked `QUESTION` and wait for `orch conduct answer`, blocked `QUESTION_DENIED`, a `default` answered once by policy, or the advisor's advice (needs `advisor.enabled`; advice that needs the owner is queued) |
| `conductor.generate`, `conductor.generate_check`, `conductor.generated_paths` | arrays of strings | empty | defaults, machine, invocation, flags | the command that regenerates the generated files of the project (`generated_paths`, globs) and the one that proves them fresh, run in the checkout of the run before the checks of every round (a first argument with a slash is a path of that checkout); a write-set path under `generated_paths` is then no write-protected path: the executor changes the source, the regenerated files belong to the piece (beacon `GENERATED`), a failure stops with `GENERATE_FAILED`. |
| `conductor.limits.*` | integers | `tokens_max` 0, `stage_timeout_s` 0, `stage_idle_timeout_s` 5400, `check_timeout_s` 7200, `check_idle_timeout_s` 3600 | all, except the run cap below | default limits of a run: `tokens_max` is a beacon, a check is stopped after `check_timeout_s` (0: no wall), `stage_timeout_s` (0: off) is a wall for every role, the silence ceilings stop a hung role or check (see `conductor.md`) |
| `conductor.limits.role_timeout_s` | table role → integer ≥ 0 | `context-scout` 900, `triager` 1800, `report-fixer` 600, `registrar` 600, `reviewer` 3600, `advisor` 1800, `researcher` 2700 (executor and bounded-implementer: none) | all | wall in seconds on a streaming role; a table names only the walls it changes, 0 removes one; `stage_timeout_s` > 0 takes precedence; exceeded → `TIMEOUT`, then the retry rule |
| `conductor.limits.unmetered` | `stop` or `charge` | `stop` | all | what an attempt that reports no usage does while `tokens_hard_max` or `run_tokens_hard_max` is set: `stop` → `TOKEN_BUDGET_UNMETERED`; `charge` → counted as `unmetered_charge_tokens` |
| `conductor.limits.unmetered_charge_tokens` | integer ≥ 0 | 50000 | all | fresh input tokens charged per attempt without usage under `unmetered = "charge"` |
| `limits.triage_repro_timeout_s` (run option, not a configuration key) | integer ≥ 0 | 600 | `--options`, the plan, phase and item layers | ceiling in seconds on the read-only rerun of a rejected Blocker or Major finding's reproduction; past it the rejection is unproven and the finding is confirmed again (`TRIAGE_REPRO_UNVERIFIED`); 0 sets none (see `conductor.md`) |
| `conductor.limits.tokens_hard_max` | integer ≥ 0 | 0 (unlimited) | all | hard admission limit on accounted fresh tokens of a piece; `TOKEN_BUDGET` preserves done steps |
| `conductor.limits.run_tokens_hard_max` | integer ≥ 0 | 0 (unlimited) | defaults, machine, project, invocation | hard admission limit on fresh tokens of the whole run; environment and work-source options cannot set it |
| `conductor.argv.<role>` | array of strings | empty | defaults, machine, invocation, flags | command line of a role instead of the launch catalog entry |
| `launch.catalog` | absolute path or `~` | empty (the shipped catalog) | defaults, machine, invocation, flags | a complete launch catalog file used instead of `configs/launch-catalog.json`; a relative path is refused (`LAUNCH_CATALOG_RELATIVE`) |
| `launch.access` | `open`, `confined` | `open` | all (project and environment can only tighten) | how far the roles that write (executor, bounded-implementer, registrar) reach on a provider CLI with a sandbox of its own (Codex): `open` is its widest mode (`danger-full-access`, so the role can use Docker and whatever the user can), `confined` keeps it in the workspace (`workspace-write`); roles that must not write stay read-only in both. History preserves the trusted floor across project `_unset` and project/environment `open`; machine, invocation and flags may explicitly reopen access |
| `launch.entries.<role>_<provider>.*` | `model_class`, `effort`, `timeout_s`, `transport`, `model_set`, `argv` | empty | `model_class`, `effort`, `timeout_s`: all; `transport`, `model_set`, `argv`: defaults, machine, invocation, flags | the fields of one catalog entry that differ (`executor_codex`, `bounded-implementer_claude-code`); the rest stays as the catalog has it, and the result must still be a valid catalog (`LAUNCH_INVALID`); an entry the catalog lacks is `LAUNCH_UNKNOWN`. `orch.py launch show ROLE PROVIDER` and `route explain` name the key that changed a field |
| `research.policy`, `research.sources.<id>.*` | see [research](research.md) | `conditional`, no sources | `argv`: defaults, machine, invocation, flags; the rest all | research sources: `command`, `filesystem`, `mcp-stdio` |
| `supervisor.recover` | `notify`, `stop-only`, `resume` | `notify` | defaults, machine, invocation, flags; the lowest wins | what `orch conduct supervise` does about a hung or dead conductor: say so, also stop and reap, also resume (see [conductor](conductor.md#supervisor)); a flag or `--config` file can only lower the machine value, a project file is `CONFIG_LAYER_FORBIDDEN` |
| `supervisor.max_recoveries`, `supervisor.window_s` | integer ≥ 0, integer ≥ 1 | `2`, `3600` | defaults, machine, invocation, flags | the breaker: resumes per run within the window before the supervisor gives the run up; `--max-recoveries` can only lower the first |
| `autopilot.allowed` | boolean | `false` | defaults, machine | whether this machine lets `orch conduct autopilot` run at all (see [conductor](conductor.md#autopilot)); a project file that sets it is `CONFIG_LAYER_FORBIDDEN`, and the autopilot then leaves the project layer out and stops with `AUTOPILOT_NOT_ALLOWED` |
| `autopilot.enabled` | boolean | `false` | all | the project's switch of the autopilot (a machine may set it for every project) |
| `autopilot.require_readiness` | boolean | `true` | all; on when any layer turns it on | a lane starts only when the work source says its phase is ready (op `readiness`) |
| `autopilot.max_runs`, `autopilot.max_wall_s`, `autopilot.max_no_progress_runs`, `autopilot.max_auto_decisions`, `autopilot.quota_wait_max_s`, `autopilot.max_recoveries` | integer ≥ 1, ≥ 1, ≥ 1, ≥ 0, ≥ 0, ≥ 0 | `20`, `43200`, `2`, `10`, `21600`, `1` | all; the lowest of the machine value and the other layers and flags wins | runs per session; seconds per session (the deadline is kept in `autopilot.json`); runs in a row without a closed piece; questions answered by the advisor or panel; longest quota wait; resumes per run after a crash, hang or one-time failure. `--max-runs` and `--max-wall-s` of `start` can only lower them |
| `autopilot.poll_s` | integer ≥ 1 | `30` | all | seconds between two looks of the controller at its run, its requests and its deadline |
| `supervisor.interval_s`, `supervisor.hung_after_s`, `supervisor.grace_s`, `supervisor.notify_send` | integer ≥ 1, integer ≥ 1, integer ≥ 1, boolean | `60`, `300`, `60`, `false` | all | seconds between passes; age of the heartbeat from which a conductor that waits for nothing is hung; time a hung conductor gets after SIGINT and after SIGTERM before SIGKILL; also call `notify-send` |
| `isolation.codex.auth` | `link`, `copy` | `link` | defaults, machine, invocation, flags | how `auth.json` of the original `CODEX_HOME` (else `~/.codex`) gets into the CODEX_HOME of an isolated Codex role (`<run dir>/isolation/codex-home`): a symbolic link, so a refreshed token is written to the original; `copy` only for a machine whose codex refuses the link (a copy rotates the refresh token and can log the interactive codex out). The profiles themselves are `configs/isolation-profiles.json` (see [conductor](conductor.md#isolation-profiles)) |
| `stubs.enabled`, `stubs.layers` | boolean, array of `machine`, `project` | `true`, both | defaults, machine, invocation, flags | additional instructions of the roles (`orch stubs publish|list|show`); a machine that runs repositories it does not trust sets `layers = ["machine"]` (see [conductor](conductor.md#stubs-additional-instructions-of-the-roles)) |
| `advisor.enabled`, `advisor.max_rounds` | boolean, integer ≥ 0 | `false`, `2` | all | the advisor role: asked on a blocking question (`conductor.questions = advisor`), red checks past `check_fixes` and a rejected Major finding, at most `max_rounds` times per piece (see [conductor](conductor.md#the-advisor-p104)) |
| `advisor.human_gate` | array of `security`, `destructive`, `public-api`, `scope-expansion`, `other` | the first four | defaults, machine, invocation, flags | base categories held for the owner; a project or environment attempt is `CONFIG_LAYER_FORBIDDEN` |
| `advisor.human_gate_extra` | array of the same categories | empty | all, additive across history | additional categories held for the owner; effective gate = base gate ∪ every layer's extra categories, even after `[]` or `_unset` |
| `advisor.min_confidence` | `high`, `medium`, `low` | `medium` | all, strictest across history | advice below the minimum is held; `high` > `medium` > `low`, and a lower value or `_unset` cannot weaken any earlier threshold (including the default) |
| `advisor.panel` | array of `PROVIDER[/MODEL_CLASS[/EFFORT]]` | empty | all | routes of the advisor panel, 2 or 3 (fewer is off; a fourth is ignored); each member advises independently, see [The advisor](conductor.md#the-advisor-p104) |
| `advisor.panel_on` | array of `low_confidence`, `always` | `["low_confidence"]` | all | when the panel advises: after a single advice of low confidence, or for every problem |

`profiles.dirs` makes orch read policy files from the listed paths, so a project file, which lives in a repository
that somebody else may control, cannot set it (`CONFIG_LAYER_FORBIDDEN`); neither can the environment. A leading `~`
is expanded; a relative entry is refused (`PROFILES_DIR_RELATIVE`), because the folder it would be taken from
cannot be told once a higher layer appends to the array. `conductor.argv` chooses the commands the conductor runs,
so a project file cannot set it either ([conductor](conductor.md#configuration)); the same holds for
`research.sources.<id>.argv` ([research](research.md)).

Advisor gates use both the category proposed by the model and categories computed from changed paths and the write set
using `conductor.risk.patterns` (`security`, `public_cli`/`schema` → `public-api`), plus changes outside the write set
(`scope-expansion`). `needs_owner`, any gated category, or confidence below the effective threshold holds advice for
the owner (`ADVICE_HELD` names the source). `approval` and `credential` questions stay open for the owner under every
`conductor.questions` mode, including `defaults` and `deny` (`QUESTION_OWNER_ONLY`). Automatic question resolutions
record `authority {mode, gate, code_categories, confidence}`; defaults use `confidence: null`.

Hard token limits count fresh input plus output, excluding cache reads. With positive `tokens_max` and
`tokens_hard_max`, the informational target must fit inside the hard limit (`OPTIONS_INVALID`). A run's `--options`
can override `run_tokens_hard_max`; `run.json.limits_run` freezes its value and source at start. Later config changes
do not change that run cap. Continue an exhausted run with `conduct resume --run RUN --raise-limit KEY=N` (repeatable;
only the two hard token keys, a larger value or explicit 0 to remove it). Raises have provenance in state and leave
the recorded item options unchanged. See [hard token limits](conductor.md#hard-token-limits-and-resume) for guarantees
and incomplete usage.

## Engine choice

`orch.settings.select_engine(settings, role, flag=None)` returns the engine and a `launch-plan.decisions` entry of
kind `binding`:

1. the flag (`ENGINE_FROM_FLAG`),
2. `engine_by_role[role]` (`ENGINE_FROM_ROLE`),
3. `engine` (`ENGINE_FROM_CONFIG`).

Lower sources that named another engine are listed as overridden (`ENGINE_OVERRIDDEN`). An unknown engine is refused
(`ENGINE_UNKNOWN`). The chosen engine is never replaced by another one: a stage that the engine cannot honour is
refused with the missing capability.

## Configuration digest

`settings.affecting(settings)` holds the values that change what preparation produces: `engine`, `engine_by_role`,
`default_profile` and `capabilities.stale`. `settings.digest(settings)` is the SHA-256 of their canonical JSON, so
changing `work_source`, `profiles.dirs` or `events.enabled` does not change it.
