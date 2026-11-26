-- 0018_extensions_resources: resource packs, their immutable versions, resources, resource versions with file bodies, quarantine.
-- Owner module: extensions (spec/modules/extensions.md §11). FKs: skm_access (module graph: extensions -> access).
-- Packs are instance-level (no workspace_id): resolution per scope is done by config (extensions.packs.*), not by rows.
CREATE SCHEMA IF NOT EXISTS skm_extensions;

-- Rows of pack_versions are immutable except the state column (active -> retired, soft uninstall).
CREATE FUNCTION skm_extensions.tg_pack_versions__state_only() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TABLE skm_extensions.packs (
    id          uuid        PRIMARY KEY,
    slug        text        NOT NULL,
    title       text        NOT NULL,
    publisher   text        NOT NULL,
    trust       text        NOT NULL,
    created_at  timestamptz NOT NULL,
    CONSTRAINT uq_packs__slug UNIQUE (slug),
    CONSTRAINT ck_packs__slug CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    CONSTRAINT ck_packs__title CHECK (char_length(title) BETWEEN 1 AND 120),
    CONSTRAINT ck_packs__publisher CHECK (publisher ~ '^[a-z0-9][a-z0-9.-]{0,62}$'),
    CONSTRAINT ck_packs__trust CHECK (trust IN ('builtin', 'operator', 'third_party'))
);
-- slug and trust never change between versions (domain rule trust_changed); the row itself is immutable
CREATE TRIGGER tg_packs__immutable BEFORE UPDATE OR DELETE ON skm_extensions.packs
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TABLE skm_extensions.pack_versions (
    id             uuid        PRIMARY KEY,
    pack_id        uuid        NOT NULL,
    version        text        NOT NULL,
    version_major  integer     NOT NULL,
    version_minor  integer     NOT NULL,
    version_patch  integer     NOT NULL,
    prerelease     text        NULL,
    digest         text        NOT NULL,
    manifest       jsonb       NOT NULL,
    priority       integer     NOT NULL,
    state          text        NOT NULL DEFAULT 'active',
    origin         text        NOT NULL,
    installed_at   timestamptz NOT NULL,
    installed_by   uuid        NOT NULL,
    CONSTRAINT fk_pack_versions__packs FOREIGN KEY (pack_id) REFERENCES skm_extensions.packs (id) ON DELETE RESTRICT,
    CONSTRAINT fk_pack_versions__principals FOREIGN KEY (installed_by) REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT uq_pack_versions__pack_id_version UNIQUE (pack_id, version),
    CONSTRAINT ck_pack_versions__version CHECK (
        version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'),
    CONSTRAINT ck_pack_versions__version_parts CHECK (
        version_major >= 0 AND version_minor >= 0 AND version_patch >= 0
        AND version = version_major || '.' || version_minor || '.' || version_patch || coalesce('-' || prerelease, '')),
    CONSTRAINT ck_pack_versions__digest CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_pack_versions__priority CHECK (priority BETWEEN -1000 AND 1000),
    CONSTRAINT ck_pack_versions__state CHECK (state IN ('active', 'retired')),
    CONSTRAINT ck_pack_versions__origin CHECK (
        origin IN ('builtin', 'runtime_catalog_snapshot') OR origin ~ '^(path|archive):.{1,200}$')
);
CREATE INDEX ix_pack_versions__pack_id_semver ON skm_extensions.pack_versions
    (pack_id, version_major DESC, version_minor DESC, version_patch DESC, (prerelease IS NULL) DESC, prerelease DESC);
CREATE TRIGGER tg_pack_versions__state_only BEFORE UPDATE OR DELETE ON skm_extensions.pack_versions
    FOR EACH ROW EXECUTE FUNCTION skm_extensions.tg_pack_versions__state_only();

CREATE TABLE skm_extensions.resources (
    id             uuid        PRIMARY KEY,
    kind           text        NOT NULL,
    key            text        NOT NULL,
    first_pack_id  uuid        NOT NULL,
    created_at     timestamptz NOT NULL,
    CONSTRAINT fk_resources__packs FOREIGN KEY (first_pack_id) REFERENCES skm_extensions.packs (id) ON DELETE RESTRICT,
    CONSTRAINT uq_resources__kind_key UNIQUE (kind, key),
    CONSTRAINT ck_resources__kind CHECK (kind IN ('skill', 'steering', 'agent_profile', 'workflow', 'plan_template',
        'prompt_block', 'integration_bundle', 'runtime_catalog', 'model_guideline')),
    CONSTRAINT ck_resources__key CHECK (
        (kind = 'prompt_block' AND key ~ '^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9_-]*$')
        OR (kind <> 'prompt_block' AND key ~ '^[a-z0-9][a-z0-9-]{1,80}$'))
);
CREATE TRIGGER tg_resources__immutable BEFORE UPDATE OR DELETE ON skm_extensions.resources
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

CREATE TABLE skm_extensions.resource_versions (
    id               uuid        PRIMARY KEY,
    resource_id      uuid        NOT NULL,
    pack_version_id  uuid        NOT NULL,
    version          text        NOT NULL,
    digest           text        NOT NULL,
    manifest         jsonb       NOT NULL,
    tokens_estimate  integer     NOT NULL,
    compat_verdict   text        NOT NULL,
    compat_report    jsonb       NOT NULL,
    created_at       timestamptz NOT NULL,
    CONSTRAINT fk_resource_versions__resources FOREIGN KEY (resource_id) REFERENCES skm_extensions.resources (id) ON DELETE RESTRICT,
    CONSTRAINT fk_resource_versions__pack_versions FOREIGN KEY (pack_version_id)
        REFERENCES skm_extensions.pack_versions (id) ON DELETE RESTRICT,
    CONSTRAINT uq_resource_versions__resource_id_pack_version_id UNIQUE (resource_id, pack_version_id),
    CONSTRAINT ck_resource_versions__version CHECK (
        version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'),
    CONSTRAINT ck_resource_versions__digest CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_resource_versions__tokens CHECK (tokens_estimate >= 0),
    CONSTRAINT ck_resource_versions__compat_verdict CHECK (compat_verdict IN ('clean', 'quarantine'))
);
-- not unique: the same content may arrive in two versions of a pack
CREATE INDEX ix_resource_versions__resource_id_digest ON skm_extensions.resource_versions (resource_id, digest);
CREATE INDEX ix_resource_versions__pack_version_id ON skm_extensions.resource_versions (pack_version_id);
CREATE TRIGGER tg_resource_versions__immutable BEFORE UPDATE OR DELETE ON skm_extensions.resource_versions
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

-- File bodies of resource versions. Not in skm_artifacts: blobs there are workspace-scoped, packs are instance-level.
CREATE TABLE skm_extensions.resource_files (
    resource_version_id  uuid    NOT NULL,
    path                 text    NOT NULL,
    size_bytes           integer NOT NULL,
    digest               text    NOT NULL,
    media_type           text    NOT NULL,
    content              bytea   NOT NULL,
    CONSTRAINT pk_resource_files PRIMARY KEY (resource_version_id, path),
    CONSTRAINT fk_resource_files__resource_versions FOREIGN KEY (resource_version_id)
        REFERENCES skm_extensions.resource_versions (id) ON DELETE RESTRICT,
    CONSTRAINT ck_resource_files__path CHECK (
        path !~ '^/' AND path !~ '(^|/)\.\.(/|$)' AND path !~ '\\' AND char_length(path) BETWEEN 1 AND 300),
    CONSTRAINT ck_resource_files__size CHECK (size_bytes BETWEEN 0 AND 1048576 AND size_bytes = octet_length(content)),
    CONSTRAINT ck_resource_files__digest CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_resource_files__media_type CHECK (char_length(media_type) BETWEEN 1 AND 100)
);
CREATE TRIGGER tg_resource_files__immutable BEFORE UPDATE OR DELETE ON skm_extensions.resource_files
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

-- Quarantine history: one active (not released) row per resource version; release keeps the row.
CREATE TABLE skm_extensions.resource_quarantine (
    id                   uuid        PRIMARY KEY,
    resource_version_id  uuid        NOT NULL,
    reason_kind          text        NOT NULL,
    reasons              jsonb       NOT NULL,
    report               jsonb       NULL,
    created_by           uuid        NOT NULL,
    created_at           timestamptz NOT NULL,
    released_by          uuid        NULL,
    released_at          timestamptz NULL,
    release_reason       text        NULL,
    CONSTRAINT fk_resource_quarantine__resource_versions FOREIGN KEY (resource_version_id)
        REFERENCES skm_extensions.resource_versions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_resource_quarantine__created_by FOREIGN KEY (created_by) REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_resource_quarantine__released_by FOREIGN KEY (released_by) REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_resource_quarantine__reason_kind CHECK (reason_kind IN ('compat', 'manual')),
    CONSTRAINT ck_resource_quarantine__reasons CHECK (jsonb_typeof(reasons) = 'array' AND jsonb_array_length(reasons) >= 1),
    CONSTRAINT ck_resource_quarantine__released CHECK (
        (released_at IS NULL) = (released_by IS NULL) AND (released_at IS NULL) = (release_reason IS NULL)),
    CONSTRAINT ck_resource_quarantine__release_reason CHECK (release_reason IS NULL OR char_length(release_reason) BETWEEN 1 AND 1000)
);
CREATE UNIQUE INDEX uq_resource_quarantine__resource_version_id_active
    ON skm_extensions.resource_quarantine (resource_version_id) WHERE released_at IS NULL;

-- ---------------------------------------------------------------- deferred FKs of skm_execution
-- skm_execution (0013, 0015) is created before this schema; its columns referencing resource versions are plain uuid
-- there. skm_execution depends on extensions (spec/modules/execution.md §2), so the FKs go down the module graph.
-- NOT VALID + VALIDATE keeps the ACCESS EXCLUSIVE lock short on a database that already holds P07 rows.
ALTER TABLE skm_execution.runs
    ADD CONSTRAINT fk_runs__resource_versions FOREIGN KEY (workflow_resource_version_id)
    REFERENCES skm_extensions.resource_versions (id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE skm_execution.runs VALIDATE CONSTRAINT fk_runs__resource_versions;

ALTER TABLE skm_execution.reviews
    ADD CONSTRAINT fk_reviews__resource_versions FOREIGN KEY (profile_version_id)
    REFERENCES skm_extensions.resource_versions (id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE skm_execution.reviews VALIDATE CONSTRAINT fk_reviews__resource_versions;

SELECT skm_core.grant_app('skm_extensions', ARRAY['packs','resource_files','resource_versions','resources']::text[]);

-- Deferred provenance FK for skm_runtimes (0017), which depends on extensions.
ALTER TABLE skm_runtimes.model_guidelines
    ADD CONSTRAINT fk_model_guidelines__resource_versions FOREIGN KEY (resource_version_id)
    REFERENCES skm_extensions.resource_versions (id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE skm_runtimes.model_guidelines VALIDATE CONSTRAINT fk_model_guidelines__resource_versions;
