# Shared test infrastructure

Use [backend.py](backend.py) for core memory/PostgreSQL contract parity and
[app.py](app.py) for its real bus `dispatch`/`ask` wrappers. Domain suites use their
own `tests/contracts/<owner>/harness.py`; the core demo backend does not wire the
whole product; their `side`/`pg_side` fixtures delegate to
[sides.py](sides.py) (`BACKEND_PARAMS`, `iter_side`, `iter_pg_side`). Some `TestApp` methods (`as_role`, `committed_events`, `run_relay`,
`host`) still raise `NotImplementedError`; use the owning suite's implementation.

To opt a contract directory into both backends, re-export these fixtures from its
`conftest.py` (as [core/conftest.py](../contracts/core/conftest.py) does):

```python
from support.backend import backend as backend
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
```

Then a test can exercise the same real bus path on each backend:

```python
from fakes.demo_module import Echo, EchoResult
from support.backend import TestBackend


def test_echo(backend: TestBackend) -> None:
    result = backend.app().dispatch(Echo(backend.seed.workspace_id, "hello"))
    assert result == EchoResult("hello")
    assert len(backend.envelopes()) == 1
```

The `postgres` parameter carries `pg`; use `pg_backend` plus `@pytest.mark.pg`
for PostgreSQL-only assertions. Configure `SKM_TEST_DATABASE_URL` and
`SKM_REQUIRE_PG=1` **before** pytest starts. [conftest.py](../conftest.py) captures
runner controls, clears `SKM_*`, isolates HOME and guards external networking.
Use `pg_dsn`/`clean_test_database`, never a fresh environment lookup or the dev DSN.
[pg.py](pg.py) owns local session databases, migration templates and cleanup;
do not share mutable backend state between tests to save setup time.

[git_repo.py](git_repo.py) provides `init_git_repo(tmp_path / "repo")` and
`repo.commit_file(...)`; [fault_injection.py](fault_injection.py) wraps real ports
at failure boundaries. Only test composition may pass overrides through
`build_app(overrides=...)`. [harness.py](harness.py) runs isolated subprocesses to
test pytest policy itself; ordinary command tests should use their domain harness.

## Golden files

assert_golden(suite, case, actual) uses tests/golden/<suite>/<case>.json or .txt.
JSON uses sorted keys, two spaces and a final newline. A mismatch prints a unified
diff. Explicitly run `uv run --frozen python tools/golden.py update <pattern>` to
regenerate expectations; updated comparisons report XFAIL ("golden updated"),
never PASS. Inspect new/untracked fixtures too; explain golden changes with a
`golden:` reason in the coordinator-owned commit.

A legacy-derived fixture must retain <case>.source.txt beside it, for example:

    source: packages/<owner>/tests/fixtures/<case>.json
    commit: 0d6a393

Record the actual donor path and revision, without importing or modifying it.
Call assert_legacy_source(path) for a legacy fixture outside tests/fixtures/legacy;
`tools/golden.py check` also validates legacy fixture metadata and rejects orphan
goldens.
