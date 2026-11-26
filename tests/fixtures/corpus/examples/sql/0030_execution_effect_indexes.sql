-- 0030_execution_effect_indexes: the effect idempotency key as a constraint, and the indexes two hot reads need.
-- external_effects: two concurrent recorders of one request both passed the adapter's pre-INSERT check; the
-- UNIQUE constraint settles that race. The reconcile sweep reads every unresolved state oldest first, while the
-- old partial index covered outcome_unknown alone and served no query.
-- decision_records: the decision inbox looks up the latest record of each listed request.

ALTER TABLE skm_execution.external_effects
    ADD CONSTRAINT uq_external_effects__run_id_kind_request_digest UNIQUE (run_id, kind, request_digest);

DROP INDEX skm_execution.ix_external_effects__outcome_unknown;
CREATE INDEX ix_external_effects__unresolved ON skm_execution.external_effects (updated_at, id)
    WHERE state IN ('intended', 'executing', 'outcome_unknown');

CREATE INDEX ix_decision_records__request_id_created_at
    ON skm_execution.decision_records (request_id, created_at DESC, id DESC);
