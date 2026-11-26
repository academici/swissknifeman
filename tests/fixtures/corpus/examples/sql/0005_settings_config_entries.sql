-- 0005_settings_config_entries — schema skm_config (module `settings`).
-- Depends on 0002_core_scopes (skm_core.scopes). Applied by `skm db migrate` in one transaction.
-- Ownership: settings module. Readers: adapters/postgres/config_store.py (ConfigStore, ScopeTree),
-- adapters/postgres/settings/repositories.py (ConfigEntryRepository, ConfigHistoryRepository).

CREATE SCHEMA IF NOT EXISTS skm_config;

-- One stored contribution of one level for one key. Levels default/pack/invocation are never stored here.
CREATE TABLE skm_config.entries (
    id           uuid        PRIMARY KEY,
    scope_id     uuid        NOT NULL,
    key          text        NOT NULL,
    op           text        NOT NULL,
    value        jsonb       NULL,
    locked       boolean     NOT NULL DEFAULT false,
    row_version  bigint      NOT NULL DEFAULT 1,
    reason       text        NOT NULL DEFAULT '',
    created_by   uuid        NOT NULL,          -- principal id (skm_access is a sibling module: no FK, see spec/modules/settings.md §11)
    created_at   timestamptz NOT NULL,
    updated_by   uuid        NOT NULL,
    updated_at   timestamptz NOT NULL,
    CONSTRAINT fk_entries__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT uq_entries__scope_id_key UNIQUE (scope_id, key),
    CONSTRAINT ck_entries__key CHECK (key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$'),
    CONSTRAINT ck_entries__op CHECK (op IN ('set', 'unset', 'append')),
    CONSTRAINT ck_entries__op_value CHECK ((op = 'unset') = (value IS NULL)),
    CONSTRAINT ck_entries__append_array CHECK (op <> 'append' OR jsonb_typeof(value) = 'array'),
    CONSTRAINT ck_entries__value_size CHECK (value IS NULL OR octet_length(value::text) <= 65536),
    CONSTRAINT ck_entries__row_version CHECK (row_version >= 1),
    CONSTRAINT ck_entries__reason_len CHECK (char_length(reason) <= 2000)
);

-- "which scopes set this key" (explain across scopes, doctor: unknown keys after a registry change)
CREATE INDEX ix_entries__key ON skm_config.entries (key);

-- Append-only history of every change of an entry (including removal). entry_id has no FK: the entry may be gone.
CREATE TABLE skm_config.entry_history (
    id           uuid        PRIMARY KEY,
    entry_id     uuid        NOT NULL,
    scope_id     uuid        NOT NULL,
    key          text        NOT NULL,
    change_kind  text        NOT NULL,
    old_op       text        NULL,
    old_value    jsonb       NULL,
    old_locked   boolean     NULL,
    new_op       text        NULL,
    new_value    jsonb       NULL,
    new_locked   boolean     NULL,
    actor_id     uuid        NOT NULL,
    request_id   text        NULL,
    reason       text        NOT NULL DEFAULT '',
    generation   bigint      NOT NULL,
    changed_at   timestamptz NOT NULL,
    CONSTRAINT fk_entry_history__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT ck_entry_history__change_kind CHECK (change_kind IN ('created', 'updated', 'removed', 'locked', 'unlocked')),
    CONSTRAINT ck_entry_history__old_op CHECK (old_op IS NULL OR old_op IN ('set', 'unset', 'append')),
    CONSTRAINT ck_entry_history__new_op CHECK (new_op IS NULL OR new_op IN ('set', 'unset', 'append')),
    CONSTRAINT ck_entry_history__shape CHECK (
        (change_kind = 'created' AND old_op IS NULL AND new_op IS NOT NULL) OR
        (change_kind = 'removed' AND old_op IS NOT NULL AND new_op IS NULL) OR
        (change_kind IN ('updated', 'locked', 'unlocked') AND old_op IS NOT NULL AND new_op IS NOT NULL))
);

CREATE INDEX ix_entry_history__scope_id_key_changed_at ON skm_config.entry_history (scope_id, key, changed_at DESC, id DESC);
CREATE INDEX ix_entry_history__changed_at ON skm_config.entry_history (changed_at DESC, id DESC);

CREATE FUNCTION skm_config.tg_entry_history__append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skm_config.entry_history is append-only' USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER tg_entry_history__append_only
    BEFORE UPDATE OR DELETE ON skm_config.entry_history
    FOR EACH ROW EXECUTE FUNCTION skm_config.tg_entry_history__append_only();

-- Single-row counter. Every transaction that writes entries runs
--   UPDATE skm_config.generation SET value = value + 1 WHERE id = 1 RETURNING value
-- (row lock serializes config writers; readers cache EffectiveConfig by this value).
CREATE TABLE skm_config.generation (
    id     smallint PRIMARY KEY DEFAULT 1,
    value  bigint   NOT NULL DEFAULT 0,
    CONSTRAINT ck_generation__single CHECK (id = 1),
    CONSTRAINT ck_generation__value CHECK (value >= 0)
);

INSERT INTO skm_config.generation (id, value) VALUES (1, 0);

CREATE FUNCTION skm_config.tg_generation__no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skm_config.generation row cannot be deleted' USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER tg_generation__no_delete
    BEFORE DELETE ON skm_config.generation
    FOR EACH ROW EXECUTE FUNCTION skm_config.tg_generation__no_delete();

-- Privileges (narrower than skm_core.grant_app): skm_app reads and writes entries, inserts history, updates the counter.
-- Guarded like grant_app: in server mode without CREATEROLE the operator creates skm_app beforehand (0001).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        GRANT USAGE ON SCHEMA skm_config TO skm_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON skm_config.entries TO skm_app;
        GRANT SELECT, INSERT ON skm_config.entry_history TO skm_app;
        GRANT SELECT, UPDATE ON skm_config.generation TO skm_app;
    END IF;
END
$$;
