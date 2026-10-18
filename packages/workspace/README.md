# workspace

The portable workspace module of the ecosystem. The plans of all projects live in one git repository of their own
(the *workspace*) instead of inside each project's repository, so they can be moved between machines without touching
product history. This module creates that repository, keeps the record of its projects and ties the checkouts of one
machine to them. It is a small command-line tool built on the `aicore` foundation (Python 3.9+, standard library only).

The places, the seven document contracts, the resolver that tells where the plans of a project live and the shared
resolution vectors belong to `aicore.workspace` ([ADR 0085](../../docs/architecture/decisions/0085-portable-workspace.md)).
This module is the command line over them. Connecting a remote and sync come later.

## Commands

Run as `swissknifeman workspace <command>` or `bin/workspace <command>`. A machine can hold several workspaces; a command works with the one chosen by `--workspace CODE` (anywhere in the arguments), `SKM_WORKSPACE`, the marker of the project you are in, or the only workspace there is. Every command takes `--json`, which prints one
JSON object on stdout. A failure prints `CODE: message` on stderr and exits 1; wrong arguments exit 2.

| Command | What it does |
| --- | --- |
| `init --code CODE [--root DIR]` | Create the workspace `CODE` under `workspaces/CODE`: the layout (`workspace.json`, `projects/`, baseline `.gitignore`, `.gitattributes`, `README.md`, `.staging/`), `git init -b main`, the first commit `skm(workspace): init` with a `Workspace-Device` trailer, and the device file of this machine. On a workspace that exists it changes nothing (`already_initialized`). A non-empty folder without `workspace.json` is `WORKSPACE_ROOT_NOT_EMPTY` and nothing is written. |
| `status [--fetch]` | Git state (branch, changed paths, remote without user information, ahead and behind of the last fetch; `--fetch` fetches first), the projects with their bindings here, the last sync. |
| `doctor` | Checks as `check-result/v1`: `workspace.layout`, `workspace.documents`, `workspace.bindings`, `workspace.legacy-plans`, `workspace.git`, `workspace.plans-migrator`. Exit 1 only on `fail`; a machine without a workspace gets a warning. |
| `doctor --publish-safety [--all]` | Publish-safety rules on the files of the next commit (`--all`: every tracked and untracked file that is not ignored); prints a `publish-report/v1` document (see below). Exit 1 and `PUBLISH_BLOCKED` on stderr when a rule blocks; warnings and local-only files exit 0. |
| `project attach [--project DIR] [--name N] [--code CODE] [--yes]` | Tie a checkout to a project: use the code of its marker, else match its remotes against the projects of the workspace (a name is not an identity), else create a project whose code is made from the folder name (or `--code`; `PROJECT_CODE_TAKEN` if another project has it). Writes the marker `.swissknifeman/project.json` and prints the command that commits it; it never commits. |
| `project list` | Projects of the workspace and where they are bound on this machine. |
| `project show CODE` | The project record, its binding and the folders it holds in the workspace. |
| `project scan DIR...` | Find checkouts with a marker (depth 4; `node_modules`, `.git` and `vendor` are skipped) and bind those of known projects. A marker with an unknown id is reported as `unknown`; no project is created. |
| `project rebind PROJECT_ID --path DIR` | Replace the bound paths by one checkout whose marker names the project (`BINDING_MARKER_MISMATCH` otherwise). |
| `project detach PROJECT_ID [--path DIR]` | Drop a binding of this machine; the workspace is not changed. |
| `migrate discover [DIR...]` | Checkouts that hold a `plans/` folder: launcher projects (`.swissknifeman/launcher.py`) under DIR (default `~/projects`, depth 4) and `local_path` of `<state>/maind/registry.json`. Reads the structure and the sizes, never a plan file; shows the marker and the number of plan and legacy folders. |
| `migrate plan --project DIR [--on-conflict keep-workspace\|import-copy] [--allow-in-progress] [--local-only-secrets] [--code CODE] [--yes]` | Dry run, writes nothing: the project, the class, digest and action of each folder, local-only files, warnings and blockers (exit 1 on a blocker). |
| `migrate apply --project DIR [same flags] [--lock-timeout S]` | Runs the checks of `plan`, calls the port, then writes `local-only.json`, the report and the binding. Prints `next`, never commits. |
| `migrate verify --project DIR` | The last report of this device against the workspace copies and the old folders. |
| `migrate rollback --project DIR` | Marker back to `legacy`; removes the folders the migration brought in. |
| `migrate cleanup --project DIR --confirm CODE` | Removes the old folders whose copy in the workspace has the same digest. |
| `connect --remote URL [--branch B]` | Classify the remote (`empty` or the same workspace; `REMOTE_FOREIGN`, `REMOTE_OTHER_WORKSPACE`) and add it as `origin`; never commits or pushes. |
| `clone URL [--code CODE] [--root DIR]` | Make a workspace of this machine from a remote: cloned beside the workspaces and moved to `workspaces/<code>` (the code is read from the remote's `workspace.json`), and the device file. |
| `list` | The workspaces of this machine: code, root, remote, number of projects. |
| `sync [--commit] [--pull] [--push] [--resolve PATH=local\|remote ...] [--resolve-reset]` | Commit (publish-safety first), pull (dry merge with `git merge-tree`, typed conflicts), resolve and push without force (see Sync). No flag: commit and pull; `--push` runs both first. |

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
| `PS-PROJECT-LEVEL` | `projects/` holds anything but folders named by a project code, or a project folder holds anything but `project.json`, `plans`, `legacy-plans`, `migrations`, `local-only.json` | block |
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

## Migration

`migrate` moves the plans of a checkout (`<root>/plans`) into `projects/<code>/` of the workspace (contract
`workspace-contract#migration`, decisions D4, D8, D12, D13). The critical section (locks, copy, verify, rename, marker) runs in
the bridge `workspace-planner` behind the port `workspace:plans-migrator`; this module never imports it. It finds the plugin named
by `workspace.plans_migrator` in `[aicore.plugins]`, else a module of the hub that declares the port in `provides.ports`. Register the
bridge with `swissknifeman config set aicore plugins.workspace-planner.manifest <hub>/bridges/workspace-planner/extension.json`
and set `trusted = true` so it receives `PLANNER_ROOT`; `workspace doctor` shows whether it is found.

- **Classes.** A folder with a `plan.json` of the plan schema is v4 (`plans/<id>`, `plans/archive/<id>`); any other folder is
  legacy and is copied byte for byte to `legacy-plans/<name>`; loose files go to `legacy-plans/_root`. `views/`, `context/` and
  `.lock` of a plan and `__pycache__` / `.DS_Store` are derived and not copied. A symlink blocks the migration.
- **Dry run.** `plan` and `apply` judge every file by the publish-safety rules as if it stood in the workspace: a secret is a
  blocker (`MIGRATION_BLOCKED_SECRET`, the value is never printed), a file over `max_tracked_bytes` (or a large binary) is
  local-only and ends in `local-only.json` and the exclude block, home paths warn. An item in progress is
  `MIGRATION_IN_PROGRESS` unless `--allow-in-progress`.
- **`--local-only-secrets`** (`plan` and `apply`; `migrate.build_plan|apply(..., local_only_secrets=True)`). Without it nothing
  changes. With it, a file whose *content* matches a secret pattern (`PS-SECRET`) is no blocker: it is copied into the workspace
  at its place like a big file, listed in `local-only.json` with the reason `secret-pattern`, kept out of git by the exclude
  block, and the plan and the report carry the warning `PS_SECRET_LOCAL_ONLY` (the plan with the file count). The files stay on
  this machine: `doctor --publish-safety` and `sync --commit` never see them, `verify` compares them like every file,
  `rollback` and `cleanup` treat them like other local-only files. Other blockers keep blocking: symlinks, and files with a
  secret *name* (`.env`, `*.pem`, `*.key`, ...) even with the flag. If the exclude block is lost, publish-safety blocks the
  files again.
- **A workspace that already has the project** (the second machine). Equal digest: `skipped-equal`; absent: `copied`; different:
  `conflict` and `apply` refuses with `MIGRATION_CONFLICT` unless `--on-conflict keep-workspace` (keep the workspace copy) or
  `import-copy` (keep both; the checkout copy is stored as `<name>~<device>`, the last 8 characters of the device id). Nothing is
  overwritten.
- **Report.** `migrations/<op_id>.json` (`workspace-migration/v1`) holds no absolute path. Archived plans have a `/` in their
  name; the schema forbids it in a report name, so it is written `%2F` (`archive%2F<id>`; `%` is `%25`).
- **Rollback and cleanup.** `rollback` is possible while the workspace copy of every plan equals the report and the old folder
  still has the digest of the report (`MIGRATION_DIVERGED` with the list otherwise); it removes only what the migration put in. The
  source is never deleted by `apply`; `cleanup` deletes an old folder only when its digest equals a copy in the workspace.
  `cleanup` and `apply` do not run git: they print the commands (`git rm -r --cached plans`, commit the marker, `workspace sync`).
- **One device.** `verify`, `rollback` and `cleanup` use the newest report of this machine's device; a report of another device
  describes another checkout.

## Where things are

| What | Where |
| --- | --- |
| the workspaces | `SKM_WORKSPACES_ROOT`, else `<data>/workspaces` (`~/.local/share/swissknifeman/workspaces/<code>`, one git root each); chosen by `--workspace`, `SKM_WORKSPACE`, the marker, or the only one |
| bindings, sync state, git lock | `<state>/workspaces/<code>` (`bindings.json`, `sync.json`, `git.lock`); the device `<state>/workspaces/device.json`; never in git |
| the marker of a project | `<checkout>/.swissknifeman/project.json`, committed with the project |

Every command that changes the workspace repository holds `git.lock` (`WORKSPACE_GIT_LOCKED` after the configured
wait). Git is always called with an argument list, never through a shell, and never with force, `reset --hard` or `clean`.

## Sync

`sync` runs under `git.lock` and follows `workspace-contract#sync`: **commit** (publish-safety over the changed files; a
`block` stops everything with `PUBLISH_BLOCKED` and nothing is committed; local-only files go to `local-only.json` and the
exclude block; a tracked file that became local-only is removed from the index with a warning and stays on disk; the execute
bit is cleared in the index; `git add -A` of `projects`, `workspace.json`, `.gitignore`, `.gitattributes`, `README.md`; the
commit is `skm(plan): <plan-id> sync <N> files` when one plan changed, else `skm(workspace): sync <N> files`, with the trailer
`Workspace-Device`), **pull** (`git fetch origin`, then `git merge-tree --write-tree`: clean is merged, fast-forward where
possible; a conflict changes neither the working tree nor `HEAD`, lists `conflicts[{path, project_id, plan, ref}]` and exits 1
`WORKSPACE_CONFLICT`), **resolve** (`--resolve PATH=local|remote`, repeatable and in parts; decisions are kept in `sync.json`
only for the paths of the last conflict report, else `RESOLUTION_INCOMPLETE`; when every path is decided and `origin/<branch>`
and `HEAD` are as at the pull the merge is made, else `WORKSPACE_CONFLICT_STALE` and the decisions are dropped;
`--resolve-reset` drops them; an error during the merge runs `git merge --abort`) and **push** (`git push origin HEAD:<branch>`,
never forced; `WORKSPACE_BEHIND` when the remote has news; the remote without user information and the branch are printed
before the push and are in the `--json` answer). `--resolve` cannot be combined with `--pull`. The side is always yours to
name: nothing here picks one.

`sync.json` (machine state) holds `last_commit_at`, `last_pull_at`, `last_push_at`, `last_result`, `last_conflicts` and
`pending_resolutions`; `audit.jsonl` gets one line per operation. Both live in `workspace_state_dir()`, never in git.

## Configuration

The `[workspace]` table (machine layer and defaults only; see `config.example.toml`): `publish.max_tracked_bytes`
(5242880), `publish.max_binary_tracked_bytes` (1048576), `git.lock_timeout_s` (60) and `plans_migrator`
(`workspace-planner`).

## Events

`workspace.root.initialized` (`{code, workspace_id}`), `workspace.project.attached` (`{project_id, created}`), `workspace.migration.applied` (`{project_id, op_id, mode, plans, local_only}`) and `workspace.migration.rolled-back` (`{project_id, op_id}`), `workspace.sync.committed` (`{sha, files}`), `workspace.sync.pulled` (`{head, merged}`), `workspace.sync.conflict` (`{paths}`) and `workspace.sync.pushed` (`{head}`), described by
`schemas/event-data/v1/`. They are journaled in the machine journal after the locks are released; a failing journal does
not change the result of a command. The extension point `workspace:plans-migrator` is filled by a bridge.

## Tests

`bash scripts/test.sh` runs the stdlib unittest suite against a throwaway `HOME`, `SKM_HOME` and `SKM_WORKSPACES_ROOT`
with temporary git repositories; it never touches a real workspace.
