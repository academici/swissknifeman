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
| `conductor.session_executor` | `handoff`, `shared`, `per-item` | `handoff` | all | a fresh executor session per piece with the handoff of the earlier pieces (`handoff`), one session for all pieces of a run (`shared`, Claude Code `--resume`) or a fresh one per step; the first run-options layer, so a plan, `--options` and `--batch` / `--no-batch` override it |
| `conductor.questions` | `queue`, `deny`, `defaults`, `advisor` | `queue` | all | what a blocking question of the executor does: blocked `QUESTION` and wait for `orch conduct answer`, blocked `QUESTION_DENIED`, a `default` answered once by policy, or the advisor's advice (needs `advisor.enabled`; advice that needs the owner is queued) |
| `conductor.limits.*` | integers | `tokens_max` 0, `stage_timeout_s` 0, `stage_idle_timeout_s` 5400, `check_timeout_s` 0, `check_idle_timeout_s` 3600 | all | default limits of a run: `tokens_max` is a beacon, the wall-clock ceilings are off (nothing long is cut), the silence ceilings stop a hung role or check (see `conductor.md`) |
| `conductor.argv.<role>` | array of strings | empty | defaults, machine, invocation, flags | command line of a role instead of the launch catalog entry |
| `launch.catalog` | absolute path or `~` | empty (the shipped catalog) | defaults, machine, invocation, flags | a complete launch catalog file used instead of `configs/launch-catalog.json`; a relative path is refused (`LAUNCH_CATALOG_RELATIVE`) |
| `launch.access` | `open`, `confined` | `open` | all (a project file can only tighten) | how far the roles that write (executor, bounded-implementer, registrar) reach on a provider CLI with a sandbox of its own (Codex): `open` is its widest mode (`danger-full-access`, so the role can use Docker and whatever the user can), `confined` keeps it in the workspace (`workspace-write`); roles that must not write stay read-only in both. A project value `open` over a machine value `confined` is ignored |
| `launch.entries.<role>_<provider>.*` | `model_class`, `effort`, `timeout_s`, `transport`, `model_set`, `argv` | empty | `model_class`, `effort`, `timeout_s`: all; `transport`, `model_set`, `argv`: defaults, machine, invocation, flags | the fields of one catalog entry that differ (`executor_codex`, `bounded-implementer_claude-code`); the rest stays as the catalog has it, and the result must still be a valid catalog (`LAUNCH_INVALID`); an entry the catalog lacks is `LAUNCH_UNKNOWN`. `orch.py launch show ROLE PROVIDER` and `route explain` name the key that changed a field |
| `research.policy`, `research.sources.<id>.*` | see [research](research.md) | `conditional`, no sources | `argv`: defaults, machine, invocation, flags; the rest all | research sources: `command`, `filesystem`, `mcp-stdio` |
| `stubs.enabled`, `stubs.layers` | boolean, array of `machine`, `project` | `true`, both | defaults, machine, invocation, flags | additional instructions of the roles (`orch stubs publish|list|show`); a machine that runs repositories it does not trust sets `layers = ["machine"]` (see [conductor](conductor.md#stubs-additional-instructions-of-the-roles)) |
| `advisor.enabled`, `advisor.max_rounds`, `advisor.human_gate` | boolean, integer ≥ 0, array of `security`, `destructive`, `public-api`, `scope-expansion`, `other` | `false`, `2`, the first four | all | the advisor role: asked on a blocking question (`conductor.questions = advisor`), red checks past `check_fixes` and a rejected Major finding, at most `max_rounds` times per piece; advice that needs the owner or has a gated category is queued, never applied (see [conductor](conductor.md#the-advisor-p104)) |

`profiles.dirs` makes orch read policy files from the listed paths, so a project file, which lives in a repository
that somebody else may control, cannot set it (`CONFIG_LAYER_FORBIDDEN`); neither can the environment. A leading `~`
is expanded; a relative entry is refused (`PROFILES_DIR_RELATIVE`), because the folder it would be taken from
cannot be told once a higher layer appends to the array. `conductor.argv` chooses the commands the conductor runs,
so a project file cannot set it either ([conductor](conductor.md#configuration)); the same holds for
`research.sources.<id>.argv` ([research](research.md)).

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
