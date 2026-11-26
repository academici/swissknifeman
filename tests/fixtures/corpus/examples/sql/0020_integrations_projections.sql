-- 0020_integrations_projections: client-integration projections (one per project × checkout binding × target) and the files
-- a host applied for them. Plans are computed on the host and never stored (spec/modules/integrations.md §4.9).
-- Hook subscriptions own no tables: definitions live in skm_config.entries, deliveries in skm_core.outbox (§11).
-- Owner module: integrations. FKs: skm_workspace (projects, checkout_bindings), skm_artifacts (pre-images).
CREATE SCHEMA IF NOT EXISTS skm_integrations;

CREATE TABLE skm_integrations.projections (
    id                      uuid        PRIMARY KEY,
    workspace_id            uuid        NOT NULL,
    project_id              uuid        NOT NULL,
    checkout_binding_id     uuid        NOT NULL,
    target                  text        NOT NULL,
    state                   text        NOT NULL DEFAULT 'pending',
    desired_digest          text        NULL,
    applied_desired_digest  text        NULL,
    renderer_version        text        NULL,
    applied_at              timestamptz NULL,
    drift_checked_at        timestamptz NULL,
    row_version             bigint      NOT NULL DEFAULT 1,
    created_at              timestamptz NOT NULL,
    updated_at              timestamptz NOT NULL,
    CONSTRAINT fk_projections__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_projections__checkout_bindings FOREIGN KEY (workspace_id, checkout_binding_id)
        REFERENCES skm_workspace.checkout_bindings (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_projections__checkout_binding_id_target UNIQUE (checkout_binding_id, target),
    CONSTRAINT ck_projections__target CHECK (target ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_projections__state CHECK (state IN ('pending', 'in_sync', 'drifted', 'failed', 'removed')),
    CONSTRAINT ck_projections__desired_digest CHECK (desired_digest IS NULL OR desired_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_projections__applied_desired_digest CHECK (
        applied_desired_digest IS NULL OR applied_desired_digest ~ '^sha256:[0-9a-f]{64}$'),
    -- in_sync means the last apply wrote the whole desired state (spec §4.9 ProjectionState.IN_SYNC)
    CONSTRAINT ck_projections__in_sync CHECK (
        state <> 'in_sync' OR (applied_desired_digest IS NOT NULL AND applied_desired_digest = desired_digest)),
    CONSTRAINT ck_projections__renderer_version CHECK (
        renderer_version IS NULL OR renderer_version ~ '^[a-z][a-z0-9_]{1,31}@[0-9]+$'),
    CONSTRAINT ck_projections__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_projections__project_id_updated_at_id ON skm_integrations.projections (project_id, updated_at, id);
CREATE INDEX ix_projections__project_id_state ON skm_integrations.projections (project_id, state);

CREATE TABLE skm_integrations.projection_files (
    projection_id              uuid        NOT NULL,
    relative_path              text        NOT NULL,
    surface                    text        NOT NULL,
    ownership                  text        NOT NULL,
    block_ids                  text[]      NOT NULL DEFAULT '{}',
    -- [{"path": ["permissions", "allow"], "mode": "replace" | "list_union_tagged"}]; shape: urn:skm:integrations:defs:v1#/$defs/owned_key_path
    owned_keys                 jsonb       NOT NULL DEFAULT '[]'::jsonb,
    applied_managed_digest     text        NOT NULL,
    applied_whole_digest       text        NOT NULL,
    pre_image_file_version_id  uuid        NULL,
    renderer                   text        NOT NULL,
    applied_at                 timestamptz NOT NULL,
    CONSTRAINT pk_projection_files PRIMARY KEY (projection_id, relative_path),
    CONSTRAINT fk_projection_files__projections FOREIGN KEY (projection_id)
        REFERENCES skm_integrations.projections (id) ON DELETE CASCADE,
    CONSTRAINT fk_projection_files__file_versions FOREIGN KEY (pre_image_file_version_id)
        REFERENCES skm_artifacts.file_versions (id) ON DELETE RESTRICT,
    CONSTRAINT ck_projection_files__relative_path CHECK (
        char_length(relative_path) BETWEEN 1 AND 1024
        AND relative_path !~ '(^/|^[A-Za-z]:|\\|(^|/)\.\.?(/|$))'
        AND position(E'\n' in relative_path) = 0),
    CONSTRAINT ck_projection_files__surface CHECK (
        surface IN ('instructions', 'skills', 'permissions', 'hooks', 'mcp', 'agents')),
    CONSTRAINT ck_projection_files__ownership CHECK (
        ownership IN ('managed_file', 'managed_block', 'merged_json', 'merged_toml')),
    CONSTRAINT ck_projection_files__boundary CHECK (
        (ownership = 'managed_block' AND cardinality(block_ids) >= 1 AND owned_keys = '[]'::jsonb)
        OR (ownership IN ('merged_json', 'merged_toml') AND cardinality(block_ids) = 0
            AND jsonb_typeof(owned_keys) = 'array' AND jsonb_array_length(owned_keys) >= 1)
        OR (ownership = 'managed_file' AND cardinality(block_ids) = 0 AND owned_keys = '[]'::jsonb)),
    CONSTRAINT ck_projection_files__applied_managed_digest CHECK (applied_managed_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_projection_files__applied_whole_digest CHECK (applied_whole_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_projection_files__renderer CHECK (renderer ~ '^[a-z][a-z0-9_]{1,31}\.[a-z_]{1,32}@[0-9]+$')
);
-- managed_file_paths(project, target) for pack_guard (spec §6.1)
CREATE INDEX ix_projection_files__projection_id_ownership ON skm_integrations.projection_files (projection_id, ownership);

SELECT skm_core.grant_app('skm_integrations', '{}'::text[]);
