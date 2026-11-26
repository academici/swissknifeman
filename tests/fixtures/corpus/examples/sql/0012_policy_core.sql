-- 0012_policy_core: tool intents (external effects), approvals, tool decision audit.
-- Owner module: policy. FKs: skm_core, skm_access, skm_workspace (module graph: policy depends on access, workspace).
-- No FK to execution: execution sits above policy and references tool_intents itself (external_effects.intent_id).
CREATE SCHEMA IF NOT EXISTS skm_policy;

CREATE TABLE skm_policy.tool_intents (
    id               uuid        PRIMARY KEY,
    workspace_id     uuid        NOT NULL,
    scope_id         uuid        NOT NULL,
    subject_ref      text        NOT NULL,
    actor_id         uuid        NOT NULL,
    kind             text        NOT NULL,
    normalized_args  jsonb       NOT NULL,
    args_digest      text        NOT NULL,
    risk             text        NOT NULL,
    reason           text        NOT NULL,
    state            text        NOT NULL DEFAULT 'proposed',
    denied_reason    text        NULL,
    receipt          jsonb       NULL,
    row_version      bigint      NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL,
    expires_at       timestamptz NOT NULL,
    CONSTRAINT uq_tool_intents__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT fk_tool_intents__workspaces FOREIGN KEY (workspace_id)
        REFERENCES skm_workspace.workspaces (id) ON DELETE RESTRICT,
    CONSTRAINT fk_tool_intents__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_tool_intents__principals FOREIGN KEY (actor_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_tool_intents__kind CHECK (kind IN ('git_commit', 'git_push', 'pr_create', 'message', 'publish', 'fs_write_external')),
    CONSTRAINT ck_tool_intents__risk CHECK (risk IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT ck_tool_intents__state CHECK (state IN (
        'proposed', 'approved', 'denied', 'expired', 'executing', 'succeeded', 'failed', 'outcome_unknown')),
    CONSTRAINT ck_tool_intents__denied_reason CHECK (
        (state = 'denied') = (denied_reason IS NOT NULL)
        AND (denied_reason IS NULL OR denied_reason IN ('not_permitted', 'forbidden_args', 'by_approver', 'revoked'))),
    CONSTRAINT ck_tool_intents__args_digest CHECK (args_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_tool_intents__normalized_args CHECK (jsonb_typeof(normalized_args) = 'object'),
    CONSTRAINT ck_tool_intents__subject_ref CHECK (char_length(subject_ref) BETWEEN 1 AND 200),
    CONSTRAINT ck_tool_intents__reason CHECK (char_length(reason) BETWEEN 1 AND 1000),
    CONSTRAINT ck_tool_intents__receipt CHECK (
        receipt IS NULL OR (jsonb_typeof(receipt) = 'object' AND octet_length(receipt::text) <= 16384)),
    CONSTRAINT ck_tool_intents__row_version CHECK (row_version >= 1),
    CONSTRAINT ck_tool_intents__expiry CHECK (expires_at > created_at)
);
-- one active intent per identical effect in a scope (propose_intent returns the existing one)
CREATE UNIQUE INDEX uq_tool_intents__scope_id_kind_args_digest_active
    ON skm_policy.tool_intents (scope_id, kind, args_digest)
    WHERE state IN ('proposed', 'approved', 'executing');
CREATE INDEX ix_tool_intents__workspace_id_created_at ON skm_policy.tool_intents (workspace_id, created_at, id);
CREATE INDEX ix_tool_intents__scope_id_state ON skm_policy.tool_intents (scope_id, state);
-- expire_intents scans only open intents
CREATE INDEX ix_tool_intents__expires_at_open ON skm_policy.tool_intents (expires_at)
    WHERE state IN ('proposed', 'approved');

CREATE TABLE skm_policy.approvals (
    id            uuid        PRIMARY KEY,
    workspace_id  uuid        NOT NULL,
    intent_id     uuid        NOT NULL,
    approver_id   uuid        NOT NULL,
    decision      text        NOT NULL,
    args_digest   text        NOT NULL,
    single_use    boolean     NOT NULL DEFAULT true,
    reason        text        NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL,
    expires_at    timestamptz NOT NULL,
    used_at       timestamptz NULL,
    CONSTRAINT fk_approvals__tool_intents FOREIGN KEY (workspace_id, intent_id)
        REFERENCES skm_policy.tool_intents (workspace_id, id) ON DELETE RESTRICT,
    -- approver_id is not an FK: the system principal (auto-approval) is not a row of skm_access.principals
    CONSTRAINT ck_approvals__decision CHECK (decision IN ('approve', 'deny')),
    CONSTRAINT ck_approvals__args_digest CHECK (args_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_approvals__reason CHECK (char_length(reason) <= 1000),
    CONSTRAINT ck_approvals__expiry CHECK (expires_at > created_at),
    CONSTRAINT ck_approvals__used CHECK (used_at IS NULL OR (decision = 'approve' AND used_at >= created_at))
);
CREATE INDEX ix_approvals__intent_id_created_at ON skm_policy.approvals (intent_id, created_at);

-- Approvals are append-only; the only allowed change is setting used_at once (start_intent_execution).
CREATE FUNCTION skm_policy.tg_approvals__append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'approvals are append-only' USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.used_at IS NOT NULL OR NEW.used_at IS NULL
        OR (to_jsonb(NEW) - 'used_at') IS DISTINCT FROM (to_jsonb(OLD) - 'used_at') THEN
        RAISE EXCEPTION 'approvals allow only a single used_at update' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tg_approvals__append_only BEFORE UPDATE OR DELETE ON skm_policy.approvals
    FOR EACH ROW EXECUTE FUNCTION skm_policy.tg_approvals__append_only();

-- Tool decisions of hooks and workers (policy.record_tool_decisions). High volume, no domain events.
CREATE TABLE skm_policy.decision_audit (
    id             uuid        PRIMARY KEY,
    workspace_id   uuid        NULL,
    scope_id       uuid        NOT NULL,
    principal_id   uuid        NOT NULL,
    source         text        NOT NULL,
    at             timestamptz NOT NULL,
    tool           text        NOT NULL,
    call_summary   text        NOT NULL,
    outcome        text        NOT NULL,
    code           text        NULL,
    rule           text        NULL,
    operation      text        NULL,
    recorded_at    timestamptz NOT NULL,
    CONSTRAINT fk_decision_audit__scopes FOREIGN KEY (scope_id)
        REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_audit__principals FOREIGN KEY (principal_id)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_decision_audit__source CHECK (source IN ('hook', 'worker')),
    CONSTRAINT ck_decision_audit__outcome CHECK (outcome IN ('allow', 'ask', 'deny', 'warn')),
    CONSTRAINT ck_decision_audit__tool CHECK (char_length(tool) BETWEEN 1 AND 200),
    CONSTRAINT ck_decision_audit__call_summary CHECK (char_length(call_summary) <= 500),
    CONSTRAINT ck_decision_audit__code CHECK (code IS NULL OR code IN (
        'tool_not_allowed', 'path_protected', 'path_outside_scope', 'path_denied', 'commands_disabled',
        'command_denied', 'rm_outside_write_scope', 'operation_denied', 'requires_intent', 'requires_task_authority',
        'capability_not_granted', 'network_denied', 'approval_unavailable_unattended')),
    CONSTRAINT ck_decision_audit__deny_code CHECK ((outcome = 'deny') = (code IS NOT NULL)),
    CONSTRAINT ck_decision_audit__operation CHECK (operation IS NULL OR operation IN (
        'modify_write_set', 'modify_outside_write_set', 'delete_tracked', 'delete_own_untracked',
        'delete_foreign_untracked', 'modify_git_dir', 'git_discard', 'git_push', 'git_force_push', 'forge_write',
        'release_publish', 'secrets_access', 'docker_socket', 'external_services'))
);
CREATE INDEX ix_decision_audit__scope_id_at ON skm_policy.decision_audit (scope_id, at);
CREATE INDEX ix_decision_audit__at ON skm_policy.decision_audit (at);
-- risk signal "outside_write_set" for review (execution reads warnings of a run scope)
CREATE INDEX ix_decision_audit__scope_id_operation ON skm_policy.decision_audit (scope_id, operation)
    WHERE operation IS NOT NULL;

SELECT skm_core.grant_app('skm_policy', '{}'::text[]);
