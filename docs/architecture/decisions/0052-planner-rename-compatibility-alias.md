# ADR 0052: `task` becomes `planner` in one rename, with a compatibility plugin for one minor release

## Status

Accepted

## Context

[ADR 0009](0009-task-renamed-to-planner.md) decided that the module `task` is renamed to `planner` and that the old
names keep working for a window. Claude Code builds the command namespace from the plugin manifest name, a command
cannot call another command through `Skill` because commands set `disable-model-invocation`, and the native
marketplace `renames` entry rewrites `enabledPlugins` and drops the old commands at once. A rename done in pieces
would leave imports, command ids and consumers under two names.

## Decision

- **One rename.** The folder, the Python package (`lib/planner`), the unit id, the Claude and Codex plugins, the
  command ids (`planner:*`), the Codex and Cursor skills and the Grok prefix-hold plugin change together, and every
  consumer in the repository changes in the same step. The plan schema URNs `urn:swissknifeman:task:plan:*`, the
  `task_files` field and the history of past releases do not change.
- **Compatibility plugin `task`.** `packages/planner/aliases/task` holds generated copies of the ten commands. Each
  copy starts with a deprecation line and then follows the `planner` command. It carries no skills and has its own
  marketplace entry, so `/task:*` keeps working for the window.
- **Environment window.** `PLANNER_ROOT` is read first; `SKM_TASK_ROOT` is still accepted and warns with
  `SKM_TASK_ROOT_DEPRECATED`. The bridge dispatcher also exports `TASK_ROOT` and `TASK_PLAN_PY` for the window.
  Command lines written as `task:<id>` are read as `planner:<id>` with a warning.
- **Removal.** When the window ends, the alias plugin is deleted and the marketplace gets `renames {task: planner}`,
  so installed copies migrate through the native mechanism. Codex, Cursor and Grok have no aliases; project
  projections are refreshed by `swissknifeman upgrade`.

## Alternatives considered

- `renames {task: planner}` at once: rejected, it removes `/task:*` immediately.
- A `task` command that calls the `planner` command: rejected, a command cannot call a command.
- Keeping the name `task`: rejected in ADR 0009.

## Consequences

- Two plugins appear in the marketplace for one release, with ten generated commands in the second one.
- Plans, URNs and contract names stay readable by old and new tools.

## Supersedes

None. Refines [ADR 0009](0009-task-renamed-to-planner.md) and the alias window of [ADR 0020](0020-migration-discipline.md).
