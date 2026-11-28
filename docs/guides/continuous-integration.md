# Continuous integration

`.github/workflows/ci.yml` runs on pushes to all branches, on pull requests into `main` and `new`, and on demand.
`tools/ci_shards.py` selects the lanes and matrix cells.

## Job graph

```text
changes ─┬─ lint ──┬─ unit (shard × Python 3.12, 3.15)
         │         ├─ pg   (shard × PostgreSQL 18.7, 19.0)
         │         ├─ e2e  (PostgreSQL 19.0)
         │         └─ compose (deploy stack)
         ├─ typecheck · contracts · docs · workflows · shell · web
         └──────────────────────────────────────────────── CI gate
```

- **changes** plans the run. A pull request takes only the lanes its changed paths need; a push takes all of
  them unless a work-branch commit requests a targeted run.
- **Quality lanes**: `lint` (format and ruff), `typecheck` (pyright), `contracts` (schema, SQL, skill and pack
  checks, plus `ci_shards.py check`), `docs` (local links and anchors), `workflows` (actionlint and zizmor),
  `shell` (shellcheck) and `web` (`make web-check` on Node 26).
- **Test lanes** start once `lint` passes. Each matrix cell runs one shard; the PostgreSQL cells use a fresh
  digest-pinned service container, tuned by `.github/actions/start-postgres`, which also installs a matching
  `pg_dump`.
- **CI gate** is the single required check. Every scheduled lane must succeed and every excluded lane must be skipped.

Actions are pinned to commit SHAs, every job has least-privilege `permissions`, and a newer push cancels an
older run on pull requests and work branches. Every push to `new` or `main` keeps its own run.

## Shards

Every test file belongs to exactly one shard: the first shard whose path prefix matches, or `other`. Shards
follow the module layout (`kernel`, `adapters`, `entrypoints`, the 14 modules, `security`, `recovery`, and
so on). A new test directory therefore never drops out of CI; it lands in `other` until a shard claims it.
`ci_shards.py check` collects every suite and fails when a shard's `pg`/`e2e` flag disagrees with its tests.

Suites select tests by marker, like the Makefile targets they split:

| Suite | Markers | Makefile equivalent |
| --- | --- | --- |
| `unit` | not `pg`, `e2e`, `evals`, `perf` | `make test` plus `make arch` |
| `pg` | `pg`, not `evals`, `perf` | `make test-pg` |
| `e2e` | `e2e` without `pg`, except the compose test | part of `make e2e` |

The unit suite, and `make test`, pass `--timeout 60 --timeout-method signal -o faulthandler_timeout=60`. A hung
unit test then fails with its name and a thread dump, instead of sitting until the job's 30-minute limit. The
`pg` and `e2e` suites keep their longer waits and do not use this bound.

The wall-time critical path after `lint` is the PostgreSQL e2e work. A full run on 2026-11-28 finished in
473 seconds; `PostgreSQL 19.0 / e2e-lifecycle` was the longest job at 407 seconds, of which pytest took 373.
That work is three cells, each with its own Postgres and two xdist workers:

- `e2e-integrations` — instance profiles, extension CLI and the integrations acceptance, CLI and doctor files.
  On that run their slowest calls were about 76, 74 and 101 seconds, and every test in the files is `pg`.
- `e2e-lifecycle` — serve, HTTP, authoring, review and the execution CLI.
- `e2e` — the remaining `tests/e2e/` files, including later additions.

PostgreSQL cells also print `--durations=20`. A targeted rerun of this path should name the cells that were
slow (`pg/e2e-integrations`, `pg/e2e-lifecycle`, `pg/e2e`).

GitHub's `gh run rerun --failed` reruns only the failed cells plus `CI gate`. Use that when the same commit
should be retried. A new commit on a work branch starts a full run unless its message contains `CI-Only:`.

## Targeted runs

After a fix, verify the cells that failed before running everything again. On a push to a work branch (not
`main` or `new`), a `CI-Only:` line in the head commit narrows the run to lanes, shards or single cells:

```text
CI-Only: lint, unit/platform@3.15, pg/hooks@19.0, e2e, web
```

`lane` selects a whole lane, `lane/shard` every cell of a shard, and `lane/shard@version` one cell. An empty selection or unknown
token fails the `changes` job. These runs publish `Targeted CI gate`. Push without the line for the full
`CI gate` required by `new`.

## Reproducing a cell locally

```bash
python tools/ci_shards.py files platform               # the shard's test files
python tools/ci_shards.py run platform --suite unit    # the unit cell
SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test SKM_REQUIRE_PG=1 \
  python tools/ci_shards.py run recovery --suite pg    # a PostgreSQL cell
```

Run the tool through `uv run --frozen` so it uses the project environment. Extra pytest arguments follow `--`.
