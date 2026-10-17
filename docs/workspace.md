# Portable workspace

The plans of a project normally live in its repository, in `plans/`. That ties them to one checkout: a second machine
sees only what was committed, plans mix with product history, and large artifacts of runs end up in git. The *portable
workspace* moves the plans of all projects into one git repository of their own. A project keeps only a small marker
that says where its plans live.

```sh
swissknifeman workspace init                                   # once per machine: create the workspace repository
swissknifeman workspace project attach --project . --yes       # write the marker; new plans go to the workspace
swissknifeman workspace migrate plan --project .               # dry run for a project that already has plans/
swissknifeman workspace migrate apply --project .              # move them
```

## The five areas of data

| Area | What it is | Where | In git |
| --- | --- | --- | --- |
| Product | the code of the project | its own repository | yes, its own |
| Marker | `{project_id, plans_store}` that names the plan store | `<checkout>/.swissknifeman/project.json` | yes, with the product |
| Plans | plan folders (`plan.json`, phases, items, notes) | `<workspace>/projects/<id>/plans/` | yes, in the workspace repository |
| Legacy plans | old-format folders and loose files, kept as they were | `<workspace>/projects/<id>/legacy-plans/` | yes, in the workspace repository |
| Machine state | bindings of checkouts to projects, the device id, the git lock | `<state>/workspace/` | never |

Large run artifacts are a sixth case handled inside the Plans area: they stay on the machine that made them
(`local-only.json`, see publish-safety below).

## Layout

```text
<workspace>/                       SKM_WORKSPACE_ROOT, else ~/.local/share/swissknifeman/workspace
  workspace.json                   workspace id and format
  .gitignore  .gitattributes  README.md
  .staging/                        scratch space of a migration; inside the workspace so a rename never crosses a volume
  projects/
    prj_<id>/
      project.json                 project record (name, remotes)
      plans/<plan-id>/...          plans of the planner
      plans/archive/<plan-id>/...  archived plans
      legacy-plans/<name>/...      folders that are not plans; legacy-plans/_root holds loose files
      migrations/<op_id>.json      one report per migration
      local-only.json              large files that stay out of git
```

Nothing portable (workspace, project, marker, local-only index, migration report) holds an absolute path. Absolute paths
exist only in the machine state, which is never committed.

## Attach and the marker

`workspace project attach` ties a checkout to a project. The project id comes from the marker if the checkout has one;
else the remotes of the checkout are matched against the projects of the workspace; else a project is created. A folder
name or a path is never an identity. The command writes the marker and prints the commit that records it; it never commits.

The marker field `plans_store` decides where the planner reads and writes plans:

- `legacy`: `<checkout>/plans`.
- `workspace`: `<workspace>/projects/<id>/plans`.

Exactly one store is in use at any moment; plans are never written to both. The marker travels with the repository, so
after `git pull` a second machine knows the project id and only has to bind the checkout (`workspace project scan`).
A project without a marker behaves as before.

## Migration

`workspace migrate` moves `<checkout>/plans` into the workspace.

| Command | What it does |
| --- | --- |
| `migrate discover [DIR...]` | lists checkouts that hold a `plans/` folder; reads structure and sizes only |
| `migrate plan --project DIR` | dry run, writes nothing: classes, digests, actions, local-only files, warnings, blockers |
| `migrate apply --project DIR` | runs the migration; prints the git commands to run next, never commits |
| `migrate verify --project DIR` | compares the last report of this machine with the workspace copies and the old folders |
| `migrate rollback --project DIR` | switches the marker back to `legacy` and removes what the migration brought in |
| `migrate cleanup --project DIR --confirm PROJECT_ID` | deletes old folders whose copy in the workspace is identical |

Flags: `--on-conflict keep-workspace|import-copy`, `--allow-in-progress`, `--lock-timeout S` (apply), `--json`.

**Classes.** A folder with a `plan.json` of the plan schema is a plan (also under `plans/archive/`). Every other folder
is legacy and is copied byte for byte to `legacy-plans/`; the planner never reads it. Loose files in `plans/` go to
`legacy-plans/_root`. Derived data (`views/`, `context/`, `.lock` of a plan, `__pycache__`, `.DS_Store`) is not copied.

**Dry run.** `plan` computes a SHA-256 for every file and judges each by the publish-safety rules as if it already stood
in the workspace. Blockers: a secret, a symlink, a plan item still `in_progress` (unless `--allow-in-progress`), an
invalid marker. Exit code 1 on a blocker.

**Apply.** The critical section takes the migration lock of the project and the plan lock of every plan, recomputes the
digest of the source, copies into `.staging/` inside the workspace and checks every digest, loads each staged plan and
runs the plan check (a plan that was red before stays exactly as red; a new error stops the migration), renames the staging
folder into `projects/<id>/plans`, writes the marker `plans_store = workspace` and releases the locks. Afterwards the
module writes `local-only.json`, the report `migrations/<op_id>.json` and the binding. The source is not deleted. Before
the rename the workspace has no `plans/` for the project, and a failure there leaves nothing behind and the marker
unchanged. A failure after the rename is completed by repeating `apply`, which finds the copy with the same digest and only
writes the marker. A repeat of a finished migration changes nothing and reports `noop`.

**A planner that is writing during the migration.** A planner process that waits for the plan lock of the old folder gets
the lock only after the switch, sees the marker and fails with `PLANS_MIGRATED` ("rerun the command"); its rerun uses the
workspace. A write into the old folder after the switch is impossible.

**A second machine (import).** When `projects/<id>/plans` already exists in the workspace (it came with `git clone`), each
plan is compared by digest: equal gives `skipped-equal`, absent gives `copied`, different gives a conflict. `apply` refuses a
conflict with `MIGRATION_CONFLICT` until you choose `--on-conflict keep-workspace` (keep the workspace plan, skip the local
one) or `import-copy` (keep both; the local plan is stored as `<plan-id>~<device>`, the last 8 characters of the device id).
Nothing is overwritten silently. Legacy folders that differ are imported under `<name>~<device>` without a conflict.

**Rollback.** Possible while the workspace copy of every plan still equals the report and the old folder still has the digest
of the report; otherwise `MIGRATION_DIVERGED` lists what differs. It removes only what the migration put in.

**Cleanup.** Deletes an old folder only if its digest equals the copy in the workspace (the others are kept with a reason),
then removes `plans/` if it is empty. It runs no git command; when `plans/` was tracked it prints
`git -C <root> rm -r --cached plans && git commit ...`. `--confirm` must repeat the project id.

The critical section runs in the bridge `workspace-planner` behind the port `workspace:plans-migrator`; register it with
`swissknifeman config set --machine aicore.plugins.workspace-planner.manifest <hub>/bridges/workspace-planner/extension.json`
and `... .trusted true`. `workspace doctor` shows whether it is found. A large project can take long: the plugin has a
timeout of 3600 s and reports progress on stderr.

## Publish-safety

The workspace is pushed to a remote, and anything that reaches git history stays there. `workspace doctor --publish-safety`
(and `migrate plan|apply`) apply these rules:

| Level | What |
| --- | --- |
| block | a secret (key patterns, `.env`, `*.pem`, `*.key`, `credentials.*`), an absolute path in a portable document, any symlink, an unknown top-level or project-level entry |
| warn | a home path (`/home/<user>/`, `/Users/<user>/`) in plan data, the execute bit, a file that git tracks but is now local-only |
| local-only | a file over 5 MiB, or a binary over 1 MiB: not committed, listed in `local-only.json`, excluded through `.git/info/exclude` |

A secret value is never printed; the report names the rule, the line and the mask.

## Error codes

Workspace: `WORKSPACE_NOT_INITIALIZED`, `WORKSPACE_ROOT_NOT_EMPTY`, `WORKSPACE_LAYOUT_INVALID`, `WORKSPACE_GIT_LOCKED`,
`WORKSPACE_GIT_TOO_OLD`, `ATTACH_CONFIRM_REQUIRED`, `PROJECT_UNKNOWN`, `PROJECT_AMBIGUOUS`, `PROJECT_MARKER_INVALID`,
`BINDING_MARKER_MISMATCH`, `BINDING_PATH_MISSING`, `REMOTE_UNREACHABLE`, `PUBLISH_BLOCKED`.

Migration: `MIGRATION_BLOCKED_SECRET`, `MIGRATION_BLOCKED_SYMLINK`, `MIGRATION_IN_PROGRESS`, `MIGRATION_CONFLICT`,
`MIGRATION_LOCKED` (a plan lock or the project migration lock was not free in time), `MIGRATION_SOURCE_CHANGED` (the source
changed after the dry run; run `plan` again), `MIGRATION_COPY_MISMATCH`, `MIGRATION_VERIFY_FAILED`, `MIGRATION_FAILED`,
`MIGRATION_ALREADY_APPLIED`, `MIGRATION_NOT_APPLIED`, `MIGRATION_DIVERGED`, `CLEANUP_CONFIRM_MISMATCH`,
`LOCAL_ONLY_NOT_RECORDED`, `MIGRATOR_UNAVAILABLE` (the bridge is not registered or cannot find the planner).

Planner: `PLANS_MIGRATED` (the plans of this project moved to the workspace; rerun the command), `PLAN_SOURCE_UNBOUND` (a
plan in the workspace needs a bound checkout for repository paths), `WORKSPACE_PROJECT_MISSING`.

## Safety rules for git

The workspace is changed by git only through argument lists, never through a shell. Nothing here uses force push,
`reset --hard` or `clean`, and a conflict is never resolved by picking a side. A remote URL is printed without user
information. Every git change of the workspace holds one lock (`git.lock` in the machine state).
