# gui — SKM GUI control plane

`gui` is the local control plane of Swiss Knife Man: one frontend build that runs as a desktop application (Tauri 2
shell) and in a browser on loopback, backed by one Python process that is the only authority. It shows the fleet and
the control surface, edits configuration with provenance and safe writes, presents plans in human form with typed
domain mutations, runs allowlisted commands (dry-run, confirmation, log stream, cancellation, audit) and keeps a plugin
catalog with isolation and quarantine.

Status: `development`, version 0.1.0: the frozen v1 contracts, the contribution resolver and the commands
`contributions` and `check`; the local API, the frontend and the desktop shell come next.

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

In 0.1.0 the contracts (`schemas/`), `lib/gui/contracts.py`, `lib/gui/errors.py`, `lib/gui/core/run_states.py`,
`lib/gui/catalog/` and the CLI exist; HTTP, storage, frontend, desktop and sidecar are the target layout.

`gui` is a tool module of the hub (`standalone.tools`): its third-party dependencies, Node and Rust are not part of the
core check; it is checked by its own `dev.test`.

## Requirements

- Python 3.11 or newer (the hub itself runs on 3.9; an older interpreter gets `PYTHON_TOO_OLD`).
- The `aicore` foundation, found by the aicore locator (`$AICORE_ROOT`, `_vendor/aicore` or the sibling folder).

## Command line

```text
gui contributions [--json] [--project DIR]   resolved catalog of GUI contributions (catalog/v1)
gui check PATH [--json]                      check one contribution: its rules and the conformance of its handler
gui --version                                print the version
gui --help                                   show the commands
```

Units come from `SKM_UNITS_PATH` or `swissknifeman units list --json`; see [docs/contribution.md](docs/contribution.md).

Exit codes: 0 ok, 1 failure (code on stderr), 2 usage error.

## Tests

```bash
bash scripts/test.sh        # from packages/gui
```
