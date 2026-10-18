# Portable workspace

The plans of a project normally live in its repository, in `plans/`. That ties them to one checkout: a second machine
sees only what was committed, plans mix with product history, and large artifacts of runs end up in git. The *portable
workspace* moves the plans of all projects into one git repository of their own. A project keeps only a small marker
that says where its plans live.

A machine can hold several workspaces (say `axioma` for the company and `home` for private work). Each is a git repository
of its own in `workspaces/<code>/`; a project belongs to exactly one of them.

```sh
swissknifeman workspace init --code axioma                     # once per workspace: create its repository
swissknifeman workspace project attach --project . --yes       # write the marker; new plans go to the workspace
swissknifeman workspace migrate plan --project .               # dry run for a project that already has plans/
swissknifeman workspace migrate apply --project .              # move them
```

## The five areas of data

| Area | What it is | Where | In git |
| --- | --- | --- | --- |
| Product | the code of the project | its own repository | yes, its own |
| Marker | `{workspace, project_id, plans_store}`: the workspace and the project by code, and where the plans live | `<checkout>/.swissknifeman/project.json` | yes, with the product |
| Plans | plan folders (`plan.json`, phases, items, notes) | `<workspace>/projects/<code>/plans/` | yes, in the workspace repository |
| Legacy plans | old-format folders and loose files, kept as they were | `<workspace>/projects/<code>/legacy-plans/` | yes, in the workspace repository |
| Machine state | bindings of checkouts to projects, the sync state, the git lock; the device id | `<home>/state/workspaces/<code>/`; `<home>/state/workspaces/device.json` | never |

Large run artifacts are a sixth case handled inside the Plans area: they stay on the machine that made them
(`local-only.json`, see publish-safety below).

## Codes

A workspace and a project are named by a **code**: lowercase words of letters and digits joined by single hyphens, starting
with a letter, at most 40 characters (`axioma`, `billium`, `skm-wt`). There is no generated id to read: the code is the folder
name (`workspaces/axioma/projects/billium/`), the key in the machine bindings and the value in the marker. For a project the
code is, as a rule, the name of the checkout folder (`attach` makes it from the folder name; `--code` chooses another). A code is
fixed once a project exists; two projects with the same code in one workspace are refused (`PROJECT_CODE_TAKEN`).

## Layout

```text
~/.local/share/swissknifeman/      the machine home (SKM_HOME moves it)
  workspaces/                      SKM_WORKSPACES_ROOT; one folder, one git repository per workspace
    axioma/                        the workspace "axioma"
      workspace.json               code, workspace id and format
      .gitignore  .gitattributes  README.md
      .staging/                    scratch space of a migration; inside the workspace so a rename never crosses a volume
      projects/
        billium/                   the project "billium"
          project.json             project record (code, name, remotes)
          plans/<plan-id>/...      plans of the planner
          plans/archive/<plan-id>/...  archived plans
          legacy-plans/<name>/...  folders that are not plans; legacy-plans/_root holds loose files
          migrations/<op_id>.json  one report per migration
          local-only.json          large files that stay out of git
```

**Which workspace a command uses.** `--workspace CODE` (anywhere in the arguments), else `SKM_WORKSPACE`, else the workspace
named by the marker of the project you are in, else the only workspace of the machine. Several workspaces and none chosen is
`WORKSPACE_AMBIGUOUS`. `workspace list` shows the workspaces of the machine.

Nothing portable (workspace, project, marker, local-only index, migration report) holds an absolute path. Absolute paths
exist only in the machine state, which is never committed.

## Attach and the marker

`workspace project attach` ties a checkout to a project. The project code comes from the marker if the checkout has one (its
workspace must be the chosen one: `WORKSPACE_MISMATCH`); else the remotes of the checkout are matched against the projects of
the workspace; else a project is created, with the code made from the folder name or given with `--code`. A path is never an
identity, and a folder name only proposes the code of a new project. The command writes the marker and prints the commit that
records it; it never commits.

The marker field `plans_store` decides where the planner reads and writes plans:

- `legacy`: `<checkout>/plans`.
- `workspace`: `workspaces/<workspace>/projects/<code>/plans`.

Exactly one store is in use at any moment; plans are never written to both. The marker travels with the repository, so
after `git pull` a second machine knows the workspace and the project and only has to bind the checkout (`workspace project scan`).
A project without a marker behaves as before.

### Optional links `plans/` and `tasks/` in the checkout

To open the code in an IDE and see the plans next to it, a checkout can carry the symbolic links `plans/` and `tasks/` to
`workspaces/<workspace>/projects/<code>/plans` and `tasks`. They are off by default: `workspace project link` makes them for one
project (and remembers it in `projects/<code>/local/config.toml`), `workspace project unlink` removes them, the setting
`workspace.link_folders` turns them on for every project of the machine (a project value beats it), and `project attach|add` and
`sync` keep the links of the projects where it is on. The links are listed in the checkout's own `.git/info/exclude`, so the
code repository never tracks them. A real `plans/` or `tasks/` folder, or a link that points anywhere else, is never replaced;
the plans stay in the workspace (`plans/` is linked only with `plans_store: workspace`). `migrate` refuses a checkout whose `plans/`
is such a link (`PLANS_LINKED`): `project unlink` first. `project doctor` checks the links (`project.links`).

## Migration

`workspace migrate` moves `<checkout>/plans` into the workspace.

| Command | What it does |
| --- | --- |
| `migrate discover [DIR...]` | lists checkouts that hold a `plans/` folder; reads structure and sizes only |
| `migrate plan --project DIR` | dry run, writes nothing: classes, digests, actions, local-only files, warnings, blockers |
| `migrate apply --project DIR` | runs the migration; prints the git commands to run next, never commits |
| `migrate verify --project DIR` | compares the last report of this machine with the workspace copies and the old folders |
| `migrate rollback --project DIR` | switches the marker back to `legacy` and removes what the migration brought in |
| `migrate cleanup --project DIR --confirm CODE` | deletes old folders whose copy in the workspace is identical |

Flags: `--on-conflict keep-workspace|import-copy`, `--allow-in-progress`, `--local-only-secrets`, `--code CODE` (the code of a project the workspace does not know yet), `--lock-timeout S` (apply), `--json`.

**Classes.** A folder with a `plan.json` of the plan schema is a plan (also under `plans/archive/`). Every other folder
is legacy and is copied byte for byte to `legacy-plans/`; the planner never reads it. Loose files in `plans/` go to
`legacy-plans/_root`. Derived data (`views/`, `context/`, `.lock` of a plan, `__pycache__`, `.DS_Store`) is not copied.

**Dry run.** `plan` computes a SHA-256 for every file and judges each by the publish-safety rules as if it already stood
in the workspace. Blockers: a secret, a symlink, a plan item still `in_progress` (unless `--allow-in-progress`), an
invalid marker. Exit code 1 on a blocker.

**Secrets that stay on the machine (`--local-only-secrets`).** Plans often hold files that only look like secrets (a variable
named `token`, a provider log, a review diff). The safety rule is not weakened and nobody certifies hundreds of files, so with
`--local-only-secrets` (`plan` and `apply`) every file with a secret *pattern in its content* stops being a blocker and is
migrated like a big local-only file: copied into the workspace at its place, listed in `local-only.json` with the reason
`secret-pattern`, excluded from the workspace git by the exclude block. The plan and the report carry the warning
`PS_SECRET_LOCAL_ONLY` (the plan with the number of files). These files are not published: `doctor --publish-safety` and
`sync --commit` do not see them, `verify` compares them like other files, `rollback` and `cleanup` handle them like other
local-only files. Without the flag nothing changes (`MIGRATION_BLOCKED_SECRET`). Symlinks and secret file *names* (`.env`,
`*.pem`, `*.key`, ...) keep blocking even with the flag. Another machine does not get these files from git: it migrates its own.

**Apply.** The critical section takes the migration lock of the project and the plan lock of every plan, recomputes the
digest of the source, copies into `.staging/` inside the workspace and checks every digest, loads each staged plan and
runs the plan check (a plan that was red before stays exactly as red; a new error stops the migration), renames the staging
folder into `projects/<code>/plans`, writes the marker `plans_store = workspace` and releases the locks. Afterwards the
module writes `local-only.json`, the report `migrations/<op_id>.json` and the binding. The source is not deleted. Before
the rename the workspace has no `plans/` for the project, and a failure there leaves nothing behind and the marker
unchanged. A failure after the rename is completed by repeating `apply`, which finds the copy with the same digest and only
writes the marker. A repeat of a finished migration changes nothing and reports `noop`.

**A planner that is writing during the migration.** A planner process that waits for the plan lock of the old folder gets
the lock only after the switch, sees the marker and fails with `PLANS_MIGRATED` ("rerun the command"); its rerun uses the
workspace. A write into the old folder after the switch is impossible.

**A second machine (import).** When `projects/<code>/plans` already exists in the workspace (it came with `git clone`), each
plan is compared by digest: equal gives `skipped-equal`, absent gives `copied`, different gives a conflict. `apply` refuses a
conflict with `MIGRATION_CONFLICT` until you choose `--on-conflict keep-workspace` (keep the workspace plan, skip the local
one) or `import-copy` (keep both; the local plan is stored as `<plan-id>~<device>`, the last 8 characters of the device id).
Nothing is overwritten silently. Legacy folders that differ are imported under `<name>~<device>` without a conflict.

**Rollback.** Possible while the workspace copy of every plan still equals the report and the old folder still has the digest
of the report; otherwise `MIGRATION_DIVERGED` lists what differs. It removes only what the migration put in.

**Cleanup.** Deletes an old folder only if its digest equals the copy in the workspace (the others are kept with a reason),
then removes `plans/` if it is empty. It runs no git command; when `plans/` was tracked it prints
`git -C <root> rm -r --cached plans && git commit ...`. `--confirm` must repeat the project code.

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

## Remote and a second machine

Needs git 2.38 or newer (`WORKSPACE_GIT_TOO_OLD` otherwise).

- `swissknifeman workspace connect --remote URL` looks at the remote first (`git ls-remote`, then a shallow clone in
  `.staging/connect-<id>` that is always removed). An empty remote or one holding this workspace becomes `origin`;
  a repository without `workspace.json` is `REMOTE_FOREIGN` and another workspace is `REMOTE_OTHER_WORKSPACE` (use
  `workspace clone`); the git configuration is not touched in these cases. `connect` never commits or pushes; it prints
  `next: swissknifeman workspace sync --push`.
- `swissknifeman workspace clone URL [--code CODE] [--root DIR]` makes a workspace from a remote: it is cloned beside the
  workspaces and moved to `workspaces/<code>`, the code read from the remote's `workspace.json` (`--code` must agree; a taken
  folder is `WORKSPACE_ROOT_NOT_EMPTY`). With `--root` it goes into an absent or empty folder
  (`WORKSPACE_ROOT_NOT_EMPTY` otherwise) and creates this machine's device if it has none. Then run
  `swissknifeman workspace project scan ~/projects`.
- `swissknifeman workspace status --fetch` fetches `origin` and shows ahead, behind and diverged against `origin/<branch>`.

Git never asks for a password here: an authentication or network failure is `REMOTE_UNREACHABLE`, with the URL shown
without user information.

## Two machines: the order

1. Machine A: `migrate apply` per project, commit the marker (`git add -f .swissknifeman/project.json`; most repositories
   ignore `.swissknifeman`), `workspace connect --remote URL`, `workspace sync --commit --push`, push the marker commits.
2. Machine B: update swissknifeman, `git pull` the checkouts (the marker arrives), `workspace clone URL`,
   `workspace project scan ~/projects`, `migrate plan` and `apply` in import mode (equal folders are skipped, new ones are
   copied, a conflict needs `--on-conflict keep-workspace|import-copy`), `workspace sync --commit --pull --push`.
   The step-by-step runbook for an agent on B is `MIGRATION-HOST-B.md` in the repository root.
3. Only after `migrate verify` is `equal` on both machines: `migrate cleanup --confirm <code>` and
   `git rm -r --cached plans` per repository. Files with secret-like content (`--local-only-secrets`) stay on the machine
   that held them; they are not in the workspace git.

## Sync between machines

`swissknifeman workspace sync [--commit] [--pull] [--push] [--resolve PATH=local|remote ...] [--resolve-reset] [--json]`
is the only way plans move between machines. It is manual: there is no background mode and no hook. Without a flag it
commits and pulls; `--push` also needs both, so it runs them first. Everything runs under the one `git.lock`.

1. **Commit.** The files that would enter the commit are judged by the publish-safety rules. A `block` (a secret, an absolute
   path in a manifest, a symlink, an unknown entry) is `PUBLISH_BLOCKED`: nothing is committed or pushed. Files that are too
   large are written to `local-only.json` and `.git/info/exclude` instead of git; a file git already tracks that became
   local-only is removed from the index (`git rm --cached`) in the sync commit, with a warning, and stays on disk. The execute
   bit is cleared in the index. The commit is `skm(plan): <plan-id> sync <N> files` when only one plan changed, else
   `skm(workspace): sync <N> files`; its body lists the projects and plans and it ends with `Workspace-Device: dev_…`.
2. **Pull.** `git fetch origin`, then a dry merge with `git merge-tree --write-tree` (git 2.38). A clean result is merged,
   fast-forward where possible. `log.jsonl` of a plan merges by the `union` driver, so two machines that only append to the
   journal never conflict. When a file changed on both sides nothing is merged and the working tree and `HEAD` stay as they
   were: the answer lists `conflicts[{path, project_id, plan, ref}]` (the `ref` is the document: `phases/P2/P2.3.json` is
   `P2.3`, `decisions/D4.json` is `D4`, `plan.json` is `plan`) and the exit is 1 with `WORKSPACE_CONFLICT`.
3. **Resolve.** Name the side for every conflicting path: `--resolve PATH=local` keeps this machine's file, `--resolve
   PATH=remote` takes the other machine's. It can be given in parts; the decisions wait in `sync.json` and the answer shows
   `{"resolution": {"decided": N, "remaining": [...]}}` until every path is decided. A path that is not in the last conflict
   report is `RESOLUTION_INCOMPLETE`. When all are decided, sync fetches again; if `origin/<branch>` or `HEAD` moved since the
   conflicts were found the decisions are dropped (`WORKSPACE_CONFLICT_STALE`) and you run `--pull` again. Otherwise it merges
   (`merge --no-commit`), takes the sides and commits `skm(workspace): merge origin/<branch> (resolved N)`; any error aborts
   the merge. `--resolve-reset` drops the decisions. `--resolve` replaces `--pull` and cannot be combined with it.
4. **Push.** `git push origin HEAD:<branch>`, never forced. The remote (without user information) and the branch are printed
   before the push. A remote that has news is `WORKSPACE_BEHIND`: run `sync --pull`, then push again.

`sync.json` and `audit.jsonl` in the machine state record the last commit, pull and push, the last result, the pending
conflicts and decisions, and one line per operation. Events: `workspace.sync.committed`, `.pulled`, `.conflict`, `.pushed`.

Two machines: on A `workspace init --code axioma`, `project attach` or `migrate apply`, `connect --remote URL`, `sync --push`; on B
`workspace clone URL`, `project scan ~/projects`, then `sync --push` on either side whenever its plans changed (the other
side runs `sync` to receive them). `scripts/e2e-workspace-sync.sh` runs this with two `SKM_HOME` and two workspaces on one bare
remote.

## Error codes

Workspace: `WORKSPACE_NOT_INITIALIZED`, `WORKSPACE_ROOT_NOT_EMPTY`, `WORKSPACE_LAYOUT_INVALID`, `WORKSPACE_GIT_LOCKED`,
`WORKSPACE_GIT_TOO_OLD`, `ATTACH_CONFIRM_REQUIRED`, `PROJECT_UNKNOWN`, `PROJECT_MARKER_MISSING` (link: no marker), `PLANS_LINKED`, `LINK_FAILED`, `LINKS_EXCLUDE_INVALID`, `PROJECT_AMBIGUOUS`, `PROJECT_MARKER_INVALID`,
`BINDING_MARKER_MISMATCH`, `BINDING_PATH_MISSING`, `REMOTE_UNREACHABLE`, `REMOTE_ALREADY_SET`, `REMOTE_FOREIGN`,
`REMOTE_OTHER_WORKSPACE`, `REMOTE_NOT_SET`, `PUBLISH_BLOCKED`.

Sync: `WORKSPACE_CONFLICT` (files changed on both sides), `RESOLUTION_INCOMPLETE` (a `--resolve` path is not in the last
conflict report, or there is none), `WORKSPACE_CONFLICT_STALE` (the remote or this workspace moved; decisions dropped),
`WORKSPACE_BEHIND` (push rejected: pull first), `WORKSPACE_MERGE_FAILED`, `WORKSPACE_MERGE_IN_PROGRESS` (an unfinished merge in
the workspace repository), `WORKSPACE_UNRELATED_HISTORIES` (this workspace and the remote share no commit),
`WORKSPACE_SYNC_FAILED` (a git step of the commit failed).

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
