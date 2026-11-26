-- 0010_artifacts_files_blobs: storage backends, staged uploads, content-addressed blobs and locations, files, immutable versions,
-- temporary access grants. Owner module: artifacts. FKs: skm_core, skm_access, skm_workspace (module graph).
CREATE SCHEMA IF NOT EXISTS skm_artifacts;

CREATE TABLE skm_artifacts.storage_backends (
    id          text        PRIMARY KEY,
    kind        text        NOT NULL,
    config_ref  text        NOT NULL,
    state       text        NOT NULL DEFAULT 'active',
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_storage_backends__id CHECK (id ~ '^[a-z][a-z0-9-]{1,31}$'),
    CONSTRAINT ck_storage_backends__kind CHECK (kind IN ('local', 's3')),
    CONSTRAINT ck_storage_backends__state CHECK (state IN ('active', 'readonly', 'retired'))
);
INSERT INTO skm_artifacts.storage_backends (id, kind, config_ref) VALUES ('local-primary', 'local', 'paths.blobs_root');

-- Bytes are already in their final immutable place; no DB reference exists yet (spec/modules/artifacts.md §1).
CREATE TABLE skm_artifacts.staged_blobs (
    id                   uuid        PRIMARY KEY,
    workspace_id         uuid        NOT NULL,
    content_digest       text        NOT NULL,
    size_bytes           bigint      NOT NULL,
    media_type           text        NOT NULL,
    detected_media_type  text        NOT NULL,
    backend_id           text        NOT NULL,
    storage_key          text        NOT NULL,
    created_by           uuid        NOT NULL,
    created_at           timestamptz NOT NULL,
    expires_at           timestamptz NOT NULL,
    consumed_at          timestamptz NULL,
    consumed_request_id  text        NULL,
    CONSTRAINT fk_staged_blobs__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_staged_blobs__storage_backends FOREIGN KEY (backend_id)
        REFERENCES skm_artifacts.storage_backends (id) ON DELETE RESTRICT,
    CONSTRAINT fk_staged_blobs__principals FOREIGN KEY (created_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_staged_blobs__digest CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_staged_blobs__size CHECK (size_bytes >= 0),
    CONSTRAINT ck_staged_blobs__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_staged_blobs__consumed CHECK ((consumed_at IS NULL) = (consumed_request_id IS NULL))
);
CREATE INDEX ix_staged_blobs__expires_at_unconsumed ON skm_artifacts.staged_blobs (expires_at) WHERE consumed_at IS NULL;
CREATE INDEX ix_staged_blobs__consumed_at ON skm_artifacts.staged_blobs (consumed_at) WHERE consumed_at IS NOT NULL;
CREATE INDEX ix_staged_blobs__backend_id_storage_key ON skm_artifacts.staged_blobs (backend_id, storage_key);

CREATE TABLE skm_artifacts.blobs (
    id                   uuid        PRIMARY KEY,
    workspace_id         uuid        NOT NULL,
    hash_algorithm       text        NOT NULL DEFAULT 'sha256',
    content_digest       text        NOT NULL,
    size_bytes           bigint      NOT NULL,
    detected_media_type  text        NOT NULL,
    availability         text        NOT NULL DEFAULT 'available',
    created_at           timestamptz NOT NULL,
    verified_at          timestamptz NULL,
    CONSTRAINT fk_blobs__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT uq_blobs__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_blobs__workspace_id_digest UNIQUE (workspace_id, hash_algorithm, content_digest, size_bytes),
    CONSTRAINT ck_blobs__algorithm CHECK (hash_algorithm = 'sha256'),
    CONSTRAINT ck_blobs__digest CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_blobs__size CHECK (size_bytes >= 0),
    CONSTRAINT ck_blobs__availability CHECK (availability IN ('available', 'missing'))
);

CREATE TABLE skm_artifacts.blob_locations (
    workspace_id     uuid        NOT NULL,
    blob_id          uuid        NOT NULL,
    backend_id       text        NOT NULL,
    storage_key      text        NOT NULL,
    storage_version  text        NULL,
    state            text        NOT NULL DEFAULT 'present',
    verified_at      timestamptz NULL,
    CONSTRAINT pk_blob_locations PRIMARY KEY (blob_id, backend_id),
    CONSTRAINT fk_blob_locations__blobs FOREIGN KEY (workspace_id, blob_id)
        REFERENCES skm_artifacts.blobs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_blob_locations__storage_backends FOREIGN KEY (backend_id)
        REFERENCES skm_artifacts.storage_backends (id) ON DELETE RESTRICT,
    CONSTRAINT uq_blob_locations__backend_id_storage_key UNIQUE (backend_id, storage_key),
    CONSTRAINT ck_blob_locations__state CHECK (state IN ('present', 'missing'))
);

CREATE TABLE skm_artifacts.files (
    id                  uuid        PRIMARY KEY,
    workspace_id        uuid        NOT NULL,
    project_id          uuid        NULL,
    title               text        NOT NULL,
    origin              text        NOT NULL,
    classification      text        NOT NULL,
    current_version_id  uuid        NULL,
    state               text        NOT NULL DEFAULT 'active',
    row_version         bigint      NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL,
    created_by          uuid        NOT NULL,
    updated_at          timestamptz NOT NULL,
    CONSTRAINT fk_files__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_files__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_files__principals FOREIGN KEY (created_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT uq_files__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_files__title CHECK (char_length(title) BETWEEN 1 AND 300),
    CONSTRAINT ck_files__origin CHECK (origin IN ('upload', 'evidence', 'transcript', 'patch', 'report', 'import', 'capture')),
    CONSTRAINT ck_files__classification CHECK (classification IN ('public', 'internal', 'confidential', 'restricted')),
    CONSTRAINT ck_files__state CHECK (state IN ('active', 'trashed'))
);
CREATE INDEX ix_files__workspace_id_project_id_created_at ON skm_artifacts.files (workspace_id, project_id, created_at DESC, id);

CREATE TABLE skm_artifacts.file_versions (
    id                   uuid        PRIMARY KEY,
    workspace_id         uuid        NOT NULL,
    file_id              uuid        NOT NULL,
    version_no           integer     NOT NULL,
    blob_id              uuid        NOT NULL,
    original_filename    text        NOT NULL,
    declared_media_type  text        NULL,
    description          text        NOT NULL DEFAULT '',
    source               jsonb       NOT NULL,
    safety               jsonb       NOT NULL,
    created_by           uuid        NOT NULL,
    created_at           timestamptz NOT NULL,
    CONSTRAINT fk_file_versions__files FOREIGN KEY (workspace_id, file_id)
        REFERENCES skm_artifacts.files (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_file_versions__blobs FOREIGN KEY (workspace_id, blob_id)
        REFERENCES skm_artifacts.blobs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_file_versions__principals FOREIGN KEY (created_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT uq_file_versions__file_id_version_no UNIQUE (file_id, version_no),
    CONSTRAINT uq_file_versions__workspace_id_file_id_id UNIQUE (workspace_id, file_id, id),
    CONSTRAINT uq_file_versions__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_file_versions__version_no CHECK (version_no >= 1),
    CONSTRAINT ck_file_versions__filename CHECK (
        octet_length(original_filename) BETWEEN 1 AND 255
        AND original_filename !~ '[/\\[:cntrl:]]'
        AND original_filename NOT IN ('.', '..')),  -- G21 basename rule (full rule incl. bidi controls: domain validate_filename)
    CONSTRAINT ck_file_versions__description CHECK (char_length(description) <= 2000),
    CONSTRAINT ck_file_versions__source_size CHECK (octet_length(source::text) < 4096),
    CONSTRAINT ck_file_versions__safety_size CHECK (octet_length(safety::text) < 65536)
);
CREATE INDEX ix_file_versions__blob_id ON skm_artifacts.file_versions (blob_id);

-- current_version_id must point to a version of the same file (composite, deferred: file -> version -> update current)
ALTER TABLE skm_artifacts.files
    ADD CONSTRAINT fk_files__current_version FOREIGN KEY (workspace_id, id, current_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, file_id, id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION skm_artifacts.tg_file_versions__immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'file versions are immutable' USING ERRCODE = 'restrict_violation';
END $$;
CREATE TRIGGER tg_file_versions__immutable BEFORE UPDATE OR DELETE ON skm_artifacts.file_versions
    FOR EACH ROW EXECUTE FUNCTION skm_artifacts.tg_file_versions__immutable();

CREATE TABLE skm_artifacts.access_grants (
    id               uuid        PRIMARY KEY,
    workspace_id     uuid        NOT NULL,
    principal_id     uuid        NOT NULL,
    file_version_id  uuid        NOT NULL,
    reason           text        NOT NULL,
    ref              text        NOT NULL,
    expires_at       timestamptz NOT NULL,
    created_at       timestamptz NOT NULL,
    revoked_at       timestamptz NULL,
    CONSTRAINT fk_access_grants__file_versions FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_access_grants__principals FOREIGN KEY (principal_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_access_grants__reason CHECK (reason IN ('assignment', 'share')),
    CONSTRAINT ck_access_grants__ref CHECK (char_length(ref) BETWEEN 1 AND 200),
    CONSTRAINT ck_access_grants__expiry CHECK (expires_at > created_at)
);
CREATE INDEX ix_access_grants__principal_id_file_version_id_active
    ON skm_artifacts.access_grants (principal_id, file_version_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_access_grants__reason_ref_active ON skm_artifacts.access_grants (reason, ref) WHERE revoked_at IS NULL;

SELECT skm_core.grant_app('skm_artifacts', '{}'::text[]);
