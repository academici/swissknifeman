# Browser mode

The GUI in a browser on this machine: `gui serve` runs the loopback backend, `gui open` hands the browser a one-time
URL. The desktop shell (later) uses the same backend and frontend.

## Install and start

```bash
swissknifeman install --profile full    # or: bash packages/gui/install.sh
gui open                                # the GUI of the current project in the default browser
```

`install.sh` links `gui` into `~/.local/bin`, installs the locked Python packages of the backend (`gui deps
ensure`: `requirements.lock`, sha256-checked wheels, no virtual environment, needs network once) and builds the
frontend when `npm` is there (Node 22.22+). Without npm the backend still installs; build the frontend later with
`npm --prefix packages/gui/frontend ci && npm --prefix packages/gui/frontend run build`.

`gui open [--project DIR] [--no-browser]` reuses a running backend or starts `gui serve` in the background (its
output goes to `state_dir("gui")/backend.log`), registers the project (`--project`, else the current one when it has
`.swissknifeman/`) and prints `GUI_URL http://127.0.0.1:<port>/?t=<token>`; the browser opens it unless
`--no-browser` or `[gui] open_browser = false`. `gui serve [--port N] [--project DIR] [--no-browser]` runs the backend
in the foreground; SIGINT or SIGTERM stops it (active runs are cancelled with their process groups).

## What the browser can do

The dashboard shows the fleet widgets of the contributions (the hub: `gui-hub`), `/projects` the trusted projects
(adding one asks for a confirmation), project pages the project widgets and routes, contribution routes their views
and actions, `/runs` the command runs with their live logs and Cancel, `/catalog` the accepted and rejected
contributions. Commands run only from their descriptors: the browser sends typed values, the backend builds the argv,
runs it in the project or owner folder with a clean environment, streams the redacted log and keeps an audit
([api.md](api.md#commands-and-runs-run-apiv1)).

## Security in short

The backend listens on `127.0.0.1` only and checks `Host` and `Origin` on every request; the session secret
(256 bits) never reaches the browser, which signs in once with the URL token and then holds an `HttpOnly`,
`SameSite=Strict` cookie; requests that change state need `Origin` and JSON; there is no CORS; responses carry a
strict CSP. Details: [api.md](api.md#authentication-and-transport-security).

## Configuration

`[gui]` in the SKM configuration (`swissknifeman config explain gui`): `port` (0: free port; machine-wide),
`open_browser`, `runs.*` (concurrency, log size, idle timeout, cancel grace), `events.*` (replay ring, queues,
heartbeat), `retention.*` (run logs), `query.max_output_bytes`.

## Troubleshooting

| Code | Meaning | Do |
| --- | --- | --- |
| `GUI_DEPS_UNAVAILABLE` | the locked Python packages are not installed and could not be | `gui deps ensure` with network once |
| `BACKEND_RUNNING` | another `gui serve` holds the backend lock | `gui open` reuses it |
| `BACKEND_START_FAILED` | the background backend did not answer in 10 s | read the tail it prints from `backend.log` |
| `FRONTEND_NOT_BUILT` | `frontend/dist` is missing | `npm --prefix packages/gui/frontend ci && npm --prefix packages/gui/frontend run build` |
| `PROTOCOL_INCOMPATIBLE` | the frontend and the backend come from different versions | rebuild the frontend from the same checkout |
| `PYTHON_TOO_OLD` | gui needs Python 3.11+ | use a newer `python3` |

## Tests of this mode

`npm --prefix packages/gui/frontend run e2e` drives Chromium (Playwright; `npx playwright install chromium` once)
against a backend in a throwaway `SKM_HOME` with the fixture units of `tests/fixtures/units/e2e`: sign-in by the
one-time URL and its refusal on reuse, a command as dry run and for real with its log, cancel of a long command with
no process of its group left, and a dropped event stream that resumes without lost or repeated log chunks.
`bash packages/gui/scripts/smoke.sh` starts the backend against the real hub units and reads the handshake, the
catalog (with `gui-hub`) and the query `gui-hub.units`; it runs no command.
