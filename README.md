# Swiss Knife Man

SKM is a provider-neutral control plane for planned, reviewed AI-assisted development.
The first public release is `0.1.0`. See the [changelog](CHANGELOG.md) for release details.

## Install and use

Use Python 3.12 or newer. From the repository root, run `uv tool install .` and
check the installation with `skm --version`. For the bundled web UI, use Node.js
22 or newer and run `make web-build` before installing.

`skm --help` lists the command groups. The getting-started guide covers PostgreSQL
setup, local startup, worker registration and the first reviewed run.
[Getting started](docs/guides/getting-started.md) · [CLI reference](docs/reference/cli.md) ·
[Platform support](docs/reference/platform-support.md) ·
[Continuous integration](docs/guides/continuous-integration.md)

## Development

Use Python 3.12+ and uv 0.5.0+:

```sh
uv sync --frozen
uv run --frozen skm --version
make check
```

`uv.lock` pins the resolved environment. Update dependencies deliberately with `uv lock`;
the allowed libraries and their layers are defined by
[ADR 0012](docs/adr/0012-dependency-policy.md).
Schemas live in `src/skm/schemas/`. Packaging includes those schemas and maps
`resources/` to `skm/_resources` and `deploy/compose.local.yaml` to `skm/_deploy/compose.local.yaml`.

`make help` lists defined targets. `make check` runs `fmt-check`, `lint`, `typecheck`, `test`,
`arch`, `docs-check` and `schema-check`. Ruff checks source, tests and tools; Pyright uses strict
source, basic tests and standard tools. Intentionally invalid architecture/plugin fixture trees
are excluded from these general checks; the test code itself remains checked.

`test-pg`, `e2e`, `evals` and `perf` invoke pytest selections outside `make check`.
An empty selection fails with pytest exit 5 (GNU make exit 2). `web-check` checks
the web client and its bundle budgets. `web-dev` starts the development server,
and `web-build` produces `web/dist`.

For a change, prefer targeted checks to the full suite: `make check-touched` lints, type-checks
and validates what the diff touches and prints the tests importing the changed modules. The
[codebase map](docs/architecture/CODEBASE-MAP.md) and the generated
[source index](docs/reference/source-index.md) show where each package lives and which tests cover it.

## Development PostgreSQL and doctor

With Docker Engine/Desktop and Compose v2 installed:

```sh
make db-up doctor
make db-psql
make db-down
```

[The dev compose](deploy/compose.dev.yaml) pins PostgreSQL 16.4, publishes only
`127.0.0.1:54329`, and waits for `pg_isready` before `db-up` succeeds. Its named volume
`skm-dev-pg` belongs to the `skm-dev` compose project (Docker name `skm-dev_skm-dev-pg`).
[The init script](deploy/postgres/init/01-databases.sql) creates separate `skm_dev` and
`skm_test` databases with `pgcrypto` on the first start of an empty volume.
The checked-in credentials are for this local development instance only.

Makefile exports these defaults; shell or make variable overrides take precedence:

```sh
export SKM_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev
export SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test
```

Use `SKM_DATABASE_URL` for development and `SKM_TEST_DATABASE_URL` for tests and doctor's
PostgreSQL probe. They must identify separate databases, including when credentials or URL
spellings differ. Running doctor directly uses the same defaults when variables are unset.

`make db-reset` **deletes all data in `skm_dev` and `skm_test`**, disconnects their clients,
recreates both databases and reinstalls `pgcrypto`. It operates only inside this dev compose
and ignores URL overrides. The reset boundary is the two dev/test databases and this compose's
own volume; the reset recipe preserves the volume and other databases. `db-down` also preserves
the volume. These targets must only be used for this local development instance.

```sh
uv run --frozen python tools/doctor.py --json
uv run --frozen python tools/doctor.py --require pg,node,git
```

Doctor checks Python 3.12+, uv 0.5.0+, lock freshness (`uv lock --check`), Compose v2,
and a psycopg connection to the test database with a two-second connection timeout and
PostgreSQL 16+ requirement. A stopped PostgreSQL produces a failure with `make db-up` as
the recovery hint. Git 2.40+ and Node 22+ are warnings unless `--require` promotes them to mandatory checks. Free disk space below 2 GiB and a file
descriptor limit below 1024 also produce warnings.

The text report has `check | status | detail | hint` columns. `--json` emits
`{"checks":[{"id":"pg","status":"ok","detail":"…","hint":""}],"ok":true}`
with all check rows. Statuses are `ok`, `warn` or `fail`; any mandatory failure exits 1,
and warnings alone exit 0.

## Manual work

Start with the [codebase map](docs/architecture/CODEBASE-MAP.md). Read the owning module,
its schemas and tests, then run the checks for the affected behavior.
Record the executor's actual validation separately from the manual review status.
A review recommendation does not start a reviewer. Follow the owner's instructions for
commits and reports; there is no mandatory commit or JSON report per leaf in manual work.
Keep the donor at `../swissknifeman/` read-only and preserve user changes and deletions.
