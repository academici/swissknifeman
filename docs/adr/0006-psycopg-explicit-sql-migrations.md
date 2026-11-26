# ADR 0006: psycopg 3, explicit SQL and an own forward-only migration runner

Status: proposed
Date: 2026-10-25

## Context
An ORM tempts treating ORM models as the domain and hides the schema; the schema must read as a document.

## Decision
Repositories are hand-written classes using parameterized SQL through psycopg 3 with a connection pool.
Mapping row ↔ domain object lives next to the repository (`mapping.py`). Migrations are numbered SQL files applied
forward-only by `skm db migrate`, with checksums in `skm_core.schema_migrations` and a committed normalized schema
snapshot that tests compare.

## Alternatives considered
- SQLAlchemy Core/ORM + Alembic: rejected — extra abstraction, autogeneration requires ORM models.
- Raw migrations via an external tool (dbmate, sqitch): rejected — extra binary dependency.

## Consequences
More explicit SQL to write; reviewable DDL diffs.

## Compatibility
n/a.

## Verification
Migration tests from empty DB; `verify` detects edited applied files; snapshot test.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).
