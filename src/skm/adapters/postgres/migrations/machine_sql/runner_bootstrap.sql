-- The machine runner records its own baseline and version history in skm_host.
CREATE SCHEMA IF NOT EXISTS skm_host;

CREATE TABLE IF NOT EXISTS skm_host.schema_migrations (
    version     integer     PRIMARY KEY,
    name        text        NOT NULL,
    checksum    text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    applied_by  text        NOT NULL DEFAULT current_user,
    duration_ms integer     NOT NULL,
    CONSTRAINT ck_schema_migrations__version CHECK (version >= 1),
    CONSTRAINT ck_schema_migrations__checksum CHECK (checksum ~ '^sha256:[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS skm_host.schema_baseline (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    epoch text NOT NULL,
    chain_sha256 text NOT NULL,
    updated_at timestamptz NOT NULL
);
