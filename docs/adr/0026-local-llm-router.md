# ADR 0026: Local LLM router and provider pool

Status: proposed
Date: 2026-11-27

## Context

Local clients need a shared inference endpoint for isolated account slots with CLI, direct HTTP and
OAuth transports. The router must preserve the provider's wire protocol where possible, isolate
stateful conversations by client, and guard against a CLI worker routing back to itself.

## Decision

### Listener and layers

The router defaults to `127.0.0.1:8317`. Startup accepts only the literal IPv4 bind address
`127.0.0.1`. The router follows [ADR 0004](0004-sync-core-async-edge.md)
and [ADR 0012](0012-dependency-policy.md).

| Path under `src/skm/` | Responsibility |
| --- | --- |
| `entrypoints/api/router/` | Async Starlette and Uvicorn entrypoint, route authentication, request handling and SSE streaming |
| `adapters/http_client/router_upstream.py` | Async `httpx` upstream transport with `trust_env=False` and a bootstrap-provided proxy bridge URL |
| `bootstrap/router.py` | Synchronous configuration and adapter composition, bridge lifecycle, validated reload and daemon lifecycle |
| `adapters/runtimes/router/` | Synchronous scheduling, in-flight deduplication, protocol translation and CLI worker isolation |

The upstream HTTP adapter receives its dependencies from bootstrap and has no imports from runtime
adapters. Core code stays synchronous. An invalid reload preserves the running configuration.

### Authorization, protocol and worker isolation

`client_keys` authenticate inference routes and identify clients. `management_key` authenticates
`/admin/*`. Missing or invalid credentials receive `401`. A valid key for the wrong role receives
`403`. The router strips inbound `Authorization` before constructing upstream authentication.

Anthropic `/v1/messages` and `/v1/messages/count_tokens` requests use native passthrough to an
Anthropic upstream. Passthrough forwards only `anthropic-version`, `anthropic-beta`, `content-type`
and `accept` from client headers. The router bounds nonstreaming responses at 16 MiB and SSE
events at 1 MiB. An empty or invalid success response can trigger fallback before delivery. A stream
becomes committed when the first SSE byte reaches the client.

Only stateless in-flight requests are eligible for deduplication. The key contains `client_id`,
method, path, model, canonical body SHA-256, stream flag and response format. Subscribers can cancel
independently. `hot_pool`, `X-Conversation-ID` and `claude-code:<id>` identify stateful requests and
exclude them from deduplication. Hot-pool workers are keyed by `(client_id, conversation_id, slot_id,
worker_generation)` with one turn in flight per worker. The signed internal `X-SKM-Internal-Hop: 1`
marker for `--bare` prevents a second `cli_subprocess` selection and breaks the routing loop.

### Versioned provider pool

`bootstrap/provider_accounts.py` owns parsing of `provider-pool.toml`. The v1 format has no
`schema_version` and keeps `[groups]`, `[slots.<id>].runtime_id` and `[slots.<id>.quota_urls]` for
quota probes. With `schema_version = 2`, slots declare `runtime_id`, `transport`, `tier`, egress
and `models` entries with `name` and `is_compat`. The three transport configurations are as follows.

| `transport` | Slot configuration |
| --- | --- |
| `cli_subprocess` | `wallet_path`, `shallow_home`, `symlink_host_files`, `write_back`, `worker_mode` (`ephemeral` or `hot_pool`) |
| `http_api` | `provider`, `base_url`, `api_key_ref` (for example `secret://env/OPENROUTER_API_KEY`), `provider_routing.allow_fallbacks`, `provider_routing.zdr` |
| `oauth_gateway` | `provider`, `base_url`, `token_file`, `write_back` |

`egress_proxy` can select a private proxy endpoint or `direct`. CLI host file symlinks default to
an empty list and exclude `.ssh` by default. The public `ProviderSlot` for `accounts --json`
contains only `runtime_id`, `slot_id`, `host_dispatches_tools`, `tier`, `transport`, `models`,
`has_egress_proxy` and `proxy_scheme`. `SlotRuntimeConfig` and `ProxyEndpoint` hold private
configuration such as credential references and proxy userinfo. Bootstrap supplies the upstream
adapter and quota prober with the `http://127.0.0.1:<ephemeral_port>` URL from `LocalProxyBridge`
for SOCKS5 egress. This keeps `socksio` outside the dependency set.

## Alternatives considered

- An externally bound listener would widen the network and credential boundary.
- Translating all Anthropic requests would risk altering native fields and streaming behavior.
- Deduplicating stateful requests by body would merge turns from distinct conversations.

## Consequences

Authentication, provider credentials, and conversation ownership are checked at their respective
boundaries. The router can use the existing account pool with a local listener and no database
requirement. Bootstrap owns transport configuration and proxy lifetimes.

## Compatibility

Existing v1 pool files remain valid. The router consumes the versioned v2 pool contract. Native
Anthropic message and token-count routes retain their protocol shape when passed through.

## Verification

P01 covers registry compatibility, credential redaction, and the local proxy bridge. P05 verifies
loopback binding, key roles, passthrough, response bounds, fallback and SSE commitment, stateless
deduplication, stateful worker isolation, and rejection of recursive CLI routing.
