# gui — SKM GUI control plane

`gui` is the local control plane of Swiss Knife Man: one frontend build that runs as a desktop application (Tauri 2
shell) and in a browser on loopback, backed by one Python process that is the only authority. It shows the fleet and
the control surface, edits configuration with provenance and safe writes, presents plans in human form with typed
domain mutations, runs allowlisted commands (dry-run, confirmation, log stream, cancellation, audit) and keeps a plugin
catalog with isolation and quarantine.

Status: `development`, version 0.1.0: the frozen v1 contracts, the contribution resolver, the loopback backend
(`gui serve` / `gui open`: projects, queries, command runs, the event stream, browser session), the browser frontend and the commands
`contributions`, `check` and `schemas bundle`, the Tauri 2 desktop shell (`desktop/`) and the PyInstaller sidecar
(`sidecar/`).

## Principles

- Canonical SKM files (plans, configuration, manifests) are the source of truth; the GUI state is a rebuildable index.
- The UI never writes files and never builds commands: it sends typed requests; the backend builds the argv from a
  registered descriptor.
- Domains (hub, planner, orch) are reached only through bridges `bridges/gui-<module>` and the aicore plugin protocol;
  `gui` imports nothing but its own `lib/gui/` and `aicore`.
- The backend listens on loopback only and authenticates every request with a session secret.

The decisions are recorded in the hub decision records 0080–0084 (see `docs/architecture.md`).

## Layout

```text
packages/gui/                      # module: kind capability, destination own-repo, requires aicore ^0.1
  unit.json                        # provides: cli bin/gui, contracts, extension_points [query, command]
  bin/gui                          # CLI: contributions, check, serve, open
  lib/gui/__init__.py              # __version__, MIN_PYTHON = (3, 11)
  lib/gui/cli.py                   # command line
  lib/gui/contracts.py             # loading of the gui contracts (with the aicore foundation)
  lib/gui/catalog/                 # discovery and resolver of contributions (stdlib)
  lib/gui/core/                    # projects, broker, runs, events, config transactions, plugins, trust (stdlib + aicore)
  lib/gui/http/                    # Starlette app and security middleware: the only place that imports third-party packages
  lib/gui/storage/                 # sqlite3 and migrations
  schemas/<contract>/v1/           # contracts urn:swissknifeman:gui:<contract>:v1
  requirements.lock                # pip --require-hashes, only for lib/gui/http and the API tests
  frontend/                        # npm workspace: React, TypeScript, Vite
  desktop/src-tauri/               # Tauri 2 shell
  sidecar/                         # PyInstaller onedir spec of the backend
  tests/                           # Python unittest; frontend tests live in frontend/
  docs/
bridges/gui-hub/                   # fleet, project, units, doctor, status
bridges/gui-planner/               # plans
bridges/gui-orch/                  # conductor runs
```

In 0.1.0 the contracts (`schemas/`), `lib/gui/contracts.py`, `lib/gui/errors.py`, `lib/gui/core/` (run states,
project registry), `lib/gui/catalog/`, `lib/gui/storage/` (`gui.db`), `lib/gui/settings.py`, `lib/gui/deps.py`, `lib/gui/backend.py`,
`lib/gui/http/`, `frontend/`, `desktop/` (Tauri 2 shell), `sidecar/` (PyInstaller onedir spec of the backend) and the CLI exist.

`gui` is a tool module of the hub (`standalone.tools`): its third-party dependencies, Node and Rust are not part of the
core check; it is checked by its own `dev.test`.

## Requirements

- Python 3.11 or newer (the hub floor, `aicore.MIN_PYTHON`; an older interpreter gets `PYTHON_TOO_OLD`).
- The `aicore` foundation, found by the aicore locator (`$AICORE_ROOT`, `_vendor/aicore` or the sibling folder).

## Browser mode

`swissknifeman install --profile full` (or `bash install.sh`) links `gui`, installs the locked backend packages and
builds the frontend when npm is present; `gui open` opens the GUI. Start, security, configuration and the error
codes of this mode: [docs/browser-mode.md](docs/browser-mode.md).

## Workspace

With the bridge `bridges/gui-workspace` (portable workspace of ADR 0085) the section Fleet gets the pages Overview,
Projects, Migration, Sync and Conflicts of the workspace. The page Projects of the GUI itself asks the query
`gui-workspace.projects`: a trusted project shows its workspace `project_id`, its binding on this machine and its plans store, and
a project that is bound in the workspace but not trusted is listed with a Trust button. Trust stays an explicit act: the button
calls the existing `POST /v1/projects` and the owner confirms the dialog; nothing is added automatically. Without the bridge (or
without a workspace) the page is the plain list of trusted projects. The bridge also contributes the forms to create a workspace (alone or bound to an empty remote), connect a remote, add a project, bind a checkout and remove an empty project; the host renders them from the command inputs. The end-to-end scenarios are `frontend/e2e/workspace.spec.ts`.

## Third-party packages

The HTTP backend needs Starlette and uvicorn (with `wsproto` for WebSocket); they are pinned with their sha256 in
`requirements.lock` (pure-Python `py3-none-any` wheels only) and imported only by `lib/gui/http`. `gui deps ensure`
installs them once into `<cache>/gui/pydeps/py<major><minor>-<lock digest>` (`$GUI_PYDEPS_DIR` overrides the folder):
with `pip --require-hashes --target` when pip works, else by itself from the PyPI JSON API, checking each wheel's
sha256 and refusing archive members that could leave the folder. No virtual environment and no system change is
needed; a failure is `GUI_DEPS_UNAVAILABLE`.

## Configuration

`[gui]` in the SKM configuration files (`configs/config.schema.json`, resolved by `aicore.config`): `port` (0: a free
port; machine-wide), `open_browser`, `runs.*` (concurrency, log and timeout limits), `events.*` (stream buffers and
heartbeat), `retention.*` (run logs) and `query.max_output_bytes`. There is no host key: the backend binds loopback
only. `swissknifeman config explain gui` shows where each value comes from.

## State

`state_dir("gui")/gui.db` (SQLite, WAL, `0600`) holds the registry of trusted projects, preferences and the audit
trail; migrations only get appended and a database from a newer gui is refused with `STATE_INCOMPATIBLE`.

## Command line

```text
gui deps ensure [--json] [--offline]         install the locked third-party packages of the backend once
gui deps path                                print their install folder
gui schemas bundle --out DIR                 each contract as one self-contained JSON Schema (for type generators)
gui serve [--port N] [--project DIR] [--no-browser]
                                             run the loopback backend and print a one-time URL (GUI_URL ...)
gui open [--project DIR] [--no-browser]      open the GUI: reuse the running backend or start one detached
gui contributions [--json] [--project DIR]   resolved catalog of GUI contributions (catalog/v1)
gui check PATH [--json]                      check one contribution: its rules and the conformance of its handler
gui --version                                print the version
gui --help                                   show the commands
```

Units come from `SKM_UNITS_PATH` or `swissknifeman units list --json`; see [docs/contribution.md](docs/contribution.md).

Exit codes: 0 ok, 1 failure (code on stderr: `BACKEND_RUNNING`, `BACKEND_START_FAILED`, `GUI_DEPS_UNAVAILABLE`, ...),
2 usage error. The project of `serve`/`open` is `--project DIR`, else the current project when it has
`.swissknifeman/`; adding it makes it trusted. The local API and its security are described in
[docs/api.md](docs/api.md).

## Frontend

`frontend/` (React, TypeScript, Vite) is built with `npm --prefix packages/gui/frontend ci && npm --prefix
packages/gui/frontend run build`; `gui serve` serves `frontend/dist`. Its transport, pages, host views, contract types
and rules are in [docs/frontend.md](docs/frontend.md).

## Tests

```bash
bash scripts/test.sh                       # from packages/gui: Python tests
npm --prefix frontend run check            # frontend: generated types, tsc, eslint, vitest
npm --prefix frontend run e2e              # browser mode end to end (Playwright, Chromium)
bash scripts/smoke.sh                      # read-only smoke against the real hub
```

`scripts/test.sh` runs `gui deps ensure` against the real cache before it switches `HOME` to a throwaway folder and
exports `GUI_PYDEPS_DIR`, so the API tests import the locked packages; offline without a filled cache it fails with
`GUI_DEPS_UNAVAILABLE` instead of skipping tests. The installer tests use a local fake index and never the network.
