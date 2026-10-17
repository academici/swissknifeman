# Plugins: trust, grants and life cycle

A *plugin* is a hub bridge (`source = unit`) or an external extension (`source = extension`) that provides a GUI
contribution. `gui.core.plugins.PluginHost` decides what a plugin may do and in which state it is. It has no HTTP
layer; the routes `/v1/plugins*` (`gui.http.routes_plugins`, [api.md](api.md#plugin-endpoints-plugin-apiv1)) and the gates
in front of queries and commands (`routes_queries`, `routes_runs`) and of the broker are thin callers of it.

## What is stored and what is derived

`gui.db` migration 3 stores only the operator's decision and the history:

| Table | Content |
|---|---|
| `plugins` | `desired` (`new`, `enabled`, `disabled`), `quarantined_at`, `quarantine_code`, `reapproval`, `digest`, `effects_json`, `source` |
| `plugin_events` | history per plugin: `kind` `state`, `failure`, `grant`, `digest`, `admin`, with `code` and a redacted `detail` (at most 500 characters); the oldest rows beyond `plugins.history_limit` are removed on insert |
| `grants` | `plugin`, `capability`, `project_id` (null: every project), `manifest_digest`, `expires_at`, `revoked_at`, `voided_at`, `void_reason` |

The `state` is never stored. `derive_state(Facts)` is a pure function; the first matching rule wins:

1. verdict `incompatible` → `incompatible`; verdict `invalid` → `invalid`; verdict `missing` (stored, no longer in the
   catalog) → `discovered`
2. quarantined → `quarantined`
3. `desired = disabled` → `disabled`; `desired = new` → `compatible`
4. `reapproval` → `permission_denied`
5. calls in flight and no outcome yet in this process → `starting`
6. the last call failed and a failure is inside the window → `degraded`
7. the last call succeeded → `healthy`
8. otherwise `enabled`

`runtime_enabled` and `ui_enabled` are both true exactly in `enabled`, `starting`, `healthy`, `degraded` and
`permission_denied`. A plugin in any other state has its routes, widgets and docs hidden and nothing of it runs.

A hub unit appears with `desired = enabled`. An extension appears as `compatible` (`desired = new`): the operator must
Enable it, which first runs the conformance check (`gui check`; the same code). Trust of aicore stays a precondition for
starting an extension (`[aicore.plugins]` `enabled` and `trusted`); enabling it in the GUI and the grants are an extra
layer and never change that configuration.

## The one door: `admit`

Every query, command and process of a plugin goes through `admit(owner, kind, effects, project_id)`, which returns a
`Ticket` (a context manager) or raises a `PluginError`:

| Code | When |
|---|---|
| `PLUGIN_UNAVAILABLE` | not in the catalog, `incompatible` or `invalid` |
| `PLUGIN_QUARANTINED` | in quarantine |
| `PLUGIN_DISABLED` | `desired` is not `enabled`, or the plugin is closing (Disable is draining it) |
| `PERMISSION_DENIED` | an extension without a covering grant for an effect other than `read` (`details`: `plugin`, `effect`, `project_id`) |

`Ticket.finish(code=None, detail=None, cancelled=False)` reports the outcome once. Only a protocol failure counts:
`PROCESS_SPAWN`, `PROCESS_TIMEOUT`, `PLUGIN_TIMEOUT`, `PROCESS_EXIT`, `PROTOCOL_STDOUT`, `PROTOCOL_STDOUT_TOO_LARGE`,
`PLUGIN_HANDSHAKE_MISMATCH`, `PLUGIN_RESPONSE_INVALID`, `PLUGIN_MANIFEST_INVALID`, `PLUGIN_ID_MISMATCH`,
`PLUGIN_UNAVAILABLE` and `OUTPUT_INVALID`. A domain error with the plugin's own code, a non-zero exit of an argv command
(do not pass `PROCESS_EXIT` for it) and a cancellation by the user are not failures. A success clears `degraded` but
keeps the failure rows. `admit` and `disable` are ordered by `host.lock`: once Disable has returned from its first step
no `admit` passes.

## Quarantine

When a failure is recorded and the failures of the plugin inside `plugins.quarantine_window_s`, counted from the last
release, reach `plugins.quarantine_failures`, the plugin gets `quarantined_at` and the code of the last failure. This is
idempotent: a later failure is recorded but never writes a second `quarantined_at`. Only `release` lifts it; it
survives a restart. `release` also starts the count anew for a plugin that has failures in the window; the history
stays.

## Grants (I13)

A grant is plugin + effect + project (or every project) + optional expiry + manifest digest. Effects: `read`,
`project.write`, `plan.write`, `config.write`, `process.spawn`, `network`, `secrets.read`, `terminal`. `read` needs no
grant; `terminal` is reserved and can never be granted. Hub units need no grants.

The *manifest digest* of a plugin is `digest_json({"contribution": <catalog digest>, "handler": <sha256 of the handler
extension.json or null>})`. Executable files of argv commands are not part of it; the broker pins them per run.

When `sync` finds a new digest: if the plugin declares no effect it did not declare before, the live grants move to the
new digest; if it declares a new one, every live grant is voided (`void_reason = manifest_widened`), `reapproval` is
set (extensions) and the plugin is `permission_denied` until a new grant is made. A voided grant never comes back, even
when the old digest returns.

`grant` checks, in the transaction that writes it: the plugin is an available extension (not `incompatible`,
`invalid`, `quarantined` or `disabled`), the capability is a declared effect other than `read` and `terminal`,
`expires_at` is RFC 3339 UTC, in the future and at most 365 days away, and the digest the client saw (when given) is the
current one (`PLUGIN_UNAVAILABLE` otherwise). The project id is not checked here. `revoke` and voiding only affect new
`admit` calls: a run that already started goes on until it ends or the plugin is disabled.

## Enforcement (I12)

`permissions` lists every effect with `declared` and an `enforcement`: `declared` for `read` and for effects the
plugin does not use, `advisory` for a used effect that needs a grant. The platform has no sandbox in v1, so
`enforced` is never reported; the grant gates the start of work, it does not limit a running process.

## Enable, Disable, drain

`enable` refuses a quarantined plugin (`PLUGIN_QUARANTINED`) and runs the conformance gate for an extension in a worker
thread: any failing check gives `PLUGIN_CONFORMANCE_FAILED` with `details.count` and `details.findings` (up to ten lines `id: observed`; `api-error/v1` details are scalars). A pass is
remembered per digest until `sync` sees another digest.

`disable` closes the plugin and writes `desired = disabled` in one step, then waits for the calls in flight and the
active runs of the owner up to `plugins.drain_timeout_s`, cancels the runs that are left and waits
`runs.cancel_grace_s` for them. It returns `{drained, cancelled}`: runs that finished on their own and runs that were
cancelled.

## Transactions and events

Each mutation holds `host.lock`, then `db_lock`, in one `BEGIN IMMEDIATE` transaction; an error leaves no partial rows.
After `COMMIT` the host calls `publish(type, data, subject)` and `audit(action, target, decision, details)`:
`gui.plugin.state` `{plugin, from, to, reason}` on every change of the derived state, and `gui.plugin.grant` `{plugin,
capability, project_id, action}` with `granted`, `revoked` or `voided`. Audit actions: `plugin.enable`,
`plugin.disable`, `plugin.release`, `plugin.grant`, `plugin.revoke`, `plugin.quarantine`, `grant.rebound`,
`grant.voided`.

## Settings `[gui.plugins]`

| Key | Default | Range |
|---|---|---|
| `drain_timeout_s` | 10 | 0..300 |
| `quarantine_failures` | 3 | 1..20 |
| `quarantine_window_s` | 300 | 10..86400 |
| `history_limit` | 200 | 10..2000 |

## Interface

`PluginHost(conn, db_lock, settings, publish, audit, active_runs, cancel_run, conformance, clock=None,
monotonic=None, sleep=None)`: `observe(catalog)`, `sync(observed)`, `view(plugin_id, project_id=None)` (`trust/v1`),
`views(project_id=None)`, `visible(plugin_id)`, `admit(...)`, `enable`/`disable` (coroutines), `release`, `grant`,
`revoke`, `history(plugin_id, limit)`, `busy(plugin_id)`. `active_runs(owner)` returns the ids of the active runs of an
owner; `cancel_run(run_id)` may be a coroutine; `conformance(observed)` returns the failing checks as `{id, observed}`
(`plugins.failing` converts `check-result/v1` documents). `clock()` is epoch seconds; the host never sleeps for real
in a test.

## Where the host stands in the backend

`BackendState.plugins` is built with the injected pieces: `active_runs` and `cancel_run` come from the broker
(`Broker.active`, `Broker.cancel(run_id, system=True)`), `conformance` runs `resolve.check` of the owner root in a worker
thread, `publish` and `audit` are the machine-frame and audit writers of the config service. `sync` runs when the state
is built, at `start()` and after every `refresh_catalog()`; `visible_catalog()` is the catalog the UI gets.

`Ticket.invoke` is the only place that calls `invoke_one`; a structural test fails when any other file of `lib/gui`
does. A query `admit`s with `["read"]`, a command with its declared effects; for an argv command the ticket goes to
`Broker.submit(ticket=...)`: its grants become `permission.grants`, `enforcement()` tells the enforcement of each
effect, and the broker finishes the ticket when the run ends (a failure to start is `PROCESS_SPAWN`, a non-zero exit,
a timeout and a cancel judge nothing).
