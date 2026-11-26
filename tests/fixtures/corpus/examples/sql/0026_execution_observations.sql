-- 0026_execution_observations: immutable invocation binding and bounded terminal observation.
-- Existing rows remain NULL/unavailable. No inferred model/version or historical backfill.
-- Application canonical UTF-8 JSON cap is 16384 bytes per value. The 32768-byte SQL backstop
-- allows jsonb text whitespace/escaping overhead; it does not widen the application contract.
-- Full JSON Schema validation and same-step/fence checks belong to the execution command boundary.

ALTER TABLE skm_execution.attempt_steps
    ADD COLUMN route_snapshot jsonb NULL,
    ADD COLUMN runtime_observation jsonb NULL,
    ADD CONSTRAINT ck_attempt_steps__route_snapshot CHECK (
        route_snapshot IS NULL OR
        (jsonb_typeof(route_snapshot) = 'object' AND octet_length(route_snapshot::text) <= 32768)
    ),
    ADD CONSTRAINT ck_attempt_steps__runtime_observation CHECK (
        runtime_observation IS NULL OR
        (jsonb_typeof(runtime_observation) = 'object'
         AND octet_length(runtime_observation::text) <= 32768 AND state <> 'started')
    );

CREATE FUNCTION skm_execution.guard_step_observation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.route_snapshot IS DISTINCT FROM OLD.route_snapshot THEN
        RAISE EXCEPTION 'skm: step route snapshot is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.runtime_observation IS NULL AND NEW.runtime_observation IS NOT NULL
       AND OLD.state <> 'started' THEN
        RAISE EXCEPTION 'skm: late observation on a terminal step is forbidden'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.runtime_observation IS NOT NULL
       AND NEW.runtime_observation IS DISTINCT FROM OLD.runtime_observation THEN
        RAISE EXCEPTION 'skm: terminal runtime observation is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER tg_attempt_steps__observation_immutable
    BEFORE UPDATE ON skm_execution.attempt_steps
    FOR EACH ROW EXECUTE FUNCTION skm_execution.guard_step_observation();

CREATE TABLE skm_execution.step_tool_calls (
    step_id uuid NOT NULL REFERENCES skm_execution.attempt_steps (id),
    call_id text COLLATE "C" NOT NULL CHECK (char_length(call_id) BETWEEN 1 AND 300),
    tool text NULL CHECK (char_length(tool) BETWEEN 1 AND 300),
    duration_ms bigint NULL CHECK (duration_ms >= 0),
    coverage text NOT NULL CHECK (coverage IN ('complete', 'partial')),
    fencing_token bigint NOT NULL CHECK (fencing_token > 0),
    recorded_at timestamptz NOT NULL,
    PRIMARY KEY (step_id, call_id)
);

CREATE TRIGGER tg_step_tool_calls__append_only
    BEFORE UPDATE OR DELETE ON skm_execution.step_tool_calls
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- Final journal ACLs after the execution schema's blanket grant_app calls.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE ALL PRIVILEGES ON skm_execution.incident_gates, skm_execution.step_tool_calls FROM skm_app;
        GRANT SELECT, INSERT ON skm_execution.incident_gates, skm_execution.step_tool_calls TO skm_app;
    END IF;
END
$$;
