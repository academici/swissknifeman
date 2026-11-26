-- 0003_core_events: domain events, per-stream and per-workspace sequences, outbox, consumer receipts (ADR 0009, 0017).

CREATE TABLE skm_core.event_streams (
    stream_kind  text   NOT NULL,
    stream_id    uuid   NOT NULL,
    last_seq     bigint NOT NULL DEFAULT 0,
    CONSTRAINT pk_event_streams PRIMARY KEY (stream_kind, stream_id),
    CONSTRAINT ck_event_streams__last_seq CHECK (last_seq >= 0)
);

-- Serializes event writes per workspace so that an SSE reader with cursor N never misses a later-committed event < N.
CREATE TABLE skm_core.workspace_event_counters (
    workspace_id uuid   PRIMARY KEY,
    last_seq     bigint NOT NULL DEFAULT 0,
    CONSTRAINT fk_workspace_event_counters__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT ck_workspace_event_counters__last_seq CHECK (last_seq >= 0)
);

CREATE TABLE skm_core.domain_events (
    id              uuid        PRIMARY KEY,
    workspace_id    uuid        NULL,
    stream_kind     text        NOT NULL,
    stream_id       uuid        NOT NULL,
    stream_seq      bigint      NOT NULL,
    workspace_seq   bigint      NULL,
    global_position bigint      NULL,         -- instance feed only; serialized through event_streams(instance_feed, instance scope id)
    event_type      text        NOT NULL,
    schema_version  integer     NOT NULL DEFAULT 1,
    actor_id        uuid        NULL,          -- principal id; no FK: skm_core is below skm_access
    request_id      text        NULL,          -- request that produced the event
    correlation_id  text        NOT NULL,      -- root of the causal chain (first request id, inherited along the chain)
    causation_id    text        NULL,          -- what caused it: the command's request_id, or the event id that triggered the command
    payload         jsonb       NOT NULL,
    occurred_at     timestamptz NOT NULL,
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_domain_events__scopes FOREIGN KEY (workspace_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT uq_domain_events__stream UNIQUE (stream_kind, stream_id, stream_seq),
    CONSTRAINT uq_domain_events__workspace_seq UNIQUE (workspace_id, workspace_seq),
    CONSTRAINT ck_domain_events__seq CHECK (stream_seq >= 1),
    CONSTRAINT ck_domain_events__workspace_seq CHECK ((workspace_id IS NULL) = (workspace_seq IS NULL)),
    CONSTRAINT ck_domain_events__global_position CHECK (
        (workspace_id IS NULL AND global_position IS NOT NULL AND global_position >= 1)
        OR (workspace_id IS NOT NULL AND global_position IS NULL)
    ),
    CONSTRAINT ck_domain_events__type CHECK (event_type ~ '^urn:skm:[a-z][a-z0-9-]*:event:[a-z][a-z0-9-]*:v[1-9][0-9]*$'),
    CONSTRAINT ck_domain_events__schema_version CHECK (schema_version >= 1),
    CONSTRAINT ck_domain_events__payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_domain_events__payload_size CHECK (octet_length(payload::text) <= 262144)
);

CREATE INDEX ix_domain_events__event_type_recorded_at ON skm_core.domain_events (event_type, recorded_at);
CREATE INDEX ix_domain_events__stream_id ON skm_core.domain_events (stream_id);
CREATE INDEX ix_domain_events__correlation_id ON skm_core.domain_events (correlation_id);
CREATE UNIQUE INDEX uq_domain_events__global_position ON skm_core.domain_events (global_position)
    WHERE global_position IS NOT NULL;

CREATE TRIGGER tg_domain_events__append_only BEFORE UPDATE OR DELETE ON skm_core.domain_events
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- One row per (event, consumer). A relay claims a batch with SELECT … FOR UPDATE SKIP LOCKED in a short transaction that
-- sets claimed_at/claimed_by and attempts + 1 (state stays 'pending'/'failed': there is no 'delivering' state); a claim older
-- than events.delivery.visibility_timeout_seconds counts as abandoned and the row is claimed again. The delivery itself runs in the
-- subscriber's own transaction (consumer_receipts + state = 'delivered'); a failure sets state failed/dead and clears the claim.
CREATE TABLE skm_core.outbox (
    id            uuid        PRIMARY KEY,
    event_id      uuid        NOT NULL,
    destination   text        NOT NULL,      -- consumer_id ("exports.plan_archived_note"), "hook:<id>" (ExternalConsumerSpec) or "sse"
    state         text        NOT NULL DEFAULT 'pending',
    available_at  timestamptz NOT NULL,
    attempts      integer     NOT NULL DEFAULT 0,
    delivery_generation integer NOT NULL DEFAULT 1, -- manual retry resets attempts, increments generation
    last_error    text        NULL,
    delivered_at  timestamptz NULL,
    claimed_at    timestamptz NULL,
    claimed_by    text        NULL,          -- relay instance id
    dead_notified_at timestamptz NULL,     -- on_dead external consumer-а доставлен (kernel §4.5 шаг 4); NULL у dead → повтор
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_outbox__domain_events FOREIGN KEY (event_id) REFERENCES skm_core.domain_events (id) ON DELETE RESTRICT,
    CONSTRAINT uq_outbox__event_id_destination UNIQUE (event_id, destination),
    CONSTRAINT ck_outbox__state CHECK (state IN ('pending', 'delivered', 'failed', 'dead')),
    CONSTRAINT ck_outbox__attempts CHECK (attempts >= 0),
    CONSTRAINT ck_outbox__delivery_generation CHECK (delivery_generation >= 1),
    CONSTRAINT ck_outbox__delivered_at CHECK ((state = 'delivered') = (delivered_at IS NOT NULL)),
    CONSTRAINT ck_outbox__destination CHECK (destination = 'sse' OR destination ~ '^([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*|hook:[a-z0-9][a-z0-9_-]*)$'),
    CONSTRAINT ck_outbox__last_error_size CHECK (last_error IS NULL OR length(last_error) <= 4000),
    CONSTRAINT ck_outbox__dead_notified CHECK (dead_notified_at IS NULL OR state = 'dead'),
    CONSTRAINT ck_outbox__claim CHECK ((claimed_at IS NULL) = (claimed_by IS NULL)
        AND (claimed_by IS NULL OR char_length(claimed_by) BETWEEN 1 AND 200))
);

CREATE INDEX ix_outbox__state_available_at ON skm_core.outbox (state, available_at) WHERE state IN ('pending', 'failed');
CREATE INDEX ix_outbox__destination_state ON skm_core.outbox (destination, state);
CREATE INDEX ix_outbox__dead_notification_due ON skm_core.outbox (available_at, id)
    WHERE state = 'dead' AND dead_notified_at IS NULL;
-- outbox_gc (janitor) deletes delivered rows older than events.outbox.delivered_retention_hours in batches.
CREATE INDEX ix_outbox__delivered_at ON skm_core.outbox (delivered_at) WHERE state = 'delivered';

-- Receipts are never updated. They are deleted only by the janitor task outbox_gc (kernel-platform §6) once no outbox
-- row of the (consumer, event) pair is left and events.outbox.delivered_retention_hours has passed; therefore the table is
-- not in the append-only list (DELETE stays granted) and UPDATE is blocked by its own trigger.
CREATE TABLE skm_core.consumer_receipts (
    consumer_id   text        NOT NULL,
    event_id      uuid        NOT NULL,
    processed_at  timestamptz NOT NULL,
    CONSTRAINT pk_consumer_receipts PRIMARY KEY (consumer_id, event_id),
    CONSTRAINT fk_consumer_receipts__domain_events FOREIGN KEY (event_id) REFERENCES skm_core.domain_events (id) ON DELETE RESTRICT
);

CREATE INDEX ix_consumer_receipts__processed_at ON skm_core.consumer_receipts (processed_at);

CREATE OR REPLACE FUNCTION skm_core.forbid_row_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skm: UPDATE on %.% is forbidden', TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE TRIGGER tg_consumer_receipts__no_update BEFORE UPDATE ON skm_core.consumer_receipts
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_row_update();

SELECT skm_core.grant_app('skm_core', ARRAY['scopes','domain_events']::text[]);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'skm_app') THEN
        REVOKE UPDATE, DELETE ON skm_core.domain_events FROM skm_app;
    END IF;
END
$$;
