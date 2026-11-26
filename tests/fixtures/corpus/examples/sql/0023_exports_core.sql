-- 0023_exports_core: vault notes queued by subscribers and their per-vault writes (ledger I6). Owner module: exports.
-- FKs: skm_core (domain_events), skm_workspace (projects, hosts) — allowed by the module graph
-- (exports depends on planning, execution, workspace; spec/modules/exports.md §2, §11).
CREATE SCHEMA IF NOT EXISTS skm_exports;

CREATE TABLE skm_exports.vault_notes (
    id            uuid        PRIMARY KEY,
    workspace_id  uuid        NOT NULL,
    project_id    uuid        NOT NULL,
    kind          text        NOT NULL,
    event_id      uuid        NOT NULL,
    source_id     uuid        NOT NULL,
    name          text        NOT NULL,
    subfolder     text        NOT NULL,
    body          text        NOT NULL,
    body_digest   text        NOT NULL,
    generation    bigint      NOT NULL DEFAULT 1,
    state         text        NOT NULL DEFAULT 'pending',
    created_at    timestamptz NOT NULL,
    requeued_at   timestamptz NULL,
    CONSTRAINT fk_vault_notes__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_vault_notes__domain_events FOREIGN KEY (event_id)
        REFERENCES skm_core.domain_events (id) ON DELETE RESTRICT,
    CONSTRAINT uq_vault_notes__event_id_kind UNIQUE (event_id, kind),
    CONSTRAINT ck_vault_notes__kind CHECK (kind IN ('plan_archived', 'run_finished')),
    -- Leave room for a numeric collision suffix within a 255-byte filesystem component.
    CONSTRAINT ck_vault_notes__name CHECK (octet_length(name) BETWEEN 4 AND 240 AND name LIKE '%.md'
        AND position('/' in name) = 0),
    CONSTRAINT ck_vault_notes__subfolder CHECK (subfolder IN ('plans', 'runs')),
    CONSTRAINT ck_vault_notes__body CHECK (octet_length(body) <= 262144),
    CONSTRAINT ck_vault_notes__body_digest CHECK (body_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_vault_notes__generation CHECK (generation > 0),
    CONSTRAINT ck_vault_notes__state CHECK (state IN ('pending', 'cancelled', 'expired'))
);
-- created_at is the first materialization time; requeue starts a fresh pending TTL without changing it.
CREATE INDEX ix_vault_notes__project_id_pending_since
    ON skm_exports.vault_notes (project_id, (COALESCE(requeued_at, created_at))) WHERE state = 'pending';

-- requeue_note(note_id, expected_generation) uses a CAS UPDATE to increment generation,
-- set state='pending' and requeued_at=now(); pending TTL uses COALESCE(requeued_at, created_at).
-- Historical receipts stay immutable until retention purge; requeue never deletes them.
-- record_note_written locks the note FOR UPDATE, rejects a stale generation/non-pending/expired note and verifies
-- expected_digest = vault_notes.body_digest before INSERT in the same transaction. A CHECK cannot compare rows.
CREATE TABLE skm_exports.vault_note_writes (
    note_id        uuid        NOT NULL,
    vault_id       uuid        NOT NULL,
    generation     bigint      NOT NULL,
    host_id        uuid        NOT NULL,
    relative_path  text        NOT NULL,
    expected_digest text       NOT NULL,
    observed_digest text       NOT NULL,
    outcome        text        NOT NULL,
    written_at     timestamptz NOT NULL,
    CONSTRAINT pk_vault_note_writes PRIMARY KEY (note_id, vault_id, generation),
    CONSTRAINT fk_vault_note_writes__vault_notes FOREIGN KEY (note_id)
        REFERENCES skm_exports.vault_notes (id) ON DELETE CASCADE,
    CONSTRAINT fk_vault_note_writes__hosts FOREIGN KEY (host_id)
        REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT ck_vault_note_writes__relative_path CHECK (char_length(relative_path) BETWEEN 1 AND 1024
        AND relative_path !~ '(^/|(^|/)\.\.(/|$))'),
    CONSTRAINT ck_vault_note_writes__generation CHECK (generation > 0),
    CONSTRAINT ck_vault_note_writes__expected_digest CHECK (expected_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_vault_note_writes__observed_digest CHECK (observed_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_vault_note_writes__outcome CHECK (outcome IN ('created', 'verified_existing', 'modified_existing')),
    -- modified_existing is a terminal observation for this generation, never verified delivery success.
    CONSTRAINT ck_vault_note_writes__outcome_digest CHECK (
        (outcome IN ('created', 'verified_existing') AND observed_digest = expected_digest)
        OR (outcome = 'modified_existing' AND observed_digest <> expected_digest))
);

-- Like consumer_receipts: UPDATE is forbidden, DELETE is reserved for janitor retention purge (including CASCADE).
CREATE TRIGGER tg_vault_note_writes__no_update BEFORE UPDATE ON skm_exports.vault_note_writes
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_row_update();

SELECT skm_core.grant_app('skm_exports', '{}'::text[]);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE ON skm_exports.vault_note_writes FROM skm_app;
    END IF;
END
$$;
