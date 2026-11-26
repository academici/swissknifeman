-- 0007_workspace_core: workspaces, projects, repositories, remotes, mounts, hosts, checkout bindings, workers.
-- Owner module: workspace. FKs: skm_core (scopes), skm_access (principals) — allowed by the module graph.
CREATE SCHEMA IF NOT EXISTS skm_workspace;

CREATE TABLE skm_workspace.workspaces (
    id            uuid        PRIMARY KEY REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    slug          text        NOT NULL,
    title         text        NOT NULL,
    state         text        NOT NULL DEFAULT 'active',
    row_version   bigint      NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL,
    updated_at    timestamptz NOT NULL,
    CONSTRAINT uq_workspaces__slug UNIQUE (slug),
    CONSTRAINT ck_workspaces__state CHECK (state IN ('active', 'suspended', 'archived')),
    CONSTRAINT ck_workspaces__slug CHECK (slug ~ '^[a-z0-9]([a-z0-9]|-(?=[a-z0-9])){1,62}$'),
    CONSTRAINT ck_workspaces__title CHECK (char_length(title) BETWEEN 1 AND 200)
);

CREATE TABLE skm_workspace.projects (
    id            uuid        PRIMARY KEY REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    workspace_id  uuid        NOT NULL,
    slug          text        NOT NULL,
    title         text        NOT NULL,
    description   text        NOT NULL DEFAULT '',
    state         text        NOT NULL DEFAULT 'active',
    row_version   bigint      NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL,
    updated_at    timestamptz NOT NULL,
    CONSTRAINT fk_projects__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT uq_projects__workspace_id_slug UNIQUE (workspace_id, slug),
    CONSTRAINT uq_projects__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_projects__state CHECK (state IN ('active', 'archived')),
    CONSTRAINT ck_projects__slug CHECK (slug ~ '^[a-z0-9]([a-z0-9]|-(?=[a-z0-9])){1,62}$'),
    CONSTRAINT ck_projects__title CHECK (char_length(title) BETWEEN 1 AND 200),
    CONSTRAINT ck_projects__description CHECK (char_length(description) <= 4000)
);
CREATE INDEX ix_projects__workspace_id_state ON skm_workspace.projects (workspace_id, state);

CREATE TABLE skm_workspace.repositories (
    id               uuid        PRIMARY KEY,
    workspace_id     uuid        NOT NULL,
    title            text        NOT NULL,
    canonical_remote text        NULL,
    provider         text        NOT NULL,
    external_id      text        NULL,
    row_version      bigint      NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL,
    CONSTRAINT fk_repositories__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT uq_repositories__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_repositories__provider CHECK (provider IN ('github', 'gitlab', 'bitbucket', 'gitea', 'other', 'none')),
    CONSTRAINT ck_repositories__provider_none CHECK ((canonical_remote IS NULL) = (provider = 'none')),
    CONSTRAINT ck_repositories__title CHECK (char_length(title) BETWEEN 1 AND 200)
);
CREATE UNIQUE INDEX uq_repositories__workspace_id_canonical_remote
    ON skm_workspace.repositories (workspace_id, canonical_remote) WHERE canonical_remote IS NOT NULL;

CREATE TABLE skm_workspace.repository_remotes (
    workspace_id   uuid        NOT NULL,
    repository_id  uuid        NOT NULL,
    normalized_url text        NOT NULL,
    display_url    text        NOT NULL,
    is_primary     boolean     NOT NULL DEFAULT false,
    added_at       timestamptz NOT NULL,
    CONSTRAINT pk_repository_remotes PRIMARY KEY (repository_id, normalized_url),
    CONSTRAINT fk_repository_remotes__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE CASCADE,
    CONSTRAINT uq_repository_remotes__workspace_id_normalized_url UNIQUE (workspace_id, normalized_url),
    CONSTRAINT ck_repository_remotes__normalized CHECK (normalized_url ~ '^[^/\s]+/[^\s]+$')
);
CREATE UNIQUE INDEX uq_repository_remotes__one_primary
    ON skm_workspace.repository_remotes (repository_id) WHERE is_primary;

CREATE TABLE skm_workspace.project_repositories (
    workspace_id   uuid        NOT NULL,
    project_id     uuid        NOT NULL,
    repository_id  uuid        NOT NULL,
    mount_name     text        NOT NULL,
    role           text        NOT NULL,
    attached_at    timestamptz NOT NULL,
    CONSTRAINT pk_project_repositories PRIMARY KEY (project_id, mount_name),
    CONSTRAINT fk_project_repositories__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_project_repositories__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_project_repositories__project_id_repository_id UNIQUE (project_id, repository_id),
    CONSTRAINT ck_project_repositories__mount_name CHECK (mount_name ~ '^[a-z0-9][a-z0-9_-]{0,31}$'),
    CONSTRAINT ck_project_repositories__role CHECK (role IN ('primary', 'secondary', 'docs', 'infra'))
);
CREATE UNIQUE INDEX uq_project_repositories__one_primary
    ON skm_workspace.project_repositories (project_id) WHERE role = 'primary';
CREATE INDEX ix_project_repositories__repository_id ON skm_workspace.project_repositories (repository_id);

CREATE TABLE skm_workspace.hosts (
    id             uuid        PRIMARY KEY REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    name           text        NOT NULL,
    os             text        NOT NULL,
    arch           text        NOT NULL,
    state          text        NOT NULL DEFAULT 'active',
    row_version    bigint      NOT NULL DEFAULT 1,
    registered_at  timestamptz NOT NULL,
    last_seen_at   timestamptz NULL,
    CONSTRAINT uq_hosts__name UNIQUE (name),
    CONSTRAINT ck_hosts__name CHECK (name ~ '^[a-z0-9][a-z0-9.-]{0,62}$'),
    CONSTRAINT ck_hosts__os CHECK (os IN ('linux', 'macos', 'windows')),
    CONSTRAINT ck_hosts__arch CHECK (arch IN ('x86_64', 'arm64', 'other')),
    CONSTRAINT ck_hosts__state CHECK (state IN ('active', 'retired'))
);

CREATE TABLE skm_workspace.checkout_bindings (
    id                uuid        PRIMARY KEY,
    workspace_id      uuid        NOT NULL,
    host_id           uuid        NOT NULL,
    repository_id     uuid        NOT NULL,
    local_locator     text        NOT NULL,
    state             text        NOT NULL,
    observed_remotes  text[]      NOT NULL DEFAULT '{}',
    observed_head     text        NULL,
    last_verified_at  timestamptz NOT NULL,
    row_version       bigint      NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL,
    updated_at        timestamptz NOT NULL,
    CONSTRAINT fk_checkout_bindings__hosts FOREIGN KEY (host_id)
        REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT fk_checkout_bindings__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_checkout_bindings__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_checkout_bindings__state CHECK (state IN ('active', 'missing', 'mismatched', 'removed')),
    CONSTRAINT ck_checkout_bindings__locator CHECK (
        char_length(local_locator) BETWEEN 1 AND 4096
        AND (local_locator ~ '^/' OR local_locator ~ '^[A-Za-z]:\\')
        AND position(E'\n' in local_locator) = 0),
    CONSTRAINT ck_checkout_bindings__head CHECK (observed_head IS NULL OR observed_head ~ '^([0-9a-f]{40}|[0-9a-f]{64})$')
);
CREATE UNIQUE INDEX uq_checkout_bindings__host_id_repository_id_live
    ON skm_workspace.checkout_bindings (host_id, repository_id) WHERE state <> 'removed';

CREATE TABLE skm_workspace.workers (
    id                 uuid        PRIMARY KEY,
    workspace_id       uuid        NOT NULL,
    host_id            uuid        NOT NULL,
    principal_id       uuid        NOT NULL,
    display_name       text        NOT NULL,
    capabilities       jsonb       NOT NULL,
    state              text        NOT NULL DEFAULT 'offline',
    last_heartbeat_at  timestamptz NULL,
    registered_at      timestamptz NOT NULL,
    row_version        bigint      NOT NULL DEFAULT 1,
    CONSTRAINT fk_workers__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_workers__hosts FOREIGN KEY (host_id)
        REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT fk_workers__principals FOREIGN KEY (principal_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT uq_workers__principal_id UNIQUE (principal_id),
    CONSTRAINT uq_workers__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_workers__state CHECK (state IN ('online', 'draining', 'offline', 'retired')),
    CONSTRAINT ck_workers__display_name CHECK (char_length(display_name) BETWEEN 1 AND 100),
    -- shape is validated by urn:skm:workspace:worker-capabilities:v1 in the application; the DB keeps a size bound
    CONSTRAINT ck_workers__capabilities_size CHECK (octet_length(capabilities::text) < 16384)
);
CREATE INDEX ix_workers__workspace_id_state ON skm_workspace.workers (workspace_id, state);
CREATE INDEX ix_workers__state_last_heartbeat_at ON skm_workspace.workers (state, last_heartbeat_at);

SELECT skm_core.grant_app('skm_workspace', '{}'::text[]);
