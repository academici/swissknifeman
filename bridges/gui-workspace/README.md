# gui-workspace

Bridge between the GUI host (`gui`) and the portable workspace (`workspace`): overview, projects, migration, sync and
conflicts as GUI views, and the workspace actions as broker commands. It is a hub unit (`unit.json`, kind `bridge`,
requires `aicore`, `gui`, `workspace`) that contributes `gui.json` (`contribution/v1`) and answers queries through the
aicore plugin protocol (`extension.json`, point `gui:query`).

The bridge only runs `workspace ... --json` — `$SKM_WORKSPACE_MODULE_ROOT/bin/workspace`, else
`swissknifeman workspace` (`$SKM_UMBRELLA` or `PATH`) — and moves fields of its JSON into `view-data/v1`. It reads no
workspace file and imports no module. A URL with userinfo (`scheme://user@host`) in an answer is refused
(`WORKSPACE_REMOTE_LEAK`) even if the CLI failed to redact it.

| Query | Workspace command | View |
| --- | --- | --- |
| `gui-workspace.overview` | `status`, `doctor --publish-safety` | `metric-group`: projects, bound here, changed files, ahead/behind/diverged, remote connected, publish verdict |
| `gui-workspace.projects` | `project list`, `status` | `resource-list`: project, status, bound here, paths, plans store, plans |
| `gui-workspace.migration` | `migrate discover` | `status-table`: one row per checkout; a row with legacy plans offers `migrate-plan` |
| `gui-workspace.sync` | `status`, `doctor --publish-safety` | `status-table`: push target (redacted remote, branch, ahead/behind; offers `sync-push`), publish-safety findings, last operation |
| `gui-workspace.conflicts` | `status` (`last_sync`) | `resource-list`: path, project, plan, ref, decision made so far |

Widget `gui-workspace.summary` (`metric-group`, fleet) shows the overview query.

Pages: Overview, Projects, Migration, Sync, Conflicts. The contract asks for the navigation section `workspace`
(orders 10–50); the contribution schema of the GUI knows only `fleet`, `project`, `plan`, `settings`, `plugins`, so the
pages sit in `fleet` with orders 110–150 until the GUI adds the section.

## Commands

Declared only in `gui.json` as `exec.kind = argv` with the fixed argv `run.py <verb> <inputs>`; the frontend sends
field values, never argv. All values are strings or enums; `run.py` checks them (exit 2, nothing runs) and builds the
`workspace` argv as a list without a shell.

| Command | Inputs | Runs | Confirmation |
| --- | --- | --- | --- |
| `init` | - | `init` (the configured root) | risk-based |
| `project-attach` | `project` (absolute folder) | `project attach --project DIR` (no `--yes`: an existing project is never reused silently) | risk-based |
| `project-scan` | `dir` | `project scan DIR` | risk-based |
| `project-rebind` | `project_id`, `path` | `project rebind ID --path DIR` | risk-based |
| `migrate-plan` | `project`, `on_conflict`? | `migrate plan` (dry run) | none |
| `migrate-apply` | `project`, `on_conflict`? | `migrate apply --yes` (timeout 7200 s) | always |
| `migrate-verify` | `project` | `migrate verify` | none |
| `migrate-cleanup` | `project`, `confirm` | `migrate cleanup --confirm ID` | always |
| `sync-commit` / `sync-pull` | — | `sync --commit` / `sync --pull` | risk-based |
| `sync-push` | — | `sync --push` (no force) | always |
| `sync-resolve` | `path`, `side` (`local`/`remote`) | `sync --resolve PATH=side` | always |
| `sync-resolve-reset` | — | `sync --resolve-reset` | risk-based |
| `connect` | `remote`, `branch`? | `connect --remote URL [--branch]` | always |

- `migrate-cleanup`: `confirm` must equal the `project_id` bound to the folder (looked up through `project list`);
  checked in `run.py` before the CLI runs and again by the CLI.
- `sync-push`: `run.py` prints `pushing to <redacted remote> branch <branch>` (from `status`) before it hands over to
  the CLI, refuses a remote with userinfo and a workspace without a remote. The generic confirmation text of the GUI
  does not name the target; the page Sync shows it in the row `push-target`.
- `connect`: a URL with a password or token (any scheme), or any userinfo on `http(s)`, is refused.
- `sync-resolve`: `path` is relative, without `..`, `=` or a leading `-`.
- Commands stream and can be cancelled; `migrate-apply` and `migrate-cleanup` have `timeout_s` ≥ 3600.

## Tests

```bash
bash scripts/test.sh
```

Fixture tests use a fake workspace module (`tests/fixtures/module/bin/workspace`, canned JSON; switches `FAKE_*`
from the environment or `$HOME/fake.json`). One scenario (init → attach → overview/projects) runs the real CLI in a
throwaway `SKM_HOME` and `SKM_WORKSPACES_ROOT`; it is skipped when `SKM_WORKSPACE_MODULE_ROOT` is unset (the hub
script `scripts/test-bridges.sh` sets it). The GUI host and aicore come from `SKM_GUI_ROOT` and `AICORE_ROOT`, else
from `swissknifeman units list --json`.
