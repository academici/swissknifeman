# Project-local launcher

Every command that works on a project runs through the file `.swissknifeman/launcher.py` inside that project. No
user, Task file, AI command or conductor passes `--project`, `--plans-root` or a path to `packages/*/scripts/*.py`:
the project root comes from where the launcher lies.

```sh
cd /work/product
swissknifeman project init                                   # once: writes the launcher and its lock
python3 -I .swissknifeman/launcher.py planner next PLAN7     # from any folder of the project
python3 -I .swissknifeman/launcher.py orch conduct run --plan PLAN7 --items P2.1
python3 -I .swissknifeman/launcher.py project context --json
```

A Taskfile hides the path once (optional; go-task is not required by anything):

```yaml
tasks:
  skm:
    cmds: ["python3 -I .swissknifeman/launcher.py {{.CLI_ARGS}}"]
```

## The chain

```text
.swissknifeman/launcher.py        stdlib only, ~60 lines, no module logic; exec (same process id)
  -> swissknifeman (PATH)         the installed hub entry, bin/swissknifeman; exec
  -> scripts/umbrella.py          validates the launcher context before routing anything
  -> module CLI (one per unit)    planner, orch, aicore project, ... ; exec
  -> aicore.state.resolve_project / planner store: the launcher root wins
```

The project holds only the transport. A fix of planner, orch or any module is installed in the hub and applies to
every project at once; `project sync` is needed only when the launcher protocol or the template changes.

## Contract

| Variable | Set by | Meaning |
| --- | --- | --- |
| `SKM_LAUNCHER_ACTIVE` | launcher | `1` |
| `SKM_LAUNCHER_PROTOCOL` | launcher | launcher protocol (today `1`) |
| `SKM_LAUNCHER_PATH` | launcher | canonical `<root>/.swissknifeman/launcher.py` |
| `SKM_LAUNCHER_PROJECT_ROOT` | launcher | canonical project root |
| `SKM_LAUNCHER_PID` | launcher | its process id: the context binds only this process |
| `SKM_INVOCATION_CWD` | launcher | the folder the command was called from |

The launcher removes `PYTHONPATH` and `SKM_PROJECT_ROOT`, refuses to run as a symlink or outside
`<root>/.swissknifeman/`, and exits 127 with `HUB_NOT_INSTALLED` when `swissknifeman` is not on `PATH`.

The umbrella (`aicore.state.validate_launcher_env`) checks before any builtin, alias or module: the protocol (older
than supported `LAUNCHER_PROTOCOL_TOO_OLD`, newer `LAUNCHER_PROTOCOL_NEWER`), the root, the launcher file (regular,
not a symlink, exactly at `<root>/.swissknifeman/launcher.py`), a second root source (`PROJECT_CONTEXT_CONFLICT`), the
cwd, and the lock (`launcher.lock.json`: missing is a warning, an error with `SKM_LAUNCHER_STRICT=1`; a protocol other
than the launcher's is refused). Messages go to stderr as `CODE: message`; stdout belongs to the module.

**Authority.** With a launcher context `aicore.state.resolve_project` returns the launcher root; a `--project` naming
another folder is `PROJECT_CONTEXT_CONFLICT`, an equal one is accepted. The planner store gives the plans folder of the project marker (`<root>/plans`, or the folder of the portable
workspace for `plans_store: workspace`) without a search, and `--plans-root` or a plan path outside that folder is `PROJECT_PATH_OVERRIDE_FORBIDDEN`. Without a launcher the
legacy order stays: `--project`, `SKM_PROJECT_ROOT`, the nearest `.git`/`.swissknifeman`.

**Process binding.** The exec chain keeps the process id, so the context is honoured only when
`SKM_LAUNCHER_PID` is the current process. A child (an agent of a conductor run, a git hook, an `orch.py` the
conductor starts with its own `--project`) inherits the variables but not the authority and resolves its project the
legacy way. A conductor lane in a worktree is therefore never pinned to the main tree.

## Commands (`swissknifeman project`, aicore)

| Command | Does |
| --- | --- |
| `init [--marker-only] [--adopt] [--dry-run] [--json]` | writes launcher + lock at the git root of the working directory (`--marker-only` outside git) |
| `sync [--adopt] [--dry-run] [--json]` | brings the managed files to the hub template; equal files are a no-op |
| `verify [--json] [--no-roundtrip]` | file, lock, digest, protocol, hub on PATH, round trip launcher -> umbrella -> same root |
| `context [--json]` | `invocation-context/v1`: root, invocation cwd, resolution, launcher (verified), `plans_root` and `plans_store {kind, project_id, workspace, reason}` of the project marker |
| `doctor [--json]` | verify + project config `schema_version` + write boundary of state, backups and a legacy plans folder + `project.plans-store` (the marker's store resolves; a workspace store lies outside the project by design) |
| `exec -- <group> [args...]` | runs a group through this project's launcher |

Writes: a temporary file in the same folder, `fsync`, `os.replace`, `fsync` of the folder
(`aicore.util.io.durable_replace`); the lock is written after the launcher. A sync holds
`.swissknifeman/project-sync.lock` (exclusive create, pid/host/start/operation; a lock of a dead process on this host
is taken over, any other is `PROJECT_SYNC_LOCKED`). A launcher this hub did not write is `FOREIGN_LAUNCHER` and is
replaced only with `--adopt` (a backup goes to `.swissknifeman/backups/`). `config.toml`, state, plans and unknown files
are never touched.

Contracts (aicore): `project-launcher-lock/v1` (`$schema`, `protocol`, `template_sha256`, `managed_files`; nothing
machine-specific, committed with the project) and `invocation-context/v1`. Template: `packages/aicore/templates/project/launcher.py`.

## Unit execution policy

`unit.json` may declare `execution: {project, cwd, writes}`. The umbrella refuses a `project: required` module without
a project (`PROJECT_CONTEXT_REQUIRED`, help words pass), starts a `cwd: project` module in the project root and a
`cwd: unit` module in its own folder. planner: `required` / `preserve` / `project`; orch: `optional` / `preserve` /
`project-and-machine` (both keep the cwd: relative `--file`/`--input` arguments mean the folder the user stood in).
`aicore.state.require_project_path(root, path)` refuses a write target that leaves the project after symlinks
(`PROJECT_WRITE_OUTSIDE_ROOT`, `PROJECT_WRITE_SYMLINK_ESCAPE`).

One public CLI per capability: `ecosystem-units check` refuses a second `provides.cli` (`UNIT_CLI`); the conductor is
`orch conduct ...` (`scripts/conduct.py` stays a private development entry).

## Decisions

1. The launcher context is bound to the process id, not inherited: children fall back to the legacy resolution.
2. The launcher removes `SKM_PROJECT_ROOT` instead of setting it, so no conflicting root reaches children.
3. `PYTHONSAFEPATH` is not set: it would leak into agents and project tests; `python3 -I` isolates the launcher itself.
4. The project commands live in aicore (`aicore project`, alias `project` of the umbrella): the umbrella stays a router.
5. The lock `$schema` follows the aicore contract ids (`urn:swissknifeman:aicore:project-launcher-lock:v1`); there is
   no `minimum_hub_version`: the protocol is the compatibility unit.
6. The run does not check the template digest (`verify` and `context` do): a hub fix never forces a sync.
7. Command catalogs keep the shorthand `plan.py`, defined once per command as
   `python3 -I .swissknifeman/launcher.py planner`; no command names a package root or script path
   (`packages/planner/tests/test_launcher_mode.py` scans every provider surface).
8. POSIX only for now: `bin/swissknifeman` is bash; Windows needs a native console entry first.

## Not done yet

- Fleet update `swissknifeman projects verify|sync --all` from the maind project registry (stage 6 of the idea):
  no consumer yet; `project sync` per project covers it until the pilot projects are migrated.
- Strict lock mode by default (`SKM_LAUNCHER_STRICT=1` is the switch) and refusing an equal `--project` in launcher
  mode: after the pilot projects carry a lock.
- `harness` still finds the planner package root for its own runs (`harness/run/task_paths.py`); internal, not a
  user surface.
- Tracing event `skm.invocation.started` (`--trace-context`): no consumer.
