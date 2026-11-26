-- 0016_execution_budgets_decisions_effects: budget accounts and reservations, decision requests/answers/records (G27),
-- external effects, integration slots, carry-forward of results, autopilot state (G8).
-- Owner module: execution (spec/modules/execution.md §4.15–§4.18, §4.21, §4.23, §5.6, §11).

-- ---------------------------------------------------------------- budgets
CREATE TABLE skm_execution.budget_accounts (
    id           uuid        NOT NULL,
    run_id       uuid        NOT NULL,
    workspace_id uuid        NOT NULL,
    scope        text        NOT NULL,
    task_id      uuid        NULL,
    dimension    text        NOT NULL,
    limit_value  numeric     NULL,                   -- NULL = no limit (config value 0)
    spent        numeric     NOT NULL DEFAULT 0,
    reserved     numeric     NOT NULL DEFAULT 0,
    row_version  bigint      NOT NULL DEFAULT 1,
    CONSTRAINT pk_budget_accounts PRIMARY KEY (id),
    CONSTRAINT fk_budget_accounts__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_budget_accounts__run_tasks FOREIGN KEY (run_id, task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_budget_accounts__scope CHECK ((scope = 'run' AND task_id IS NULL) OR (scope = 'task' AND task_id IS NOT NULL)),
    CONSTRAINT ck_budget_accounts__dimension CHECK (dimension IN ('usd', 'tokens', 'wall_seconds', 'attempts', 'review_rounds', 'tool_calls')),
    CONSTRAINT ck_budget_accounts__amounts CHECK (spent >= 0 AND reserved >= 0 AND (limit_value IS NULL OR limit_value > 0)),
    -- Reserve uses a conditional UPDATE; settlement must record actual usage even after an overrun.
    -- An over-limit account blocks further reservations and pauses the run; history is never discarded.
    CONSTRAINT ck_budget_accounts__row_version CHECK (row_version >= 1)
);
CREATE UNIQUE INDEX uq_budget_accounts__run_id_dimension_run ON skm_execution.budget_accounts (run_id, dimension) WHERE scope = 'run';
CREATE UNIQUE INDEX uq_budget_accounts__task_id_dimension_task ON skm_execution.budget_accounts (task_id, dimension) WHERE scope = 'task';

CREATE TABLE skm_execution.budget_reservations (
    id             uuid        NOT NULL,
    run_id         uuid        NOT NULL,
    workspace_id   uuid        NOT NULL,
    account_ids    uuid[]      NOT NULL,
    dimension      text        NOT NULL,
    attempt_id     uuid        NULL,
    step_id        uuid        NULL,
    amount         numeric     NOT NULL,
    state          text        NOT NULL DEFAULT 'reserved',
    settled_amount numeric     NULL,
    created_at     timestamptz NOT NULL,
    settled_at     timestamptz NULL,
    CONSTRAINT pk_budget_reservations PRIMARY KEY (id),
    CONSTRAINT fk_budget_reservations__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_budget_reservations__attempt_steps FOREIGN KEY (attempt_id, step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_budget_reservations__dimension CHECK (dimension IN ('usd', 'tokens', 'wall_seconds', 'attempts', 'review_rounds', 'tool_calls')),
    CONSTRAINT ck_budget_reservations__amount CHECK (amount > 0 AND (settled_amount IS NULL OR settled_amount >= 0)),
    CONSTRAINT ck_budget_reservations__state CHECK (state IN ('reserved', 'settled', 'released')),
    CONSTRAINT ck_budget_reservations__settled CHECK ((state = 'reserved') = (settled_at IS NULL)
        AND (state = 'settled') = (settled_amount IS NOT NULL)),
    CONSTRAINT ck_budget_reservations__accounts CHECK (cardinality(account_ids) BETWEEN 1 AND 4),
    CONSTRAINT ck_budget_reservations__step CHECK (step_id IS NULL OR attempt_id IS NOT NULL)
);
CREATE INDEX ix_budget_reservations__run_id_state ON skm_execution.budget_reservations (run_id, state);

-- ---------------------------------------------------------------- decision requests, answers, records
CREATE TABLE skm_execution.decision_requests (
    id                uuid        NOT NULL,
    workspace_id      uuid        NOT NULL,
    run_id            uuid        NOT NULL,          -- project-level autopilot escalations use the last run of the queue
    task_id           uuid        NULL,
    kind              text        NOT NULL,
    audience          text        NOT NULL,
    category          text        NULL,
    gate_categories   text[]      NOT NULL DEFAULT '{}',
    question_key      text        NULL,
    question_digest   text        NULL,
    revision          integer     NOT NULL DEFAULT 1,
    payload           jsonb       NOT NULL,
    attempt_id        uuid        NULL,
    stage_record_id   uuid        NULL,
    asked_by_step_id  uuid        NULL,
    input_part_digest text        NULL,
    blocking          boolean     NOT NULL,
    state             text        NOT NULL DEFAULT 'open',
    stale_answer      jsonb       NULL,
    deadline_at       timestamptz NULL,
    row_version       bigint      NOT NULL DEFAULT 1,
    created_at        timestamptz NOT NULL,
    updated_at        timestamptz NOT NULL,
    CONSTRAINT pk_decision_requests PRIMARY KEY (id),
    CONSTRAINT uq_decision_requests__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT fk_decision_requests__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_requests__run_tasks FOREIGN KEY (run_id, task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_requests__attempt_stages FOREIGN KEY (attempt_id, stage_record_id)
        REFERENCES skm_execution.attempt_stages (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_requests__attempt_steps FOREIGN KEY (attempt_id, asked_by_step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_decision_requests__kind CHECK (kind IN ('question', 'approval', 'manual_check', 'escalation', 'budget', 'readiness')),
    CONSTRAINT ck_decision_requests__audience CHECK (audience IN ('owner', 'advisor', 'consilium')),
    CONSTRAINT ck_decision_requests__category CHECK ((kind = 'question') = (category IS NOT NULL)
        AND (category IS NULL OR category IN ('local_reversible', 'bounded_ambiguity', 'cross_module', 'architectural',
            'authority_required', 'external_fact'))),
    CONSTRAINT ck_decision_requests__gate_categories CHECK (gate_categories <@ ARRAY['security', 'destructive', 'public_api',
        'scope_expansion', 'product', 'legal', 'cost', 'data_loss']::text[]),
    CONSTRAINT ck_decision_requests__question CHECK ((kind = 'question') = (question_key IS NOT NULL)
        AND (question_key IS NULL OR (question_key ~ '^qk-[0-9a-f]{16}$' AND question_digest ~ '^sha256:[0-9a-f]{64}$'
            AND input_part_digest IS NOT NULL))),
    CONSTRAINT ck_decision_requests__state CHECK (state IN ('open', 'answered', 'applied', 'assumed', 'denied', 'stale',
        'expired', 'cancelled')),
    CONSTRAINT ck_decision_requests__assumed CHECK (state <> 'assumed' OR NOT blocking),
    CONSTRAINT ck_decision_requests__revision CHECK (revision >= 1),
    CONSTRAINT ck_decision_requests__payload CHECK (jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 262144),
    CONSTRAINT ck_decision_requests__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_decision_requests__workspace_id_state_created_at ON skm_execution.decision_requests (workspace_id, state, created_at DESC, id);
CREATE INDEX ix_decision_requests__task_id_open ON skm_execution.decision_requests (task_id) WHERE state = 'open';
CREATE INDEX ix_decision_requests__run_id_state ON skm_execution.decision_requests (run_id, state);
CREATE INDEX ix_decision_requests__deadline_at_open ON skm_execution.decision_requests (deadline_at)
    WHERE state = 'open' AND deadline_at IS NOT NULL;

CREATE TABLE skm_execution.decision_answers (
    id                       uuid        NOT NULL,
    request_id               uuid        NOT NULL,
    workspace_id             uuid        NOT NULL,
    request_revision         integer     NOT NULL,
    answered_by_kind         text        NOT NULL,
    answered_by_principal_id uuid        NULL,
    answered_by_attempt_id   uuid        NULL,
    answered_by_step_id      uuid        NULL,
    value                    jsonb       NOT NULL,
    authority                jsonb       NOT NULL,   -- AuthorityEnvelope {mode, gate_categories[], confidence}
    answered_at              timestamptz NOT NULL,
    CONSTRAINT pk_decision_answers PRIMARY KEY (id),
    CONSTRAINT uq_decision_answers__request_id_request_revision UNIQUE (request_id, request_revision),
    CONSTRAINT fk_decision_answers__decision_requests FOREIGN KEY (workspace_id, request_id)
        REFERENCES skm_execution.decision_requests (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_answers__attempt_steps FOREIGN KEY (answered_by_attempt_id, answered_by_step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_decision_answers__by CHECK (
        (answered_by_kind = 'owner' AND answered_by_principal_id IS NOT NULL AND answered_by_step_id IS NULL)
        OR (answered_by_kind IN ('advisor', 'consilium') AND answered_by_step_id IS NOT NULL AND answered_by_principal_id IS NULL)
        OR (answered_by_kind IN ('policy', 'reuse') AND answered_by_principal_id IS NULL AND answered_by_step_id IS NULL)),
    CONSTRAINT ck_decision_answers__authority CHECK (jsonb_typeof(authority) = 'object'),
    CONSTRAINT ck_decision_answers__revision CHECK (request_revision >= 1)
);
CREATE TRIGGER tg_decision_answers__append_only BEFORE UPDATE OR DELETE ON skm_execution.decision_answers
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

CREATE TABLE skm_execution.decision_records (
    id                    uuid        NOT NULL,
    workspace_id          uuid        NOT NULL,
    project_id            uuid        NOT NULL,
    run_id                uuid        NOT NULL,
    task_id               uuid        NOT NULL,
    request_id            uuid        NOT NULL,
    category              text        NOT NULL,
    gate_categories       text[]      NOT NULL DEFAULT '{}',
    authority             text        NOT NULL,
    status                text        NOT NULL DEFAULT 'applied',
    selected_option       text        NULL,
    value                 jsonb       NOT NULL,
    rationale             text        NOT NULL,
    evidence_refs         jsonb       NOT NULL DEFAULT '[]',
    assumptions           jsonb       NOT NULL DEFAULT '[]',
    requires_owner        boolean     NOT NULL,
    question_key          text        NOT NULL,
    question_input_digest text        NOT NULL,
    created_at            timestamptz NOT NULL,
    superseded_at         timestamptz NULL,
    CONSTRAINT pk_decision_records PRIMARY KEY (id),
    CONSTRAINT fk_decision_records__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_records__run_tasks FOREIGN KEY (run_id, task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_records__decision_requests FOREIGN KEY (workspace_id, request_id)
        REFERENCES skm_execution.decision_requests (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_decision_records__category CHECK (category IN ('local_reversible', 'bounded_ambiguity', 'cross_module',
        'architectural', 'authority_required', 'external_fact')),
    CONSTRAINT ck_decision_records__authority CHECK (authority IN ('owner', 'advisor', 'consilium')),
    CONSTRAINT ck_decision_records__owner CHECK (NOT requires_owner OR authority = 'owner'),
    CONSTRAINT ck_decision_records__status CHECK ((status = 'superseded') = (superseded_at IS NOT NULL)
        AND status IN ('applied', 'superseded')),
    CONSTRAINT ck_decision_records__keys CHECK (question_key ~ '^qk-[0-9a-f]{16}$' AND question_input_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_decision_records__json CHECK (jsonb_typeof(evidence_refs) = 'array' AND jsonb_typeof(assumptions) = 'array'),
    CONSTRAINT ck_decision_records__rationale CHECK (char_length(rationale) BETWEEN 1 AND 2000)
);
-- reuse lookup: one applied record per (project, question_key)
CREATE UNIQUE INDEX uq_decision_records__project_id_question_key_applied ON skm_execution.decision_records (project_id, question_key)
    WHERE status = 'applied';

-- Only applied -> superseded may change; every other update or delete is refused.
CREATE FUNCTION skm_execution.tg_decision_records__supersede_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status <> 'applied' OR NEW.status <> 'superseded'
       OR (to_jsonb(NEW) - 'status' - 'superseded_at') <> (to_jsonb(OLD) - 'status' - 'superseded_at') THEN
        RAISE EXCEPTION 'skm_execution.decision_records: only applied -> superseded is allowed' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tg_decision_records__supersede_only BEFORE UPDATE OR DELETE ON skm_execution.decision_records
    FOR EACH ROW EXECUTE FUNCTION skm_execution.tg_decision_records__supersede_only();

-- ---------------------------------------------------------------- external effects
CREATE TABLE skm_execution.external_effects (
    id             uuid        NOT NULL,
    workspace_id   uuid        NOT NULL,
    run_id         uuid        NOT NULL,
    task_id        uuid        NOT NULL,
    attempt_id     uuid        NOT NULL,
    kind           text        NOT NULL,
    intent_id      uuid        NULL,
    request_digest text        NOT NULL,
    request        jsonb       NOT NULL DEFAULT '{}'::jsonb, -- immutable exact effect envelope; no credentials
    state          text        NOT NULL DEFAULT 'intended',
    receipt        jsonb       NULL,                 -- {response_digest?, ref?, at}
    row_version    bigint      NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL,
    updated_at     timestamptz NOT NULL,
    CONSTRAINT pk_external_effects PRIMARY KEY (id),
    CONSTRAINT fk_external_effects__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_external_effects__tool_intents FOREIGN KEY (workspace_id, intent_id)
        REFERENCES skm_policy.tool_intents (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_external_effects__kind CHECK (kind IN ('git_commit', 'git_push', 'pr_create', 'message', 'publish', 'fs_write_external')),
    CONSTRAINT ck_external_effects__intent CHECK (kind = 'git_commit' OR intent_id IS NOT NULL),
    CONSTRAINT ck_external_effects__state CHECK (state IN ('intended', 'executing', 'succeeded', 'failed', 'outcome_unknown')),
    CONSTRAINT ck_external_effects__receipt CHECK ((state = 'succeeded') <= (receipt IS NOT NULL)),
    CONSTRAINT ck_external_effects__request_digest CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_external_effects__request_object CHECK (jsonb_typeof(request) = 'object'),
    CONSTRAINT ck_external_effects__git_request CHECK (kind <> 'git_commit' OR
        request ?& ARRAY['repository_id', 'target_branch', 'before_sha', 'after_sha', 'tree_sha',
            'baseline_sha', 'output_ids', 'output_digests', 'commit_shas', 'assignment_fencing_token',
            'slot_fencing_token', 'writer_epoch_sha']),
    CONSTRAINT ck_external_effects__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_external_effects__outcome_unknown ON skm_execution.external_effects (updated_at) WHERE state = 'outcome_unknown';
CREATE INDEX ix_external_effects__attempt_id ON skm_execution.external_effects (attempt_id);

-- ---------------------------------------------------------------- integration slots (one holder per repository branch)
CREATE TABLE skm_execution.integration_slots (
    id                uuid        NOT NULL,
    workspace_id      uuid        NOT NULL,
    repository_id     uuid        NOT NULL,
    target_branch     text        NOT NULL,
    writer_host_id    uuid        NOT NULL, -- durable across slot release/expiry and across runs
    holder_attempt_id uuid        NULL,
    fencing_token     bigint      NOT NULL DEFAULT 0,
    expires_at        timestamptz NULL,
    row_version       bigint      NOT NULL DEFAULT 1,
    CONSTRAINT pk_integration_slots PRIMARY KEY (id),
    CONSTRAINT uq_integration_slots__repository_id_target_branch UNIQUE (repository_id, target_branch),
    CONSTRAINT fk_integration_slots__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_integration_slots__writer_host FOREIGN KEY (writer_host_id)
        REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT fk_integration_slots__attempts FOREIGN KEY (workspace_id, holder_attempt_id)
        REFERENCES skm_execution.attempts (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_integration_slots__holder CHECK ((holder_attempt_id IS NULL) = (expires_at IS NULL)),
    CONSTRAINT ck_integration_slots__branch CHECK (target_branch ~ '^[A-Za-z0-9._/-]{1,200}$' AND target_branch !~ '\.\.'),
    CONSTRAINT ck_integration_slots__counters CHECK (fencing_token >= 0 AND row_version >= 1)
);

-- ---------------------------------------------------------------- integration host of (run, repository) (K6)
-- Target writer_host_id is pinned globally in integration_slots before prepare; this run-local pin must agree.
-- Both pins determine required_host_id during schedule/claim. Releasing a slot never clears its target host pin.
CREATE TABLE skm_execution.run_integration_hosts (
    run_id        uuid        NOT NULL,
    workspace_id  uuid        NOT NULL,
    repository_id uuid        NOT NULL,
    host_id       uuid        NOT NULL,
    pinned_at     timestamptz NOT NULL,
    CONSTRAINT pk_run_integration_hosts PRIMARY KEY (run_id, repository_id),
    CONSTRAINT fk_run_integration_hosts__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_integration_hosts__repositories FOREIGN KEY (workspace_id, repository_id)
        REFERENCES skm_workspace.repositories (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_integration_hosts__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT
);
CREATE TRIGGER tg_run_integration_hosts__append_only BEFORE UPDATE OR DELETE ON skm_execution.run_integration_hosts
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- carry-forward of accepted results (manual, v2.0)
CREATE TABLE skm_execution.result_carry_forwards (
    id                   uuid        NOT NULL,
    workspace_id         uuid        NOT NULL,
    source_run_id        uuid        NOT NULL,
    source_task_id       uuid        NOT NULL,
    source_attempt_id    uuid        NOT NULL,
    source_output_id     uuid        NOT NULL,
    target_run_id        uuid        NOT NULL,
    target_task_id       uuid        NOT NULL,
    compatibility_digest text        NOT NULL,
    compatibility_inputs jsonb       NOT NULL,       -- canonical versioned source/target binding evidence (§execution 4.18)
    decision             text        NOT NULL,
    approved_by          uuid        NOT NULL,
    reason               text        NOT NULL,
    created_at           timestamptz NOT NULL,
    CONSTRAINT pk_result_carry_forwards PRIMARY KEY (id),
    CONSTRAINT fk_result_carry_forwards__source_attempt FOREIGN KEY (source_run_id, source_task_id, source_attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_result_carry_forwards__source_output FOREIGN KEY (source_attempt_id, source_output_id)
        REFERENCES skm_execution.attempt_outputs (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_result_carry_forwards__target_task FOREIGN KEY (target_run_id, target_task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_result_carry_forwards__source_run FOREIGN KEY (workspace_id, source_run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_result_carry_forwards__target_run FOREIGN KEY (workspace_id, target_run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_result_carry_forwards__runs CHECK (source_run_id <> target_run_id),
    CONSTRAINT ck_result_carry_forwards__decision CHECK (decision IN ('accepted', 'rejected')),
    CONSTRAINT ck_result_carry_forwards__digest CHECK (compatibility_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_result_carry_forwards__inputs CHECK ((
        jsonb_typeof(compatibility_inputs) = 'object'
        AND compatibility_inputs ?& ARRAY['schema_version', 'source', 'target']
        AND compatibility_inputs->>'schema_version' = '1'
        AND jsonb_typeof(compatibility_inputs->'source') = 'object'
        AND jsonb_typeof(compatibility_inputs->'target') = 'object') IS TRUE),
    CONSTRAINT ck_result_carry_forwards__reason CHECK (char_length(reason) BETWEEN 1 AND 2000)
);
CREATE UNIQUE INDEX uq_result_carry_forwards__target_task_id_accepted ON skm_execution.result_carry_forwards (target_task_id)
    WHERE decision = 'accepted';
CREATE TRIGGER tg_result_carry_forwards__append_only BEFORE UPDATE OR DELETE ON skm_execution.result_carry_forwards
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- autopilot state (one row per project, G8)
-- Stored state is never "disabled": the effective state is computed from execution.autopilot.allowed/enabled (§4.21).
CREATE TABLE skm_execution.autopilot_states (
    project_id         uuid        NOT NULL,
    workspace_id       uuid        NOT NULL,
    state              text        NOT NULL DEFAULT 'idle',
    emergency          boolean     NOT NULL DEFAULT false,
    current_run_id     uuid        NULL,
    session_started_at timestamptz NULL,
    counters           jsonb       NOT NULL DEFAULT '{"runs_started": 0, "auto_decisions": 0, "no_progress_runs": 0, "recoveries": 0, "infra_failures": 0, "last_blocker": null}',
    session_limits     jsonb       NOT NULL DEFAULT '{}',   -- invocation limits of start_autopilot, narrowing only (K2)
    stop_code          text        NULL,
    stop_detail        text        NULL,
    updated_by         uuid        NOT NULL,
    updated_at         timestamptz NOT NULL,
    row_version        bigint      NOT NULL DEFAULT 1,
    CONSTRAINT pk_autopilot_states PRIMARY KEY (project_id),
    CONSTRAINT fk_autopilot_states__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_autopilot_states__runs FOREIGN KEY (workspace_id, current_run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_autopilot_states__state CHECK (state IN ('idle', 'running', 'paused', 'draining', 'stopped')),
    CONSTRAINT ck_autopilot_states__emergency CHECK (NOT emergency OR state = 'stopped'),
    CONSTRAINT ck_autopilot_states__stop_code CHECK ((state = 'stopped') = (stop_code IS NOT NULL)
        AND (stop_code IS NULL OR stop_code ~ '^AUTOPILOT_[A-Z_]{2,40}$')),
    CONSTRAINT ck_autopilot_states__session CHECK (state NOT IN ('running', 'paused', 'draining') OR session_started_at IS NOT NULL),
    CONSTRAINT ck_autopilot_states__counters CHECK (jsonb_typeof(counters) = 'object' AND jsonb_typeof(session_limits) = 'object'),
    CONSTRAINT ck_autopilot_states__stop_detail CHECK (stop_detail IS NULL OR char_length(stop_detail) <= 2000),
    CONSTRAINT ck_autopilot_states__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_autopilot_states__active ON skm_execution.autopilot_states (state) WHERE state IN ('running', 'paused', 'draining');
CREATE INDEX ix_autopilot_states__emergency ON skm_execution.autopilot_states (project_id) WHERE emergency;

SELECT skm_core.grant_app('skm_execution', ARRAY['step_notes','acceptance_decisions','attempt_file_bindings','attempt_outputs','check_evidence_bindings','decision_answers','deviation_acceptances','execution_bundles','finding_resolutions','fix_briefs','manual_check_verdicts','output_file_bindings','readiness_reports','result_carry_forwards','review_evidence_bindings','review_requests','run_integration_hosts','run_reconfigurations','run_task_edges']::text[]);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON skm_execution.decision_answers, skm_execution.result_carry_forwards,
            skm_execution.run_integration_hosts, skm_execution.revision_visas FROM skm_app;
        REVOKE DELETE ON skm_execution.decision_records FROM skm_app;
    END IF;
END
$$;
