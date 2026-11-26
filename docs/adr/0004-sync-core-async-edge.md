# ADR 0004: Synchronous core, async only at the HTTP edge

Status: proposed
Date: 2026-10-25

## Context
Mixing threading, asyncio and ad-hoc cancellation without one lifecycle owner produces hard-to-test code.

## Decision
Domain, application, persistence (psycopg sync + pool), worker and runtime adapters are synchronous. Subprocess
stream reading uses threads inside `platform.process`. The Starlette API calls application handlers through a
threadpool; SSE endpoints are async generators reading the event store.

## Alternatives considered
- Async everywhere: rejected — no benefit for pure logic and DB-per-command transactions; doubles API surface.
- anyio structured concurrency in core: deferred until measured need.

## Consequences
Simple handler signatures and deterministic tests.

## Compatibility
n/a.

## Verification
Architecture test forbids `async def` outside `entrypoints/api` and `adapters/http_client`.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).
