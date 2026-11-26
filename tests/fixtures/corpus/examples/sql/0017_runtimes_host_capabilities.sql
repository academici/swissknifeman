-- 0017_runtimes_host_capabilities: runtime installations, capability verifications and model catalog.
-- Owner module: runtimes. The FK to the published extensions resource version is added in 0018.
CREATE SCHEMA IF NOT EXISTS skm_runtimes;

-- Written only by runtimes.record_host_runtimes (host operation detect_runtimes -> SkmClient).
CREATE TABLE skm_runtimes.host_runtimes (
    host_id         uuid        NOT NULL,
    runtime_id      text        NOT NULL,
    version         text        NULL,
    binary_locator  text        NULL,          -- host path; returned only with permission checkout.read_locator, never exported
    auth_state      text        NOT NULL,
    details         jsonb       NOT NULL DEFAULT '{}'::jsonb,   -- string -> string, no secrets
    detected_at     timestamptz NOT NULL,
    updated_at      timestamptz NOT NULL,
    CONSTRAINT pk_host_runtimes PRIMARY KEY (host_id, runtime_id),
    CONSTRAINT fk_host_runtimes__hosts FOREIGN KEY (host_id) REFERENCES skm_workspace.hosts (id) ON DELETE RESTRICT,
    CONSTRAINT ck_host_runtimes__runtime_id CHECK (runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_host_runtimes__version CHECK (version IS NULL OR char_length(version) BETWEEN 1 AND 100),
    CONSTRAINT ck_host_runtimes__binary_locator CHECK (binary_locator IS NULL OR char_length(binary_locator) BETWEEN 1 AND 4096),
    CONSTRAINT ck_host_runtimes__auth_state CHECK (auth_state IN ('ok', 'missing', 'expired', 'unknown')),
    CONSTRAINT ck_host_runtimes__details CHECK (jsonb_typeof(details) = 'object')
);
CREATE INDEX ix_host_runtimes__runtime_id ON skm_runtimes.host_runtimes (runtime_id);

-- Append-only: a newer verification overrides the static capabilities.toml status (effective_capabilities).
CREATE TABLE skm_runtimes.capability_verifications (
    id               uuid        PRIMARY KEY,
    runtime_id       text        NOT NULL,
    runtime_version  text        NULL,
    verification_context jsonb  NULL,     -- exact host/binary/OS/kernel/adapter/isolation/launch context, no secrets
    verification_key text        NULL,     -- SHA256 of canonical verification_context, computed by application
    capability       text        NOT NULL,
    status           text        NOT NULL,
    evidence         text        NOT NULL,
    limitations      text        NOT NULL DEFAULT '',
    verified_at      date        NOT NULL,
    recorded_by      uuid        NOT NULL,
    recorded_at      timestamptz NOT NULL,
    CONSTRAINT fk_capability_verifications__principals FOREIGN KEY (recorded_by)
        REFERENCES skm_access.principals (id) ON DELETE RESTRICT,
    CONSTRAINT ck_capability_verifications__runtime_id CHECK (runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_capability_verifications__capability CHECK (capability IN (
        'headless_execution', 'structured_result', 'stream_events', 'session_resume', 'tool_interception',
        'reliable_cancellation', 'usage_reporting', 'workspace_binding', 'native_subagents', 'mcp_support',
        'permission_flags', 'sandbox_native', 'effort_control', 'model_selection', 'config_isolation')),
    CONSTRAINT ck_capability_verifications__status CHECK (status IN ('native', 'adapted', 'unsupported', 'unknown')),
    CONSTRAINT ck_capability_verifications__context CHECK (
        (verification_context IS NULL AND verification_key IS NULL) OR
        (verification_context IS NOT NULL AND verification_key IS NOT NULL AND
         jsonb_typeof(verification_context) = 'object' AND verification_key ~ '^sha256:[a-f0-9]{64}$')),
    CONSTRAINT ck_capability_verifications__evidence CHECK (char_length(evidence) BETWEEN 1 AND 500),
    CONSTRAINT ck_capability_verifications__limitations CHECK (char_length(limitations) <= 2000)
);
CREATE UNIQUE INDEX uq_capability_verifications__record ON skm_runtimes.capability_verifications
    (runtime_id, coalesce(runtime_version, ''), coalesce(verification_key, ''), capability, verified_at, status);
CREATE INDEX ix_capability_verifications__runtime_id_capability_recorded_at
    ON skm_runtimes.capability_verifications (runtime_id, capability, recorded_at DESC);
CREATE TRIGGER tg_capability_verifications__append_only BEFORE UPDATE OR DELETE ON skm_runtimes.capability_verifications
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_mutation();

-- Stable model identities can be offered by several runtimes.
CREATE TABLE skm_runtimes.canonical_models (
    model_id text PRIMARY KEY,
    CONSTRAINT ck_canonical_models__model_id CHECK (model_id <> '')
);

CREATE TABLE skm_runtimes.provider_model_offerings (
    runtime_id                 text    NOT NULL,
    model_id                   text    NOT NULL,
    provider_model_id          text    NOT NULL,
    display_name               text    NOT NULL,
    context_window_tokens      bigint  NOT NULL,
    max_output_tokens          bigint  NULL,
    patterns                   text[]  NOT NULL,
    status                     text    NOT NULL,
    verified_at                date    NOT NULL,
    source                     text    NOT NULL,
    input_per_mtok_usd         numeric NULL,
    output_per_mtok_usd        numeric NULL,
    cache_read_per_mtok_usd    numeric NULL,
    cache_write_per_mtok_usd   numeric NULL,
    price_verified_at         date    NULL,
    price_source               text    NULL,
    CONSTRAINT pk_provider_model_offerings PRIMARY KEY (runtime_id, model_id),
    CONSTRAINT fk_provider_model_offerings__canonical_models FOREIGN KEY (model_id)
        REFERENCES skm_runtimes.canonical_models (model_id) ON DELETE RESTRICT,
    CONSTRAINT ck_provider_model_offerings__runtime_id CHECK (runtime_id ~ '^[a-z][a-z0-9_]{1,31}$'),
    CONSTRAINT ck_provider_model_offerings__selector CHECK (provider_model_id <> ''),
    CONSTRAINT ck_provider_model_offerings__tokens CHECK (context_window_tokens >= 1000 AND max_output_tokens >= 0),
    CONSTRAINT ck_provider_model_offerings__status CHECK (status IN ('confirmed', 'unverified', 'deprecated')),
    CONSTRAINT ck_provider_model_offerings__pricing CHECK (
        (input_per_mtok_usd IS NULL AND output_per_mtok_usd IS NULL AND cache_read_per_mtok_usd IS NULL AND
         cache_write_per_mtok_usd IS NULL AND price_verified_at IS NULL AND price_source IS NULL) OR
        (input_per_mtok_usd IS NOT NULL AND output_per_mtok_usd IS NOT NULL AND price_verified_at IS NOT NULL AND
         price_source IS NOT NULL AND
         input_per_mtok_usd >= 0 AND input_per_mtok_usd < 'Infinity'::numeric AND
         output_per_mtok_usd >= 0 AND output_per_mtok_usd < 'Infinity'::numeric AND
         (cache_read_per_mtok_usd IS NULL OR
          (cache_read_per_mtok_usd >= 0 AND cache_read_per_mtok_usd < 'Infinity'::numeric)) AND
         (cache_write_per_mtok_usd IS NULL OR
          (cache_write_per_mtok_usd >= 0 AND cache_write_per_mtok_usd < 'Infinity'::numeric)))
    )
);
CREATE INDEX ix_provider_model_offerings__model_id ON skm_runtimes.provider_model_offerings (model_id);

-- Guidelines retain the immutable source version used at publication.
CREATE TABLE skm_runtimes.model_guidelines (
    resource_version_id uuid   NOT NULL,
    runtime_id          text   NOT NULL,
    model_id            text   NOT NULL,
    classes             text[] NOT NULL,
    suited_roles        text[] NOT NULL,
    notes               text   NOT NULL,
    CONSTRAINT pk_model_guidelines PRIMARY KEY (resource_version_id, runtime_id, model_id),
    CONSTRAINT fk_model_guidelines__provider_model_offerings FOREIGN KEY (runtime_id, model_id)
        REFERENCES skm_runtimes.provider_model_offerings (runtime_id, model_id) ON DELETE RESTRICT
);
CREATE INDEX ix_model_guidelines__offering ON skm_runtimes.model_guidelines (runtime_id, model_id);

CREATE TABLE skm_runtimes.host_model_availability (
    host_id      uuid        NOT NULL,
    runtime_id   text        NOT NULL,
    model_id     text        NOT NULL,
    effort       text        NOT NULL,
    observed_at  timestamptz NOT NULL,
    expires_at   timestamptz NOT NULL,
    CONSTRAINT pk_host_model_availability PRIMARY KEY (host_id, runtime_id, model_id, effort),
    CONSTRAINT fk_host_model_availability__hosts FOREIGN KEY (host_id)
        REFERENCES skm_workspace.hosts (id) ON DELETE CASCADE,
    CONSTRAINT fk_host_model_availability__provider_model_offerings FOREIGN KEY (runtime_id, model_id)
        REFERENCES skm_runtimes.provider_model_offerings (runtime_id, model_id) ON DELETE RESTRICT,
    CONSTRAINT ck_host_model_availability__effort CHECK (effort IN ('low', 'medium', 'high', 'xhigh')),
    CONSTRAINT ck_host_model_availability__expires_at CHECK (expires_at > observed_at)
);
CREATE INDEX ix_host_model_availability__offering ON skm_runtimes.host_model_availability (runtime_id, model_id);

SELECT skm_core.grant_app('skm_runtimes', ARRAY['capability_verifications']::text[]);
