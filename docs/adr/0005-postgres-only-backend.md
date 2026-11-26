# ADR 0005: PostgreSQL is the production backend for shared state in v2.0

Status: proposed
Date: 2026-10-25

## Context
Legacy state is many weakly linked JSON/JSONL/TOML files plus one SQLite DB, kept consistent by locks and
best-effort multi-file writes (not crash-atomic). The owner chose a database as the source of truth.

## Decision
PostgreSQL ≥ 16 is the only production backend for shared application state, including shared knowledge.
The shared state repository ports have in-memory implementations for unit and contract tests.
Legacy JSON is imported once by a migration tool (P14). Filesystem-backed shared state is out of scope.

`LocalSqliteMemoryStore` owns host-private episodic memory in a SQLite database under the selected profile's
host state directory. The store uses WAL mode and owner-only permissions (0600 for the database and its
WAL/SHM files). It expires and prunes episodes locally. Queries are project-local by default
(`inherit_workspace=false`). Explicit inheritance can add workspace-level records from the same workspace.
Re-recording the same kind and text within a session and scope leaves the original expiry in place.
Health probes expire within five minutes. Each scope accepts at most one probe every 30 seconds and keeps
the latest eight live probes.
Every episode is classified `HOST_PRIVATE`. Episodes stay in host-local storage and are available
to the supported host-local memory operations. See [ADR 0019](0019-versioned-context-manifest.md).

## Alternatives considered
- Filesystem + SQLite + PostgreSQL in parallel (audit vs-kyro): rejected for v2.0 — triples the work before the
  model is proven.

## Consequences
Local mode needs a local PostgreSQL for shared application state (docker compose provided). Tests needing
PostgreSQL run with `SKM_TEST_DATABASE_URL`. Episodic storage requires no PostgreSQL migration.

## Compatibility
Release 0.1.0 initializes empty PostgreSQL databases and restores backups from its own schema baseline.

## Verification
Contract suites run on memory and Postgres adapters in CI.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).
