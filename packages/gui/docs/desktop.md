# Desktop shell

The desktop shell is a Tauri 2 application in `packages/gui/desktop/src-tauri`. It starts the Python sidecar
(`gui serve --sidecar`, see [api.md](api.md) § Desktop sidecar), keeps it alive and gives the webview a small,
restricted adapter to the sidecar API. The webview never talks to the loopback port itself and never sees the session
secret.

## Layout

| Path | Content |
|---|---|
| `desktop/src-tauri/Cargo.toml` | workspace: `core`, `app` |
| `core/` | `skm-gui-core`, no Tauri, only `serde`/`serde_json`: `adapter`, `ready`, `backoff` (delays and `Policy`), `batch` |
| `app/` | `skm-gui-app` (binary `skm-gui`): `main.rs` (builder, plugins, single instance, window events), `sidecar.rs` (supervisor), `commands.rs` (adapter) |
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

Spawn through the shell plugin (`sidecar("gui-backend")`), one handshake line on stdin, READY within 20 s
(`READY_INVALID` or a timeout kills it), health check `GET /v1/bootstrap` with Bearer every 10 s (three failures kill
it). An exit restarts with the delays 0.5, 1, 2, 4, 8, 16, then 30 s; 60 s of stable work resets the counter; more than
5 exits within 300 s make the state `failed` until `sidecar_restart`. On exit of the shell the sidecar gets SIGTERM
(15 s), then kill. The shell plugin cannot close the child stdin, so the "close stdin first" step of the protocol is
replaced by SIGTERM; the sidecar treats both the same way.

## Configuration

`tauri.conf.json`: `withGlobalTauri: true`, CSP `default-src 'self'; script-src 'self'; style-src 'self'; connect-src
ipc: http://ipc.localhost; img-src 'self' data:`, `frontendDist: ../../frontend/dist`, one local window `main`,
`bundle.externalBin: ["binaries/gui-backend"]`, deep link scheme `skm-gui` (the handler only brings the window forward).
`capabilities/default.json` lists the window `main` and exactly the permissions of the allowlist in
`tests/test_desktop_config.py`: `core:app|event|window:default`, the six `allow-*` permissions of the commands (generated
from `app/build.rs`), `shell:allow-spawn` scoped to the sidecar `binaries/gui-backend`, `updater:default`,
`dialog:allow-open`, `deep-link:default`. No `fs:`, `http:`, `process:` and no `shell:allow-execute`. The single-instance
plugin has no permissions. Bundle: `targets: ["appimage","deb","app"]`, `createUpdaterArtifacts: true`, `resources` copies the sidecar onedir tree
`binaries/gui-backend-onedir/` to `gui-backend/`, and `plugins.updater` holds the placeholders `OWNER_PUBKEY_REQUIRED` and
`https://updates.invalid/...` that the owner replaces (`desktop/scripts/check-release-config.py --release` fails while
they stay). The updater plugin is registered in `app/src/main.rs`. Release steps: `docs/desktop-release.md`.

## Checked and not checked

Checked by Python tests (`test_desktop_vectors.py`, `test_desktop_config.py`): the rules of the core through the oracle
over the vectors, the structure of the configuration, and a static reading of the commands. **Not checked** (no Rust
toolchain on the development machine, decision D26): that any Rust file compiles, that `core/tests/vectors.rs` passes,
the behaviour of the supervisor and the adapter at run time, the crate versions (chosen by major; `Cargo.lock` is not
committed), the build-script options `capabilities_path_pattern` and `app_manifest` with the config in `src-tauri`
while the crate lives in `src-tauri/app`, and the shell plugin sidecar resolution of a PyInstaller onedir tree. The
owner runs `cargo test -p skm-gui-core` and the first `cargo tauri build` (see `docs/desktop-release.md`). `test_desktop_release.py` covers the release scripts (`check-release-config.py`,
`make-update-json.py`, `smoke.sh`) on fake files.
