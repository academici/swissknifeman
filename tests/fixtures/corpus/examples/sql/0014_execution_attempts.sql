-- 0014_execution_attempts: attempts, execution environments, stages, steps, assignments and leases, outputs,
-- file bindings of attempts and outputs, recovery records. Owner module: execution (spec/modules/execution.md §4.6–§4.11,
-- §4.22, §11). Children carry (run_id, task_id, attempt_id) and reference attempts by that triple, so a stage, step,
-- output or assignment can never belong to another task's attempt.

-- ---------------------------------------------------------------- attempts
CREATE TABLE skm_execution.attempts (
    id                 uuid        NOT NULL,
    run_id             uuid        NOT NULL,
    task_id            uuid        NOT NULL,
    workspace_id       uuid        NOT NULL,
    attempt_no         integer     NOT NULL,
    state              text        NOT NULL DEFAULT 'preparing',
    worker_id          uuid        NULL,
    host_id            uuid        NULL,
    environment_id     uuid        NULL,                 -- FK below (environments reference attempts first)
    current_output_id  uuid        NULL,                 -- FK below
    executor_route     jsonb       NULL,                 -- {runtime_id, model, effort}
    started_at         timestamptz NULL,
    finished_at        timestamptz NULL,
    end_reason         text        NULL,
    row_version        bigint      NOT NULL DEFAULT 1,
    created_at         timestamptz NOT NULL,
    CONSTRAINT pk_attempts PRIMARY KEY (id),
    CONSTRAINT uq_attempts__task_id_attempt_no UNIQUE (task_id, attempt_no),
    CONSTRAINT uq_attempts__task_id_id UNIQUE (task_id, id),
    CONSTRAINT uq_attempts__run_id_task_id_id UNIQUE (run_id, task_id, id),
    CONSTRAINT uq_attempts__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_attempts__workspace_run_id UNIQUE (workspace_id, run_id, id),
    CONSTRAINT fk_attempts__run_tasks FOREIGN KEY (run_id, task_id)
        REFERENCES skm_execution.run_tasks (run_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempts__workers FOREIGN KEY (workspace_id, worker_id)
        REFERENCES skm_workspace.workers (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempts__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT ck_attempts__attempt_no CHECK (attempt_no >= 1),
    CONSTRAINT ck_attempts__state CHECK (state IN ('preparing', 'running', 'waiting', 'submitted', 'completed',
        'ownership_lost', 'abandoned')),
    CONSTRAINT ck_attempts__finished CHECK ((finished_at IS NOT NULL) = (state IN ('completed', 'ownership_lost', 'abandoned'))
        AND (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)),
    CONSTRAINT ck_attempts__end_reason CHECK ((end_reason IS NOT NULL) = (finished_at IS NOT NULL)
        AND (end_reason IS NULL OR end_reason IN ('ACCEPTED', 'LEASE_LOST', 'RESTARTED', 'RETRY_NEW_ATTEMPT',
            'RECOVERY_NEW_ATTEMPT', 'OWNER_DECISION', 'GATE_REREVIEW', 'FAILED', 'SKIPPED', 'CANCELLED'))),
    CONSTRAINT ck_attempts__row_version CHECK (row_version >= 1)
);
CREATE INDEX ix_attempts__run_id_state ON skm_execution.attempts (run_id, state);
CREATE INDEX ix_attempts__host_id_state ON skm_execution.attempts (host_id, state) WHERE host_id IS NOT NULL;

-- ---------------------------------------------------------------- execution environments (one per attempt)
CREATE TABLE skm_execution.execution_environments (
    id                          uuid        NOT NULL,
    attempt_id                  uuid        NOT NULL,
    workspace_id                uuid        NOT NULL,
    host_id                     uuid        NOT NULL,
    kind                        text        NOT NULL,
    baseline                    jsonb       NOT NULL,     -- [{mount, repository_id, commit_sha, dirty_patch_file_version_id}]
    dirty_patch_file_version_id uuid        NULL,         -- existing_checkout only (G40)
    branch                      text        NOT NULL,
    local_locator               text        NOT NULL,     -- never returned without checkout.read_locator
    state                       text        NOT NULL DEFAULT 'preparing',
    created_at                  timestamptz NOT NULL,
    discarded_at                timestamptz NULL,
    removed_at                  timestamptz NULL,
    CONSTRAINT pk_execution_environments PRIMARY KEY (id),
    CONSTRAINT uq_execution_environments__attempt_id UNIQUE (attempt_id),
    CONSTRAINT uq_execution_environments__attempt_id_id UNIQUE (attempt_id, id),
    CONSTRAINT fk_execution_environments__attempts FOREIGN KEY (workspace_id, attempt_id)
        REFERENCES skm_execution.attempts (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_execution_environments__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT fk_execution_environments__file_versions FOREIGN KEY (workspace_id, dirty_patch_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_execution_environments__kind CHECK (kind IN ('git_worktree', 'existing_checkout', 'managed_clone')),
    CONSTRAINT ck_execution_environments__dirty_patch CHECK (dirty_patch_file_version_id IS NULL OR kind = 'existing_checkout'),
    CONSTRAINT ck_execution_environments__state CHECK (state IN ('preparing', 'ready', 'discarded', 'retained', 'removed')),
    CONSTRAINT ck_execution_environments__timestamps CHECK ((state IN ('discarded', 'removed')) = (discarded_at IS NOT NULL)
        AND (state = 'removed') = (removed_at IS NOT NULL)),
    CONSTRAINT ck_execution_environments__branch CHECK (branch ~ '^skm/attempt/[0-9a-f-]{36}$' OR kind = 'existing_checkout'),
    CONSTRAINT ck_execution_environments__locator CHECK (char_length(local_locator) BETWEEN 1 AND 4096
        AND position(E'\n' in local_locator) = 0),
    CONSTRAINT ck_execution_environments__baseline CHECK (jsonb_typeof(baseline) = 'array')
);
CREATE INDEX ix_execution_environments__host_id_state ON skm_execution.execution_environments (host_id, state, created_at);
-- K13: repositories of a project held by a live existing_checkout environment (busy until confirmed reap)
CREATE INDEX ix_execution_environments__existing_checkout_live ON skm_execution.execution_environments (attempt_id)
    WHERE kind = 'existing_checkout' AND state IN ('preparing', 'ready');

ALTER TABLE skm_execution.attempts ADD CONSTRAINT fk_attempts__execution_environments
    FOREIGN KEY (id, environment_id) REFERENCES skm_execution.execution_environments (attempt_id, id);

-- ---------------------------------------------------------------- stage records ("started" before execution)
CREATE TABLE skm_execution.attempt_stages (
    id            uuid        NOT NULL,
    run_id        uuid        NOT NULL,
    task_id       uuid        NOT NULL,
    attempt_id    uuid        NOT NULL,
    seq           integer     NOT NULL,
    stage_id      text        NOT NULL,
    stage_type    text        NOT NULL,
    round_no      integer     NOT NULL DEFAULT 1,
    mode          text        NOT NULL DEFAULT 'normal',
    retry_of_id   uuid        NULL,
    state         text        NOT NULL,
    input_digest  text        NOT NULL,
    outcome_kind  text        NULL,
    outcome       jsonb       NULL,
    error_code    text        NULL,
    fencing_token bigint      NOT NULL,                 -- 0 for control-plane stages and reused scout
    runtime_started_at  timestamptz NULL,               -- runtime_started handoff / first non-agent heartbeat (rule L, K4)
    process_identities jsonb       NOT NULL DEFAULT '[]'::jsonb, -- durable spawned unit ownership, including checks
    reused_from_step_id uuid        NULL,               -- reused scout result (§5.2); FK below (steps are created later)
    started_at    timestamptz NOT NULL,
    finished_at   timestamptz NULL,
    CONSTRAINT pk_attempt_stages PRIMARY KEY (id),
    CONSTRAINT uq_attempt_stages__attempt_id_seq UNIQUE (attempt_id, seq),
    CONSTRAINT uq_attempt_stages__attempt_id_id UNIQUE (attempt_id, id),
    CONSTRAINT fk_attempt_stages__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_stages__retry_of FOREIGN KEY (attempt_id, retry_of_id)
        REFERENCES skm_execution.attempt_stages (attempt_id, id),
    CONSTRAINT ck_attempt_stages__stage_id CHECK (stage_id ~ '^[a-z][a-z0-9_]{0,31}$'),
    CONSTRAINT ck_attempt_stages__stage_type CHECK (stage_type ~ '^[a-z][a-z0-9_]{0,40}$'),   -- built-in 10 + plugin types
    CONSTRAINT ck_attempt_stages__mode CHECK (mode IN ('normal', 'retry', 'rework', 'final_correction', 'continue_with_answer',
        'resume_interrupted', 'retriage_with_advice', 'reconcile')),
    CONSTRAINT ck_attempt_stages__retry_of CHECK ((retry_of_id IS NULL OR mode = 'retry') AND (retry_of_id IS NULL OR retry_of_id <> id)),
    CONSTRAINT ck_attempt_stages__state CHECK (state IN ('started', 'context_draft', 'running', 'completed', 'failed',
        'interrupted', 'skipped')),
    CONSTRAINT ck_attempt_stages__outcome_kind CHECK (outcome_kind IS NULL OR outcome_kind IN ('success', 'checks_failed',
        'checks_error', 'checks_unknown', 'manual_pending', 'tree_changed', 'verdict_green', 'verdict_attention', 'verdict_red',
        'question', 'blocked', 'write_scope_violation', 'result_invalid', 'runtime_error', 'conflict', 'approval_required',
        'outcome_unknown', 'held', 'accepted', 'not_acceptable', 'cancelled')),
    CONSTRAINT ck_attempt_stages__finished CHECK ((finished_at IS NOT NULL) = (state IN ('completed', 'failed', 'interrupted', 'skipped'))
        AND (finished_at IS NULL OR finished_at >= started_at)),
    CONSTRAINT ck_attempt_stages__completed_outcome CHECK (state <> 'completed' OR outcome_kind IS NOT NULL),
    CONSTRAINT ck_attempt_stages__input_digest CHECK (input_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_attempt_stages__error_code CHECK (error_code IS NULL OR error_code ~ '^[A-Z][A-Z0-9_]{2,63}$'),
    CONSTRAINT ck_attempt_stages__counters CHECK (seq >= 1 AND round_no >= 1 AND fencing_token >= 0),
    CONSTRAINT ck_attempt_stages__process_identities CHECK (jsonb_typeof(process_identities) = 'array'),
    CONSTRAINT ck_attempt_stages__runtime_started CHECK (runtime_started_at IS NULL OR runtime_started_at >= started_at),
    CONSTRAINT ck_attempt_stages__reused CHECK (reused_from_step_id IS NULL OR (stage_type = 'agent_step'
        AND state = 'completed' AND fencing_token = 0 AND runtime_started_at IS NULL))
);
-- at most one unfinished stage per attempt (§4.7)
CREATE UNIQUE INDEX uq_attempt_stages__attempt_id_active ON skm_execution.attempt_stages (attempt_id)
    WHERE state IN ('started', 'context_draft', 'running');
-- idempotent begin_stage lookup
CREATE INDEX ix_attempt_stages__attempt_id_stage_id_round_no_input_digest
    ON skm_execution.attempt_stages (attempt_id, stage_id, round_no, input_digest);
-- timeouts and stall detection scan unfinished stages
CREATE INDEX ix_attempt_stages__unfinished_started_at ON skm_execution.attempt_stages (started_at)
    WHERE state IN ('started', 'context_draft', 'running');

-- ---------------------------------------------------------------- steps (one role call through a runtime)
CREATE TABLE skm_execution.attempt_steps (
    id                         uuid        NOT NULL,
    attempt_id                 uuid        NOT NULL,
    stage_record_id            uuid        NOT NULL,
    workspace_id               uuid        NOT NULL,
    parent_step_id             uuid        NULL,          -- delegation reserve (G29)
    seq                        integer     NOT NULL,
    role                       text        NOT NULL,
    purpose                    text        NOT NULL DEFAULT 'primary',
    runtime_id                 text        NOT NULL,
    model                      text        NOT NULL,
    effort                     text        NULL,
    operation                  text        NOT NULL,      -- runtimes Admission.operation (RT-01)
    admission                  jsonb       NOT NULL,      -- serialized Admission + RouteDecision.resume_allowance
    route_source               text        NOT NULL,      -- RouteDecision.source
    route_reason               text        NOT NULL,      -- derived code for surfaces (§4.8)
    context_manifest_id        uuid        NOT NULL,
    session_mode               text        NOT NULL,
    session_ref                text        NULL,
    session_fingerprint        jsonb       NOT NULL,      -- SessionFingerprint (G7)
    session_fingerprint_digest text        NOT NULL,
    fresh_reason               text        NULL,
    state                      text        NOT NULL DEFAULT 'started',
    result                     jsonb       NULL,
    raw_result_file_version_id uuid        NULL,
    repairs                    jsonb       NOT NULL DEFAULT '[]',
    schema_errors              jsonb       NOT NULL DEFAULT '[]',
    usage                      jsonb       NULL,          -- urn:skm:runtimes:usage-report:v1 (K9)
    usage_status               text        NULL,          -- = usage.status
    usage_so_far               jsonb       NULL,          -- last renew_lease.progress.usage_so_far (K4)
    process_identity           jsonb       NULL,          -- process identity + durable typed ownership; agent step copy (K12)
    activity                   jsonb       NULL,          -- runtimes.summarize_tool_activity summary
    reuse_key                  text        NULL,          -- scout_reuse_key (§5.2)
    transcript_file_version_id uuid        NULL,
    last_progress_at           timestamptz NULL,
    error_code                 text        NULL,
    started_at                 timestamptz NOT NULL,
    finished_at                timestamptz NULL,
    CONSTRAINT pk_attempt_steps PRIMARY KEY (id),
    CONSTRAINT uq_attempt_steps__attempt_id_seq UNIQUE (attempt_id, seq),
    CONSTRAINT uq_attempt_steps__attempt_id_id UNIQUE (attempt_id, id),
    CONSTRAINT fk_attempt_steps__attempt_stages FOREIGN KEY (attempt_id, stage_record_id)
        REFERENCES skm_execution.attempt_stages (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_steps__parent FOREIGN KEY (attempt_id, parent_step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id),
    -- FK fk_attempt_steps__context_manifests (context_manifest_id -> skm_context.context_manifests) is added in
    -- 0019_context_manifests (skm_context does not exist yet at this migration).
    CONSTRAINT fk_attempt_steps__raw_result FOREIGN KEY (workspace_id, raw_result_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_steps__transcript FOREIGN KEY (workspace_id, transcript_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_attempt_steps__role CHECK (role IN ('scout', 'executor', 'reviewer', 'triager', 'advisor', 'researcher', 'registrar')),
    CONSTRAINT ck_attempt_steps__purpose CHECK (purpose IN ('primary', 'result_retry', 'triage_reverify', 'consilium_member',
        'consilium_critic')),
    CONSTRAINT ck_attempt_steps__parent CHECK (parent_step_id IS NULL OR parent_step_id <> id),
    CONSTRAINT ck_attempt_steps__operation CHECK (operation IN ('new_implementation', 'continuation', 'bounded_fix',
        'scope_change', 'review', 'final_close', 'research', 'advice', 'auxiliary')),
    CONSTRAINT ck_attempt_steps__admission CHECK (jsonb_typeof(admission) = 'object'),
    CONSTRAINT ck_attempt_steps__route_source CHECK (route_source IN ('previous_route', 'plan_route', 'role_routing',
        'role_fallback', 'preference')),
    CONSTRAINT ck_attempt_steps__route_reason CHECK (route_reason IN ('ROUTE_DEFAULT', 'ROUTE_FALLBACK', 'ROUTE_UPGRADED', 'ROUTE_OVERRIDE')),
    CONSTRAINT ck_attempt_steps__session_mode CHECK (session_mode IN ('new', 'resume')),
    CONSTRAINT ck_attempt_steps__fresh_reason CHECK (fresh_reason IS NULL OR (session_mode = 'new' AND fresh_reason IN (
        'ADMISSION_NO_RESUME', 'NO_PREVIOUS_SESSION', 'AUTHORITY_CHANGED', 'ENVIRONMENT_CHANGED', 'ROUTE_CHANGED', 'RESUME_UNSUPPORTED',
        'SCOPE_CHANGED', 'SESSION_CONTAMINATED', 'CONTEXT_BLOATED', 'NOT_A_CONTINUATION', 'SESSION_LOST',
        'OPERATOR_LIVE_CONTROL'))),
    CONSTRAINT ck_attempt_steps__fingerprint CHECK (jsonb_typeof(session_fingerprint) = 'object'
        AND session_fingerprint_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_attempt_steps__state CHECK (state IN ('started', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT ck_attempt_steps__finished CHECK ((finished_at IS NOT NULL) = (state <> 'started')
        AND (finished_at IS NULL OR finished_at >= started_at)),
    CONSTRAINT ck_attempt_steps__result CHECK ((result IS NOT NULL) <= (state = 'succeeded')),
    CONSTRAINT ck_attempt_steps__json CHECK (jsonb_typeof(repairs) = 'array' AND jsonb_typeof(schema_errors) = 'array'
        AND (usage IS NULL OR jsonb_typeof(usage) = 'object') AND (usage_so_far IS NULL OR jsonb_typeof(usage_so_far) = 'object')
        AND (process_identity IS NULL OR jsonb_typeof(process_identity) = 'object')
        AND (activity IS NULL OR (jsonb_typeof(activity) = 'object' AND octet_length(activity::text) <= 65536))),
    CONSTRAINT ck_attempt_steps__reuse_key CHECK (reuse_key IS NULL OR (role = 'scout' AND reuse_key ~ '^sha256:[0-9a-f]{64}$')),
    CONSTRAINT ck_attempt_steps__usage_status CHECK ((usage_status IS NULL) = (usage IS NULL)
        AND (usage_status IS NULL OR usage_status IN ('reported', 'estimated', 'unknown'))),
    CONSTRAINT ck_attempt_steps__seq CHECK (seq >= 1)
);
CREATE INDEX ix_attempt_steps__attempt_id_role_seq ON skm_execution.attempt_steps (attempt_id, role, seq DESC);
CREATE INDEX ix_attempt_steps__stage_record_id ON skm_execution.attempt_steps (stage_record_id);
CREATE INDEX ix_attempt_steps__session_fingerprint_digest ON skm_execution.attempt_steps (session_fingerprint_digest);
CREATE INDEX ix_attempt_steps__running_last_progress_at ON skm_execution.attempt_steps (last_progress_at) WHERE state = 'started';
-- reuse scout lookup (§5.2): succeeded scout steps by key
CREATE INDEX ix_attempt_steps__workspace_id_reuse_key ON skm_execution.attempt_steps (workspace_id, reuse_key)
    WHERE reuse_key IS NOT NULL AND state = 'succeeded';
-- the reused step may belong to another run of the same project: plain FK by step id (intentional cross-run reference)
ALTER TABLE skm_execution.attempt_stages ADD CONSTRAINT fk_attempt_stages__reused_from_step
    FOREIGN KEY (reused_from_step_id) REFERENCES skm_execution.attempt_steps (id) ON DELETE RESTRICT;

-- ---------------------------------------------------------------- assignments and leases
CREATE TABLE skm_execution.assignments (
    id                          uuid        NOT NULL,
    run_id                      uuid        NOT NULL,
    task_id                     uuid        NOT NULL,
    attempt_id                  uuid        NOT NULL,
    workspace_id                uuid        NOT NULL,
    state                       text        NOT NULL DEFAULT 'available',
    available_at                timestamptz NOT NULL,
    required_capabilities       text[]      NOT NULL DEFAULT '{}',
    required_host_id            uuid        NULL,          -- C2
    required_labels             text[]      NOT NULL DEFAULT '{}',   -- G16 (execution.workers.selector)
    environment_kind            text        NOT NULL DEFAULT 'git_worktree',
    required_isolation_profiles text[]      NOT NULL DEFAULT '{}',
    priority                    integer     NOT NULL,      -- = run_tasks.position
    last_fencing_token          bigint      NOT NULL DEFAULT 0,
    reap_stage_record_id        uuid        NULL,          -- generic L2 barrier for all units of interrupted stage
    reap_step_id                uuid        NULL,          -- rule L2: issued only to a worker that confirmed reap of this step (K12)
    row_version                 bigint      NOT NULL DEFAULT 1,
    created_at                  timestamptz NOT NULL,
    updated_at                  timestamptz NOT NULL,
    CONSTRAINT pk_assignments PRIMARY KEY (id),
    CONSTRAINT uq_assignments__attempt_id_id UNIQUE (attempt_id, id),
    CONSTRAINT fk_assignments__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignments__runs FOREIGN KEY (workspace_id, run_id)
        REFERENCES skm_execution.runs (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignments__hosts FOREIGN KEY (required_host_id) REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignments__reap_stage FOREIGN KEY (attempt_id, reap_stage_record_id)
        REFERENCES skm_execution.attempt_stages (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignments__reap_step FOREIGN KEY (attempt_id, reap_step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_assignments__reap CHECK ((reap_step_id IS NULL OR required_host_id IS NOT NULL)
        AND (reap_stage_record_id IS NULL OR required_host_id IS NOT NULL)),
    CONSTRAINT ck_assignments__state CHECK (state IN ('available', 'leased', 'completed', 'expired', 'cancelled')),
    CONSTRAINT ck_assignments__environment_kind CHECK (environment_kind IN ('git_worktree', 'existing_checkout', 'managed_clone')),
    CONSTRAINT ck_assignments__isolation CHECK (
        array_position(required_isolation_profiles, NULL) IS NULL
        AND array_to_string(required_isolation_profiles, ',') ~
            '^((none|worktree|landlock|container|[a-z0-9_.-]+:[a-z0-9_-]+)(,(none|worktree|landlock|container|[a-z0-9_.-]+:[a-z0-9_-]+))*)?$'
    ),
    CONSTRAINT ck_assignments__labels CHECK (cardinality(required_labels) <= 32 AND cardinality(required_capabilities) <= 64),
    CONSTRAINT ck_assignments__counters CHECK (priority >= 0 AND last_fencing_token >= 0 AND row_version >= 1)
);
-- claim: small partial index; array filters run on its rows (§11.2)
CREATE INDEX ix_assignments__claim ON skm_execution.assignments (priority, available_at, id) WHERE state = 'available';
-- at most one live assignment per attempt
CREATE UNIQUE INDEX uq_assignments__attempt_id_live ON skm_execution.assignments (attempt_id) WHERE state IN ('available', 'leased');
CREATE INDEX ix_assignments__run_id_state ON skm_execution.assignments (run_id, state);

CREATE TABLE skm_execution.assignment_leases (
    assignment_id     uuid        NOT NULL,
    workspace_id      uuid        NOT NULL,
    worker_id         uuid        NOT NULL,
    fencing_token     bigint      NOT NULL,
    expires_at        timestamptz NOT NULL,
    last_heartbeat_at timestamptz NOT NULL,
    process_identity  jsonb       NULL,                  -- process identity + durable typed ownership from renew_lease (§5.17)
    CONSTRAINT pk_assignment_leases PRIMARY KEY (assignment_id),
    CONSTRAINT fk_assignment_leases__assignments FOREIGN KEY (assignment_id)
        REFERENCES skm_execution.assignments (id) ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_leases__workers FOREIGN KEY (workspace_id, worker_id)
        REFERENCES skm_workspace.workers (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_assignment_leases__fencing_token CHECK (fencing_token >= 1),
    CONSTRAINT ck_assignment_leases__heartbeat CHECK (last_heartbeat_at <= expires_at),
    CONSTRAINT ck_assignment_leases__process_identity CHECK (process_identity IS NULL OR jsonb_typeof(process_identity) = 'object')
);
CREATE INDEX ix_assignment_leases__expires_at ON skm_execution.assignment_leases (expires_at);

-- Defence in depth for fencing: a lease always carries the current token of its assignment, which is leased.
CREATE FUNCTION skm_execution.tg_assignment_leases__fence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE a record;
BEGIN
    SELECT state, last_fencing_token, workspace_id INTO a FROM skm_execution.assignments WHERE id = NEW.assignment_id;
    IF a.state <> 'leased' OR a.last_fencing_token <> NEW.fencing_token OR a.workspace_id <> NEW.workspace_id THEN
        RAISE EXCEPTION 'skm_execution.assignment_leases: lease token % does not match assignment % (state %, token %)',
            NEW.fencing_token, NEW.assignment_id, a.state, a.last_fencing_token USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tg_assignment_leases__fence BEFORE INSERT OR UPDATE OF fencing_token, assignment_id
    ON skm_execution.assignment_leases FOR EACH ROW EXECUTE FUNCTION skm_execution.tg_assignment_leases__fence();

-- D-REG-9: append-only notes are proposals; only advance() creates DecisionRequests.
CREATE TABLE skm_execution.step_notes (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    run_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    step_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    fencing_token bigint NOT NULL,
    kind text NOT NULL,
    text text NOT NULL,
    options jsonb NULL,
    why_blocked text NULL,
    urgency text NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT fk_step_notes__run FOREIGN KEY (workspace_id, run_id) REFERENCES skm_execution.runs (workspace_id, id),
    CONSTRAINT fk_step_notes__attempt FOREIGN KEY (workspace_id, run_id, attempt_id) REFERENCES skm_execution.attempts (workspace_id, run_id, id),
    CONSTRAINT fk_step_notes__step FOREIGN KEY (attempt_id, step_id) REFERENCES skm_execution.attempt_steps (attempt_id, id),
    CONSTRAINT fk_step_notes__assignment FOREIGN KEY (attempt_id, assignment_id) REFERENCES skm_execution.assignments (attempt_id, id),
    CONSTRAINT ck_step_notes__fence CHECK (fencing_token >= 1),
    CONSTRAINT ck_step_notes__kind CHECK (kind IN ('progress','assumption','risk','question')),
    CONSTRAINT ck_step_notes__text CHECK (char_length(text) BETWEEN 1 AND 20000),
    CONSTRAINT ck_step_notes__options CHECK (options IS NULL OR (kind = 'question' AND jsonb_typeof(options) = 'array' AND octet_length(options::text) <= 65536)),
    CONSTRAINT ck_step_notes__why CHECK (why_blocked IS NULL OR (kind = 'question' AND char_length(why_blocked) <= 2000)),
    CONSTRAINT ck_step_notes__urgency CHECK (urgency IS NULL OR (kind = 'question' AND urgency IN ('normal','blocking')))
);
CREATE INDEX ix_step_notes__step_created ON skm_execution.step_notes (step_id, created_at, id);
CREATE TRIGGER tg_step_notes__append_only BEFORE UPDATE OR DELETE ON skm_execution.step_notes
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- ---------------------------------------------------------------- outputs (immutable)
CREATE TABLE skm_execution.attempt_outputs (
    id                    uuid        NOT NULL,
    attempt_id            uuid        NOT NULL,
    task_id               uuid        NOT NULL,
    run_id                uuid        NOT NULL,
    workspace_id          uuid        NOT NULL,
    seq                   integer     NOT NULL,
    source                text        NOT NULL,
    manifest              jsonb       NOT NULL,          -- OutputManifest (§4.11)
    manifest_digest       text        NOT NULL,
    tree_digest           text        NOT NULL,
    outside_write_scope   jsonb       NOT NULL DEFAULT '[]',
    excluded_paths        jsonb       NOT NULL DEFAULT '[]',
    produced_by_step_id   uuid        NULL,
    patch_file_version_id uuid        NULL,
    sealed_at             timestamptz NOT NULL,
    CONSTRAINT pk_attempt_outputs PRIMARY KEY (id),
    CONSTRAINT uq_attempt_outputs__attempt_id_seq UNIQUE (attempt_id, seq),
    CONSTRAINT uq_attempt_outputs__attempt_id_id UNIQUE (attempt_id, id),
    CONSTRAINT uq_attempt_outputs__task_id_id UNIQUE (task_id, id),
    CONSTRAINT fk_attempt_outputs__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_outputs__attempt_steps FOREIGN KEY (attempt_id, produced_by_step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_outputs__file_versions FOREIGN KEY (workspace_id, patch_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_attempt_outputs__source CHECK ((source = 'executor' AND produced_by_step_id IS NOT NULL)
        OR (source = 'range' AND produced_by_step_id IS NULL)),
    CONSTRAINT ck_attempt_outputs__digests CHECK (manifest_digest ~ '^sha256:[0-9a-f]{64}$' AND tree_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_attempt_outputs__json CHECK (jsonb_typeof(manifest) = 'object' AND jsonb_typeof(outside_write_scope) = 'array'
        AND jsonb_typeof(excluded_paths) = 'array'),
    CONSTRAINT ck_attempt_outputs__seq CHECK (seq >= 1)
);
CREATE TRIGGER tg_attempt_outputs__immutable BEFORE UPDATE OR DELETE ON skm_execution.attempt_outputs
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

ALTER TABLE skm_execution.attempts ADD CONSTRAINT fk_attempts__current_output
    FOREIGN KEY (id, current_output_id) REFERENCES skm_execution.attempt_outputs (attempt_id, id);
ALTER TABLE skm_execution.run_tasks ADD CONSTRAINT fk_run_tasks__current_attempt
    FOREIGN KEY (id, current_attempt_id) REFERENCES skm_execution.attempts (task_id, id);
ALTER TABLE skm_execution.run_tasks ADD CONSTRAINT fk_run_tasks__accepted_attempt
    FOREIGN KEY (id, accepted_attempt_id) REFERENCES skm_execution.attempts (task_id, id);
ALTER TABLE skm_execution.run_tasks ADD CONSTRAINT fk_run_tasks__accepted_output
    FOREIGN KEY (accepted_attempt_id, accepted_output_id) REFERENCES skm_execution.attempt_outputs (attempt_id, id);

-- ---------------------------------------------------------------- file bindings (append-only)
CREATE TABLE skm_execution.attempt_file_bindings (
    attempt_id      uuid        NOT NULL,
    workspace_id    uuid        NOT NULL,
    file_version_id uuid        NOT NULL,
    role            text        NOT NULL,
    step_id         uuid        NULL,
    created_at      timestamptz NOT NULL,
    CONSTRAINT pk_attempt_file_bindings PRIMARY KEY (attempt_id, file_version_id, role),
    CONSTRAINT fk_attempt_file_bindings__attempts FOREIGN KEY (workspace_id, attempt_id)
        REFERENCES skm_execution.attempts (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_file_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_attempt_file_bindings__attempt_steps FOREIGN KEY (attempt_id, step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_attempt_file_bindings__role CHECK (role IN ('evidence', 'transcript', 'prompt', 'raw_result', 'patch',
        'fix_brief', 'diagnostic', 'coverage_report'))
);
CREATE INDEX ix_attempt_file_bindings__file_version_id ON skm_execution.attempt_file_bindings (file_version_id);

CREATE TABLE skm_execution.output_file_bindings (
    output_id       uuid        NOT NULL,
    attempt_id      uuid        NOT NULL,
    workspace_id    uuid        NOT NULL,
    file_version_id uuid        NOT NULL,
    role            text        NOT NULL,
    created_at      timestamptz NOT NULL,
    CONSTRAINT pk_output_file_bindings PRIMARY KEY (output_id, file_version_id, role),
    CONSTRAINT fk_output_file_bindings__attempt_outputs FOREIGN KEY (attempt_id, output_id)
        REFERENCES skm_execution.attempt_outputs (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_output_file_bindings__file_versions FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_output_file_bindings__role CHECK (role IN ('patch', 'evidence', 'coverage_report'))
);

-- ---------------------------------------------------------------- recovery records (G10)
-- Open while the procedure runs (outcome NULL); frozen once the outcome is set.
CREATE TABLE skm_execution.run_recoveries (
    id                       uuid        NOT NULL,
    run_id                   uuid        NOT NULL,
    task_id                  uuid        NOT NULL,
    attempt_id               uuid        NOT NULL,
    stage_record_id          uuid        NOT NULL,
    step_id                  uuid        NULL,
    workspace_id             uuid        NOT NULL,
    trigger                  text        NOT NULL,
    steps_done               jsonb       NOT NULL DEFAULT '[]',   -- [{step, at, result}] of §5.17
    snapshot_file_version_id uuid        NULL,
    outcome                  text        NULL,
    reason_codes             text[]      NOT NULL DEFAULT '{}',
    at                       timestamptz NOT NULL,
    finished_at              timestamptz NULL,
    CONSTRAINT pk_run_recoveries PRIMARY KEY (id),
    CONSTRAINT fk_run_recoveries__attempts FOREIGN KEY (run_id, task_id, attempt_id)
        REFERENCES skm_execution.attempts (run_id, task_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_recoveries__attempt_stages FOREIGN KEY (attempt_id, stage_record_id)
        REFERENCES skm_execution.attempt_stages (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_recoveries__attempt_steps FOREIGN KEY (attempt_id, step_id)
        REFERENCES skm_execution.attempt_steps (attempt_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_run_recoveries__file_versions FOREIGN KEY (workspace_id, snapshot_file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_run_recoveries__trigger CHECK (trigger IN ('hung', 'suspected_stall', 'orphaned', 'lease_expired')),
    CONSTRAINT ck_run_recoveries__outcome CHECK (outcome IS NULL OR outcome IN ('retried', 'new_attempt', 'escalated', 'not_needed')),
    CONSTRAINT ck_run_recoveries__finished CHECK ((outcome IS NULL) = (finished_at IS NULL)),
    CONSTRAINT ck_run_recoveries__steps CHECK (jsonb_typeof(steps_done) = 'array')
);
CREATE INDEX ix_run_recoveries__run_id_at ON skm_execution.run_recoveries (run_id, at);
CREATE UNIQUE INDEX uq_run_recoveries__stage_record_id_open ON skm_execution.run_recoveries (stage_record_id) WHERE outcome IS NULL;

CREATE FUNCTION skm_execution.tg_run_recoveries__frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.outcome IS NOT NULL THEN
        RAISE EXCEPTION 'skm_execution.run_recoveries: finished recovery records are immutable' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tg_run_recoveries__frozen BEFORE UPDATE OR DELETE ON skm_execution.run_recoveries
    FOR EACH ROW EXECUTE FUNCTION skm_execution.tg_run_recoveries__frozen();

CREATE TRIGGER tg_attempt_file_bindings__append_only BEFORE UPDATE OR DELETE ON skm_execution.attempt_file_bindings
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();
CREATE TRIGGER tg_output_file_bindings__append_only BEFORE UPDATE OR DELETE ON skm_execution.output_file_bindings
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

SELECT skm_core.grant_app('skm_execution', ARRAY['step_notes','attempt_file_bindings','attempt_outputs','execution_bundles','output_file_bindings','readiness_reports','review_requests','run_reconfigurations','run_task_edges']::text[]);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON skm_execution.attempt_outputs, skm_execution.attempt_file_bindings,
            skm_execution.output_file_bindings FROM skm_app;
    END IF;
END
$$;

-- Pending adjustments are consumed atomically when the next agent step is prepared.
ALTER TABLE skm_execution.run_tasks
    ADD COLUMN live_controls jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(live_controls) = 'object' AND octet_length(live_controls::text) <= 16384);

CREATE TABLE skm_execution.incident_gates (
    id uuid PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES skm_execution.run_tasks (id),
    stop_after uuid NULL REFERENCES skm_execution.attempt_steps (id),
    fencing_token bigint NULL CHECK (fencing_token > 0),
    kind text NOT NULL CHECK (kind IN ('reroute_task', 'override_actor', 'steer_task', 'abort_step', 'budget_breaker')),
    actor_id uuid NOT NULL,
    reason text NOT NULL CHECK (char_length(reason) BETWEEN 1 AND 2000),
    details jsonb NOT NULL CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL,
    CHECK ((kind IN ('abort_step', 'budget_breaker')) = (stop_after IS NOT NULL)),
    CHECK (stop_after IS NULL OR fencing_token IS NOT NULL)
);

CREATE TRIGGER tg_incident_gates__append_only
    BEFORE UPDATE OR DELETE ON skm_execution.incident_gates
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();
