-- 0006_access_principals_tokens: principals, identities, API tokens, memberships.
-- Owner module: access. FKs only to skm_core (module graph: access has no dependencies).
CREATE SCHEMA IF NOT EXISTS skm_access;

CREATE TABLE skm_access.principals (
    id            uuid        PRIMARY KEY,
    kind          text        NOT NULL,
    display_name  text        NOT NULL,
    state         text        NOT NULL DEFAULT 'active',
    row_version   bigint      NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL,
    created_by    uuid        NULL,
    updated_at    timestamptz NOT NULL,
    password_hash bytea       NULL,
    CONSTRAINT ck_principals__password CHECK (
        password_hash IS NULL OR (kind = 'human' AND octet_length(password_hash) = 48)
    ),
    CONSTRAINT ck_principals__kind CHECK (kind IN ('human', 'service', 'worker')),
    CONSTRAINT ck_principals__state CHECK (state IN ('active', 'disabled')),
    CONSTRAINT ck_principals__display_name CHECK (char_length(display_name) BETWEEN 1 AND 200),
    CONSTRAINT ck_principals__row_version CHECK (row_version >= 1),
    CONSTRAINT fk_principals__created_by FOREIGN KEY (created_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT
);
CREATE INDEX ix_principals__kind_created_at ON skm_access.principals (kind, created_at, id);

CREATE TABLE skm_access.principal_identities (
    principal_id  uuid        NOT NULL,
    issuer        text        NOT NULL,
    subject       text        NOT NULL,
    created_at    timestamptz NOT NULL,
    CONSTRAINT pk_principal_identities PRIMARY KEY (issuer, subject),
    CONSTRAINT fk_principal_identities__principals FOREIGN KEY (principal_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_principal_identities__issuer CHECK (char_length(issuer) BETWEEN 1 AND 200),
    CONSTRAINT ck_principal_identities__subject CHECK (char_length(subject) BETWEEN 1 AND 300)
);
CREATE INDEX ix_principal_identities__principal_id ON skm_access.principal_identities (principal_id);

CREATE TABLE skm_access.api_tokens (
    id            uuid        PRIMARY KEY,
    principal_id  uuid        NOT NULL,
    kind          text        NOT NULL DEFAULT 'personal',
    name          text        NOT NULL,
    prefix        text        NOT NULL,
    secret_hash   bytea       NOT NULL,
    scope_id      uuid        NULL,
    permissions   text[]      NULL,
    expires_at    timestamptz NULL,
    created_at    timestamptz NOT NULL,
    created_by    uuid        NOT NULL,
    last_used_at  timestamptz NULL,
    revoked_at    timestamptz NULL,
    revoked_by    uuid        NULL,
    assignment_id uuid        NULL,
    step_id       uuid        NULL,
    superseded_by uuid        NULL,
    scope_grants  jsonb       NULL,
    assignment_scope_id uuid  NULL,
    worker_id     uuid        NULL,
    CONSTRAINT fk_api_tokens__assignment_scope FOREIGN KEY (assignment_scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT ck_api_tokens__scope_grants CHECK (scope_grants IS NULL OR (
        kind <> 'assignment' AND scope_id IS NULL AND permissions IS NULL AND jsonb_typeof(scope_grants) = 'object'
    )),
    CONSTRAINT ck_api_tokens__worker_binding CHECK (worker_id IS NULL OR kind = 'worker'),
    CONSTRAINT fk_api_tokens__principals FOREIGN KEY (principal_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_api_tokens__created_by FOREIGN KEY (created_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_api_tokens__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    -- deferred: rotate_token first marks the old token superseded (freeing its name), then inserts the new one
    CONSTRAINT fk_api_tokens__superseded_by FOREIGN KEY (superseded_by)
        REFERENCES skm_access.api_tokens (id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT uq_api_tokens__prefix UNIQUE (prefix),
    CONSTRAINT ck_api_tokens__kind CHECK (kind IN ('personal', 'worker', 'assignment')),
    -- worker and assignment tokens always expire (G20); assignment_id only on assignment tokens (no FK: execution is above access)
    CONSTRAINT ck_api_tokens__kind_expiry CHECK (kind = 'personal' OR expires_at IS NOT NULL),
    CONSTRAINT ck_api_tokens__assignment CHECK ((kind = 'assignment') = (assignment_id IS NOT NULL)),
    -- step_id binds an assignment token to the step whose runtime received it (record_step_note derives the claim from it)
    CONSTRAINT ck_api_tokens__step CHECK ((kind = 'assignment') = (step_id IS NOT NULL)),
    CONSTRAINT ck_api_tokens__assignment_scope CHECK (
        (kind = 'assignment') = (assignment_scope_id IS NOT NULL)
        AND (assignment_scope_id IS NULL OR (scope_id IS NOT NULL AND assignment_scope_id = scope_id))
    ),
    CONSTRAINT ck_api_tokens__superseded CHECK (superseded_by IS NULL OR (kind <> 'assignment' AND superseded_by <> id)),
    CONSTRAINT ck_api_tokens__prefix CHECK (prefix ~ '^(live_)?[a-z2-7]{8}$'),
    CONSTRAINT ck_api_tokens__secret_hash CHECK (octet_length(secret_hash) = 32),
    CONSTRAINT ck_api_tokens__name CHECK (name ~ '^[A-Za-z0-9 ._-]{1,100}$'),
    CONSTRAINT ck_api_tokens__revoked CHECK ((revoked_at IS NULL) = (revoked_by IS NULL)),
    CONSTRAINT ck_api_tokens__expiry CHECK (
        expires_at IS NULL OR expires_at > created_at
        OR (expires_at = created_at AND superseded_by IS NOT NULL)
    )
);
-- token names are unique among the not-revoked, not-superseded tokens of a principal (a rotated token keeps its name)
CREATE UNIQUE INDEX uq_api_tokens__principal_id_name_active
    ON skm_access.api_tokens (principal_id, name) WHERE revoked_at IS NULL AND superseded_by IS NULL;
CREATE INDEX ix_api_tokens__assignment_id ON skm_access.api_tokens (assignment_id) WHERE assignment_id IS NOT NULL;
CREATE INDEX ix_api_tokens__principal_id_created_at ON skm_access.api_tokens (principal_id, created_at, id);

-- Token kind follows the principal kind (domain rule; this trigger is the safety net):
-- worker principals hold worker/assignment tokens only, human/service principals hold personal tokens only.
CREATE FUNCTION skm_access.tg_api_tokens__kind() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    principal_kind text;
BEGIN
    SELECT kind INTO principal_kind FROM skm_access.principals WHERE id = NEW.principal_id;
    IF (principal_kind = 'worker') <> (NEW.kind IN ('worker', 'assignment')) THEN
        RAISE EXCEPTION 'token kind % does not match principal kind %', NEW.kind, principal_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind = 'assignment' AND NEW.assignment_scope_id IS NULL THEN
        NEW.assignment_scope_id := NEW.scope_id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tg_api_tokens__kind BEFORE INSERT ON skm_access.api_tokens
    FOR EACH ROW EXECUTE FUNCTION skm_access.tg_api_tokens__kind();

CREATE TABLE skm_access.memberships (
    scope_id      uuid        NOT NULL,
    principal_id  uuid        NOT NULL,
    role          text        NOT NULL,
    granted_by    uuid        NULL,
    granted_at    timestamptz NOT NULL,
    CONSTRAINT pk_memberships PRIMARY KEY (scope_id, principal_id),
    CONSTRAINT fk_memberships__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_memberships__principals FOREIGN KEY (principal_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_memberships__granted_by FOREIGN KEY (granted_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_memberships__role CHECK (role IN ('owner', 'maintainer', 'member', 'viewer', 'worker'))
);
CREATE INDEX ix_memberships__principal_id ON skm_access.memberships (principal_id);
CREATE INDEX ix_memberships__scope_id_role ON skm_access.memberships (scope_id, role);

-- The worker role is never granted on the instance scope (enforced in the domain; this trigger is the safety net).
CREATE FUNCTION skm_access.tg_memberships__worker_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.role = 'worker' AND EXISTS (
        SELECT 1 FROM skm_core.scopes s WHERE s.id = NEW.scope_id AND s.kind IN ('instance', 'host')
    ) THEN
        RAISE EXCEPTION 'worker role is not allowed on scope kind instance/host' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tg_memberships__worker_scope BEFORE INSERT OR UPDATE ON skm_access.memberships
    FOR EACH ROW EXECUTE FUNCTION skm_access.tg_memberships__worker_scope();

-- Worker ids are workspace-owned and assignment ids are execution-owned; access cannot reference either.
CREATE TABLE skm_access.web_sessions (
    id           uuid        PRIMARY KEY,
    principal_id uuid        NOT NULL REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    secret_hash  bytea       NOT NULL UNIQUE CHECK (octet_length(secret_hash) = 32),
    created_at   timestamptz NOT NULL,
    expires_at   timestamptz NOT NULL CHECK (expires_at > created_at),
    revoked_at   timestamptz NULL
);
CREATE INDEX ix_web_sessions__principal_id ON skm_access.web_sessions (principal_id);

CREATE TABLE skm_access.pairing_tokens (
    id                uuid        PRIMARY KEY,
    issuer_id         uuid        NOT NULL REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    issuer_token_id   uuid        NULL REFERENCES skm_access.api_tokens (id) ON DELETE RESTRICT,
    workspace_id      uuid        NOT NULL REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    secret_hash       bytea       NOT NULL UNIQUE CHECK (octet_length(secret_hash) = 32),
    binding           jsonb       NOT NULL CHECK (jsonb_typeof(binding) = 'object'),
    created_at        timestamptz NOT NULL,
    expires_at        timestamptz NOT NULL CHECK (expires_at > created_at),
    revoked_at        timestamptz NULL,
    consumed_at       timestamptz NULL,
    result_principal_id uuid      NULL REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    result_token_id   uuid        NULL REFERENCES skm_access.api_tokens (id) ON DELETE RESTRICT,
    result_worker_id  uuid        NULL,
    CONSTRAINT ck_pairing_tokens__consumed CHECK (
        (consumed_at IS NULL AND result_token_id IS NULL AND result_principal_id IS NULL AND result_worker_id IS NULL)
        OR (consumed_at IS NOT NULL AND result_token_id IS NOT NULL AND result_principal_id IS NOT NULL)
    )
);
CREATE INDEX ix_pairing_tokens__workspace ON skm_access.pairing_tokens (workspace_id);

CREATE FUNCTION skm_access.tg_keep_issued_binding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    mutable_columns text[] := string_to_array(TG_ARGV[0], ',');
BEGIN
    IF (to_jsonb(OLD) - mutable_columns) IS DISTINCT FROM (to_jsonb(NEW) - mutable_columns)
        OR (to_jsonb(OLD) ->> 'revoked_at' IS NOT NULL AND
            (to_jsonb(OLD) -> 'revoked_at', to_jsonb(OLD) -> 'revoked_by') IS DISTINCT FROM
            (to_jsonb(NEW) -> 'revoked_at', to_jsonb(NEW) -> 'revoked_by'))
        OR (to_jsonb(OLD) ->> 'consumed_at' IS NOT NULL AND OLD IS DISTINCT FROM NEW
            AND (to_jsonb(OLD) - 'revoked_at') IS DISTINCT FROM (to_jsonb(NEW) - 'revoked_at'))
    THEN
        RAISE EXCEPTION 'issued access bindings are immutable' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tg_api_tokens__immutable BEFORE UPDATE ON skm_access.api_tokens
    FOR EACH ROW EXECUTE FUNCTION skm_access.tg_keep_issued_binding(
        'name,expires_at,last_used_at,revoked_at,revoked_by,superseded_by'
    );
CREATE TRIGGER tg_web_sessions__immutable BEFORE UPDATE ON skm_access.web_sessions
    FOR EACH ROW EXECUTE FUNCTION skm_access.tg_keep_issued_binding('revoked_at');
CREATE TRIGGER tg_pairing_tokens__immutable BEFORE UPDATE ON skm_access.pairing_tokens
    FOR EACH ROW EXECUTE FUNCTION skm_access.tg_keep_issued_binding(
        'revoked_at,consumed_at,result_principal_id,result_token_id,result_worker_id'
    );

CREATE FUNCTION skm_access.tg_principals__first_password() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.password_hash IS NOT NULL AND OLD.password_hash IS DISTINCT FROM NEW.password_hash THEN
        RAISE EXCEPTION 'the first password has already been set' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tg_principals__first_password BEFORE UPDATE OF password_hash ON skm_access.principals
    FOR EACH ROW EXECUTE FUNCTION skm_access.tg_principals__first_password();

-- PostgreSQL delivers these secret-free invalidation hints after commit.
CREATE FUNCTION skm_access.tg_notify_access_changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('skm_access_changed', json_build_object(
        'table', TG_TABLE_NAME, 'id', COALESCE(to_jsonb(NEW)->>'id', to_jsonb(OLD)->>'id')
    )::text);
    RETURN NULL;
END $$;
CREATE TRIGGER tg_api_tokens__notify AFTER INSERT OR UPDATE OF expires_at, revoked_at, superseded_by
    ON skm_access.api_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();
CREATE TRIGGER tg_web_sessions__notify AFTER INSERT OR UPDATE OF revoked_at
    ON skm_access.web_sessions FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();
CREATE TRIGGER tg_pairing_tokens__notify AFTER INSERT OR UPDATE OF revoked_at, consumed_at
    ON skm_access.pairing_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();
CREATE TRIGGER tg_principals__notify AFTER UPDATE OF state, password_hash
    ON skm_access.principals FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();
CREATE TRIGGER tg_memberships__notify AFTER INSERT OR UPDATE OR DELETE
    ON skm_access.memberships FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();

SELECT skm_core.grant_app('skm_access', '{}'::text[]);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON ALL TABLES IN SCHEMA skm_access FROM skm_app;
        GRANT UPDATE (display_name, state, row_version, updated_at, password_hash) ON skm_access.principals TO skm_app;
        GRANT UPDATE (name, expires_at, last_used_at, revoked_at, revoked_by, superseded_by) ON skm_access.api_tokens TO skm_app;
        GRANT UPDATE (role, granted_by, granted_at), DELETE ON skm_access.memberships TO skm_app;
        GRANT UPDATE (revoked_at) ON skm_access.web_sessions TO skm_app;
        GRANT UPDATE (revoked_at, consumed_at, result_principal_id, result_token_id, result_worker_id)
            ON skm_access.pairing_tokens TO skm_app;
    END IF;
END $$;
