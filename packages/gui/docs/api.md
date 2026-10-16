# Local API contracts

The contracts of the gui local API, frozen before the API itself exists (the HTTP server arrives later). Each is a
JSON Schema under `schemas/<contract>/v1/`, validated by `gui.contracts.validate`. The code sources are
`gui.errors` (error codes) and `gui.core.run_states` (run states); `tests/test_runtime_contracts.py` keeps them, the
schemas and this page in step.

| Contract | Used for |
| --- | --- |
| `api-error/v1` | the body of every failed request and of the `error` stream frame |
| `bootstrap/v1` | `GET /v1/bootstrap`: the handshake |
| `run/v1` | the record of a command run (`/v1/runs/{id}`) |
| `stream/v1` | the frames of the WebSocket `/v1/events` |
| `trust/v1` | the trust state of a plugin (`/v1/plugins`) |
| `config-mutation/v1` | the configuration write: preview and commit |

The API listens on loopback only and authenticates every request with the session secret; no contract has a field
for a secret value. Values that may be secret (run input, argv, log text) are redacted before they are stored or sent;
a secret configuration key takes only a reference (`env://NAME`, `keyring://NAME`).

## Errors (`api-error/v1`)

`{"$schema": "urn:swissknifeman:gui:api-error:v1", "error": {code, class, message, retryable, correlation_id,
details?, issues?}}`. The message is safe to show (no secret, token or trace); `correlation_id` ties the error to the
audit and backend logs; `issues` lists validation issues as `{pointer, code, message}`.

### Code registry

| Code | Class | HTTP | Retryable |
| --- | --- | --- | --- |
| `AUTH_REQUIRED` | unauthorized | 401 | no |
| `AUTH_INVALID` | unauthorized | 401 | no |
| `HOST_REJECTED` | forbidden | 403 | no |
| `ORIGIN_REJECTED` | forbidden | 403 | no |
| `PROTOCOL_INCOMPATIBLE` | incompatible | 409 | no |
| `PAYLOAD_TOO_LARGE` | limit | 413 | no |
| `NOT_FOUND` | not_found | 404 | no |
| `INPUT_INVALID` | invalid | 422 | no |
| `OUTPUT_INVALID` | internal | 502 | no |
| `PATH_ESCAPE` | forbidden | 403 | no |
| `PERMISSION_DENIED` | forbidden | 403 | no |
| `CONFIRMATION_REQUIRED` | forbidden | 428 | no |
| `CONCURRENCY_LIMIT` | limit | 429 | yes |
| `RUN_NOT_CANCELLABLE` | conflict | 409 | no |
| `HANDLER_FAILED` | unavailable | 502 | yes |
| `HANDLER_TIMEOUT` | timeout | 504 | yes |
| `PLUGIN_UNAVAILABLE` | unavailable | 503 | yes |
| `PLUGIN_QUARANTINED` | unavailable | 503 | no |
| `CONFIG_REVISION_CONFLICT` | conflict | 409 | no |
| `CONFIG_LOCKED` | locked | 423 | yes |
| `CONFIG_LAYER_FORBIDDEN` | forbidden | 403 | no |
| `PREVIEW_STALE` | conflict | 409 | no |
| `CONTRIB_INVALID` | invalid | 422 | no |
| `CONTRIB_UNREADABLE` | invalid | 422 | no |
| `CONTRIB_OWNER_MISMATCH` | invalid | 422 | no |
| `CONTRIB_ID_PREFIX` | invalid | 422 | no |
| `CONTRIB_CONFLICT` | conflict | 409 | no |
| `CONTRIB_INCOMPATIBLE` | incompatible | 409 | no |
| `CONTRIB_HANDLER_MISSING` | invalid | 422 | no |
| `CONTRIB_PATH_ESCAPE` | forbidden | 403 | no |
| `CONTRIB_REF_UNKNOWN` | invalid | 422 | no |
| `CONTRIB_INPUT_UNKNOWN` | invalid | 422 | no |
| `CONTRIB_CAPABILITY_RESERVED` | forbidden | 403 | no |
| `CATALOG_SOURCE_UNAVAILABLE` | unavailable | 503 | yes |
| `INTERNAL` | internal | 500 | no |

`AUTH_*`, `HOST_REJECTED` and `ORIGIN_REJECTED` come from the security checks of every request (session secret,
Host in `127.0.0.1:<port>`, `localhost:<port>`, `[::1]:<port>`, Origin in the allowlist of the mode).
The `CONTRIB_*` codes are the rejection codes of the contribution resolver ([contribution.md](contribution.md));
`CATALOG_SOURCE_UNAVAILABLE` means the unit list could not be read. A new code is added to `gui.errors.CODES` and to
this table in the same change.

## Handshake (`bootstrap/v1`)

`GET /v1/bootstrap` answers one of two kinds, chosen by `mode`:

- `desktop`: served through the Tauri shell; carries `shell.version`.
- `browser`: served to a browser on loopback; has no `shell`.

Both carry `epoch` (id of this backend process, new at every start), `backend {version, python}`, `gui_protocol
{min, max}`, `contracts [{id, version}]`, `units [{id, version}]`, `features` and `platform {os, arch}` (`linux` or
`darwin`; `x86_64` or `aarch64`).

**Compatibility rule.** The frontend carries its own protocol version `N`. When `N` is outside `[min, max]`, the
frontend shows a diagnostic screen with `PROTOCOL_INCOMPATIBLE` and the versions of both sides; the main UI does not
open. A contract the frontend needs and `contracts` lacks is the same failure.

## Runs (`run/v1`)

A run records what ran (`command`, `owner`, `executable {path, digest}`, `argv_redacted`, `cwd`), in which context
(`context {project_id?, plan_id?, item_id?}`, redacted `input`), who asked (`actor {kind: user|system, id}`), the
decision (`permission {decision: allowed|confirmed|denied, effects [{effect, enforcement}], grants}`), the log size
(`log {stdout_bytes, stderr_bytes, truncated}`), its state, timestamps, `exit {code, signal}` and `error`.

### States and transitions

| State | Next states |
| --- | --- |
| `queued` | `authorizing`, `cancelled`, `lost` |
| `authorizing` | `denied`, `starting`, `lost` |
| `starting` | `failed_to_start`, `running`, `lost` |
| `running` | `succeeded`, `failed`, `cancelling`, `timed_out`, `lost` |
| `cancelling` | `cancelled`, `lost` |
| `denied` | terminal |
| `failed_to_start` | terminal |
| `succeeded` | terminal |
| `failed` | terminal |
| `cancelled` | terminal |
| `timed_out` | terminal |
| `lost` | terminal |

- A transition is written to the state store before its event is published.
- Every state that is not terminal may become `lost`: after a crash the backend marks unfinished runs `lost`. Runs in
  `starting`, `running` or `cancelling` are checked first (a live process with the same pid and create time); a PID is
  never adopted.
- A queued run is cancelled without a process (`queued → cancelled`); a running one goes through `cancelling`. A
  cancel in any other state is `RUN_NOT_CANCELLABLE`.

## Event stream (`stream/v1`)

One frame per WebSocket message, chosen by `kind`:

| Kind | Direction | Fields |
| --- | --- | --- |
| `subscribe` | client → server | `id`, `filter {projects?, runs?, owners?, types?}`, `cursor` (int or null), `epoch` (string or null) |
| `unsubscribe` | client → server | `id` |
| `event` | server → client | `seq`, `sub`, `event` (aicore `event/v1`, unchanged) |
| `log` | server → client | `seq`, `sub`, `run_id`, `stream` (`stdout`/`stderr`), `chunk`, `text`, `truncated` |
| `run` | server → client | `seq`, `sub`, `run {run_id, state, exit?, finished_at?}` |
| `snapshot_required` | server → client | `sub`, `reason` (`cursor_expired`/`overflow`) |
| `heartbeat` | server → client | `seq`, `at` |
| `error` | server → client | `sub?`, `error` (`api-error/v1` error object) |

**Cursor, epoch, snapshot.** `seq` grows monotonically inside one backend process; `epoch` (from bootstrap) names that
process. A client that reconnects sends `subscribe` with the last `seq` it applied as `cursor` and the `epoch` it was
read in; the server replays the frames after it. When the cursor is older than the retention, the epoch differs (the
backend restarted) or a subscription's queue overflowed, the server sends `snapshot_required`: the client reloads the
state through the HTTP API and subscribes again with `cursor: null, epoch: null`. A `subscribe` with a cursor and no
epoch is `INPUT_INVALID`. Progress events may be coalesced; log chunks come from a bounded ring buffer and the full
log stays on disk.

## Plugin trust (`trust/v1`)

A plugin document holds `id`, `source` (`unit`/`extension`), `state`, the flags `runtime_enabled` (queries, commands,
processes) and `ui_enabled` (routes, widgets, docs), `manifest_digest`, `compatibility {protocol_ok,
missing_contracts}`, `failures {count, window_s, last_code?}`, `permissions` (each declared effect with `declared`
and `enforcement`: `declared`, `enforced` or `advisory`) and `grants`.

- States: `discovered → compatible → enabled → starting → healthy`; `compatible → disabled`; `starting | healthy →
  degraded → quarantined`; terminal errors `incompatible`, `invalid`, `permission_denied`.
- A grant is `{id, plugin, capability, project_id (null: every project), manifest_digest, granted_at, expires_at (null:
  no expiry), granted_by}`. Trust is not transitive; a manifest digest change with new permissions voids the grant.
- The UI never shows `enforced` for an effect the platform does not limit.

## Configuration write (`config-mutation/v1`)

Four kinds, chosen by `kind`; the GUI writes only the `machine` and `project` layers, through aicore:

1. `preview_request {module, layer, expected_revision, patch}` — `patch` is a list of `{op: set, key, value}` and
   `{op: unset, key}`; `expected_revision` is the digest of the layer file the user edited.
2. `preview {preview_id, module, layer, file, revision, diff, issues, confirm_required, confirm_reasons}` — no side
   effects; `diff` shows the layer value and the effective value (with its layer) before and after; `preview_id` is the
   digest of module, layer, revision and patch.
3. `commit_request {preview_id, expected_revision, confirmed}` — `confirmed` must be true when the preview required a
   confirmation (`CONFIRMATION_REQUIRED` otherwise).
4. `commit_result {revision, file, backup}`.

The commit takes the layer lock (`CONFIG_LOCKED` on timeout), compares the file revision with `expected_revision`
(`CONFIG_REVISION_CONFLICT`), repeats the preview on the current text and compares `preview_id` (`PREVIEW_STALE`),
writes through aicore (temp file, fsync, atomic replace, backup), re-reads and validates. A write is never blind:
there is no last-write-wins. A layer the key may not be set in is `CONFIG_LAYER_FORBIDDEN`. Configuration values are
scalars or lists of scalars (TOML has no null); `null` in a diff means the key is absent.
