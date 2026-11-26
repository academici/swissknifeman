-- 0015_execution_checks_reviews: check executions and manual verdicts, reviews, findings with stable keys (C9),
-- resolutions, fix briefs (G4), acceptance decisions, deviation acceptances, evidence bindings.
-- Owner module: execution (spec/modules/execution.md §4.12–§4.14, §5.4, §5.8–§5.9, §11).
-- Every row points at an output of the same attempt and a check spec of the run's own revision.

-- ---------------------------------------------------------------- check executions
CREATE TABLE skm_execution.check_executions (
    id             uuid        NOT NULL,
    workspace_id   uuid        NOT NULL,
    run_id         uuid        NOT NULL,
    task_id        uuid        NOT NULL,
    attempt_id     uuid        NOT NULL,
    output_id      uuid        NOT NULL,
    revision_id    uuid        NOT NULL,                  -- = runs.revision_id (fk_check_executions__runs_revision)
    check_spec_id  uuid        NOT NULL,
    check_key      text        NOT NULL,
    kind           text        NOT NULL,
    required       boolean     NOT NULL,
    state          text        NOT NULL DEFAULT 'pending',
    exit_code      integer     NULL,
    summary        text        NOT NULL DEFAULT '',
    error_code     text        NULL,
    reused_from_id uuid        NULL,
    fingerprint    text        NOT NULL,
    round_no       integer     NOT NULL,
    started_at     timestamptz NULL,
    finished_at    timestamptz NULL,
    created_at     timestamptz NOT NULL,
    CONSTRAINT pk_check_executions PRIMARY KEY (id),
    CONSTRAINT uq_check_executions__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_check_executions__output_id_check_spec_id_round_no UNIQUE (output_id, check_spec_id, round_no),
    CONSTRAINT fk_check_executions__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_check_executions__attempt_outputs FOREIGN KEY (attempt_id, output_id)
        REFERENCES skm_execution.attempt_outputs (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_check_executions__runs_revision FOREIGN KEY (run_id, revision_id)
        REFERENCES skm_execution.runs (id, revision_id) ON DELETE RESTRICT,
    CONSTRAINT fk_check_executions__check_specs FOREIGN KEY (revision_id, check_spec_id)
        REFERENCES skm_planning.check_specs (revision_id, check_id) ON DELETE RESTRICT,
    CONSTRAINT fk_check_executions__reused_from FOREIGN KEY (workspace_id, reused_from_id)
        REFERENCES skm_execution.check_executions (workspace_id, id),
    CONSTRAINT ck_check_executions__kind CHECK (kind IN ('command', 'shell', 'manual', 'external')),
    CONSTRAINT ck_check_executions__state CHECK (state IN ('pending', 'running', 'passed', 'failed', 'manual_pending', 'error',
        'cancelled', 'unknown')),
    CONSTRAINT ck_check_executions__manual CHECK (kind = 'manual' OR state <> 'manual_pending'),
    CONSTRAINT ck_check_executions__reused CHECK (reused_from_id IS NULL OR (reused_from_id <> id AND state = 'passed')),
    CONSTRAINT ck_check_executions__summary CHECK (char_length(summary) <= 4000),
    CONSTRAINT ck_check_executions__fingerprint CHECK (fingerprint ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_check_executions__error_code CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{2,63}$'),
    CONSTRAINT ck_check_executions__round_no CHECK (round_no >= 1),
    CONSTRAINT ck_check_executions__finished CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX ix_check_executions__output_id ON skm_execution.check_executions (output_id);
CREATE INDEX ix_check_executions__task_id_round_no ON skm_execution.check_executions (task_id, round_no);
-- reuse of a green result with the same fingerprint (execution.checks.reuse_green)
CREATE INDEX ix_check_executions__fingerprint_check_spec_id_passed ON skm_execution.check_executions (fingerprint, check_spec_id)
    WHERE state = 'passed' AND reused_from_id IS NULL;

CREATE TABLE skm_execution.manual_check_verdicts (
    id                 uuid        NOT NULL,
    check_execution_id uuid        NOT NULL,
    workspace_id       uuid        NOT NULL,
    principal_id       uuid        NOT NULL,
    verdict            text        NOT NULL,
    comment            text        NOT NULL DEFAULT '',
    supersedes_id      uuid        NULL,
    recorded_at        timestamptz NOT NULL,
    CONSTRAINT pk_manual_check_verdicts PRIMARY KEY (id),
    CONSTRAINT uq_manual_check_verdicts__check_execution_id_id UNIQUE (check_execution_id, id),
    CONSTRAINT fk_manual_check_verdicts__check_executions FOREIGN KEY (workspace_id, check_execution_id)
        REFERENCES skm_execution.check_executions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_manual_check_verdicts__supersedes FOREIGN KEY (check_execution_id, supersedes_id)
        REFERENCES skm_execution.manual_check_verdicts (check_execution_id, id),
    CONSTRAINT ck_manual_check_verdicts__verdict CHECK (verdict IN ('pass', 'fail')),
    CONSTRAINT ck_manual_check_verdicts__comment CHECK (char_length(comment) <= 4000),
    CONSTRAINT ck_manual_check_verdicts__supersedes CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);
CREATE UNIQUE INDEX uq_manual_check_verdicts__supersedes_id ON skm_execution.manual_check_verdicts (supersedes_id)
    WHERE supersedes_id IS NOT NULL;   -- a verdict is superseded at most once: the chain stays linear

CREATE TABLE skm_execution.check_evidence_bindings (
    check_execution_id uuid        NOT NULL,
    workspace_id       uuid        NOT NULL,
    file_version_id    uuid        NOT NULL,
    role               text        NOT NULL,
    created_at         timestamptz NOT NULL,
    CONSTRAINT pk_check_evidence_bindings PRIMARY KEY (check_execution_id, file_version_id, role),
    CONSTRAINT fk_check_evidence_bindings__check_executions FOREIGN KEY (workspace_id, check_execution_id)
        REFERENCES skm_execution.check_executions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_check_evidence_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_check_evidence_bindings__role CHECK (role IN ('stdout', 'stderr', 'report', 'evidence'))
);

-- ---------------------------------------------------------------- reviews and findings
CREATE TABLE skm_execution.reviews (
    id                 uuid        NOT NULL,
    workspace_id       uuid        NOT NULL,
    run_id             uuid        NOT NULL,
    task_id            uuid        NOT NULL,
    attempt_id         uuid        NOT NULL,
    output_id          uuid        NOT NULL,
    round_no           integer     NOT NULL,             -- per task, over all attempts
    reviewer_kind      text        NOT NULL,
    reviewer_ref       jsonb       NOT NULL,             -- {step_id | principal_id, runtime_id?, model?}
    step_id            uuid        NULL,
    profile_key        text        NOT NULL,
    profile_version_id uuid        NULL,
    audit_scope        text        NOT NULL,
    state              text        NOT NULL DEFAULT 'started',
    verdict            text        NULL,
    freshness          text        NOT NULL DEFAULT 'fresh',
    base_output_id     uuid        NULL,                 -- round > 1: output of the previous review (any attempt of the task)
    residual_risk      text        NOT NULL DEFAULT '',
    created_at         timestamptz NOT NULL,
    completed_at       timestamptz NULL,
    CONSTRAINT pk_reviews PRIMARY KEY (id),
    CONSTRAINT uq_reviews__task_id_id UNIQUE (task_id, id),
    CONSTRAINT uq_reviews__task_id_round_no UNIQUE (task_id, round_no),
    CONSTRAINT uq_reviews__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT fk_reviews__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_reviews__attempt_outputs FOREIGN KEY (attempt_id, output_id)
        REFERENCES skm_execution.attempt_outputs (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_reviews__base_output FOREIGN KEY (task_id, base_output_id)
        REFERENCES skm_execution.attempt_outputs (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_reviews__attempt_steps FOREIGN KEY (attempt_id, step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    -- FK fk_reviews__resource_versions (profile_version_id -> skm_extensions.resource_versions) is added in
    -- 0018_extensions_resources (skm_extensions does not exist yet at this migration).
    CONSTRAINT ck_reviews__reviewer_kind CHECK ((reviewer_kind = 'agent' AND step_id IS NOT NULL AND profile_version_id IS NOT NULL)
        OR (reviewer_kind = 'human' AND step_id IS NULL)),
    CONSTRAINT ck_reviews__profile_key CHECK (profile_key ~ '^[a-z][a-z0-9-]{1,60}$'),
    CONSTRAINT ck_reviews__audit_scope CHECK (audit_scope IN ('corrected', 'full', 'range')),
    CONSTRAINT ck_reviews__state CHECK (state IN ('started', 'completed', 'failed')),
    CONSTRAINT ck_reviews__verdict CHECK ((verdict IS NOT NULL) = (state = 'completed')
        AND (verdict IS NULL OR verdict IN ('green', 'attention', 'red'))),
    CONSTRAINT ck_reviews__freshness CHECK (freshness IN ('fresh', 'findings_only')),
    CONSTRAINT ck_reviews__base_output CHECK ((round_no = 1) = (base_output_id IS NULL)),
    CONSTRAINT ck_reviews__completed_at CHECK ((completed_at IS NOT NULL) = (state <> 'started')),
    CONSTRAINT ck_reviews__round_no CHECK (round_no >= 1)
);
CREATE INDEX ix_reviews__output_id ON skm_execution.reviews (output_id);

CREATE TABLE skm_execution.review_findings (
    id                   uuid        NOT NULL,
    review_id            uuid        NOT NULL,
    task_id              uuid        NOT NULL,
    workspace_id         uuid        NOT NULL,
    local_id             text        NOT NULL,
    finding_key          text        NOT NULL,           -- fk-<16 hex>, stable between rounds (§5.8, C9)
    first_seen_review_id uuid        NOT NULL,
    severity             text        NOT NULL,
    confidence           text        NOT NULL,
    basis                text        NOT NULL DEFAULT 'correctness',
    category             text        NOT NULL,
    message              text        NOT NULL,
    failure_scenario     text        NOT NULL,
    location             jsonb       NOT NULL,           -- {mount, path, line_start?, line_end?}
    reproduction         jsonb       NULL,               -- {argv[], expected_exit?}
    state                text        NOT NULL DEFAULT 'open',
    row_version          bigint      NOT NULL DEFAULT 1,
    created_at           timestamptz NOT NULL,
    updated_at           timestamptz NOT NULL,
    CONSTRAINT pk_review_findings PRIMARY KEY (id),
    CONSTRAINT uq_review_findings__task_id_id UNIQUE (task_id, id),
    CONSTRAINT uq_review_findings__review_id_local_id UNIQUE (review_id, local_id),
    CONSTRAINT uq_review_findings__review_id_finding_key UNIQUE (review_id, finding_key),
    CONSTRAINT fk_review_findings__reviews FOREIGN KEY (task_id, review_id)
        REFERENCES skm_execution.reviews (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_findings__first_seen FOREIGN KEY (task_id, first_seen_review_id)
        REFERENCES skm_execution.reviews (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_review_findings__local_id CHECK (local_id ~ '^F[0-9]{1,3}$'),
    CONSTRAINT ck_review_findings__finding_key CHECK (finding_key ~ '^fk-[0-9a-f]{16}$'),
    CONSTRAINT ck_review_findings__severity CHECK (severity IN ('blocker', 'major', 'minor', 'nit')),
    CONSTRAINT ck_review_findings__confidence CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT ck_review_findings__basis CHECK (basis IN ('correctness', 'security', 'contract', 'test', 'maintainability', 'docs')),
    CONSTRAINT ck_review_findings__state CHECK (state IN ('open', 'confirmed', 'rejected', 'resolved', 'waived', 'deferred')),
    CONSTRAINT ck_review_findings__texts CHECK (char_length(message) BETWEEN 1 AND 2000 AND char_length(failure_scenario) BETWEEN 1 AND 3000
        AND char_length(category) BETWEEN 1 AND 82),
    CONSTRAINT ck_review_findings__json CHECK (jsonb_typeof(location) = 'object'
        AND (reproduction IS NULL OR jsonb_typeof(reproduction) = 'object')),
    CONSTRAINT ck_review_findings__row_version CHECK (row_version >= 1)
);
-- logical finding of a task = latest row per key
CREATE INDEX ix_review_findings__task_id_finding_key_created_at ON skm_execution.review_findings (task_id, finding_key, created_at DESC);

CREATE TABLE skm_execution.finding_resolutions (
    id               uuid        NOT NULL,
    finding_id       uuid        NOT NULL,
    task_id          uuid        NOT NULL,
    resolution_kind  text        NOT NULL,
    target_output_id uuid        NULL,
    comment          text        NOT NULL DEFAULT '',
    resolved_by      jsonb       NOT NULL,               -- {step_id} | {principal_id}
    at               timestamptz NOT NULL,
    CONSTRAINT pk_finding_resolutions PRIMARY KEY (id),
    CONSTRAINT fk_finding_resolutions__review_findings FOREIGN KEY (task_id, finding_id)
        REFERENCES skm_execution.review_findings (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_finding_resolutions__attempt_outputs FOREIGN KEY (task_id, target_output_id)
        REFERENCES skm_execution.attempt_outputs (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_finding_resolutions__kind CHECK (resolution_kind IN ('fixed', 'rejected_by_triage', 'waived', 'superseded')),
    CONSTRAINT ck_finding_resolutions__fixed CHECK (resolution_kind <> 'fixed' OR target_output_id IS NOT NULL),
    CONSTRAINT ck_finding_resolutions__resolved_by CHECK (jsonb_typeof(resolved_by) = 'object')
);
CREATE INDEX ix_finding_resolutions__finding_id ON skm_execution.finding_resolutions (finding_id);

CREATE TABLE skm_execution.review_evidence_bindings (
    review_id       uuid        NOT NULL,
    workspace_id    uuid        NOT NULL,
    file_version_id uuid        NOT NULL,
    role            text        NOT NULL,
    created_at      timestamptz NOT NULL,
    CONSTRAINT pk_review_evidence_bindings PRIMARY KEY (review_id, file_version_id, role),
    CONSTRAINT fk_review_evidence_bindings__reviews FOREIGN KEY (workspace_id, review_id)
        REFERENCES skm_execution.reviews (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_review_evidence_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_review_evidence_bindings__role CHECK (role IN ('report', 'diff', 'transcript', 'evidence'))
);

-- ---------------------------------------------------------------- fix briefs (G4; immutable documents fix-brief/v1)
CREATE TABLE skm_execution.fix_briefs (
    id                          uuid        NOT NULL,
    run_id                      uuid        NOT NULL,
    task_id                     uuid        NOT NULL,
    attempt_id                  uuid        NOT NULL,
    workspace_id                uuid        NOT NULL,
    source_review_id            uuid        NULL,
    source_check_round          integer     NULL,
    document                    jsonb       NOT NULL,   -- urn:skm:execution:fix-brief:v1
    digest                      text        NOT NULL,
    truncated                   boolean     NOT NULL,
    full_report_file_version_id uuid        NOT NULL,
    created_at                  timestamptz NOT NULL,
    CONSTRAINT pk_fix_briefs PRIMARY KEY (id),
    CONSTRAINT uq_fix_briefs__task_id_id UNIQUE (task_id, id),
    CONSTRAINT fk_fix_briefs__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_fix_briefs__reviews FOREIGN KEY (task_id, source_review_id)
        REFERENCES skm_execution.reviews (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_fix_briefs__file_versions FOREIGN KEY (workspace_id, full_report_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_fix_briefs__source CHECK ((source_review_id IS NULL) <> (source_check_round IS NULL)),
    CONSTRAINT ck_fix_briefs__digest CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_fix_briefs__document CHECK (jsonb_typeof(document) = 'object'
        AND document ->> 'schema' = 'urn:skm:execution:fix-brief:v1' AND octet_length(document::text) <= 1048576)
);
CREATE TRIGGER tg_fix_briefs__immutable BEFORE UPDATE OR DELETE ON skm_execution.fix_briefs
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- acceptance
CREATE TABLE skm_execution.acceptance_decisions (
    id           uuid        NOT NULL,
    workspace_id uuid        NOT NULL,
    run_id       uuid        NOT NULL,
    task_id      uuid        NOT NULL,
    attempt_id   uuid        NULL,                  -- NULL only for a carried-forward result
    output_id    uuid        NULL,
    decision     text        NOT NULL,
    clearance    text        NULL,
    actor_id     uuid        NOT NULL,              -- principal or the system principal `system` (SYSTEM_PRINCIPAL_ID)
    basis        jsonb       NOT NULL,              -- AcceptanceBasis (§4.14)
    decided_at   timestamptz NOT NULL,
    CONSTRAINT pk_acceptance_decisions PRIMARY KEY (id),
    CONSTRAINT fk_acceptance_decisions__run_tasks FOREIGN KEY (run_id, task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_acceptance_decisions__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_acceptance_decisions__attempt_outputs FOREIGN KEY (attempt_id, output_id)
        REFERENCES skm_execution.attempt_outputs (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_acceptance_decisions__decision CHECK (decision IN ('accepted', 'rejected')),
    CONSTRAINT ck_acceptance_decisions__clearance CHECK ((decision = 'accepted') = (clearance IS NOT NULL)
        AND (clearance IS NULL OR clearance IN ('green', 'findings_only', 'cleared_by_triage', 'deviation', 'self', 'waived', 'report'))),
    CONSTRAINT ck_acceptance_decisions__output CHECK (output_id IS NULL OR attempt_id IS NOT NULL),
    CONSTRAINT ck_acceptance_decisions__basis CHECK (jsonb_typeof(basis) = 'object')
);
CREATE INDEX ix_acceptance_decisions__task_id_decided_at ON skm_execution.acceptance_decisions (task_id, decided_at DESC);
CREATE TRIGGER tg_acceptance_decisions__append_only BEFORE UPDATE OR DELETE ON skm_execution.acceptance_decisions
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TABLE skm_execution.deviation_acceptances (
    id                    uuid        NOT NULL,
    workspace_id          uuid        NOT NULL,
    run_id                uuid        NOT NULL,
    task_id               uuid        NOT NULL,
    plan_id               uuid        NOT NULL,
    revision_id           uuid        NOT NULL,
    scope                 text        NOT NULL,
    criterion_id          uuid        NULL,
    criterion_entity_kind text        NOT NULL DEFAULT 'criterion',
    finding_id            uuid        NULL,
    reason                text        NOT NULL,
    approved_by           uuid        NOT NULL,
    approved_at           timestamptz NOT NULL,
    CONSTRAINT pk_deviation_acceptances PRIMARY KEY (id),
    CONSTRAINT fk_deviation_acceptances__run_tasks FOREIGN KEY (run_id, task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_deviation_acceptances__runs_revision FOREIGN KEY (run_id, plan_id, revision_id)
        REFERENCES skm_execution.runs (id, plan_id, revision_id) ON DELETE RESTRICT,
    CONSTRAINT fk_deviation_acceptances__criterion FOREIGN KEY (workspace_id, plan_id, revision_id, criterion_id, criterion_entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind) ON DELETE RESTRICT,
    CONSTRAINT fk_deviation_acceptances__review_findings FOREIGN KEY (task_id, finding_id)
        REFERENCES skm_execution.review_findings (task_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_deviation_acceptances__entity_kind CHECK (criterion_entity_kind = 'criterion'),
    CONSTRAINT ck_deviation_acceptances__scope CHECK (
        (scope = 'criterion' AND criterion_id IS NOT NULL AND finding_id IS NULL)
        OR (scope = 'finding' AND finding_id IS NOT NULL AND criterion_id IS NULL)
        OR (scope = 'attention_verdict' AND criterion_id IS NULL AND finding_id IS NULL)
        OR (scope = 'coverage' AND criterion_id IS NOT NULL AND finding_id IS NULL)),
    CONSTRAINT ck_deviation_acceptances__reason CHECK (char_length(reason) BETWEEN 1 AND 2000)
);
CREATE INDEX ix_deviation_acceptances__task_id ON skm_execution.deviation_acceptances (task_id);
CREATE TRIGGER tg_deviation_acceptances__append_only BEFORE UPDATE OR DELETE ON skm_execution.deviation_acceptances
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_manual_check_verdicts__append_only BEFORE UPDATE OR DELETE ON skm_execution.manual_check_verdicts
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();
CREATE TRIGGER tg_check_evidence_bindings__append_only BEFORE UPDATE OR DELETE ON skm_execution.check_evidence_bindings
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();
CREATE TRIGGER tg_review_evidence_bindings__append_only BEFORE UPDATE OR DELETE ON skm_execution.review_evidence_bindings
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();
CREATE TRIGGER tg_finding_resolutions__append_only BEFORE UPDATE OR DELETE ON skm_execution.finding_resolutions
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

SELECT skm_core.grant_app('skm_execution', ARRAY['step_notes','acceptance_decisions','attempt_file_bindings','attempt_outputs','check_evidence_bindings','deviation_acceptances','execution_bundles','finding_resolutions','fix_briefs','manual_check_verdicts','output_file_bindings','readiness_reports','review_evidence_bindings','review_requests','run_reconfigurations','run_task_edges']::text[]);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON skm_execution.manual_check_verdicts, skm_execution.check_evidence_bindings,
            skm_execution.review_evidence_bindings, skm_execution.finding_resolutions, skm_execution.fix_briefs,
            skm_execution.acceptance_decisions, skm_execution.deviation_acceptances FROM skm_app;
    END IF;
END
$$;
