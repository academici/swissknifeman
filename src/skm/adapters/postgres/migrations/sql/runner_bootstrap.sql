-- Executed by MigrationRunner (adapters/postgres/migrations/runner.py) before the first numbered migration.
-- Not a numbered migration itself: it creates the bookkeeping the runner needs. Idempotent.
CREATE SCHEMA IF NOT EXISTS skm_core;

CREATE TABLE IF NOT EXISTS skm_core.schema_migrations (
    version     integer     PRIMARY KEY,
    name        text        NOT NULL,
    checksum    text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    applied_by  text        NOT NULL DEFAULT current_user,
    duration_ms integer     NOT NULL,
    CONSTRAINT ck_schema_migrations__version CHECK (version >= 1),
    CONSTRAINT ck_schema_migrations__checksum CHECK (checksum ~ '^sha256:[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS skm_core.schema_baseline (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    epoch text NOT NULL,
    chain_sha256 text NOT NULL,
    updated_at timestamptz NOT NULL
);

-- The runner holds pg_advisory_xact_lock(hashtext('skm.migrations')) inside each migration transaction and
-- pg_advisory_lock(hashtext('skm.migrations.session')) for the whole `skm db migrate` call.
