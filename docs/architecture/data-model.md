# Data model

Exact table names, columns and constraints are the PostgreSQL migrations in
[`adapters/postgres/migrations/sql/`](../../src/skm/adapters/postgres/migrations/sql/).
[ADR 0005](../adr/0005-postgres-only-backend.md),
[ADR 0006](../adr/0006-psycopg-explicit-sql-migrations.md) and
[ADR 0007](../adr/0007-identity-uuidv7-display-keys.md) record the backend, migration
and identity decisions.

## Conventions

| Topic | Contract |
|---|---|
| Backend | PostgreSQL 16+; memory adapters are for tests |
| Ownership | One schema per module, plus `skm_core`; settings owns `skm_config` |
| Identity | Application-generated UUIDv7; display keys are separate scoped aliases |
| Workspace isolation | Composite parent keys/FKs include `workspace_id` |
| Time | Aware UTC and `timestamptz`; imported date-only values use `source_date` |
| Versions | `schema_version`, `revision_no`, `row_version`, `stream_seq` are distinct |
| Concurrency | Conditional writes with expected row/edit versions |
| JSONB | Schema-validated bounded document payloads; relational identity, state and links stay in columns |
| Immutability | Revision contents, outputs and historical records use append-only/immutable constraints |
| Deletion | Durable entities archive/trash; cascades are limited to owner-dependent technical children |
| Permissions | Migrator owns DDL; app receives only required DML, with cumulative append-only restrictions |

## Ownership map

| Schema | Principal records |
|---|---|
| `skm_core` | Scopes, streams, events, workspace counters, outbox, consumer/idempotency receipts and audit |
| `skm_config` | Entries, history and generation |
| `skm_access` | Principals, identities, API token hashes and memberships |
| `skm_workspace` | Workspaces, projects, repositories/remotes, hosts, checkout bindings and workers |
| `skm_artifacts` | Staged blobs, blobs/locations, files/versions and access grants |
| `skm_extensions` | Packs/versions, resources/versions/files and quarantine |
| `skm_planning` | Plan identities/aliases, drafts, immutable revisions, typed specification tables and file bindings |
| `skm_policy` | Tool intents, approvals and decision audit |
| `skm_runtimes` | Host runtime installations and capability verifications |
| `skm_context` | Texts, draft/final manifests, blocks, research queries and external sources |
| `skm_execution` | Readiness, bundles, runs/tasks, attempts/environments/stages/steps, assignments/leases, outputs, checks, reviews, acceptance, budgets, decisions and effects |
| `skm_integrations` | Projections and owned file/block/key state |
| `skm_knowledge` | Expiring memory, durable curated lessons and graph generations/nodes/edges |
| `skm_learning` | Activity, candidates, signals and human promotion reviews |
| `skm_exports` | Derived vault notes and per-vault write receipts |

## Publication and artifacts

A Plan owns mutable Drafts and immutable Revisions. Publication locks the plan
before the draft, checks expected versions/base revision, resolves pinned material
versions, and recalculates the prepared candidate digest. A mismatching
`expected_content_digest` returns `VERSION_CONFLICT`; identical content returns
`NO_CHANGES`. Revision, members, typed spec, payload/digest, current revision,
event and receipt commit atomically. Preview creates no approval or ticket.

Bytes enter through staged blob upload before a command links a file version.
Digest coordination covers promote/register/consume/cleanup (E12). Referenced
blobs are not physically deleted in this version. Bindings live in consumer schemas;
knowledge of a digest does not grant read access.

## Migrations and history

Release 0.1.0 initializes the project and machine databases from separate baselines.
The packaged files live under `src/skm/adapters/postgres/migrations/`.
`skm db status` compares project migrations with the database history.
New changes append the next number and preserve applied checksums.
Every migration commits atomically with its history receipt. Deferred FKs close
before application data is created. Nontransactional/autocommit fallback is forbidden.

E53–E57 keep causal history in existing append-only domain events and existing IDs.
The bounded history reader pins `through_seq`; it does not replay effects or infer
past facts from mutable rows. E58 adds typed work-policy snapshots in readiness and
bundles, preserving null versus empty override semantics. See [execution](execution.md).
