-- 0019_context_manifests: step-owned and standalone context manifests (two-phase: draft -> final), their blocks, content-addressed texts,
-- research queries (one row per source answer) and external documents found by research.
-- Owner module: context (spec/modules/context.md §11). FKs: skm_workspace, skm_planning, skm_artifacts,
-- skm_extensions, skm_access (module graph: context -> planning, extensions, artifacts).
CREATE SCHEMA IF NOT EXISTS skm_context;

-- Texts of control-plane blocks (and of host blocks when context.store_host_block_content = true). Append-only.
CREATE TABLE skm_context.texts (
    digest      text        PRIMARY KEY,
    text        text        NOT NULL,
    size_bytes  integer     NOT NULL,
    created_at  timestamptz NOT NULL,
    CONSTRAINT ck_texts__digest CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_texts__size CHECK (size_bytes = octet_length(text))
);
CREATE TRIGGER tg_texts__append_only BEFORE UPDATE OR DELETE ON skm_context.texts
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- The only allowed update of a manifest: state draft -> final with the decision fields filled once.
CREATE FUNCTION skm_context.tg_context_manifests__finalize_only() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TABLE skm_context.context_manifests (
    id                        uuid        PRIMARY KEY,
    state                     text        NOT NULL DEFAULT 'draft',
    workspace_id              uuid        NOT NULL,
    project_id                uuid        NOT NULL,
    plan_id                   uuid        NULL,
    revision_id               uuid        NULL,
    entity_id                 uuid        NULL,     -- item or unit of the revision (checked by planning.public, polymorphic)
    role                      text        NOT NULL,
    stage_id                  text        NOT NULL,
    step_ref                  text        NULL,     -- execution step id; one manifest per step (a fallback route is a new step)
    owner_ref                 text        NOT NULL,     -- step:<step_id> or standalone:<principal_id>
    attempt_no                integer     NOT NULL,
    round_no                  integer     NOT NULL,
    agent_profile_version_id  uuid        NOT NULL,
    runtime_id                text        NOT NULL,
    model                     text        NOT NULL,
    route                     jsonb       NOT NULL,     -- {route_source, operation, config_mode, self_loads[], self_loads_observed[]|null}
    draft_digest              text        NOT NULL,
    mode                      text        NULL,
    task_digest               text        NULL,
    prompt_digest             text        NULL,
    prompt_file_version_id    uuid        NULL,
    total_tokens_estimate     integer     NULL,
    total_limit               integer     NOT NULL,
    budgets                   jsonb       NOT NULL,
    host_inputs               jsonb       NOT NULL,     -- HostInputRequest[] of the draft (what the host had to read/query)
    host_facts                jsonb       NULL,
    skills_trace              jsonb       NOT NULL,
    diagnostics               jsonb       NOT NULL DEFAULT '[]'::jsonb,
    estimator_id              text        NOT NULL,
    assembler_version         integer     NOT NULL,
    created_at                timestamptz NOT NULL,
    finalized_at              timestamptz NULL,
    CONSTRAINT fk_context_manifests__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_manifests__plans FOREIGN KEY (workspace_id, project_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_manifests__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_manifests__resource_versions FOREIGN KEY (agent_profile_version_id)
        REFERENCES skm_extensions.resource_versions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_context_manifests__file_versions FOREIGN KEY (workspace_id, prompt_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_context_manifests__step_ref UNIQUE (step_ref),
    CONSTRAINT ck_context_manifests__state CHECK (state IN ('draft', 'final')),
    CONSTRAINT ck_context_manifests__role CHECK (role IN ('scout', 'executor', 'reviewer', 'triager', 'advisor', 'researcher',
        'registrar')),
    CONSTRAINT ck_context_manifests__owner_ref CHECK (
        (step_ref IS NOT NULL AND owner_ref ~ '^step:.+$' AND owner_ref = 'step:' || step_ref
            AND ((plan_id IS NOT NULL AND revision_id IS NOT NULL AND entity_id IS NOT NULL)
                OR (plan_id IS NULL AND revision_id IS NULL AND entity_id IS NULL)))
        OR (step_ref IS NULL
            AND owner_ref ~ '^standalone:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            AND (revision_id IS NULL OR plan_id IS NOT NULL)
            AND (entity_id IS NULL OR revision_id IS NOT NULL))),
    CONSTRAINT ck_context_manifests__numbers CHECK (attempt_no >= 1 AND round_no >= 1 AND total_limit >= 1000
        AND (total_tokens_estimate IS NULL OR total_tokens_estimate >= 0)),
    CONSTRAINT ck_context_manifests__runtime_id CHECK (runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_context_manifests__route CHECK (jsonb_typeof(route) = 'object'
        AND route ? 'route_source' AND route ? 'operation' AND route->>'config_mode' IN ('isolated', 'inherit')),
    CONSTRAINT ck_context_manifests__mode CHECK (mode IS NULL OR mode IN ('full', 'delta')),
    CONSTRAINT ck_context_manifests__digests CHECK (draft_digest ~ '^sha256:[0-9a-f]{64}$'
        AND (task_digest IS NULL OR task_digest ~ '^sha256:[0-9a-f]{64}$')
        AND (prompt_digest IS NULL OR prompt_digest ~ '^sha256:[0-9a-f]{64}$')),
    CONSTRAINT ck_context_manifests__estimator_id CHECK (estimator_id = 'heuristic-v1'),
    CONSTRAINT ck_context_manifests__final_fields CHECK (
        (state = 'draft' AND mode IS NULL AND task_digest IS NULL AND prompt_digest IS NULL AND prompt_file_version_id IS NULL
            AND total_tokens_estimate IS NULL AND finalized_at IS NULL)
        OR (state = 'final' AND mode IS NOT NULL AND task_digest IS NOT NULL AND prompt_digest IS NOT NULL
            AND prompt_file_version_id IS NOT NULL AND total_tokens_estimate IS NOT NULL AND finalized_at IS NOT NULL))
);
CREATE INDEX ix_context_manifests__workspace_id_plan_id_created_at
    ON skm_context.context_manifests (workspace_id, plan_id, created_at DESC);
CREATE FUNCTION skm_context.check_standalone_entity() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER tg_context_manifests__standalone_entity BEFORE INSERT ON skm_context.context_manifests
    FOR EACH ROW EXECUTE FUNCTION skm_context.check_standalone_entity();

CREATE TRIGGER tg_context_manifests__finalize_only BEFORE UPDATE OR DELETE ON skm_context.context_manifests
    FOR EACH ROW EXECUTE FUNCTION skm_context.tg_context_manifests__finalize_only();

CREATE TABLE skm_context.context_blocks (
    manifest_id         uuid    NOT NULL,
    ordinal             integer NOT NULL,
    block_ref           text    NOT NULL,      -- d:<n> | c:<n> | x:<n> | h:<request_id>
    position            integer NULL,
    block_type          text    NOT NULL,
    budget_class        text    NOT NULL,
    mandatory           boolean NOT NULL,
    source_kind         text    NOT NULL,
    source_ref          text    NOT NULL,
    atomic_group        text    NULL, -- immutable server-owned group, included/excluded as a unit
    source_version      text    NULL,
    trust               text    NOT NULL,
    tokens_estimate     integer NULL,
    content_digest      text    NULL,
    included            boolean NULL,          -- NULL: draft row, decision not taken yet
    reason              text    NOT NULL,
    detail              text    NULL,
    content_stored      boolean NOT NULL,
    research_query_ids  uuid[]  NULL,          -- host research block: rows it was rendered from (server re-renders to verify)
    CONSTRAINT pk_context_blocks PRIMARY KEY (manifest_id, ordinal),
    CONSTRAINT fk_context_blocks__context_manifests FOREIGN KEY (manifest_id)
        REFERENCES skm_context.context_manifests (id) ON DELETE RESTRICT,
    CONSTRAINT uq_context_blocks__manifest_id_block_ref UNIQUE (manifest_id, block_ref),
    CONSTRAINT uq_context_blocks__manifest_id_position UNIQUE (manifest_id, position),
    CONSTRAINT ck_context_blocks__block_ref CHECK (block_ref ~ '^(d:[0-9]+|c:[0-9]+|x:[0-9]+|h:hi:[0-9]+)$'),
    CONSTRAINT ck_context_blocks__block_type CHECK (block_type IN ('resume_note', 'system_constraints', 'role_contract',
        'run_rules', 'runtime_notes', 'task_contract', 'acceptance', 'requirements', 'decisions', 'decision_answers',
        'review_feedback', 'previous_attempt', 'candidate_diff', 'findings_under_review', 'context_map', 'steering', 'skills',
        'skill_index', 'materials', 'repo_instructions', 'research', 'memory', 'history', 'result_contract')),
    CONSTRAINT ck_context_blocks__budget_class CHECK (budget_class IN ('core', 'task', 'supporting', 'retrieval')),
    CONSTRAINT ck_context_blocks__source_kind CHECK (source_kind IN ('spec', 'resource', 'file_version', 'execution', 'memory',
        'core', 'external', 'repository_path')),
    CONSTRAINT ck_context_blocks__trust CHECK (trust IN ('system', 'operator', 'project', 'repository', 'model', 'external',
        'third_party', 'memory')),
    CONSTRAINT ck_context_blocks__position CHECK ((included IS TRUE) = (position IS NOT NULL) AND (position IS NULL OR position >= 0)),
    CONSTRAINT ck_context_blocks__tokens CHECK (tokens_estimate IS NULL OR tokens_estimate >= 0),
    CONSTRAINT ck_context_blocks__atomic_group CHECK (atomic_group IS NULL OR char_length(atomic_group) BETWEEN 1 AND 200),
    CONSTRAINT ck_context_blocks__content_digest CHECK (content_digest IS NULL OR content_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_context_blocks__stored CHECK (NOT content_stored OR content_digest IS NOT NULL)
);
-- Draft rows (included IS NULL) get their decision once by context.finalize_manifest; final-manifest rows are frozen
-- (checked in PostgresContextRepository.finalize: UPDATE ... WHERE included IS NULL, row count must match).

-- One row = the answer of one research source to one query. Errors are stored (audit) but never served from cache.
CREATE TABLE skm_context.research_queries (
    id                    uuid        PRIMARY KEY,
    workspace_id          uuid        NOT NULL,
    project_id            uuid        NOT NULL,
    step_ref              text        NULL,
    requested_by          uuid        NOT NULL,
    source_id             text        NOT NULL,
    source_kind           text        NOT NULL,
    tier                  text        NOT NULL,
    query_text            text        NOT NULL,   -- after redaction
    query_digest          text        NOT NULL,
    depth                 text        NOT NULL,
    max_documents         integer     NOT NULL,
    cache_key             text        NOT NULL,
    source_config_digest  text        NOT NULL,
    status                text        NOT NULL,
    error_code            text        NULL,
    error_message         text        NULL,
    citations             jsonb       NOT NULL DEFAULT '[]'::jsonb,
    claims                jsonb       NOT NULL DEFAULT '[]'::jsonb,
    limitations           jsonb       NOT NULL DEFAULT '[]'::jsonb,
    usage                 jsonb       NULL,
    usage_complete        boolean     NOT NULL,
    retrieved_at          timestamptz NOT NULL,
    expires_at            timestamptz NULL,
    created_at            timestamptz NOT NULL,
    CONSTRAINT fk_research_queries__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_research_queries__principals FOREIGN KEY (requested_by) REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT uq_research_queries__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT ck_research_queries__source_id CHECK (source_id ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'),
    CONSTRAINT ck_research_queries__source_kind CHECK (source_kind ~ '^[a-z][a-z0-9_]{1,62}$'),
    CONSTRAINT ck_research_queries__tier CHECK (tier IN ('local_docs', 'codegraph', 'external_search', 'deep_research')),
    CONSTRAINT ck_research_queries__query_text CHECK (char_length(query_text) BETWEEN 1 AND 20000),
    CONSTRAINT ck_research_queries__depth CHECK (depth IN ('standard', 'deep')),
    CONSTRAINT ck_research_queries__max_documents CHECK (max_documents BETWEEN 1 AND 50),
    CONSTRAINT ck_research_queries__digests CHECK (query_digest ~ '^sha256:[0-9a-f]{64}$' AND cache_key ~ '^sha256:[0-9a-f]{64}$'
        AND source_config_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_research_queries__status CHECK (status IN ('ok', 'empty', 'error')),
    CONSTRAINT ck_research_queries__error CHECK ((status = 'error') = (error_code IS NOT NULL)
        AND (error_code IS NULL OR error_code IN ('RESEARCH_SOURCE_UNAVAILABLE', 'RESEARCH_SOURCE_TIMEOUT', 'RESEARCH_SOURCE_INVALID'))),
    CONSTRAINT ck_research_queries__expires CHECK ((status <> 'error' OR expires_at IS NULL)
        AND (expires_at IS NULL OR expires_at > retrieved_at)),
    CONSTRAINT ck_research_queries__json CHECK (jsonb_typeof(citations) = 'array' AND jsonb_typeof(claims) = 'array'
        AND jsonb_typeof(limitations) = 'array')
);
CREATE INDEX ix_research_queries__cache ON skm_context.research_queries (workspace_id, project_id, cache_key, retrieved_at DESC)
    WHERE status <> 'error';
CREATE INDEX ix_research_queries__step_ref ON skm_context.research_queries (step_ref) WHERE step_ref IS NOT NULL;
CREATE TRIGGER tg_research_queries__append_only BEFORE UPDATE OR DELETE ON skm_context.research_queries
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- External documents (audit G39): what research found, with provenance and the captured material when saved.
CREATE TABLE skm_context.external_sources (
    id                        uuid        PRIMARY KEY,       -- document_id
    workspace_id              uuid        NOT NULL,
    project_id                uuid        NOT NULL,
    query_id                  uuid        NOT NULL,
    ordinal                   integer     NOT NULL,
    origin                    text        NOT NULL,
    url                       text        NULL,
    title                     text        NOT NULL,
    retrieved_at              timestamptz NOT NULL,
    content_digest            text        NULL,
    size_bytes                integer     NULL,
    locator                   jsonb       NOT NULL DEFAULT '{}'::jsonb,
    excerpt                   text        NOT NULL,
    trust_class               text        NOT NULL,
    classification            text        NOT NULL,
    provenance                jsonb       NOT NULL,          -- {source_id, source_kind, tier, adapter_version, raw_digest}
    captured_file_version_id  uuid        NULL,
    created_at                timestamptz NOT NULL,
    CONSTRAINT fk_external_sources__research_queries FOREIGN KEY (workspace_id, query_id)
        REFERENCES skm_context.research_queries (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_external_sources__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_external_sources__file_versions FOREIGN KEY (workspace_id, captured_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_external_sources__query_id_ordinal UNIQUE (query_id, ordinal),
    CONSTRAINT ck_external_sources__origin CHECK (origin ~ '^(https?://|repo:|file:|mcp:|answer:).+' AND char_length(origin) <= 2000),
    CONSTRAINT ck_external_sources__url CHECK (url IS NULL OR (url ~ '^https?://' AND char_length(url) <= 2000)),
    CONSTRAINT ck_external_sources__title CHECK (char_length(title) BETWEEN 1 AND 500),
    CONSTRAINT ck_external_sources__content_digest CHECK (content_digest IS NULL OR content_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_external_sources__excerpt CHECK (char_length(excerpt) <= 20000),
    CONSTRAINT ck_external_sources__trust_class CHECK (trust_class IN ('repository', 'external', 'third_party')),
    CONSTRAINT ck_external_sources__classification CHECK (classification IN ('public', 'internal', 'confidential', 'restricted')),
    CONSTRAINT ck_external_sources__ordinal CHECK (ordinal >= 0 AND ordinal < 50)
);
CREATE INDEX ix_external_sources__project_id_origin ON skm_context.external_sources (workspace_id, project_id, origin);
CREATE TRIGGER tg_external_sources__append_only BEFORE UPDATE OR DELETE ON skm_context.external_sources
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- deferred FK of skm_execution
-- skm_execution.attempt_steps (0014) is created before this schema; context_manifest_id is a plain uuid there.
-- skm_execution depends on context (spec/modules/execution.md §2), so the FK goes down the module graph.
ALTER TABLE skm_execution.attempt_steps
    ADD CONSTRAINT fk_attempt_steps__context_manifests FOREIGN KEY (context_manifest_id)
    REFERENCES skm_context.context_manifests (id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE skm_execution.attempt_steps VALIDATE CONSTRAINT fk_attempt_steps__context_manifests;

SELECT skm_core.grant_app('skm_context', ARRAY['external_sources','research_queries','texts']::text[]);
