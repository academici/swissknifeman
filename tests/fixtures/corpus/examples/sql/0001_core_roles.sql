-- 0001_core_roles: application roles and the grant helper used by every module migration.
-- Dev mode: the bootstrap user (superuser `skm`) owns all objects; roles are created when allowed.
-- Server mode: an operator creates the roles beforehand if the migrating user lacks CREATEROLE (docs/guides/server-mode.md).

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND (rolsuper OR rolcreaterole)) THEN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
            CREATE ROLE skm_app NOLOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_migrator') THEN
            CREATE ROLE skm_migrator NOLOGIN;
        END IF;
    ELSE
        RAISE NOTICE 'skm: current user cannot create roles; create skm_app and skm_migrator manually for server mode';
    END IF;
END
$$;

-- Grants DML on a module schema to skm_app (if the role exists). Called at the end of every module migration:
--   SELECT skm_core.grant_app('skm_workspace', '{}'::text[]);
-- Every call supplies the cumulative list of append-only tables in this schema.
-- A later migration must not accidentally restore UPDATE/DELETE on earlier immutable data.
CREATE OR REPLACE FUNCTION skm_core.grant_app(schema_name text, append_only_tables text[] DEFAULT '{}') RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    table_name text;
BEGIN
    IF schema_name !~ '^skm_[a-z_]+$' THEN
        RAISE EXCEPTION 'skm: invalid schema name %', schema_name;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO skm_app', schema_name);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO skm_app', schema_name);
        EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO skm_app', schema_name);
        -- New tables start with read/append access; the owner migration grants mutable DML explicitly.
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE UPDATE, DELETE ON TABLES FROM skm_app', schema_name);
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT ON TABLES TO skm_app', schema_name);
        FOREACH table_name IN ARRAY append_only_tables LOOP
            IF table_name !~ '^[a-z][a-z0-9_]*$' THEN
                RAISE EXCEPTION 'skm: invalid append-only table name %', table_name;
            END IF;
            EXECUTE format('REVOKE UPDATE, DELETE ON TABLE %I.%I FROM skm_app', schema_name, table_name);
        END LOOP;
        IF schema_name = 'skm_core' THEN
            -- Application commands can only read the migration history and baseline.
            REVOKE ALL PRIVILEGES ON skm_core.schema_migrations, skm_core.schema_baseline FROM skm_app;
            GRANT SELECT ON skm_core.schema_migrations, skm_core.schema_baseline TO skm_app;
        END IF;
    END IF;
END
$$;

-- Shared trigger function for append-only tables (domain_events, audit_records, entry_history, …).
CREATE OR REPLACE FUNCTION skm_core.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skm: % on %.% is forbidden (append-only)', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

-- Shared trigger function for immutable rows (scopes, plan_revisions, file_versions, …): UPDATE is forbidden, DELETE too.
CREATE OR REPLACE FUNCTION skm_core.forbid_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skm: rows of %.% are immutable', TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

SELECT skm_core.grant_app('skm_core', '{}'::text[]);
