-- Roles are provisioned with the machine database. A migrator login owns the schema objects;
-- the machine application receives usage and only the DML needed by the local store.
GRANT USAGE ON SCHEMA skm_host TO skm_host_app;
GRANT SELECT ON skm_host.schema_migrations, skm_host.schema_baseline TO skm_host_app;

CREATE TABLE skm_host.installation (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    installation_id uuid NOT NULL UNIQUE
);

CREATE TABLE skm_host.operator_settings (
    installation_id uuid NOT NULL REFERENCES skm_host.installation (installation_id),
    key text NOT NULL CHECK (key <> ''),
    value jsonb NOT NULL,
    PRIMARY KEY (installation_id, key)
);

CREATE TABLE skm_host.user_settings (
    installation_id uuid NOT NULL REFERENCES skm_host.installation (installation_id),
    instance_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    key text NOT NULL CHECK (key <> ''),
    value jsonb NOT NULL,
    PRIMARY KEY (installation_id, instance_id, principal_id, key)
);

CREATE TABLE skm_host.profiles (
    installation_id uuid NOT NULL REFERENCES skm_host.installation (installation_id),
    name text NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{0,31}$'),
    instance_id uuid NOT NULL,
    origin text NOT NULL CHECK (origin <> ''),
    endpoint text,
    credential_ref text CHECK (
        length(credential_ref) <= 1038
        AND credential_ref ~ '^secret://(env/[A-Z_][A-Z0-9_]{0,127}|file/[^[:space:]]+|keyring/[A-Za-z0-9._-]{1,128}/[A-Za-z0-9._@-]{1,128})$'
    ),
    ca_bundle text,
    revision uuid NOT NULL DEFAULT gen_random_uuid(),
    PRIMARY KEY (installation_id, name),
    UNIQUE (installation_id, instance_id),
    UNIQUE (installation_id, revision, instance_id, origin)
);

CREATE TABLE skm_host.sessions (
    installation_id uuid NOT NULL,
    profile_revision uuid NOT NULL,
    instance_id uuid NOT NULL,
    origin text NOT NULL,
    principal_id uuid NOT NULL,
    handle_hash text NOT NULL CHECK (handle_hash ~ '^[0-9a-f]{64}$'),
    issued_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (installation_id, handle_hash),
    CONSTRAINT fk_sessions__profile FOREIGN KEY (installation_id, profile_revision, instance_id, origin)
        REFERENCES skm_host.profiles (installation_id, revision, instance_id, origin) ON DELETE CASCADE,
    CHECK (expires_at > issued_at AND expires_at <= issued_at + interval '15 minutes')
);
CREATE INDEX ix_sessions__profile ON skm_host.sessions (installation_id, profile_revision, instance_id, origin);
CREATE INDEX ix_sessions__principal ON skm_host.sessions (installation_id, instance_id, principal_id);

CREATE TABLE skm_host.checkouts (
    installation_id uuid NOT NULL REFERENCES skm_host.installation (installation_id),
    instance_id uuid NOT NULL,
    host_id uuid NOT NULL,
    checkout_id uuid NOT NULL,
    root text NOT NULL CHECK (root <> ''),
    PRIMARY KEY (installation_id, instance_id, host_id, checkout_id),
    UNIQUE (installation_id, instance_id, host_id, root)
);

CREATE TABLE skm_host.bindings (
    installation_id uuid NOT NULL,
    instance_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    host_id uuid NOT NULL,
    checkout_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    PRIMARY KEY (installation_id, instance_id, host_id, checkout_id, principal_id),
    FOREIGN KEY (installation_id, instance_id, host_id, checkout_id)
        REFERENCES skm_host.checkouts (installation_id, instance_id, host_id, checkout_id)
);

CREATE TABLE skm_host.retries (
    installation_id uuid NOT NULL,
    instance_id uuid NOT NULL,
    principal_id uuid NOT NULL,
    host_id uuid NOT NULL,
    checkout_id uuid NOT NULL,
    operation text NOT NULL CHECK (operation IN ('bind', 'verify')),
    request_id uuid NOT NULL,
    step text NOT NULL CHECK (step <> ''),
    idempotency_key text NOT NULL CHECK (idempotency_key <> ''),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    safe_until timestamptz NOT NULL,
    receipt jsonb CHECK (jsonb_typeof(receipt) = 'object'),
    PRIMARY KEY (installation_id, instance_id, host_id, checkout_id, principal_id, operation, request_id, step),
    FOREIGN KEY (installation_id, instance_id, host_id, checkout_id)
        REFERENCES skm_host.checkouts (installation_id, instance_id, host_id, checkout_id),
    UNIQUE (installation_id, instance_id, principal_id, idempotency_key)
);

GRANT SELECT, INSERT ON skm_host.installation, skm_host.checkouts, skm_host.retries TO skm_host_app;
GRANT SELECT, INSERT, UPDATE ON skm_host.operator_settings, skm_host.user_settings, skm_host.bindings TO skm_host_app;
GRANT SELECT, INSERT, DELETE ON skm_host.profiles, skm_host.sessions TO skm_host_app;
GRANT UPDATE (receipt) ON skm_host.retries TO skm_host_app;
