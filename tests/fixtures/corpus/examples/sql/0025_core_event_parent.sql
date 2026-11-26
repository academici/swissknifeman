-- 0025_core_event_parent: preserve the producing command's own cause in durable event history.
-- causation_id keeps its immediate-command request id semantics; parent_causation_id = RequestMeta.causation_id.
-- Existing append-only events remain NULL: no historical UPDATE/backfill or inferred parents.
-- These identifiers carry diagnostic context, never authority or proof of a caller-supplied causal edge.

ALTER TABLE skm_core.domain_events
    ADD COLUMN parent_causation_id text NULL,
    ADD CONSTRAINT ck_domain_events__parent_causation_id CHECK (
        parent_causation_id IS NULL OR char_length(parent_causation_id) <= 64
    );
