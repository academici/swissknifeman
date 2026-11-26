-- 0004_core_idempotency_audit: command receipts (idempotency) and the audit log of authorization decisions.

CREATE TABLE skm_core.idempotency_receipts (
    id              uuid        PRIMARY KEY,
    workspace_id    uuid        NULL,
    principal_id    uuid        NOT NULL,
    operation       text        NOT NULL,      -- bus command name, e.g. "planning.publish_revision"
    key             text        NOT NULL,
    request_digest  text        NOT NULL,
    result_type     text        NOT NULL,      -- URN of the result DTO schema, e.g. "urn:skm:workspace:result:create-project:v1"
    result          jsonb       NOT NULL,      -- serialized result DTO returned on retry (deserialized by result_type)
    created_at      timestamptz NOT NULL,
    expires_at      timestamptz NOT NULL,
    -- uniqueness key of the instance-level (workspace_id IS NULL) commands: the nil UUID stands for "no workspace".
    -- GENERATED: never listed in INSERT.
    scope_key       uuid        GENERATED ALWAYS AS (coalesce(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid)) STORED,
    CONSTRAINT fk_idempotency_receipts__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT uq_idempotency_receipts__scope_key_principal_id_operation_key UNIQUE (scope_key, principal_id, operation, key),
    CONSTRAINT ck_idempotency_receipts__result_type CHECK (char_length(result_type) BETWEEN 1 AND 200),
    CONSTRAINT ck_idempotency_receipts__operation CHECK (operation ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),
    CONSTRAINT ck_idempotency_receipts__key CHECK (key ~ '^[A-Za-z0-9._:-]{1,200}$'),
    CONSTRAINT ck_idempotency_receipts__digest CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_idempotency_receipts__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_idempotency_receipts__result_size CHECK (octet_length(result::text) <= 1048576)
);

CREATE INDEX ix_idempotency_receipts__expires_at ON skm_core.idempotency_receipts (expires_at);

CREATE TABLE skm_core.audit_records (
    id            uuid        PRIMARY KEY,
    workspace_id  uuid        NULL,
    actor_id      uuid        NOT NULL,
    action        text        NOT NULL,         -- bus command/query name or "artifacts.upload_blob"
    target        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    decision      text        NOT NULL,
    reason_code   text        NULL,
    request_id    text        NOT NULL,
    recorded_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_audit_records__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT ck_audit_records__decision CHECK (decision IN ('allowed', 'denied')),
    CONSTRAINT ck_audit_records__reason CHECK ((decision = 'denied') = (reason_code IS NOT NULL)),
    CONSTRAINT ck_audit_records__target_object CHECK (jsonb_typeof(target) = 'object')
);

CREATE INDEX ix_audit_records__workspace_id_recorded_at ON skm_core.audit_records (workspace_id, recorded_at);
CREATE INDEX ix_audit_records__actor_id_recorded_at ON skm_core.audit_records (actor_id, recorded_at);

CREATE TRIGGER tg_audit_records__append_only BEFORE UPDATE OR DELETE ON skm_core.audit_records
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

SELECT skm_core.grant_app('skm_core', ARRAY['scopes','audit_records','domain_events']::text[]);  -- consumer_receipts: DELETE by outbox_gc (0003)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON skm_core.audit_records FROM skm_app;
    END IF;
END
$$;
