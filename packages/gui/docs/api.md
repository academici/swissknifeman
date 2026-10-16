# Local API

The local API of the gui backend (`gui serve`, `lib/gui/http`) and its contracts. Each contract is a
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
| `project/v1` | `/v1/projects`: the trusted projects |

The API listens on loopback only and authenticates every request with the session secret; no contract has a field
for a secret value. Values that may be secret (run input, argv, log text) are redacted before they are stored or sent;
a secret configuration key takes only a reference (`env://NAME`, `keyring://NAME`).

## Endpoints

All bodies are JSON (`ensure_ascii=False`); every failure is an `api-error/v1` envelope with a fresh
`correlation_id` and never a trace (an unexpected failure is `INTERNAL`, its redacted trace goes to
`state_dir("gui")/backend.log`).

| Method and path | Answer |
| --- | --- |
| `GET /v1/bootstrap` | `bootstrap/v1` kind `browser`: epoch, versions, `gui_protocol`, contracts of `unit.json`, units of the accepted contributions, features (`queries`, `projects`), platform |
| `GET /v1/ui/contributions[?refresh=1]` | `catalog/v1`, resolved at start; `refresh=1` collects and resolves again |
| `GET /v1/schemas/{contract}/{version}` | the JSON Schema of a contract listed in `unit.json`; anything else `NOT_FOUND` |
| `GET /v1/projects`, `GET /v1/projects/{id}` | `project/v1` (`project_list`, `project`) |
| `POST /v1/projects` `{path, confirm?}` | `201` `project/v1`; a bearer client adds at once (`source: open`), a browser session confirms first (`source: user`) |
| `POST /v1/queries/{id}` `{context, params}` | the `view-data/v1` answer of a query of an accepted contribution |
| `GET /v1/commands[?scope=&project_id=]` | `run-api/v1` `command_list`: the commands of the accepted catalog, without argv or paths |
| `POST /v1/commands/{id}/runs` `run_request` | `202` `run/v1` (`running`, or a terminal state such as `denied`); `428`, `429`, `422` before a run exists |
| `GET /v1/runs[?project_id=&state=&limit=&cursor=]` | `run-api/v1` `run_list`, newest first, `next_cursor` while pages remain |
| `GET /v1/runs/{run_id}` | `run/v1` |
| `POST /v1/runs/{run_id}:cancel` `{}` | `run/v1` in `cancelling` (or `cancelled` from `queued`); `RUN_NOT_CANCELLABLE` otherwise |
| `GET /v1/runs/{run_id}/log?stream=&cursor=&limit=` | `run-api/v1` `log_page`: stored chunks from chunk `cursor`; `next_cursor` null when the run ended and all were returned |
| WebSocket `/v1/events` | `stream/v1` frames: subscriptions, replay by cursor, run, log, journal events, heartbeats |
| `POST /v1/session/tokens` `{}` | `201` `{url}`: a new one-time browser URL; bearer only (`PERMISSION_DENIED` otherwise) |
| `GET /?t=<token>` | the token exchange: `303` to `/` with the session cookie |
| `GET` any other path | the built frontend (`frontend/dist`): a file inside it, else `index.html`; `FRONTEND_NOT_BUILT` without a build |

### Queries

The query id must be in the accepted catalog (`NOT_FOUND`). `context` has only `project_id`, `plan_id`, `item_id`,
`run_id`; the scope of the query says which are required (`project`: `project_id`; `plan`: and `plan_id`; `item`:
and `item_id`; `run`: `run_id`); `project_id` must name a registered project whose root is still in place. `params`
are checked by `gui.core.inputs` against the query's fields (unknown, required, type, enum, pattern, bounds,
reference patterns, `project-path` inside the project after `realpath`); every problem is an issue of
`INPUT_INVALID`. The handler (the aicore command plugin the contribution names) is called at `gui:query` with
`{id, context, params}` and the deadline `timeout_s`; a hub unit's handler is trusted, an extension's comes from
`[aicore.plugins]` as configured (`PLUGIN_UNAVAILABLE` when it is not usable). The answer must fit
`query.max_output_bytes`, be `view-data/v1` and be the view the query `returns` (`OUTPUT_INVALID`, `502`); then
secret values (secret-named environment variables, the session secret) are redacted. A handler error is
`HANDLER_FAILED` (`details.plugin_code`), a missed deadline `HANDLER_TIMEOUT`. With `cache_s` the answer is reused
for that many seconds for the same owner, query, context and params.

## Commands and runs (`run-api/v1`)

A run request carries only typed values (I2): `{$schema, kind: "run_request", context, input, dry_run, confirm?}`.
The command must be in the accepted catalog (`NOT_FOUND`); its scope says which context is required (as for queries);
`input` is checked by `gui.core.inputs` (pointer `/input/<name>`); `dry_run` needs a declared dry run. Then:

- **Confirmation.** `confirmation: always`, or `risk-based` with risk `medium`/`high` and not a dry run, answers `428
  CONFIRMATION_REQUIRED` before any run exists; the same request with `confirm` gets the run with decision
  `confirmed`.
- **Limits.** Active runs are counted globally (`runs.max_global`), per project, per owner and per
  `concurrency_key` (with `{project_id}`, `{plan_id}`, `{item_id}` filled in); over a limit is `429
  CONCURRENCY_LIMIT` and no run is created (there is no queue).
- **Permission (until plugin trust exists).** A hub unit's command is `allowed`; an extension's only when
  `[aicore.plugins]` trusts it, else the run is `denied` (`PERMISSION_DENIED`). Every effect is reported with
  enforcement `advisory`: nothing is enforced by the OS yet (I12).
- **argv** (`gui.core.argv`, I4). `argv[0]` is the descriptor's literal path, resolved inside the owner root and
  executable (`PATH_ESCAPE`, `HANDLER_FAILED`); each `{input}` part is exactly one element with one value, which may
  not start with `-` (`INPUT_INVALID`, issue `leading_dash`); fields with a flag follow in input order (a true
  boolean adds the flag alone, another value the flag and the value); the dry run's `argv_append` comes last. No
  shell is involved.
- **Working folder and environment** (I5). `cwd: project` is the registered project root after `realpath`, `owner`
  the real owner root; the environment is `aicore.ext.environment.clean_environment` plus the variables the
  descriptor lists in `exec.env`.
- **Process.** A new session (`start_new_session`), stdin closed. Cancel, a timeout (`timeout_s` of the command, or
  `runs.idle_timeout_s` without output) and shutdown signal the group with SIGTERM, wait `runs.cancel_grace_s`, then
  send SIGKILL to the group; when the leader exits, a group that is still alive is killed. Exit 0 is `succeeded`,
  any other end `failed` (`exit {code, signal}`), a timeout `timed_out` (`HANDLER_TIMEOUT`, `details.reason`
  `total` or `idle`). An `invoke` command calls the owner's handler once at `gui:command` with
  `{id, context, input}`; its JSON output becomes the stdout log.
- **Logs** (I6). Each stream is read in blocks of `runs.chunk_bytes`, decoded as UTF-8 (invalid bytes replaced),
  cleaned of OSC/CSI/other escape sequences and control characters except tab, newline and carriage return, and
  redacted (secret-named environment values, the variables the plugin may read as secrets, the session secret; an
  end that could begin a secret waits for the next block). Each chunk is written to
  `state_dir("gui")/runs/<run_id>/<stream>.jsonl` (`{chunk, at, text, truncated}`) and only then published. Past
  `runs.log_max_bytes` per stream the last chunk is marked `truncated` and the rest is read and dropped. Old logs are
  pruned at start by age (`retention.log_days`) and total size (`retention.log_total_mb`).
- **State** (I11). Every transition is written in its own transaction before its `run` frame is published. When the
  backend starts, every unfinished run of an earlier backend becomes `lost`; a process of such a run that is still
  alive with the same PID and start time is stopped with its group (`error.details.orphan_killed`). A PID is never
  watched again.
- **Audit.** `audit` rows `run.requested` (command, owner, redacted input, dry run), `run.decided` (decision,
  effects), `run.started` (program path and digest, redacted argv, cwd), `run.finished` (state, exit, duration).
  A run with a project is also journaled there as `gui.run.<verb>` (started, succeeded, failed, cancelled,
  timed_out, lost, denied) with `{run_id, command, owner, state}`; a journal failure never changes the run.

## Events (`/v1/events`)

The WebSocket passes the same Host, Origin (required) and session checks as every request before it is accepted
(else closed `4403` or `4401`). The client sends `subscribe {id, filter, cursor, epoch}` and `unsubscribe {id}`
frames (at most 64 KiB, else closed `1009`; anything else is an `error` frame `INPUT_INVALID`; at most 16
subscriptions, `CONCURRENCY_LIMIT`). A filter narrows by `projects`, `runs`, `owners` (exact) and `types` (shell
patterns: journal event types, `gui.run`, `gui.log`); every key given must match.

Every frame the backend publishes (`event`, `log`, `run`, `heartbeat`) has the next `seq` of the backend process;
the last `events.ring_frames` are kept. A subscription with `cursor` and the current `epoch` (from `/v1/bootstrap`)
first gets the kept frames after the cursor, then live frames, without gaps or duplicates; an older cursor or
another epoch gets `snapshot_required` (`cursor_expired`) and the client reloads. Each subscription has a queue of
`events.queue_frames`; a client that falls behind gets `snapshot_required` (`overflow`) instead of the dropped
frames and stays subscribed. `.progress` events with the same type and subject within 250 ms replace each other in
a queue. Heartbeats come every `events.heartbeat_s`. The journals of the registered projects are read from their
end every `events.journal_poll_s` and their events come as `event` frames unchanged.

### Confirmation

A request that grants trust or runs a risky command answers `428 CONFIRMATION_REQUIRED` with
`details {confirm, risk, summary}`; the UI shows the summary and repeats the same request with
`confirm`. The token is an HMAC (session secret) of the purpose, the backend epoch and the request payload, so
it fits only that request in this backend process.

## Authentication and transport security

The backend binds `127.0.0.1` only (there is no host option) and runs uvicorn without proxy headers, server header
or access log. A pure ASGI middleware checks every HTTP request and WebSocket handshake, in this order:

1. `Host` is exactly `127.0.0.1:<port>`, `localhost:<port>` or `[::1]:<port>`, else `HOST_REJECTED` (DNS
   rebinding); a WebSocket is closed with `4403` before accept.
2. A present `Origin` is one of `http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>`, else
   `ORIGIN_REJECTED`; a WebSocket must send one.
3. A body over 1 MiB (declared or streamed) is `PAYLOAD_TOO_LARGE`; `POST`, `PUT`, `PATCH` and `DELETE` need
   `Content-Type: application/json` (`INPUT_INVALID`).
4. Authentication: `Authorization: Bearer <session secret>` (the CLI, later the desktop shell) or the cookie
   `skm_gui_session`; nothing else is accepted (`AUTH_REQUIRED` without one, `AUTH_INVALID` for a wrong one; a page
   request gets a short HTML page instead). A cookie-authenticated request that changes state must send `Origin`
   (`ORIGIN_REJECTED`), which with `SameSite=Strict` closes CSRF.
5. Every response gets `Content-Security-Policy` (`default-src 'self'`, no inline script or style, no
   `unsafe-eval`, `connect-src` to the three loopback WebSocket origins, `frame-ancestors 'none'`),
   `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, and `/v1/*`
   `Cache-Control: no-store`. No CORS header is ever sent.

The session secret has 256 bits (`secrets.token_urlsafe(32)`) and lives in the backend process and in
`state_dir("gui")/backend.json` (`0600`, folder `0700`) for `gui open`. The browser never sees it: `gui open` asks
`POST /v1/session/tokens` for a one-time URL `http://127.0.0.1:<port>/?t=<token>`; the first `GET` with it answers
`303` with `Set-Cookie: skm_gui_session=<value>; HttpOnly; SameSite=Strict; Path=/` (no `Secure`: plain loopback
HTTP). A token lives 300 s and works once; the backend keeps only sha256 values of tokens and cookies and compares
with `hmac.compare_digest`. Secrets, tokens and cookies are never logged and never part of a response.

### Single instance

`gui serve` holds `flock` on `state_dir("gui")/backend.lock` for its whole life; a second one exits with
`BACKEND_RUNNING` (CLI code, exit 1). `gui open` reuses a backend whose `backend.json` names a live process that
answers `GET /v1/bootstrap` with its secret; otherwise it starts `gui serve` detached (output to `backend.log`, no URL
in it) and waits up to 10 s (`BACKEND_START_FAILED` with the log tail). SIGTERM or SIGINT end the backend
gracefully and remove `backend.json`.

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
| `GUI_DEPS_UNAVAILABLE` | unavailable | 503 | yes |
| `STATE_INCOMPATIBLE` | internal | 500 | no |
| `FRONTEND_NOT_BUILT` | unavailable | 503 | no |
| `INTERNAL` | internal | 500 | no |

`AUTH_*`, `HOST_REJECTED` and `ORIGIN_REJECTED` come from the security checks of every request (session secret,
Host in `127.0.0.1:<port>`, `localhost:<port>`, `[::1]:<port>`, Origin in the allowlist of the mode).
The `CONTRIB_*` codes are the rejection codes of the contribution resolver ([contribution.md](contribution.md));
`CATALOG_SOURCE_UNAVAILABLE` means the unit list could not be read. `GUI_DEPS_UNAVAILABLE` means the locked
third-party packages of the backend are not installed and could not be (`gui deps ensure`); `STATE_INCOMPATIBLE`
means `gui.db` was written by a newer gui (its schema version is above the known migrations) and is left untouched.
A new code is added to `gui.errors.CODES` and to
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

## Projects (`project/v1`)

The control plane keeps its own registry of trusted projects in `gui.db` (`state_dir("gui")`, SQLite). A project
gets in only by an explicit act of the owner: `gui open`/`gui serve` with `--project DIR` or from inside a project, or
a confirmed `POST /v1/projects`. Its root is the nearest folder above the path with `.git` or `.swissknifeman/`
(else the path itself) after `realpath`; the id is `<slug of the folder name>-<first 8 hex of sha256(root)>`, so
adding the same root again returns the same entry. Every entry is `trusted: true` in v1; the maind fleet is shown by
the `gui-hub` bridge as data and grants no trust (I13).

- `project`: `{$schema, kind: "project", id, name, root, trusted, source: open|user, added_at}`.
- `project_list`: `{$schema, kind: "project_list", projects: [...]}` sorted by name and id.

A working folder of a project (the `cwd` of a command, a `project-path` input) is resolved only through the registry:
the stored root must still be the same real directory (else `NOT_FOUND`) and the path must stay inside it after
`realpath` (else `PATH_ESCAPE`). Adding and removing a project writes an `audit` row.
