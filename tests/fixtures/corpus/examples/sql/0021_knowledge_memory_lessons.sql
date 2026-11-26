-- 0021_knowledge_memory_lessons: short-lived memory, durable curated lessons, the project graph and its index generations.
-- Owner module: knowledge. FKs: skm_core (scopes), skm_access (principals), skm_workspace (workspaces, projects,
-- repositories) — allowed by the module graph (knowledge depends on workspace). Spec: spec/modules/knowledge.md.
CREATE SCHEMA IF NOT EXISTS skm_knowledge;

-- Memory: ephemeral context (TTL ≤ 72 h, ≤ 800 chars, ≤ 8 live entries per scope — limits live in config and the
-- domain; the DB keeps hard upper bounds only). The body never goes into domain events.
CREATE TABLE skm_knowledge.memory_entries (
    id             uuid        PRIMARY KEY,
    scope_kind     text        NOT NULL,
    scope_id       uuid        NULL,
    namespace      text        NULL,
    workspace_id   uuid        NULL,
    kind           text        NOT NULL,
    body           text        NOT NULL,
    state          text        NOT NULL DEFAULT 'live',
    writer         text        NOT NULL,
    source         text        NOT NULL,
    created_by     uuid        NOT NULL,
    supersedes_id  uuid        NULL,
    created_at     timestamptz NOT NULL,
    expires_at     timestamptz NOT NULL,
    state_changed_at timestamptz NULL,
    row_version    bigint      NOT NULL DEFAULT 1,
    CONSTRAINT fk_memory_entries__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_memory_entries__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_memory_entries__principals FOREIGN KEY (created_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_memory_entries__supersedes FOREIGN KEY (supersedes_id)
        REFERENCES skm_knowledge.memory_entries (id) ON DELETE SET NULL,
    CONSTRAINT ck_memory_entries__scope_kind CHECK (scope_kind IN ('project', 'namespace', 'global')),
    CONSTRAINT ck_memory_entries__scope_shape CHECK (
        (scope_kind = 'project' AND scope_id IS NOT NULL AND namespace IS NULL AND workspace_id IS NOT NULL)
        OR (scope_kind = 'namespace' AND scope_id IS NULL AND namespace IS NOT NULL AND workspace_id IS NOT NULL)
        OR (scope_kind = 'global' AND scope_id IS NULL AND namespace IS NULL AND workspace_id IS NULL)),
    CONSTRAINT ck_memory_entries__namespace CHECK (namespace IS NULL OR namespace ~ '^[a-z][a-z0-9-]{1,40}$'),
    CONSTRAINT ck_memory_entries__kind CHECK (
        kind IN ('context', 'fact', 'blocker', 'coordination', 'active_handoff', 'health_probe')),
    CONSTRAINT ck_memory_entries__body CHECK (char_length(body) BETWEEN 1 AND 2000 AND body = btrim(body)),
    CONSTRAINT ck_memory_entries__state CHECK (state IN ('live', 'forgotten', 'expired', 'superseded')),
    CONSTRAINT ck_memory_entries__source CHECK (source IN ('cli', 'mcp', 'hook', 'api', 'internal')),
    CONSTRAINT ck_memory_entries__writer CHECK (writer ~ '^[a-z][a-z0-9_]{1,31}$'),
    -- hard cap 72 h (knowledge.memory.max_ttl_hours can only narrow it)
    CONSTRAINT ck_memory_entries__ttl CHECK (expires_at > created_at AND expires_at <= created_at + interval '72 hours'),
    CONSTRAINT ck_memory_entries__state_changed_at CHECK ((state = 'live') = (state_changed_at IS NULL))
);
-- One live active_handoff per scope. remember() marks any live handoff of the scope superseded (even one already past
-- expires_at but not yet swept by expire_memory) before inserting the new one. KNOWLEDGE-05 requires the
-- expected_handoff_id CAS under a transaction-scoped lock of the complete scope tuple; the index is the final guard.
CREATE UNIQUE INDEX uq_memory_entries__live_handoff
    ON skm_knowledge.memory_entries (scope_kind, scope_id, namespace, workspace_id) NULLS NOT DISTINCT
    WHERE state = 'live' AND kind = 'active_handoff';
CREATE INDEX ix_memory_entries__scope_live
    ON skm_knowledge.memory_entries (scope_kind, scope_id, namespace, workspace_id, expires_at) WHERE state = 'live';
CREATE INDEX ix_memory_entries__expires_at_live ON skm_knowledge.memory_entries (expires_at) WHERE state = 'live';
CREATE INDEX ix_memory_entries__state_changed_at ON skm_knowledge.memory_entries (state_changed_at) WHERE state <> 'live';
CREATE INDEX ix_memory_entries__body_fts ON skm_knowledge.memory_entries USING gin (to_tsvector('simple', body));

-- Lessons: durable, curated by a human from a learning candidate. They never expire.
CREATE TABLE skm_knowledge.lessons (
    id                  uuid        PRIMARY KEY,
    workspace_id        uuid        NOT NULL,
    scope_id            uuid        NOT NULL,
    kind                text        NOT NULL,
    trigger             text        NOT NULL,
    action              text        NOT NULL,
    -- [{"kind": "check_execution" | "review" | "attempt" | "file_version" | "client_session", "id": "<uuid or key>"}]
    evidence            jsonb       NOT NULL DEFAULT '[]'::jsonb,
    confidence          double precision NOT NULL,
    confidence_tier     text        NOT NULL,
    state               text        NOT NULL DEFAULT 'curated',
    candidate_id        uuid        NOT NULL,     -- stable reference into skm_learning (no FK: learning sits above knowledge)
    promoted_by         uuid        NOT NULL,
    promoted_at         timestamptz NOT NULL,
    deprecated_by       uuid        NULL,
    deprecated_at       timestamptz NULL,
    deprecation_reason  text        NULL,
    supersedes_id       uuid        NULL,
    review_flag         text        NOT NULL DEFAULT 'none',
    applicability       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    row_version         bigint      NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL,
    updated_at          timestamptz NOT NULL,
    CONSTRAINT fk_lessons__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lessons__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lessons__promoted_by FOREIGN KEY (promoted_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lessons__deprecated_by FOREIGN KEY (deprecated_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_lessons__supersedes FOREIGN KEY (supersedes_id)
        REFERENCES skm_knowledge.lessons (id) ON DELETE RESTRICT,
    CONSTRAINT uq_lessons__candidate_id UNIQUE (candidate_id),
    CONSTRAINT ck_lessons__kind CHECK (kind IN ('heuristic', 'procedure', 'gotcha')),
    CONSTRAINT ck_lessons__trigger CHECK (char_length(trigger) BETWEEN 1 AND 500),
    CONSTRAINT ck_lessons__action CHECK (char_length(action) BETWEEN 1 AND 1000),
    CONSTRAINT ck_lessons__evidence CHECK (jsonb_typeof(evidence) = 'array' AND jsonb_array_length(evidence) <= 50),
    CONSTRAINT ck_lessons__confidence CHECK (confidence >= 0 AND confidence < 1),
    CONSTRAINT ck_lessons__confidence_tier CHECK (confidence_tier IN ('none', 'tentative', 'moderate', 'strong', 'core')),
    CONSTRAINT ck_lessons__state CHECK (state IN ('curated', 'deprecated')),
    CONSTRAINT ck_lessons__deprecation CHECK (
        (state = 'curated' AND deprecated_at IS NULL AND deprecated_by IS NULL AND deprecation_reason IS NULL)
        OR (state = 'deprecated' AND deprecated_at IS NOT NULL AND deprecated_by IS NOT NULL
            AND char_length(deprecation_reason) BETWEEN 1 AND 500)),
    CONSTRAINT ck_lessons__review_flag CHECK (review_flag IN ('none', 'decay')),
    -- Typed bounds/keys, exact binding IDs and timestamps are validated by LessonApplicability before persistence.
    CONSTRAINT ck_lessons__applicability CHECK (jsonb_typeof(applicability) = 'object' AND octet_length(applicability::text) <= 16384)
);
CREATE INDEX ix_lessons__workspace_scope_state ON skm_knowledge.lessons (workspace_id, scope_id, state, updated_at, id);

-- Graph index generations: what a source (serena, manifests, manual, plugin) imported for a repository and when.
CREATE TABLE skm_knowledge.graph_indexes (
    id              uuid        PRIMARY KEY,
    workspace_id    uuid        NOT NULL,
    project_id      uuid        NULL,
    repository_id   uuid        NULL,
    source          text        NOT NULL,
    generation      integer     NOT NULL,
    revision        text        NULL,
    dirty           boolean     NOT NULL DEFAULT false,
    languages       text[]      NOT NULL DEFAULT '{}',
    basis_default   text        NOT NULL,
    tool_name       text        NOT NULL,
    tool_version    text        NOT NULL,
    indexed_at      timestamptz NOT NULL,
    completeness    text        NOT NULL,
    -- [{"code": "language_unsupported", "message": "...", "count": 3}]
    limitations     jsonb       NOT NULL DEFAULT '[]'::jsonb,
    files_indexed   integer     NOT NULL DEFAULT 0,
    files_skipped   integer     NOT NULL DEFAULT 0,
    nodes           integer     NOT NULL DEFAULT 0,
    edges           integer     NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL,
    CONSTRAINT fk_graph_indexes__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_graph_indexes__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_graph_indexes__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_graph_indexes__generation UNIQUE NULLS NOT DISTINCT (workspace_id, source, repository_id, generation),
    CONSTRAINT ck_graph_indexes__source CHECK (source ~ '^[a-z][a-z0-9-]{1,40}$'),
    CONSTRAINT ck_graph_indexes__generation CHECK (generation >= 1),
    CONSTRAINT ck_graph_indexes__revision CHECK (revision IS NULL OR revision ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'),
    CONSTRAINT ck_graph_indexes__basis_default CHECK (basis_default IN ('declared', 'lsp', 'ast', 'text', 'heuristic')),
    CONSTRAINT ck_graph_indexes__completeness CHECK (completeness IN ('complete', 'partial', 'unknown')),
    CONSTRAINT ck_graph_indexes__limitations CHECK (jsonb_typeof(limitations) = 'array'),
    CONSTRAINT ck_graph_indexes__counts CHECK (files_indexed >= 0 AND files_skipped >= 0 AND nodes >= 0 AND edges >= 0)
);
CREATE INDEX ix_graph_indexes__latest
    ON skm_knowledge.graph_indexes (workspace_id, source, repository_id, generation DESC);

CREATE TABLE skm_knowledge.graph_nodes (
    id             uuid        PRIMARY KEY,
    workspace_id   uuid        NOT NULL,
    project_id     uuid        NULL,
    repository_id  uuid        NULL,
    node_key       text        NOT NULL,
    type           text        NOT NULL,
    attrs          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    source         text        NOT NULL,
    created_at     timestamptz NOT NULL,
    updated_at     timestamptz NOT NULL,
    CONSTRAINT fk_graph_nodes__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_graph_nodes__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_graph_nodes__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_graph_nodes__workspace_id_node_key UNIQUE (workspace_id, node_key),
    CONSTRAINT uq_graph_nodes__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_graph_nodes__type CHECK (
        type IN ('project', 'agent', 'memory', 'skill', 'entity', 'tool', 'package', 'doc', 'symbol')),
    CONSTRAINT ck_graph_nodes__node_key CHECK (
        char_length(node_key) BETWEEN 3 AND 340 AND node_key LIKE type || ':%'),
    CONSTRAINT ck_graph_nodes__source CHECK (source ~ '^[a-z][a-z0-9-]{1,40}$'),
    CONSTRAINT ck_graph_nodes__attrs CHECK (jsonb_typeof(attrs) = 'object' AND octet_length(attrs::text) < 16384)
);
CREATE INDEX ix_graph_nodes__source_repository ON skm_knowledge.graph_nodes (workspace_id, source, repository_id);

-- Multi-edges are allowed: the key is (src, dst, type, source, source_key), not (src, dst) (legacy defect, §4.3).
CREATE TABLE skm_knowledge.graph_edges (
    id             uuid        PRIMARY KEY,
    workspace_id   uuid        NOT NULL,
    src_node_id    uuid        NOT NULL,
    dst_node_id    uuid        NOT NULL,
    type           text        NOT NULL,
    attrs          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    source         text        NOT NULL,
    source_key     text        NOT NULL DEFAULT '',
    repository_id  uuid        NULL,
    basis          text        NULL,
    created_at     timestamptz NOT NULL,
    -- composite FKs keep both ends inside the same workspace
    CONSTRAINT fk_graph_edges__src FOREIGN KEY (workspace_id, src_node_id)
        REFERENCES skm_knowledge.graph_nodes (workspace_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_graph_edges__dst FOREIGN KEY (workspace_id, dst_node_id)
        REFERENCES skm_knowledge.graph_nodes (workspace_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_graph_edges__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_graph_edges__identity UNIQUE (src_node_id, dst_node_id, type, source, source_key),
    CONSTRAINT ck_graph_edges__type CHECK (
        type IN ('uses', 'knows', 'relates_to', 'belongs_to', 'depends_on', 'provided_by', 'requires', 'references')),
    CONSTRAINT ck_graph_edges__source CHECK (source ~ '^[a-z][a-z0-9-]{1,40}$'),
    CONSTRAINT ck_graph_edges__source_key CHECK (char_length(source_key) <= 300),
    CONSTRAINT ck_graph_edges__basis CHECK (basis IS NULL OR basis IN ('declared', 'lsp', 'ast', 'text', 'heuristic')),
    CONSTRAINT ck_graph_edges__attrs CHECK (jsonb_typeof(attrs) = 'object' AND octet_length(attrs::text) < 8192)
);
CREATE INDEX ix_graph_edges__src ON skm_knowledge.graph_edges (workspace_id, src_node_id, type);
CREATE INDEX ix_graph_edges__dst ON skm_knowledge.graph_edges (workspace_id, dst_node_id, type);
CREATE INDEX ix_graph_edges__source_repository ON skm_knowledge.graph_edges (workspace_id, source, repository_id);

SELECT skm_core.grant_app('skm_knowledge', '{}'::text[]);
