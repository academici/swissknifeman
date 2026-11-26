-- 0022_learning_core: processed activity (idempotency key and pathology history), lesson candidates, their confidence
-- signals and human reviews. Owner module: learning. FKs: skm_core (scopes), skm_access (principals),
-- skm_workspace (projects), skm_knowledge (lessons) — allowed: learning depends on execution and knowledge.
-- Execution rows are referenced by id only (run/task/attempt) to keep learning removable. Spec: spec/modules/learning.md.
CREATE SCHEMA IF NOT EXISTS skm_learning;

CREATE TABLE skm_learning.activity_records (
    id               uuid        PRIMARY KEY,
    workspace_id     uuid        NOT NULL,
    project_id       uuid        NOT NULL,
    scope_id         uuid        NOT NULL,
    source_kind      text        NOT NULL,
    source_key       text        NOT NULL,
    run_id           uuid        NULL,
    task_id          uuid        NULL,
    attempt_id       uuid        NULL,
    outcome          text        NOT NULL,
    task_outcome     text        NULL,
    exposure_coverage text       NOT NULL DEFAULT 'unknown',
    exposed_lesson_refs jsonb    NOT NULL DEFAULT '[]'::jsonb,
    detector_evidence jsonb      NOT NULL DEFAULT '[]'::jsonb,
    pathology_codes  text[]      NOT NULL DEFAULT '{}',
    summary_digest   text        NOT NULL,
    observed_at      timestamptz NOT NULL,
    created_at       timestamptz NOT NULL,
    CONSTRAINT fk_activity_records__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_activity_records__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT uq_activity_records__workspace_id_source_key UNIQUE (workspace_id, source_key),
    CONSTRAINT ck_activity_records__source_kind CHECK (source_kind IN ('attempt', 'client_session')),
    CONSTRAINT ck_activity_records__source_shape CHECK (
        (source_kind = 'attempt' AND attempt_id IS NOT NULL AND task_id IS NOT NULL AND run_id IS NOT NULL
            AND source_key = attempt_id::text)
        OR (source_kind = 'client_session' AND attempt_id IS NULL
            AND source_key ~ '^[a-z][a-z0-9_]{1,31}:[^\s]{1,200}$')),
    CONSTRAINT ck_activity_records__outcome CHECK (outcome IN ('success', 'failure', 'unknown')),
    CONSTRAINT ck_activity_records__task_outcome CHECK (task_outcome IS NULL OR task_outcome IN ('success', 'failure', 'unknown')),
    CONSTRAINT ck_activity_records__exposure CHECK (exposure_coverage IN ('complete', 'unknown')
        AND jsonb_typeof(exposed_lesson_refs) = 'array'),
    CONSTRAINT ck_activity_records__detector_evidence CHECK (jsonb_typeof(detector_evidence) = 'array'
        AND octet_length(detector_evidence::text) <= 65536),
    CONSTRAINT ck_activity_records__pathology_codes CHECK (pathology_codes <@ ARRAY[
        'file_reread', 'tool_error_loop', 'no_op_run', 'no_verify', 'cache_miss', 'retrieval_stuffing',
        'protected_write', 'static_context', 'fanout']::text[]),
    CONSTRAINT ck_activity_records__summary_digest CHECK (summary_digest ~ '^sha256:[0-9a-f]{64}$')
);
-- relapse rule: the last `pathology_window` records of a scope; stats per project
CREATE INDEX ix_activity_records__scope_id_observed_at ON skm_learning.activity_records (scope_id, observed_at DESC, id);
CREATE INDEX ix_activity_records__project_id_observed_at ON skm_learning.activity_records (project_id, observed_at DESC);

CREATE TABLE skm_learning.candidates (
    id                 uuid        PRIMARY KEY,
    workspace_id       uuid        NOT NULL,
    project_id         uuid        NOT NULL,
    scope_id           uuid        NOT NULL,
    display_key        text        NOT NULL,
    detector           text        NOT NULL,
    pathology_code     text        NULL,
    kind               text        NOT NULL,
    trigger            text        NOT NULL,
    action             text        NOT NULL,
    review_hint        text        NULL,
    meta               jsonb       NOT NULL DEFAULT '{}'::jsonb,
    evidence           jsonb       NOT NULL DEFAULT '[]'::jsonb,
    fingerprint        text        NOT NULL,
    state              text        NOT NULL DEFAULT 'observed',
    s_total            integer     NOT NULL DEFAULT 0,
    n_total            integer     NOT NULL DEFAULT 0,
    known_outcome_total integer    NOT NULL DEFAULT 0,
    unknown_outcome_total integer  NOT NULL DEFAULT 0,
    independent_known_total integer NOT NULL DEFAULT 0,
    independent_success_total integer NOT NULL DEFAULT 0,
    exposed_total      integer     NOT NULL DEFAULT 0,
    exposure_unknown_total integer NOT NULL DEFAULT 0,
    support_score      double precision NOT NULL DEFAULT 0,
    freshness          double precision NOT NULL DEFAULT 0,
    stale              boolean     NOT NULL DEFAULT false,
    tests_total        integer     NOT NULL DEFAULT 0,
    tests_passed       integer     NOT NULL DEFAULT 0,
    days_since         integer     NOT NULL DEFAULT 0,
    confidence         double precision NOT NULL DEFAULT 0,
    confidence_tier    text        NOT NULL DEFAULT 'none',
    curated_ready      boolean     NOT NULL DEFAULT false,
    conflicts_with_id  uuid        NULL,
    -- proposed_update/review_status/gates are views over append-only proposals/reviews/signals.
    lesson_id          uuid        NULL,
    recomputed_at      timestamptz NULL,
    row_version        bigint      NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL,
    updated_at         timestamptz NOT NULL,
    CONSTRAINT fk_candidates__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_candidates__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT uq_candidates__scope_id_id UNIQUE (scope_id, id),
    CONSTRAINT fk_candidates__conflicts_with FOREIGN KEY (scope_id, conflicts_with_id)
        REFERENCES skm_learning.candidates (scope_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_candidates__lessons FOREIGN KEY (lesson_id)
        REFERENCES skm_knowledge.lessons (id) ON DELETE RESTRICT,
    CONSTRAINT uq_candidates__scope_id_fingerprint UNIQUE (scope_id, fingerprint),
    CONSTRAINT uq_candidates__project_id_display_key UNIQUE (project_id, display_key),
    CONSTRAINT ck_candidates__display_key CHECK (display_key ~ '^LC-[1-9][0-9]*$'),
    CONSTRAINT ck_candidates__detector CHECK (
        detector IN ('resolved_failure', 'workaround', 'pathology', 'workflow_relaunch')),
    CONSTRAINT ck_candidates__pathology_code CHECK (
        (detector = 'pathology') = (pathology_code IS NOT NULL)
        AND (pathology_code IS NULL OR pathology_code IN ('file_reread', 'tool_error_loop', 'no_verify', 'protected_write'))),
    CONSTRAINT ck_candidates__kind CHECK (kind IN ('heuristic', 'procedure', 'gotcha')),
    CONSTRAINT ck_candidates__trigger CHECK (char_length(trigger) BETWEEN 1 AND 500),
    CONSTRAINT ck_candidates__action CHECK (char_length(action) BETWEEN 1 AND 1000),
    CONSTRAINT ck_candidates__review_hint CHECK (review_hint IS NULL OR char_length(review_hint) <= 300),
    CONSTRAINT ck_candidates__meta CHECK (jsonb_typeof(meta) = 'object' AND octet_length(meta::text) < 16384),
    CONSTRAINT ck_candidates__evidence CHECK (jsonb_typeof(evidence) = 'array' AND jsonb_array_length(evidence) <= 50),
    CONSTRAINT ck_candidates__fingerprint CHECK (fingerprint ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_candidates__state CHECK (state IN ('observed', 'candidate', 'promoted', 'rejected', 'deprecated')),
    CONSTRAINT ck_candidates__promoted CHECK ((state = 'promoted') = (lesson_id IS NOT NULL)),
    CONSTRAINT ck_candidates__counters CHECK (
        n_total >= 0 AND known_outcome_total >= 0 AND unknown_outcome_total >= 0
        AND known_outcome_total + unknown_outcome_total = n_total
        AND s_total BETWEEN 0 AND known_outcome_total
        AND independent_known_total BETWEEN 0 AND known_outcome_total
        AND independent_success_total BETWEEN 0 AND independent_known_total
        AND independent_success_total <= s_total
        AND exposed_total >= 0 AND exposure_unknown_total >= 0
        AND exposed_total + exposure_unknown_total <= n_total
        AND independent_known_total <= n_total - exposed_total - exposure_unknown_total
        AND tests_total >= 0 AND tests_passed BETWEEN 0 AND tests_total AND days_since >= 0),
    CONSTRAINT ck_candidates__confidence CHECK (confidence >= 0 AND confidence < 1
        AND support_score >= 0 AND support_score < 1 AND freshness BETWEEN 0 AND 1),
    CONSTRAINT ck_candidates__confidence_tier CHECK (confidence_tier IN ('none', 'tentative', 'moderate', 'strong', 'core')),
    CONSTRAINT ck_candidates__no_self_conflict CHECK (conflicts_with_id IS NULL OR conflicts_with_id <> id)
);
CREATE INDEX ix_candidates__scope_state_updated ON skm_learning.candidates (scope_id, state, updated_at DESC, id);
CREATE INDEX ix_candidates__workspace_id_id ON skm_learning.candidates (workspace_id, id);

-- Append-only real activity signals; review/promotion never inserts empirical evidence.
-- Recompute restores source/known/dependency counters and S/N from here at a fixed now.
CREATE TABLE skm_learning.signals (
    id                  uuid        PRIMARY KEY,
    candidate_id        uuid        NOT NULL,
    activity_record_id  uuid        NOT NULL,
    source              text        NOT NULL,
    sessions_total      integer     NOT NULL DEFAULT 1,
    sessions_known      integer     NOT NULL,
    sessions_success    integer     NOT NULL,
    evidence_dependency text        NOT NULL,
    tests_total         integer     NOT NULL DEFAULT 0,
    tests_passed        integer     NOT NULL DEFAULT 0,
    observed_at         timestamptz NOT NULL,
    created_at          timestamptz NOT NULL,
    CONSTRAINT fk_signals__candidates FOREIGN KEY (candidate_id)
        REFERENCES skm_learning.candidates (id) ON DELETE CASCADE,
    CONSTRAINT fk_signals__activity_records FOREIGN KEY (activity_record_id)
        REFERENCES skm_learning.activity_records (id) ON DELETE RESTRICT,
    CONSTRAINT uq_signals__identity UNIQUE NULLS NOT DISTINCT (candidate_id, activity_record_id, source),
    CONSTRAINT ck_signals__source CHECK (source = 'extract'),
    CONSTRAINT ck_signals__dependency CHECK (evidence_dependency IN ('independent', 'exposed', 'unknown')),
    CONSTRAINT ck_signals__counters CHECK (
        sessions_total = 1 AND sessions_known IN (0, 1) AND sessions_success BETWEEN 0 AND sessions_known
        AND tests_total >= 0 AND tests_passed BETWEEN 0 AND tests_total)
);
CREATE INDEX ix_signals__candidate_id_observed_at ON skm_learning.signals (candidate_id, observed_at, id);
-- UPDATE is forbidden; DELETE only by cascade from a removed candidate
CREATE TRIGGER tg_signals__append_only BEFORE UPDATE ON skm_learning.signals
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- Every distinct wording has its own candidate/signals. This relation never transfers support to the target.
CREATE TABLE skm_learning.candidate_proposals (
    id                  uuid PRIMARY KEY,
    scope_id            uuid NOT NULL,
    candidate_id        uuid NOT NULL,
    source_candidate_id uuid NOT NULL,
    source_activity_id  uuid NOT NULL,
    source_key          text NOT NULL,
    kind                text NOT NULL,
    trigger             text NOT NULL,
    action              text NOT NULL,
    fingerprint         text NOT NULL,
    detector_version    text NOT NULL,
    relation            text NOT NULL,
    observed_at         timestamptz NOT NULL,
    received_at         timestamptz NOT NULL,
    CONSTRAINT fk_candidate_proposals__target FOREIGN KEY (scope_id, candidate_id)
        REFERENCES skm_learning.candidates (scope_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_candidate_proposals__source FOREIGN KEY (scope_id, source_candidate_id)
        REFERENCES skm_learning.candidates (scope_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_candidate_proposals__activity FOREIGN KEY (source_activity_id)
        REFERENCES skm_learning.activity_records (id) ON DELETE RESTRICT,
    CONSTRAINT uq_candidate_proposals__identity UNIQUE (candidate_id, source_activity_id, fingerprint),
    CONSTRAINT ck_candidate_proposals__not_self CHECK (candidate_id <> source_candidate_id),
    CONSTRAINT ck_candidate_proposals__relation CHECK (relation IN ('update', 'conflict')),
    CONSTRAINT ck_candidate_proposals__kind CHECK (kind IN ('heuristic', 'procedure', 'gotcha')),
    CONSTRAINT ck_candidate_proposals__trigger CHECK (char_length(trigger) BETWEEN 1 AND 500),
    CONSTRAINT ck_candidate_proposals__action CHECK (char_length(action) BETWEEN 1 AND 1000),
    CONSTRAINT ck_candidate_proposals__fingerprint CHECK (fingerprint ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_candidate_proposals__detector_version CHECK (char_length(detector_version) BETWEEN 1 AND 100)
);
CREATE INDEX ix_candidate_proposals__target_observed
    ON skm_learning.candidate_proposals (candidate_id, observed_at DESC, source_key DESC, fingerprint DESC);
CREATE TRIGGER tg_candidate_proposals__append_only BEFORE UPDATE ON skm_learning.candidate_proposals
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TABLE skm_learning.candidate_reviews (
    id              uuid        PRIMARY KEY,
    candidate_id    uuid        NOT NULL,
    proposal_id     uuid        NULL,
    reviewer_id     uuid        NOT NULL,
    reviewer_kind   text        NOT NULL,
    verdict         text        NOT NULL,
    note            text        NULL,
    edited_trigger  text        NULL,
    edited_action   text        NULL,
    edited_kind     text        NULL,
    created_at      timestamptz NOT NULL,
    CONSTRAINT fk_candidate_reviews__candidates FOREIGN KEY (candidate_id)
        REFERENCES skm_learning.candidates (id) ON DELETE CASCADE,
    CONSTRAINT fk_candidate_reviews__proposals FOREIGN KEY (proposal_id)
        REFERENCES skm_learning.candidate_proposals (id) ON DELETE RESTRICT,
    CONSTRAINT fk_candidate_reviews__principals FOREIGN KEY (reviewer_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_candidate_reviews__reviewer_kind CHECK (reviewer_kind IN ('human', 'service', 'worker')),
    CONSTRAINT ck_candidate_reviews__verdict CHECK (verdict IN ('approve', 'reject', 'edit', 'comment')),
    CONSTRAINT ck_candidate_reviews__note CHECK (note IS NULL OR char_length(note) <= 2000),
    CONSTRAINT ck_candidate_reviews__edit CHECK (
        (verdict = 'edit') = (edited_trigger IS NOT NULL OR edited_action IS NOT NULL OR edited_kind IS NOT NULL)),
    CONSTRAINT ck_candidate_reviews__edited_kind CHECK (
        edited_kind IS NULL OR edited_kind IN ('heuristic', 'procedure', 'gotcha')),
    -- reject and edit change what a human sees later; worker (agent) and service principals may only approve or comment
    CONSTRAINT ck_candidate_reviews__human_only CHECK (reviewer_kind = 'human' OR verdict IN ('approve', 'comment'))
);
CREATE INDEX ix_candidate_reviews__candidate_id_created_at ON skm_learning.candidate_reviews (candidate_id, created_at);
CREATE TRIGGER tg_candidate_reviews__append_only BEFORE UPDATE ON skm_learning.candidate_reviews
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TRIGGER tg_activity_records__append_only BEFORE UPDATE ON skm_learning.activity_records
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

SELECT skm_core.grant_app('skm_learning', ARRAY['activity_records','signals','candidate_reviews','candidate_proposals']::text[]);
