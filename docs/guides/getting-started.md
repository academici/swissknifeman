# Getting started

## Install from the checkout

Use Python 3.12 or newer. From the repository root, install the local candidate
as a CLI tool with `uv tool install .`. To use the locked development environment
instead, run `uv sync --frozen` and prefix the commands below with `uv run --frozen`.
Check the selected binary with `skm --version`.

## Roll out onto an existing project

New installs and new database plans use this checkout's `skm`. Plans that still live as JSON files, rather than as database rows, stay byte-for-byte where they are. That includes `../swissknifeman/plans/`, an untracked `plans/` tree in a checkout, and the live consumer scopes `project:commerz` and `project:swissknifeman`. Do not import those files, rewrite them, migrate them into the database, or delete them. Moving a project onto this toolkit must not convert those JSON plans.

Delete `../swissknifeman` only after those consumers no longer need it. Do not stop the live `maind` MCP processes that still serve `project:commerz` and `project:swissknifeman`.

For the web UI, use Node.js 22+ and run `make web-build`. Build before
`uv tool install .` so the wheel includes the bundle. The checkout environment
serves the bundle directly from `web/dist`.

## Start a local instance

The first `skm local up` starts a private PostgreSQL Compose stack on an assigned
loopback port. Initialize the instance, then start the API and worker.

```sh
skm local up
skm init --host-name laptop
skm local up
skm whoami
skm local status
```

With the bundle built, open the UI with `skm local open`. Use `skm local down`
to stop the stack, or `skm local down --keep-db` to leave PostgreSQL running.
[Local and self-managed PostgreSQL](local-mode.md) · [Server mode](server-mode.md)

## Authenticate and run a worker

`skm init` creates an owner and the default `personal` workspace. The embedded CLI
uses the private owner-token file whose path is shown by `skm local token`. In
the web login, use a token issued for your role. HTTP clients send it as
`Authorization: Bearer <token>`. Use `skm token create` with `--scope`,
`--permission`, `--expires-in`, and `--save` to limit and store a credential.
Keep token files private and use `skm token revoke` to withdraw a credential.
[Web sign-in](web.md#sign-in) · [CLI reference](../reference/cli.md)

`skm local up` registers the local host and starts a worker by default.
For a standalone worker with `local up --no-worker`, use `skm host register`
if the host is new. The worker reports the installed SKM version, `0.1.0` for this release.

Run `skm config machine-keys` and `skm runtime detect` on the worker host.
The local operator sets allowed runtimes, models and efforts in machine
storage. Use `skm runtime capabilities <runtime-id> --version <version>` to
check the installed version, and verify isolation on the same host. Set
`host_id`, `runtime_id` and `isolation_profile` to the registered host and
verified capabilities before submitting work.
[Machine settings](local-mode.md#configure-runtimes)

```sh
skm worker register --host "$host_id" --save-token \
  --runtime "$runtime_id" --isolation "$isolation_profile"
```

Repeat `--runtime` and `--isolation` to advertise additional verified
capabilities. Set `worker_id` to the returned ID, then run
`skm worker start --worker "$worker_id"`. Use `skm worker list` to inspect
registrations. Remote workers use a separate, expiring credential and make
outbound requests to the API.
[Worker provisioning](server-mode.md#outbound-workers) ·
[Platform support](../reference/platform-support.md)

## Review work

In a Git checkout with a configured remote, create a project and bind its
primary repository:

```sh
skm project create example
skm use personal/example
skm repo bind --mount main --register
```

Use `skm plan create "Example plan"` to open a draft. Edit and validate it with
`skm plan draft edit <plan>` and `skm plan draft validate <plan>`, then
`skm plan publish <plan> --reason "Initial revision"`. Check the revision with
`skm run readiness <plan>`, then submit it with `skm run start <plan>`.

For progressive execution, preview and start the same revision and selection. A human
with `plan.approve` signs the report. The caller who starts the run needs `run.start`.

```sh
skm run readiness <plan> --revision <revision> --mode progressive_per_phase --phase P1
skm plan approve <plan> <report-id> --reason "Reviewed phase P1"
skm run start <plan> --revision <revision> --mode progressive_per_phase --phase P1 --visa-id <visa-id>
```

Add `--semantic-audit` to `skm run readiness` to request the advisor audit when
the instance enables it. The command returns an audit run ID when it schedules
one. Wait for that audit to finish before starting the revision. Both the report
and visa must be current under `execution.readiness.max_age_seconds`, and the
signer must still hold `plan.approve` on the plan.

For a waiting run, inspect its blocking reason with
`skm run show <run>` and find the request with `skm inbox list --run <run>`.
Inspect the actual check evidence before recording a manual check with
`skm inbox verdict <check> pass` or `skm inbox verdict <check> fail`.

Track independent manual review separately from executor checks. Record the
reviewed diff or commit range, findings and verdict. A separate SKM review run
can be requested with `skm review request --base <sha> --head <sha>` and
inspected with `skm review show <run>`. The workflow uses the v2 CLI and
PostgreSQL state. [Concepts](concepts.md) · [Web Inbox](web.md#manual-review-and-inbox)

## Back up and restore

Use the local source profile, PostgreSQL client tools and an unused archive
directory. `skm backup restore` requires a reachable source database and
`admin.storage` on the instance named in the archive. A verified archive alone
cannot be restored through this command while the source database is unreachable.
Use an unused database name on the target. The target role must be able to
connect to the target server's `postgres` maintenance database and run
`CREATE DATABASE`.

```sh
skm backup create --output "$archive_dir"
skm backup verify "$archive_dir"
skm backup restore "$archive_dir" --target-database-url "$staging_dsn" --yes
```

Set `restored_profile` to the profile reported by restore. Verify storage with
`skm --bootstrap "$restored_profile" storage verify`. Register recovery hosts
and rebind any Git effects that require inspection using `skm backup rebind`
under the restored profile. Then run
`skm --bootstrap "$restored_profile" backup activate --yes`. The restored
profile starts in quarantine. Owners resume runs explicitly and external
destinations require verification. [Recovery rehearsal and commands](../evidence/backup-restore.md)
