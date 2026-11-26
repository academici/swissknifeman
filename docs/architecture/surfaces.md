# Surfaces

Exact CLI verbs are the generated [CLI reference](../reference/cli.md). HTTP routes
live in [`entrypoints/api/`](../../src/skm/entrypoints/api/). MCP tools live in
[`entrypoints/mcp/`](../../src/skm/entrypoints/mcp/). The browser client is described in
[the web guide](../guides/web.md). [ADR 0004](../adr/0004-sync-core-async-edge.md) keeps
async at the HTTP edge. Assignment tokens cannot call the worker protocol, worker
batches recheck the claim, and only local `skm db migrate` applies migrations.

## Client boundary

Surfaces parse input, invoke `SkmClient` or a host operation, and render results.
`SkmClient` exposes whole-command `dispatch`, `ask`, staged `upload_blob`,
`open_file_version_content` and `events`. Embedded and HTTP implementations share
the contract; remote calls never expose an unfinished UoW. Retry uses the original
idempotency key where allowed. Commands declaring forbidden idempotency reject it.

| Surface | Contract |
|---|---|
| CLI | argparse groups, human output by default, schema-defined `--json` output; typed references, ambiguity errors |
| HTTP API | Starlette/uvicorn, declarative command/query routes, OpenAPI 3.1 from schemas |
| SSE | Workspace sequence or separately ordered instance feed; explicit cursor control frames on reconnect |
| MCP | stdio JSON-RPC tools through the same client and current token authority |
| Web | React/TypeScript/Vite client; server-provided transitions, blocking reasons and schema forms |

## Errors and concurrency

| CLI exit | Meaning |
|---|---|
| 0 | Success |
| 1 | Validation, refusal or not found |
| 2 | CLI usage |
| 3 | Backend unavailable |
| 4 | Waiting for human input |
| 5 | Forbidden or unauthenticated |
| 6 | Conflict, precondition, missing capability or unknown outcome |
| 70 | Internal error |
| 130 | Interrupted |

The error catalog owns the mapping shared by CLI/API/MCP; the per-code exit is in
the generated [error reference](../reference/errors.md).
API errors use `application/problem+json` and the catalog code. Conditional writes
use ETag/If-Match and row/edit versions; pagination uses opaque keyset cursors.
Bearer secrets are hashed at rest. Worker and assignment credentials have distinct
scope/permissions; assignment tokens cannot call the worker protocol (E31).
SSE rechecks authorization, and bounded worker NDJSON batches recheck claim/token
for every batch (E19). Live text is best effort, not authoritative history.

## Web areas

| Area | Responsibility |
|---|---|
| Shell | Token login, workspace/project selection, navigation and connection state |
| Projects | Projects, repositories, hosts and checkout bindings |
| Plans | Draft editing, validation, candidate preview, publication, history and diff |
| Runs | Tasks, attempts, steps, checks, reviews, budgets and live stream |
| Inbox | Questions, approvals, manual verdicts and escalations |
| Settings | Schema-generated forms with level, effective value, provenance, lock and history |
| Extensions | Packs, resource versions and provenance |
| Workers and health | Host/runtime detection, worker state and readiness |

No client recomputes acceptance or bypasses the bus. Draft authoring remains
source-pinned with bounded reads and exact replacement; publication rechecks the
prepared candidate digest and authority (E52). Health separates liveness from
readiness. Only local `skm db migrate` applies migrations (E34); API startup does
not silently migrate server state. `tools/gen.py` generates the
[CLI](../reference/cli.md), [configuration](../reference/config.md), [error](../reference/errors.md)
and [event](../reference/events.md) references; an API reference arrives with its generator.
