"""Run the actual pytest policy against tiny suites, without a database/provider."""

from collections.abc import Callable

import pytest

pytestmark = pytest.mark.integration
type Runner = Callable[..., pytest.RunResult]

PG_TEST = """
import pytest
@pytest.mark.pg
def test_pg_gate():
    assert False, 'pg body must not run without a DSN'
"""


def test_pg_without_dsn_skips_locally(runner: Runner) -> None:
    result = runner(PG_TEST, args=("-rs",))
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*SKM_TEST_DATABASE_URL is not set*"])


@pytest.mark.parametrize("marker", ["pg", "e2e", "evals"])
def test_service_gates_run_before_session_fixtures(runner: Runner, marker: str) -> None:
    result = runner(f"""
import pytest
@pytest.fixture(scope='session')
def external_service():
    pytest.fail('must not initialize a database or paid runtime')
@pytest.mark.{marker}
def test_external(external_service):
    assert False
""")
    result.assert_outcomes(skipped=1)


def test_required_pg_without_test_dsn_errors_even_with_dev_dsn(runner: Runner) -> None:
    result = runner(PG_TEST, controls={"SKM_REQUIRE_PG": "1", "SKM_DATABASE_URL": "postgresql:///skm_dev"})
    result.assert_outcomes(errors=1)
    assert result.ret == 1
    result.stdout.fnmatch_lines(["*SKM_REQUIRE_PG=1 but SKM_TEST_DATABASE_URL is not set*"])


def test_explicit_test_dsn_is_captured_before_environment_isolation(runner: Runner) -> None:
    result = runner(
        """
import pytest
@pytest.mark.pg
def test_dsn(pg_dsn, visible_env):
    assert pg_dsn == 'postgresql:///skm_test'
    assert not any(k.startswith('SKM_') for k in visible_env)
""",
        controls={"SKM_REQUIRE_PG": "1", "SKM_TEST_DATABASE_URL": "postgresql:///skm_test"},
    )
    result.assert_outcomes(passed=1)


def test_evals_are_skipped_without_explicit_opt_in(runner: Runner) -> None:
    result = runner("""
import pytest
@pytest.mark.evals
def test_paid():
    assert False, 'must not invoke a paid provider'
""")
    result.assert_outcomes(skipped=1)


def test_evals_opt_in_allows_the_test_body(runner: Runner) -> None:
    result = runner(
        """
import pytest
@pytest.mark.evals
def test_paid():
    assert 2 + 2 == 4  # gate diagnostic; no provider call
""",
        controls={"SKM_EVALS": "1"},
    )
    result.assert_outcomes(passed=1)


def test_e2e_also_requires_the_test_dsn(runner: Runner) -> None:
    result = runner(PG_TEST.replace("mark.pg", "mark.e2e"), controls={"SKM_REQUIRE_PG": "1"})
    result.assert_outcomes(errors=1)


def test_e2e_requires_git_before_running_the_body(runner: Runner) -> None:
    result = runner(
        PG_TEST.replace("mark.pg", "mark.e2e"),
        controls={"SKM_TEST_DATABASE_URL": "postgresql:///skm_test", "PATH": ""},
    )
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*e2e tests require git in PATH*"])


def test_host_skm_variables_and_home_are_isolated(runner: Runner) -> None:
    result = runner(
        """
from pathlib import Path
import pytest
@pytest.mark.integration
def test_isolation(visible_env, tmp_path):
    assert not any(k.startswith('SKM_') for k in visible_env)
    assert Path(visible_env['HOME']) == tmp_path / 'home'
    assert Path(visible_env['HOME']).is_dir()
""",
        controls={"SKM_TOKEN": "host-secret", "SKM_BOOTSTRAP": "host-bootstrap"},
    )
    result.assert_outcomes(passed=1)


def test_pure_tests_do_not_allocate_tmp_path(runner: Runner) -> None:
    result = runner(
        """
import socket
from pathlib import Path
import pytest

@pytest.fixture
def tmp_path():
    pytest.fail('a pure test must not request a temporary directory')

def test_pure(visible_env):
    assert not any(name.startswith('SKM_') for name in visible_env)
    assert Path(visible_env['HOME']).is_dir()
    sock = socket.socket.__new__(socket.socket)
    with pytest.raises(RuntimeError, match='loopback'):
        sock.connect(('192.0.2.1', -1))
""",
        controls={"SKM_TOKEN": "host-secret"},
    )
    result.assert_outcomes(passed=1)


def test_environment_is_isolated_through_session_and_module_finalizers(runner: Runner) -> None:
    result = runner(
        """
import os
from pathlib import Path
import pytest

HOST_HOME = '/host-home-for-isolation-regression'

def snapshot():
    env = dict(os.environ)
    assert not any(name.startswith('SKM_') for name in env)
    assert env['HOME'] != HOST_HOME
    assert Path(env['HOME']).is_dir()
    return env

@pytest.fixture(scope='session')
def session_env():
    before = snapshot()
    yield before
    snapshot()
    assert Path(before['HOME']).is_dir()

@pytest.fixture(scope='module')
def module_env(session_env):
    before = snapshot()
    yield before
    snapshot()

@pytest.mark.integration
@pytest.mark.pg
def test_snapshots(session_env, module_env, visible_env, tmp_path, pg_dsn):
    assert 'SKM_TOKEN' not in session_env
    assert 'SKM_TOKEN' not in module_env
    assert 'SKM_TOKEN' not in visible_env
    assert Path(visible_env['HOME']) == tmp_path / 'home'
    assert pg_dsn == 'postgresql:///skm_test'
    snapshot()
""",
        controls={
            "SKM_TOKEN": "host-secret",
            "SKM_TEST_DATABASE_URL": "postgresql:///skm_test",
            "SKM_REQUIRE_PG": "1",
            "HOME": "/host-home-for-isolation-regression",
        },
    )
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize("scope", ["function", "module", "session"])
@pytest.mark.parametrize("eval_first", [False, True])
def test_network_guard_covers_fixture_lifecycle_and_preserves_eval_opt_in(
    runner: Runner, scope: str, eval_first: bool
) -> None:
    fixtures = f"""
import socket
import pytest

cleanups = []

def external_probe(*, allowed=False):
    # __new__ leaves fd=-1: no socket syscall or network traffic is needed.
    sock = socket.socket.__new__(socket.socket)
    for method in ('connect', 'connect_ex'):
        if allowed:
            with pytest.raises((OSError, OverflowError)):
                getattr(sock, method)(('192.0.2.1', -1))
        else:
            with pytest.raises(RuntimeError, match='loopback'):
                getattr(sock, method)(('192.0.2.1', -1))

def cleanup(kind, *, allowed=False):
    external_probe(allowed=allowed)
    cleanups.append((kind, allowed))

@pytest.fixture(scope='session', autouse=True)
def completed_cleanups():
    yield
    assert sorted(cleanups) == [
        ('factory', False), ('factory', True), ('request', False), ('request', True),
    ]

@pytest.fixture(scope={scope!r})
def ordinary_service():
    external_probe()
    yield
    external_probe()

@pytest.fixture(scope={scope!r})
def eval_service():
    external_probe(allowed=True)
    yield
    external_probe(allowed=True)

@pytest.fixture(scope={scope!r})
def deferred_factory(request):
    def register(*, allowed):
        request.addfinalizer(lambda: cleanup('factory', allowed=allowed))
    return register
"""
    ordinary_test = """
def test_ordinary(ordinary_service, deferred_factory, request):
    external_probe()
    request.addfinalizer(lambda: cleanup('request'))
    deferred_factory(allowed=False)
"""
    eval_test = """

@pytest.mark.evals
def test_opted_in_eval(eval_service, deferred_factory, request):
    external_probe(allowed=True)
    request.addfinalizer(lambda: cleanup('request', allowed=True))
    deferred_factory(allowed=True)
"""
    test_bodies = eval_test + ordinary_test if eval_first else ordinary_test + eval_test
    result = runner(
        fixtures + test_bodies,
        controls={"SKM_EVALS": "1"},
    )
    # Each cleanup retains its registration policy, whatever test finishes last.
    result.assert_outcomes(passed=2)


@pytest.mark.parametrize(("profile", "examples"), [("dev", 100), ("ci", 500)])
def test_hypothesis_profiles_are_effective(runner: Runner, profile: str, examples: int) -> None:
    result = runner(
        f"""
from hypothesis import settings
def test_profile():
    assert settings.default.max_examples == {examples}
    assert settings.default.deadline is {"None" if profile == "ci" else "not None"}
    assert settings.default.derandomize is {profile == "ci"}
""",
        controls={"HYPOTHESIS_PROFILE": profile},
    )
    result.assert_outcomes(passed=1)


def test_network_is_blocked_before_external_connect(runner: Runner) -> None:
    result = runner("""
import socket
import pytest
@pytest.mark.parametrize('method', ['connect', 'connect_ex'])
def test_network(method):
    with socket.socket() as sock, pytest.raises(RuntimeError, match='loopback'):
        getattr(sock, method)(('192.0.2.1', 9))
def test_loopback():
    with socket.socket() as server, socket.socket() as client:
        server.bind(('127.0.0.1', 0))
        server.listen()
        client.connect(server.getsockname())
        accepted, address = server.accept()
        accepted.close()
""")
    result.assert_outcomes(passed=3)


def test_network_guard_delegates_loopback_and_unix_without_creating_sockets(runner: Runner) -> None:
    result = runner("""
import socket
import pytest

@pytest.mark.parametrize('host', ['127.0.0.1', '::1'])
def test_loopback_delegates(host):
    sock = socket.socket.__new__(socket.socket)
    for method in ('connect', 'connect_ex'):
        with pytest.raises((OSError, OverflowError)):
            getattr(sock, method)((host, -1))

class UnixProbe(socket.socket):
    @property
    def family(self):
        return socket.AF_UNIX

def test_unix_delegates():
    sock = UnixProbe.__new__(UnixProbe)
    for method in ('connect', 'connect_ex'):
        with pytest.raises((OSError, TypeError)):
            getattr(sock, method)('not-an-open-unix-socket')
""")
    result.assert_outcomes(passed=3)


def test_golden_update_remains_xfailed_with_strict_xfails(runner: Runner) -> None:
    result = runner(
        """
from support import golden
def test_update(tmp_path):
    golden.GOLDEN_ROOT = tmp_path
    golden.assert_golden('example', 'case', {'a': 1})
""",
        controls={"SKM_GOLDEN_UPDATE": "1"},
        args=("-rx",),
    )
    result.assert_outcomes(xfailed=1)
    result.stdout.fnmatch_lines(["*golden updated*"])


def test_unknown_marker_is_an_error(runner: Runner) -> None:
    result = runner("""
import pytest
@pytest.mark.misspelled
def test_unknown(): pass
""")
    result.assert_outcomes(errors=1)


def test_warnings_are_errors(runner: Runner) -> None:
    result = runner("""
import warnings
def test_warning():
    warnings.warn('unexpected warning', UserWarning)
""")
    result.assert_outcomes(failed=1)
