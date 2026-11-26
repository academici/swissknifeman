"""Runner controls, isolation and opt-in gates shared by all test levels."""

import os
import shutil
import socket
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path

import pytest
from hypothesis import settings

from skm.platform.logging import setup as logging_setup
from support import golden

pytest_plugins = ["pytester", "support.harness"]


@dataclass(frozen=True)
class RunnerControls:
    test_dsn: str
    require_pg: bool
    evals: bool
    golden_update: bool
    host_home: str = ""
    container_image: str = ""


CONTROLS = pytest.StashKey[RunnerControls]()


@dataclass
class _NetworkPolicy:
    allowed: bool = False


NETWORK_POLICY = pytest.StashKey[_NetworkPolicy]()


@contextmanager
def _network_access(policy: _NetworkPolicy, *, allowed: bool) -> Iterator[None]:
    previous = policy.allowed
    policy.allowed = allowed
    try:
        yield
    finally:
        policy.allowed = previous


def pytest_configure(config: pytest.Config) -> None:
    # Explicit derandomize: on a CI host (CI=true) Hypothesis derandomizes its default, which "dev" inherits.
    settings.register_profile("dev", max_examples=100, deadline=200, derandomize=False)
    settings.register_profile("ci", max_examples=500, deadline=None, derandomize=True)
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
    # Capture runner controls before any user fixture can see the host environment.
    workerinput = getattr(config, "workerinput", None)
    xdist_controls = workerinput.get("skm_controls") if isinstance(workerinput, dict) else None
    if isinstance(xdist_controls, dict):
        config.stash[CONTROLS] = RunnerControls(
            test_dsn=str(xdist_controls.get("test_dsn", "")),
            require_pg=bool(xdist_controls.get("require_pg", False)),
            evals=bool(xdist_controls.get("evals", False)),
            golden_update=bool(xdist_controls.get("golden_update", False)),
            host_home=str(xdist_controls.get("host_home", "")),
            container_image=str(xdist_controls.get("container_image", "")),
        )
    else:
        config.stash[CONTROLS] = RunnerControls(
            test_dsn=os.environ.get("SKM_TEST_DATABASE_URL", "").strip(),
            require_pg=os.environ.get("SKM_REQUIRE_PG") == "1",
            evals=os.environ.get("SKM_EVALS") == "1",
            golden_update=os.environ.get("SKM_GOLDEN_UPDATE") == "1",
            host_home=os.environ.get("HOME", ""),
            container_image=os.environ.get("SKM_TEST_CONTAINER_IMAGE", "").strip(),
        )
    if isinstance(workerinput, dict):
        # An xdist worker always runs execnet's I/O thread, so Python 3.14+ flags every deliberate
        # fork() in crash and ownership tests as forking a multi-threaded process. Single-process
        # runs keep the check.
        config.addinivalue_line(
            "filterwarnings",
            r"ignore:This process \(pid=\d+\) is multi-threaded, use of fork\(\) may lead to deadlocks"
            ":DeprecationWarning",
        )
    # Config cleanups run after all module/session finalizers, including on errors.
    home = tempfile.TemporaryDirectory(prefix="skm-test-home-")
    config.add_cleanup(home.cleanup)
    patch = pytest.MonkeyPatch()
    config.add_cleanup(patch.undo)
    for name in tuple(os.environ):
        if name.startswith("SKM_"):
            patch.delenv(name)
    patch.setenv("HOME", home.name)
    patch.setattr(golden, "UPDATE", config.stash[CONTROLS].golden_update)
    policy = _NetworkPolicy()
    config.stash[NETWORK_POLICY] = policy
    _install_network_guard(patch, policy)
    _install_finalizer_guard(patch, policy)


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node: object) -> None:
    """Forward captured RunnerControls to xdist workers after SKM_* env scrubbing."""
    workerinput = getattr(node, "workerinput", None)
    node_config = getattr(node, "config", None)
    controls = node_config.stash.get(CONTROLS, None) if node_config is not None else None
    if isinstance(workerinput, dict) and controls is not None:
        workerinput["skm_controls"] = {
            "test_dsn": controls.test_dsn,
            "require_pg": controls.require_pg,
            "evals": controls.evals,
            "golden_update": controls.golden_update,
            "host_home": controls.host_home,
            "container_image": controls.container_image,
        }


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    # Gate before session fixtures can open a database or start a live runtime.
    controls = item.config.stash[CONTROLS]
    if item.get_closest_marker("evals") and not controls.evals:
        pytest.skip("live evals require SKM_EVALS=1")
    if item.get_closest_marker("pg") or item.get_closest_marker("e2e"):
        if not controls.test_dsn:
            if controls.require_pg:
                pytest.fail("SKM_REQUIRE_PG=1 but SKM_TEST_DATABASE_URL is not set", pytrace=False)
            pytest.skip("SKM_TEST_DATABASE_URL is not set")
        if item.get_closest_marker("e2e") and shutil.which("git") is None:
            pytest.fail("e2e tests require git in PATH", pytrace=False)


@pytest.hookimpl(wrapper=True, tryfirst=True, specname="pytest_runtest_setup")
def pytest_network_setup(item: pytest.Item) -> Iterator[None]:
    allowed = item.config.stash[CONTROLS].evals and item.get_closest_marker("evals") is not None
    with _network_access(item.config.stash[NETWORK_POLICY], allowed=allowed):
        yield


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    allowed = item.config.stash[CONTROLS].evals and item.get_closest_marker("evals") is not None
    with _network_access(item.config.stash[NETWORK_POLICY], allowed=allowed):
        yield


def _guard_finalizer(policy: _NetworkPolicy, finalizer: Callable[[], object]) -> Callable[[], object]:
    allowed = policy.allowed

    def finalize() -> object:
        # Retain the registration policy even when another test triggers cleanup.
        with _network_access(policy, allowed=allowed):
            return finalizer()

    return finalize


def _install_finalizer_guard(patch: pytest.MonkeyPatch, policy: _NetworkPolicy) -> None:
    fixture_add_finalizer = pytest.FixtureDef.addfinalizer
    item_add_finalizer = pytest.Item.addfinalizer

    def fixture_finalizer(fixturedef: pytest.FixtureDef[object], finalizer: Callable[[], object]) -> None:
        fixture_add_finalizer(fixturedef, _guard_finalizer(policy, finalizer))

    def item_finalizer(item: pytest.Item, finalizer: Callable[[], object]) -> None:
        item_add_finalizer(item, _guard_finalizer(policy, finalizer))

    # Cover both request.addfinalizer routes for the entire session, including
    # registrations from test bodies and factories called after fixture setup.
    patch.setattr(pytest.FixtureDef, "addfinalizer", fixture_finalizer)
    patch.setattr(pytest.Item, "addfinalizer", item_finalizer)


@pytest.fixture
def pg_dsn(request: pytest.FixtureRequest) -> str:
    """Only the explicit test DSN; never fall back to SKM_DATABASE_URL."""
    if not (request.node.get_closest_marker("pg") or request.node.get_closest_marker("e2e")):
        pytest.fail("pg_dsn requires the pg or e2e marker")
    return request.config.stash[CONTROLS].test_dsn


@pytest.fixture(autouse=True)
def _isolated_env(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scrub controls for every test; allocate a per-test HOME only for local IO tests."""
    for name in tuple(os.environ):
        if name.startswith("SKM_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(golden, "UPDATE", request.config.stash[CONTROLS].golden_update)
    is_integration = "integration" in request.node.path.relative_to(request.config.rootpath).parts
    if (
        is_integration
        or request.node.get_closest_marker("integration")
        or request.node.get_closest_marker("e2e")
    ):
        tmp_path: Path = request.getfixturevalue("tmp_path")
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))


@pytest.fixture(autouse=True)
def _restore_logging_sink() -> Iterator[None]:
    """Keep the process-wide log sink of one test out of the next.

    An in-process CLI call configures logging for the whole process, with that test's stderr as the
    stream and its --quiet/--verbose level. Without the restore, a later test on the same xdist worker
    logs into a closed capture or below the level it expects, depending only on scheduling.
    """
    settings = logging_setup._state.settings
    yield
    logging_setup._state.settings = settings


def _install_network_guard(patch: pytest.MonkeyPatch, policy: _NetworkPolicy) -> None:
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def check_address(sock: socket.socket, address: object) -> None:
        if policy.allowed or sock.family == socket.AF_UNIX:
            return
        if isinstance(address, tuple) and address:
            try:
                if ip_address(address[0]).is_loopback:
                    return
            except ValueError:
                pass
        raise RuntimeError("tests may connect only to loopback addresses (live evals are opt-in)")

    def guarded_connect(sock: socket.socket, address: tuple | str | bytes) -> None:
        check_address(sock, address)
        connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: tuple | str | bytes) -> int:
        check_address(sock, address)
        return connect_ex(sock, address)

    patch.setattr(socket.socket, "connect", guarded_connect)
    patch.setattr(socket.socket, "connect_ex", guarded_connect_ex)


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    return state
