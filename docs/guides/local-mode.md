# Local mode

Local mode runs the control plane and worker on one machine. Use the installed SKM package and a
Docker engine with the Compose plugin for the managed PostgreSQL service. On the first invocation,
`skm local up` starts PostgreSQL. The API and worker start after `skm init`.

```sh
skm local up
skm init --host-name laptop
skm local up
skm whoami
skm local status
skm local open
```

Keep the bootstrap profile, owner token and database credentials private. The managed stack
assigns a loopback port and stores credential references for separate project and machine
roles. The API also binds to loopback. Use `skm local down` to stop the processes and
managed PostgreSQL, or pass `--keep-db` to leave PostgreSQL running.

For self-managed PostgreSQL 16+, use distinct project and machine databases. Set
`SKM_DATABASE_URL` and `SKM_DATABASE_MIGRATOR_URL` for the project app and migrator
roles, and `SKM_MACHINE_DATABASE_URL` and `SKM_MACHINE_DATABASE_MIGRATOR_URL` for the
machine app and migrator roles. Begin at `skm init`. Keep the referenced environment
variables available for subsequent commands that use those profiles.

Record the package source, version and wheel digest, the bootstrap instance UUID and the
Python lock used to install it. Record the runtime executable, version and dependency locks
for any plugins or scripts.

## Configure runtimes

Use `skm config machine-keys` to list operator settings and `skm runtime detect` to
inspect the runtime and account available on this host. Machine settings accept JSON values.
For example, a host operator can allow Codex and a specific model and effort:

```sh
skm config machine-set runtimes.allowed '["codex"]'
skm config machine-set runtimes.models.allowed '{"codex":{"gpt-6-sol":["high"]}}'
```

Choose model identifiers supported by the host's verified runtime and model catalog.
When a runtime needs a local account, grant access on the machine through
`runtimes.accounts` with secret references or permit copying the selected native account
with `runtimes.credentials.copy` where supported. Check the applicable backend before
advertising runtime and isolation capabilities.

Use [server mode](server-mode.md) for a TLS reverse proxy, outbound-only remote workers,
and the coordinated restart procedure.
