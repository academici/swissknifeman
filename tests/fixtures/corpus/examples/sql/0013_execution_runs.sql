-- 0013_execution_runs: readiness reports, runs, execution bundles, reconfigurations, review requests, run tasks and edges.
-- Owner module: execution (spec/modules/execution.md §4.1–§4.5, §4.20, §11).
-- FKs only along the module graph (ADR 0003): skm_core, skm_workspace, skm_planning, skm_extensions, skm_artifacts.
-- No FK to skm_access: execution does not depend on access; principal ids are plain uuids (principals are never deleted).
-- Internal references are composite ((run_id, id), (workspace_id, id)) so a row can never point into another run.

CREATE SCHEMA IF NOT EXISTS skm_execution;

-- ---------------------------------------------------------------- readiness reports (immutable certificates, G28)
CREATE TABLE skm_execution.readiness_reports (
    id                   uuid        NOT NULL,
    workspace_id         uuid        NOT NULL,
    project_id           uuid        NOT NULL,
    plan_id              uuid        NOT NULL,
    revision_id          uuid        NOT NULL,
    revision_digest      text        NOT NULL,
    status               text        NOT NULL,             -- stored status; "stale" is computed on read (§5.12)
    scope                jsonb       NOT NULL DEFAULT '{"kind": "plan", "phase_keys": []}',
    inputs               jsonb       NOT NULL,             -- digests per staleness part (requirements, dependencies, …)
    inputs_digest        text        NOT NULL,
    policy_digest        text        NOT NULL,
    results              jsonb       NOT NULL,             -- [{rule_id, outcome, findings_count}]
    findings             jsonb       NOT NULL DEFAULT '[]',
    assumptions          jsonb       NOT NULL DEFAULT '[]',
    structural_counts    jsonb       NOT NULL,
    estimate             jsonb       NOT NULL,
    audit                jsonb       NULL,                 -- semantic audit by plan-auditor (§5.12)
    supersedes_report_id uuid        NULL,
    validator_version    integer     NOT NULL,
    created_by           uuid        NOT NULL,
    created_at           timestamptz NOT NULL,
    CONSTRAINT pk_readiness_reports PRIMARY KEY (id),
    CONSTRAINT uq_readiness_reports__revision_scope_id UNIQUE (workspace_id, plan_id, revision_id, id),
    CONSTRAINT fk_readiness_reports__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_readiness_reports__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_readiness_reports__supersedes FOREIGN KEY (workspace_id, plan_id, revision_id, supersedes_report_id)
        REFERENCES skm_execution.readiness_reports (workspace_id, plan_id, revision_id, id),
    CONSTRAINT ck_readiness_reports__status CHECK (status IN ('ready', 'ready_with_advisories', 'not_ready')),
    CONSTRAINT ck_readiness_reports__digests CHECK (revision_digest ~ '^sha256:[0-9a-f]{64}$'
        AND inputs_digest ~ '^sha256:[0-9a-f]{64}$' AND policy_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_readiness_reports__json CHECK (jsonb_typeof(scope) = 'object' AND jsonb_typeof(inputs) = 'object'
        AND jsonb_typeof(results) = 'array' AND jsonb_typeof(findings) = 'array' AND jsonb_typeof(assumptions) = 'array'
        AND jsonb_typeof(structural_counts) = 'object' AND jsonb_typeof(estimate) = 'object'),
    CONSTRAINT ck_readiness_reports__supersedes CHECK (supersedes_report_id IS NULL OR (supersedes_report_id <> id AND audit IS NOT NULL)),
    CONSTRAINT ck_readiness_reports__validator_version CHECK (validator_version >= 1)
);
CREATE INDEX ix_readiness_reports__revision_id_created_at ON skm_execution.readiness_reports (revision_id, created_at DESC);
CREATE TRIGGER tg_readiness_reports__immutable BEFORE UPDATE OR DELETE ON skm_execution.readiness_reports
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- human approval of a revision readiness report
CREATE TABLE skm_execution.revision_visas (
    id                  uuid        NOT NULL,
    workspace_id        uuid        NOT NULL,
    plan_id             uuid        NOT NULL,
    revision_id         uuid        NOT NULL,
    readiness_report_id uuid        NOT NULL,
    selection           jsonb       NULL,
    signed_by           uuid        NOT NULL,
    reason              text        NOT NULL,
    signed_at           timestamptz NOT NULL,
    CONSTRAINT pk_revision_visas PRIMARY KEY (id),
    CONSTRAINT fk_revision_visas__readiness_report FOREIGN KEY (workspace_id, plan_id, revision_id, readiness_report_id)
        REFERENCES skm_execution.readiness_reports (workspace_id, plan_id, revision_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_revision_visas__selection CHECK (selection IS NULL OR jsonb_typeof(selection) = 'object'),
    CONSTRAINT ck_revision_visas__reason CHECK (char_length(reason) BETWEEN 1 AND 2000 AND btrim(reason) <> '')
);
CREATE INDEX ix_revision_visas__report ON skm_execution.revision_visas (readiness_report_id);
CREATE TRIGGER tg_revision_visas__immutable BEFORE UPDATE OR DELETE ON skm_execution.revision_visas
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- review requests (G5, D-EX-1)
-- The request is created before its run: runs.review_request_id points here (no back reference).
CREATE TABLE skm_execution.review_requests (
    id                    uuid        NOT NULL,
    workspace_id          uuid        NOT NULL,
    project_id            uuid        NOT NULL,
    mount                 text        NOT NULL,
    repository_id         uuid        NOT NULL,
    target_kind           text        NOT NULL,
    base_commit           text        NOT NULL,
    head_commit           text        NULL,
    patch_file_version_id uuid        NULL,
    target_digest         text        NOT NULL,
    profile_key           text        NOT NULL DEFAULT 'reviewer',          -- execution.review.profile default (E15)
    reason                text        NOT NULL,
    requested_by          uuid        NOT NULL,
    plan_id               uuid        NOT NULL,             -- service plan of the project (purpose = review_requests)
    revision_id           uuid        NOT NULL,             -- its revision published for this request
    created_at            timestamptz NOT NULL,
    CONSTRAINT pk_review_requests PRIMARY KEY (id),
    CONSTRAINT uq_review_requests__workspace_id_project_id_id UNIQUE (workspace_id, project_id, id),
    CONSTRAINT uq_review_requests__revision_id UNIQUE (revision_id),
    CONSTRAINT fk_review_requests__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_requests__project_repositories FOREIGN KEY (project_id, mount)
        REFERENCES skm_workspace.project_repositories (project_id, mount_name) ON DELETE RESTRICT,
    CONSTRAINT fk_review_requests__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_requests__file_versions FOREIGN KEY (workspace_id, patch_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_requests__plans FOREIGN KEY (workspace_id, project_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_requests__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_review_requests__target CHECK (
        (target_kind = 'commits' AND head_commit IS NOT NULL AND patch_file_version_id IS NULL)
        OR (target_kind = 'working_tree' AND head_commit IS NULL AND patch_file_version_id IS NOT NULL)),
    CONSTRAINT ck_review_requests__commits CHECK (base_commit ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'
        AND (head_commit IS NULL OR head_commit ~ '^([0-9a-f]{40}|[0-9a-f]{64})$')),
    CONSTRAINT ck_review_requests__target_digest CHECK (target_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_review_requests__profile_key CHECK (profile_key ~ '^[a-z][a-z0-9-]{1,60}$'),
    CONSTRAINT ck_review_requests__reason CHECK (char_length(reason) BETWEEN 1 AND 2000)
);
CREATE INDEX ix_review_requests__project_id_created_at ON skm_execution.review_requests (project_id, created_at DESC);
CREATE TRIGGER tg_review_requests__immutable BEFORE UPDATE OR DELETE ON skm_execution.review_requests
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- runs
CREATE TABLE skm_execution.runs (
    id                           uuid        NOT NULL,     -- = scope id of kind run
    workspace_id                 uuid        NOT NULL,
    project_id                   uuid        NOT NULL,
    kind                         text        NOT NULL DEFAULT 'plan',
    plan_id                      uuid        NULL,
    revision_id                  uuid        NULL,
    revision_no                  integer     NULL,
    inline_spec_file_version_id  uuid        NULL,
    status                       text        NOT NULL DEFAULT 'created',
    requested_by                 uuid        NOT NULL,
    readiness_report_id          uuid        NULL,
    audited_report_id            uuid        NULL,
    review_request_id            uuid        NULL,
    compiler_version             integer     NOT NULL,
    workflow_resource_version_id uuid        NOT NULL,
    review_grouping              jsonb       NOT NULL,
    autopilot                    boolean     NOT NULL DEFAULT false,
    queued                       boolean     NOT NULL DEFAULT false,   -- waits for execution.parallel.max_runs_per_project
    pause_reason                 text        NULL,
    pause_source                 text        NULL,     -- system | owner (K2); set together with status paused
    stop_code                    text        NULL,     -- current code only; cleared by resume/unblock/cancel (§4.1)
    unmetered_at                 timestamptz NULL,     -- unknown usage under policy block (§5.6); reserve refused while set
    row_version                  bigint      NOT NULL DEFAULT 1,
    created_at                   timestamptz NOT NULL,
    started_at                   timestamptz NULL,
    finished_at                  timestamptz NULL,
    CONSTRAINT pk_runs PRIMARY KEY (id),
    CONSTRAINT uq_runs__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_runs__id_kind UNIQUE (id, kind),
    CONSTRAINT uq_runs__id_plan_id_revision_id UNIQUE (id, plan_id, revision_id),
    CONSTRAINT uq_runs__id_revision_id UNIQUE (id, revision_id),
    CONSTRAINT fk_runs__scopes FOREIGN KEY (id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_runs__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_runs__plans FOREIGN KEY (workspace_id, project_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_runs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_runs__inline_spec FOREIGN KEY (workspace_id, inline_spec_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_runs__readiness_reports FOREIGN KEY (workspace_id, plan_id, revision_id, readiness_report_id)
        REFERENCES skm_execution.readiness_reports (workspace_id, plan_id, revision_id, id),
    CONSTRAINT fk_runs__audited_report FOREIGN KEY (workspace_id, plan_id, revision_id, audited_report_id)
        REFERENCES skm_execution.readiness_reports (workspace_id, plan_id, revision_id, id),
    CONSTRAINT fk_runs__review_requests FOREIGN KEY (workspace_id, project_id, review_request_id)
        REFERENCES skm_execution.review_requests (workspace_id, project_id, id),
    -- FK fk_runs__resource_versions (workflow_resource_version_id -> skm_extensions.resource_versions) is added in
    -- 0018_extensions_resources (skm_extensions does not exist yet at this migration).
    CONSTRAINT ck_runs__kind CHECK (kind IN ('plan', 'review_request', 'readiness_audit', 'adhoc')),
    CONSTRAINT ck_runs__status CHECK (status IN ('created', 'ready', 'running', 'waiting', 'paused', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT ck_runs__kind_refs CHECK (
        (kind = 'review_request') = (review_request_id IS NOT NULL)
        AND (kind = 'readiness_audit') = (audited_report_id IS NOT NULL)
        AND (kind = 'plan' OR readiness_report_id IS NULL)),
    CONSTRAINT ck_runs__spec_source CHECK (
        (kind = 'adhoc' AND plan_id IS NULL AND revision_id IS NULL AND revision_no IS NULL
            AND inline_spec_file_version_id IS NOT NULL)
        OR (kind <> 'adhoc' AND plan_id IS NOT NULL AND revision_id IS NOT NULL AND revision_no IS NOT NULL
            AND inline_spec_file_version_id IS NULL)),
    CONSTRAINT ck_runs__revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_runs__compiler_version CHECK (compiler_version >= 1),
    CONSTRAINT ck_runs__started_at CHECK ((started_at IS NULL) = (status IN ('created', 'ready'))),
    CONSTRAINT ck_runs__finished_at CHECK ((finished_at IS NOT NULL) = (status IN ('succeeded', 'failed', 'cancelled'))
        AND (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)),
    CONSTRAINT ck_runs__pause_reason CHECK ((status = 'paused') = (pause_reason IS NOT NULL)),
    CONSTRAINT ck_runs__queued CHECK (NOT queued OR status = 'ready'),
    CONSTRAINT ck_runs__pause_source CHECK ((status = 'paused') = (pause_source IS NOT NULL)
        AND (pause_source IS NULL OR pause_source IN ('system', 'owner'))),
    CONSTRAINT ck_runs__stop_code CHECK (stop_code IS NULL OR (stop_code ~ '^[A-Z][A-Z0-9_]{2,63}$'
        AND status IN ('waiting', 'paused', 'failed'))),
    CONSTRAINT ck_runs__review_grouping CHECK (jsonb_typeof(review_grouping) = 'object'),
    CONSTRAINT ck_runs__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_runs__project_id_status_created_at ON skm_execution.runs (project_id, status, created_at DESC, id DESC);
CREATE INDEX ix_runs__plan_id_created_at ON skm_execution.runs (plan_id, created_at DESC);
CREATE INDEX ix_runs__status_active ON skm_execution.runs (status, id) WHERE status IN ('running', 'waiting');
CREATE INDEX ix_runs__queued ON skm_execution.runs (project_id, created_at) WHERE queued;
CREATE UNIQUE INDEX uq_runs__review_request_id ON skm_execution.runs (review_request_id) WHERE review_request_id IS NOT NULL;

CREATE FUNCTION skm_execution.check_run_binding() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER tg_runs__binding
    BEFORE INSERT OR UPDATE OF id, kind, workspace_id, project_id, plan_id, inline_spec_file_version_id
    ON skm_execution.runs FOR EACH ROW EXECUTE FUNCTION skm_execution.check_run_binding();

-- ---------------------------------------------------------------- execution bundles (frozen run inputs)
CREATE TABLE skm_execution.execution_bundles (
    run_id          uuid        NOT NULL,
    workspace_id    uuid        NOT NULL,
    config_snapshot jsonb       NOT NULL,    -- every run_frozen key of the run chain; secrets only as {"$secret_ref": …}
    config_digest   text        NOT NULL,
    policy_digest   text        NOT NULL,
    resource_pins   jsonb       NOT NULL,    -- {resources: [{kind, key, resource_version_id, digest}], packs: {slug: pack_version_id}} (K19)
    selection       jsonb       NULL,        -- run subset (K14): {task_keys[], phases[], stop_after, compiled_keys[], satisfied[]}
    context_policy  jsonb       NOT NULL,
    review_grouping jsonb       NOT NULL,
    created_at      timestamptz NOT NULL,
    CONSTRAINT pk_execution_bundles PRIMARY KEY (run_id),
    CONSTRAINT fk_execution_bundles__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_execution_bundles__digests CHECK (config_digest ~ '^sha256:[0-9a-f]{64}$' AND policy_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_execution_bundles__json CHECK (jsonb_typeof(config_snapshot) = 'object' AND jsonb_typeof(resource_pins) = 'object'
        AND jsonb_typeof(resource_pins -> 'resources') = 'array' AND jsonb_typeof(resource_pins -> 'packs') = 'object'
        AND (selection IS NULL OR jsonb_typeof(selection) = 'object')
        AND jsonb_typeof(context_policy) = 'object' AND jsonb_typeof(review_grouping) = 'object'),
    CONSTRAINT ck_execution_bundles__size CHECK (octet_length(config_snapshot::text) <= 1048576)
);
CREATE TRIGGER tg_execution_bundles__immutable BEFORE UPDATE OR DELETE ON skm_execution.execution_bundles
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- run reconfigurations (append-only)
CREATE TABLE skm_execution.run_reconfigurations (
    id           uuid        NOT NULL,
    run_id       uuid        NOT NULL,
    workspace_id uuid        NOT NULL,
    changes      jsonb       NOT NULL,       -- {key: {old, new}}
    reason       text        NOT NULL,
    changed_by   uuid        NOT NULL,
    changed_at   timestamptz NOT NULL,
    CONSTRAINT pk_run_reconfigurations PRIMARY KEY (id),
    CONSTRAINT fk_run_reconfigurations__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_run_reconfigurations__changes CHECK (jsonb_typeof(changes) = 'object' AND changes <> '{}'::jsonb),
    CONSTRAINT ck_run_reconfigurations__reason CHECK (char_length(reason) BETWEEN 1 AND 2000)
);
CREATE INDEX ix_run_reconfigurations__run_id_changed_at ON skm_execution.run_reconfigurations (run_id, changed_at);
CREATE TRIGGER tg_run_reconfigurations__append_only BEFORE UPDATE OR DELETE ON skm_execution.run_reconfigurations
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- run tasks
-- Spec-backed kinds reference a typed revision member of the run's own revision:
-- (workspace_id, plan_id, revision_id) is pinned to the run by fk_run_tasks__runs_revision.
CREATE TABLE skm_execution.run_tasks (
    id                     uuid        NOT NULL,
    run_id                 uuid        NOT NULL,
    run_kind               text        NOT NULL,
    workspace_id           uuid        NOT NULL,
    plan_id                uuid        NULL,
    revision_id            uuid        NULL,
    kind                   text        NOT NULL,
    spec_entity_id         uuid        NULL,
    spec_entity_kind       text        NULL,
    display_key            text        NOT NULL,
    origin                 jsonb       NULL,              -- synthetic kinds: {source_task_id, finding_ids[], reason}
    position               integer     NOT NULL,
    status                 text        NOT NULL DEFAULT 'blocked',
    work_kind              text        NOT NULL,
    review_mode            text        NOT NULL,
    review_profile         text        NULL,
    declared_write_scope   jsonb       NULL,              -- [{mount, pattern}]; NULL = unknown (conflicts with everything)
    required_host_id       uuid        NULL,
    current_attempt_id     uuid        NULL,              -- FK added in 0014
    accepted_attempt_id    uuid        NULL,              -- FK added in 0014
    accepted_output_id     uuid        NULL,              -- FK added in 0014
    check_fix_rounds       integer     NOT NULL DEFAULT 0,
    review_rounds          integer     NOT NULL DEFAULT 0,
    attempt_count          integer     NOT NULL DEFAULT 0,
    blocking_reason        jsonb       NULL,              -- BlockingReason (§4.19)
    blocking_code          text        NULL,              -- = blocking_reason.code (filters, inbox)
    blocking_next_check_at timestamptz NULL,              -- = blocking_reason.next_check_at (scheduler rechecks)
    row_version            bigint      NOT NULL DEFAULT 1,
    created_at             timestamptz NOT NULL,
    updated_at             timestamptz NOT NULL,
    CONSTRAINT pk_run_tasks PRIMARY KEY (id),
    CONSTRAINT uq_run_tasks__run_id_id UNIQUE (run_id, id),
    CONSTRAINT uq_run_tasks__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_run_tasks__run_id_display_key UNIQUE (run_id, display_key),
    CONSTRAINT fk_run_tasks__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_tasks__run_kind FOREIGN KEY (run_id, run_kind)
        REFERENCES skm_execution.runs (id, kind) ON DELETE RESTRICT,
    CONSTRAINT fk_run_tasks__runs_revision FOREIGN KEY (run_id, plan_id, revision_id)
        REFERENCES skm_execution.runs (id, plan_id, revision_id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_tasks__revision_members FOREIGN KEY (workspace_id, plan_id, revision_id, spec_entity_id, spec_entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind) ON DELETE RESTRICT,
    CONSTRAINT fk_run_tasks__hosts FOREIGN KEY (required_host_id) REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT ck_run_tasks__kind CHECK (kind IN ('unit', 'item', 'item_gate', 'phase_gate', 'plan_acceptance',
        'integration', 'followup', 'group_review', 'plan_audit', 'adhoc')),
    CONSTRAINT ck_run_tasks__spec_source CHECK (
        (kind = 'adhoc' AND run_kind = 'adhoc' AND plan_id IS NULL AND revision_id IS NULL
            AND spec_entity_id IS NULL AND spec_entity_kind IS NULL)
        OR (kind <> 'adhoc' AND run_kind <> 'adhoc' AND plan_id IS NOT NULL AND revision_id IS NOT NULL)),
    CONSTRAINT ck_run_tasks__spec_entity CHECK ((
        (kind = 'unit' AND spec_entity_kind = 'unit' AND spec_entity_id IS NOT NULL)
        OR (kind IN ('item', 'item_gate') AND spec_entity_kind = 'item' AND spec_entity_id IS NOT NULL)
        OR (kind = 'phase_gate' AND spec_entity_kind = 'phase' AND spec_entity_id IS NOT NULL)
        OR (kind IN ('plan_acceptance', 'integration', 'followup', 'group_review', 'plan_audit', 'adhoc')
            AND spec_entity_id IS NULL AND spec_entity_kind IS NULL)
    ) IS TRUE),
    CONSTRAINT ck_run_tasks__origin CHECK ((kind IN ('integration', 'followup', 'group_review')) = (origin IS NOT NULL)
        AND (origin IS NULL OR jsonb_typeof(origin) = 'object')),
    CONSTRAINT ck_run_tasks__status CHECK (status IN ('blocked', 'ready', 'assigned', 'executing', 'checking', 'manual_pending',
        'reviewing', 'rework_required', 'awaiting_decision', 'integrating', 'accepted', 'failed', 'cancelled', 'superseded', 'skipped')),
    CONSTRAINT ck_run_tasks__work_kind CHECK (work_kind IN ('code', 'docs', 'research', 'config', 'test', 'review', 'ops')),
    CONSTRAINT ck_run_tasks__review_mode CHECK (review_mode IN ('required', 'self', 'waived')),
    CONSTRAINT ck_run_tasks__review_profile CHECK (review_profile IS NULL OR review_profile ~ '^[a-z][a-z0-9-]{1,60}$'),
    CONSTRAINT ck_run_tasks__display_key CHECK (
        (kind = 'adhoc' AND display_key ~ '^ADHOC-[0-9]+$')
        OR (kind <> 'adhoc' AND display_key ~ '^(P[0-9]+(\.[0-9]+)?(/U[0-9]+|#gate)?|INT-[0-9]+|FU-[0-9]+|GR-[0-9]+|PLAN#accept|AUDIT)$')),
    CONSTRAINT ck_run_tasks__write_scope CHECK (declared_write_scope IS NULL OR jsonb_typeof(declared_write_scope) = 'array'),
    CONSTRAINT ck_run_tasks__counters CHECK (position >= 0 AND check_fix_rounds >= 0 AND review_rounds >= 0 AND attempt_count >= 0),
    CONSTRAINT ck_run_tasks__accepted CHECK (accepted_output_id IS NULL OR accepted_attempt_id IS NOT NULL),
    CONSTRAINT ck_run_tasks__blocking CHECK ((blocking_reason IS NULL) = (blocking_code IS NULL)
        AND (blocking_reason IS NULL OR blocking_reason ->> 'code' = blocking_code)
        AND (blocking_next_check_at IS NULL OR blocking_reason IS NOT NULL)),
    CONSTRAINT ck_run_tasks__blocking_code CHECK (blocking_code IS NULL OR blocking_code IN ('WAITING_OWNER', 'WAITING_ANSWER',
        'WAITING_ADVISOR', 'WAITING_MANUAL_CHECK', 'WAITING_APPROVAL', 'WAITING_PROVIDER', 'WAITING_BUDGET_RESET',
        'BLOCKED_BY_DEPENDENCY', 'BLOCKED_BY_MATERIAL', 'BLOCKED_BY_BUDGET', 'BLOCKED_BY_CAPABILITY', 'BLOCKED_BY_POLICY',
        'BLOCKED_BY_INTEGRATION', 'SUSPECTED_STALL', 'RECOVERING')),
    CONSTRAINT ck_run_tasks__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_run_tasks__run_id_status_position ON skm_execution.run_tasks (run_id, status, position);
CREATE INDEX ix_run_tasks__blocking_next_check_at ON skm_execution.run_tasks (blocking_next_check_at)
    WHERE blocking_next_check_at IS NOT NULL;
CREATE INDEX ix_run_tasks__workspace_id_blocking_code ON skm_execution.run_tasks (workspace_id, blocking_code)
    WHERE blocking_code IS NOT NULL;
CREATE INDEX ix_run_tasks__spec_entity_id ON skm_execution.run_tasks (spec_entity_id) WHERE spec_entity_id IS NOT NULL;

-- ---------------------------------------------------------------- task edges (append-only; synthetic tasks add rows)
CREATE TABLE skm_execution.run_task_edges (
    run_id               uuid   NOT NULL,
    dependent_task_id    uuid   NOT NULL,
    prerequisite_task_id uuid   NOT NULL,
    kind                 text   NOT NULL,
    reasons              text[] NOT NULL DEFAULT '{}',   -- EdgeReason of planning (UNIT_DEPENDS_ON, PHASE_MEMBER, …)
    CONSTRAINT pk_run_task_edges PRIMARY KEY (run_id, dependent_task_id, prerequisite_task_id),
    CONSTRAINT fk_run_task_edges__dependent FOREIGN KEY (run_id, dependent_task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_task_edges__prerequisite FOREIGN KEY (run_id, prerequisite_task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_run_task_edges__no_self CHECK (dependent_task_id <> prerequisite_task_id),
    CONSTRAINT ck_run_task_edges__kind CHECK (kind IN ('blocks', 'batch', 'integration', 'gate_member'))
);
CREATE INDEX ix_run_task_edges__run_id_prerequisite_task_id ON skm_execution.run_task_edges (run_id, prerequisite_task_id);
CREATE TRIGGER tg_run_task_edges__append_only BEFORE UPDATE OR DELETE ON skm_execution.run_task_edges
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

SELECT skm_core.grant_app('skm_execution', ARRAY['execution_bundles','readiness_reports','revision_visas','review_requests','run_reconfigurations','run_task_edges']::text[]);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON skm_execution.readiness_reports, skm_execution.review_requests,
            skm_execution.execution_bundles, skm_execution.run_reconfigurations, skm_execution.run_task_edges FROM skm_app;
    END IF;
END
$$;
