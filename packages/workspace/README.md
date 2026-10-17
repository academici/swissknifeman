# workspace

The portable workspace module of the ecosystem. The plans of all projects live in one git repository of their own
(the *workspace*) instead of inside each project's repository, so they can be moved between machines without touching
product history. This module creates that repository, keeps the record of its projects and ties the checkouts of one
machine to them. It is a small command-line tool built on the `aicore` foundation (Python 3.9+, standard library only).

The places, the seven document contracts, the resolver that tells where the plans of a project live and the shared
resolution vectors belong to `aicore.workspace` ([ADR 0085](../../docs/architecture/decisions/0085-portable-workspace.md)).
This module is the command line over them. Migration of existing plans, connecting a remote and sync come later.

## Commands

Run as `swissknifeman workspace <command>` or `bin/workspace <command>`. Every command takes `--json`, which prints one
JSON object on stdout. A failure prints `CODE: message` on stderr and exits 1; wrong arguments exit 2.

| Command | What it does |
| --- | --- |
| `init [--root DIR]` | Create the layout (`workspace.json`, `projects/`, baseline `.gitignore`, `.gitattributes`, `README.md`, `.staging/`), `git init -b main`, the first commit `skm(workspace): init` with a `Workspace-Device` trailer, and the device file of this machine. On a workspace that exists it changes nothing (`already_initialized`). A non-empty folder without `workspace.json` is `WORKSPACE_ROOT_NOT_EMPTY` and nothing is written. |
| `status [--fetch]` | Git state (branch, changed paths, remote without user information, ahead and behind of the last fetch; `--fetch` fetches first), the projects with their bindings here, the last sync. |
| `doctor` | Checks as `check-result/v1`: `workspace.layout`, `workspace.documents`, `workspace.bindings`, `workspace.legacy-plans`, `workspace.git`. Exit 1 only on `fail`; a machine without a workspace gets a warning. |
| `doctor --publish-safety [--all]` | Publish-safety rules on the files of the next commit (`--all`: every tracked and untracked file that is not ignored); prints a `publish-report/v1` document (see below). Exit 1 and `PUBLISH_BLOCKED` on stderr when a rule blocks; warnings and local-only files exit 0. |
| `project attach [--project DIR] [--name N] [--yes]` | Tie a checkout to a project: use the id of its marker, else match its remotes against the projects of the workspace (never its name), else create a project. Writes the marker `.swissknifeman/project.json` and prints the command that commits it; it never commits. |
| `project list` | Projects of the workspace and where they are bound on this machine. |
| `project show PROJECT_ID` | The project record, its binding and the folders it holds in the workspace. |
| `project scan DIR...` | Find checkouts with a marker (depth 4; `node_modules`, `.git` and `vendor` are skipped) and bind those of known projects. A marker with an unknown id is reported as `unknown`; no project is created. |
| `project rebind PROJECT_ID --path DIR` | Replace the bound paths by one checkout whose marker names the project (`BINDING_MARKER_MISMATCH` otherwise). |
| `project detach PROJECT_ID [--path DIR]` | Drop a binding of this machine; the workspace is not changed. |

## Publish-safety

The workspace is pushed to a remote, and a secret or a machine path that reaches git history is not removed by an ignore
file. `doctor --publish-safety` applies these rules (`safety.py`); the report lists `block`, `warn` and `local_only`
findings, each with the rule, the path (relative to the workspace) and a detail, and a `verdict` (`ok`, `warn`, `block`).
A secret value is never printed: the detail names the rule, the line and the mask `‹redacted›`.

| Rule | Condition | Level |
| --- | --- | --- |
| `PS-SECRET` | a match of the `aicore.util.redact` patterns in a UTF-8 text file within `max_tracked_bytes`, or a secret file name (`.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `credentials.*`, `secrets.*`) | block |
| `PS-MANIFEST-PATH` | an absolute path in `workspace.json`, `projects/*/project.json`, `projects/*/local-only.json`, `projects/*/migrations/*.json` | block |
| `PS-SYMLINK` | any symbolic link | block |
| `PS-TOP-LEVEL` | a top-level entry outside `.gitignore`, `.gitattributes`, `workspace.json`, `README.md`, `projects` | block |
| `PS-PROJECT-LEVEL` | `projects/` holds anything but `prj_<id>` folders, or a project folder holds anything but `project.json`, `plans`, `legacy-plans`, `migrations`, `local-only.json` | block |
| `PS-EXECUTABLE` | the execute bit | warn |
| `PS-HOME-PATH` | `/home/<user>/`, `/Users/<user>/` or `C:\Users\` in the text of plan data | warn |
| `PS-TRACKED-LOCAL-ONLY` | git already tracks a file that is now local-only; nothing is removed from the index here | warn |
| `PS-SIZE` | larger than `max_tracked_bytes` | local-only (`size`) |
| `PS-BINARY` | a NUL byte in the first 8000 bytes and larger than `max_binary_tracked_bytes` | local-only (`binary`) |

Two kinds of match are not treated as secrets because they are common in plan text: a lower-case hyphenated word that starts
with `sk-` (the tail of a slug such as `task-development-workflow`) and the value of a `name = value` pair that is a
placeholder (`<NAME>`, `$NAME`, `{name}`) or a secret reference (`env://NAME`).

Local-only files stay out of git. `localonly.update` keeps `projects/<id>/local-only.json` (path relative to the project
folder, size, SHA-256, owning device, reason; sorted, portable) and `localonly.rebuild_exclude` rebuilds the block between
`# skm:local-only begin` and `# skm:local-only end` in `.git/info/exclude` from the entries of this device, leaving every
other line alone. Sync and migrate call them; neither takes `git.lock` itself, the caller holds it.

## Where things are

| What | Where |
| --- | --- |
| the workspace (the one git root) | `SKM_WORKSPACE_ROOT`, else `<data>/workspace` (`~/.local/share/swissknifeman/workspace`) |
| bindings, device, git lock | `<state>/workspace` (`bindings.json`, `device.json`, `git.lock`); never in git |
| the marker of a project | `<checkout>/.swissknifeman/project.json`, committed with the project |

Every command that changes the workspace repository holds `git.lock` (`WORKSPACE_GIT_LOCKED` after the configured
wait). Git is always called with an argument list, never through a shell, and never with force, `reset --hard` or `clean`.

## Configuration

The `[workspace]` table (machine layer and defaults only; see `config.example.toml`): `publish.max_tracked_bytes`
(5242880), `publish.max_binary_tracked_bytes` (1048576), `git.lock_timeout_s` (60) and `plans_migrator`
(`workspace-planner`).

## Events

`workspace.root.initialized` (`{workspace_id}`) and `workspace.project.attached` (`{project_id, created}`), described by
`schemas/event-data/v1/`. They are journaled in the machine journal after the locks are released; a failing journal does
not change the result of a command. The extension point `workspace:plans-migrator` is filled by a bridge.

## Tests

`bash scripts/test.sh` runs the stdlib unittest suite against a throwaway `HOME`, `SKM_HOME` and `SKM_WORKSPACE_ROOT`
with temporary git repositories; it never touches a real workspace.
