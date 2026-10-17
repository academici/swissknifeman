# Desktop shell

The desktop shell is a Tauri 2 application in `packages/gui/desktop/src-tauri`. It starts the Python sidecar
(`gui serve --sidecar`, see [api.md](api.md) § Desktop sidecar), keeps it alive and gives the webview a small,
restricted adapter to the sidecar API. The webview never talks to the loopback port itself and never sees the session
secret.

## Layout

| Path | Content |
|---|---|
| `desktop/src-tauri/Cargo.toml` | the app crate `skm-gui-app` (binary `skm-gui`) and the workspace member `core` |
| `core/` | `skm-gui-core`, no Tauri, only `serde`/`serde_json`: `adapter`, `ready`, `backoff` (delays and `Policy`), `batch` |
| `src/`, `build.rs` | the app: `main.rs` (builder, plugins, single instance, window events), `sidecar.rs` (supervisor), `commands.rs` (adapter); `icons/` (placeholder icons from `cargo tauri icon`; replace with the product icon) |
| `tauri.conf.json`, `capabilities/default.json` | configuration, checked structurally |
| `desktop/tests/vectors/*.json` | expected values of the core, the only source |
| `tests/desktop_oracle.py` | Python oracle of the core rules (test code, not in the product) |

## Adapter commands

| Command | Result |
|---|---|
| `api_request(method, path, body?)` | `{status, body}`; no headers |
| `api_subscribe(filter, channel)` | subscription id |
| `api_unsubscribe(id)` | — |
| `sidecar_status()` | `{state: starting\|ready\|restarting\|failed, port?, restarts, last_error?}` |
| `sidecar_restart()` | resets the restart policy and restarts |
| `sidecar_log(lines?)` | at most 200 lines of the sidecar log |

No command takes a URL, host, scheme or header. `adapter::validate` runs before anything is sent: methods `GET`,
`POST`, `PATCH` (`ADAPTER_METHOD`); the path starts with `/v1/`, is at most 2048 bytes of printable ASCII without
space, control characters, `\` and `#`, and has no `..` also after percent-decoding, and a malformed or decoding to
NUL, control or `\` percent sequence is refused (`ADAPTER_PATH`); body at most 1 048 576 bytes
(`ADAPTER_BODY_TOO_LARGE`). Rust sets `Authorization: Bearer <secret>`, `Origin: http://127.0.0.1:<port>` and
`Content-Type`. Redirects are not followed.

The secret (32 bytes from the OS generator, base64url) exists in the Rust process and in the sidecar stdin only. It is not
in `sidecar_status`; `sidecar_log` and `last_error` pass a filter that replaces its value by `[redacted]`.

## Subscriptions

`api_subscribe` opens one WebSocket to `/v1/events` per subscription and sends a `stream/v1` `subscribe` frame with the
given filter (`cursor` and `epoch` are `null`: a webview that wants a replay resubscribes and handles
`snapshot_required`). Frames reach the `Channel` in batches: a JSON array of frames, at most 50 frames or 50 ms; the
queue holds 1000 frames and the oldest are dropped on overflow, reported as a first element `{"dropped": N}`. When the
socket ends, the last message is `[{"closed": true}]`. The task stops when `Channel.send` fails, on `api_unsubscribe`
and when a window is destroyed.

## Supervisor

Spawn through the shell plugin from the resource tree (`<resource_dir>/gui-backend/gui-backend`), one handshake line on stdin, READY within 20 s
(`READY_INVALID` or a timeout kills it), health check `GET /v1/bootstrap` with Bearer every 10 s (three failures kill
it). An exit restarts with the delays 0.5, 1, 2, 4, 8, 16, then 30 s; 60 s of stable work resets the counter; more than
5 exits within 300 s make the state `failed` until `sidecar_restart`. On exit of the shell the sidecar gets SIGTERM
(15 s), then kill. The shell plugin cannot close the child stdin, so the "close stdin first" step of the protocol is
replaced by SIGTERM; the sidecar treats both the same way.

## Terminal

The terminal is not supported in desktop mode in version 1 (decision D30). The adapter forwards only `GET /v1/events`
subscriptions and never opens a WebSocket for `/v1/terminal/{id}/io`; the sidecar does not announce the bootstrap
feature `terminal` and answers `POST /v1/terminal/sessions` with `PERMISSION_DENIED` (`details.reason:
terminal_unsupported`). The terminal works in browser mode (`gui open`) when the owner enables `[gui.terminal]`.

## Configuration

`tauri.conf.json`: `withGlobalTauri: true`, CSP `default-src 'self'; script-src 'self'; style-src 'self'; connect-src
ipc: http://ipc.localhost; img-src 'self' data:`, `frontendDist: ../../frontend/dist`, one local window `main`,
no `bundle.externalBin`, deep link scheme `skm-gui` (the handler only brings the window forward).
`capabilities/default.json` lists the window `main` and exactly the permissions of the allowlist in
`tests/test_desktop_config.py`: `core:app|event|window:default`, the six `allow-*` permissions of the commands (generated
from `build.rs`), `updater:default`,
`dialog:allow-open`, `deep-link:default`. No `fs:`, `http:`, `process:` and no `shell:allow-execute`. The single-instance
plugin has no permissions. Bundle: `targets: ["appimage","deb","app"]`, `createUpdaterArtifacts: true`, `resources` copies the sidecar onedir tree
`binaries/gui-backend-onedir/` to `gui-backend/`, and `plugins.updater` holds the public key of the updater and the placeholder endpoint
`https://updates.invalid/...` that the owner replaces (`desktop/scripts/check-release-config.py --release` fails while
it stays). The updater plugin is registered in `src/main.rs`. Release steps: `docs/desktop-release.md`.

## Checked and not checked

Checked by Python tests (`test_desktop_vectors.py`, `test_desktop_config.py`): the rules of the core through the oracle
over the vectors, the structure of the configuration, and a static reading of the commands.

Checked on the owner's machine (Ubuntu 24.04, Rust 1.99, Tauri CLI 2.12, PyInstaller 6.22, first build, 2026-10-17):
`cargo test -p skm-gui-core` (vectors, 5 tests); the PyInstaller onedir build of the sidecar and its handshake, `GUI_READY`
in about 1 s and `GET /v1/bootstrap` with the Bearer secret (`desktop/scripts/smoke.sh`); `cargo tauri build` produces the
AppImage and the deb with signed updater artifacts; the AppImage starts, the shell starts the sidecar from the resource
directory (`gui-backend/gui-backend`), the web view renders the application through `TauriTransport` under the production CSP
(Dashboard, Plugins, the fleet widget with real data), the sidecar answers 401 without the secret, and no `gui-backend`
or `skm-gui` process is left after the window is closed.

Findings of that first build (fixed in the repository): the crate and `tauri.conf.json` now share the folder `src-tauri` (the
CLI looks for the config next to the crate), `icons/` are required, the PyInstaller spec found `aicore` by a wrong path, the
AppImage rewrites ELF files so the sidecar digest covers ELF files by name only (`gui.sidecar_digest`), the AppImage puts
`PYTHONHOME`, `PYTHONPATH` and `LD_LIBRARY_PATH` into the environment and the sidecar removes them before it starts the hub
umbrella (`gui.sidecar.scrub_environment`), and `rust-ini` is pinned to 0.21.1 in `Cargo.lock` because 0.21.3 breaks
`tauri-plugin-deep-link` 2.6.2.

**Not checked:** installing the `.deb`, the update flow with a real https endpoint and a wrong signature, macOS, the
behaviour of the supervisor after a crash of the sidecar (restart with backoff) and of the diagnostics screen in the real
web view, closing the window while a run is active, and the stability of `Cargo.lock` against newer crate versions.
