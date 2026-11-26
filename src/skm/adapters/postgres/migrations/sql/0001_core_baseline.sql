-- SKM 0.1.0 project database baseline. Runner bookkeeping is created by runner_bootstrap.sql.
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

CREATE SCHEMA skm_access;

CREATE SCHEMA skm_artifacts;

CREATE SCHEMA skm_config;

CREATE SCHEMA skm_context;

CREATE SCHEMA skm_execution;

CREATE SCHEMA skm_exports;

CREATE SCHEMA skm_extensions;

CREATE SCHEMA skm_integrations;

CREATE SCHEMA skm_knowledge;

CREATE SCHEMA skm_learning;

CREATE SCHEMA skm_planning;

CREATE SCHEMA skm_policy;

CREATE SCHEMA skm_runtimes;

CREATE SCHEMA skm_workspace;

CREATE FUNCTION skm_access.tg_api_tokens__kind() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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

CREATE FUNCTION skm_access.tg_keep_issued_binding() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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

CREATE FUNCTION skm_access.tg_memberships__worker_scope() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.role = 'worker' AND EXISTS (
        SELECT 1 FROM skm_core.scopes s WHERE s.id = NEW.scope_id AND s.kind IN ('instance', 'host')
    ) THEN
        RAISE EXCEPTION 'worker role is not allowed on scope kind instance/host' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION skm_access.tg_notify_access_changed() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    PERFORM pg_notify('skm_access_changed', json_build_object(
        'table', TG_TABLE_NAME, 'id', COALESCE(to_jsonb(NEW)->>'id', to_jsonb(OLD)->>'id')
    )::text);
    RETURN NULL;
END $$;

CREATE FUNCTION skm_access.tg_principals__first_password() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF OLD.password_hash IS NOT NULL AND OLD.password_hash IS DISTINCT FROM NEW.password_hash THEN
        RAISE EXCEPTION 'the first password has already been set' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION skm_artifacts.tg_file_versions__immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'file versions are immutable' USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION skm_config.tg_entry_history__append_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'skm_config.entry_history is append-only' USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE FUNCTION skm_config.tg_generation__no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'skm_config.generation row cannot be deleted' USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE FUNCTION skm_context.check_standalone_entity() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.step_ref IS NULL AND NEW.entity_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM skm_planning.revision_members m
        WHERE (m.workspace_id, m.plan_id, m.revision_id, m.entity_id) =
              (NEW.workspace_id, NEW.plan_id, NEW.revision_id, NEW.entity_id)
    ) THEN
        RAISE EXCEPTION 'skm: standalone manifest entity does not belong to the revision'
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_context_manifests__standalone_entity';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_context.tg_context_manifests__finalize_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'skm: context manifests are never deleted' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.state <> 'draft' OR NEW.state <> 'final' THEN
        RAISE EXCEPTION 'skm: context manifest % -> % is not allowed', OLD.state, NEW.state USING ERRCODE = 'restrict_violation';
    END IF;
    IF (NEW.id, NEW.workspace_id, NEW.project_id, NEW.plan_id, NEW.revision_id, NEW.entity_id, NEW.role, NEW.stage_id,
        NEW.step_ref, NEW.owner_ref, NEW.attempt_no, NEW.round_no, NEW.agent_profile_version_id, NEW.runtime_id, NEW.model,
        NEW.draft_digest, NEW.total_limit, NEW.host_inputs, NEW.estimator_id, NEW.assembler_version, NEW.created_at)
       IS DISTINCT FROM
       (OLD.id, OLD.workspace_id, OLD.project_id, OLD.plan_id, OLD.revision_id, OLD.entity_id, OLD.role, OLD.stage_id,
        OLD.step_ref, OLD.owner_ref, OLD.attempt_no, OLD.round_no, OLD.agent_profile_version_id, OLD.runtime_id, OLD.model,
        OLD.draft_digest, OLD.total_limit, OLD.host_inputs, OLD.estimator_id, OLD.assembler_version, OLD.created_at) THEN
        RAISE EXCEPTION 'skm: finalization may not change draft fields' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_core.check_scope_parent() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    parent_kind text;
    parent_workspace uuid;
    expected text[];
BEGIN
    IF NEW.kind = 'instance' THEN
        RETURN NEW;
    END IF;
    SELECT kind, workspace_id INTO parent_kind, parent_workspace FROM skm_core.scopes WHERE id = NEW.parent_id;
    expected := CASE NEW.kind
        WHEN 'workspace' THEN ARRAY['instance']
        WHEN 'host' THEN ARRAY['instance']
        WHEN 'project' THEN ARRAY['workspace']
        WHEN 'plan' THEN ARRAY['project']
        WHEN 'run' THEN ARRAY['plan', 'project']
    END;
    IF (parent_kind = ANY(expected)) IS NOT TRUE THEN
        RAISE EXCEPTION 'skm: scope of kind % needs a parent of kind %, got %', NEW.kind, expected, parent_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind IN ('project', 'plan', 'run') AND NEW.workspace_id IS DISTINCT FROM parent_workspace THEN
        RAISE EXCEPTION 'skm: scope % must belong to workspace % of its parent', NEW.id, parent_workspace
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_core.forbid_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'skm: % on %.% is forbidden (append-only)', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE FUNCTION skm_core.forbid_row_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'skm: UPDATE on %.% is forbidden', TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE FUNCTION skm_core.forbid_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'skm: rows of %.% are immutable', TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE FUNCTION skm_core.grant_app(schema_name text, append_only_tables text[] DEFAULT '{}'::text[]) RETURNS void
    LANGUAGE plpgsql
    AS $_$
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
$_$;

CREATE FUNCTION skm_execution.check_run_binding() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM skm_core.scopes s
        WHERE s.id = NEW.id AND s.kind = 'run' AND s.workspace_id = NEW.workspace_id
          AND s.parent_id = CASE WHEN NEW.kind = 'adhoc' THEN NEW.project_id ELSE NEW.plan_id END
    ) THEN
        RAISE EXCEPTION 'skm: run scope does not match run %', NEW.id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_runs__scope_binding';
    END IF;
    IF NEW.kind = 'adhoc' AND NOT EXISTS (
        SELECT 1 FROM skm_artifacts.file_versions v
        JOIN skm_artifacts.files f ON (f.workspace_id, f.id) = (v.workspace_id, v.file_id)
        WHERE v.workspace_id = NEW.workspace_id AND v.id = NEW.inline_spec_file_version_id
          AND f.project_id = NEW.project_id
    ) THEN
        RAISE EXCEPTION 'skm: inline spec does not belong to the project of run %', NEW.id
            USING ERRCODE = 'check_violation', CONSTRAINT = 'ck_runs__inline_spec_project';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_execution.guard_assignment_reconcile_binding() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.reconcile_effect_id IS DISTINCT FROM OLD.reconcile_effect_id THEN
        RAISE EXCEPTION 'skm: assignment reconcile effect binding is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_execution.guard_step_observation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.route_snapshot IS DISTINCT FROM OLD.route_snapshot THEN
        RAISE EXCEPTION 'skm: step route snapshot is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.runtime_observation IS NULL AND NEW.runtime_observation IS NOT NULL
       AND OLD.state <> 'started' THEN
        RAISE EXCEPTION 'skm: late observation on a terminal step is forbidden'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.runtime_observation IS NOT NULL
       AND NEW.runtime_observation IS DISTINCT FROM OLD.runtime_observation THEN
        RAISE EXCEPTION 'skm: terminal runtime observation is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_execution.tg_assignment_leases__fence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE a record;
BEGIN
    SELECT state, last_fencing_token, workspace_id INTO a FROM skm_execution.assignments WHERE id = NEW.assignment_id;
    IF a.state <> 'leased' OR a.last_fencing_token <> NEW.fencing_token OR a.workspace_id <> NEW.workspace_id THEN
        RAISE EXCEPTION 'skm_execution.assignment_leases: lease token % does not match assignment % (state %, token %)',
            NEW.fencing_token, NEW.assignment_id, a.state, a.last_fencing_token USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION skm_execution.tg_decision_records__supersede_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status <> 'applied' OR NEW.status <> 'superseded'
       OR (to_jsonb(NEW) - 'status' - 'superseded_at') <> (to_jsonb(OLD) - 'status' - 'superseded_at') THEN
        RAISE EXCEPTION 'skm_execution.decision_records: only applied -> superseded is allowed' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION skm_execution.tg_run_recoveries__frozen() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.outcome IS NOT NULL THEN
        RAISE EXCEPTION 'skm_execution.run_recoveries: finished recovery records are immutable' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION skm_extensions.tg_pack_versions__state_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'skm: pack versions are never deleted (retire them)' USING ERRCODE = 'restrict_violation';
    END IF;
    IF (NEW.id, NEW.pack_id, NEW.version, NEW.digest, NEW.manifest, NEW.priority, NEW.origin, NEW.installed_at, NEW.installed_by)
       IS DISTINCT FROM
       (OLD.id, OLD.pack_id, OLD.version, OLD.digest, OLD.manifest, OLD.priority, OLD.origin, OLD.installed_at, OLD.installed_by) THEN
        RAISE EXCEPTION 'skm: only state of a pack version may change' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NOT (OLD.state = 'active' AND NEW.state = 'retired') AND OLD.state <> NEW.state THEN
        RAISE EXCEPTION 'skm: pack version state % -> % is not allowed', OLD.state, NEW.state USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE FUNCTION skm_planning.tg_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'skm_planning.%: rows are immutable (published revision content)', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE FUNCTION skm_planning.tg_material_has_pin() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.kind = 'file_version' AND NOT EXISTS (
        SELECT 1 FROM skm_planning.revision_file_bindings b
        WHERE b.revision_id = NEW.revision_id AND b.material_id = NEW.material_id) THEN
        RAISE EXCEPTION 'material % of revision % has no file version pin', NEW.material_id, NEW.revision_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION skm_planning.tg_member_kind_matches_identity() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM skm_planning.plan_entity_identities i
                   WHERE i.plan_id = NEW.plan_id AND i.entity_id = NEW.entity_id AND i.entity_kind = NEW.entity_kind) THEN
        RAISE EXCEPTION 'entity % changes kind to %', NEW.entity_id, NEW.entity_kind USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION skm_policy.tg_approvals__append_only() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'approvals are append-only' USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.used_at IS NOT NULL OR NEW.used_at IS NULL
        OR (to_jsonb(NEW) - 'used_at') IS DISTINCT FROM (to_jsonb(OLD) - 'used_at') THEN
        RAISE EXCEPTION 'approvals allow only a single used_at update' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;

CREATE TABLE skm_access.api_tokens (
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    kind text DEFAULT 'personal'::text NOT NULL,
    name text NOT NULL,
    prefix text NOT NULL,
    secret_hash bytea NOT NULL,
    scope_id uuid,
    permissions text[],
    expires_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    created_by uuid NOT NULL,
    last_used_at timestamp with time zone,
    revoked_at timestamp with time zone,
    revoked_by uuid,
    assignment_id uuid,
    step_id uuid,
    superseded_by uuid,
    scope_grants jsonb,
    assignment_scope_id uuid,
    worker_id uuid,
    CONSTRAINT ck_api_tokens__assignment CHECK (((kind = 'assignment'::text) = (assignment_id IS NOT NULL))),
    CONSTRAINT ck_api_tokens__assignment_scope CHECK ((((kind = 'assignment'::text) = (assignment_scope_id IS NOT NULL)) AND ((assignment_scope_id IS NULL) OR ((scope_id IS NOT NULL) AND (assignment_scope_id = scope_id))))),
    CONSTRAINT ck_api_tokens__expiry CHECK (((expires_at IS NULL) OR (expires_at > created_at) OR ((expires_at = created_at) AND (superseded_by IS NOT NULL)))),
    CONSTRAINT ck_api_tokens__kind CHECK ((kind = ANY (ARRAY['personal'::text, 'worker'::text, 'assignment'::text]))),
    CONSTRAINT ck_api_tokens__kind_expiry CHECK (((kind = 'personal'::text) OR (expires_at IS NOT NULL))),
    CONSTRAINT ck_api_tokens__name CHECK ((name ~ '^[A-Za-z0-9 ._-]{1,100}$'::text)),
    CONSTRAINT ck_api_tokens__prefix CHECK ((prefix ~ '^(live_)?[a-z2-7]{8}$'::text)),
    CONSTRAINT ck_api_tokens__revoked CHECK (((revoked_at IS NULL) = (revoked_by IS NULL))),
    CONSTRAINT ck_api_tokens__scope_grants CHECK (((scope_grants IS NULL) OR ((kind <> 'assignment'::text) AND (scope_id IS NULL) AND (permissions IS NULL) AND (jsonb_typeof(scope_grants) = 'object'::text)))),
    CONSTRAINT ck_api_tokens__secret_hash CHECK ((octet_length(secret_hash) = 32)),
    CONSTRAINT ck_api_tokens__step CHECK (((kind = 'assignment'::text) = (step_id IS NOT NULL))),
    CONSTRAINT ck_api_tokens__superseded CHECK (((superseded_by IS NULL) OR ((kind <> 'assignment'::text) AND (superseded_by <> id)))),
    CONSTRAINT ck_api_tokens__worker_binding CHECK (((worker_id IS NULL) OR (kind = 'worker'::text)))
);

CREATE TABLE skm_access.memberships (
    scope_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    role text NOT NULL,
    granted_by uuid,
    granted_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_memberships__role CHECK ((role = ANY (ARRAY['owner'::text, 'maintainer'::text, 'member'::text, 'viewer'::text, 'worker'::text])))
);

CREATE TABLE skm_access.pairing_tokens (
    id uuid NOT NULL,
    issuer_id uuid NOT NULL,
    issuer_token_id uuid,
    workspace_id uuid NOT NULL,
    secret_hash bytea NOT NULL,
    binding jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    consumed_at timestamp with time zone,
    result_principal_id uuid,
    result_token_id uuid,
    result_worker_id uuid,
    CONSTRAINT ck_pairing_tokens__consumed CHECK ((((consumed_at IS NULL) AND (result_token_id IS NULL) AND (result_principal_id IS NULL) AND (result_worker_id IS NULL)) OR ((consumed_at IS NOT NULL) AND (result_token_id IS NOT NULL) AND (result_principal_id IS NOT NULL)))),
    CONSTRAINT pairing_tokens_binding_check CHECK ((jsonb_typeof(binding) = 'object'::text)),
    CONSTRAINT pairing_tokens_check CHECK ((expires_at > created_at)),
    CONSTRAINT pairing_tokens_secret_hash_check CHECK ((octet_length(secret_hash) = 32))
);

CREATE TABLE skm_access.principal_identities (
    principal_id uuid NOT NULL,
    issuer text NOT NULL,
    subject text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_principal_identities__issuer CHECK (((char_length(issuer) >= 1) AND (char_length(issuer) <= 200))),
    CONSTRAINT ck_principal_identities__subject CHECK (((char_length(subject) >= 1) AND (char_length(subject) <= 300)))
);

CREATE TABLE skm_access.principals (
    id uuid NOT NULL,
    kind text NOT NULL,
    display_name text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    created_by uuid,
    updated_at timestamp with time zone NOT NULL,
    password_hash bytea,
    CONSTRAINT ck_principals__display_name CHECK (((char_length(display_name) >= 1) AND (char_length(display_name) <= 200))),
    CONSTRAINT ck_principals__kind CHECK ((kind = ANY (ARRAY['human'::text, 'service'::text, 'worker'::text]))),
    CONSTRAINT ck_principals__password CHECK (((password_hash IS NULL) OR ((kind = 'human'::text) AND (octet_length(password_hash) = 48)))),
    CONSTRAINT ck_principals__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_principals__state CHECK ((state = ANY (ARRAY['active'::text, 'disabled'::text])))
);

CREATE TABLE skm_access.web_sessions (
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    secret_hash bytea NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT web_sessions_check CHECK ((expires_at > created_at)),
    CONSTRAINT web_sessions_secret_hash_check CHECK ((octet_length(secret_hash) = 32))
);

CREATE TABLE skm_artifacts.access_grants (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    reason text NOT NULL,
    ref text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_access_grants__expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_access_grants__reason CHECK ((reason = ANY (ARRAY['assignment'::text, 'share'::text]))),
    CONSTRAINT ck_access_grants__ref CHECK (((char_length(ref) >= 1) AND (char_length(ref) <= 200)))
);

CREATE TABLE skm_artifacts.blob_locations (
    workspace_id uuid NOT NULL,
    blob_id uuid NOT NULL,
    backend_id text NOT NULL,
    storage_key text NOT NULL,
    storage_version text,
    state text DEFAULT 'present'::text NOT NULL,
    verified_at timestamp with time zone,
    CONSTRAINT ck_blob_locations__state CHECK ((state = ANY (ARRAY['present'::text, 'missing'::text])))
);

CREATE TABLE skm_artifacts.blobs (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    hash_algorithm text DEFAULT 'sha256'::text NOT NULL,
    content_digest text NOT NULL,
    size_bytes bigint NOT NULL,
    detected_media_type text NOT NULL,
    availability text DEFAULT 'available'::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    verified_at timestamp with time zone,
    CONSTRAINT ck_blobs__algorithm CHECK ((hash_algorithm = 'sha256'::text)),
    CONSTRAINT ck_blobs__availability CHECK ((availability = ANY (ARRAY['available'::text, 'missing'::text]))),
    CONSTRAINT ck_blobs__digest CHECK ((content_digest ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_blobs__size CHECK ((size_bytes >= 0))
);

CREATE TABLE skm_artifacts.file_versions (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    file_id uuid NOT NULL,
    version_no integer NOT NULL,
    blob_id uuid NOT NULL,
    original_filename text NOT NULL,
    declared_media_type text,
    description text DEFAULT ''::text NOT NULL,
    source jsonb NOT NULL,
    safety jsonb NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_file_versions__description CHECK ((char_length(description) <= 2000)),
    CONSTRAINT ck_file_versions__filename CHECK ((((octet_length(original_filename) >= 1) AND (octet_length(original_filename) <= 255)) AND (original_filename !~ '[/\\[:cntrl:]]'::text) AND (original_filename <> ALL (ARRAY['.'::text, '..'::text])))),
    CONSTRAINT ck_file_versions__safety_size CHECK ((octet_length((safety)::text) < 65536)),
    CONSTRAINT ck_file_versions__source_size CHECK ((octet_length((source)::text) < 4096)),
    CONSTRAINT ck_file_versions__version_no CHECK ((version_no >= 1))
);

CREATE TABLE skm_artifacts.files (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    title text NOT NULL,
    origin text NOT NULL,
    classification text NOT NULL,
    current_version_id uuid,
    state text DEFAULT 'active'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    created_by uuid NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_files__classification CHECK ((classification = ANY (ARRAY['public'::text, 'internal'::text, 'confidential'::text, 'restricted'::text]))),
    CONSTRAINT ck_files__origin CHECK ((origin = ANY (ARRAY['upload'::text, 'evidence'::text, 'transcript'::text, 'patch'::text, 'report'::text, 'import'::text, 'capture'::text]))),
    CONSTRAINT ck_files__state CHECK ((state = ANY (ARRAY['active'::text, 'trashed'::text]))),
    CONSTRAINT ck_files__title CHECK (((char_length(title) >= 1) AND (char_length(title) <= 300)))
);

CREATE TABLE skm_artifacts.staged_blobs (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    content_digest text NOT NULL,
    size_bytes bigint NOT NULL,
    media_type text NOT NULL,
    detected_media_type text NOT NULL,
    backend_id text NOT NULL,
    storage_key text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    consumed_request_id text,
    CONSTRAINT ck_staged_blobs__consumed CHECK (((consumed_at IS NULL) = (consumed_request_id IS NULL))),
    CONSTRAINT ck_staged_blobs__digest CHECK ((content_digest ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_staged_blobs__expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_staged_blobs__size CHECK ((size_bytes >= 0))
);

CREATE TABLE skm_artifacts.storage_backends (
    id text NOT NULL,
    kind text NOT NULL,
    config_ref text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_storage_backends__id CHECK ((id ~ '^[a-z][a-z0-9-]{1,31}$'::text)),
    CONSTRAINT ck_storage_backends__kind CHECK ((kind = ANY (ARRAY['local'::text, 's3'::text]))),
    CONSTRAINT ck_storage_backends__state CHECK ((state = ANY (ARRAY['active'::text, 'readonly'::text, 'retired'::text])))
);

CREATE TABLE skm_config.entries (
    id uuid NOT NULL,
    scope_id uuid NOT NULL,
    key text NOT NULL,
    op text NOT NULL,
    value jsonb,
    locked boolean DEFAULT false NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_by uuid NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_entries__append_array CHECK (((op <> 'append'::text) OR (jsonb_typeof(value) = 'array'::text))),
    CONSTRAINT ck_entries__key CHECK ((key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$'::text)),
    CONSTRAINT ck_entries__op CHECK ((op = ANY (ARRAY['set'::text, 'unset'::text, 'append'::text]))),
    CONSTRAINT ck_entries__op_value CHECK (((op = 'unset'::text) = (value IS NULL))),
    CONSTRAINT ck_entries__reason_len CHECK ((char_length(reason) <= 2000)),
    CONSTRAINT ck_entries__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_entries__value_size CHECK (((value IS NULL) OR (octet_length((value)::text) <= 65536)))
);

CREATE TABLE skm_config.entry_history (
    id uuid NOT NULL,
    entry_id uuid NOT NULL,
    scope_id uuid NOT NULL,
    key text NOT NULL,
    change_kind text NOT NULL,
    old_op text,
    old_value jsonb,
    old_locked boolean,
    new_op text,
    new_value jsonb,
    new_locked boolean,
    actor_id uuid NOT NULL,
    request_id text,
    reason text DEFAULT ''::text NOT NULL,
    generation bigint NOT NULL,
    changed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_entry_history__change_kind CHECK ((change_kind = ANY (ARRAY['created'::text, 'updated'::text, 'removed'::text, 'locked'::text, 'unlocked'::text]))),
    CONSTRAINT ck_entry_history__new_op CHECK (((new_op IS NULL) OR (new_op = ANY (ARRAY['set'::text, 'unset'::text, 'append'::text])))),
    CONSTRAINT ck_entry_history__old_op CHECK (((old_op IS NULL) OR (old_op = ANY (ARRAY['set'::text, 'unset'::text, 'append'::text])))),
    CONSTRAINT ck_entry_history__shape CHECK ((((change_kind = 'created'::text) AND (old_op IS NULL) AND (new_op IS NOT NULL)) OR ((change_kind = 'removed'::text) AND (old_op IS NOT NULL) AND (new_op IS NULL)) OR ((change_kind = ANY (ARRAY['updated'::text, 'locked'::text, 'unlocked'::text])) AND (old_op IS NOT NULL) AND (new_op IS NOT NULL))))
);

CREATE TABLE skm_config.generation (
    id smallint DEFAULT 1 NOT NULL,
    value bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_generation__single CHECK ((id = 1)),
    CONSTRAINT ck_generation__value CHECK ((value >= 0))
);

CREATE TABLE skm_context.context_blocks (
    manifest_id uuid NOT NULL,
    ordinal integer NOT NULL,
    block_ref text NOT NULL,
    "position" integer,
    block_type text NOT NULL,
    budget_class text NOT NULL,
    mandatory boolean NOT NULL,
    source_kind text NOT NULL,
    source_ref text NOT NULL,
    atomic_group text,
    source_version text,
    trust text NOT NULL,
    tokens_estimate integer,
    content_digest text,
    included boolean,
    reason text NOT NULL,
    detail text,
    content_stored boolean NOT NULL,
    research_query_ids uuid[],
    CONSTRAINT ck_context_blocks__atomic_group CHECK (((atomic_group IS NULL) OR ((char_length(atomic_group) >= 1) AND (char_length(atomic_group) <= 200)))),
    CONSTRAINT ck_context_blocks__block_ref CHECK ((block_ref ~ '^(d:[0-9]+|c:[0-9]+|x:[0-9]+|h:hi:[0-9]+)$'::text)),
    CONSTRAINT ck_context_blocks__block_type CHECK ((block_type = ANY (ARRAY['resume_note'::text, 'system_constraints'::text, 'role_contract'::text, 'run_rules'::text, 'runtime_notes'::text, 'task_contract'::text, 'acceptance'::text, 'requirements'::text, 'decisions'::text, 'decision_answers'::text, 'review_feedback'::text, 'previous_attempt'::text, 'candidate_diff'::text, 'findings_under_review'::text, 'context_map'::text, 'steering'::text, 'skills'::text, 'skill_index'::text, 'materials'::text, 'repo_instructions'::text, 'research'::text, 'memory'::text, 'history'::text, 'result_contract'::text]))),
    CONSTRAINT ck_context_blocks__budget_class CHECK ((budget_class = ANY (ARRAY['core'::text, 'task'::text, 'supporting'::text, 'retrieval'::text]))),
    CONSTRAINT ck_context_blocks__content_digest CHECK (((content_digest IS NULL) OR (content_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_context_blocks__position CHECK ((((included IS TRUE) = ("position" IS NOT NULL)) AND (("position" IS NULL) OR ("position" >= 0)))),
    CONSTRAINT ck_context_blocks__source_kind CHECK ((source_kind = ANY (ARRAY['spec'::text, 'resource'::text, 'file_version'::text, 'execution'::text, 'memory'::text, 'core'::text, 'external'::text, 'repository_path'::text]))),
    CONSTRAINT ck_context_blocks__stored CHECK (((NOT content_stored) OR (content_digest IS NOT NULL))),
    CONSTRAINT ck_context_blocks__tokens CHECK (((tokens_estimate IS NULL) OR (tokens_estimate >= 0))),
    CONSTRAINT ck_context_blocks__trust CHECK ((trust = ANY (ARRAY['system'::text, 'operator'::text, 'project'::text, 'repository'::text, 'model'::text, 'external'::text, 'third_party'::text, 'memory'::text])))
);

CREATE TABLE skm_context.context_manifests (
    id uuid NOT NULL,
    state text DEFAULT 'draft'::text NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    plan_id uuid,
    revision_id uuid,
    entity_id uuid,
    role text NOT NULL,
    stage_id text NOT NULL,
    step_ref text,
    owner_ref text NOT NULL,
    attempt_no integer NOT NULL,
    round_no integer NOT NULL,
    agent_profile_version_id uuid NOT NULL,
    runtime_id text NOT NULL,
    model text NOT NULL,
    route jsonb NOT NULL,
    draft_digest text NOT NULL,
    mode text,
    task_digest text,
    prompt_digest text,
    prompt_file_version_id uuid,
    total_tokens_estimate integer,
    total_limit integer NOT NULL,
    budgets jsonb NOT NULL,
    host_inputs jsonb NOT NULL,
    host_facts jsonb,
    skills_trace jsonb NOT NULL,
    diagnostics jsonb DEFAULT '[]'::jsonb NOT NULL,
    estimator_id text NOT NULL,
    assembler_version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    finalized_at timestamp with time zone,
    CONSTRAINT ck_context_manifests__digests CHECK (((draft_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND ((task_digest IS NULL) OR (task_digest ~ '^sha256:[0-9a-f]{64}$'::text)) AND ((prompt_digest IS NULL) OR (prompt_digest ~ '^sha256:[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_context_manifests__estimator_id CHECK ((estimator_id = 'heuristic-v1'::text)),
    CONSTRAINT ck_context_manifests__final_fields CHECK ((((state = 'draft'::text) AND (mode IS NULL) AND (task_digest IS NULL) AND (prompt_digest IS NULL) AND (prompt_file_version_id IS NULL) AND (total_tokens_estimate IS NULL) AND (finalized_at IS NULL)) OR ((state = 'final'::text) AND (mode IS NOT NULL) AND (task_digest IS NOT NULL) AND (prompt_digest IS NOT NULL) AND (prompt_file_version_id IS NOT NULL) AND (total_tokens_estimate IS NOT NULL) AND (finalized_at IS NOT NULL)))),
    CONSTRAINT ck_context_manifests__mode CHECK (((mode IS NULL) OR (mode = ANY (ARRAY['full'::text, 'delta'::text])))),
    CONSTRAINT ck_context_manifests__numbers CHECK (((attempt_no >= 1) AND (round_no >= 1) AND (total_limit >= 1000) AND ((total_tokens_estimate IS NULL) OR (total_tokens_estimate >= 0)))),
    CONSTRAINT ck_context_manifests__owner_ref CHECK ((((step_ref IS NOT NULL) AND (owner_ref ~ '^step:.+$'::text) AND (owner_ref = ('step:'::text || step_ref)) AND (((plan_id IS NOT NULL) AND (revision_id IS NOT NULL) AND (entity_id IS NOT NULL)) OR ((plan_id IS NULL) AND (revision_id IS NULL) AND (entity_id IS NULL)))) OR ((step_ref IS NULL) AND (owner_ref ~ '^standalone:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'::text) AND ((revision_id IS NULL) OR (plan_id IS NOT NULL)) AND ((entity_id IS NULL) OR (revision_id IS NOT NULL))))),
    CONSTRAINT ck_context_manifests__role CHECK ((role = ANY (ARRAY['scout'::text, 'executor'::text, 'reviewer'::text, 'triager'::text, 'advisor'::text, 'researcher'::text, 'registrar'::text]))),
    CONSTRAINT ck_context_manifests__route CHECK (((jsonb_typeof(route) = 'object'::text) AND (route ? 'route_source'::text) AND (route ? 'operation'::text) AND ((route ->> 'config_mode'::text) = ANY (ARRAY['isolated'::text, 'inherit'::text])))),
    CONSTRAINT ck_context_manifests__runtime_id CHECK ((runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'::text)),
    CONSTRAINT ck_context_manifests__state CHECK ((state = ANY (ARRAY['draft'::text, 'final'::text])))
);

CREATE TABLE skm_context.external_sources (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    query_id uuid NOT NULL,
    ordinal integer NOT NULL,
    origin text NOT NULL,
    url text,
    title text NOT NULL,
    retrieved_at timestamp with time zone NOT NULL,
    content_digest text,
    size_bytes integer,
    locator jsonb DEFAULT '{}'::jsonb NOT NULL,
    excerpt text NOT NULL,
    trust_class text NOT NULL,
    classification text NOT NULL,
    provenance jsonb NOT NULL,
    captured_file_version_id uuid,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_external_sources__classification CHECK ((classification = ANY (ARRAY['public'::text, 'internal'::text, 'confidential'::text, 'restricted'::text]))),
    CONSTRAINT ck_external_sources__content_digest CHECK (((content_digest IS NULL) OR (content_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_external_sources__excerpt CHECK ((char_length(excerpt) <= 20000)),
    CONSTRAINT ck_external_sources__ordinal CHECK (((ordinal >= 0) AND (ordinal < 50))),
    CONSTRAINT ck_external_sources__origin CHECK (((origin ~ '^(https?://|repo:|file:|mcp:|answer:).+'::text) AND (char_length(origin) <= 2000))),
    CONSTRAINT ck_external_sources__title CHECK (((char_length(title) >= 1) AND (char_length(title) <= 500))),
    CONSTRAINT ck_external_sources__trust_class CHECK ((trust_class = ANY (ARRAY['repository'::text, 'external'::text, 'third_party'::text]))),
    CONSTRAINT ck_external_sources__url CHECK (((url IS NULL) OR ((url ~ '^https?://'::text) AND (char_length(url) <= 2000))))
);

CREATE TABLE skm_context.research_queries (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    step_ref text,
    requested_by uuid NOT NULL,
    source_id text NOT NULL,
    source_kind text NOT NULL,
    tier text NOT NULL,
    query_text text NOT NULL,
    query_digest text NOT NULL,
    depth text NOT NULL,
    max_documents integer NOT NULL,
    cache_key text NOT NULL,
    source_config_digest text NOT NULL,
    status text NOT NULL,
    error_code text,
    error_message text,
    citations jsonb DEFAULT '[]'::jsonb NOT NULL,
    claims jsonb DEFAULT '[]'::jsonb NOT NULL,
    limitations jsonb DEFAULT '[]'::jsonb NOT NULL,
    usage jsonb,
    usage_complete boolean NOT NULL,
    retrieved_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_research_queries__depth CHECK ((depth = ANY (ARRAY['standard'::text, 'deep'::text]))),
    CONSTRAINT ck_research_queries__digests CHECK (((query_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND (cache_key ~ '^sha256:[0-9a-f]{64}$'::text) AND (source_config_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_research_queries__error CHECK ((((status = 'error'::text) = (error_code IS NOT NULL)) AND ((error_code IS NULL) OR (error_code = ANY (ARRAY['RESEARCH_SOURCE_UNAVAILABLE'::text, 'RESEARCH_SOURCE_TIMEOUT'::text, 'RESEARCH_SOURCE_INVALID'::text]))))),
    CONSTRAINT ck_research_queries__expires CHECK ((((status <> 'error'::text) OR (expires_at IS NULL)) AND ((expires_at IS NULL) OR (expires_at > retrieved_at)))),
    CONSTRAINT ck_research_queries__json CHECK (((jsonb_typeof(citations) = 'array'::text) AND (jsonb_typeof(claims) = 'array'::text) AND (jsonb_typeof(limitations) = 'array'::text))),
    CONSTRAINT ck_research_queries__max_documents CHECK (((max_documents >= 1) AND (max_documents <= 50))),
    CONSTRAINT ck_research_queries__query_text CHECK (((char_length(query_text) >= 1) AND (char_length(query_text) <= 20000))),
    CONSTRAINT ck_research_queries__source_id CHECK ((source_id ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'::text)),
    CONSTRAINT ck_research_queries__source_kind CHECK ((source_kind ~ '^[a-z][a-z0-9_]{1,62}$'::text)),
    CONSTRAINT ck_research_queries__status CHECK ((status = ANY (ARRAY['ok'::text, 'empty'::text, 'error'::text]))),
    CONSTRAINT ck_research_queries__tier CHECK ((tier = ANY (ARRAY['local_docs'::text, 'codegraph'::text, 'external_search'::text, 'deep_research'::text])))
);

CREATE TABLE skm_context.texts (
    digest text NOT NULL,
    text text NOT NULL,
    size_bytes integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_texts__digest CHECK ((digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_texts__size CHECK ((size_bytes = octet_length(text)))
);

CREATE TABLE skm_core.audit_records (
    id uuid NOT NULL,
    workspace_id uuid,
    actor_id uuid NOT NULL,
    action text NOT NULL,
    target jsonb DEFAULT '{}'::jsonb NOT NULL,
    decision text NOT NULL,
    reason_code text,
    request_id text NOT NULL,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_audit_records__decision CHECK ((decision = ANY (ARRAY['allowed'::text, 'denied'::text]))),
    CONSTRAINT ck_audit_records__reason CHECK (((decision = 'denied'::text) = (reason_code IS NOT NULL))),
    CONSTRAINT ck_audit_records__target_object CHECK ((jsonb_typeof(target) = 'object'::text))
);

CREATE TABLE skm_core.consumer_receipts (
    consumer_id text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamp with time zone NOT NULL
);

CREATE TABLE skm_core.domain_events (
    id uuid NOT NULL,
    workspace_id uuid,
    stream_kind text NOT NULL,
    stream_id uuid NOT NULL,
    stream_seq bigint NOT NULL,
    workspace_seq bigint,
    global_position bigint,
    event_type text NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    actor_id uuid,
    request_id text,
    correlation_id text NOT NULL,
    causation_id text,
    payload jsonb NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL,
    parent_causation_id text,
    CONSTRAINT ck_domain_events__global_position CHECK ((((workspace_id IS NULL) AND (global_position IS NOT NULL) AND (global_position >= 1)) OR ((workspace_id IS NOT NULL) AND (global_position IS NULL)))),
    CONSTRAINT ck_domain_events__parent_causation_id CHECK (((parent_causation_id IS NULL) OR (char_length(parent_causation_id) <= 64))),
    CONSTRAINT ck_domain_events__payload_object CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ck_domain_events__payload_size CHECK ((octet_length((payload)::text) <= 262144)),
    CONSTRAINT ck_domain_events__schema_version CHECK ((schema_version >= 1)),
    CONSTRAINT ck_domain_events__seq CHECK ((stream_seq >= 1)),
    CONSTRAINT ck_domain_events__type CHECK ((event_type ~ '^urn:skm:[a-z][a-z0-9-]*:event:[a-z][a-z0-9-]*:v[1-9][0-9]*$'::text)),
    CONSTRAINT ck_domain_events__workspace_seq CHECK (((workspace_id IS NULL) = (workspace_seq IS NULL)))
);

CREATE TABLE skm_core.event_streams (
    stream_kind text NOT NULL,
    stream_id uuid NOT NULL,
    last_seq bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_event_streams__last_seq CHECK ((last_seq >= 0))
);

CREATE TABLE skm_core.idempotency_receipts (
    id uuid NOT NULL,
    workspace_id uuid,
    principal_id uuid NOT NULL,
    operation text NOT NULL,
    key text NOT NULL,
    request_digest text NOT NULL,
    result_type text NOT NULL,
    result jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    scope_key uuid GENERATED ALWAYS AS (COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid)) STORED,
    CONSTRAINT ck_idempotency_receipts__digest CHECK ((request_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_idempotency_receipts__expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_idempotency_receipts__key CHECK ((key ~ '^[A-Za-z0-9._:-]{1,200}$'::text)),
    CONSTRAINT ck_idempotency_receipts__operation CHECK ((operation ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'::text)),
    CONSTRAINT ck_idempotency_receipts__result_size CHECK ((octet_length((result)::text) <= 1048576)),
    CONSTRAINT ck_idempotency_receipts__result_type CHECK (((char_length(result_type) >= 1) AND (char_length(result_type) <= 200)))
);

CREATE TABLE skm_core.outbox (
    id uuid NOT NULL,
    event_id uuid NOT NULL,
    destination text NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    available_at timestamp with time zone NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    delivery_generation integer DEFAULT 1 NOT NULL,
    last_error text,
    delivered_at timestamp with time zone,
    claimed_at timestamp with time zone,
    claimed_by text,
    dead_notified_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_outbox__attempts CHECK ((attempts >= 0)),
    CONSTRAINT ck_outbox__claim CHECK ((((claimed_at IS NULL) = (claimed_by IS NULL)) AND ((claimed_by IS NULL) OR ((char_length(claimed_by) >= 1) AND (char_length(claimed_by) <= 200))))),
    CONSTRAINT ck_outbox__dead_notified CHECK (((dead_notified_at IS NULL) OR (state = 'dead'::text))),
    CONSTRAINT ck_outbox__delivered_at CHECK (((state = 'delivered'::text) = (delivered_at IS NOT NULL))),
    CONSTRAINT ck_outbox__delivery_generation CHECK ((delivery_generation >= 1)),
    CONSTRAINT ck_outbox__destination CHECK (((destination = 'sse'::text) OR (destination ~ '^([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*|hook:[a-z0-9][a-z0-9_-]*)$'::text))),
    CONSTRAINT ck_outbox__last_error_size CHECK (((last_error IS NULL) OR (length(last_error) <= 4000))),
    CONSTRAINT ck_outbox__state CHECK ((state = ANY (ARRAY['pending'::text, 'delivered'::text, 'failed'::text, 'dead'::text])))
);

CREATE TABLE skm_core.scopes (
    id uuid NOT NULL,
    kind text NOT NULL,
    parent_id uuid,
    workspace_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_scopes__kind CHECK ((kind = ANY (ARRAY['instance'::text, 'workspace'::text, 'project'::text, 'plan'::text, 'run'::text, 'host'::text]))),
    CONSTRAINT ck_scopes__root CHECK (((kind = 'instance'::text) = (parent_id IS NULL))),
    CONSTRAINT ck_scopes__workspace_id CHECK ((((kind = ANY (ARRAY['instance'::text, 'host'::text])) AND (workspace_id IS NULL)) OR ((kind = 'workspace'::text) AND (workspace_id IS NOT NULL) AND (workspace_id = id)) OR ((kind = ANY (ARRAY['project'::text, 'plan'::text, 'run'::text])) AND (workspace_id IS NOT NULL))))
);

CREATE TABLE skm_core.workspace_event_counters (
    workspace_id uuid NOT NULL,
    last_seq bigint DEFAULT 0 NOT NULL,
    CONSTRAINT ck_workspace_event_counters__last_seq CHECK ((last_seq >= 0))
);

CREATE TABLE skm_execution.acceptance_decisions (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid,
    output_id uuid,
    decision text NOT NULL,
    clearance text,
    actor_id uuid NOT NULL,
    basis jsonb NOT NULL,
    decided_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_acceptance_decisions__basis CHECK ((jsonb_typeof(basis) = 'object'::text)),
    CONSTRAINT ck_acceptance_decisions__clearance CHECK ((((decision = 'accepted'::text) = (clearance IS NOT NULL)) AND ((clearance IS NULL) OR (clearance = ANY (ARRAY['green'::text, 'findings_only'::text, 'cleared_by_triage'::text, 'deviation'::text, 'self'::text, 'waived'::text, 'report'::text]))))),
    CONSTRAINT ck_acceptance_decisions__decision CHECK ((decision = ANY (ARRAY['accepted'::text, 'rejected'::text]))),
    CONSTRAINT ck_acceptance_decisions__output CHECK (((output_id IS NULL) OR (attempt_id IS NOT NULL)))
);

CREATE TABLE skm_execution.assignment_leases (
    assignment_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    worker_id uuid NOT NULL,
    fencing_token bigint NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_heartbeat_at timestamp with time zone NOT NULL,
    process_identity jsonb,
    offered_runtimes text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT ck_assignment_leases__fencing_token CHECK ((fencing_token >= 1)),
    CONSTRAINT ck_assignment_leases__heartbeat CHECK ((last_heartbeat_at <= expires_at)),
    CONSTRAINT ck_assignment_leases__process_identity CHECK (((process_identity IS NULL) OR (jsonb_typeof(process_identity) = 'object'::text)))
);

CREATE TABLE skm_execution.assignments (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    state text DEFAULT 'available'::text NOT NULL,
    available_at timestamp with time zone NOT NULL,
    required_capabilities text[] DEFAULT '{}'::text[] NOT NULL,
    required_host_id uuid,
    required_labels text[] DEFAULT '{}'::text[] NOT NULL,
    environment_kind text DEFAULT 'git_worktree'::text NOT NULL,
    required_isolation_profiles text[] DEFAULT '{}'::text[] NOT NULL,
    priority integer NOT NULL,
    last_fencing_token bigint DEFAULT 0 NOT NULL,
    reap_stage_record_id uuid,
    reap_step_id uuid,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    reconcile_effect_id uuid,
    CONSTRAINT ck_assignments__counters CHECK (((priority >= 0) AND (last_fencing_token >= 0) AND (row_version >= 1))),
    CONSTRAINT ck_assignments__environment_kind CHECK ((environment_kind = ANY (ARRAY['git_worktree'::text, 'existing_checkout'::text, 'managed_clone'::text]))),
    CONSTRAINT ck_assignments__isolation CHECK (((array_position(required_isolation_profiles, NULL::text) IS NULL) AND (array_to_string(required_isolation_profiles, ','::text) ~ '^((none|worktree|landlock|container|[a-z0-9_.-]+:[a-z0-9_-]+)(,(none|worktree|landlock|container|[a-z0-9_.-]+:[a-z0-9_-]+))*)?$'::text))),
    CONSTRAINT ck_assignments__labels CHECK (((cardinality(required_labels) <= 32) AND (cardinality(required_capabilities) <= 64))),
    CONSTRAINT ck_assignments__reap CHECK ((((reap_step_id IS NULL) OR (required_host_id IS NOT NULL)) AND ((reap_stage_record_id IS NULL) OR (required_host_id IS NOT NULL)))),
    CONSTRAINT ck_assignments__reconcile_binding CHECK (((reconcile_effect_id IS NULL) OR ((required_host_id IS NOT NULL) AND (reap_stage_record_id IS NULL) AND (reap_step_id IS NULL)))),
    CONSTRAINT ck_assignments__state CHECK ((state = ANY (ARRAY['available'::text, 'leased'::text, 'completed'::text, 'expired'::text, 'cancelled'::text])))
);

CREATE TABLE skm_execution.attempt_file_bindings (
    attempt_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    role text NOT NULL,
    step_id uuid,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_attempt_file_bindings__role CHECK ((role = ANY (ARRAY['evidence'::text, 'transcript'::text, 'prompt'::text, 'raw_result'::text, 'patch'::text, 'fix_brief'::text, 'diagnostic'::text, 'coverage_report'::text])))
);

CREATE TABLE skm_execution.attempt_outputs (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    task_id uuid NOT NULL,
    run_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    seq integer NOT NULL,
    source text NOT NULL,
    manifest jsonb NOT NULL,
    manifest_digest text NOT NULL,
    tree_digest text NOT NULL,
    outside_write_scope jsonb DEFAULT '[]'::jsonb NOT NULL,
    excluded_paths jsonb DEFAULT '[]'::jsonb NOT NULL,
    produced_by_step_id uuid,
    patch_file_version_id uuid,
    sealed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_attempt_outputs__digests CHECK (((manifest_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND (tree_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_attempt_outputs__json CHECK (((jsonb_typeof(manifest) = 'object'::text) AND (jsonb_typeof(outside_write_scope) = 'array'::text) AND (jsonb_typeof(excluded_paths) = 'array'::text))),
    CONSTRAINT ck_attempt_outputs__seq CHECK ((seq >= 1)),
    CONSTRAINT ck_attempt_outputs__source CHECK ((((source = 'executor'::text) AND (produced_by_step_id IS NOT NULL)) OR ((source = 'range'::text) AND (produced_by_step_id IS NULL))))
);

CREATE TABLE skm_execution.attempt_stages (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    seq integer NOT NULL,
    stage_id text NOT NULL,
    stage_type text NOT NULL,
    round_no integer DEFAULT 1 NOT NULL,
    mode text DEFAULT 'normal'::text NOT NULL,
    retry_of_id uuid,
    state text NOT NULL,
    input_digest text NOT NULL,
    outcome_kind text,
    outcome jsonb,
    error_code text,
    fencing_token bigint NOT NULL,
    runtime_started_at timestamp with time zone,
    process_identities jsonb DEFAULT '[]'::jsonb NOT NULL,
    reused_from_step_id uuid,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_attempt_stages__completed_outcome CHECK (((state <> 'completed'::text) OR (outcome_kind IS NOT NULL))),
    CONSTRAINT ck_attempt_stages__counters CHECK (((seq >= 1) AND (round_no >= 1) AND (fencing_token >= 0))),
    CONSTRAINT ck_attempt_stages__error_code CHECK (((error_code IS NULL) OR (error_code ~ '^[A-Z][A-Z0-9_]{2,63}$'::text))),
    CONSTRAINT ck_attempt_stages__finished CHECK ((((finished_at IS NOT NULL) = (state = ANY (ARRAY['completed'::text, 'failed'::text, 'interrupted'::text, 'skipped'::text]))) AND ((finished_at IS NULL) OR (finished_at >= started_at)))),
    CONSTRAINT ck_attempt_stages__input_digest CHECK ((input_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_attempt_stages__mode CHECK ((mode = ANY (ARRAY['normal'::text, 'retry'::text, 'rework'::text, 'final_correction'::text, 'continue_with_answer'::text, 'resume_interrupted'::text, 'retriage_with_advice'::text, 'reconcile'::text]))),
    CONSTRAINT ck_attempt_stages__outcome_kind CHECK (((outcome_kind IS NULL) OR (outcome_kind = ANY (ARRAY['success'::text, 'checks_failed'::text, 'checks_error'::text, 'checks_unknown'::text, 'manual_pending'::text, 'tree_changed'::text, 'verdict_green'::text, 'verdict_attention'::text, 'verdict_red'::text, 'question'::text, 'blocked'::text, 'write_scope_violation'::text, 'result_invalid'::text, 'runtime_error'::text, 'conflict'::text, 'approval_required'::text, 'outcome_unknown'::text, 'held'::text, 'accepted'::text, 'not_acceptable'::text, 'cancelled'::text])))),
    CONSTRAINT ck_attempt_stages__process_identities CHECK ((jsonb_typeof(process_identities) = 'array'::text)),
    CONSTRAINT ck_attempt_stages__retry_of CHECK ((((retry_of_id IS NULL) OR (mode = 'retry'::text)) AND ((retry_of_id IS NULL) OR (retry_of_id <> id)))),
    CONSTRAINT ck_attempt_stages__reused CHECK (((reused_from_step_id IS NULL) OR ((stage_type = 'agent_step'::text) AND (state = 'completed'::text) AND (fencing_token = 0) AND (runtime_started_at IS NULL)))),
    CONSTRAINT ck_attempt_stages__runtime_started CHECK (((runtime_started_at IS NULL) OR (runtime_started_at >= started_at))),
    CONSTRAINT ck_attempt_stages__stage_id CHECK ((stage_id ~ '^[a-z][a-z0-9_]{0,31}$'::text)),
    CONSTRAINT ck_attempt_stages__stage_type CHECK ((stage_type ~ '^[a-z][a-z0-9_]{0,40}$'::text)),
    CONSTRAINT ck_attempt_stages__state CHECK ((state = ANY (ARRAY['started'::text, 'context_draft'::text, 'running'::text, 'completed'::text, 'failed'::text, 'interrupted'::text, 'skipped'::text])))
);

CREATE TABLE skm_execution.attempt_steps (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    stage_record_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    parent_step_id uuid,
    seq integer NOT NULL,
    role text NOT NULL,
    purpose text DEFAULT 'primary'::text NOT NULL,
    runtime_id text NOT NULL,
    model text NOT NULL,
    effort text,
    operation text NOT NULL,
    admission jsonb NOT NULL,
    route_source text NOT NULL,
    route_reason text NOT NULL,
    context_manifest_id uuid NOT NULL,
    session_mode text NOT NULL,
    session_ref text,
    session_fingerprint jsonb NOT NULL,
    session_fingerprint_digest text NOT NULL,
    fresh_reason text,
    state text DEFAULT 'started'::text NOT NULL,
    result jsonb,
    raw_result_file_version_id uuid,
    repairs jsonb DEFAULT '[]'::jsonb NOT NULL,
    schema_errors jsonb DEFAULT '[]'::jsonb NOT NULL,
    usage jsonb,
    usage_status text,
    usage_so_far jsonb,
    process_identity jsonb,
    activity jsonb,
    reuse_key text,
    transcript_file_version_id uuid,
    last_progress_at timestamp with time zone,
    error_code text,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    route_snapshot jsonb,
    runtime_observation jsonb,
    CONSTRAINT ck_attempt_steps__admission CHECK ((jsonb_typeof(admission) = 'object'::text)),
    CONSTRAINT ck_attempt_steps__fingerprint CHECK (((jsonb_typeof(session_fingerprint) = 'object'::text) AND (session_fingerprint_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_attempt_steps__finished CHECK ((((finished_at IS NOT NULL) = (state <> 'started'::text)) AND ((finished_at IS NULL) OR (finished_at >= started_at)))),
    CONSTRAINT ck_attempt_steps__fresh_reason CHECK (((fresh_reason IS NULL) OR ((session_mode = 'new'::text) AND (fresh_reason = ANY (ARRAY['ADMISSION_NO_RESUME'::text, 'NO_PREVIOUS_SESSION'::text, 'AUTHORITY_CHANGED'::text, 'ENVIRONMENT_CHANGED'::text, 'ROUTE_CHANGED'::text, 'RESUME_UNSUPPORTED'::text, 'SCOPE_CHANGED'::text, 'SESSION_CONTAMINATED'::text, 'CONTEXT_BLOATED'::text, 'NOT_A_CONTINUATION'::text, 'SESSION_LOST'::text, 'OPERATOR_LIVE_CONTROL'::text]))))),
    CONSTRAINT ck_attempt_steps__json CHECK (((jsonb_typeof(repairs) = 'array'::text) AND (jsonb_typeof(schema_errors) = 'array'::text) AND ((usage IS NULL) OR (jsonb_typeof(usage) = 'object'::text)) AND ((usage_so_far IS NULL) OR (jsonb_typeof(usage_so_far) = 'object'::text)) AND ((process_identity IS NULL) OR (jsonb_typeof(process_identity) = 'object'::text)) AND ((activity IS NULL) OR ((jsonb_typeof(activity) = 'object'::text) AND (octet_length((activity)::text) <= 65536))))),
    CONSTRAINT ck_attempt_steps__operation CHECK ((operation = ANY (ARRAY['new_implementation'::text, 'continuation'::text, 'bounded_fix'::text, 'scope_change'::text, 'review'::text, 'final_close'::text, 'research'::text, 'advice'::text, 'auxiliary'::text]))),
    CONSTRAINT ck_attempt_steps__parent CHECK (((parent_step_id IS NULL) OR (parent_step_id <> id))),
    CONSTRAINT ck_attempt_steps__purpose CHECK ((purpose = ANY (ARRAY['primary'::text, 'result_retry'::text, 'triage_reverify'::text, 'consilium_member'::text, 'consilium_critic'::text]))),
    CONSTRAINT ck_attempt_steps__result CHECK (((result IS NOT NULL) <= (state = 'succeeded'::text))),
    CONSTRAINT ck_attempt_steps__reuse_key CHECK (((reuse_key IS NULL) OR ((role = 'scout'::text) AND (reuse_key ~ '^sha256:[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_attempt_steps__role CHECK ((role = ANY (ARRAY['scout'::text, 'executor'::text, 'reviewer'::text, 'triager'::text, 'advisor'::text, 'researcher'::text, 'registrar'::text]))),
    CONSTRAINT ck_attempt_steps__route_reason CHECK ((route_reason = ANY (ARRAY['ROUTE_DEFAULT'::text, 'ROUTE_FALLBACK'::text, 'ROUTE_UPGRADED'::text, 'ROUTE_OVERRIDE'::text]))),
    CONSTRAINT ck_attempt_steps__route_snapshot CHECK (((route_snapshot IS NULL) OR ((jsonb_typeof(route_snapshot) = 'object'::text) AND (octet_length((route_snapshot)::text) <= 32768)))),
    CONSTRAINT ck_attempt_steps__route_source CHECK ((route_source = ANY (ARRAY['previous_route'::text, 'plan_route'::text, 'role_routing'::text, 'role_fallback'::text, 'preference'::text, 'host_substitution'::text]))),
    CONSTRAINT ck_attempt_steps__runtime_observation CHECK (((runtime_observation IS NULL) OR ((jsonb_typeof(runtime_observation) = 'object'::text) AND (octet_length((runtime_observation)::text) <= 32768) AND (state <> 'started'::text)))),
    CONSTRAINT ck_attempt_steps__seq CHECK ((seq >= 1)),
    CONSTRAINT ck_attempt_steps__session_mode CHECK ((session_mode = ANY (ARRAY['new'::text, 'resume'::text]))),
    CONSTRAINT ck_attempt_steps__state CHECK ((state = ANY (ARRAY['started'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text]))),
    CONSTRAINT ck_attempt_steps__usage_status CHECK ((((usage_status IS NULL) = (usage IS NULL)) AND ((usage_status IS NULL) OR (usage_status = ANY (ARRAY['reported'::text, 'estimated'::text, 'unknown'::text])))))
);

CREATE TABLE skm_execution.attempts (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    attempt_no integer NOT NULL,
    state text DEFAULT 'preparing'::text NOT NULL,
    worker_id uuid,
    host_id uuid,
    environment_id uuid,
    current_output_id uuid,
    executor_route jsonb,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    end_reason text,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    continuation jsonb,
    CONSTRAINT ck_attempts__attempt_no CHECK ((attempt_no >= 1)),
    CONSTRAINT ck_attempts__continuation CHECK (((continuation IS NULL) OR COALESCE(((state <> ALL (ARRAY['completed'::text, 'ownership_lost'::text, 'abandoned'::text])) AND
CASE
    WHEN (jsonb_typeof(continuation) = 'object'::text) THEN ((octet_length((continuation)::text) <= 131072) AND ((continuation -> 'schema_version'::text) = '1'::jsonb) AND (jsonb_typeof((continuation -> 'continuation_id'::text)) = 'string'::text) AND ((char_length((continuation ->> 'continuation_id'::text)) >= 1) AND (char_length((continuation ->> 'continuation_id'::text)) <= 64)) AND
    CASE (continuation ->> 'kind'::text)
        WHEN 'stage'::text THEN ((continuation ?& ARRAY['schema_version'::text, 'continuation_id'::text, 'kind'::text, 'stage'::text, 'cause'::text]) AND ((continuation - ARRAY['schema_version'::text, 'continuation_id'::text, 'kind'::text, 'stage'::text, 'cause'::text]) = '{}'::jsonb) AND (jsonb_typeof((continuation -> 'cause'::text)) = 'object'::text) AND
        CASE
            WHEN (jsonb_typeof((continuation -> 'stage'::text)) = 'object'::text) THEN (((continuation -> 'stage'::text) ?& ARRAY['stage_id'::text, 'stage_type'::text, 'mode'::text, 'round_no'::text, 'params'::text, 'not_before'::text, 'route_override'::text, 'feedback_refs'::text, 'input_output_id'::text, 'retry_of_id'::text]) AND (jsonb_typeof((continuation #> '{stage,stage_id}'::text[])) = 'string'::text) AND (jsonb_typeof((continuation #> '{stage,stage_type}'::text[])) = 'string'::text) AND (jsonb_typeof((continuation #> '{stage,mode}'::text[])) = 'string'::text) AND
            CASE
                WHEN (jsonb_typeof((continuation #> '{stage,round_no}'::text[])) = 'number'::text) THEN ((((continuation #>> '{stage,round_no}'::text[]))::numeric >= (1)::numeric) AND (trunc(((continuation #>> '{stage,round_no}'::text[]))::numeric) = ((continuation #>> '{stage,round_no}'::text[]))::numeric))
                ELSE false
            END AND (jsonb_typeof((continuation #> '{stage,params}'::text[])) = 'object'::text) AND (jsonb_typeof((continuation #> '{stage,not_before}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND (jsonb_typeof((continuation #> '{stage,route_override}'::text[])) = ANY (ARRAY['object'::text, 'null'::text])) AND (jsonb_typeof((continuation #> '{stage,input_output_id}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND (jsonb_typeof((continuation #> '{stage,retry_of_id}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND
            CASE
                WHEN (jsonb_typeof((continuation #> '{stage,feedback_refs}'::text[])) = 'object'::text) THEN (((continuation #> '{stage,feedback_refs}'::text[]) ?& ARRAY['fix_brief_id'::text, 'schema_errors_step_id'::text, 'answer_request_ids'::text, 'advice_step_id'::text, 'interrupted_stage_record_id'::text]) AND (jsonb_typeof((continuation #> '{stage,feedback_refs,fix_brief_id}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND (jsonb_typeof((continuation #> '{stage,feedback_refs,schema_errors_step_id}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND (jsonb_typeof((continuation #> '{stage,feedback_refs,advice_step_id}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND (jsonb_typeof((continuation #> '{stage,feedback_refs,interrupted_stage_record_id}'::text[])) = ANY (ARRAY['string'::text, 'null'::text])) AND
                CASE
                    WHEN (jsonb_typeof((continuation #> '{stage,feedback_refs,answer_request_ids}'::text[])) = 'array'::text) THEN (jsonb_array_length((continuation #> '{stage,feedback_refs,answer_request_ids}'::text[])) <= 128)
                    ELSE false
                END)
                ELSE false
            END)
            ELSE false
        END)
        WHEN 'advance'::text THEN ((continuation ?& ARRAY['schema_version'::text, 'continuation_id'::text, 'kind'::text, 'triggers'::text]) AND ((continuation - ARRAY['schema_version'::text, 'continuation_id'::text, 'kind'::text, 'triggers'::text]) = '{}'::jsonb) AND
        CASE
            WHEN (jsonb_typeof((continuation -> 'triggers'::text)) = 'array'::text) THEN (((jsonb_array_length((continuation -> 'triggers'::text)) >= 1) AND (jsonb_array_length((continuation -> 'triggers'::text)) <= 128)) AND (NOT jsonb_path_exists(continuation, '$."triggers"[*]?(((((@.type() != "object" || !(exists (@."source_event_id"))) || @."source_event_id".type() != "string") || @."source_event_id" == "") || !(exists (@."cause"))) || @."cause".type() != "object")'::jsonpath)))
            ELSE false
        END)
        ELSE false
    END)
    ELSE false
END), false))),
    CONSTRAINT ck_attempts__end_reason CHECK ((((end_reason IS NOT NULL) = (finished_at IS NOT NULL)) AND ((end_reason IS NULL) OR (end_reason = ANY (ARRAY['ACCEPTED'::text, 'LEASE_LOST'::text, 'RESTARTED'::text, 'RETRY_NEW_ATTEMPT'::text, 'RECOVERY_NEW_ATTEMPT'::text, 'OWNER_DECISION'::text, 'GATE_REREVIEW'::text, 'FAILED'::text, 'SKIPPED'::text, 'CANCELLED'::text]))))),
    CONSTRAINT ck_attempts__finished CHECK ((((finished_at IS NOT NULL) = (state = ANY (ARRAY['completed'::text, 'ownership_lost'::text, 'abandoned'::text]))) AND ((finished_at IS NULL) OR (started_at IS NULL) OR (finished_at >= started_at)))),
    CONSTRAINT ck_attempts__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_attempts__state CHECK ((state = ANY (ARRAY['preparing'::text, 'running'::text, 'waiting'::text, 'submitted'::text, 'completed'::text, 'ownership_lost'::text, 'abandoned'::text])))
);

CREATE TABLE skm_execution.autopilot_states (
    project_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    state text DEFAULT 'idle'::text NOT NULL,
    emergency boolean DEFAULT false NOT NULL,
    current_run_id uuid,
    session_started_at timestamp with time zone,
    counters jsonb DEFAULT '{"recoveries": 0, "last_blocker": null, "runs_started": 0, "auto_decisions": 0, "infra_failures": 0, "no_progress_runs": 0}'::jsonb NOT NULL,
    session_limits jsonb DEFAULT '{}'::jsonb NOT NULL,
    stop_code text,
    stop_detail text,
    updated_by uuid NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_autopilot_states__counters CHECK (((jsonb_typeof(counters) = 'object'::text) AND (jsonb_typeof(session_limits) = 'object'::text))),
    CONSTRAINT ck_autopilot_states__emergency CHECK (((NOT emergency) OR (state = 'stopped'::text))),
    CONSTRAINT ck_autopilot_states__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_autopilot_states__session CHECK (((state <> ALL (ARRAY['running'::text, 'paused'::text, 'draining'::text])) OR (session_started_at IS NOT NULL))),
    CONSTRAINT ck_autopilot_states__state CHECK ((state = ANY (ARRAY['idle'::text, 'running'::text, 'paused'::text, 'draining'::text, 'stopped'::text]))),
    CONSTRAINT ck_autopilot_states__stop_code CHECK ((((state = 'stopped'::text) = (stop_code IS NOT NULL)) AND ((stop_code IS NULL) OR (stop_code ~ '^AUTOPILOT_[A-Z_]{2,40}$'::text)))),
    CONSTRAINT ck_autopilot_states__stop_detail CHECK (((stop_detail IS NULL) OR (char_length(stop_detail) <= 2000)))
);

CREATE TABLE skm_execution.budget_accounts (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    scope text NOT NULL,
    task_id uuid,
    dimension text NOT NULL,
    limit_value numeric,
    spent numeric DEFAULT 0 NOT NULL,
    reserved numeric DEFAULT 0 NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_budget_accounts__amounts CHECK (((spent >= (0)::numeric) AND (reserved >= (0)::numeric) AND ((limit_value IS NULL) OR (limit_value > (0)::numeric)))),
    CONSTRAINT ck_budget_accounts__dimension CHECK ((dimension = ANY (ARRAY['usd'::text, 'tokens'::text, 'wall_seconds'::text, 'attempts'::text, 'review_rounds'::text, 'tool_calls'::text]))),
    CONSTRAINT ck_budget_accounts__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_budget_accounts__scope CHECK ((((scope = 'run'::text) AND (task_id IS NULL)) OR ((scope = 'task'::text) AND (task_id IS NOT NULL))))
);

CREATE TABLE skm_execution.budget_reservations (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    account_ids uuid[] NOT NULL,
    dimension text NOT NULL,
    attempt_id uuid,
    step_id uuid,
    amount numeric NOT NULL,
    state text DEFAULT 'reserved'::text NOT NULL,
    settled_amount numeric,
    created_at timestamp with time zone NOT NULL,
    settled_at timestamp with time zone,
    CONSTRAINT ck_budget_reservations__accounts CHECK (((cardinality(account_ids) >= 1) AND (cardinality(account_ids) <= 4))),
    CONSTRAINT ck_budget_reservations__amount CHECK (((amount > (0)::numeric) AND ((settled_amount IS NULL) OR (settled_amount >= (0)::numeric)))),
    CONSTRAINT ck_budget_reservations__dimension CHECK ((dimension = ANY (ARRAY['usd'::text, 'tokens'::text, 'wall_seconds'::text, 'attempts'::text, 'review_rounds'::text, 'tool_calls'::text]))),
    CONSTRAINT ck_budget_reservations__settled CHECK ((((state = 'reserved'::text) = (settled_at IS NULL)) AND ((state = 'settled'::text) = (settled_amount IS NOT NULL)))),
    CONSTRAINT ck_budget_reservations__state CHECK ((state = ANY (ARRAY['reserved'::text, 'settled'::text, 'released'::text]))),
    CONSTRAINT ck_budget_reservations__step CHECK (((step_id IS NULL) OR (attempt_id IS NOT NULL)))
);

CREATE TABLE skm_execution.check_evidence_bindings (
    check_execution_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    role text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_check_evidence_bindings__role CHECK ((role = ANY (ARRAY['stdout'::text, 'stderr'::text, 'report'::text, 'evidence'::text])))
);

CREATE TABLE skm_execution.check_executions (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    output_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    check_spec_id uuid NOT NULL,
    check_key text NOT NULL,
    kind text NOT NULL,
    required boolean NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    exit_code integer,
    summary text DEFAULT ''::text NOT NULL,
    error_code text,
    reused_from_id uuid,
    fingerprint text NOT NULL,
    round_no integer NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_check_executions__error_code CHECK (((error_code IS NULL) OR (error_code ~ '^[A-Z][A-Z0-9_]{2,63}$'::text))),
    CONSTRAINT ck_check_executions__fingerprint CHECK ((fingerprint ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_check_executions__finished CHECK (((finished_at IS NULL) OR (started_at IS NULL) OR (finished_at >= started_at))),
    CONSTRAINT ck_check_executions__kind CHECK ((kind = ANY (ARRAY['command'::text, 'shell'::text, 'manual'::text, 'external'::text]))),
    CONSTRAINT ck_check_executions__manual CHECK (((kind = 'manual'::text) OR (state <> 'manual_pending'::text))),
    CONSTRAINT ck_check_executions__reused CHECK (((reused_from_id IS NULL) OR ((reused_from_id <> id) AND (state = 'passed'::text)))),
    CONSTRAINT ck_check_executions__round_no CHECK ((round_no >= 1)),
    CONSTRAINT ck_check_executions__state CHECK ((state = ANY (ARRAY['pending'::text, 'running'::text, 'passed'::text, 'failed'::text, 'manual_pending'::text, 'error'::text, 'cancelled'::text, 'unknown'::text]))),
    CONSTRAINT ck_check_executions__summary CHECK ((char_length(summary) <= 4000))
);

CREATE TABLE skm_execution.decision_answers (
    id uuid NOT NULL,
    request_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    request_revision integer NOT NULL,
    answered_by_kind text NOT NULL,
    answered_by_principal_id uuid,
    answered_by_attempt_id uuid,
    answered_by_step_id uuid,
    value jsonb NOT NULL,
    authority jsonb NOT NULL,
    answered_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_decision_answers__authority CHECK ((jsonb_typeof(authority) = 'object'::text)),
    CONSTRAINT ck_decision_answers__by CHECK ((((answered_by_kind = 'owner'::text) AND (answered_by_principal_id IS NOT NULL) AND (answered_by_step_id IS NULL)) OR ((answered_by_kind = ANY (ARRAY['advisor'::text, 'consilium'::text])) AND (answered_by_step_id IS NOT NULL) AND (answered_by_principal_id IS NULL)) OR ((answered_by_kind = ANY (ARRAY['policy'::text, 'reuse'::text])) AND (answered_by_principal_id IS NULL) AND (answered_by_step_id IS NULL)))),
    CONSTRAINT ck_decision_answers__revision CHECK ((request_revision >= 1))
);

CREATE TABLE skm_execution.decision_records (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    request_id uuid NOT NULL,
    category text NOT NULL,
    gate_categories text[] DEFAULT '{}'::text[] NOT NULL,
    authority text NOT NULL,
    status text DEFAULT 'applied'::text NOT NULL,
    selected_option text,
    value jsonb NOT NULL,
    rationale text NOT NULL,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    assumptions jsonb DEFAULT '[]'::jsonb NOT NULL,
    requires_owner boolean NOT NULL,
    question_key text NOT NULL,
    question_input_digest text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    superseded_at timestamp with time zone,
    CONSTRAINT ck_decision_records__authority CHECK ((authority = ANY (ARRAY['owner'::text, 'advisor'::text, 'consilium'::text]))),
    CONSTRAINT ck_decision_records__category CHECK ((category = ANY (ARRAY['local_reversible'::text, 'bounded_ambiguity'::text, 'cross_module'::text, 'architectural'::text, 'authority_required'::text, 'external_fact'::text]))),
    CONSTRAINT ck_decision_records__json CHECK (((jsonb_typeof(evidence_refs) = 'array'::text) AND (jsonb_typeof(assumptions) = 'array'::text))),
    CONSTRAINT ck_decision_records__keys CHECK (((question_key ~ '^qk-[0-9a-f]{16}$'::text) AND (question_input_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_decision_records__owner CHECK (((NOT requires_owner) OR (authority = 'owner'::text))),
    CONSTRAINT ck_decision_records__rationale CHECK (((char_length(rationale) >= 1) AND (char_length(rationale) <= 2000))),
    CONSTRAINT ck_decision_records__status CHECK ((((status = 'superseded'::text) = (superseded_at IS NOT NULL)) AND (status = ANY (ARRAY['applied'::text, 'superseded'::text]))))
);

CREATE TABLE skm_execution.decision_requests (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid,
    kind text NOT NULL,
    audience text NOT NULL,
    category text,
    gate_categories text[] DEFAULT '{}'::text[] NOT NULL,
    question_key text,
    question_digest text,
    revision integer DEFAULT 1 NOT NULL,
    payload jsonb NOT NULL,
    attempt_id uuid,
    stage_record_id uuid,
    asked_by_step_id uuid,
    input_part_digest text,
    blocking boolean NOT NULL,
    state text DEFAULT 'open'::text NOT NULL,
    stale_answer jsonb,
    deadline_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_decision_requests__assumed CHECK (((state <> 'assumed'::text) OR (NOT blocking))),
    CONSTRAINT ck_decision_requests__audience CHECK ((audience = ANY (ARRAY['owner'::text, 'advisor'::text, 'consilium'::text]))),
    CONSTRAINT ck_decision_requests__category CHECK ((((kind = 'question'::text) = (category IS NOT NULL)) AND ((category IS NULL) OR (category = ANY (ARRAY['local_reversible'::text, 'bounded_ambiguity'::text, 'cross_module'::text, 'architectural'::text, 'authority_required'::text, 'external_fact'::text]))))),
    CONSTRAINT ck_decision_requests__gate_categories CHECK ((gate_categories <@ ARRAY['security'::text, 'destructive'::text, 'public_api'::text, 'scope_expansion'::text, 'product'::text, 'legal'::text, 'cost'::text, 'data_loss'::text])),
    CONSTRAINT ck_decision_requests__kind CHECK ((kind = ANY (ARRAY['question'::text, 'approval'::text, 'manual_check'::text, 'escalation'::text, 'budget'::text, 'readiness'::text]))),
    CONSTRAINT ck_decision_requests__payload CHECK (((jsonb_typeof(payload) = 'object'::text) AND (octet_length((payload)::text) <= 262144))),
    CONSTRAINT ck_decision_requests__question CHECK ((((kind = 'question'::text) = (question_key IS NOT NULL)) AND ((question_key IS NULL) OR ((question_key ~ '^qk-[0-9a-f]{16}$'::text) AND (question_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND (input_part_digest IS NOT NULL))))),
    CONSTRAINT ck_decision_requests__revision CHECK ((revision >= 1)),
    CONSTRAINT ck_decision_requests__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_decision_requests__state CHECK ((state = ANY (ARRAY['open'::text, 'answered'::text, 'applied'::text, 'assumed'::text, 'denied'::text, 'stale'::text, 'expired'::text, 'cancelled'::text])))
);

CREATE TABLE skm_execution.deviation_acceptances (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    scope text NOT NULL,
    criterion_id uuid,
    criterion_entity_kind text DEFAULT 'criterion'::text NOT NULL,
    finding_id uuid,
    reason text NOT NULL,
    approved_by uuid NOT NULL,
    approved_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_deviation_acceptances__entity_kind CHECK ((criterion_entity_kind = 'criterion'::text)),
    CONSTRAINT ck_deviation_acceptances__reason CHECK (((char_length(reason) >= 1) AND (char_length(reason) <= 2000))),
    CONSTRAINT ck_deviation_acceptances__scope CHECK ((((scope = 'criterion'::text) AND (criterion_id IS NOT NULL) AND (finding_id IS NULL)) OR ((scope = 'finding'::text) AND (finding_id IS NOT NULL) AND (criterion_id IS NULL)) OR ((scope = 'attention_verdict'::text) AND (criterion_id IS NULL) AND (finding_id IS NULL)) OR ((scope = 'coverage'::text) AND (criterion_id IS NOT NULL) AND (finding_id IS NULL))))
);

CREATE TABLE skm_execution.execution_bundles (
    run_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    config_snapshot jsonb NOT NULL,
    config_digest text NOT NULL,
    policy_digest text NOT NULL,
    resource_pins jsonb NOT NULL,
    selection jsonb,
    context_policy jsonb NOT NULL,
    review_grouping jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    work_policies jsonb,
    CONSTRAINT ck_execution_bundles__digests CHECK (((config_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND (policy_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_execution_bundles__json CHECK (((jsonb_typeof(config_snapshot) = 'object'::text) AND (jsonb_typeof(resource_pins) = 'object'::text) AND (jsonb_typeof((resource_pins -> 'resources'::text)) = 'array'::text) AND (jsonb_typeof((resource_pins -> 'packs'::text)) = 'object'::text) AND ((selection IS NULL) OR (jsonb_typeof(selection) = 'object'::text)) AND (jsonb_typeof(context_policy) = 'object'::text) AND (jsonb_typeof(review_grouping) = 'object'::text))),
    CONSTRAINT ck_execution_bundles__size CHECK ((octet_length((config_snapshot)::text) <= 1048576)),
    CONSTRAINT ck_execution_bundles__work_policies CHECK (((work_policies IS NULL) OR ((jsonb_typeof(work_policies) = 'object'::text) AND (octet_length((work_policies)::text) <= 16777216))))
);

CREATE TABLE skm_execution.execution_environments (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    host_id uuid NOT NULL,
    kind text NOT NULL,
    baseline jsonb NOT NULL,
    dirty_patch_file_version_id uuid,
    branch text NOT NULL,
    local_locator text NOT NULL,
    state text DEFAULT 'preparing'::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    discarded_at timestamp with time zone,
    removed_at timestamp with time zone,
    CONSTRAINT ck_execution_environments__baseline CHECK ((jsonb_typeof(baseline) = 'array'::text)),
    CONSTRAINT ck_execution_environments__branch CHECK (((branch ~ '^skm/attempt/[0-9a-f-]{36}$'::text) OR (kind = 'existing_checkout'::text))),
    CONSTRAINT ck_execution_environments__dirty_patch CHECK (((dirty_patch_file_version_id IS NULL) OR (kind = 'existing_checkout'::text))),
    CONSTRAINT ck_execution_environments__kind CHECK ((kind = ANY (ARRAY['git_worktree'::text, 'existing_checkout'::text, 'managed_clone'::text]))),
    CONSTRAINT ck_execution_environments__locator CHECK ((((char_length(local_locator) >= 1) AND (char_length(local_locator) <= 4096)) AND (POSITION(('
'::text) IN (local_locator)) = 0))),
    CONSTRAINT ck_execution_environments__state CHECK ((state = ANY (ARRAY['preparing'::text, 'ready'::text, 'discarded'::text, 'retained'::text, 'removed'::text]))),
    CONSTRAINT ck_execution_environments__timestamps CHECK ((((state = ANY (ARRAY['discarded'::text, 'removed'::text])) = (discarded_at IS NOT NULL)) AND ((state = 'removed'::text) = (removed_at IS NOT NULL))))
);

CREATE TABLE skm_execution.external_effects (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    kind text NOT NULL,
    intent_id uuid,
    request_digest text NOT NULL,
    request jsonb DEFAULT '{}'::jsonb NOT NULL,
    state text DEFAULT 'intended'::text NOT NULL,
    receipt jsonb,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_external_effects__git_request CHECK (((kind <> 'git_commit'::text) OR (request ?& ARRAY['repository_id'::text, 'target_branch'::text, 'before_sha'::text, 'after_sha'::text, 'tree_sha'::text, 'baseline_sha'::text, 'output_ids'::text, 'output_digests'::text, 'commit_shas'::text, 'assignment_fencing_token'::text, 'slot_fencing_token'::text, 'writer_epoch_sha'::text]))),
    CONSTRAINT ck_external_effects__intent CHECK (((kind = 'git_commit'::text) OR (intent_id IS NOT NULL))),
    CONSTRAINT ck_external_effects__kind CHECK ((kind = ANY (ARRAY['git_commit'::text, 'git_push'::text, 'pr_create'::text, 'message'::text, 'publish'::text, 'fs_write_external'::text]))),
    CONSTRAINT ck_external_effects__receipt CHECK (((state = 'succeeded'::text) <= (receipt IS NOT NULL))),
    CONSTRAINT ck_external_effects__request_digest CHECK ((request_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_external_effects__request_object CHECK ((jsonb_typeof(request) = 'object'::text)),
    CONSTRAINT ck_external_effects__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_external_effects__state CHECK ((state = ANY (ARRAY['intended'::text, 'executing'::text, 'succeeded'::text, 'failed'::text, 'outcome_unknown'::text])))
);

CREATE TABLE skm_execution.finding_resolutions (
    id uuid NOT NULL,
    finding_id uuid NOT NULL,
    task_id uuid NOT NULL,
    resolution_kind text NOT NULL,
    target_output_id uuid,
    comment text DEFAULT ''::text NOT NULL,
    resolved_by jsonb NOT NULL,
    at timestamp with time zone NOT NULL,
    CONSTRAINT ck_finding_resolutions__fixed CHECK (((resolution_kind <> 'fixed'::text) OR (target_output_id IS NOT NULL))),
    CONSTRAINT ck_finding_resolutions__kind CHECK ((resolution_kind = ANY (ARRAY['fixed'::text, 'rejected_by_triage'::text, 'waived'::text, 'superseded'::text]))),
    CONSTRAINT ck_finding_resolutions__resolved_by CHECK ((jsonb_typeof(resolved_by) = 'object'::text))
);

CREATE TABLE skm_execution.fix_briefs (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    source_review_id uuid,
    source_check_round integer,
    document jsonb NOT NULL,
    digest text NOT NULL,
    truncated boolean NOT NULL,
    full_report_file_version_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_fix_briefs__digest CHECK ((digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_fix_briefs__document CHECK (((jsonb_typeof(document) = 'object'::text) AND ((document ->> 'schema'::text) = 'urn:skm:execution:fix-brief:v1'::text) AND (octet_length((document)::text) <= 1048576))),
    CONSTRAINT ck_fix_briefs__source CHECK (((source_review_id IS NULL) <> (source_check_round IS NULL)))
);

CREATE TABLE skm_execution.incident_gates (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    stop_after uuid,
    fencing_token bigint,
    kind text NOT NULL,
    actor_id uuid NOT NULL,
    reason text NOT NULL,
    details jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT incident_gates_check CHECK (((kind = ANY (ARRAY['abort_step'::text, 'budget_breaker'::text])) = (stop_after IS NOT NULL))),
    CONSTRAINT incident_gates_check1 CHECK (((stop_after IS NULL) OR (fencing_token IS NOT NULL))),
    CONSTRAINT incident_gates_details_check CHECK ((jsonb_typeof(details) = 'object'::text)),
    CONSTRAINT incident_gates_fencing_token_check CHECK ((fencing_token > 0)),
    CONSTRAINT incident_gates_kind_check CHECK ((kind = ANY (ARRAY['reroute_task'::text, 'override_actor'::text, 'steer_task'::text, 'abort_step'::text, 'budget_breaker'::text]))),
    CONSTRAINT incident_gates_reason_check CHECK (((char_length(reason) >= 1) AND (char_length(reason) <= 2000)))
);

CREATE TABLE skm_execution.integration_slots (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    target_branch text NOT NULL,
    writer_host_id uuid NOT NULL,
    holder_attempt_id uuid,
    fencing_token bigint DEFAULT 0 NOT NULL,
    expires_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_integration_slots__branch CHECK (((target_branch ~ '^[A-Za-z0-9._/-]{1,200}$'::text) AND (target_branch !~ '\.\.'::text))),
    CONSTRAINT ck_integration_slots__counters CHECK (((fencing_token >= 0) AND (row_version >= 1))),
    CONSTRAINT ck_integration_slots__holder CHECK (((holder_attempt_id IS NULL) = (expires_at IS NULL)))
);

CREATE TABLE skm_execution.manual_check_verdicts (
    id uuid NOT NULL,
    check_execution_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    verdict text NOT NULL,
    comment text DEFAULT ''::text NOT NULL,
    supersedes_id uuid,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_manual_check_verdicts__comment CHECK ((char_length(comment) <= 4000)),
    CONSTRAINT ck_manual_check_verdicts__supersedes CHECK (((supersedes_id IS NULL) OR (supersedes_id <> id))),
    CONSTRAINT ck_manual_check_verdicts__verdict CHECK ((verdict = ANY (ARRAY['pass'::text, 'fail'::text])))
);

CREATE TABLE skm_execution.output_file_bindings (
    output_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    role text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_output_file_bindings__role CHECK ((role = ANY (ARRAY['patch'::text, 'evidence'::text, 'coverage_report'::text])))
);

CREATE TABLE skm_execution.readiness_reports (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    revision_digest text NOT NULL,
    status text NOT NULL,
    scope jsonb DEFAULT '{"kind": "plan", "phase_keys": []}'::jsonb NOT NULL,
    inputs jsonb NOT NULL,
    inputs_digest text NOT NULL,
    policy_digest text NOT NULL,
    results jsonb NOT NULL,
    findings jsonb DEFAULT '[]'::jsonb NOT NULL,
    assumptions jsonb DEFAULT '[]'::jsonb NOT NULL,
    structural_counts jsonb NOT NULL,
    estimate jsonb NOT NULL,
    audit jsonb,
    supersedes_report_id uuid,
    validator_version integer NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    work_policies jsonb,
    start_request jsonb,
    CONSTRAINT ck_readiness_reports__digests CHECK (((revision_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND (inputs_digest ~ '^sha256:[0-9a-f]{64}$'::text) AND (policy_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_readiness_reports__json CHECK (((jsonb_typeof(scope) = 'object'::text) AND (jsonb_typeof(inputs) = 'object'::text) AND (jsonb_typeof(results) = 'array'::text) AND (jsonb_typeof(findings) = 'array'::text) AND (jsonb_typeof(assumptions) = 'array'::text) AND (jsonb_typeof(structural_counts) = 'object'::text) AND (jsonb_typeof(estimate) = 'object'::text))),
    CONSTRAINT ck_readiness_reports__start_request CHECK (((start_request IS NULL) OR ((jsonb_typeof(start_request) = 'object'::text) AND (octet_length((start_request)::text) <= 1048576)))),
    CONSTRAINT ck_readiness_reports__status CHECK ((status = ANY (ARRAY['ready'::text, 'ready_with_advisories'::text, 'not_ready'::text]))),
    CONSTRAINT ck_readiness_reports__supersedes CHECK (((supersedes_report_id IS NULL) OR ((supersedes_report_id <> id) AND (audit IS NOT NULL)))),
    CONSTRAINT ck_readiness_reports__validator_version CHECK ((validator_version >= 1)),
    CONSTRAINT ck_readiness_reports__work_policies CHECK (((work_policies IS NULL) OR ((jsonb_typeof(work_policies) = 'object'::text) AND (octet_length((work_policies)::text) <= 16777216))))
);

CREATE TABLE skm_execution.result_carry_forwards (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    source_run_id uuid NOT NULL,
    source_task_id uuid NOT NULL,
    source_attempt_id uuid NOT NULL,
    source_output_id uuid NOT NULL,
    target_run_id uuid NOT NULL,
    target_task_id uuid NOT NULL,
    compatibility_digest text NOT NULL,
    compatibility_inputs jsonb NOT NULL,
    decision text NOT NULL,
    approved_by uuid NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_result_carry_forwards__decision CHECK ((decision = ANY (ARRAY['accepted'::text, 'rejected'::text]))),
    CONSTRAINT ck_result_carry_forwards__digest CHECK ((compatibility_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_result_carry_forwards__inputs CHECK ((((jsonb_typeof(compatibility_inputs) = 'object'::text) AND (compatibility_inputs ?& ARRAY['schema_version'::text, 'source'::text, 'target'::text]) AND ((compatibility_inputs ->> 'schema_version'::text) = '1'::text) AND (jsonb_typeof((compatibility_inputs -> 'source'::text)) = 'object'::text) AND (jsonb_typeof((compatibility_inputs -> 'target'::text)) = 'object'::text)) IS TRUE)),
    CONSTRAINT ck_result_carry_forwards__reason CHECK (((char_length(reason) >= 1) AND (char_length(reason) <= 2000))),
    CONSTRAINT ck_result_carry_forwards__runs CHECK ((source_run_id <> target_run_id))
);

CREATE TABLE skm_execution.review_evidence_bindings (
    review_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    role text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_review_evidence_bindings__role CHECK ((role = ANY (ARRAY['report'::text, 'diff'::text, 'transcript'::text, 'evidence'::text])))
);

CREATE TABLE skm_execution.review_findings (
    id uuid NOT NULL,
    review_id uuid NOT NULL,
    task_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    local_id text NOT NULL,
    finding_key text NOT NULL,
    first_seen_review_id uuid NOT NULL,
    severity text NOT NULL,
    confidence text NOT NULL,
    basis text DEFAULT 'correctness'::text NOT NULL,
    category text NOT NULL,
    message text NOT NULL,
    failure_scenario text NOT NULL,
    location jsonb NOT NULL,
    reproduction jsonb,
    state text DEFAULT 'open'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_review_findings__basis CHECK ((basis = ANY (ARRAY['correctness'::text, 'security'::text, 'contract'::text, 'test'::text, 'maintainability'::text, 'docs'::text]))),
    CONSTRAINT ck_review_findings__confidence CHECK ((confidence = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text]))),
    CONSTRAINT ck_review_findings__finding_key CHECK ((finding_key ~ '^fk-[0-9a-f]{16}$'::text)),
    CONSTRAINT ck_review_findings__json CHECK (((jsonb_typeof(location) = 'object'::text) AND ((reproduction IS NULL) OR (jsonb_typeof(reproduction) = 'object'::text)))),
    CONSTRAINT ck_review_findings__local_id CHECK ((local_id ~ '^F[0-9]{1,3}$'::text)),
    CONSTRAINT ck_review_findings__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_review_findings__severity CHECK ((severity = ANY (ARRAY['blocker'::text, 'major'::text, 'minor'::text, 'nit'::text]))),
    CONSTRAINT ck_review_findings__state CHECK ((state = ANY (ARRAY['open'::text, 'confirmed'::text, 'rejected'::text, 'resolved'::text, 'waived'::text, 'deferred'::text]))),
    CONSTRAINT ck_review_findings__texts CHECK ((((char_length(message) >= 1) AND (char_length(message) <= 2000)) AND ((char_length(failure_scenario) >= 1) AND (char_length(failure_scenario) <= 3000)) AND ((char_length(category) >= 1) AND (char_length(category) <= 82))))
);

CREATE TABLE skm_execution.review_requests (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    mount text NOT NULL,
    repository_id uuid NOT NULL,
    target_kind text NOT NULL,
    base_commit text NOT NULL,
    head_commit text,
    patch_file_version_id uuid,
    target_digest text NOT NULL,
    profile_key text DEFAULT 'reviewer'::text NOT NULL,
    reason text NOT NULL,
    requested_by uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_review_requests__commits CHECK (((base_commit ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'::text) AND ((head_commit IS NULL) OR (head_commit ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'::text)))),
    CONSTRAINT ck_review_requests__profile_key CHECK ((profile_key ~ '^[a-z][a-z0-9-]{1,60}$'::text)),
    CONSTRAINT ck_review_requests__reason CHECK (((char_length(reason) >= 1) AND (char_length(reason) <= 2000))),
    CONSTRAINT ck_review_requests__target CHECK ((((target_kind = 'commits'::text) AND (head_commit IS NOT NULL) AND (patch_file_version_id IS NULL)) OR ((target_kind = 'working_tree'::text) AND (head_commit IS NULL) AND (patch_file_version_id IS NOT NULL)))),
    CONSTRAINT ck_review_requests__target_digest CHECK ((target_digest ~ '^sha256:[0-9a-f]{64}$'::text))
);

CREATE TABLE skm_execution.reviews (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    output_id uuid NOT NULL,
    round_no integer NOT NULL,
    reviewer_kind text NOT NULL,
    reviewer_ref jsonb NOT NULL,
    step_id uuid,
    profile_key text NOT NULL,
    profile_version_id uuid,
    audit_scope text NOT NULL,
    state text DEFAULT 'started'::text NOT NULL,
    verdict text,
    freshness text DEFAULT 'fresh'::text NOT NULL,
    base_output_id uuid,
    residual_risk text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT ck_reviews__audit_scope CHECK ((audit_scope = ANY (ARRAY['corrected'::text, 'full'::text, 'range'::text]))),
    CONSTRAINT ck_reviews__base_output CHECK (((round_no = 1) = (base_output_id IS NULL))),
    CONSTRAINT ck_reviews__completed_at CHECK (((completed_at IS NOT NULL) = (state <> 'started'::text))),
    CONSTRAINT ck_reviews__freshness CHECK ((freshness = ANY (ARRAY['fresh'::text, 'findings_only'::text]))),
    CONSTRAINT ck_reviews__profile_key CHECK ((profile_key ~ '^[a-z][a-z0-9-]{1,60}$'::text)),
    CONSTRAINT ck_reviews__reviewer_kind CHECK ((((reviewer_kind = 'agent'::text) AND (step_id IS NOT NULL) AND (profile_version_id IS NOT NULL)) OR ((reviewer_kind = 'human'::text) AND (step_id IS NULL)))),
    CONSTRAINT ck_reviews__round_no CHECK ((round_no >= 1)),
    CONSTRAINT ck_reviews__state CHECK ((state = ANY (ARRAY['started'::text, 'completed'::text, 'failed'::text]))),
    CONSTRAINT ck_reviews__verdict CHECK ((((verdict IS NOT NULL) = (state = 'completed'::text)) AND ((verdict IS NULL) OR (verdict = ANY (ARRAY['green'::text, 'attention'::text, 'red'::text])))))
);

CREATE TABLE skm_execution.revision_visas (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    readiness_report_id uuid NOT NULL,
    selection jsonb,
    signed_by uuid NOT NULL,
    reason text NOT NULL,
    signed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_revision_visas__reason CHECK ((((char_length(reason) >= 1) AND (char_length(reason) <= 2000)) AND (btrim(reason) <> ''::text))),
    CONSTRAINT ck_revision_visas__selection CHECK (((selection IS NULL) OR (jsonb_typeof(selection) = 'object'::text)))
);

CREATE TABLE skm_execution.run_integration_hosts (
    run_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    host_id uuid NOT NULL,
    pinned_at timestamp with time zone NOT NULL
);

CREATE TABLE skm_execution.run_reconfigurations (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    changes jsonb NOT NULL,
    reason text NOT NULL,
    changed_by uuid NOT NULL,
    changed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_run_reconfigurations__changes CHECK (((jsonb_typeof(changes) = 'object'::text) AND (changes <> '{}'::jsonb))),
    CONSTRAINT ck_run_reconfigurations__reason CHECK (((char_length(reason) >= 1) AND (char_length(reason) <= 2000)))
);

CREATE TABLE skm_execution.run_recoveries (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    task_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    stage_record_id uuid NOT NULL,
    step_id uuid,
    workspace_id uuid NOT NULL,
    trigger text NOT NULL,
    steps_done jsonb DEFAULT '[]'::jsonb NOT NULL,
    snapshot_file_version_id uuid,
    outcome text,
    reason_codes text[] DEFAULT '{}'::text[] NOT NULL,
    at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_run_recoveries__finished CHECK (((outcome IS NULL) = (finished_at IS NULL))),
    CONSTRAINT ck_run_recoveries__outcome CHECK (((outcome IS NULL) OR (outcome = ANY (ARRAY['retried'::text, 'new_attempt'::text, 'escalated'::text, 'not_needed'::text])))),
    CONSTRAINT ck_run_recoveries__steps CHECK ((jsonb_typeof(steps_done) = 'array'::text)),
    CONSTRAINT ck_run_recoveries__trigger CHECK ((trigger = ANY (ARRAY['hung'::text, 'suspected_stall'::text, 'orphaned'::text, 'lease_expired'::text])))
);

CREATE TABLE skm_execution.run_task_edges (
    run_id uuid NOT NULL,
    dependent_task_id uuid NOT NULL,
    prerequisite_task_id uuid NOT NULL,
    kind text NOT NULL,
    reasons text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT ck_run_task_edges__kind CHECK ((kind = ANY (ARRAY['blocks'::text, 'batch'::text, 'integration'::text, 'gate_member'::text]))),
    CONSTRAINT ck_run_task_edges__no_self CHECK ((dependent_task_id <> prerequisite_task_id))
);

CREATE TABLE skm_execution.run_tasks (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    run_kind text NOT NULL,
    workspace_id uuid NOT NULL,
    plan_id uuid,
    revision_id uuid,
    kind text NOT NULL,
    spec_entity_id uuid,
    spec_entity_kind text,
    display_key text NOT NULL,
    origin jsonb,
    "position" integer NOT NULL,
    status text DEFAULT 'blocked'::text NOT NULL,
    work_kind text NOT NULL,
    review_mode text NOT NULL,
    review_profile text,
    declared_write_scope jsonb,
    required_host_id uuid,
    current_attempt_id uuid,
    accepted_attempt_id uuid,
    accepted_output_id uuid,
    check_fix_rounds integer DEFAULT 0 NOT NULL,
    review_rounds integer DEFAULT 0 NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    blocking_reason jsonb,
    blocking_code text,
    blocking_next_check_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    live_controls jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_run_tasks__accepted CHECK (((accepted_output_id IS NULL) OR (accepted_attempt_id IS NOT NULL))),
    CONSTRAINT ck_run_tasks__blocking CHECK ((((blocking_reason IS NULL) = (blocking_code IS NULL)) AND ((blocking_reason IS NULL) OR ((blocking_reason ->> 'code'::text) = blocking_code)) AND ((blocking_next_check_at IS NULL) OR (blocking_reason IS NOT NULL)))),
    CONSTRAINT ck_run_tasks__blocking_code CHECK (((blocking_code IS NULL) OR (blocking_code = ANY (ARRAY['WAITING_OWNER'::text, 'WAITING_ANSWER'::text, 'WAITING_ADVISOR'::text, 'WAITING_MANUAL_CHECK'::text, 'WAITING_APPROVAL'::text, 'WAITING_PROVIDER'::text, 'WAITING_BUDGET_RESET'::text, 'BLOCKED_BY_DEPENDENCY'::text, 'BLOCKED_BY_MATERIAL'::text, 'BLOCKED_BY_BUDGET'::text, 'BLOCKED_BY_CAPABILITY'::text, 'BLOCKED_BY_POLICY'::text, 'BLOCKED_BY_INTEGRATION'::text, 'SUSPECTED_STALL'::text, 'RECOVERING'::text])))),
    CONSTRAINT ck_run_tasks__counters CHECK ((("position" >= 0) AND (check_fix_rounds >= 0) AND (review_rounds >= 0) AND (attempt_count >= 0))),
    CONSTRAINT ck_run_tasks__display_key CHECK ((((kind = 'adhoc'::text) AND (display_key ~ '^ADHOC-[0-9]+$'::text)) OR ((kind <> 'adhoc'::text) AND (display_key ~ '^(P[0-9]+(\.[0-9]+)?(/U[0-9]+|#gate)?|INT-[0-9]+|FU-[0-9]+|GR-[0-9]+|PLAN#accept|AUDIT)$'::text)))),
    CONSTRAINT ck_run_tasks__kind CHECK ((kind = ANY (ARRAY['unit'::text, 'item'::text, 'item_gate'::text, 'phase_gate'::text, 'plan_acceptance'::text, 'integration'::text, 'followup'::text, 'group_review'::text, 'plan_audit'::text, 'adhoc'::text]))),
    CONSTRAINT ck_run_tasks__origin CHECK ((((kind = ANY (ARRAY['integration'::text, 'followup'::text, 'group_review'::text])) = (origin IS NOT NULL)) AND ((origin IS NULL) OR (jsonb_typeof(origin) = 'object'::text)))),
    CONSTRAINT ck_run_tasks__review_mode CHECK ((review_mode = ANY (ARRAY['required'::text, 'self'::text, 'waived'::text]))),
    CONSTRAINT ck_run_tasks__review_profile CHECK (((review_profile IS NULL) OR (review_profile ~ '^[a-z][a-z0-9-]{1,60}$'::text))),
    CONSTRAINT ck_run_tasks__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_run_tasks__spec_entity CHECK (((((kind = 'unit'::text) AND (spec_entity_kind = 'unit'::text) AND (spec_entity_id IS NOT NULL)) OR ((kind = ANY (ARRAY['item'::text, 'item_gate'::text])) AND (spec_entity_kind = 'item'::text) AND (spec_entity_id IS NOT NULL)) OR ((kind = 'phase_gate'::text) AND (spec_entity_kind = 'phase'::text) AND (spec_entity_id IS NOT NULL)) OR ((kind = ANY (ARRAY['plan_acceptance'::text, 'integration'::text, 'followup'::text, 'group_review'::text, 'plan_audit'::text, 'adhoc'::text])) AND (spec_entity_id IS NULL) AND (spec_entity_kind IS NULL))) IS TRUE)),
    CONSTRAINT ck_run_tasks__spec_source CHECK ((((kind = 'adhoc'::text) AND (run_kind = 'adhoc'::text) AND (plan_id IS NULL) AND (revision_id IS NULL) AND (spec_entity_id IS NULL) AND (spec_entity_kind IS NULL)) OR ((kind <> 'adhoc'::text) AND (run_kind <> 'adhoc'::text) AND (plan_id IS NOT NULL) AND (revision_id IS NOT NULL)))),
    CONSTRAINT ck_run_tasks__status CHECK ((status = ANY (ARRAY['blocked'::text, 'ready'::text, 'assigned'::text, 'executing'::text, 'checking'::text, 'manual_pending'::text, 'reviewing'::text, 'rework_required'::text, 'awaiting_decision'::text, 'integrating'::text, 'accepted'::text, 'failed'::text, 'cancelled'::text, 'superseded'::text, 'skipped'::text]))),
    CONSTRAINT ck_run_tasks__work_kind CHECK ((work_kind = ANY (ARRAY['code'::text, 'docs'::text, 'research'::text, 'config'::text, 'test'::text, 'review'::text, 'ops'::text]))),
    CONSTRAINT ck_run_tasks__write_scope CHECK (((declared_write_scope IS NULL) OR (jsonb_typeof(declared_write_scope) = 'array'::text))),
    CONSTRAINT run_tasks_live_controls_check CHECK (((jsonb_typeof(live_controls) = 'object'::text) AND (octet_length((live_controls)::text) <= 16384)))
);

CREATE TABLE skm_execution.runs (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    kind text DEFAULT 'plan'::text NOT NULL,
    plan_id uuid,
    revision_id uuid,
    revision_no integer,
    inline_spec_file_version_id uuid,
    status text DEFAULT 'created'::text NOT NULL,
    requested_by uuid NOT NULL,
    readiness_report_id uuid,
    audited_report_id uuid,
    review_request_id uuid,
    compiler_version integer NOT NULL,
    workflow_resource_version_id uuid NOT NULL,
    review_grouping jsonb NOT NULL,
    autopilot boolean DEFAULT false NOT NULL,
    queued boolean DEFAULT false NOT NULL,
    pause_reason text,
    pause_source text,
    stop_code text,
    unmetered_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    CONSTRAINT ck_runs__compiler_version CHECK ((compiler_version >= 1)),
    CONSTRAINT ck_runs__finished_at CHECK ((((finished_at IS NOT NULL) = (status = ANY (ARRAY['succeeded'::text, 'failed'::text, 'cancelled'::text]))) AND ((finished_at IS NULL) OR (started_at IS NULL) OR (finished_at >= started_at)))),
    CONSTRAINT ck_runs__kind CHECK ((kind = ANY (ARRAY['plan'::text, 'review_request'::text, 'readiness_audit'::text, 'adhoc'::text]))),
    CONSTRAINT ck_runs__kind_refs CHECK ((((kind = 'review_request'::text) = (review_request_id IS NOT NULL)) AND ((kind = 'readiness_audit'::text) = (audited_report_id IS NOT NULL)) AND ((kind = 'plan'::text) OR (readiness_report_id IS NULL)))),
    CONSTRAINT ck_runs__pause_reason CHECK (((status = 'paused'::text) = (pause_reason IS NOT NULL))),
    CONSTRAINT ck_runs__pause_source CHECK ((((status = 'paused'::text) = (pause_source IS NOT NULL)) AND ((pause_source IS NULL) OR (pause_source = ANY (ARRAY['system'::text, 'owner'::text]))))),
    CONSTRAINT ck_runs__queued CHECK (((NOT queued) OR (status = 'ready'::text))),
    CONSTRAINT ck_runs__review_grouping CHECK ((jsonb_typeof(review_grouping) = 'object'::text)),
    CONSTRAINT ck_runs__revision_no CHECK ((revision_no >= 1)),
    CONSTRAINT ck_runs__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_runs__spec_source CHECK ((((kind = 'adhoc'::text) AND (plan_id IS NULL) AND (revision_id IS NULL) AND (revision_no IS NULL) AND (inline_spec_file_version_id IS NOT NULL)) OR ((kind <> 'adhoc'::text) AND (plan_id IS NOT NULL) AND (revision_id IS NOT NULL) AND (revision_no IS NOT NULL) AND (inline_spec_file_version_id IS NULL)))),
    CONSTRAINT ck_runs__started_at CHECK (((started_at IS NULL) = (status = ANY (ARRAY['created'::text, 'ready'::text])))),
    CONSTRAINT ck_runs__status CHECK ((status = ANY (ARRAY['created'::text, 'ready'::text, 'running'::text, 'waiting'::text, 'paused'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text]))),
    CONSTRAINT ck_runs__stop_code CHECK (((stop_code IS NULL) OR ((stop_code ~ '^[A-Z][A-Z0-9_]{2,63}$'::text) AND (status = ANY (ARRAY['waiting'::text, 'paused'::text, 'failed'::text])))))
);

CREATE TABLE skm_execution.step_notes (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    step_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    fencing_token bigint NOT NULL,
    kind text NOT NULL,
    text text NOT NULL,
    options jsonb,
    why_blocked text,
    urgency text,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_step_notes__fence CHECK ((fencing_token >= 1)),
    CONSTRAINT ck_step_notes__kind CHECK ((kind = ANY (ARRAY['progress'::text, 'assumption'::text, 'risk'::text, 'question'::text]))),
    CONSTRAINT ck_step_notes__options CHECK (((options IS NULL) OR ((kind = 'question'::text) AND (jsonb_typeof(options) = 'array'::text) AND (octet_length((options)::text) <= 65536)))),
    CONSTRAINT ck_step_notes__text CHECK (((char_length(text) >= 1) AND (char_length(text) <= 20000))),
    CONSTRAINT ck_step_notes__urgency CHECK (((urgency IS NULL) OR ((kind = 'question'::text) AND (urgency = ANY (ARRAY['normal'::text, 'blocking'::text]))))),
    CONSTRAINT ck_step_notes__why CHECK (((why_blocked IS NULL) OR ((kind = 'question'::text) AND (char_length(why_blocked) <= 2000))))
);

CREATE TABLE skm_execution.step_tool_calls (
    step_id uuid NOT NULL,
    call_id text NOT NULL COLLATE pg_catalog."C",
    tool text,
    duration_ms bigint,
    coverage text NOT NULL,
    fencing_token bigint NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT step_tool_calls_call_id_check CHECK (((char_length(call_id) >= 1) AND (char_length(call_id) <= 300))),
    CONSTRAINT step_tool_calls_coverage_check CHECK ((coverage = ANY (ARRAY['complete'::text, 'partial'::text]))),
    CONSTRAINT step_tool_calls_duration_ms_check CHECK ((duration_ms >= 0)),
    CONSTRAINT step_tool_calls_fencing_token_check CHECK ((fencing_token > 0)),
    CONSTRAINT step_tool_calls_tool_check CHECK (((char_length(tool) >= 1) AND (char_length(tool) <= 300)))
);

CREATE TABLE skm_exports.vault_note_writes (
    note_id uuid NOT NULL,
    vault_id uuid NOT NULL,
    generation bigint NOT NULL,
    host_id uuid NOT NULL,
    relative_path text NOT NULL,
    expected_digest text NOT NULL,
    observed_digest text NOT NULL,
    outcome text NOT NULL,
    written_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_vault_note_writes__expected_digest CHECK ((expected_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_vault_note_writes__generation CHECK ((generation > 0)),
    CONSTRAINT ck_vault_note_writes__observed_digest CHECK ((observed_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_vault_note_writes__outcome CHECK ((outcome = ANY (ARRAY['created'::text, 'verified_existing'::text, 'modified_existing'::text]))),
    CONSTRAINT ck_vault_note_writes__outcome_digest CHECK ((((outcome = ANY (ARRAY['created'::text, 'verified_existing'::text])) AND (observed_digest = expected_digest)) OR ((outcome = 'modified_existing'::text) AND (observed_digest <> expected_digest)))),
    CONSTRAINT ck_vault_note_writes__relative_path CHECK ((((char_length(relative_path) >= 1) AND (char_length(relative_path) <= 1024)) AND (relative_path !~ '(^/|(^|/)\.\.(/|$))'::text)))
);

CREATE TABLE skm_exports.vault_notes (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    kind text NOT NULL,
    event_id uuid NOT NULL,
    source_id uuid NOT NULL,
    name text NOT NULL,
    subfolder text NOT NULL,
    body text NOT NULL,
    body_digest text NOT NULL,
    generation bigint DEFAULT 1 NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    requeued_at timestamp with time zone,
    CONSTRAINT ck_vault_notes__body CHECK ((octet_length(body) <= 262144)),
    CONSTRAINT ck_vault_notes__body_digest CHECK ((body_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_vault_notes__generation CHECK ((generation > 0)),
    CONSTRAINT ck_vault_notes__kind CHECK ((kind = ANY (ARRAY['plan_archived'::text, 'run_finished'::text]))),
    CONSTRAINT ck_vault_notes__name CHECK ((((octet_length(name) >= 4) AND (octet_length(name) <= 240)) AND (name ~~ '%.md'::text) AND (POSITION(('/'::text) IN (name)) = 0))),
    CONSTRAINT ck_vault_notes__state CHECK ((state = ANY (ARRAY['pending'::text, 'cancelled'::text, 'expired'::text]))),
    CONSTRAINT ck_vault_notes__subfolder CHECK ((subfolder = ANY (ARRAY['plans'::text, 'runs'::text])))
);

CREATE TABLE skm_extensions.pack_versions (
    id uuid NOT NULL,
    pack_id uuid NOT NULL,
    version text NOT NULL,
    version_major integer NOT NULL,
    version_minor integer NOT NULL,
    version_patch integer NOT NULL,
    prerelease text,
    digest text NOT NULL,
    manifest jsonb NOT NULL,
    priority integer NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    origin text NOT NULL,
    installed_at timestamp with time zone NOT NULL,
    installed_by uuid NOT NULL,
    CONSTRAINT ck_pack_versions__digest CHECK ((digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_pack_versions__origin CHECK (((origin = ANY (ARRAY['builtin'::text, 'runtime_catalog_snapshot'::text])) OR (origin ~ '^(path|archive):.{1,200}$'::text))),
    CONSTRAINT ck_pack_versions__priority CHECK (((priority >= '-1000'::integer) AND (priority <= 1000))),
    CONSTRAINT ck_pack_versions__state CHECK ((state = ANY (ARRAY['active'::text, 'retired'::text]))),
    CONSTRAINT ck_pack_versions__version CHECK ((version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'::text)),
    CONSTRAINT ck_pack_versions__version_parts CHECK (((version_major >= 0) AND (version_minor >= 0) AND (version_patch >= 0) AND (version = (((((version_major || '.'::text) || version_minor) || '.'::text) || version_patch) || COALESCE(('-'::text || prerelease), ''::text)))))
);

CREATE TABLE skm_extensions.packs (
    id uuid NOT NULL,
    slug text NOT NULL,
    title text NOT NULL,
    publisher text NOT NULL,
    trust text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_packs__publisher CHECK ((publisher ~ '^[a-z0-9][a-z0-9.-]{0,62}$'::text)),
    CONSTRAINT ck_packs__slug CHECK ((slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'::text)),
    CONSTRAINT ck_packs__title CHECK (((char_length(title) >= 1) AND (char_length(title) <= 120))),
    CONSTRAINT ck_packs__trust CHECK ((trust = ANY (ARRAY['builtin'::text, 'operator'::text, 'third_party'::text])))
);

CREATE TABLE skm_extensions.resource_files (
    resource_version_id uuid NOT NULL,
    path text NOT NULL,
    size_bytes integer NOT NULL,
    digest text NOT NULL,
    media_type text NOT NULL,
    content bytea NOT NULL,
    CONSTRAINT ck_resource_files__digest CHECK ((digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_resource_files__media_type CHECK (((char_length(media_type) >= 1) AND (char_length(media_type) <= 100))),
    CONSTRAINT ck_resource_files__path CHECK (((path !~ '^/'::text) AND (path !~ '(^|/)\.\.(/|$)'::text) AND (path !~ '\\'::text) AND ((char_length(path) >= 1) AND (char_length(path) <= 300)))),
    CONSTRAINT ck_resource_files__size CHECK ((((size_bytes >= 0) AND (size_bytes <= 1048576)) AND (size_bytes = octet_length(content))))
);

CREATE TABLE skm_extensions.resource_quarantine (
    id uuid NOT NULL,
    resource_version_id uuid NOT NULL,
    reason_kind text NOT NULL,
    reasons jsonb NOT NULL,
    report jsonb,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    released_by uuid,
    released_at timestamp with time zone,
    release_reason text,
    CONSTRAINT ck_resource_quarantine__reason_kind CHECK ((reason_kind = ANY (ARRAY['compat'::text, 'manual'::text]))),
    CONSTRAINT ck_resource_quarantine__reasons CHECK (((jsonb_typeof(reasons) = 'array'::text) AND (jsonb_array_length(reasons) >= 1))),
    CONSTRAINT ck_resource_quarantine__release_reason CHECK (((release_reason IS NULL) OR ((char_length(release_reason) >= 1) AND (char_length(release_reason) <= 1000)))),
    CONSTRAINT ck_resource_quarantine__released CHECK ((((released_at IS NULL) = (released_by IS NULL)) AND ((released_at IS NULL) = (release_reason IS NULL))))
);

CREATE TABLE skm_extensions.resource_versions (
    id uuid NOT NULL,
    resource_id uuid NOT NULL,
    pack_version_id uuid NOT NULL,
    version text NOT NULL,
    digest text NOT NULL,
    manifest jsonb NOT NULL,
    tokens_estimate integer NOT NULL,
    compat_verdict text NOT NULL,
    compat_report jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_resource_versions__compat_verdict CHECK ((compat_verdict = ANY (ARRAY['clean'::text, 'quarantine'::text]))),
    CONSTRAINT ck_resource_versions__digest CHECK ((digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_resource_versions__tokens CHECK ((tokens_estimate >= 0)),
    CONSTRAINT ck_resource_versions__version CHECK ((version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'::text))
);

CREATE TABLE skm_extensions.resources (
    id uuid NOT NULL,
    kind text NOT NULL,
    key text NOT NULL,
    first_pack_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_resources__key CHECK ((((kind = 'prompt_block'::text) AND (key ~ '^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9_-]*$'::text)) OR ((kind <> 'prompt_block'::text) AND (key ~ '^[a-z0-9][a-z0-9-]{1,80}$'::text)))),
    CONSTRAINT ck_resources__kind CHECK ((kind = ANY (ARRAY['skill'::text, 'steering'::text, 'agent_profile'::text, 'workflow'::text, 'plan_template'::text, 'prompt_block'::text, 'integration_bundle'::text, 'runtime_catalog'::text, 'model_guideline'::text])))
);

CREATE TABLE skm_integrations.projection_files (
    projection_id uuid NOT NULL,
    relative_path text NOT NULL,
    surface text NOT NULL,
    ownership text NOT NULL,
    block_ids text[] DEFAULT '{}'::text[] NOT NULL,
    owned_keys jsonb DEFAULT '[]'::jsonb NOT NULL,
    applied_managed_digest text NOT NULL,
    applied_whole_digest text NOT NULL,
    pre_image_file_version_id uuid,
    renderer text NOT NULL,
    applied_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_projection_files__applied_managed_digest CHECK ((applied_managed_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_projection_files__applied_whole_digest CHECK ((applied_whole_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_projection_files__boundary CHECK ((((ownership = 'managed_block'::text) AND (cardinality(block_ids) >= 1) AND (owned_keys = '[]'::jsonb)) OR ((ownership = ANY (ARRAY['merged_json'::text, 'merged_toml'::text])) AND (cardinality(block_ids) = 0) AND (jsonb_typeof(owned_keys) = 'array'::text) AND (jsonb_array_length(owned_keys) >= 1)) OR ((ownership = 'managed_file'::text) AND (cardinality(block_ids) = 0) AND (owned_keys = '[]'::jsonb)))),
    CONSTRAINT ck_projection_files__ownership CHECK ((ownership = ANY (ARRAY['managed_file'::text, 'managed_block'::text, 'merged_json'::text, 'merged_toml'::text]))),
    CONSTRAINT ck_projection_files__relative_path CHECK ((((char_length(relative_path) >= 1) AND (char_length(relative_path) <= 1024)) AND (relative_path !~ '(^/|^[A-Za-z]:|\\|(^|/)\.\.?(/|$))'::text) AND (POSITION(('
'::text) IN (relative_path)) = 0))),
    CONSTRAINT ck_projection_files__renderer CHECK ((renderer ~ '^[a-z][a-z0-9_]{1,31}\.[a-z_]{1,32}@[0-9]+$'::text)),
    CONSTRAINT ck_projection_files__surface CHECK ((surface = ANY (ARRAY['instructions'::text, 'skills'::text, 'permissions'::text, 'hooks'::text, 'mcp'::text, 'agents'::text])))
);

CREATE TABLE skm_integrations.projections (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    checkout_binding_id uuid NOT NULL,
    target text NOT NULL,
    state text DEFAULT 'pending'::text NOT NULL,
    desired_digest text,
    applied_desired_digest text,
    renderer_version text,
    applied_at timestamp with time zone,
    drift_checked_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_projections__applied_desired_digest CHECK (((applied_desired_digest IS NULL) OR (applied_desired_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_projections__desired_digest CHECK (((desired_digest IS NULL) OR (desired_digest ~ '^sha256:[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_projections__in_sync CHECK (((state <> 'in_sync'::text) OR ((applied_desired_digest IS NOT NULL) AND (applied_desired_digest = desired_digest)))),
    CONSTRAINT ck_projections__renderer_version CHECK (((renderer_version IS NULL) OR (renderer_version ~ '^[a-z][a-z0-9_]{1,31}@[0-9]+$'::text))),
    CONSTRAINT ck_projections__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_projections__state CHECK ((state = ANY (ARRAY['pending'::text, 'in_sync'::text, 'drifted'::text, 'failed'::text, 'removed'::text]))),
    CONSTRAINT ck_projections__target CHECK ((target ~ '^[a-z][a-z0-9_]{1,31}$'::text))
);

CREATE TABLE skm_knowledge.graph_edges (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    src_node_id uuid NOT NULL,
    dst_node_id uuid NOT NULL,
    type text NOT NULL,
    attrs jsonb DEFAULT '{}'::jsonb NOT NULL,
    source text NOT NULL,
    source_key text DEFAULT ''::text NOT NULL,
    repository_id uuid,
    basis text,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_graph_edges__attrs CHECK (((jsonb_typeof(attrs) = 'object'::text) AND (octet_length((attrs)::text) < 8192))),
    CONSTRAINT ck_graph_edges__basis CHECK (((basis IS NULL) OR (basis = ANY (ARRAY['declared'::text, 'lsp'::text, 'ast'::text, 'text'::text, 'heuristic'::text])))),
    CONSTRAINT ck_graph_edges__source CHECK ((source ~ '^[a-z][a-z0-9-]{1,40}$'::text)),
    CONSTRAINT ck_graph_edges__source_key CHECK ((char_length(source_key) <= 300)),
    CONSTRAINT ck_graph_edges__type CHECK ((type = ANY (ARRAY['uses'::text, 'knows'::text, 'relates_to'::text, 'belongs_to'::text, 'depends_on'::text, 'provided_by'::text, 'requires'::text, 'references'::text])))
);

CREATE TABLE skm_knowledge.graph_indexes (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    repository_id uuid,
    source text NOT NULL,
    generation integer NOT NULL,
    revision text,
    dirty boolean DEFAULT false NOT NULL,
    languages text[] DEFAULT '{}'::text[] NOT NULL,
    basis_default text NOT NULL,
    tool_name text NOT NULL,
    tool_version text NOT NULL,
    indexed_at timestamp with time zone NOT NULL,
    completeness text NOT NULL,
    limitations jsonb DEFAULT '[]'::jsonb NOT NULL,
    files_indexed integer DEFAULT 0 NOT NULL,
    files_skipped integer DEFAULT 0 NOT NULL,
    nodes integer DEFAULT 0 NOT NULL,
    edges integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_graph_indexes__basis_default CHECK ((basis_default = ANY (ARRAY['declared'::text, 'lsp'::text, 'ast'::text, 'text'::text, 'heuristic'::text]))),
    CONSTRAINT ck_graph_indexes__completeness CHECK ((completeness = ANY (ARRAY['complete'::text, 'partial'::text, 'unknown'::text]))),
    CONSTRAINT ck_graph_indexes__counts CHECK (((files_indexed >= 0) AND (files_skipped >= 0) AND (nodes >= 0) AND (edges >= 0))),
    CONSTRAINT ck_graph_indexes__generation CHECK ((generation >= 1)),
    CONSTRAINT ck_graph_indexes__limitations CHECK ((jsonb_typeof(limitations) = 'array'::text)),
    CONSTRAINT ck_graph_indexes__revision CHECK (((revision IS NULL) OR (revision ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'::text))),
    CONSTRAINT ck_graph_indexes__source CHECK ((source ~ '^[a-z][a-z0-9-]{1,40}$'::text))
);

CREATE TABLE skm_knowledge.graph_nodes (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    repository_id uuid,
    node_key text NOT NULL,
    type text NOT NULL,
    attrs jsonb DEFAULT '{}'::jsonb NOT NULL,
    source text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_graph_nodes__attrs CHECK (((jsonb_typeof(attrs) = 'object'::text) AND (octet_length((attrs)::text) < 16384))),
    CONSTRAINT ck_graph_nodes__node_key CHECK ((((char_length(node_key) >= 3) AND (char_length(node_key) <= 340)) AND (node_key ~~ (type || ':%'::text)))),
    CONSTRAINT ck_graph_nodes__source CHECK ((source ~ '^[a-z][a-z0-9-]{1,40}$'::text)),
    CONSTRAINT ck_graph_nodes__type CHECK ((type = ANY (ARRAY['project'::text, 'agent'::text, 'memory'::text, 'skill'::text, 'entity'::text, 'tool'::text, 'package'::text, 'doc'::text, 'symbol'::text])))
);

CREATE TABLE skm_knowledge.lessons (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    scope_id uuid NOT NULL,
    kind text NOT NULL,
    trigger text NOT NULL,
    action text NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    confidence double precision NOT NULL,
    confidence_tier text NOT NULL,
    state text DEFAULT 'curated'::text NOT NULL,
    candidate_id uuid NOT NULL,
    promoted_by uuid NOT NULL,
    promoted_at timestamp with time zone NOT NULL,
    deprecated_by uuid,
    deprecated_at timestamp with time zone,
    deprecation_reason text,
    supersedes_id uuid,
    review_flag text DEFAULT 'none'::text NOT NULL,
    applicability jsonb DEFAULT '{}'::jsonb NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_lessons__action CHECK (((char_length(action) >= 1) AND (char_length(action) <= 1000))),
    CONSTRAINT ck_lessons__applicability CHECK (((jsonb_typeof(applicability) = 'object'::text) AND (octet_length((applicability)::text) <= 16384))),
    CONSTRAINT ck_lessons__confidence CHECK (((confidence >= (0)::double precision) AND (confidence < (1)::double precision))),
    CONSTRAINT ck_lessons__confidence_tier CHECK ((confidence_tier = ANY (ARRAY['none'::text, 'tentative'::text, 'moderate'::text, 'strong'::text, 'core'::text]))),
    CONSTRAINT ck_lessons__deprecation CHECK ((((state = 'curated'::text) AND (deprecated_at IS NULL) AND (deprecated_by IS NULL) AND (deprecation_reason IS NULL)) OR ((state = 'deprecated'::text) AND (deprecated_at IS NOT NULL) AND (deprecated_by IS NOT NULL) AND ((char_length(deprecation_reason) >= 1) AND (char_length(deprecation_reason) <= 500))))),
    CONSTRAINT ck_lessons__evidence CHECK (((jsonb_typeof(evidence) = 'array'::text) AND (jsonb_array_length(evidence) <= 50))),
    CONSTRAINT ck_lessons__kind CHECK ((kind = ANY (ARRAY['heuristic'::text, 'procedure'::text, 'gotcha'::text]))),
    CONSTRAINT ck_lessons__review_flag CHECK ((review_flag = ANY (ARRAY['none'::text, 'decay'::text]))),
    CONSTRAINT ck_lessons__state CHECK ((state = ANY (ARRAY['curated'::text, 'deprecated'::text]))),
    CONSTRAINT ck_lessons__trigger CHECK (((char_length(trigger) >= 1) AND (char_length(trigger) <= 500)))
);

CREATE TABLE skm_knowledge.memory_entries (
    id uuid NOT NULL,
    scope_kind text NOT NULL,
    scope_id uuid,
    namespace text,
    workspace_id uuid,
    kind text NOT NULL,
    body text NOT NULL,
    state text DEFAULT 'live'::text NOT NULL,
    writer text NOT NULL,
    source text NOT NULL,
    created_by uuid NOT NULL,
    supersedes_id uuid,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    state_changed_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_memory_entries__body CHECK ((((char_length(body) >= 1) AND (char_length(body) <= 2000)) AND (body = btrim(body)))),
    CONSTRAINT ck_memory_entries__kind CHECK ((kind = ANY (ARRAY['context'::text, 'fact'::text, 'blocker'::text, 'coordination'::text, 'active_handoff'::text, 'health_probe'::text]))),
    CONSTRAINT ck_memory_entries__namespace CHECK (((namespace IS NULL) OR (namespace ~ '^[a-z][a-z0-9-]{1,40}$'::text))),
    CONSTRAINT ck_memory_entries__scope_kind CHECK ((scope_kind = ANY (ARRAY['project'::text, 'namespace'::text, 'global'::text]))),
    CONSTRAINT ck_memory_entries__scope_shape CHECK ((((scope_kind = 'project'::text) AND (scope_id IS NOT NULL) AND (namespace IS NULL) AND (workspace_id IS NOT NULL)) OR ((scope_kind = 'namespace'::text) AND (scope_id IS NULL) AND (namespace IS NOT NULL) AND (workspace_id IS NOT NULL)) OR ((scope_kind = 'global'::text) AND (scope_id IS NULL) AND (namespace IS NULL) AND (workspace_id IS NULL)))),
    CONSTRAINT ck_memory_entries__source CHECK ((source = ANY (ARRAY['cli'::text, 'mcp'::text, 'hook'::text, 'api'::text, 'internal'::text]))),
    CONSTRAINT ck_memory_entries__state CHECK ((state = ANY (ARRAY['live'::text, 'forgotten'::text, 'expired'::text, 'superseded'::text]))),
    CONSTRAINT ck_memory_entries__state_changed_at CHECK (((state = 'live'::text) = (state_changed_at IS NULL))),
    CONSTRAINT ck_memory_entries__ttl CHECK (((expires_at > created_at) AND (expires_at <= (created_at + '72:00:00'::interval)))),
    CONSTRAINT ck_memory_entries__writer CHECK ((writer ~ '^[a-z][a-z0-9_]{1,31}$'::text))
);

CREATE TABLE skm_learning.activity_records (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    scope_id uuid NOT NULL,
    source_kind text NOT NULL,
    source_key text NOT NULL,
    run_id uuid,
    task_id uuid,
    attempt_id uuid,
    outcome text NOT NULL,
    task_outcome text,
    exposure_coverage text DEFAULT 'unknown'::text NOT NULL,
    exposed_lesson_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    detector_evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    pathology_codes text[] DEFAULT '{}'::text[] NOT NULL,
    summary_digest text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_activity_records__detector_evidence CHECK (((jsonb_typeof(detector_evidence) = 'array'::text) AND (octet_length((detector_evidence)::text) <= 65536))),
    CONSTRAINT ck_activity_records__exposure CHECK (((exposure_coverage = ANY (ARRAY['complete'::text, 'unknown'::text])) AND (jsonb_typeof(exposed_lesson_refs) = 'array'::text))),
    CONSTRAINT ck_activity_records__outcome CHECK ((outcome = ANY (ARRAY['success'::text, 'failure'::text, 'unknown'::text]))),
    CONSTRAINT ck_activity_records__pathology_codes CHECK ((pathology_codes <@ ARRAY['file_reread'::text, 'tool_error_loop'::text, 'no_op_run'::text, 'no_verify'::text, 'cache_miss'::text, 'retrieval_stuffing'::text, 'protected_write'::text, 'static_context'::text, 'fanout'::text])),
    CONSTRAINT ck_activity_records__source_kind CHECK ((source_kind = ANY (ARRAY['attempt'::text, 'client_session'::text]))),
    CONSTRAINT ck_activity_records__source_shape CHECK ((((source_kind = 'attempt'::text) AND (attempt_id IS NOT NULL) AND (task_id IS NOT NULL) AND (run_id IS NOT NULL) AND (source_key = (attempt_id)::text)) OR ((source_kind = 'client_session'::text) AND (attempt_id IS NULL) AND (source_key ~ '^[a-z][a-z0-9_]{1,31}:[^\s]{1,200}$'::text)))),
    CONSTRAINT ck_activity_records__summary_digest CHECK ((summary_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_activity_records__task_outcome CHECK (((task_outcome IS NULL) OR (task_outcome = ANY (ARRAY['success'::text, 'failure'::text, 'unknown'::text]))))
);

CREATE TABLE skm_learning.candidate_proposals (
    id uuid NOT NULL,
    scope_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    source_candidate_id uuid NOT NULL,
    source_activity_id uuid NOT NULL,
    source_key text NOT NULL,
    kind text NOT NULL,
    trigger text NOT NULL,
    action text NOT NULL,
    fingerprint text NOT NULL,
    detector_version text NOT NULL,
    relation text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_candidate_proposals__action CHECK (((char_length(action) >= 1) AND (char_length(action) <= 1000))),
    CONSTRAINT ck_candidate_proposals__detector_version CHECK (((char_length(detector_version) >= 1) AND (char_length(detector_version) <= 100))),
    CONSTRAINT ck_candidate_proposals__fingerprint CHECK ((fingerprint ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_candidate_proposals__kind CHECK ((kind = ANY (ARRAY['heuristic'::text, 'procedure'::text, 'gotcha'::text]))),
    CONSTRAINT ck_candidate_proposals__not_self CHECK ((candidate_id <> source_candidate_id)),
    CONSTRAINT ck_candidate_proposals__relation CHECK ((relation = ANY (ARRAY['update'::text, 'conflict'::text]))),
    CONSTRAINT ck_candidate_proposals__trigger CHECK (((char_length(trigger) >= 1) AND (char_length(trigger) <= 500)))
);

CREATE TABLE skm_learning.candidate_reviews (
    id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    proposal_id uuid,
    reviewer_id uuid NOT NULL,
    reviewer_kind text NOT NULL,
    verdict text NOT NULL,
    note text,
    edited_trigger text,
    edited_action text,
    edited_kind text,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_candidate_reviews__edit CHECK (((verdict = 'edit'::text) = ((edited_trigger IS NOT NULL) OR (edited_action IS NOT NULL) OR (edited_kind IS NOT NULL)))),
    CONSTRAINT ck_candidate_reviews__edited_kind CHECK (((edited_kind IS NULL) OR (edited_kind = ANY (ARRAY['heuristic'::text, 'procedure'::text, 'gotcha'::text])))),
    CONSTRAINT ck_candidate_reviews__human_only CHECK (((reviewer_kind = 'human'::text) OR (verdict = ANY (ARRAY['approve'::text, 'comment'::text])))),
    CONSTRAINT ck_candidate_reviews__note CHECK (((note IS NULL) OR (char_length(note) <= 2000))),
    CONSTRAINT ck_candidate_reviews__reviewer_kind CHECK ((reviewer_kind = ANY (ARRAY['human'::text, 'service'::text, 'worker'::text]))),
    CONSTRAINT ck_candidate_reviews__verdict CHECK ((verdict = ANY (ARRAY['approve'::text, 'reject'::text, 'edit'::text, 'comment'::text])))
);

CREATE TABLE skm_learning.candidates (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    scope_id uuid NOT NULL,
    display_key text NOT NULL,
    detector text NOT NULL,
    pathology_code text,
    kind text NOT NULL,
    trigger text NOT NULL,
    action text NOT NULL,
    review_hint text,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    fingerprint text NOT NULL,
    state text DEFAULT 'observed'::text NOT NULL,
    s_total integer DEFAULT 0 NOT NULL,
    n_total integer DEFAULT 0 NOT NULL,
    known_outcome_total integer DEFAULT 0 NOT NULL,
    unknown_outcome_total integer DEFAULT 0 NOT NULL,
    independent_known_total integer DEFAULT 0 NOT NULL,
    independent_success_total integer DEFAULT 0 NOT NULL,
    exposed_total integer DEFAULT 0 NOT NULL,
    exposure_unknown_total integer DEFAULT 0 NOT NULL,
    support_score double precision DEFAULT 0 NOT NULL,
    freshness double precision DEFAULT 0 NOT NULL,
    stale boolean DEFAULT false NOT NULL,
    tests_total integer DEFAULT 0 NOT NULL,
    tests_passed integer DEFAULT 0 NOT NULL,
    days_since integer DEFAULT 0 NOT NULL,
    confidence double precision DEFAULT 0 NOT NULL,
    confidence_tier text DEFAULT 'none'::text NOT NULL,
    curated_ready boolean DEFAULT false NOT NULL,
    conflicts_with_id uuid,
    lesson_id uuid,
    recomputed_at timestamp with time zone,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_candidates__action CHECK (((char_length(action) >= 1) AND (char_length(action) <= 1000))),
    CONSTRAINT ck_candidates__confidence CHECK (((confidence >= (0)::double precision) AND (confidence < (1)::double precision) AND (support_score >= (0)::double precision) AND (support_score < (1)::double precision) AND ((freshness >= (0)::double precision) AND (freshness <= (1)::double precision)))),
    CONSTRAINT ck_candidates__confidence_tier CHECK ((confidence_tier = ANY (ARRAY['none'::text, 'tentative'::text, 'moderate'::text, 'strong'::text, 'core'::text]))),
    CONSTRAINT ck_candidates__counters CHECK (((n_total >= 0) AND (known_outcome_total >= 0) AND (unknown_outcome_total >= 0) AND ((known_outcome_total + unknown_outcome_total) = n_total) AND ((s_total >= 0) AND (s_total <= known_outcome_total)) AND ((independent_known_total >= 0) AND (independent_known_total <= known_outcome_total)) AND ((independent_success_total >= 0) AND (independent_success_total <= independent_known_total)) AND (independent_success_total <= s_total) AND (exposed_total >= 0) AND (exposure_unknown_total >= 0) AND ((exposed_total + exposure_unknown_total) <= n_total) AND (independent_known_total <= ((n_total - exposed_total) - exposure_unknown_total)) AND (tests_total >= 0) AND ((tests_passed >= 0) AND (tests_passed <= tests_total)) AND (days_since >= 0))),
    CONSTRAINT ck_candidates__detector CHECK ((detector = ANY (ARRAY['resolved_failure'::text, 'workaround'::text, 'pathology'::text, 'workflow_relaunch'::text]))),
    CONSTRAINT ck_candidates__display_key CHECK ((display_key ~ '^LC-[1-9][0-9]*$'::text)),
    CONSTRAINT ck_candidates__evidence CHECK (((jsonb_typeof(evidence) = 'array'::text) AND (jsonb_array_length(evidence) <= 50))),
    CONSTRAINT ck_candidates__fingerprint CHECK ((fingerprint ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_candidates__kind CHECK ((kind = ANY (ARRAY['heuristic'::text, 'procedure'::text, 'gotcha'::text]))),
    CONSTRAINT ck_candidates__meta CHECK (((jsonb_typeof(meta) = 'object'::text) AND (octet_length((meta)::text) < 16384))),
    CONSTRAINT ck_candidates__no_self_conflict CHECK (((conflicts_with_id IS NULL) OR (conflicts_with_id <> id))),
    CONSTRAINT ck_candidates__pathology_code CHECK ((((detector = 'pathology'::text) = (pathology_code IS NOT NULL)) AND ((pathology_code IS NULL) OR (pathology_code = ANY (ARRAY['file_reread'::text, 'tool_error_loop'::text, 'no_verify'::text, 'protected_write'::text]))))),
    CONSTRAINT ck_candidates__promoted CHECK (((state = 'promoted'::text) = (lesson_id IS NOT NULL))),
    CONSTRAINT ck_candidates__review_hint CHECK (((review_hint IS NULL) OR (char_length(review_hint) <= 300))),
    CONSTRAINT ck_candidates__state CHECK ((state = ANY (ARRAY['observed'::text, 'candidate'::text, 'promoted'::text, 'rejected'::text, 'deprecated'::text]))),
    CONSTRAINT ck_candidates__trigger CHECK (((char_length(trigger) >= 1) AND (char_length(trigger) <= 500)))
);

CREATE TABLE skm_learning.signals (
    id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    activity_record_id uuid NOT NULL,
    source text NOT NULL,
    sessions_total integer DEFAULT 1 NOT NULL,
    sessions_known integer NOT NULL,
    sessions_success integer NOT NULL,
    evidence_dependency text NOT NULL,
    tests_total integer DEFAULT 0 NOT NULL,
    tests_passed integer DEFAULT 0 NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_signals__counters CHECK (((sessions_total = 1) AND (sessions_known = ANY (ARRAY[0, 1])) AND ((sessions_success >= 0) AND (sessions_success <= sessions_known)) AND (tests_total >= 0) AND ((tests_passed >= 0) AND (tests_passed <= tests_total)))),
    CONSTRAINT ck_signals__dependency CHECK ((evidence_dependency = ANY (ARRAY['independent'::text, 'exposed'::text, 'unknown'::text]))),
    CONSTRAINT ck_signals__source CHECK ((source = 'extract'::text))
);

CREATE TABLE skm_planning.acceptance_criteria (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    criterion_id uuid NOT NULL,
    entity_kind text DEFAULT 'criterion'::text NOT NULL,
    owner_entity_id uuid NOT NULL,
    owner_kind text NOT NULL,
    "position" integer NOT NULL,
    statement text NOT NULL,
    verification_mode text NOT NULL,
    CONSTRAINT ck_acceptance_criteria__entity_kind_valid CHECK ((entity_kind = 'criterion'::text)),
    CONSTRAINT ck_acceptance_criteria__owner_kind_valid CHECK ((owner_kind = ANY (ARRAY['item'::text, 'unit'::text]))),
    CONSTRAINT ck_acceptance_criteria__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_acceptance_criteria__verification_mode_valid CHECK ((verification_mode = ANY (ARRAY['check'::text, 'review'::text, 'manual'::text])))
);

CREATE TABLE skm_planning.artifact_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    item_id uuid NOT NULL,
    "position" integer NOT NULL,
    artifact_key text,
    role text NOT NULL,
    mount_name text NOT NULL,
    path text NOT NULL,
    note text,
    CONSTRAINT ck_artifact_specs__artifact_key_valid CHECK ((artifact_key ~ '^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$'::text)),
    CONSTRAINT ck_artifact_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_artifact_specs__role_valid CHECK ((role = ANY (ARRAY['input'::text, 'output'::text])))
);

CREATE TABLE skm_planning.batch_members (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    phase_id uuid NOT NULL,
    batch_key text NOT NULL,
    item_id uuid NOT NULL,
    "position" integer NOT NULL,
    CONSTRAINT ck_batch_members__position_valid CHECK (("position" >= 0))
);

CREATE TABLE skm_planning.batch_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    phase_id uuid NOT NULL,
    batch_key text NOT NULL,
    "position" integer NOT NULL,
    mode text NOT NULL,
    note text,
    CONSTRAINT ck_batch_specs__batch_key_valid CHECK ((batch_key ~ '^B[0-9A-Za-z-]+$'::text)),
    CONSTRAINT ck_batch_specs__mode_valid CHECK ((mode = ANY (ARRAY['recommended'::text, 'required'::text]))),
    CONSTRAINT ck_batch_specs__position_valid CHECK (("position" >= 0))
);

CREATE TABLE skm_planning.check_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    check_id uuid NOT NULL,
    entity_kind text DEFAULT 'check'::text NOT NULL,
    owner_entity_id uuid NOT NULL,
    owner_kind text NOT NULL,
    local_key text NOT NULL,
    "position" integer NOT NULL,
    title text,
    kind text NOT NULL,
    category text NOT NULL,
    required boolean NOT NULL,
    rerun_after_integration boolean DEFAULT false NOT NULL,
    definition jsonb NOT NULL,
    evidence_policy jsonb,
    CONSTRAINT ck_check_specs__category_valid CHECK ((category = ANY (ARRAY['acceptance'::text, 'impact'::text, 'live'::text]))),
    CONSTRAINT ck_check_specs__entity_kind_valid CHECK ((entity_kind = 'check'::text)),
    CONSTRAINT ck_check_specs__kind_valid CHECK ((kind = ANY (ARRAY['command'::text, 'shell'::text, 'manual'::text, 'external'::text]))),
    CONSTRAINT ck_check_specs__local_key_valid CHECK ((local_key ~ '^V[0-9]+$'::text)),
    CONSTRAINT ck_check_specs__owner_kind_valid CHECK ((owner_kind = ANY (ARRAY['phase'::text, 'item'::text]))),
    CONSTRAINT ck_check_specs__position_valid CHECK (("position" >= 0))
);

CREATE TABLE skm_planning.criterion_check_bindings (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    criterion_id uuid NOT NULL,
    check_id uuid NOT NULL
);

CREATE TABLE skm_planning.decision_bindings (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    decision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    binding_kind text NOT NULL,
    CONSTRAINT ck_decision_bindings__binding_kind_valid CHECK ((binding_kind = ANY (ARRAY['applies_to'::text, 'cited_by'::text])))
);

CREATE TABLE skm_planning.decision_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    decision_id uuid NOT NULL,
    entity_kind text DEFAULT 'decision'::text NOT NULL,
    "position" integer NOT NULL,
    title text NOT NULL,
    state text NOT NULL,
    source_date date,
    question text,
    options jsonb DEFAULT '[]'::jsonb NOT NULL,
    context_md text,
    decision text,
    rationale text,
    consequences jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_global boolean DEFAULT false NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    origin_kind text,
    origin_ref text,
    answered_by text,
    sections jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT ck_decision_specs__answered_by_valid CHECK ((answered_by = ANY (ARRAY['owner'::text, 'agent'::text]))),
    CONSTRAINT ck_decision_specs__entity_kind_valid CHECK ((entity_kind = 'decision'::text)),
    CONSTRAINT ck_decision_specs__fields CHECK ((((state <> 'open'::text) OR (question IS NOT NULL)) AND ((state <> ALL (ARRAY['proposed'::text, 'accepted'::text])) OR ((decision IS NOT NULL) AND (rationale IS NOT NULL))))),
    CONSTRAINT ck_decision_specs__origin_kind_valid CHECK ((origin_kind = ANY (ARRAY['owner'::text, 'agent'::text, 'advice'::text, 'panel'::text, 'import'::text]))),
    CONSTRAINT ck_decision_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_decision_specs__state_valid CHECK ((state = ANY (ARRAY['open'::text, 'proposed'::text, 'accepted'::text, 'rejected'::text, 'superseded'::text])))
);

CREATE TABLE skm_planning.decision_supersessions (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    decision_id uuid NOT NULL,
    superseded_decision_id uuid NOT NULL,
    CONSTRAINT ck_decision_supersessions__no_self CHECK ((decision_id <> superseded_decision_id))
);

CREATE TABLE skm_planning.dependency_edges (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    dependent_entity_id uuid NOT NULL,
    prerequisite_entity_id uuid NOT NULL,
    dependency_kind text NOT NULL,
    implicit boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_dependency_edges__dependency_kind_valid CHECK ((dependency_kind = ANY (ARRAY['phase_depends_on'::text, 'item_depends_on'::text, 'unit_depends_on'::text]))),
    CONSTRAINT ck_dependency_edges__implicit CHECK (((NOT implicit) OR (dependency_kind = 'phase_depends_on'::text))),
    CONSTRAINT ck_dependency_edges__no_self CHECK ((dependent_entity_id <> prerequisite_entity_id))
);

CREATE TABLE skm_planning.entity_check_bindings (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    check_id uuid NOT NULL,
    binding_role text DEFAULT 'gate'::text NOT NULL,
    CONSTRAINT ck_entity_check_bindings__binding_role_valid CHECK ((binding_role = ANY (ARRAY['gate'::text, 'advisory'::text])))
);

CREATE TABLE skm_planning.entity_path_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    role text NOT NULL,
    "position" integer NOT NULL,
    mount_name text NOT NULL,
    pattern text NOT NULL,
    change text,
    note text,
    CONSTRAINT ck_entity_path_specs__change CHECK (((role = 'change_hint'::text) = (change IS NOT NULL))),
    CONSTRAINT ck_entity_path_specs__change_valid CHECK ((change = ANY (ARRAY['create'::text, 'modify'::text, 'delete'::text, 'any'::text]))),
    CONSTRAINT ck_entity_path_specs__mount_name_valid CHECK ((mount_name ~ '^[a-z0-9][a-z0-9-]{0,62}$'::text)),
    CONSTRAINT ck_entity_path_specs__pattern_valid CHECK (((pattern !~ '^(/|~|[A-Za-z]:)'::text) AND (pattern !~ '(^|/)\.\.(/|$)'::text))),
    CONSTRAINT ck_entity_path_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_entity_path_specs__role_valid CHECK ((role = ANY (ARRAY['change_hint'::text, 'declared_write_scope'::text, 'output'::text])))
);

CREATE TABLE skm_planning.entity_read_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    purpose text NOT NULL,
    "position" integer NOT NULL,
    target_kind text NOT NULL,
    mount_name text,
    path text,
    section text,
    material_id uuid,
    material_section text,
    target_entity_id uuid,
    artifact_key text,
    external_url text,
    required boolean NOT NULL,
    why text NOT NULL,
    CONSTRAINT ck_entity_read_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_entity_read_specs__purpose_valid CHECK ((purpose = ANY (ARRAY['read'::text, 'example'::text, 'supporting'::text]))),
    CONSTRAINT ck_entity_read_specs__target CHECK ((((target_kind = 'repository_path'::text) AND (mount_name IS NOT NULL) AND (path IS NOT NULL) AND (material_id IS NULL) AND (target_entity_id IS NULL) AND (artifact_key IS NULL) AND (external_url IS NULL)) OR ((target_kind = 'material'::text) AND (material_id IS NOT NULL) AND (mount_name IS NULL) AND (path IS NULL) AND (target_entity_id IS NULL) AND (artifact_key IS NULL) AND (external_url IS NULL)) OR ((target_kind = 'plan_entity'::text) AND (target_entity_id IS NOT NULL) AND (mount_name IS NULL) AND (path IS NULL) AND (material_id IS NULL) AND (artifact_key IS NULL) AND (external_url IS NULL)) OR ((target_kind = 'artifact'::text) AND (artifact_key IS NOT NULL) AND (mount_name IS NULL) AND (path IS NULL) AND (material_id IS NULL) AND (target_entity_id IS NULL) AND (external_url IS NULL)) OR ((target_kind = 'external_source'::text) AND (external_url IS NOT NULL) AND (mount_name IS NULL) AND (path IS NULL) AND (material_id IS NULL) AND (target_entity_id IS NULL) AND (artifact_key IS NULL)))),
    CONSTRAINT ck_entity_read_specs__target_kind_valid CHECK ((target_kind = ANY (ARRAY['repository_path'::text, 'material'::text, 'plan_entity'::text, 'artifact'::text, 'external_source'::text])))
);

CREATE TABLE skm_planning.entity_relations (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    source_entity_id uuid NOT NULL,
    target_entity_id uuid NOT NULL,
    relation text NOT NULL,
    "position" integer NOT NULL,
    note text,
    CONSTRAINT ck_entity_relations__no_self CHECK ((source_entity_id <> target_entity_id)),
    CONSTRAINT ck_entity_relations__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_entity_relations__relation_valid CHECK ((relation = ANY (ARRAY['informs'::text, 'consumes'::text, 'conflicts'::text, 'follows_up'::text, 'supersedes'::text])))
);

CREATE TABLE skm_planning.entity_requirement_links (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    relation text NOT NULL,
    CONSTRAINT ck_entity_requirement_links__relation_valid CHECK ((relation = ANY (ARRAY['implements'::text, 'verifies'::text, 'owns'::text])))
);

CREATE TABLE skm_planning.entity_skill_requirements (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    resource_key text NOT NULL,
    version_constraint text,
    "position" integer NOT NULL,
    CONSTRAINT ck_entity_skill_requirements__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_entity_skill_requirements__resource_key_valid CHECK ((resource_key ~ '^[a-z][a-z0-9-]*(?:(?::|/)[a-z][a-z0-9-]*)?$'::text))
);

CREATE TABLE skm_planning.item_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    item_id uuid NOT NULL,
    entity_kind text DEFAULT 'item'::text NOT NULL,
    phase_id uuid NOT NULL,
    "position" integer NOT NULL,
    title text NOT NULL,
    summary text NOT NULL,
    why text NOT NULL,
    work_kind text DEFAULT 'code'::text NOT NULL,
    unit_strategy text DEFAULT 'dag'::text NOT NULL,
    authority_kind text DEFAULT 'routine'::text NOT NULL,
    authority_gate text,
    authority_label text,
    authority_scope text,
    research_need text DEFAULT 'none'::text NOT NULL,
    research_question text,
    route jsonb,
    scope jsonb,
    rules jsonb DEFAULT '[]'::jsonb NOT NULL,
    guidance_md text,
    deliverables jsonb DEFAULT '[]'::jsonb NOT NULL,
    sections jsonb DEFAULT '[]'::jsonb NOT NULL,
    work_policy jsonb,
    CONSTRAINT ck_item_specs__authority_gate_valid CHECK ((authority_gate ~ '^[A-Z0-9][A-Z0-9._-]*$'::text)),
    CONSTRAINT ck_item_specs__authority_kind_valid CHECK ((authority_kind = ANY (ARRAY['routine'::text, 'owner_gate'::text, 'external_gate'::text]))),
    CONSTRAINT ck_item_specs__entity_kind_valid CHECK ((entity_kind = 'item'::text)),
    CONSTRAINT ck_item_specs__gate CHECK ((((authority_kind = 'routine'::text) AND (authority_gate IS NULL) AND (authority_label IS NULL) AND (authority_scope IS NULL)) OR ((authority_kind <> 'routine'::text) AND (authority_scope IS NOT NULL) AND ((authority_gate IS NULL) <> (authority_label IS NULL))))),
    CONSTRAINT ck_item_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_item_specs__research_need_valid CHECK ((research_need = ANY (ARRAY['none'::text, 'optional'::text, 'required'::text]))),
    CONSTRAINT ck_item_specs__unit_strategy_valid CHECK ((unit_strategy = ANY (ARRAY['dag'::text, 'sequential'::text]))),
    CONSTRAINT ck_item_specs__work_kind_valid CHECK ((work_kind = ANY (ARRAY['code'::text, 'docs'::text, 'research'::text, 'config'::text, 'test'::text, 'review'::text, 'ops'::text]))),
    CONSTRAINT ck_item_specs__work_policy CHECK (((work_policy IS NULL) OR ((jsonb_typeof(work_policy) = 'object'::text) AND (octet_length((work_policy)::text) <= 4096))))
);

CREATE TABLE skm_planning.material_bindings (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    material_id uuid NOT NULL,
    entity_id uuid NOT NULL
);

CREATE TABLE skm_planning.material_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    material_id uuid NOT NULL,
    entity_kind text DEFAULT 'material'::text NOT NULL,
    "position" integer NOT NULL,
    title text NOT NULL,
    kind text NOT NULL,
    role text NOT NULL,
    required_for text[] DEFAULT '{}'::text[] NOT NULL,
    freshness_policy text DEFAULT 'pinned'::text NOT NULL,
    freshness_max_age_s integer,
    why text,
    is_global boolean DEFAULT false NOT NULL,
    mount_name text,
    path text,
    external_url text,
    retrieved_at timestamp with time zone,
    content_digest text,
    selector jsonb,
    CONSTRAINT ck_material_specs__content_digest_valid CHECK ((content_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_material_specs__entity_kind_valid CHECK ((entity_kind = 'material'::text)),
    CONSTRAINT ck_material_specs__freshness_kind CHECK (((kind = 'file_version'::text) OR ((kind = 'repository_path'::text) AND (freshness_policy = 'pinned'::text)) OR ((kind = 'external_source'::text) AND (freshness_policy = ANY (ARRAY['pinned'::text, 'must_refresh'::text]))))),
    CONSTRAINT ck_material_specs__freshness_max_age_s_valid CHECK (((freshness_max_age_s >= 60) AND (freshness_max_age_s <= 31536000))),
    CONSTRAINT ck_material_specs__freshness_policy_valid CHECK ((freshness_policy = ANY (ARRAY['pinned'::text, 'latest_at_publish'::text, 'must_refresh'::text]))),
    CONSTRAINT ck_material_specs__kind_valid CHECK ((kind = ANY (ARRAY['file_version'::text, 'repository_path'::text, 'external_source'::text]))),
    CONSTRAINT ck_material_specs__max_age CHECK (((freshness_policy = 'must_refresh'::text) = (freshness_max_age_s IS NOT NULL))),
    CONSTRAINT ck_material_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_material_specs__required_for CHECK ((required_for <@ ARRAY['execution'::text, 'review'::text, 'acceptance'::text])),
    CONSTRAINT ck_material_specs__role_valid CHECK ((role = ANY (ARRAY['input'::text, 'reference'::text]))),
    CONSTRAINT ck_material_specs__target CHECK ((((kind = 'file_version'::text) AND (mount_name IS NULL) AND (path IS NULL) AND (external_url IS NULL)) OR ((kind = 'repository_path'::text) AND (mount_name IS NOT NULL) AND (path IS NOT NULL) AND (external_url IS NULL)) OR ((kind = 'external_source'::text) AND (mount_name IS NULL) AND (path IS NULL) AND (external_url IS NOT NULL))))
);

CREATE TABLE skm_planning.phase_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    phase_id uuid NOT NULL,
    entity_kind text DEFAULT 'phase'::text NOT NULL,
    "position" integer NOT NULL,
    title text NOT NULL,
    goal text NOT NULL,
    context_md text,
    design_state text NOT NULL,
    strategy text DEFAULT 'dag'::text NOT NULL,
    depends_on_declared boolean NOT NULL,
    contract jsonb DEFAULT '{}'::jsonb NOT NULL,
    scope jsonb,
    pitfalls jsonb DEFAULT '[]'::jsonb NOT NULL,
    deliverables jsonb DEFAULT '[]'::jsonb NOT NULL,
    assurance jsonb,
    sections jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT ck_phase_specs__design_state_valid CHECK ((design_state = ANY (ARRAY['skeleton'::text, 'detailed'::text]))),
    CONSTRAINT ck_phase_specs__entity_kind_valid CHECK ((entity_kind = 'phase'::text)),
    CONSTRAINT ck_phase_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_phase_specs__strategy_valid CHECK ((strategy = ANY (ARRAY['dag'::text, 'sequential'::text])))
);

CREATE TABLE skm_planning.plan_aliases (
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    alias text NOT NULL,
    alias_kind text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_plan_aliases__alias CHECK (((length(alias) >= 1) AND (length(alias) <= 200))),
    CONSTRAINT ck_plan_aliases__alias_kind CHECK ((alias_kind = ANY (ARRAY['short'::text, 'system'::text, 'legacy'::text, 'external'::text]))),
    CONSTRAINT ck_plan_aliases__short CHECK (((alias_kind <> 'short'::text) OR ((alias ~ '^[A-Z]{2,8}[1-9][0-9]*$'::text) AND (alias !~ '^AC[0-9]'::text)))),
    CONSTRAINT ck_plan_aliases__system CHECK (((alias_kind <> 'system'::text) OR (alias = 'review-requests'::text)))
);

CREATE TABLE skm_planning.plan_design_brief_rag_bindings (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    design_brief_id uuid NOT NULL,
    file_version_id uuid NOT NULL
);

CREATE TABLE skm_planning.plan_design_brief_research_references (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    design_brief_id uuid NOT NULL,
    reference text NOT NULL,
    content_digest text NOT NULL,
    CONSTRAINT ck_design_brief_research__digest CHECK ((content_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_design_brief_research__reference CHECK ((((char_length(reference) >= 1) AND (char_length(reference) <= 1000)) AND (btrim(reference) <> ''::text)))
);

CREATE TABLE skm_planning.plan_design_briefs (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    goal text NOT NULL,
    context_md text,
    constraints text[] DEFAULT '{}'::text[] NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_plan_design_briefs__goal CHECK ((((char_length(goal) >= 1) AND (char_length(goal) <= 20000)) AND (btrim(goal) <> ''::text)))
);

CREATE TABLE skm_planning.plan_drafts (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    id uuid NOT NULL,
    base_revision_id uuid,
    edit_version bigint DEFAULT 1 NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    document jsonb NOT NULL,
    state text DEFAULT 'open'::text NOT NULL,
    published_revision_id uuid,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_by uuid NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    CONSTRAINT ck_plan_drafts__closed CHECK (((state = 'open'::text) = (closed_at IS NULL))),
    CONSTRAINT ck_plan_drafts__edit_version_valid CHECK ((edit_version >= 1)),
    CONSTRAINT ck_plan_drafts__published CHECK (((state = 'published'::text) = (published_revision_id IS NOT NULL))),
    CONSTRAINT ck_plan_drafts__size CHECK ((octet_length((document)::text) <= 16777216)),
    CONSTRAINT ck_plan_drafts__state CHECK ((state = ANY (ARRAY['open'::text, 'published'::text, 'abandoned'::text])))
);

CREATE TABLE skm_planning.plan_entity_identities (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    entity_kind text NOT NULL,
    first_revision_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_plan_entity_identities__entity_kind CHECK ((entity_kind = ANY (ARRAY['phase'::text, 'item'::text, 'unit'::text, 'requirement'::text, 'criterion'::text, 'check'::text, 'decision'::text, 'material'::text])))
);

CREATE TABLE skm_planning.plan_relations (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    "position" integer NOT NULL,
    kind text NOT NULL,
    target_plan_id uuid,
    target_ref text NOT NULL,
    note text,
    CONSTRAINT ck_plan_relations__kind_valid CHECK ((kind = ANY (ARRAY['predecessor'::text, 'supersedes'::text, 'related'::text]))),
    CONSTRAINT ck_plan_relations__no_self CHECK (((target_plan_id IS NULL) OR (target_plan_id <> plan_id))),
    CONSTRAINT ck_plan_relations__position_valid CHECK (("position" >= 0))
);

CREATE TABLE skm_planning.plan_revisions (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    id uuid NOT NULL,
    revision_no integer NOT NULL,
    parent_revision_id uuid,
    schema_version integer NOT NULL,
    content_digest text NOT NULL,
    canonicalization_version integer DEFAULT 1 NOT NULL,
    compiler_version integer DEFAULT 1 NOT NULL,
    published_by uuid NOT NULL,
    published_at timestamp with time zone NOT NULL,
    change_reason text NOT NULL,
    origin text DEFAULT 'draft'::text NOT NULL,
    restored_from_revision_id uuid,
    CONSTRAINT ck_plan_revisions__change_reason_valid CHECK (((length(change_reason) >= 1) AND (length(change_reason) <= 2000))),
    CONSTRAINT ck_plan_revisions__content_digest_valid CHECK ((content_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_plan_revisions__origin CHECK ((origin = ANY (ARRAY['draft'::text, 'restore'::text, 'import'::text, 'system'::text]))),
    CONSTRAINT ck_plan_revisions__parent CHECK (((revision_no = 1) = (parent_revision_id IS NULL))),
    CONSTRAINT ck_plan_revisions__restored_from CHECK ((((origin = 'restore'::text) = (restored_from_revision_id IS NOT NULL)) AND ((restored_from_revision_id IS NULL) OR ((restored_from_revision_id <> id) AND (parent_revision_id IS NOT NULL))))),
    CONSTRAINT ck_plan_revisions__revision_no_valid CHECK ((revision_no >= 1)),
    CONSTRAINT ck_plan_revisions__schema_version_valid CHECK ((schema_version >= 1))
);

CREATE TABLE skm_planning.plans (
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    title text NOT NULL,
    lifecycle_state text DEFAULT 'active'::text NOT NULL,
    purpose text DEFAULT 'standard'::text NOT NULL,
    current_revision_id uuid,
    next_revision_no integer DEFAULT 1 NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    archived_at timestamp with time zone,
    CONSTRAINT ck_plans__archived_at CHECK (((lifecycle_state = 'archived'::text) = (archived_at IS NOT NULL))),
    CONSTRAINT ck_plans__lifecycle_state CHECK ((lifecycle_state = ANY (ARRAY['active'::text, 'archived'::text]))),
    CONSTRAINT ck_plans__next_revision_no CHECK ((next_revision_no >= 1)),
    CONSTRAINT ck_plans__purpose CHECK ((purpose = ANY (ARRAY['standard'::text, 'review_requests'::text]))),
    CONSTRAINT ck_plans__title_valid CHECK (((length(title) >= 1) AND (length(title) <= 300)))
);

CREATE TABLE skm_planning.project_plan_counters (
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    next_plan_no integer DEFAULT 1 NOT NULL,
    CONSTRAINT ck_project_plan_counters__next_plan_no_valid CHECK ((next_plan_no >= 1))
);

CREATE TABLE skm_planning.requirement_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    entity_kind text DEFAULT 'requirement'::text NOT NULL,
    "position" integer NOT NULL,
    statement text NOT NULL,
    priority text NOT NULL,
    source_kind text NOT NULL,
    source_ref text,
    CONSTRAINT ck_requirement_specs__entity_kind_valid CHECK ((entity_kind = 'requirement'::text)),
    CONSTRAINT ck_requirement_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_requirement_specs__priority_valid CHECK ((priority = ANY (ARRAY['must'::text, 'should'::text, 'could'::text]))),
    CONSTRAINT ck_requirement_specs__source_kind_valid CHECK ((source_kind = ANY (ARRAY['brief_message'::text, 'owner'::text, 'derived'::text, 'external'::text])))
);

CREATE TABLE skm_planning.review_requirements (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    owner_entity_id uuid NOT NULL,
    owner_kind text DEFAULT 'item'::text NOT NULL,
    mode text NOT NULL,
    profile_key text,
    independence text,
    reviewer jsonb,
    max_rounds integer,
    covers jsonb DEFAULT '[]'::jsonb NOT NULL,
    required_evidence text[] DEFAULT '{}'::text[] NOT NULL,
    reason text,
    waived_by text,
    CONSTRAINT ck_review_requirements__independence_valid CHECK ((independence = ANY (ARRAY['separate_session'::text, 'separate_runtime'::text, 'human'::text]))),
    CONSTRAINT ck_review_requirements__max_rounds_valid CHECK (((max_rounds >= 1) AND (max_rounds <= 10))),
    CONSTRAINT ck_review_requirements__mode CHECK ((((mode = 'required'::text) AND (reason IS NULL) AND (waived_by IS NULL)) OR ((mode = 'self'::text) AND (reason IS NOT NULL) AND (waived_by IS NULL)) OR ((mode = 'waived'::text) AND (reason IS NOT NULL) AND (waived_by IS NOT NULL)))),
    CONSTRAINT ck_review_requirements__mode_valid CHECK ((mode = ANY (ARRAY['required'::text, 'self'::text, 'waived'::text]))),
    CONSTRAINT ck_review_requirements__owner_kind_valid CHECK ((owner_kind = 'item'::text))
);

CREATE TABLE skm_planning.revision_file_bindings (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    material_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    role text NOT NULL,
    selector jsonb,
    CONSTRAINT ck_revision_file_bindings__role_valid CHECK ((role = ANY (ARRAY['input'::text, 'reference'::text])))
);

CREATE TABLE skm_planning.revision_members (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    entity_kind text NOT NULL,
    display_key text NOT NULL,
    "position" integer NOT NULL,
    CONSTRAINT ck_revision_members__display_key_valid CHECK (((length(display_key) >= 1) AND (length(display_key) <= 200))),
    CONSTRAINT ck_revision_members__entity_kind CHECK ((entity_kind = ANY (ARRAY['phase'::text, 'item'::text, 'unit'::text, 'requirement'::text, 'criterion'::text, 'check'::text, 'decision'::text, 'material'::text]))),
    CONSTRAINT ck_revision_members__position_valid CHECK (("position" >= 0))
);

CREATE TABLE skm_planning.revision_payloads (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    document jsonb NOT NULL,
    document_digest text NOT NULL,
    CONSTRAINT ck_revision_payloads__document_digest_valid CHECK ((document_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_revision_payloads__size CHECK ((octet_length((document)::text) <= 16777216))
);

CREATE TABLE skm_planning.revision_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    title text NOT NULL,
    goal text NOT NULL,
    context_md text,
    non_goals jsonb DEFAULT '[]'::jsonb NOT NULL,
    rules jsonb DEFAULT '[]'::jsonb NOT NULL,
    design_brief_id uuid,
    brief jsonb,
    execution_constraints jsonb DEFAULT '{}'::jsonb NOT NULL,
    sections jsonb DEFAULT '[]'::jsonb NOT NULL,
    extensions jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_revision_specs__arrays CHECK (((jsonb_typeof(non_goals) = 'array'::text) AND (jsonb_typeof(rules) = 'array'::text) AND (jsonb_typeof(sections) = 'array'::text) AND (jsonb_typeof(extensions) = 'object'::text) AND (jsonb_typeof(execution_constraints) = 'object'::text)))
);

CREATE TABLE skm_planning.unit_specs (
    workspace_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    unit_id uuid NOT NULL,
    entity_kind text DEFAULT 'unit'::text NOT NULL,
    item_id uuid NOT NULL,
    parent_unit_id uuid,
    "position" integer NOT NULL,
    local_key text NOT NULL,
    title text NOT NULL,
    goal text NOT NULL,
    unit_kind text DEFAULT 'implementation'::text NOT NULL,
    work_kind text,
    mode text DEFAULT 'either'::text NOT NULL,
    route jsonb,
    instructions_md text,
    command jsonb,
    sections jsonb DEFAULT '[]'::jsonb NOT NULL,
    work_policy jsonb,
    CONSTRAINT ck_unit_specs__command CHECK (((unit_kind = 'command'::text) = (command IS NOT NULL))),
    CONSTRAINT ck_unit_specs__entity_kind_valid CHECK ((entity_kind = 'unit'::text)),
    CONSTRAINT ck_unit_specs__invariant_valid CHECK ((unit_kind = ANY (ARRAY['preparation'::text, 'implementation'::text, 'review'::text, 'verification'::text, 'integration'::text, 'command'::text]))),
    CONSTRAINT ck_unit_specs__local_key_valid CHECK ((local_key ~ '^U[0-9]+$'::text)),
    CONSTRAINT ck_unit_specs__mode_valid CHECK ((mode = ANY (ARRAY['self'::text, 'delegate'::text, 'either'::text]))),
    CONSTRAINT ck_unit_specs__no_self_parent CHECK (((parent_unit_id IS NULL) OR (parent_unit_id <> unit_id))),
    CONSTRAINT ck_unit_specs__position_valid CHECK (("position" >= 0)),
    CONSTRAINT ck_unit_specs__work_kind_valid CHECK ((work_kind = ANY (ARRAY['code'::text, 'docs'::text, 'research'::text, 'config'::text, 'test'::text, 'review'::text, 'ops'::text]))),
    CONSTRAINT ck_unit_specs__work_policy CHECK (((work_policy IS NULL) OR ((jsonb_typeof(work_policy) = 'object'::text) AND (octet_length((work_policy)::text) <= 4096))))
);

CREATE TABLE skm_policy.approvals (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    intent_id uuid NOT NULL,
    approver_id uuid NOT NULL,
    decision text NOT NULL,
    args_digest text NOT NULL,
    single_use boolean DEFAULT true NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    CONSTRAINT ck_approvals__args_digest CHECK ((args_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_approvals__decision CHECK ((decision = ANY (ARRAY['approve'::text, 'deny'::text]))),
    CONSTRAINT ck_approvals__expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_approvals__reason CHECK ((char_length(reason) <= 1000)),
    CONSTRAINT ck_approvals__used CHECK (((used_at IS NULL) OR ((decision = 'approve'::text) AND (used_at >= created_at))))
);

CREATE TABLE skm_policy.decision_audit (
    id uuid NOT NULL,
    workspace_id uuid,
    scope_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    source text NOT NULL,
    at timestamp with time zone NOT NULL,
    tool text NOT NULL,
    call_summary text NOT NULL,
    outcome text NOT NULL,
    code text,
    rule text,
    operation text,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_decision_audit__call_summary CHECK ((char_length(call_summary) <= 500)),
    CONSTRAINT ck_decision_audit__code CHECK (((code IS NULL) OR (code = ANY (ARRAY['tool_not_allowed'::text, 'path_protected'::text, 'path_outside_scope'::text, 'path_denied'::text, 'commands_disabled'::text, 'command_denied'::text, 'rm_outside_write_scope'::text, 'operation_denied'::text, 'requires_intent'::text, 'requires_task_authority'::text, 'capability_not_granted'::text, 'network_denied'::text, 'approval_unavailable_unattended'::text])))),
    CONSTRAINT ck_decision_audit__deny_code CHECK (((outcome = 'deny'::text) = (code IS NOT NULL))),
    CONSTRAINT ck_decision_audit__operation CHECK (((operation IS NULL) OR (operation = ANY (ARRAY['modify_write_set'::text, 'modify_outside_write_set'::text, 'delete_tracked'::text, 'delete_own_untracked'::text, 'delete_foreign_untracked'::text, 'modify_git_dir'::text, 'git_discard'::text, 'git_push'::text, 'git_force_push'::text, 'forge_write'::text, 'release_publish'::text, 'secrets_access'::text, 'docker_socket'::text, 'external_services'::text])))),
    CONSTRAINT ck_decision_audit__outcome CHECK ((outcome = ANY (ARRAY['allow'::text, 'ask'::text, 'deny'::text, 'warn'::text]))),
    CONSTRAINT ck_decision_audit__source CHECK ((source = ANY (ARRAY['hook'::text, 'worker'::text]))),
    CONSTRAINT ck_decision_audit__tool CHECK (((char_length(tool) >= 1) AND (char_length(tool) <= 200)))
);

CREATE TABLE skm_policy.tool_intents (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    scope_id uuid NOT NULL,
    subject_ref text NOT NULL,
    actor_id uuid NOT NULL,
    kind text NOT NULL,
    normalized_args jsonb NOT NULL,
    args_digest text NOT NULL,
    risk text NOT NULL,
    reason text NOT NULL,
    state text DEFAULT 'proposed'::text NOT NULL,
    denied_reason text,
    receipt jsonb,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_tool_intents__args_digest CHECK ((args_digest ~ '^sha256:[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_tool_intents__denied_reason CHECK ((((state = 'denied'::text) = (denied_reason IS NOT NULL)) AND ((denied_reason IS NULL) OR (denied_reason = ANY (ARRAY['not_permitted'::text, 'forbidden_args'::text, 'by_approver'::text, 'revoked'::text]))))),
    CONSTRAINT ck_tool_intents__expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_tool_intents__kind CHECK ((kind = ANY (ARRAY['git_commit'::text, 'git_push'::text, 'pr_create'::text, 'message'::text, 'publish'::text, 'fs_write_external'::text]))),
    CONSTRAINT ck_tool_intents__normalized_args CHECK ((jsonb_typeof(normalized_args) = 'object'::text)),
    CONSTRAINT ck_tool_intents__reason CHECK (((char_length(reason) >= 1) AND (char_length(reason) <= 1000))),
    CONSTRAINT ck_tool_intents__receipt CHECK (((receipt IS NULL) OR ((jsonb_typeof(receipt) = 'object'::text) AND (octet_length((receipt)::text) <= 16384)))),
    CONSTRAINT ck_tool_intents__risk CHECK ((risk = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text, 'critical'::text]))),
    CONSTRAINT ck_tool_intents__row_version CHECK ((row_version >= 1)),
    CONSTRAINT ck_tool_intents__state CHECK ((state = ANY (ARRAY['proposed'::text, 'approved'::text, 'denied'::text, 'expired'::text, 'executing'::text, 'succeeded'::text, 'failed'::text, 'outcome_unknown'::text]))),
    CONSTRAINT ck_tool_intents__subject_ref CHECK (((char_length(subject_ref) >= 1) AND (char_length(subject_ref) <= 200)))
);

CREATE TABLE skm_runtimes.canonical_models (
    model_id text NOT NULL,
    CONSTRAINT ck_canonical_models__model_id CHECK ((model_id <> ''::text))
);

CREATE TABLE skm_runtimes.capability_verifications (
    id uuid NOT NULL,
    runtime_id text NOT NULL,
    runtime_version text,
    verification_context jsonb,
    verification_key text,
    capability text NOT NULL,
    status text NOT NULL,
    evidence text NOT NULL,
    limitations text DEFAULT ''::text NOT NULL,
    verified_at date NOT NULL,
    recorded_by uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_capability_verifications__capability CHECK ((capability = ANY (ARRAY['headless_execution'::text, 'structured_result'::text, 'stream_events'::text, 'session_resume'::text, 'tool_interception'::text, 'reliable_cancellation'::text, 'usage_reporting'::text, 'workspace_binding'::text, 'native_subagents'::text, 'mcp_support'::text, 'permission_flags'::text, 'sandbox_native'::text, 'effort_control'::text, 'model_selection'::text, 'config_isolation'::text]))),
    CONSTRAINT ck_capability_verifications__context CHECK ((((verification_context IS NULL) AND (verification_key IS NULL)) OR ((verification_context IS NOT NULL) AND (verification_key IS NOT NULL) AND (jsonb_typeof(verification_context) = 'object'::text) AND (verification_key ~ '^sha256:[a-f0-9]{64}$'::text)))),
    CONSTRAINT ck_capability_verifications__evidence CHECK (((char_length(evidence) >= 1) AND (char_length(evidence) <= 500))),
    CONSTRAINT ck_capability_verifications__limitations CHECK ((char_length(limitations) <= 2000)),
    CONSTRAINT ck_capability_verifications__runtime_id CHECK ((runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'::text)),
    CONSTRAINT ck_capability_verifications__status CHECK ((status = ANY (ARRAY['native'::text, 'adapted'::text, 'unsupported'::text, 'unknown'::text])))
);

CREATE TABLE skm_runtimes.worker_model_offer_snapshots (
    worker_id uuid NOT NULL,
    publisher_token_id uuid NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    snapshot jsonb NOT NULL,
    CONSTRAINT pk_worker_model_offer_snapshots PRIMARY KEY (worker_id),
    CONSTRAINT ck_worker_model_offer_snapshots__expires_at CHECK (expires_at > observed_at),
    CONSTRAINT ck_worker_model_offer_snapshots__snapshot CHECK (jsonb_typeof(snapshot) = 'object')
);

CREATE TABLE skm_runtimes.host_model_availability (
    host_id uuid NOT NULL,
    runtime_id text NOT NULL,
    model_id text NOT NULL,
    effort text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_host_model_availability__effort CHECK ((effort = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text, 'xhigh'::text]))),
    CONSTRAINT ck_host_model_availability__expires_at CHECK ((expires_at > observed_at))
);

CREATE TABLE skm_runtimes.host_runtimes (
    host_id uuid NOT NULL,
    runtime_id text NOT NULL,
    version text,
    binary_locator text,
    auth_state text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    detected_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_host_runtimes__auth_state CHECK ((auth_state = ANY (ARRAY['ok'::text, 'missing'::text, 'expired'::text, 'unknown'::text]))),
    CONSTRAINT ck_host_runtimes__binary_locator CHECK (((binary_locator IS NULL) OR ((char_length(binary_locator) >= 1) AND (char_length(binary_locator) <= 4096)))),
    CONSTRAINT ck_host_runtimes__details CHECK ((jsonb_typeof(details) = 'object'::text)),
    CONSTRAINT ck_host_runtimes__runtime_id CHECK ((runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'::text)),
    CONSTRAINT ck_host_runtimes__version CHECK (((version IS NULL) OR ((char_length(version) >= 1) AND (char_length(version) <= 100))))
);

CREATE TABLE skm_runtimes.model_guidelines (
    resource_version_id uuid NOT NULL,
    runtime_id text NOT NULL,
    model_id text NOT NULL,
    classes text[] NOT NULL,
    suited_roles text[] NOT NULL,
    notes text NOT NULL
);

CREATE TABLE skm_runtimes.provider_model_offerings (
    runtime_id text NOT NULL,
    model_id text NOT NULL,
    provider_model_id text NOT NULL,
    display_name text NOT NULL,
    context_window_tokens bigint NOT NULL,
    max_output_tokens bigint,
    patterns text[] NOT NULL,
    status text NOT NULL,
    verified_at date NOT NULL,
    source text NOT NULL,
    input_per_mtok_usd numeric,
    output_per_mtok_usd numeric,
    cache_read_per_mtok_usd numeric,
    cache_write_per_mtok_usd numeric,
    price_verified_at date,
    price_source text,
    CONSTRAINT ck_provider_model_offerings__pricing CHECK ((((input_per_mtok_usd IS NULL) AND (output_per_mtok_usd IS NULL) AND (cache_read_per_mtok_usd IS NULL) AND (cache_write_per_mtok_usd IS NULL) AND (price_verified_at IS NULL) AND (price_source IS NULL)) OR ((input_per_mtok_usd IS NOT NULL) AND (output_per_mtok_usd IS NOT NULL) AND (price_verified_at IS NOT NULL) AND (price_source IS NOT NULL) AND (input_per_mtok_usd >= (0)::numeric) AND (input_per_mtok_usd < 'Infinity'::numeric) AND (output_per_mtok_usd >= (0)::numeric) AND (output_per_mtok_usd < 'Infinity'::numeric) AND ((cache_read_per_mtok_usd IS NULL) OR ((cache_read_per_mtok_usd >= (0)::numeric) AND (cache_read_per_mtok_usd < 'Infinity'::numeric))) AND ((cache_write_per_mtok_usd IS NULL) OR ((cache_write_per_mtok_usd >= (0)::numeric) AND (cache_write_per_mtok_usd < 'Infinity'::numeric)))))),
    CONSTRAINT ck_provider_model_offerings__runtime_id CHECK ((runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'::text)),
    CONSTRAINT ck_provider_model_offerings__selector CHECK ((provider_model_id <> ''::text)),
    CONSTRAINT ck_provider_model_offerings__status CHECK ((status = ANY (ARRAY['confirmed'::text, 'unverified'::text, 'deprecated'::text]))),
    CONSTRAINT ck_provider_model_offerings__tokens CHECK (((context_window_tokens >= 1000) AND (max_output_tokens >= 0)))
);

CREATE TABLE skm_workspace.checkout_bindings (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    host_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    local_locator text NOT NULL,
    state text NOT NULL,
    observed_remotes text[] DEFAULT '{}'::text[] NOT NULL,
    observed_head text,
    last_verified_at timestamp with time zone NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_checkout_bindings__head CHECK (((observed_head IS NULL) OR (observed_head ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'::text))),
    CONSTRAINT ck_checkout_bindings__locator CHECK ((((char_length(local_locator) >= 1) AND (char_length(local_locator) <= 4096)) AND ((local_locator ~ '^/'::text) OR (local_locator ~ '^[A-Za-z]:\\'::text)) AND (POSITION(('
'::text) IN (local_locator)) = 0))),
    CONSTRAINT ck_checkout_bindings__state CHECK ((state = ANY (ARRAY['active'::text, 'missing'::text, 'mismatched'::text, 'removed'::text])))
);

CREATE TABLE skm_workspace.hosts (
    id uuid NOT NULL,
    name text NOT NULL,
    os text NOT NULL,
    arch text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    registered_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone,
    CONSTRAINT ck_hosts__arch CHECK ((arch = ANY (ARRAY['x86_64'::text, 'arm64'::text, 'other'::text]))),
    CONSTRAINT ck_hosts__name CHECK ((name ~ '^[a-z0-9][a-z0-9.-]{0,62}$'::text)),
    CONSTRAINT ck_hosts__os CHECK ((os = ANY (ARRAY['linux'::text, 'macos'::text, 'windows'::text]))),
    CONSTRAINT ck_hosts__state CHECK ((state = ANY (ARRAY['active'::text, 'retired'::text])))
);

CREATE TABLE skm_workspace.project_repositories (
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    mount_name text NOT NULL,
    role text NOT NULL,
    attached_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_project_repositories__mount_name CHECK ((mount_name ~ '^[a-z0-9][a-z0-9_-]{0,31}$'::text)),
    CONSTRAINT ck_project_repositories__role CHECK ((role = ANY (ARRAY['primary'::text, 'secondary'::text, 'docs'::text, 'infra'::text])))
);

CREATE TABLE skm_workspace.projects (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    slug text NOT NULL,
    title text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_projects__description CHECK ((char_length(description) <= 4000)),
    CONSTRAINT ck_projects__slug CHECK ((slug ~ '^[a-z0-9]([a-z0-9]|-(?=[a-z0-9])){1,62}$'::text)),
    CONSTRAINT ck_projects__state CHECK ((state = ANY (ARRAY['active'::text, 'archived'::text]))),
    CONSTRAINT ck_projects__title CHECK (((char_length(title) >= 1) AND (char_length(title) <= 200)))
);

CREATE TABLE skm_workspace.repositories (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    title text NOT NULL,
    canonical_remote text,
    provider text NOT NULL,
    external_id text,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_repositories__provider CHECK ((provider = ANY (ARRAY['github'::text, 'gitlab'::text, 'bitbucket'::text, 'gitea'::text, 'other'::text, 'none'::text]))),
    CONSTRAINT ck_repositories__provider_none CHECK (((canonical_remote IS NULL) = (provider = 'none'::text))),
    CONSTRAINT ck_repositories__title CHECK (((char_length(title) >= 1) AND (char_length(title) <= 200)))
);

CREATE TABLE skm_workspace.repository_remotes (
    workspace_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    normalized_url text NOT NULL,
    display_url text NOT NULL,
    is_primary boolean DEFAULT false NOT NULL,
    added_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_repository_remotes__normalized CHECK ((normalized_url ~ '^[^/\s]+/[^\s]+$'::text))
);

CREATE TABLE skm_workspace.workers (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    host_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    display_name text NOT NULL,
    capabilities jsonb NOT NULL,
    state text DEFAULT 'offline'::text NOT NULL,
    last_heartbeat_at timestamp with time zone,
    registered_at timestamp with time zone NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_workers__capabilities_size CHECK ((octet_length((capabilities)::text) < 16384)),
    CONSTRAINT ck_workers__display_name CHECK (((char_length(display_name) >= 1) AND (char_length(display_name) <= 100))),
    CONSTRAINT ck_workers__state CHECK ((state = ANY (ARRAY['online'::text, 'draining'::text, 'offline'::text, 'retired'::text])))
);

CREATE TABLE skm_workspace.workspaces (
    id uuid NOT NULL,
    slug text NOT NULL,
    title text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_workspaces__slug CHECK ((slug ~ '^[a-z0-9]([a-z0-9]|-(?=[a-z0-9])){1,62}$'::text)),
    CONSTRAINT ck_workspaces__state CHECK ((state = ANY (ARRAY['active'::text, 'suspended'::text, 'archived'::text]))),
    CONSTRAINT ck_workspaces__title CHECK (((char_length(title) >= 1) AND (char_length(title) <= 200)))
);

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT api_tokens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_secret_hash_key UNIQUE (secret_hash);

ALTER TABLE ONLY skm_access.memberships
    ADD CONSTRAINT pk_memberships PRIMARY KEY (scope_id, principal_id);

ALTER TABLE ONLY skm_access.principal_identities
    ADD CONSTRAINT pk_principal_identities PRIMARY KEY (issuer, subject);

ALTER TABLE ONLY skm_access.principals
    ADD CONSTRAINT principals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT uq_api_tokens__prefix UNIQUE (prefix);

ALTER TABLE ONLY skm_access.web_sessions
    ADD CONSTRAINT web_sessions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_access.web_sessions
    ADD CONSTRAINT web_sessions_secret_hash_key UNIQUE (secret_hash);

ALTER TABLE ONLY skm_artifacts.access_grants
    ADD CONSTRAINT access_grants_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_artifacts.blobs
    ADD CONSTRAINT blobs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT file_versions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_artifacts.files
    ADD CONSTRAINT files_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_artifacts.blob_locations
    ADD CONSTRAINT pk_blob_locations PRIMARY KEY (blob_id, backend_id);

ALTER TABLE ONLY skm_artifacts.staged_blobs
    ADD CONSTRAINT staged_blobs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_artifacts.storage_backends
    ADD CONSTRAINT storage_backends_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_artifacts.blob_locations
    ADD CONSTRAINT uq_blob_locations__backend_id_storage_key UNIQUE (backend_id, storage_key);

ALTER TABLE ONLY skm_artifacts.blobs
    ADD CONSTRAINT uq_blobs__workspace_id_digest UNIQUE (workspace_id, hash_algorithm, content_digest, size_bytes);

ALTER TABLE ONLY skm_artifacts.blobs
    ADD CONSTRAINT uq_blobs__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT uq_file_versions__file_id_version_no UNIQUE (file_id, version_no);

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT uq_file_versions__workspace_id_file_id_id UNIQUE (workspace_id, file_id, id);

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT uq_file_versions__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_artifacts.files
    ADD CONSTRAINT uq_files__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_config.entries
    ADD CONSTRAINT entries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_config.entry_history
    ADD CONSTRAINT entry_history_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_config.generation
    ADD CONSTRAINT generation_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_config.entries
    ADD CONSTRAINT uq_entries__scope_id_key UNIQUE (scope_id, key);

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT context_manifests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_context.external_sources
    ADD CONSTRAINT external_sources_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_context.context_blocks
    ADD CONSTRAINT pk_context_blocks PRIMARY KEY (manifest_id, ordinal);

ALTER TABLE ONLY skm_context.research_queries
    ADD CONSTRAINT research_queries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_context.texts
    ADD CONSTRAINT texts_pkey PRIMARY KEY (digest);

ALTER TABLE ONLY skm_context.context_blocks
    ADD CONSTRAINT uq_context_blocks__manifest_id_block_ref UNIQUE (manifest_id, block_ref);

ALTER TABLE ONLY skm_context.context_blocks
    ADD CONSTRAINT uq_context_blocks__manifest_id_position UNIQUE (manifest_id, "position");

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT uq_context_manifests__step_ref UNIQUE (step_ref);

ALTER TABLE ONLY skm_context.external_sources
    ADD CONSTRAINT uq_external_sources__query_id_ordinal UNIQUE (query_id, ordinal);

ALTER TABLE ONLY skm_context.research_queries
    ADD CONSTRAINT uq_research_queries__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_core.audit_records
    ADD CONSTRAINT audit_records_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_core.domain_events
    ADD CONSTRAINT domain_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_core.idempotency_receipts
    ADD CONSTRAINT idempotency_receipts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_core.outbox
    ADD CONSTRAINT outbox_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_core.consumer_receipts
    ADD CONSTRAINT pk_consumer_receipts PRIMARY KEY (consumer_id, event_id);

ALTER TABLE ONLY skm_core.event_streams
    ADD CONSTRAINT pk_event_streams PRIMARY KEY (stream_kind, stream_id);

ALTER TABLE ONLY skm_core.scopes
    ADD CONSTRAINT scopes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_core.domain_events
    ADD CONSTRAINT uq_domain_events__stream UNIQUE (stream_kind, stream_id, stream_seq);

ALTER TABLE ONLY skm_core.domain_events
    ADD CONSTRAINT uq_domain_events__workspace_seq UNIQUE (workspace_id, workspace_seq);

ALTER TABLE ONLY skm_core.idempotency_receipts
    ADD CONSTRAINT uq_idempotency_receipts__scope_key_principal_id_operation_key UNIQUE (scope_key, principal_id, operation, key);

ALTER TABLE ONLY skm_core.outbox
    ADD CONSTRAINT uq_outbox__event_id_destination UNIQUE (event_id, destination);

ALTER TABLE ONLY skm_core.workspace_event_counters
    ADD CONSTRAINT workspace_event_counters_pkey PRIMARY KEY (workspace_id);

ALTER TABLE ONLY skm_execution.incident_gates
    ADD CONSTRAINT incident_gates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.acceptance_decisions
    ADD CONSTRAINT pk_acceptance_decisions PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.assignment_leases
    ADD CONSTRAINT pk_assignment_leases PRIMARY KEY (assignment_id);

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT pk_assignments PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.attempt_file_bindings
    ADD CONSTRAINT pk_attempt_file_bindings PRIMARY KEY (attempt_id, file_version_id, role);

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT pk_attempt_outputs PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.attempt_stages
    ADD CONSTRAINT pk_attempt_stages PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT pk_attempt_steps PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT pk_attempts PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.autopilot_states
    ADD CONSTRAINT pk_autopilot_states PRIMARY KEY (project_id);

ALTER TABLE ONLY skm_execution.budget_accounts
    ADD CONSTRAINT pk_budget_accounts PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.budget_reservations
    ADD CONSTRAINT pk_budget_reservations PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.check_evidence_bindings
    ADD CONSTRAINT pk_check_evidence_bindings PRIMARY KEY (check_execution_id, file_version_id, role);

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT pk_check_executions PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.decision_answers
    ADD CONSTRAINT pk_decision_answers PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.decision_records
    ADD CONSTRAINT pk_decision_records PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.decision_requests
    ADD CONSTRAINT pk_decision_requests PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.deviation_acceptances
    ADD CONSTRAINT pk_deviation_acceptances PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.execution_bundles
    ADD CONSTRAINT pk_execution_bundles PRIMARY KEY (run_id);

ALTER TABLE ONLY skm_execution.execution_environments
    ADD CONSTRAINT pk_execution_environments PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.external_effects
    ADD CONSTRAINT pk_external_effects PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.finding_resolutions
    ADD CONSTRAINT pk_finding_resolutions PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.fix_briefs
    ADD CONSTRAINT pk_fix_briefs PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.integration_slots
    ADD CONSTRAINT pk_integration_slots PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.manual_check_verdicts
    ADD CONSTRAINT pk_manual_check_verdicts PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.output_file_bindings
    ADD CONSTRAINT pk_output_file_bindings PRIMARY KEY (output_id, file_version_id, role);

ALTER TABLE ONLY skm_execution.readiness_reports
    ADD CONSTRAINT pk_readiness_reports PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.result_carry_forwards
    ADD CONSTRAINT pk_result_carry_forwards PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.review_evidence_bindings
    ADD CONSTRAINT pk_review_evidence_bindings PRIMARY KEY (review_id, file_version_id, role);

ALTER TABLE ONLY skm_execution.review_findings
    ADD CONSTRAINT pk_review_findings PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT pk_review_requests PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT pk_reviews PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.revision_visas
    ADD CONSTRAINT pk_revision_visas PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.run_integration_hosts
    ADD CONSTRAINT pk_run_integration_hosts PRIMARY KEY (run_id, repository_id);

ALTER TABLE ONLY skm_execution.run_reconfigurations
    ADD CONSTRAINT pk_run_reconfigurations PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.run_recoveries
    ADD CONSTRAINT pk_run_recoveries PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.run_task_edges
    ADD CONSTRAINT pk_run_task_edges PRIMARY KEY (run_id, dependent_task_id, prerequisite_task_id);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT pk_run_tasks PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT pk_runs PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.step_notes
    ADD CONSTRAINT step_notes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_execution.step_tool_calls
    ADD CONSTRAINT step_tool_calls_pkey PRIMARY KEY (step_id, call_id);

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT uq_assignments__attempt_id_id UNIQUE (attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT uq_attempt_outputs__attempt_id_id UNIQUE (attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT uq_attempt_outputs__attempt_id_seq UNIQUE (attempt_id, seq);

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT uq_attempt_outputs__task_id_id UNIQUE (task_id, id);

ALTER TABLE ONLY skm_execution.attempt_stages
    ADD CONSTRAINT uq_attempt_stages__attempt_id_id UNIQUE (attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_stages
    ADD CONSTRAINT uq_attempt_stages__attempt_id_seq UNIQUE (attempt_id, seq);

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT uq_attempt_steps__attempt_id_id UNIQUE (attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT uq_attempt_steps__attempt_id_seq UNIQUE (attempt_id, seq);

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT uq_attempts__run_id_task_id_id UNIQUE (run_id, task_id, id);

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT uq_attempts__task_id_attempt_no UNIQUE (task_id, attempt_no);

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT uq_attempts__task_id_id UNIQUE (task_id, id);

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT uq_attempts__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT uq_attempts__workspace_run_id UNIQUE (workspace_id, run_id, id);

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT uq_check_executions__output_id_check_spec_id_round_no UNIQUE (output_id, check_spec_id, round_no);

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT uq_check_executions__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_execution.decision_answers
    ADD CONSTRAINT uq_decision_answers__request_id_request_revision UNIQUE (request_id, request_revision);

ALTER TABLE ONLY skm_execution.decision_requests
    ADD CONSTRAINT uq_decision_requests__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_execution.execution_environments
    ADD CONSTRAINT uq_execution_environments__attempt_id UNIQUE (attempt_id);

ALTER TABLE ONLY skm_execution.execution_environments
    ADD CONSTRAINT uq_execution_environments__attempt_id_id UNIQUE (attempt_id, id);

ALTER TABLE ONLY skm_execution.external_effects
    ADD CONSTRAINT uq_external_effects__run_id_kind_request_digest UNIQUE (run_id, kind, request_digest);

ALTER TABLE ONLY skm_execution.external_effects
    ADD CONSTRAINT uq_external_effects__run_task_attempt_id UNIQUE (run_id, task_id, attempt_id, id);

ALTER TABLE ONLY skm_execution.fix_briefs
    ADD CONSTRAINT uq_fix_briefs__task_id_id UNIQUE (task_id, id);

ALTER TABLE ONLY skm_execution.integration_slots
    ADD CONSTRAINT uq_integration_slots__repository_id_target_branch UNIQUE (repository_id, target_branch);

ALTER TABLE ONLY skm_execution.manual_check_verdicts
    ADD CONSTRAINT uq_manual_check_verdicts__check_execution_id_id UNIQUE (check_execution_id, id);

ALTER TABLE ONLY skm_execution.readiness_reports
    ADD CONSTRAINT uq_readiness_reports__revision_scope_id UNIQUE (workspace_id, plan_id, revision_id, id);

ALTER TABLE ONLY skm_execution.review_findings
    ADD CONSTRAINT uq_review_findings__review_id_finding_key UNIQUE (review_id, finding_key);

ALTER TABLE ONLY skm_execution.review_findings
    ADD CONSTRAINT uq_review_findings__review_id_local_id UNIQUE (review_id, local_id);

ALTER TABLE ONLY skm_execution.review_findings
    ADD CONSTRAINT uq_review_findings__task_id_id UNIQUE (task_id, id);

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT uq_review_requests__revision_id UNIQUE (revision_id);

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT uq_review_requests__workspace_id_project_id_id UNIQUE (workspace_id, project_id, id);

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT uq_reviews__task_id_id UNIQUE (task_id, id);

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT uq_reviews__task_id_round_no UNIQUE (task_id, round_no);

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT uq_reviews__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT uq_run_tasks__run_id_display_key UNIQUE (run_id, display_key);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT uq_run_tasks__run_id_id UNIQUE (run_id, id);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT uq_run_tasks__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT uq_runs__id_kind UNIQUE (id, kind);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT uq_runs__id_plan_id_revision_id UNIQUE (id, plan_id, revision_id);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT uq_runs__id_revision_id UNIQUE (id, revision_id);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT uq_runs__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_exports.vault_note_writes
    ADD CONSTRAINT pk_vault_note_writes PRIMARY KEY (note_id, vault_id, generation);

ALTER TABLE ONLY skm_exports.vault_notes
    ADD CONSTRAINT uq_vault_notes__event_id_kind UNIQUE (event_id, kind);

ALTER TABLE ONLY skm_exports.vault_notes
    ADD CONSTRAINT vault_notes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_extensions.pack_versions
    ADD CONSTRAINT pack_versions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_extensions.packs
    ADD CONSTRAINT packs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_extensions.resource_files
    ADD CONSTRAINT pk_resource_files PRIMARY KEY (resource_version_id, path);

ALTER TABLE ONLY skm_extensions.resource_quarantine
    ADD CONSTRAINT resource_quarantine_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_extensions.resource_versions
    ADD CONSTRAINT resource_versions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_extensions.resources
    ADD CONSTRAINT resources_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_extensions.pack_versions
    ADD CONSTRAINT uq_pack_versions__pack_id_version UNIQUE (pack_id, version);

ALTER TABLE ONLY skm_extensions.packs
    ADD CONSTRAINT uq_packs__slug UNIQUE (slug);

ALTER TABLE ONLY skm_extensions.resource_versions
    ADD CONSTRAINT uq_resource_versions__resource_id_pack_version_id UNIQUE (resource_id, pack_version_id);

ALTER TABLE ONLY skm_extensions.resources
    ADD CONSTRAINT uq_resources__kind_key UNIQUE (kind, key);

ALTER TABLE ONLY skm_integrations.projection_files
    ADD CONSTRAINT pk_projection_files PRIMARY KEY (projection_id, relative_path);

ALTER TABLE ONLY skm_integrations.projections
    ADD CONSTRAINT projections_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_integrations.projections
    ADD CONSTRAINT uq_projections__checkout_binding_id_target UNIQUE (checkout_binding_id, target);

ALTER TABLE ONLY skm_knowledge.graph_edges
    ADD CONSTRAINT graph_edges_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_knowledge.graph_indexes
    ADD CONSTRAINT graph_indexes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_knowledge.graph_nodes
    ADD CONSTRAINT graph_nodes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT lessons_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_knowledge.memory_entries
    ADD CONSTRAINT memory_entries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_knowledge.graph_edges
    ADD CONSTRAINT uq_graph_edges__identity UNIQUE (src_node_id, dst_node_id, type, source, source_key);

ALTER TABLE ONLY skm_knowledge.graph_indexes
    ADD CONSTRAINT uq_graph_indexes__generation UNIQUE NULLS NOT DISTINCT (workspace_id, source, repository_id, generation);

ALTER TABLE ONLY skm_knowledge.graph_nodes
    ADD CONSTRAINT uq_graph_nodes__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_knowledge.graph_nodes
    ADD CONSTRAINT uq_graph_nodes__workspace_id_node_key UNIQUE (workspace_id, node_key);

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT uq_lessons__candidate_id UNIQUE (candidate_id);

ALTER TABLE ONLY skm_learning.activity_records
    ADD CONSTRAINT activity_records_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_learning.candidate_proposals
    ADD CONSTRAINT candidate_proposals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_learning.candidate_reviews
    ADD CONSTRAINT candidate_reviews_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT candidates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_learning.signals
    ADD CONSTRAINT signals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_learning.activity_records
    ADD CONSTRAINT uq_activity_records__workspace_id_source_key UNIQUE (workspace_id, source_key);

ALTER TABLE ONLY skm_learning.candidate_proposals
    ADD CONSTRAINT uq_candidate_proposals__identity UNIQUE (candidate_id, source_activity_id, fingerprint);

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT uq_candidates__project_id_display_key UNIQUE (project_id, display_key);

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT uq_candidates__scope_id_fingerprint UNIQUE (scope_id, fingerprint);

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT uq_candidates__scope_id_id UNIQUE (scope_id, id);

ALTER TABLE ONLY skm_learning.signals
    ADD CONSTRAINT uq_signals__identity UNIQUE NULLS NOT DISTINCT (candidate_id, activity_record_id, source);

ALTER TABLE ONLY skm_planning.acceptance_criteria
    ADD CONSTRAINT pk_acceptance_criteria PRIMARY KEY (revision_id, criterion_id);

ALTER TABLE ONLY skm_planning.artifact_specs
    ADD CONSTRAINT pk_artifact_specs PRIMARY KEY (revision_id, item_id, "position");

ALTER TABLE ONLY skm_planning.batch_members
    ADD CONSTRAINT pk_batch_members PRIMARY KEY (revision_id, phase_id, batch_key, item_id);

ALTER TABLE ONLY skm_planning.batch_specs
    ADD CONSTRAINT pk_batch_specs PRIMARY KEY (revision_id, phase_id, batch_key);

ALTER TABLE ONLY skm_planning.check_specs
    ADD CONSTRAINT pk_check_specs PRIMARY KEY (revision_id, check_id);

ALTER TABLE ONLY skm_planning.criterion_check_bindings
    ADD CONSTRAINT pk_criterion_check_bindings PRIMARY KEY (revision_id, criterion_id, check_id);

ALTER TABLE ONLY skm_planning.decision_bindings
    ADD CONSTRAINT pk_decision_bindings PRIMARY KEY (revision_id, decision_id, entity_id, binding_kind);

ALTER TABLE ONLY skm_planning.decision_specs
    ADD CONSTRAINT pk_decision_specs PRIMARY KEY (revision_id, decision_id);

ALTER TABLE ONLY skm_planning.decision_supersessions
    ADD CONSTRAINT pk_decision_supersessions PRIMARY KEY (revision_id, decision_id, superseded_decision_id);

ALTER TABLE ONLY skm_planning.dependency_edges
    ADD CONSTRAINT pk_dependency_edges PRIMARY KEY (revision_id, dependent_entity_id, prerequisite_entity_id, dependency_kind);

ALTER TABLE ONLY skm_planning.entity_check_bindings
    ADD CONSTRAINT pk_entity_check_bindings PRIMARY KEY (revision_id, entity_id, check_id);

ALTER TABLE ONLY skm_planning.entity_path_specs
    ADD CONSTRAINT pk_entity_path_specs PRIMARY KEY (revision_id, entity_id, role, "position");

ALTER TABLE ONLY skm_planning.entity_read_specs
    ADD CONSTRAINT pk_entity_read_specs PRIMARY KEY (revision_id, entity_id, purpose, "position");

ALTER TABLE ONLY skm_planning.entity_relations
    ADD CONSTRAINT pk_entity_relations PRIMARY KEY (revision_id, source_entity_id, target_entity_id, relation);

ALTER TABLE ONLY skm_planning.entity_requirement_links
    ADD CONSTRAINT pk_entity_requirement_links PRIMARY KEY (revision_id, entity_id, requirement_id, relation);

ALTER TABLE ONLY skm_planning.entity_skill_requirements
    ADD CONSTRAINT pk_entity_skill_requirements PRIMARY KEY (revision_id, entity_id, resource_key);

ALTER TABLE ONLY skm_planning.item_specs
    ADD CONSTRAINT pk_item_specs PRIMARY KEY (revision_id, item_id);

ALTER TABLE ONLY skm_planning.material_bindings
    ADD CONSTRAINT pk_material_bindings PRIMARY KEY (revision_id, material_id, entity_id);

ALTER TABLE ONLY skm_planning.material_specs
    ADD CONSTRAINT pk_material_specs PRIMARY KEY (revision_id, material_id);

ALTER TABLE ONLY skm_planning.phase_specs
    ADD CONSTRAINT pk_phase_specs PRIMARY KEY (revision_id, phase_id);

ALTER TABLE ONLY skm_planning.plan_aliases
    ADD CONSTRAINT pk_plan_aliases PRIMARY KEY (workspace_id, project_id, alias);

ALTER TABLE ONLY skm_planning.plan_design_brief_rag_bindings
    ADD CONSTRAINT pk_plan_design_brief_rag_bindings PRIMARY KEY (design_brief_id, file_version_id);

ALTER TABLE ONLY skm_planning.plan_design_brief_research_references
    ADD CONSTRAINT pk_plan_design_brief_research_refs PRIMARY KEY (design_brief_id, reference);

ALTER TABLE ONLY skm_planning.plan_design_briefs
    ADD CONSTRAINT pk_plan_design_briefs PRIMARY KEY (id);

ALTER TABLE ONLY skm_planning.plan_drafts
    ADD CONSTRAINT pk_plan_drafts PRIMARY KEY (id);

ALTER TABLE ONLY skm_planning.plan_entity_identities
    ADD CONSTRAINT pk_plan_entity_identities PRIMARY KEY (plan_id, entity_id);

ALTER TABLE ONLY skm_planning.plan_relations
    ADD CONSTRAINT pk_plan_relations PRIMARY KEY (revision_id, "position");

ALTER TABLE ONLY skm_planning.plan_revisions
    ADD CONSTRAINT pk_plan_revisions PRIMARY KEY (id);

ALTER TABLE ONLY skm_planning.plans
    ADD CONSTRAINT pk_plans PRIMARY KEY (id);

ALTER TABLE ONLY skm_planning.project_plan_counters
    ADD CONSTRAINT pk_project_plan_counters PRIMARY KEY (project_id);

ALTER TABLE ONLY skm_planning.requirement_specs
    ADD CONSTRAINT pk_requirement_specs PRIMARY KEY (revision_id, requirement_id);

ALTER TABLE ONLY skm_planning.review_requirements
    ADD CONSTRAINT pk_review_requirements PRIMARY KEY (revision_id, owner_entity_id);

ALTER TABLE ONLY skm_planning.revision_file_bindings
    ADD CONSTRAINT pk_revision_file_bindings PRIMARY KEY (revision_id, material_id);

ALTER TABLE ONLY skm_planning.revision_members
    ADD CONSTRAINT pk_revision_members PRIMARY KEY (revision_id, entity_id);

ALTER TABLE ONLY skm_planning.revision_payloads
    ADD CONSTRAINT pk_revision_payloads PRIMARY KEY (revision_id);

ALTER TABLE ONLY skm_planning.revision_specs
    ADD CONSTRAINT pk_revision_specs PRIMARY KEY (revision_id);

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT pk_unit_specs PRIMARY KEY (revision_id, unit_id);

ALTER TABLE ONLY skm_planning.batch_members
    ADD CONSTRAINT uq_batch_members__item UNIQUE (revision_id, item_id);

ALTER TABLE ONLY skm_planning.batch_specs
    ADD CONSTRAINT uq_batch_specs__phase_position UNIQUE (revision_id, phase_id, "position");

ALTER TABLE ONLY skm_planning.check_specs
    ADD CONSTRAINT uq_check_specs__owner_local_key UNIQUE (revision_id, owner_entity_id, local_key);

ALTER TABLE ONLY skm_planning.item_specs
    ADD CONSTRAINT uq_item_specs__revision_id_position UNIQUE (revision_id, "position");

ALTER TABLE ONLY skm_planning.material_specs
    ADD CONSTRAINT uq_material_specs__scope UNIQUE (workspace_id, plan_id, revision_id, material_id);

ALTER TABLE ONLY skm_planning.phase_specs
    ADD CONSTRAINT uq_phase_specs__revision_id_position UNIQUE (revision_id, "position");

ALTER TABLE ONLY skm_planning.plan_design_briefs
    ADD CONSTRAINT uq_plan_design_briefs__scope_id UNIQUE (workspace_id, plan_id, id);

ALTER TABLE ONLY skm_planning.plan_drafts
    ADD CONSTRAINT uq_plan_drafts__workspace_id_plan_id_id UNIQUE (workspace_id, plan_id, id);

ALTER TABLE ONLY skm_planning.plan_entity_identities
    ADD CONSTRAINT uq_plan_entity_identities__entity_id UNIQUE (entity_id);

ALTER TABLE ONLY skm_planning.plan_revisions
    ADD CONSTRAINT uq_plan_revisions__plan_id_revision_no UNIQUE (plan_id, revision_no);

ALTER TABLE ONLY skm_planning.plan_revisions
    ADD CONSTRAINT uq_plan_revisions__workspace_id_plan_id_id UNIQUE (workspace_id, plan_id, id);

ALTER TABLE ONLY skm_planning.plans
    ADD CONSTRAINT uq_plans__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_planning.plans
    ADD CONSTRAINT uq_plans__workspace_id_project_id_id UNIQUE (workspace_id, project_id, id);

ALTER TABLE ONLY skm_planning.revision_members
    ADD CONSTRAINT uq_revision_members__revision_id_display_key UNIQUE (revision_id, display_key);

ALTER TABLE ONLY skm_planning.revision_members
    ADD CONSTRAINT uq_revision_members__scope_entity UNIQUE (workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.revision_members
    ADD CONSTRAINT uq_revision_members__scope_entity_kind UNIQUE (workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT uq_unit_specs__item_local_key UNIQUE (revision_id, item_id, local_key);

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT uq_unit_specs__item_position UNIQUE (revision_id, item_id, "position");

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT uq_unit_specs__revision_item_unit UNIQUE (revision_id, item_id, unit_id);

ALTER TABLE ONLY skm_policy.approvals
    ADD CONSTRAINT approvals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_policy.decision_audit
    ADD CONSTRAINT decision_audit_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_policy.tool_intents
    ADD CONSTRAINT tool_intents_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_policy.tool_intents
    ADD CONSTRAINT uq_tool_intents__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_runtimes.canonical_models
    ADD CONSTRAINT canonical_models_pkey PRIMARY KEY (model_id);

ALTER TABLE ONLY skm_runtimes.capability_verifications
    ADD CONSTRAINT capability_verifications_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_runtimes.host_model_availability
    ADD CONSTRAINT pk_host_model_availability PRIMARY KEY (host_id, runtime_id, model_id, effort);

ALTER TABLE ONLY skm_runtimes.host_runtimes
    ADD CONSTRAINT pk_host_runtimes PRIMARY KEY (host_id, runtime_id);

ALTER TABLE ONLY skm_runtimes.model_guidelines
    ADD CONSTRAINT pk_model_guidelines PRIMARY KEY (resource_version_id, runtime_id, model_id);

ALTER TABLE ONLY skm_runtimes.provider_model_offerings
    ADD CONSTRAINT pk_provider_model_offerings PRIMARY KEY (runtime_id, model_id);

ALTER TABLE ONLY skm_workspace.checkout_bindings
    ADD CONSTRAINT checkout_bindings_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_workspace.hosts
    ADD CONSTRAINT hosts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_workspace.project_repositories
    ADD CONSTRAINT pk_project_repositories PRIMARY KEY (project_id, mount_name);

ALTER TABLE ONLY skm_workspace.repository_remotes
    ADD CONSTRAINT pk_repository_remotes PRIMARY KEY (repository_id, normalized_url);

ALTER TABLE ONLY skm_workspace.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_workspace.repositories
    ADD CONSTRAINT repositories_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_workspace.checkout_bindings
    ADD CONSTRAINT uq_checkout_bindings__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_workspace.hosts
    ADD CONSTRAINT uq_hosts__name UNIQUE (name);

ALTER TABLE ONLY skm_workspace.project_repositories
    ADD CONSTRAINT uq_project_repositories__project_id_repository_id UNIQUE (project_id, repository_id);

ALTER TABLE ONLY skm_workspace.projects
    ADD CONSTRAINT uq_projects__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_workspace.projects
    ADD CONSTRAINT uq_projects__workspace_id_slug UNIQUE (workspace_id, slug);

ALTER TABLE ONLY skm_workspace.repositories
    ADD CONSTRAINT uq_repositories__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_workspace.repository_remotes
    ADD CONSTRAINT uq_repository_remotes__workspace_id_normalized_url UNIQUE (workspace_id, normalized_url);

ALTER TABLE ONLY skm_workspace.workers
    ADD CONSTRAINT uq_workers__principal_id UNIQUE (principal_id);

ALTER TABLE ONLY skm_workspace.workers
    ADD CONSTRAINT uq_workers__workspace_id_id UNIQUE (workspace_id, id);

ALTER TABLE ONLY skm_workspace.workspaces
    ADD CONSTRAINT uq_workspaces__slug UNIQUE (slug);

ALTER TABLE ONLY skm_workspace.workers
    ADD CONSTRAINT workers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY skm_workspace.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);

CREATE INDEX ix_api_tokens__assignment_id ON skm_access.api_tokens USING btree (assignment_id) WHERE (assignment_id IS NOT NULL);

CREATE INDEX ix_api_tokens__principal_id_created_at ON skm_access.api_tokens USING btree (principal_id, created_at, id);

CREATE INDEX ix_memberships__principal_id ON skm_access.memberships USING btree (principal_id);

CREATE INDEX ix_memberships__scope_id_role ON skm_access.memberships USING btree (scope_id, role);

CREATE INDEX ix_pairing_tokens__workspace ON skm_access.pairing_tokens USING btree (workspace_id);

CREATE INDEX ix_principal_identities__principal_id ON skm_access.principal_identities USING btree (principal_id);

CREATE INDEX ix_principals__kind_created_at ON skm_access.principals USING btree (kind, created_at, id);

CREATE INDEX ix_web_sessions__principal_id ON skm_access.web_sessions USING btree (principal_id);

CREATE UNIQUE INDEX uq_api_tokens__principal_id_name_active ON skm_access.api_tokens USING btree (principal_id, name) WHERE ((revoked_at IS NULL) AND (superseded_by IS NULL));

CREATE INDEX ix_access_grants__principal_id_file_version_id_active ON skm_artifacts.access_grants USING btree (principal_id, file_version_id) WHERE (revoked_at IS NULL);

CREATE INDEX ix_access_grants__reason_ref_active ON skm_artifacts.access_grants USING btree (reason, ref) WHERE (revoked_at IS NULL);

CREATE INDEX ix_file_versions__blob_id ON skm_artifacts.file_versions USING btree (blob_id);

CREATE INDEX ix_files__workspace_id_project_id_created_at ON skm_artifacts.files USING btree (workspace_id, project_id, created_at DESC, id);

CREATE INDEX ix_staged_blobs__backend_id_storage_key ON skm_artifacts.staged_blobs USING btree (backend_id, storage_key);

CREATE INDEX ix_staged_blobs__consumed_at ON skm_artifacts.staged_blobs USING btree (consumed_at) WHERE (consumed_at IS NOT NULL);

CREATE INDEX ix_staged_blobs__expires_at_unconsumed ON skm_artifacts.staged_blobs USING btree (expires_at) WHERE (consumed_at IS NULL);

CREATE INDEX ix_entries__key ON skm_config.entries USING btree (key);

CREATE INDEX ix_entry_history__changed_at ON skm_config.entry_history USING btree (changed_at DESC, id DESC);

CREATE INDEX ix_entry_history__scope_id_key_changed_at ON skm_config.entry_history USING btree (scope_id, key, changed_at DESC, id DESC);

CREATE INDEX ix_context_manifests__workspace_id_plan_id_created_at ON skm_context.context_manifests USING btree (workspace_id, plan_id, created_at DESC);

CREATE INDEX ix_external_sources__project_id_origin ON skm_context.external_sources USING btree (workspace_id, project_id, origin);

CREATE INDEX ix_research_queries__cache ON skm_context.research_queries USING btree (workspace_id, project_id, cache_key, retrieved_at DESC) WHERE (status <> 'error'::text);

CREATE INDEX ix_research_queries__step_ref ON skm_context.research_queries USING btree (step_ref) WHERE (step_ref IS NOT NULL);

CREATE INDEX ix_audit_records__actor_id_recorded_at ON skm_core.audit_records USING btree (actor_id, recorded_at);

CREATE INDEX ix_audit_records__workspace_id_recorded_at ON skm_core.audit_records USING btree (workspace_id, recorded_at);

CREATE INDEX ix_consumer_receipts__processed_at ON skm_core.consumer_receipts USING btree (processed_at);

CREATE INDEX ix_domain_events__correlation_id ON skm_core.domain_events USING btree (correlation_id);

CREATE INDEX ix_domain_events__event_type_recorded_at ON skm_core.domain_events USING btree (event_type, recorded_at);

CREATE INDEX ix_domain_events__stream_id ON skm_core.domain_events USING btree (stream_id);

CREATE INDEX ix_idempotency_receipts__expires_at ON skm_core.idempotency_receipts USING btree (expires_at);

CREATE INDEX ix_outbox__dead_notification_due ON skm_core.outbox USING btree (available_at, id) WHERE ((state = 'dead'::text) AND (dead_notified_at IS NULL));

CREATE INDEX ix_outbox__delivered_at ON skm_core.outbox USING btree (delivered_at) WHERE (state = 'delivered'::text);

CREATE INDEX ix_outbox__destination_state ON skm_core.outbox USING btree (destination, state);

CREATE INDEX ix_outbox__state_available_at ON skm_core.outbox USING btree (state, available_at) WHERE (state = ANY (ARRAY['pending'::text, 'failed'::text]));

CREATE INDEX ix_scopes__parent_id ON skm_core.scopes USING btree (parent_id);

CREATE INDEX ix_scopes__workspace_id_kind ON skm_core.scopes USING btree (workspace_id, kind);

CREATE UNIQUE INDEX uq_domain_events__global_position ON skm_core.domain_events USING btree (global_position) WHERE (global_position IS NOT NULL);

CREATE UNIQUE INDEX uq_scopes__single_instance ON skm_core.scopes USING btree (kind) WHERE (kind = 'instance'::text);

CREATE INDEX ix_acceptance_decisions__task_id_decided_at ON skm_execution.acceptance_decisions USING btree (task_id, decided_at DESC);

CREATE INDEX ix_assignment_leases__expires_at ON skm_execution.assignment_leases USING btree (expires_at);

CREATE INDEX ix_assignments__claim ON skm_execution.assignments USING btree (priority, available_at, id) WHERE (state = 'available'::text);

CREATE INDEX ix_assignments__run_id_state ON skm_execution.assignments USING btree (run_id, state);

CREATE INDEX ix_attempt_file_bindings__file_version_id ON skm_execution.attempt_file_bindings USING btree (file_version_id);

CREATE INDEX ix_attempt_stages__attempt_id_stage_id_round_no_input_digest ON skm_execution.attempt_stages USING btree (attempt_id, stage_id, round_no, input_digest);

CREATE INDEX ix_attempt_stages__unfinished_started_at ON skm_execution.attempt_stages USING btree (started_at) WHERE (state = ANY (ARRAY['started'::text, 'context_draft'::text, 'running'::text]));

CREATE INDEX ix_attempt_steps__attempt_id_role_seq ON skm_execution.attempt_steps USING btree (attempt_id, role, seq DESC);

CREATE INDEX ix_attempt_steps__running_last_progress_at ON skm_execution.attempt_steps USING btree (last_progress_at) WHERE (state = 'started'::text);

CREATE INDEX ix_attempt_steps__session_fingerprint_digest ON skm_execution.attempt_steps USING btree (session_fingerprint_digest);

CREATE INDEX ix_attempt_steps__stage_record_id ON skm_execution.attempt_steps USING btree (stage_record_id);

CREATE INDEX ix_attempt_steps__workspace_id_reuse_key ON skm_execution.attempt_steps USING btree (workspace_id, reuse_key) WHERE ((reuse_key IS NOT NULL) AND (state = 'succeeded'::text));

CREATE INDEX ix_attempts__host_id_state ON skm_execution.attempts USING btree (host_id, state) WHERE (host_id IS NOT NULL);

CREATE INDEX ix_attempts__run_id_state ON skm_execution.attempts USING btree (run_id, state);

CREATE INDEX ix_autopilot_states__active ON skm_execution.autopilot_states USING btree (state) WHERE (state = ANY (ARRAY['running'::text, 'paused'::text, 'draining'::text]));

CREATE INDEX ix_autopilot_states__emergency ON skm_execution.autopilot_states USING btree (project_id) WHERE emergency;

CREATE INDEX ix_budget_reservations__run_id_state ON skm_execution.budget_reservations USING btree (run_id, state);

CREATE INDEX ix_check_executions__fingerprint_check_spec_id_passed ON skm_execution.check_executions USING btree (fingerprint, check_spec_id) WHERE ((state = 'passed'::text) AND (reused_from_id IS NULL));

CREATE INDEX ix_check_executions__output_id ON skm_execution.check_executions USING btree (output_id);

CREATE INDEX ix_check_executions__task_id_round_no ON skm_execution.check_executions USING btree (task_id, round_no);

CREATE INDEX ix_decision_records__request_id_created_at ON skm_execution.decision_records USING btree (request_id, created_at DESC, id DESC);

CREATE INDEX ix_decision_requests__deadline_at_open ON skm_execution.decision_requests USING btree (deadline_at) WHERE ((state = 'open'::text) AND (deadline_at IS NOT NULL));

CREATE INDEX ix_decision_requests__run_id_state ON skm_execution.decision_requests USING btree (run_id, state);

CREATE INDEX ix_decision_requests__task_id_open ON skm_execution.decision_requests USING btree (task_id) WHERE (state = 'open'::text);

CREATE INDEX ix_decision_requests__workspace_id_state_created_at ON skm_execution.decision_requests USING btree (workspace_id, state, created_at DESC, id);

CREATE INDEX ix_deviation_acceptances__task_id ON skm_execution.deviation_acceptances USING btree (task_id);

CREATE INDEX ix_execution_environments__existing_checkout_live ON skm_execution.execution_environments USING btree (attempt_id) WHERE ((kind = 'existing_checkout'::text) AND (state = ANY (ARRAY['preparing'::text, 'ready'::text])));

CREATE INDEX ix_execution_environments__host_id_state ON skm_execution.execution_environments USING btree (host_id, state, created_at);

CREATE INDEX ix_external_effects__attempt_id ON skm_execution.external_effects USING btree (attempt_id);

CREATE INDEX ix_external_effects__unresolved ON skm_execution.external_effects USING btree (updated_at, id) WHERE (state = ANY (ARRAY['intended'::text, 'executing'::text, 'outcome_unknown'::text]));

CREATE INDEX ix_finding_resolutions__finding_id ON skm_execution.finding_resolutions USING btree (finding_id);

CREATE INDEX ix_readiness_reports__revision_id_created_at ON skm_execution.readiness_reports USING btree (revision_id, created_at DESC);

CREATE INDEX ix_review_findings__task_id_finding_key_created_at ON skm_execution.review_findings USING btree (task_id, finding_key, created_at DESC);

CREATE INDEX ix_review_requests__project_id_created_at ON skm_execution.review_requests USING btree (project_id, created_at DESC);

CREATE INDEX ix_reviews__output_id ON skm_execution.reviews USING btree (output_id);

CREATE INDEX ix_revision_visas__report ON skm_execution.revision_visas USING btree (readiness_report_id);

CREATE INDEX ix_run_reconfigurations__run_id_changed_at ON skm_execution.run_reconfigurations USING btree (run_id, changed_at);

CREATE INDEX ix_run_recoveries__run_id_at ON skm_execution.run_recoveries USING btree (run_id, at);

CREATE INDEX ix_run_task_edges__run_id_prerequisite_task_id ON skm_execution.run_task_edges USING btree (run_id, prerequisite_task_id);

CREATE INDEX ix_run_tasks__blocking_next_check_at ON skm_execution.run_tasks USING btree (blocking_next_check_at) WHERE (blocking_next_check_at IS NOT NULL);

CREATE INDEX ix_run_tasks__run_id_status_position ON skm_execution.run_tasks USING btree (run_id, status, "position");

CREATE INDEX ix_run_tasks__spec_entity_id ON skm_execution.run_tasks USING btree (spec_entity_id) WHERE (spec_entity_id IS NOT NULL);

CREATE INDEX ix_run_tasks__workspace_id_blocking_code ON skm_execution.run_tasks USING btree (workspace_id, blocking_code) WHERE (blocking_code IS NOT NULL);

CREATE INDEX ix_runs__plan_id_created_at ON skm_execution.runs USING btree (plan_id, created_at DESC);

CREATE INDEX ix_runs__project_id_status_created_at ON skm_execution.runs USING btree (project_id, status, created_at DESC, id DESC);

CREATE INDEX ix_runs__queued ON skm_execution.runs USING btree (project_id, created_at) WHERE queued;

CREATE INDEX ix_runs__status_active ON skm_execution.runs USING btree (status, id) WHERE (status = ANY (ARRAY['running'::text, 'waiting'::text]));

CREATE INDEX ix_step_notes__step_created ON skm_execution.step_notes USING btree (step_id, created_at, id);

CREATE UNIQUE INDEX uq_assignments__attempt_id_live ON skm_execution.assignments USING btree (attempt_id) WHERE (state = ANY (ARRAY['available'::text, 'leased'::text]));

CREATE UNIQUE INDEX uq_assignments__reconcile_effect_live ON skm_execution.assignments USING btree (reconcile_effect_id) WHERE ((reconcile_effect_id IS NOT NULL) AND (state = ANY (ARRAY['available'::text, 'leased'::text])));

CREATE UNIQUE INDEX uq_attempt_stages__attempt_id_active ON skm_execution.attempt_stages USING btree (attempt_id) WHERE (state = ANY (ARRAY['started'::text, 'context_draft'::text, 'running'::text]));

CREATE UNIQUE INDEX uq_budget_accounts__run_id_dimension_run ON skm_execution.budget_accounts USING btree (run_id, dimension) WHERE (scope = 'run'::text);

CREATE UNIQUE INDEX uq_budget_accounts__task_id_dimension_task ON skm_execution.budget_accounts USING btree (task_id, dimension) WHERE (scope = 'task'::text);

CREATE UNIQUE INDEX uq_decision_records__project_id_question_key_applied ON skm_execution.decision_records USING btree (project_id, question_key) WHERE (status = 'applied'::text);

CREATE UNIQUE INDEX uq_manual_check_verdicts__supersedes_id ON skm_execution.manual_check_verdicts USING btree (supersedes_id) WHERE (supersedes_id IS NOT NULL);

CREATE UNIQUE INDEX uq_result_carry_forwards__target_task_id_accepted ON skm_execution.result_carry_forwards USING btree (target_task_id) WHERE (decision = 'accepted'::text);

CREATE UNIQUE INDEX uq_run_recoveries__stage_record_id_open ON skm_execution.run_recoveries USING btree (stage_record_id) WHERE (outcome IS NULL);

CREATE UNIQUE INDEX uq_runs__review_request_id ON skm_execution.runs USING btree (review_request_id) WHERE (review_request_id IS NOT NULL);

CREATE INDEX ix_vault_notes__project_id_pending_since ON skm_exports.vault_notes USING btree (project_id, COALESCE(requeued_at, created_at)) WHERE (state = 'pending'::text);

CREATE INDEX ix_pack_versions__pack_id_semver ON skm_extensions.pack_versions USING btree (pack_id, version_major DESC, version_minor DESC, version_patch DESC, ((prerelease IS NULL)) DESC, prerelease DESC);

CREATE INDEX ix_resource_versions__pack_version_id ON skm_extensions.resource_versions USING btree (pack_version_id);

CREATE INDEX ix_resource_versions__resource_id_digest ON skm_extensions.resource_versions USING btree (resource_id, digest);

CREATE UNIQUE INDEX uq_resource_quarantine__resource_version_id_active ON skm_extensions.resource_quarantine USING btree (resource_version_id) WHERE (released_at IS NULL);

CREATE INDEX ix_projection_files__projection_id_ownership ON skm_integrations.projection_files USING btree (projection_id, ownership);

CREATE INDEX ix_projections__project_id_state ON skm_integrations.projections USING btree (project_id, state);

CREATE INDEX ix_projections__project_id_updated_at_id ON skm_integrations.projections USING btree (project_id, updated_at, id);

CREATE INDEX ix_graph_edges__dst ON skm_knowledge.graph_edges USING btree (workspace_id, dst_node_id, type);

CREATE INDEX ix_graph_edges__source_repository ON skm_knowledge.graph_edges USING btree (workspace_id, source, repository_id);

CREATE INDEX ix_graph_edges__src ON skm_knowledge.graph_edges USING btree (workspace_id, src_node_id, type);

CREATE INDEX ix_graph_indexes__latest ON skm_knowledge.graph_indexes USING btree (workspace_id, source, repository_id, generation DESC);

CREATE INDEX ix_graph_nodes__source_repository ON skm_knowledge.graph_nodes USING btree (workspace_id, source, repository_id);

CREATE INDEX ix_lessons__workspace_scope_state ON skm_knowledge.lessons USING btree (workspace_id, scope_id, state, updated_at, id);

CREATE INDEX ix_memory_entries__body_fts ON skm_knowledge.memory_entries USING gin (to_tsvector('simple'::regconfig, body));

CREATE INDEX ix_memory_entries__expires_at_live ON skm_knowledge.memory_entries USING btree (expires_at) WHERE (state = 'live'::text);

CREATE INDEX ix_memory_entries__scope_live ON skm_knowledge.memory_entries USING btree (scope_kind, scope_id, namespace, workspace_id, expires_at) WHERE (state = 'live'::text);

CREATE INDEX ix_memory_entries__state_changed_at ON skm_knowledge.memory_entries USING btree (state_changed_at) WHERE (state <> 'live'::text);

CREATE UNIQUE INDEX uq_memory_entries__live_handoff ON skm_knowledge.memory_entries USING btree (scope_kind, scope_id, namespace, workspace_id) NULLS NOT DISTINCT WHERE ((state = 'live'::text) AND (kind = 'active_handoff'::text));

CREATE INDEX ix_activity_records__project_id_observed_at ON skm_learning.activity_records USING btree (project_id, observed_at DESC);

CREATE INDEX ix_activity_records__scope_id_observed_at ON skm_learning.activity_records USING btree (scope_id, observed_at DESC, id);

CREATE INDEX ix_candidate_proposals__target_observed ON skm_learning.candidate_proposals USING btree (candidate_id, observed_at DESC, source_key DESC, fingerprint DESC);

CREATE INDEX ix_candidate_reviews__candidate_id_created_at ON skm_learning.candidate_reviews USING btree (candidate_id, created_at);

CREATE INDEX ix_candidates__scope_state_updated ON skm_learning.candidates USING btree (scope_id, state, updated_at DESC, id);

CREATE INDEX ix_candidates__workspace_id_id ON skm_learning.candidates USING btree (workspace_id, id);

CREATE INDEX ix_signals__candidate_id_observed_at ON skm_learning.signals USING btree (candidate_id, observed_at, id);

CREATE INDEX ix_acceptance_criteria__revision_id_owner_entity_id ON skm_planning.acceptance_criteria USING btree (revision_id, owner_entity_id);

CREATE INDEX ix_check_specs__revision_id_owner_entity_id ON skm_planning.check_specs USING btree (revision_id, owner_entity_id);

CREATE INDEX ix_decision_bindings__revision_id_entity_id ON skm_planning.decision_bindings USING btree (revision_id, entity_id);

CREATE INDEX ix_dependency_edges__revision_id_prerequisite ON skm_planning.dependency_edges USING btree (revision_id, prerequisite_entity_id);

CREATE INDEX ix_entity_requirement_links__revision_id_requirement_id ON skm_planning.entity_requirement_links USING btree (revision_id, requirement_id);

CREATE INDEX ix_item_specs__revision_id_phase_id_position ON skm_planning.item_specs USING btree (revision_id, phase_id, "position", item_id);

CREATE INDEX ix_plan_aliases__plan_id ON skm_planning.plan_aliases USING btree (plan_id);

CREATE INDEX ix_plan_design_brief_rag__version ON skm_planning.plan_design_brief_rag_bindings USING btree (workspace_id, file_version_id);

CREATE INDEX ix_plan_drafts__plan_id_state ON skm_planning.plan_drafts USING btree (plan_id, state);

CREATE INDEX ix_plan_relations__target_plan_id ON skm_planning.plan_relations USING btree (target_plan_id) WHERE (target_plan_id IS NOT NULL);

CREATE INDEX ix_plans__workspace_id_project_id_lifecycle_state_updated_at_id ON skm_planning.plans USING btree (workspace_id, project_id, lifecycle_state, updated_at DESC, id DESC);

CREATE INDEX ix_revision_file_bindings__file_version_id ON skm_planning.revision_file_bindings USING btree (file_version_id);

CREATE INDEX ix_revision_members__revision_id_entity_kind_position ON skm_planning.revision_members USING btree (revision_id, entity_kind, "position");

CREATE INDEX ix_unit_specs__revision_id_item_id_position ON skm_planning.unit_specs USING btree (revision_id, item_id, "position", unit_id);

CREATE UNIQUE INDEX uq_artifact_specs__output_key ON skm_planning.artifact_specs USING btree (revision_id, artifact_key) WHERE ((role = 'output'::text) AND (artifact_key IS NOT NULL));

CREATE UNIQUE INDEX uq_plan_aliases__plan_id_short ON skm_planning.plan_aliases USING btree (plan_id) WHERE (alias_kind = ANY (ARRAY['short'::text, 'system'::text]));

CREATE UNIQUE INDEX uq_plans__project_id_review_requests ON skm_planning.plans USING btree (project_id) WHERE (purpose = 'review_requests'::text);

CREATE INDEX ix_approvals__intent_id_created_at ON skm_policy.approvals USING btree (intent_id, created_at);

CREATE INDEX ix_decision_audit__at ON skm_policy.decision_audit USING btree (at);

CREATE INDEX ix_decision_audit__scope_id_at ON skm_policy.decision_audit USING btree (scope_id, at);

CREATE INDEX ix_decision_audit__scope_id_operation ON skm_policy.decision_audit USING btree (scope_id, operation) WHERE (operation IS NOT NULL);

CREATE INDEX ix_tool_intents__expires_at_open ON skm_policy.tool_intents USING btree (expires_at) WHERE (state = ANY (ARRAY['proposed'::text, 'approved'::text]));

CREATE INDEX ix_tool_intents__scope_id_state ON skm_policy.tool_intents USING btree (scope_id, state);

CREATE INDEX ix_tool_intents__workspace_id_created_at ON skm_policy.tool_intents USING btree (workspace_id, created_at, id);

CREATE UNIQUE INDEX uq_tool_intents__scope_id_kind_args_digest_active ON skm_policy.tool_intents USING btree (scope_id, kind, args_digest) WHERE (state = ANY (ARRAY['proposed'::text, 'approved'::text, 'executing'::text]));

CREATE INDEX ix_capability_verifications__runtime_id_capability_recorded_at ON skm_runtimes.capability_verifications USING btree (runtime_id, capability, recorded_at DESC);

CREATE INDEX ix_host_model_availability__offering ON skm_runtimes.host_model_availability USING btree (runtime_id, model_id);

CREATE INDEX ix_host_runtimes__runtime_id ON skm_runtimes.host_runtimes USING btree (runtime_id);

CREATE INDEX ix_model_guidelines__offering ON skm_runtimes.model_guidelines USING btree (runtime_id, model_id);

CREATE INDEX ix_provider_model_offerings__model_id ON skm_runtimes.provider_model_offerings USING btree (model_id);

CREATE UNIQUE INDEX uq_capability_verifications__record ON skm_runtimes.capability_verifications USING btree (runtime_id, COALESCE(runtime_version, ''::text), COALESCE(verification_key, ''::text), capability, verified_at, status);

CREATE INDEX ix_project_repositories__repository_id ON skm_workspace.project_repositories USING btree (repository_id);

CREATE INDEX ix_projects__workspace_id_state ON skm_workspace.projects USING btree (workspace_id, state);

CREATE INDEX ix_workers__state_last_heartbeat_at ON skm_workspace.workers USING btree (state, last_heartbeat_at);

CREATE INDEX ix_workers__workspace_id_state ON skm_workspace.workers USING btree (workspace_id, state);

CREATE UNIQUE INDEX uq_checkout_bindings__host_id_repository_id_live ON skm_workspace.checkout_bindings USING btree (host_id, repository_id) WHERE (state <> 'removed'::text);

CREATE UNIQUE INDEX uq_project_repositories__one_primary ON skm_workspace.project_repositories USING btree (project_id) WHERE (role = 'primary'::text);

CREATE UNIQUE INDEX uq_repositories__workspace_id_canonical_remote ON skm_workspace.repositories USING btree (workspace_id, canonical_remote) WHERE (canonical_remote IS NOT NULL);

CREATE UNIQUE INDEX uq_repository_remotes__one_primary ON skm_workspace.repository_remotes USING btree (repository_id) WHERE is_primary;

CREATE TRIGGER tg_api_tokens__immutable BEFORE UPDATE ON skm_access.api_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_keep_issued_binding('name,expires_at,last_used_at,revoked_at,revoked_by,superseded_by');

CREATE TRIGGER tg_api_tokens__kind BEFORE INSERT ON skm_access.api_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_api_tokens__kind();

CREATE TRIGGER tg_api_tokens__notify AFTER INSERT OR UPDATE OF expires_at, revoked_at, superseded_by ON skm_access.api_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();

CREATE TRIGGER tg_memberships__notify AFTER INSERT OR DELETE OR UPDATE ON skm_access.memberships FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();

CREATE TRIGGER tg_memberships__worker_scope BEFORE INSERT OR UPDATE ON skm_access.memberships FOR EACH ROW EXECUTE FUNCTION skm_access.tg_memberships__worker_scope();

CREATE TRIGGER tg_pairing_tokens__immutable BEFORE UPDATE ON skm_access.pairing_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_keep_issued_binding('revoked_at,consumed_at,result_principal_id,result_token_id,result_worker_id');

CREATE TRIGGER tg_pairing_tokens__notify AFTER INSERT OR UPDATE OF revoked_at, consumed_at ON skm_access.pairing_tokens FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();

CREATE TRIGGER tg_principals__first_password BEFORE UPDATE OF password_hash ON skm_access.principals FOR EACH ROW EXECUTE FUNCTION skm_access.tg_principals__first_password();

CREATE TRIGGER tg_principals__notify AFTER UPDATE OF state, password_hash ON skm_access.principals FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();

CREATE TRIGGER tg_web_sessions__immutable BEFORE UPDATE ON skm_access.web_sessions FOR EACH ROW EXECUTE FUNCTION skm_access.tg_keep_issued_binding('revoked_at');

CREATE TRIGGER tg_web_sessions__notify AFTER INSERT OR UPDATE OF revoked_at ON skm_access.web_sessions FOR EACH ROW EXECUTE FUNCTION skm_access.tg_notify_access_changed();

CREATE TRIGGER tg_file_versions__immutable BEFORE DELETE OR UPDATE ON skm_artifacts.file_versions FOR EACH ROW EXECUTE FUNCTION skm_artifacts.tg_file_versions__immutable();

CREATE TRIGGER tg_entry_history__append_only BEFORE DELETE OR UPDATE ON skm_config.entry_history FOR EACH ROW EXECUTE FUNCTION skm_config.tg_entry_history__append_only();

CREATE TRIGGER tg_generation__no_delete BEFORE DELETE ON skm_config.generation FOR EACH ROW EXECUTE FUNCTION skm_config.tg_generation__no_delete();

CREATE TRIGGER tg_context_manifests__finalize_only BEFORE DELETE OR UPDATE ON skm_context.context_manifests FOR EACH ROW EXECUTE FUNCTION skm_context.tg_context_manifests__finalize_only();

CREATE TRIGGER tg_context_manifests__standalone_entity BEFORE INSERT ON skm_context.context_manifests FOR EACH ROW EXECUTE FUNCTION skm_context.check_standalone_entity();

CREATE TRIGGER tg_external_sources__append_only BEFORE DELETE OR UPDATE ON skm_context.external_sources FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_research_queries__append_only BEFORE DELETE OR UPDATE ON skm_context.research_queries FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_texts__append_only BEFORE DELETE OR UPDATE ON skm_context.texts FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_audit_records__append_only BEFORE DELETE OR UPDATE ON skm_core.audit_records FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_consumer_receipts__no_update BEFORE UPDATE ON skm_core.consumer_receipts FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_row_update();

CREATE TRIGGER tg_domain_events__append_only BEFORE DELETE OR UPDATE ON skm_core.domain_events FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_scopes__immutable BEFORE UPDATE ON skm_core.scopes FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TRIGGER tg_scopes__parent_kind BEFORE INSERT ON skm_core.scopes FOR EACH ROW EXECUTE FUNCTION skm_core.check_scope_parent();

CREATE TRIGGER tg_acceptance_decisions__append_only BEFORE DELETE OR UPDATE ON skm_execution.acceptance_decisions FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_assignment_leases__fence BEFORE INSERT OR UPDATE OF fencing_token, assignment_id ON skm_execution.assignment_leases FOR EACH ROW EXECUTE FUNCTION skm_execution.tg_assignment_leases__fence();

CREATE TRIGGER tg_assignments__reconcile_binding_immutable BEFORE UPDATE ON skm_execution.assignments FOR EACH ROW EXECUTE FUNCTION skm_execution.guard_assignment_reconcile_binding();

CREATE TRIGGER tg_attempt_file_bindings__append_only BEFORE DELETE OR UPDATE ON skm_execution.attempt_file_bindings FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_attempt_outputs__immutable BEFORE DELETE OR UPDATE ON skm_execution.attempt_outputs FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_attempt_steps__observation_immutable BEFORE UPDATE ON skm_execution.attempt_steps FOR EACH ROW EXECUTE FUNCTION skm_execution.guard_step_observation();

CREATE TRIGGER tg_check_evidence_bindings__append_only BEFORE DELETE OR UPDATE ON skm_execution.check_evidence_bindings FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_decision_answers__append_only BEFORE DELETE OR UPDATE ON skm_execution.decision_answers FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_decision_records__supersede_only BEFORE DELETE OR UPDATE ON skm_execution.decision_records FOR EACH ROW EXECUTE FUNCTION skm_execution.tg_decision_records__supersede_only();

CREATE TRIGGER tg_deviation_acceptances__append_only BEFORE DELETE OR UPDATE ON skm_execution.deviation_acceptances FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_execution_bundles__immutable BEFORE DELETE OR UPDATE ON skm_execution.execution_bundles FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_finding_resolutions__append_only BEFORE DELETE OR UPDATE ON skm_execution.finding_resolutions FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_fix_briefs__immutable BEFORE DELETE OR UPDATE ON skm_execution.fix_briefs FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_incident_gates__append_only BEFORE DELETE OR UPDATE ON skm_execution.incident_gates FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_manual_check_verdicts__append_only BEFORE DELETE OR UPDATE ON skm_execution.manual_check_verdicts FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_output_file_bindings__append_only BEFORE DELETE OR UPDATE ON skm_execution.output_file_bindings FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_readiness_reports__immutable BEFORE DELETE OR UPDATE ON skm_execution.readiness_reports FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_result_carry_forwards__append_only BEFORE DELETE OR UPDATE ON skm_execution.result_carry_forwards FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_review_evidence_bindings__append_only BEFORE DELETE OR UPDATE ON skm_execution.review_evidence_bindings FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_review_requests__immutable BEFORE DELETE OR UPDATE ON skm_execution.review_requests FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_revision_visas__immutable BEFORE DELETE OR UPDATE ON skm_execution.revision_visas FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_run_integration_hosts__append_only BEFORE DELETE OR UPDATE ON skm_execution.run_integration_hosts FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_run_reconfigurations__append_only BEFORE DELETE OR UPDATE ON skm_execution.run_reconfigurations FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_run_recoveries__frozen BEFORE DELETE OR UPDATE ON skm_execution.run_recoveries FOR EACH ROW EXECUTE FUNCTION skm_execution.tg_run_recoveries__frozen();

CREATE TRIGGER tg_run_task_edges__append_only BEFORE DELETE OR UPDATE ON skm_execution.run_task_edges FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_runs__binding BEFORE INSERT OR UPDATE OF id, kind, workspace_id, project_id, plan_id, inline_spec_file_version_id ON skm_execution.runs FOR EACH ROW EXECUTE FUNCTION skm_execution.check_run_binding();

CREATE TRIGGER tg_step_notes__append_only BEFORE DELETE OR UPDATE ON skm_execution.step_notes FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_step_tool_calls__append_only BEFORE DELETE OR UPDATE ON skm_execution.step_tool_calls FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_vault_note_writes__no_update BEFORE UPDATE ON skm_exports.vault_note_writes FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_row_update();

CREATE TRIGGER tg_pack_versions__state_only BEFORE DELETE OR UPDATE ON skm_extensions.pack_versions FOR EACH ROW EXECUTE FUNCTION skm_extensions.tg_pack_versions__state_only();

CREATE TRIGGER tg_packs__immutable BEFORE DELETE OR UPDATE ON skm_extensions.packs FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TRIGGER tg_resource_files__immutable BEFORE DELETE OR UPDATE ON skm_extensions.resource_files FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TRIGGER tg_resource_versions__immutable BEFORE DELETE OR UPDATE ON skm_extensions.resource_versions FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TRIGGER tg_resources__immutable BEFORE DELETE OR UPDATE ON skm_extensions.resources FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TRIGGER tg_activity_records__append_only BEFORE UPDATE ON skm_learning.activity_records FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_candidate_proposals__append_only BEFORE UPDATE ON skm_learning.candidate_proposals FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_candidate_reviews__append_only BEFORE UPDATE ON skm_learning.candidate_reviews FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_signals__append_only BEFORE UPDATE ON skm_learning.signals FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_acceptance_criteria__immutable BEFORE DELETE OR UPDATE ON skm_planning.acceptance_criteria FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_artifact_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.artifact_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_batch_members__immutable BEFORE DELETE OR UPDATE ON skm_planning.batch_members FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_batch_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.batch_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_check_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.check_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_criterion_check_bindings__immutable BEFORE DELETE OR UPDATE ON skm_planning.criterion_check_bindings FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_decision_bindings__immutable BEFORE DELETE OR UPDATE ON skm_planning.decision_bindings FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_decision_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.decision_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_decision_supersessions__immutable BEFORE DELETE OR UPDATE ON skm_planning.decision_supersessions FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_dependency_edges__immutable BEFORE DELETE OR UPDATE ON skm_planning.dependency_edges FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_design_brief_rag__immutable BEFORE DELETE OR UPDATE ON skm_planning.plan_design_brief_rag_bindings FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_design_brief_research__immutable BEFORE DELETE OR UPDATE ON skm_planning.plan_design_brief_research_references FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_entity_check_bindings__immutable BEFORE DELETE OR UPDATE ON skm_planning.entity_check_bindings FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_entity_path_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.entity_path_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_entity_read_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.entity_read_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_entity_relations__immutable BEFORE DELETE OR UPDATE ON skm_planning.entity_relations FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_entity_requirement_links__immutable BEFORE DELETE OR UPDATE ON skm_planning.entity_requirement_links FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_entity_skill_requirements__immutable BEFORE DELETE OR UPDATE ON skm_planning.entity_skill_requirements FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_item_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.item_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_material_bindings__immutable BEFORE DELETE OR UPDATE ON skm_planning.material_bindings FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE CONSTRAINT TRIGGER tg_material_specs__has_pin AFTER INSERT ON skm_planning.material_specs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_material_has_pin();

CREATE TRIGGER tg_material_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.material_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_phase_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.phase_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_plan_design_briefs__immutable BEFORE DELETE OR UPDATE ON skm_planning.plan_design_briefs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_plan_entity_identities__immutable BEFORE DELETE OR UPDATE ON skm_planning.plan_entity_identities FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_plan_relations__immutable BEFORE DELETE OR UPDATE ON skm_planning.plan_relations FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_plan_revisions__immutable BEFORE DELETE OR UPDATE ON skm_planning.plan_revisions FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_requirement_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.requirement_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_review_requirements__immutable BEFORE DELETE OR UPDATE ON skm_planning.review_requirements FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_revision_file_bindings__immutable BEFORE DELETE OR UPDATE ON skm_planning.revision_file_bindings FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_revision_members__immutable BEFORE DELETE OR UPDATE ON skm_planning.revision_members FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_revision_members__kind BEFORE INSERT ON skm_planning.revision_members FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_member_kind_matches_identity();

CREATE TRIGGER tg_revision_payloads__immutable BEFORE DELETE OR UPDATE ON skm_planning.revision_payloads FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_revision_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.revision_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_unit_specs__immutable BEFORE DELETE OR UPDATE ON skm_planning.unit_specs FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TRIGGER tg_approvals__append_only BEFORE DELETE OR UPDATE ON skm_policy.approvals FOR EACH ROW EXECUTE FUNCTION skm_policy.tg_approvals__append_only();

CREATE TRIGGER tg_capability_verifications__append_only BEFORE DELETE OR UPDATE ON skm_runtimes.capability_verifications FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- Preserve the reference schema's foreign-key creation order. PostgreSQL can report a different
-- constraint first when a write violates several foreign keys on the same relation.
ALTER TABLE ONLY skm_core.scopes
    ADD CONSTRAINT fk_scopes__parent FOREIGN KEY (parent_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_core.workspace_event_counters
    ADD CONSTRAINT fk_workspace_event_counters__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_core.domain_events
    ADD CONSTRAINT fk_domain_events__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_core.outbox
    ADD CONSTRAINT fk_outbox__domain_events FOREIGN KEY (event_id) REFERENCES skm_core.domain_events(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_core.consumer_receipts
    ADD CONSTRAINT fk_consumer_receipts__domain_events FOREIGN KEY (event_id) REFERENCES skm_core.domain_events(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_core.idempotency_receipts
    ADD CONSTRAINT fk_idempotency_receipts__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_core.audit_records
    ADD CONSTRAINT fk_audit_records__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_config.entries
    ADD CONSTRAINT fk_entries__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_config.entry_history
    ADD CONSTRAINT fk_entry_history__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.principals
    ADD CONSTRAINT fk_principals__created_by FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.principal_identities
    ADD CONSTRAINT fk_principal_identities__principals FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT fk_api_tokens__assignment_scope FOREIGN KEY (assignment_scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT fk_api_tokens__principals FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT fk_api_tokens__created_by FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT fk_api_tokens__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.api_tokens
    ADD CONSTRAINT fk_api_tokens__superseded_by FOREIGN KEY (superseded_by) REFERENCES skm_access.api_tokens(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY skm_access.memberships
    ADD CONSTRAINT fk_memberships__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.memberships
    ADD CONSTRAINT fk_memberships__principals FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.memberships
    ADD CONSTRAINT fk_memberships__granted_by FOREIGN KEY (granted_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.web_sessions
    ADD CONSTRAINT web_sessions_principal_id_fkey FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_issuer_id_fkey FOREIGN KEY (issuer_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_issuer_token_id_fkey FOREIGN KEY (issuer_token_id) REFERENCES skm_access.api_tokens(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_result_principal_id_fkey FOREIGN KEY (result_principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_access.pairing_tokens
    ADD CONSTRAINT pairing_tokens_result_token_id_fkey FOREIGN KEY (result_token_id) REFERENCES skm_access.api_tokens(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.workspaces
    ADD CONSTRAINT workspaces_id_fkey FOREIGN KEY (id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.projects
    ADD CONSTRAINT projects_id_fkey FOREIGN KEY (id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.projects
    ADD CONSTRAINT fk_projects__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.repositories
    ADD CONSTRAINT fk_repositories__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.repository_remotes
    ADD CONSTRAINT fk_repository_remotes__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_workspace.project_repositories
    ADD CONSTRAINT fk_project_repositories__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.project_repositories
    ADD CONSTRAINT fk_project_repositories__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.hosts
    ADD CONSTRAINT hosts_id_fkey FOREIGN KEY (id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.checkout_bindings
    ADD CONSTRAINT fk_checkout_bindings__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.checkout_bindings
    ADD CONSTRAINT fk_checkout_bindings__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.workers
    ADD CONSTRAINT fk_workers__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.workers
    ADD CONSTRAINT fk_workers__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_workspace.workers
    ADD CONSTRAINT fk_workers__principals FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plans
    ADD CONSTRAINT plans_id_fkey FOREIGN KEY (id) REFERENCES skm_core.scopes(id);

ALTER TABLE ONLY skm_planning.plans
    ADD CONSTRAINT fk_plans__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_design_briefs
    ADD CONSTRAINT fk_plan_design_briefs__plans FOREIGN KEY (workspace_id, plan_id) REFERENCES skm_planning.plans(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.project_plan_counters
    ADD CONSTRAINT fk_project_plan_counters__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_aliases
    ADD CONSTRAINT fk_plan_aliases__plans FOREIGN KEY (workspace_id, project_id, plan_id) REFERENCES skm_planning.plans(workspace_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_revisions
    ADD CONSTRAINT fk_plan_revisions__plans FOREIGN KEY (workspace_id, plan_id) REFERENCES skm_planning.plans(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_revisions
    ADD CONSTRAINT fk_plan_revisions__parent FOREIGN KEY (workspace_id, plan_id, parent_revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_revisions
    ADD CONSTRAINT fk_plan_revisions__restored_from FOREIGN KEY (workspace_id, plan_id, restored_from_revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plans
    ADD CONSTRAINT fk_plans__current_revision FOREIGN KEY (workspace_id, id, current_revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY skm_planning.revision_payloads
    ADD CONSTRAINT fk_revision_payloads__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_drafts
    ADD CONSTRAINT fk_plan_drafts__plans FOREIGN KEY (workspace_id, plan_id) REFERENCES skm_planning.plans(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_drafts
    ADD CONSTRAINT fk_plan_drafts__base_revision FOREIGN KEY (workspace_id, plan_id, base_revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_drafts
    ADD CONSTRAINT fk_plan_drafts__published_revision FOREIGN KEY (workspace_id, plan_id, published_revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_entity_identities
    ADD CONSTRAINT fk_plan_entity_identities__plans FOREIGN KEY (workspace_id, plan_id) REFERENCES skm_planning.plans(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_entity_identities
    ADD CONSTRAINT fk_plan_entity_identities__first_revision FOREIGN KEY (workspace_id, plan_id, first_revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.revision_members
    ADD CONSTRAINT fk_revision_members__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.revision_members
    ADD CONSTRAINT fk_revision_members__identities FOREIGN KEY (plan_id, entity_id) REFERENCES skm_planning.plan_entity_identities(plan_id, entity_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.revision_specs
    ADD CONSTRAINT fk_revision_specs__design_brief FOREIGN KEY (workspace_id, plan_id, design_brief_id) REFERENCES skm_planning.plan_design_briefs(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.revision_specs
    ADD CONSTRAINT fk_revision_specs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.phase_specs
    ADD CONSTRAINT fk_phase_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, phase_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.batch_specs
    ADD CONSTRAINT fk_batch_specs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.batch_specs
    ADD CONSTRAINT fk_batch_specs__phase FOREIGN KEY (revision_id, phase_id) REFERENCES skm_planning.phase_specs(revision_id, phase_id);

ALTER TABLE ONLY skm_planning.item_specs
    ADD CONSTRAINT fk_item_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, item_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.item_specs
    ADD CONSTRAINT fk_item_specs__phase FOREIGN KEY (revision_id, phase_id) REFERENCES skm_planning.phase_specs(revision_id, phase_id);

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT fk_unit_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, unit_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT fk_unit_specs__item FOREIGN KEY (revision_id, item_id) REFERENCES skm_planning.item_specs(revision_id, item_id);

ALTER TABLE ONLY skm_planning.unit_specs
    ADD CONSTRAINT fk_unit_specs__parent FOREIGN KEY (revision_id, item_id, parent_unit_id) REFERENCES skm_planning.unit_specs(revision_id, item_id, unit_id);

ALTER TABLE ONLY skm_planning.requirement_specs
    ADD CONSTRAINT fk_requirement_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, requirement_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.check_specs
    ADD CONSTRAINT fk_check_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, check_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.check_specs
    ADD CONSTRAINT fk_check_specs__owner FOREIGN KEY (workspace_id, plan_id, revision_id, owner_entity_id, owner_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.acceptance_criteria
    ADD CONSTRAINT fk_acceptance_criteria__member FOREIGN KEY (workspace_id, plan_id, revision_id, criterion_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.acceptance_criteria
    ADD CONSTRAINT fk_acceptance_criteria__owner FOREIGN KEY (workspace_id, plan_id, revision_id, owner_entity_id, owner_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.decision_specs
    ADD CONSTRAINT fk_decision_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, decision_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.decision_supersessions
    ADD CONSTRAINT fk_decision_supersessions__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.decision_supersessions
    ADD CONSTRAINT fk_decision_supersessions__decision FOREIGN KEY (revision_id, decision_id) REFERENCES skm_planning.decision_specs(revision_id, decision_id);

ALTER TABLE ONLY skm_planning.decision_supersessions
    ADD CONSTRAINT fk_decision_supersessions__superseded FOREIGN KEY (revision_id, superseded_decision_id) REFERENCES skm_planning.decision_specs(revision_id, decision_id);

ALTER TABLE ONLY skm_planning.decision_bindings
    ADD CONSTRAINT fk_decision_bindings__decision FOREIGN KEY (revision_id, decision_id) REFERENCES skm_planning.decision_specs(revision_id, decision_id);

ALTER TABLE ONLY skm_planning.decision_bindings
    ADD CONSTRAINT fk_decision_bindings__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.material_specs
    ADD CONSTRAINT fk_material_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, material_id, entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.material_bindings
    ADD CONSTRAINT fk_material_bindings__material FOREIGN KEY (revision_id, material_id) REFERENCES skm_planning.material_specs(revision_id, material_id);

ALTER TABLE ONLY skm_planning.material_bindings
    ADD CONSTRAINT fk_material_bindings__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_requirement_links
    ADD CONSTRAINT fk_entity_requirement_links__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_requirement_links
    ADD CONSTRAINT fk_entity_requirement_links__requirement FOREIGN KEY (revision_id, requirement_id) REFERENCES skm_planning.requirement_specs(revision_id, requirement_id);

ALTER TABLE ONLY skm_planning.dependency_edges
    ADD CONSTRAINT fk_dependency_edges__dependent FOREIGN KEY (workspace_id, plan_id, revision_id, dependent_entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.dependency_edges
    ADD CONSTRAINT fk_dependency_edges__prerequisite FOREIGN KEY (workspace_id, plan_id, revision_id, prerequisite_entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_relations
    ADD CONSTRAINT fk_entity_relations__source FOREIGN KEY (workspace_id, plan_id, revision_id, source_entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_relations
    ADD CONSTRAINT fk_entity_relations__target FOREIGN KEY (workspace_id, plan_id, revision_id, target_entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.batch_members
    ADD CONSTRAINT fk_batch_members__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.batch_members
    ADD CONSTRAINT fk_batch_members__batch FOREIGN KEY (revision_id, phase_id, batch_key) REFERENCES skm_planning.batch_specs(revision_id, phase_id, batch_key);

ALTER TABLE ONLY skm_planning.batch_members
    ADD CONSTRAINT fk_batch_members__item FOREIGN KEY (revision_id, item_id) REFERENCES skm_planning.item_specs(revision_id, item_id);

ALTER TABLE ONLY skm_planning.entity_check_bindings
    ADD CONSTRAINT fk_entity_check_bindings__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_check_bindings
    ADD CONSTRAINT fk_entity_check_bindings__check FOREIGN KEY (revision_id, check_id) REFERENCES skm_planning.check_specs(revision_id, check_id);

ALTER TABLE ONLY skm_planning.criterion_check_bindings
    ADD CONSTRAINT fk_criterion_check_bindings__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.criterion_check_bindings
    ADD CONSTRAINT fk_criterion_check_bindings__criterion FOREIGN KEY (revision_id, criterion_id) REFERENCES skm_planning.acceptance_criteria(revision_id, criterion_id);

ALTER TABLE ONLY skm_planning.criterion_check_bindings
    ADD CONSTRAINT fk_criterion_check_bindings__check FOREIGN KEY (revision_id, check_id) REFERENCES skm_planning.check_specs(revision_id, check_id);

ALTER TABLE ONLY skm_planning.review_requirements
    ADD CONSTRAINT fk_review_requirements__owner FOREIGN KEY (workspace_id, plan_id, revision_id, owner_entity_id, owner_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind);

ALTER TABLE ONLY skm_planning.entity_path_specs
    ADD CONSTRAINT fk_entity_path_specs__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.artifact_specs
    ADD CONSTRAINT fk_artifact_specs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.artifact_specs
    ADD CONSTRAINT fk_artifact_specs__item FOREIGN KEY (revision_id, item_id) REFERENCES skm_planning.item_specs(revision_id, item_id);

ALTER TABLE ONLY skm_planning.entity_read_specs
    ADD CONSTRAINT fk_entity_read_specs__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_read_specs
    ADD CONSTRAINT fk_entity_read_specs__material FOREIGN KEY (revision_id, material_id) REFERENCES skm_planning.material_specs(revision_id, material_id);

ALTER TABLE ONLY skm_planning.entity_read_specs
    ADD CONSTRAINT fk_entity_read_specs__target FOREIGN KEY (workspace_id, plan_id, revision_id, target_entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.entity_skill_requirements
    ADD CONSTRAINT fk_entity_skill_requirements__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id);

ALTER TABLE ONLY skm_planning.plan_relations
    ADD CONSTRAINT fk_plan_relations__revision FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id);

ALTER TABLE ONLY skm_planning.plan_relations
    ADD CONSTRAINT fk_plan_relations__target FOREIGN KEY (workspace_id, target_plan_id) REFERENCES skm_planning.plans(workspace_id, id);

ALTER TABLE ONLY skm_artifacts.staged_blobs
    ADD CONSTRAINT fk_staged_blobs__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.staged_blobs
    ADD CONSTRAINT fk_staged_blobs__storage_backends FOREIGN KEY (backend_id) REFERENCES skm_artifacts.storage_backends(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.staged_blobs
    ADD CONSTRAINT fk_staged_blobs__principals FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.blobs
    ADD CONSTRAINT fk_blobs__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.blob_locations
    ADD CONSTRAINT fk_blob_locations__blobs FOREIGN KEY (workspace_id, blob_id) REFERENCES skm_artifacts.blobs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.blob_locations
    ADD CONSTRAINT fk_blob_locations__storage_backends FOREIGN KEY (backend_id) REFERENCES skm_artifacts.storage_backends(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.files
    ADD CONSTRAINT fk_files__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.files
    ADD CONSTRAINT fk_files__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.files
    ADD CONSTRAINT fk_files__principals FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT fk_file_versions__files FOREIGN KEY (workspace_id, file_id) REFERENCES skm_artifacts.files(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT fk_file_versions__blobs FOREIGN KEY (workspace_id, blob_id) REFERENCES skm_artifacts.blobs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.file_versions
    ADD CONSTRAINT fk_file_versions__principals FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.files
    ADD CONSTRAINT fk_files__current_version FOREIGN KEY (workspace_id, id, current_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, file_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY skm_artifacts.access_grants
    ADD CONSTRAINT fk_access_grants__file_versions FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_artifacts.access_grants
    ADD CONSTRAINT fk_access_grants__principals FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.revision_file_bindings
    ADD CONSTRAINT fk_revision_file_bindings__material FOREIGN KEY (workspace_id, plan_id, revision_id, material_id) REFERENCES skm_planning.material_specs(workspace_id, plan_id, revision_id, material_id);

ALTER TABLE ONLY skm_planning.revision_file_bindings
    ADD CONSTRAINT fk_revision_file_bindings__file_version FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_design_brief_rag_bindings
    ADD CONSTRAINT fk_design_brief_rag__brief FOREIGN KEY (workspace_id, plan_id, design_brief_id) REFERENCES skm_planning.plan_design_briefs(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_design_brief_rag_bindings
    ADD CONSTRAINT fk_design_brief_rag__file_version FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_planning.plan_design_brief_research_references
    ADD CONSTRAINT fk_design_brief_research__brief FOREIGN KEY (workspace_id, plan_id, design_brief_id) REFERENCES skm_planning.plan_design_briefs(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_policy.tool_intents
    ADD CONSTRAINT fk_tool_intents__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_policy.tool_intents
    ADD CONSTRAINT fk_tool_intents__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_policy.tool_intents
    ADD CONSTRAINT fk_tool_intents__principals FOREIGN KEY (actor_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_policy.approvals
    ADD CONSTRAINT fk_approvals__tool_intents FOREIGN KEY (workspace_id, intent_id) REFERENCES skm_policy.tool_intents(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_policy.decision_audit
    ADD CONSTRAINT fk_decision_audit__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_policy.decision_audit
    ADD CONSTRAINT fk_decision_audit__principals FOREIGN KEY (principal_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.readiness_reports
    ADD CONSTRAINT fk_readiness_reports__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.readiness_reports
    ADD CONSTRAINT fk_readiness_reports__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.readiness_reports
    ADD CONSTRAINT fk_readiness_reports__supersedes FOREIGN KEY (workspace_id, plan_id, revision_id, supersedes_report_id) REFERENCES skm_execution.readiness_reports(workspace_id, plan_id, revision_id, id);

ALTER TABLE ONLY skm_execution.revision_visas
    ADD CONSTRAINT fk_revision_visas__readiness_report FOREIGN KEY (workspace_id, plan_id, revision_id, readiness_report_id) REFERENCES skm_execution.readiness_reports(workspace_id, plan_id, revision_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT fk_review_requests__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT fk_review_requests__project_repositories FOREIGN KEY (project_id, mount) REFERENCES skm_workspace.project_repositories(project_id, mount_name) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT fk_review_requests__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT fk_review_requests__file_versions FOREIGN KEY (workspace_id, patch_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT fk_review_requests__plans FOREIGN KEY (workspace_id, project_id, plan_id) REFERENCES skm_planning.plans(workspace_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_requests
    ADD CONSTRAINT fk_review_requests__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__scopes FOREIGN KEY (id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__plans FOREIGN KEY (workspace_id, project_id, plan_id) REFERENCES skm_planning.plans(workspace_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__inline_spec FOREIGN KEY (workspace_id, inline_spec_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__readiness_reports FOREIGN KEY (workspace_id, plan_id, revision_id, readiness_report_id) REFERENCES skm_execution.readiness_reports(workspace_id, plan_id, revision_id, id);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__audited_report FOREIGN KEY (workspace_id, plan_id, revision_id, audited_report_id) REFERENCES skm_execution.readiness_reports(workspace_id, plan_id, revision_id, id);

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__review_requests FOREIGN KEY (workspace_id, project_id, review_request_id) REFERENCES skm_execution.review_requests(workspace_id, project_id, id);

ALTER TABLE ONLY skm_execution.execution_bundles
    ADD CONSTRAINT fk_execution_bundles__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_reconfigurations
    ADD CONSTRAINT fk_run_reconfigurations__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__run_kind FOREIGN KEY (run_id, run_kind) REFERENCES skm_execution.runs(id, kind) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__runs_revision FOREIGN KEY (run_id, plan_id, revision_id) REFERENCES skm_execution.runs(id, plan_id, revision_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__revision_members FOREIGN KEY (workspace_id, plan_id, revision_id, spec_entity_id, spec_entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__hosts FOREIGN KEY (required_host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_task_edges
    ADD CONSTRAINT fk_run_task_edges__dependent FOREIGN KEY (run_id, dependent_task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_task_edges
    ADD CONSTRAINT fk_run_task_edges__prerequisite FOREIGN KEY (run_id, prerequisite_task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT fk_attempts__run_tasks FOREIGN KEY (run_id, task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT fk_attempts__workers FOREIGN KEY (workspace_id, worker_id) REFERENCES skm_workspace.workers(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT fk_attempts__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.execution_environments
    ADD CONSTRAINT fk_execution_environments__attempts FOREIGN KEY (workspace_id, attempt_id) REFERENCES skm_execution.attempts(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.execution_environments
    ADD CONSTRAINT fk_execution_environments__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.execution_environments
    ADD CONSTRAINT fk_execution_environments__file_versions FOREIGN KEY (workspace_id, dirty_patch_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT fk_attempts__execution_environments FOREIGN KEY (id, environment_id) REFERENCES skm_execution.execution_environments(attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_stages
    ADD CONSTRAINT fk_attempt_stages__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_stages
    ADD CONSTRAINT fk_attempt_stages__retry_of FOREIGN KEY (attempt_id, retry_of_id) REFERENCES skm_execution.attempt_stages(attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT fk_attempt_steps__attempt_stages FOREIGN KEY (attempt_id, stage_record_id) REFERENCES skm_execution.attempt_stages(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT fk_attempt_steps__parent FOREIGN KEY (attempt_id, parent_step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT fk_attempt_steps__raw_result FOREIGN KEY (workspace_id, raw_result_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT fk_attempt_steps__transcript FOREIGN KEY (workspace_id, transcript_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_stages
    ADD CONSTRAINT fk_attempt_stages__reused_from_step FOREIGN KEY (reused_from_step_id) REFERENCES skm_execution.attempt_steps(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT fk_assignments__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT fk_assignments__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT fk_assignments__hosts FOREIGN KEY (required_host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT fk_assignments__reap_stage FOREIGN KEY (attempt_id, reap_stage_record_id) REFERENCES skm_execution.attempt_stages(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT fk_assignments__reap_step FOREIGN KEY (attempt_id, reap_step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignment_leases
    ADD CONSTRAINT fk_assignment_leases__assignments FOREIGN KEY (assignment_id) REFERENCES skm_execution.assignments(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.assignment_leases
    ADD CONSTRAINT fk_assignment_leases__workers FOREIGN KEY (workspace_id, worker_id) REFERENCES skm_workspace.workers(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.step_notes
    ADD CONSTRAINT fk_step_notes__run FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id);

ALTER TABLE ONLY skm_execution.step_notes
    ADD CONSTRAINT fk_step_notes__attempt FOREIGN KEY (workspace_id, run_id, attempt_id) REFERENCES skm_execution.attempts(workspace_id, run_id, id);

ALTER TABLE ONLY skm_execution.step_notes
    ADD CONSTRAINT fk_step_notes__step FOREIGN KEY (attempt_id, step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id);

ALTER TABLE ONLY skm_execution.step_notes
    ADD CONSTRAINT fk_step_notes__assignment FOREIGN KEY (attempt_id, assignment_id) REFERENCES skm_execution.assignments(attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT fk_attempt_outputs__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT fk_attempt_outputs__attempt_steps FOREIGN KEY (attempt_id, produced_by_step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_outputs
    ADD CONSTRAINT fk_attempt_outputs__file_versions FOREIGN KEY (workspace_id, patch_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempts
    ADD CONSTRAINT fk_attempts__current_output FOREIGN KEY (id, current_output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__current_attempt FOREIGN KEY (id, current_attempt_id) REFERENCES skm_execution.attempts(task_id, id);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__accepted_attempt FOREIGN KEY (id, accepted_attempt_id) REFERENCES skm_execution.attempts(task_id, id);

ALTER TABLE ONLY skm_execution.run_tasks
    ADD CONSTRAINT fk_run_tasks__accepted_output FOREIGN KEY (accepted_attempt_id, accepted_output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id);

ALTER TABLE ONLY skm_execution.attempt_file_bindings
    ADD CONSTRAINT fk_attempt_file_bindings__attempts FOREIGN KEY (workspace_id, attempt_id) REFERENCES skm_execution.attempts(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_file_bindings
    ADD CONSTRAINT fk_attempt_file_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_file_bindings
    ADD CONSTRAINT fk_attempt_file_bindings__attempt_steps FOREIGN KEY (attempt_id, step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.output_file_bindings
    ADD CONSTRAINT fk_output_file_bindings__attempt_outputs FOREIGN KEY (attempt_id, output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.output_file_bindings
    ADD CONSTRAINT fk_output_file_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_recoveries
    ADD CONSTRAINT fk_run_recoveries__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_recoveries
    ADD CONSTRAINT fk_run_recoveries__attempt_stages FOREIGN KEY (attempt_id, stage_record_id) REFERENCES skm_execution.attempt_stages(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_recoveries
    ADD CONSTRAINT fk_run_recoveries__attempt_steps FOREIGN KEY (attempt_id, step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_recoveries
    ADD CONSTRAINT fk_run_recoveries__file_versions FOREIGN KEY (workspace_id, snapshot_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.incident_gates
    ADD CONSTRAINT incident_gates_task_id_fkey FOREIGN KEY (task_id) REFERENCES skm_execution.run_tasks(id);

ALTER TABLE ONLY skm_execution.incident_gates
    ADD CONSTRAINT incident_gates_stop_after_fkey FOREIGN KEY (stop_after) REFERENCES skm_execution.attempt_steps(id);

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT fk_check_executions__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT fk_check_executions__attempt_outputs FOREIGN KEY (attempt_id, output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT fk_check_executions__runs_revision FOREIGN KEY (run_id, revision_id) REFERENCES skm_execution.runs(id, revision_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT fk_check_executions__check_specs FOREIGN KEY (revision_id, check_spec_id) REFERENCES skm_planning.check_specs(revision_id, check_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.check_executions
    ADD CONSTRAINT fk_check_executions__reused_from FOREIGN KEY (workspace_id, reused_from_id) REFERENCES skm_execution.check_executions(workspace_id, id);

ALTER TABLE ONLY skm_execution.manual_check_verdicts
    ADD CONSTRAINT fk_manual_check_verdicts__check_executions FOREIGN KEY (workspace_id, check_execution_id) REFERENCES skm_execution.check_executions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.manual_check_verdicts
    ADD CONSTRAINT fk_manual_check_verdicts__supersedes FOREIGN KEY (check_execution_id, supersedes_id) REFERENCES skm_execution.manual_check_verdicts(check_execution_id, id);

ALTER TABLE ONLY skm_execution.check_evidence_bindings
    ADD CONSTRAINT fk_check_evidence_bindings__check_executions FOREIGN KEY (workspace_id, check_execution_id) REFERENCES skm_execution.check_executions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.check_evidence_bindings
    ADD CONSTRAINT fk_check_evidence_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT fk_reviews__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT fk_reviews__attempt_outputs FOREIGN KEY (attempt_id, output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT fk_reviews__base_output FOREIGN KEY (task_id, base_output_id) REFERENCES skm_execution.attempt_outputs(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT fk_reviews__attempt_steps FOREIGN KEY (attempt_id, step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_findings
    ADD CONSTRAINT fk_review_findings__reviews FOREIGN KEY (task_id, review_id) REFERENCES skm_execution.reviews(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_findings
    ADD CONSTRAINT fk_review_findings__first_seen FOREIGN KEY (task_id, first_seen_review_id) REFERENCES skm_execution.reviews(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.finding_resolutions
    ADD CONSTRAINT fk_finding_resolutions__review_findings FOREIGN KEY (task_id, finding_id) REFERENCES skm_execution.review_findings(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.finding_resolutions
    ADD CONSTRAINT fk_finding_resolutions__attempt_outputs FOREIGN KEY (task_id, target_output_id) REFERENCES skm_execution.attempt_outputs(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_evidence_bindings
    ADD CONSTRAINT fk_review_evidence_bindings__reviews FOREIGN KEY (workspace_id, review_id) REFERENCES skm_execution.reviews(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.review_evidence_bindings
    ADD CONSTRAINT fk_review_evidence_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.fix_briefs
    ADD CONSTRAINT fk_fix_briefs__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.fix_briefs
    ADD CONSTRAINT fk_fix_briefs__reviews FOREIGN KEY (task_id, source_review_id) REFERENCES skm_execution.reviews(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.fix_briefs
    ADD CONSTRAINT fk_fix_briefs__file_versions FOREIGN KEY (workspace_id, full_report_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.acceptance_decisions
    ADD CONSTRAINT fk_acceptance_decisions__run_tasks FOREIGN KEY (run_id, task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.acceptance_decisions
    ADD CONSTRAINT fk_acceptance_decisions__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.acceptance_decisions
    ADD CONSTRAINT fk_acceptance_decisions__attempt_outputs FOREIGN KEY (attempt_id, output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.deviation_acceptances
    ADD CONSTRAINT fk_deviation_acceptances__run_tasks FOREIGN KEY (run_id, task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.deviation_acceptances
    ADD CONSTRAINT fk_deviation_acceptances__runs_revision FOREIGN KEY (run_id, plan_id, revision_id) REFERENCES skm_execution.runs(id, plan_id, revision_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.deviation_acceptances
    ADD CONSTRAINT fk_deviation_acceptances__criterion FOREIGN KEY (workspace_id, plan_id, revision_id, criterion_id, criterion_entity_kind) REFERENCES skm_planning.revision_members(workspace_id, plan_id, revision_id, entity_id, entity_kind) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.deviation_acceptances
    ADD CONSTRAINT fk_deviation_acceptances__review_findings FOREIGN KEY (task_id, finding_id) REFERENCES skm_execution.review_findings(task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.budget_accounts
    ADD CONSTRAINT fk_budget_accounts__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.budget_accounts
    ADD CONSTRAINT fk_budget_accounts__run_tasks FOREIGN KEY (run_id, task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.budget_reservations
    ADD CONSTRAINT fk_budget_reservations__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.budget_reservations
    ADD CONSTRAINT fk_budget_reservations__attempt_steps FOREIGN KEY (attempt_id, step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_requests
    ADD CONSTRAINT fk_decision_requests__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_requests
    ADD CONSTRAINT fk_decision_requests__run_tasks FOREIGN KEY (run_id, task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_requests
    ADD CONSTRAINT fk_decision_requests__attempt_stages FOREIGN KEY (attempt_id, stage_record_id) REFERENCES skm_execution.attempt_stages(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_requests
    ADD CONSTRAINT fk_decision_requests__attempt_steps FOREIGN KEY (attempt_id, asked_by_step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_answers
    ADD CONSTRAINT fk_decision_answers__decision_requests FOREIGN KEY (workspace_id, request_id) REFERENCES skm_execution.decision_requests(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_answers
    ADD CONSTRAINT fk_decision_answers__attempt_steps FOREIGN KEY (answered_by_attempt_id, answered_by_step_id) REFERENCES skm_execution.attempt_steps(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_records
    ADD CONSTRAINT fk_decision_records__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_records
    ADD CONSTRAINT fk_decision_records__run_tasks FOREIGN KEY (run_id, task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.decision_records
    ADD CONSTRAINT fk_decision_records__decision_requests FOREIGN KEY (workspace_id, request_id) REFERENCES skm_execution.decision_requests(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.external_effects
    ADD CONSTRAINT fk_external_effects__attempts FOREIGN KEY (run_id, task_id, attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.external_effects
    ADD CONSTRAINT fk_external_effects__tool_intents FOREIGN KEY (workspace_id, intent_id) REFERENCES skm_policy.tool_intents(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.integration_slots
    ADD CONSTRAINT fk_integration_slots__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.integration_slots
    ADD CONSTRAINT fk_integration_slots__writer_host FOREIGN KEY (writer_host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.integration_slots
    ADD CONSTRAINT fk_integration_slots__attempts FOREIGN KEY (workspace_id, holder_attempt_id) REFERENCES skm_execution.attempts(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_integration_hosts
    ADD CONSTRAINT fk_run_integration_hosts__runs FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_integration_hosts
    ADD CONSTRAINT fk_run_integration_hosts__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.run_integration_hosts
    ADD CONSTRAINT fk_run_integration_hosts__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.result_carry_forwards
    ADD CONSTRAINT fk_result_carry_forwards__source_attempt FOREIGN KEY (source_run_id, source_task_id, source_attempt_id) REFERENCES skm_execution.attempts(run_id, task_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.result_carry_forwards
    ADD CONSTRAINT fk_result_carry_forwards__source_output FOREIGN KEY (source_attempt_id, source_output_id) REFERENCES skm_execution.attempt_outputs(attempt_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.result_carry_forwards
    ADD CONSTRAINT fk_result_carry_forwards__target_task FOREIGN KEY (target_run_id, target_task_id) REFERENCES skm_execution.run_tasks(run_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.result_carry_forwards
    ADD CONSTRAINT fk_result_carry_forwards__source_run FOREIGN KEY (workspace_id, source_run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.result_carry_forwards
    ADD CONSTRAINT fk_result_carry_forwards__target_run FOREIGN KEY (workspace_id, target_run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.autopilot_states
    ADD CONSTRAINT fk_autopilot_states__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.autopilot_states
    ADD CONSTRAINT fk_autopilot_states__runs FOREIGN KEY (workspace_id, current_run_id) REFERENCES skm_execution.runs(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_runtimes.host_runtimes
    ADD CONSTRAINT fk_host_runtimes__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_runtimes.capability_verifications
    ADD CONSTRAINT fk_capability_verifications__principals FOREIGN KEY (recorded_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_runtimes.provider_model_offerings
    ADD CONSTRAINT fk_provider_model_offerings__canonical_models FOREIGN KEY (model_id) REFERENCES skm_runtimes.canonical_models(model_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_runtimes.model_guidelines
    ADD CONSTRAINT fk_model_guidelines__provider_model_offerings FOREIGN KEY (runtime_id, model_id) REFERENCES skm_runtimes.provider_model_offerings(runtime_id, model_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_runtimes.worker_model_offer_snapshots
    ADD CONSTRAINT fk_worker_model_offer_snapshots__workers FOREIGN KEY (worker_id) REFERENCES skm_workspace.workers(id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_runtimes.host_model_availability
    ADD CONSTRAINT fk_host_model_availability__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_runtimes.host_model_availability
    ADD CONSTRAINT fk_host_model_availability__provider_model_offerings FOREIGN KEY (runtime_id, model_id) REFERENCES skm_runtimes.provider_model_offerings(runtime_id, model_id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.pack_versions
    ADD CONSTRAINT fk_pack_versions__packs FOREIGN KEY (pack_id) REFERENCES skm_extensions.packs(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.pack_versions
    ADD CONSTRAINT fk_pack_versions__principals FOREIGN KEY (installed_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resources
    ADD CONSTRAINT fk_resources__packs FOREIGN KEY (first_pack_id) REFERENCES skm_extensions.packs(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resource_versions
    ADD CONSTRAINT fk_resource_versions__resources FOREIGN KEY (resource_id) REFERENCES skm_extensions.resources(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resource_versions
    ADD CONSTRAINT fk_resource_versions__pack_versions FOREIGN KEY (pack_version_id) REFERENCES skm_extensions.pack_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resource_files
    ADD CONSTRAINT fk_resource_files__resource_versions FOREIGN KEY (resource_version_id) REFERENCES skm_extensions.resource_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resource_quarantine
    ADD CONSTRAINT fk_resource_quarantine__resource_versions FOREIGN KEY (resource_version_id) REFERENCES skm_extensions.resource_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resource_quarantine
    ADD CONSTRAINT fk_resource_quarantine__created_by FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_extensions.resource_quarantine
    ADD CONSTRAINT fk_resource_quarantine__released_by FOREIGN KEY (released_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.runs
    ADD CONSTRAINT fk_runs__resource_versions FOREIGN KEY (workflow_resource_version_id) REFERENCES skm_extensions.resource_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.reviews
    ADD CONSTRAINT fk_reviews__resource_versions FOREIGN KEY (profile_version_id) REFERENCES skm_extensions.resource_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_runtimes.model_guidelines
    ADD CONSTRAINT fk_model_guidelines__resource_versions FOREIGN KEY (resource_version_id) REFERENCES skm_extensions.resource_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT fk_context_manifests__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT fk_context_manifests__plans FOREIGN KEY (workspace_id, project_id, plan_id) REFERENCES skm_planning.plans(workspace_id, project_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT fk_context_manifests__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id) REFERENCES skm_planning.plan_revisions(workspace_id, plan_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT fk_context_manifests__resource_versions FOREIGN KEY (agent_profile_version_id) REFERENCES skm_extensions.resource_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.context_manifests
    ADD CONSTRAINT fk_context_manifests__file_versions FOREIGN KEY (workspace_id, prompt_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.context_blocks
    ADD CONSTRAINT fk_context_blocks__context_manifests FOREIGN KEY (manifest_id) REFERENCES skm_context.context_manifests(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.research_queries
    ADD CONSTRAINT fk_research_queries__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.research_queries
    ADD CONSTRAINT fk_research_queries__principals FOREIGN KEY (requested_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.external_sources
    ADD CONSTRAINT fk_external_sources__research_queries FOREIGN KEY (workspace_id, query_id) REFERENCES skm_context.research_queries(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.external_sources
    ADD CONSTRAINT fk_external_sources__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_context.external_sources
    ADD CONSTRAINT fk_external_sources__file_versions FOREIGN KEY (workspace_id, captured_file_version_id) REFERENCES skm_artifacts.file_versions(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.attempt_steps
    ADD CONSTRAINT fk_attempt_steps__context_manifests FOREIGN KEY (context_manifest_id) REFERENCES skm_context.context_manifests(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_integrations.projections
    ADD CONSTRAINT fk_projections__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_integrations.projections
    ADD CONSTRAINT fk_projections__checkout_bindings FOREIGN KEY (workspace_id, checkout_binding_id) REFERENCES skm_workspace.checkout_bindings(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_integrations.projection_files
    ADD CONSTRAINT fk_projection_files__projections FOREIGN KEY (projection_id) REFERENCES skm_integrations.projections(id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_integrations.projection_files
    ADD CONSTRAINT fk_projection_files__file_versions FOREIGN KEY (pre_image_file_version_id) REFERENCES skm_artifacts.file_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.memory_entries
    ADD CONSTRAINT fk_memory_entries__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.memory_entries
    ADD CONSTRAINT fk_memory_entries__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.memory_entries
    ADD CONSTRAINT fk_memory_entries__principals FOREIGN KEY (created_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.memory_entries
    ADD CONSTRAINT fk_memory_entries__supersedes FOREIGN KEY (supersedes_id) REFERENCES skm_knowledge.memory_entries(id) ON DELETE SET NULL;

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT fk_lessons__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT fk_lessons__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT fk_lessons__promoted_by FOREIGN KEY (promoted_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT fk_lessons__deprecated_by FOREIGN KEY (deprecated_by) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.lessons
    ADD CONSTRAINT fk_lessons__supersedes FOREIGN KEY (supersedes_id) REFERENCES skm_knowledge.lessons(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_indexes
    ADD CONSTRAINT fk_graph_indexes__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_indexes
    ADD CONSTRAINT fk_graph_indexes__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_indexes
    ADD CONSTRAINT fk_graph_indexes__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_nodes
    ADD CONSTRAINT fk_graph_nodes__workspaces FOREIGN KEY (workspace_id) REFERENCES skm_workspace.workspaces(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_nodes
    ADD CONSTRAINT fk_graph_nodes__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_nodes
    ADD CONSTRAINT fk_graph_nodes__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_knowledge.graph_edges
    ADD CONSTRAINT fk_graph_edges__src FOREIGN KEY (workspace_id, src_node_id) REFERENCES skm_knowledge.graph_nodes(workspace_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_knowledge.graph_edges
    ADD CONSTRAINT fk_graph_edges__dst FOREIGN KEY (workspace_id, dst_node_id) REFERENCES skm_knowledge.graph_nodes(workspace_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_knowledge.graph_edges
    ADD CONSTRAINT fk_graph_edges__repositories FOREIGN KEY (workspace_id, repository_id) REFERENCES skm_workspace.repositories(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.activity_records
    ADD CONSTRAINT fk_activity_records__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.activity_records
    ADD CONSTRAINT fk_activity_records__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT fk_candidates__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT fk_candidates__scopes FOREIGN KEY (scope_id) REFERENCES skm_core.scopes(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT fk_candidates__conflicts_with FOREIGN KEY (scope_id, conflicts_with_id) REFERENCES skm_learning.candidates(scope_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidates
    ADD CONSTRAINT fk_candidates__lessons FOREIGN KEY (lesson_id) REFERENCES skm_knowledge.lessons(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.signals
    ADD CONSTRAINT fk_signals__candidates FOREIGN KEY (candidate_id) REFERENCES skm_learning.candidates(id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_learning.signals
    ADD CONSTRAINT fk_signals__activity_records FOREIGN KEY (activity_record_id) REFERENCES skm_learning.activity_records(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidate_proposals
    ADD CONSTRAINT fk_candidate_proposals__target FOREIGN KEY (scope_id, candidate_id) REFERENCES skm_learning.candidates(scope_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_learning.candidate_proposals
    ADD CONSTRAINT fk_candidate_proposals__source FOREIGN KEY (scope_id, source_candidate_id) REFERENCES skm_learning.candidates(scope_id, id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_learning.candidate_proposals
    ADD CONSTRAINT fk_candidate_proposals__activity FOREIGN KEY (source_activity_id) REFERENCES skm_learning.activity_records(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidate_reviews
    ADD CONSTRAINT fk_candidate_reviews__candidates FOREIGN KEY (candidate_id) REFERENCES skm_learning.candidates(id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_learning.candidate_reviews
    ADD CONSTRAINT fk_candidate_reviews__proposals FOREIGN KEY (proposal_id) REFERENCES skm_learning.candidate_proposals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_learning.candidate_reviews
    ADD CONSTRAINT fk_candidate_reviews__principals FOREIGN KEY (reviewer_id) REFERENCES skm_access.principals(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_exports.vault_notes
    ADD CONSTRAINT fk_vault_notes__projects FOREIGN KEY (workspace_id, project_id) REFERENCES skm_workspace.projects(workspace_id, id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_exports.vault_notes
    ADD CONSTRAINT fk_vault_notes__domain_events FOREIGN KEY (event_id) REFERENCES skm_core.domain_events(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_exports.vault_note_writes
    ADD CONSTRAINT fk_vault_note_writes__vault_notes FOREIGN KEY (note_id) REFERENCES skm_exports.vault_notes(id) ON DELETE CASCADE;

ALTER TABLE ONLY skm_exports.vault_note_writes
    ADD CONSTRAINT fk_vault_note_writes__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts(id) ON DELETE RESTRICT;

ALTER TABLE ONLY skm_execution.step_tool_calls
    ADD CONSTRAINT step_tool_calls_step_id_fkey FOREIGN KEY (step_id) REFERENCES skm_execution.attempt_steps(id);

ALTER TABLE ONLY skm_execution.assignments
    ADD CONSTRAINT fk_assignments__reconcile_effect FOREIGN KEY (run_id, task_id, attempt_id, reconcile_effect_id) REFERENCES skm_execution.external_effects(run_id, task_id, attempt_id, id) ON DELETE RESTRICT;

GRANT USAGE ON SCHEMA skm_access TO skm_app;

GRANT USAGE ON SCHEMA skm_artifacts TO skm_app;

GRANT USAGE ON SCHEMA skm_config TO skm_app;

GRANT USAGE ON SCHEMA skm_context TO skm_app;

GRANT USAGE ON SCHEMA skm_core TO skm_app;

GRANT USAGE ON SCHEMA skm_execution TO skm_app;

GRANT USAGE ON SCHEMA skm_exports TO skm_app;

GRANT USAGE ON SCHEMA skm_extensions TO skm_app;

GRANT USAGE ON SCHEMA skm_integrations TO skm_app;

GRANT USAGE ON SCHEMA skm_knowledge TO skm_app;

GRANT USAGE ON SCHEMA skm_learning TO skm_app;

GRANT USAGE ON SCHEMA skm_planning TO skm_app;

GRANT USAGE ON SCHEMA skm_policy TO skm_app;

GRANT USAGE ON SCHEMA skm_runtimes TO skm_app;

GRANT USAGE ON SCHEMA skm_workspace TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_access.api_tokens TO skm_app;

GRANT UPDATE(name) ON TABLE skm_access.api_tokens TO skm_app;

GRANT UPDATE(expires_at) ON TABLE skm_access.api_tokens TO skm_app;

GRANT UPDATE(last_used_at) ON TABLE skm_access.api_tokens TO skm_app;

GRANT UPDATE(revoked_at) ON TABLE skm_access.api_tokens TO skm_app;

GRANT UPDATE(revoked_by) ON TABLE skm_access.api_tokens TO skm_app;

GRANT UPDATE(superseded_by) ON TABLE skm_access.api_tokens TO skm_app;

GRANT SELECT,INSERT,DELETE ON TABLE skm_access.memberships TO skm_app;

GRANT UPDATE(role) ON TABLE skm_access.memberships TO skm_app;

GRANT UPDATE(granted_by) ON TABLE skm_access.memberships TO skm_app;

GRANT UPDATE(granted_at) ON TABLE skm_access.memberships TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_access.pairing_tokens TO skm_app;

GRANT UPDATE(revoked_at) ON TABLE skm_access.pairing_tokens TO skm_app;

GRANT UPDATE(consumed_at) ON TABLE skm_access.pairing_tokens TO skm_app;

GRANT UPDATE(result_principal_id) ON TABLE skm_access.pairing_tokens TO skm_app;

GRANT UPDATE(result_token_id) ON TABLE skm_access.pairing_tokens TO skm_app;

GRANT UPDATE(result_worker_id) ON TABLE skm_access.pairing_tokens TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_access.principal_identities TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_access.principals TO skm_app;

GRANT UPDATE(display_name) ON TABLE skm_access.principals TO skm_app;

GRANT UPDATE(state) ON TABLE skm_access.principals TO skm_app;

GRANT UPDATE(row_version) ON TABLE skm_access.principals TO skm_app;

GRANT UPDATE(updated_at) ON TABLE skm_access.principals TO skm_app;

GRANT UPDATE(password_hash) ON TABLE skm_access.principals TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_access.web_sessions TO skm_app;

GRANT UPDATE(revoked_at) ON TABLE skm_access.web_sessions TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.access_grants TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.blob_locations TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.blobs TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.file_versions TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.files TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.staged_blobs TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_artifacts.storage_backends TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_config.entries TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_config.entry_history TO skm_app;

GRANT SELECT,UPDATE ON TABLE skm_config.generation TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_context.context_blocks TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_context.context_manifests TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_context.external_sources TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_context.research_queries TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_context.texts TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_core.audit_records TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_core.consumer_receipts TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_core.domain_events TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_core.event_streams TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_core.idempotency_receipts TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_core.outbox TO skm_app;

GRANT SELECT ON TABLE skm_core.schema_baseline TO skm_app;

GRANT SELECT ON TABLE skm_core.schema_migrations TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_core.scopes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_core.workspace_event_counters TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.acceptance_decisions TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.assignment_leases TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.assignments TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.attempt_file_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.attempt_outputs TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.attempt_stages TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.attempt_steps TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.attempts TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.autopilot_states TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.budget_accounts TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.budget_reservations TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.check_evidence_bindings TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.check_executions TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.decision_answers TO skm_app;

GRANT SELECT,INSERT,UPDATE ON TABLE skm_execution.decision_records TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.decision_requests TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.deviation_acceptances TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.execution_bundles TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.execution_environments TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.external_effects TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.finding_resolutions TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.fix_briefs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.incident_gates TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.integration_slots TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.manual_check_verdicts TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.output_file_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.readiness_reports TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.result_carry_forwards TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.review_evidence_bindings TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.review_findings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.review_requests TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.reviews TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.revision_visas TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.run_integration_hosts TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.run_reconfigurations TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.run_recoveries TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.run_task_edges TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.run_tasks TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_execution.runs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.step_notes TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_execution.step_tool_calls TO skm_app;

GRANT SELECT,INSERT,DELETE ON TABLE skm_exports.vault_note_writes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_exports.vault_notes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_extensions.pack_versions TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_extensions.packs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_extensions.resource_files TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_extensions.resource_quarantine TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_extensions.resource_versions TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_extensions.resources TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_integrations.projection_files TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_integrations.projections TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_knowledge.graph_edges TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_knowledge.graph_indexes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_knowledge.graph_nodes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_knowledge.lessons TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_knowledge.memory_entries TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_learning.activity_records TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_learning.candidate_proposals TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_learning.candidate_reviews TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_learning.candidates TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_learning.signals TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.acceptance_criteria TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.artifact_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.batch_members TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.batch_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.check_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.criterion_check_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.decision_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.decision_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.decision_supersessions TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.dependency_edges TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.entity_check_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.entity_path_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.entity_read_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.entity_relations TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.entity_requirement_links TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.entity_skill_requirements TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.item_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.material_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.material_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.phase_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_aliases TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_design_brief_rag_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_design_brief_research_references TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_design_briefs TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_planning.plan_drafts TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_entity_identities TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_relations TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.plan_revisions TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_planning.plans TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_planning.project_plan_counters TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.requirement_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.review_requirements TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.revision_file_bindings TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.revision_members TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.revision_payloads TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.revision_specs TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_planning.unit_specs TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_policy.approvals TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_policy.decision_audit TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_policy.tool_intents TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_runtimes.canonical_models TO skm_app;

GRANT SELECT,INSERT ON TABLE skm_runtimes.capability_verifications TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_runtimes.host_model_availability TO skm_app;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_runtimes.worker_model_offer_snapshots TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_runtimes.host_runtimes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_runtimes.model_guidelines TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_runtimes.provider_model_offerings TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.checkout_bindings TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.hosts TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.project_repositories TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.projects TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.repositories TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.repository_remotes TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.workers TO skm_app;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE skm_workspace.workspaces TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_access GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_artifacts GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_context GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_core GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_execution GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_exports GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_extensions GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_integrations GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_knowledge GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_learning GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_planning GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_policy GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_runtimes GRANT SELECT,INSERT ON TABLES TO skm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA skm_workspace GRANT SELECT,INSERT ON TABLES TO skm_app;

-- Initial values for the configuration generation and primary artifact backend.
INSERT INTO skm_config.generation (id, value) VALUES (1, 0);
INSERT INTO skm_artifacts.storage_backends (id, kind, config_ref)
VALUES ('local-primary', 'local', 'paths.blobs_root');
