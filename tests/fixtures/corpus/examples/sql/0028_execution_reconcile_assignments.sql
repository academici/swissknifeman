-- 0028_execution_reconcile_assignments: a narrow, server-owned read-only recovery lane.
-- Existing assignments retain NULL. A new row binds exactly one pre-existing effect and its attempt;
-- no run/task/attempt cursor, continuation, budget or publication right is changed by this DDL.
-- Effect state, pinned integration host, fresh worker authority and no-IO mode remain command-boundary checks.

ALTER TABLE skm_execution.external_effects
    ADD CONSTRAINT uq_external_effects__run_task_attempt_id UNIQUE (run_id, task_id, attempt_id, id);

ALTER TABLE skm_execution.assignments
    ADD COLUMN reconcile_effect_id uuid NULL,
    ADD CONSTRAINT fk_assignments__reconcile_effect FOREIGN KEY (run_id, task_id, attempt_id, reconcile_effect_id)
        REFERENCES skm_execution.external_effects (run_id, task_id, attempt_id, id) ON DELETE RESTRICT,
    ADD CONSTRAINT ck_assignments__reconcile_binding CHECK (
        reconcile_effect_id IS NULL OR
        (required_host_id IS NOT NULL AND reap_stage_record_id IS NULL AND reap_step_id IS NULL)
    );

CREATE UNIQUE INDEX uq_assignments__reconcile_effect_live
    ON skm_execution.assignments (reconcile_effect_id)
    WHERE reconcile_effect_id IS NOT NULL AND state IN ('available', 'leased');

-- uq_assignments__attempt_id_live from 0014 remains in force: no concurrent ordinary/reconcile assignment.
CREATE FUNCTION skm_execution.guard_assignment_reconcile_binding() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.reconcile_effect_id IS DISTINCT FROM OLD.reconcile_effect_id THEN
        RAISE EXCEPTION 'skm: assignment reconcile effect binding is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER tg_assignments__reconcile_binding_immutable
    BEFORE UPDATE ON skm_execution.assignments
    FOR EACH ROW EXECUTE FUNCTION skm_execution.guard_assignment_reconcile_binding();
