# Server mode

Compose runs a PostgreSQL control plane and an HTTP worker on separate networks and data volumes.
The API is published on the Docker host's loopback interface. PostgreSQL stays on the internal
`database` network, and the worker reaches the API on `worker-api`.

## Record the deployment

Before installation or upgrade, record the source repository and revision, SKM package version,
wheel SHA-256, image IDs or registry digests, and the instance UUID from the bootstrap profile.
Keep that record with the hashes of `uv.lock` and `web/package-lock.json`, the pinned base image references,
and the build-backend requirements in the Dockerfile. Record any additional runtime, plugin or script
packages and their locks and checksums. Retain the chosen images and wheel artifacts or verified build
caches so the same installation can be reproduced.

| Stage | Docker Official Image reference |
| --- | --- |
| Web bundle | `node:24.22.3-bookworm-slim@sha256:dc26ae92c9fb15cf6b1d63e20f0944b2efe0f115b20e00be48fb23fceb061c54` |
| API and wheel build | `python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df` |
| Worker | `python:3.12.16-bookworm@sha256:4209fae09a3e20afd863e528bfddc235da5fd5977983e1996cd54cc9a72e6267` |

The API image builds the web bundle with the npm lock, builds the SKM wheel offline, and installs
hash-checked locked wheels offline. The worker uses the same installed wheel. Its Bookworm base
includes Debian package `git 1:2.39.5-0+deb12u3` and pins its complete dependency set in the image
digest. The worker Dockerfile uses those preinstalled packages and runs its setup step offline.
Build the images together using Compose.

## First install

Use Docker with the Compose plugin (2.23.1 or later) and BuildKit. From the repository root, define
a shorthand for the server stack:

```sh
compose() { docker compose -f deploy/compose.yaml "$@"; }
```

Load three different 32-byte random passwords from your secret store into the environment as
`SKM_PG_ADMIN_PASSWORD`, `SKM_PG_MIGRATOR_PASSWORD` and `SKM_PG_APP_PASSWORD`. Use hex encoding
because Compose interpolates the app and migrator passwords into PostgreSQL URLs. For a fresh
disposable deployment, each value can be generated with `openssl rand -hex 32`. Keep rendered
Compose configuration and Docker inspection output private because they include the credentials.

```sh
compose build
compose up -d init
compose wait init
compose up -d --wait api
curl --fail http://127.0.0.1:8765/health/ready
```

When PostgreSQL initializes an empty volume, its administrator creates two login roles in
separate role groups. `skm_migrator_login` uses the `skm_migrator` group to apply schema changes
through the one-shot `skm db migrate` service. `skm_app_login` uses `skm_app` for runtime reads
and DML, with read-only access to `skm_core.schema_migrations`. PostgreSQL denies schema and table
creation and ledger writes to the app role. Rotate credentials through PostgreSQL and the
secret store together. Startup environment changes alone cannot rotate an existing login.

The explicit `init` service provisions the instance and the first owner after migration. Save
the operator token outside the deployment checkout. Back up the PostgreSQL and API volumes
together, preserving the bootstrap profile, token pepper and blobs.

```sh
umask 077
operator_state="$HOME/.config/skm/operator"
mkdir -p "$operator_state"
compose cp init:/var/lib/skm/secrets/owner.token "$operator_state/owner.token"
chmod 600 "$operator_state/owner.token"
```

The owner token lives on the setup-only volume. The API uses the application DSN and a persistent
API volume. Its bootstrap disables automatic migrations. Use the readiness and migration-status
endpoints to diagnose a schema mismatch and run apply through the local migrator service.

## TLS reverse proxy

Terminate TLS at a reverse proxy on the Docker host. Point its upstream to
`http://127.0.0.1:8765` and keep the API's plaintext listener loopback-only.
Preserve the public Host header, Authorization header, and request path. Disable response
buffering for SSE and choose timeouts that allow long-poll and event-stream requests.

For a public URL such as `https://skm.example.org`, export these settings before running `init`:

```sh
export SKM_API_ALLOWED_HOSTS='["api:8765","127.0.0.1:8765","skm.example.org"]'
export SKM_API_CORS_ORIGINS='["https://skm.example.org"]'
```

For an existing installation, set `api.allowed_hosts` and `api.cors.origins` at instance scope
using the operator CLI, then restart the API. Keep the internal API and healthcheck hosts in
the allowed list, and include the loopback address with the chosen port if using a custom host port.

Use a valid certificate for the public hostname. Keep the public origin exact, including a port if
the browser sends one. With proxy header trust disabled, the explicit HTTPS origin allows browser
requests forwarded over plain HTTP.

## Outbound workers

Create a host and a scoped, expiring worker credential for each worker using an operator HTTP
profile. The [CLI reference](../reference/cli.md) lists `skm host register`, `skm worker register`
and the worker lifecycle commands. Use the registered host UUID, instance UUID and workspace UUID
when provisioning the worker. Store the worker token in a file owned by the worker OS user with
mode `0600`; the worker can rotate the token in place. Keep the API owner token, database DSNs
and provider credentials out of the worker bootstrap.

For a laptop worker, install the recorded SKM wheel or equivalent package. Save this profile as
`worker.toml` and replace the instance UUID, host UUID and paths with values for that host.
Use absolute paths under a private, worker-owned state directory.

```toml
schema = "urn:skm:config:bootstrap:v1"
instance_id = "<instance UUID>"

[access]
mode = "http"

[api]
endpoint = "https://skm.example.org/api/v1"
credential = "secret://file//absolute/worker-state/worker.token"

[host]
id = "<registered host UUID>"

[paths]
state_dir = "/absolute/worker-state"
```

```sh
SKM_WORKSPACE='<workspace UUID>' skm --bootstrap worker.toml worker start
```

The laptop initiates HTTPS requests for claims, heartbeats and results. It requires zero inbound
ports. Use the normal certificate trust store or set `api.ca_bundle` for a managed CA.

For the Compose worker, use the same profile with endpoint `http://api:8765/api/v1`,
state path `/var/lib/skm`, and credential `secret://file//var/lib/skm/worker.token`.
Import the profile and token into its private Compose volume before starting it:

```sh
export SKM_WORKER_WORKSPACE='<workspace UUID>'
compose run --no-deps -T --entrypoint sh worker -ec 'umask 077; cat > bootstrap.toml' < worker.toml
compose run --no-deps -T --entrypoint sh worker -ec 'umask 077; cat > worker.token' < worker.token
compose up -d --no-deps worker
```

Register the runtime and isolation capabilities observed on each worker. Check the actual
executable and version with `skm runtime detect`, and verify authentication, tool visibility,
filesystem/network containment and process cleanup with the applicable backend checks.
Advertise support only for combinations with that evidence. Run workloads requiring sandboxing,
provider connectivity or external effects on a separately configured worker profile with the
specific grants and a verified backend.

## Maintain a 0.1.0 installation

Initialize new installations from empty databases as described above. The 0.1.0
baseline requires its own schema history. For recovery of data created by 0.1.0,
follow the [backup and restore procedure](../evidence/backup-restore.md).

For maintenance that requires taking a running 0.1.0 instance offline:

1. Run `skm worker drain <worker>` for every registered worker. Wait for active
   assignments to complete or be released, then stop the processes.
2. Back up PostgreSQL and the API state with the recorded 0.1.0 images and
   credentials. Stop the API with `compose stop api` and retain its volumes.
3. Start the API with `compose up -d --no-deps --wait api`. Check readiness,
   then start the workers and set drained registrations to online in the [Workers view](web.md).

### Local owner password and pairing credentials

Pass `SKM_FIRST_ADMIN_PASSWORD` in the environment of `skm init` to set the local owner's
first password. Use 12–1024 characters. A later `skm init` can set a missing password for
an existing local owner. Bootstrap keeps an existing password and returns the owner bearer
only when it first creates the owner.

New API bearers use `skm_live_<prefix>_<random>_<crc32>`. The prefix is eight lowercase
Base32 characters, the random field is 43 Base64url characters, and the checksum is eight
lowercase hexadecimal digits over the preceding text. Authentication checks the checksum
and verifies the peppered HMAC. Existing `skm_<prefix>_<random>` bearers remain supported.

The access facade issues pairing proofs within the caller's transaction. A system-authenticated
caller passes the proof, pairing ID and workspace ID to `workspace.exchange_pairing_token`.
The first committed exchange returns the bearer. A retry returns the original IDs and status.
To recover a lost worker bearer, an issuer with live `worker.register` on the workspace can
issue a pairing that replaces the original. Exchanging it keeps the worker and revokes its
prior credentials in the same transaction. For a lost personal bearer, an authorized operator
can rotate its token ID with zero grace.

A multi-scope token holds explicit scope–permission pairs. A pair applies to its scope and
descendants, and the principal's live role must also allow the permission there. Default personal
grants freeze the issuer's live permissions at the requested scope. Ordinary token rotation
rechecks the issuer before copying the immutable grant. Worker registration uses a fixed worker
grant for its workspace and host, including `worker.claim`.
