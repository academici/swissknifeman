# workspace-planner

Bridge between the portable **workspace** and the **planner**. It fills the extension point `workspace:plans-migrator` of
the workspace module (`provides.ports` of `unit.json`): the one place that knows the `PlanLock` of the planner and the
layout of the workspace at the same time (PLAN6 decision D6, contract `workspace-contract#migration`).

The workspace module never imports this code. It calls the plugin `workspace-planner` through `aicore.ext.plugins`
(`timeout_seconds` 3600, a large project takes minutes; `limits.max_stdout_bytes` 32 MiB, because the manifest of digests of a project with thousands of plan files exceeds the default 1 MiB); the request and the answer follow the contract
`urn:swissknifeman:workspace:plans-migrator` (`schemas/plans-migrator/v1` of the workspace module).

| `op` | What it does |
| --- | --- |
| `inspect` | Classifies `<project_root>/plans` and answers a manifest: `plans[]` (`name`, `class` `v4` / `legacy`, `files[] {path, bytes, sha256}`, `bytes`, `digest`, `in_progress[]`), `top_level[]`, `symlinks[]`, `derived_skipped`, `digest`. Reads and hashes, writes nothing. |
| `apply` | The critical section of the migration (below). Answers `result` `applied` / `noop`, or `refused` with `code`, `message` and the `phase` it stopped at. |
| `verify` | Loads the plan folders of `plans_root` through the planner store and answers, per plan, `loaded`, `problems` and the `check` errors as `(code, where)`; with `compare_to` (a baseline folder) also `new_errors`, and `ok` is false when there is one. |

## Classes

- **v4** — a folder with `plan.json` whose `$schema` is `urn:swissknifeman:task:plan:plan:v1`, in `plans/` or `plans/archive/`.
  `views/`, `context/` and `.lock` of the plan folder are derived and are not part of the manifest.
- **legacy** — every other folder of `plans/` or `plans/archive/`; copied byte for byte, opaque to the planner.
- **top level** — loose files of `plans/` (and `plans/archive/`); they go to `legacy-plans/_root/<same relative path>`.
- `__pycache__` and `.DS_Store` are left out everywhere. A symlink (or a socket, a device) is never followed or copied: it is
  listed in `symlinks` and `apply` refuses with `MIGRATION_BLOCKED_SYMLINK` before it copies anything.

A folder name is its path relative to `plans/` (`archive/<id>` for an archived plan). The digest of a folder is
`sha256:` over the sorted `(path relative to the folder, sha256)` pairs, so the same plan has the same digest in the checkout
and in the workspace; the digest of the manifest covers the names, classes and digests of the folders and the loose files.

## The critical section (`apply`)

Input: `project_root`, `workspace_root`, `project_id`, `op_id`, the `manifest` of a dry run, `mode` (`initial` | `import`),
`on_conflict` (`null` | `keep-workspace` | `import-copy`), `device_short`, `lock_timeout_s` (default 30).

1. **lock** — `flock` on `<workspace state>/migrate-<project_id>.lock` (a second migration of the project:
   `MIGRATION_LOCKED`), then the `PlanLock` of every v4 plan of the manifest in the order of the sorted folder paths. A plan held
   for longer than `lock_timeout_s` gives `MIGRATION_LOCKED` with `locked: [plan]`; the locks already taken are released in
   reverse order.
2. **digest** — the source is scanned again under the locks; a different digest is `MIGRATION_SOURCE_CHANGED` with
   `changed: [folders]` (run the dry run again).
3. **plan** — per folder the workspace copy decides the `action`: absent → `copied`; equal digest → `skipped-equal`; different →
   a plan needs `on_conflict` (`MIGRATION_CONFLICT` with `conflicts[]` otherwise), `keep-workspace` → `kept-workspace`,
   `import-copy` → `imported-copy` as `<name>~<device_short>` (`stored_as`). An opaque legacy folder that differs always goes next
   to the existing one as `<name>~<device_short>` unless `keep-workspace` is chosen (contract step 6).
4. **copy** — the folders to move are copied with `shutil.copy2` (nothing is dereferenced) into
   `<workspace>/.staging/<op_id>` — inside the workspace, so the rename stays on one volume — and the digest of every copy is
   compared with the manifest (`MIGRATION_COPY_MISMATCH`).
5. **verify** — every staged v4 plan is loaded by the planner store and `check` is run on it (without a checkout: the planner skips the
   existence of repository paths); an error the source plan does not have is `MIGRATION_VERIFY_FAILED` with `plans[]`.
6. **rename** — `os.rename` of the whole `plans` folder when the workspace has none (or an empty one), otherwise one folder at a time into
   absent targets; the digest of what arrived is compared again (W4). A failed move is `MIGRATION_TRANSFER_FAILED`.
7. **marker** — `plans_store = workspace` is written atomically (`aicore.workspace.write_marker`) while every lock is still held;
   a writer that waited for a `PlanLock` then gets `PLANS_MIGRATED` (W3). The marker names `project_id`; a marker of another
   project is `PROJECT_MARKER_MISMATCH`.
8. The locks are released, the staging folder is removed.

Any failure before the rename removes the staging folder of this call and leaves the marker as it was. A repeat of the same
manifest after a rename that was not followed by the marker finds the folders with equal digests (`skipped-equal`) and only writes
the marker; with the marker already at `workspace` and every copy equal the answer is `noop`. The source is never deleted.

`PlanLock` creates an empty `.lock` file in a plan folder that has none; `.lock` is a derived file and is not copied.

## Environment

| Variable | Use |
| --- | --- |
| `PLANNER_ROOT` / `PLANNER_PLAN_PY`, then a `planner` command | the planner library (`planner.plan.store`, `planner.plan.check`) |
| `SKM_WORKSPACE_MODULE_ROOT`, then a `swissknifeman` command | where the workspace module is (tests read its contract schemas) |
| `AICORE_ROOT`, `_vendor/aicore`, the hub foundation | the foundation library (locations, the project marker) |
| `SKM_HOME`, `SKM_WORKSPACE_ROOT` | the machine state (migration lock) and the workspace root, as for every aicore location |
| `SKM_MIGRATOR_FAIL_AT` | tests only: `copy`, `pre-rename` or `post-rename` raises an error at that point |

Progress goes to stderr (`workspace-planner: scanned N files`, `copied N files`). The bridge prints no file content and no
secret: answers hold paths relative to `plans/`, sizes and digests.

## Files

`migrator.py` (the plugin: `describe`, `invoke`), `inspector.py` (`inspect` and the walk and digest rules the other parts share —
not named `inspect.py`, which would hide the standard library module from every script started in this folder), `apply.py`,
`verify.py`, `partners.py` (finding the partners), `extension.json`, `tests/` (`bash scripts/test.sh`).
