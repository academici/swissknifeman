# ADR 0085: Portable workspace: plans leave the project repository and live in one git root of their own

## Status

Accepted

## Context

Plans (`plans/<plan-id>/…`, layout v4) are committed in the repository of their project. On the first machine they take
1.8 GB (3755 files with home paths in their data, 307 files above 1 MiB, the largest 76 MB), travel with product commits,
and a second machine sees only what was pushed with the product. Every reader of plans (planner, orch, harness, analyst,
GUI) would compute a second location on its own (audit finding A10).

## Decision

- **D2 Places.** `workspace_root()` is `SKM_WORKSPACE_ROOT` (absolute, else `ValueError` like `SKM_HOME`) or
  `data_dir()/workspace`; machine files (bindings, device, sync state, audit, locks) are in `workspace_state_dir()` =
  `state_dir("workspace")`. Git exists only in `workspace_root()`. Both functions create nothing.
- **D3 Identity.** The project is the `project_id` of the committed marker `<root>/.swissknifeman/project.json`
  (`{project_id, plans_store}`); run-time resolution reads only that file. Remotes serve `workspace project attach`
  to find an existing project; a path or basename is never an identity.
- **D4 One switch.** `plans_store` (`legacy` or `workspace`) names the single store; it changes only inside the
  migration critical section under the plan lock of every plan, and a legacy plan lock then reports `PLANS_MIGRATED`
  (no dual-write; invariants W1–W5 of the contract).
- **D5–D7 Layout, modules, commits.** Layout v4 stays and moves as it is to `projects/<project_id>/plans/`. aicore owns
  the places, seven contracts (`workspace`, `workspace-project`, `project-marker`, `workspace-bindings`,
  `workspace-device`, `workspace-local-only`, `workspace-migration`), the resolver `aicore.workspace` and the shared
  vectors `schemas/workspace/v1/resolution-vectors.json`; the module `workspace` owns the commands; the planner keeps a
  stdlib copy of the resolver that passes the same vectors (changed together); the migration critical section is a
  bridge. A piece yields a product commit and a separate local plan commit in the workspace under the git lock.
- **D8 Publish safety.** Secrets, absolute paths in portable manifests, symlinks and unknown roots block; home paths in
  plan data and executable bits warn; files above 5 MiB or binaries above 1 MiB are local-only (`local-only.json`).
- **D10, D13.** The execution input built by the bridge keeps plan reads available to the executor; migration on a second
  machine is an import that merges by digest.
- **Portable documents hold no absolute path** (W8): schemas reject path fields, the validator rejects any string that
  starts with `/`, `~` or `X:\`. Bindings (absolute paths) are a machine file, written under `flock` and replaced atomically.

## Alternatives considered

- Remote matching at run time: rejected, it breaks on renames and forks; the marker travels with `git pull`.
- Reshaping layout v4: rejected, it already stores every document as a file. Curated artifacts only: rejected, they are evidence.
- Writing both stores during a migration: rejected, it loses the write of a process that resolved the old store.

## Consequences

- One rule tells every reader where plans live; the vectors fail a copy that drifts from it.
- A plan without a bound checkout (`source_root` is `None`) can be read and edited but not run (`PLAN_SOURCE_UNBOUND`).
- Deferred: background sync, per-device journal, merge UI, cross-machine run claims, selective sync (recorded in the workspace audit of 2026-10, no longer kept as a file).

## Amendment 2026-10-18: workspaces and codes

A machine holds several workspaces, each a git repository in `workspaces/<code>/`. A workspace and a project are named by a
code (the folder name), not by a generated id: the marker is `{workspace, project_id, plans_store}` and the plans of a project
are `workspaces/<workspace>/projects/<project_id>/plans`. `workspace.json` gets `code` and layout 2. Machine files move to
`state/workspaces/<code>/` (the device file is shared). `SKM_WORKSPACES_ROOT` (the folder) and `SKM_WORKSPACE` (the choice)
replace `SKM_WORKSPACE_ROOT`. `project doctor` checks the wiring of a checkout (`project.workspace`). The migration of a
machine that used layout 1 is done once by hand.

## Amendment 2026-10-18: machine home and project layer (PLAN7)

- **One machine home.** The machine keeps `config/`, `state/`, `cache/` and `workspaces/` below `SKM_HOME` (default
  `~/.local/share/swissknifeman`); the `XDG_*` variables no longer move it. A machine with the old XDG folders uses each of them
  until `config migrate-home` moves it; a set `SKM_HOME` marks a sandbox and switches that lookup off. This amends D2: the
  places of `aicore.state` are `<home>/…`, and `workspaces_root()` is `<home>/workspaces`.
- **Project layer in the workspace.** The config, state, backups and stubs of a project on a machine are
  `workspaces/<workspace>/projects/<code>/local/` (contract `project-local-config/v1`, `repo.path` absolute because it is a machine
  document). `local/` is never tracked: the tracking policy of the workspace repository names it in the ignore list, so another
  machine builds its own. Resolution goes through the marker; a checkout without a marker, or whose project folder is not on the
  machine, keeps `.swissknifeman/` as before. This amends D3: the marker still decides identity, and now also where the project
  layer is.
- **Launcher-only checkout.** A checkout holds the launcher, its lock and the marker, nothing else of Swiss Knife Man.
  `project init --project CODE` writes the marker, `project migrate` moves an older checkout's project layer into `local/`
  without overwriting (a differing file is `PROJECT_MIGRATE_CONFLICT`, both copies stay), `project doctor` reports `project.local`
  and `project.checkout-layer`.
- **Optional links.** `plans/` and `tasks/` of a checkout may be symbolic links into the project folder of the workspace
  (`workspace project link|unlink`, setting `workspace.link_folders`, off by default). They are listed in the checkout's
  `.git/info/exclude`, a real folder is never replaced, and the plans stay in the workspace. This does not reopen D4: the marker
  stays the single switch.
- **Environment.** `SKM_HOME`, `SKM_WORKSPACES` and `SKM_WORKSPACE` are exported from the shell profile by the installers
  (`aicore shell-env`, one table in `aicore.state.envtable`), so a project and the agent's shell see the same machine; the launcher
  passes them on and invents none.
- **Second machine.** The runbook `MIGRATION-HOST-B.md` runs `config migrate-home` and `shell-env install` before the clone and
  `project migrate` after the plans are replaced; `local/` of machine A never arrives on B.

## Supersedes

None.
