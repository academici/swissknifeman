"""Isolated SKM subprocesses for acceptance tests and their browser launcher."""

from __future__ import annotations

import ctypes
import json as jsonlib
import os
import signal
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack, suppress
from dataclasses import dataclass, replace
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from typing import Any, ClassVar, Literal, cast, override
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import psycopg

from skm.adapters.checks.lifecycle import TrustedCheckLauncher
from skm.adapters.checks.registry import build_check_registry
from skm.adapters.git.repo_inspect import GitRepositoryInspector
from skm.adapters.git.runner import GitRunner
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.adapters.sandbox.registry import build_isolation_registry
from skm.application_bus.host import HostServices
from skm.bootstrap.builtins import builtin_runtime_data
from skm.bootstrap.modules import MANIFESTS
from skm.bootstrap.plugin_distribution import RuntimeDataFiles
from skm.entrypoints.cli.context import CliOptions
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.main import Backend, main, production_backend
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.execution.host.isolation import IsolationSpec, WrappedCommand
from skm.modules.execution.ports import CheckRunnerRegistry
from skm.modules.extensions.domain.payload import PackPayload, PayloadFile
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.public import ProcessOwnership
from skm.modules.workspace.ports import RepositoryInspector
from skm.modules.workspace.public import MountView, checkout_locator
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.system_clock import SystemClock
from support.pg import PgSession, check_admin_dsn

__all__ = ["CliResult", "Instance", "ManagedProcess"]

_ROOT = Path(__file__).resolve().parents[2]
_CLI = (sys.executable, "-c", "from support.processes import _cli_main; raise SystemExit(_cli_main())")
_SUPERVISOR = "from support.processes import _supervise; raise SystemExit(_supervise())"
_STOP_GRACE = _REAP_GRACE = 10.0
Service = Literal["serve", "worker"]


@dataclass(frozen=True, slots=True)
class CliResult:
    exit_code: int
    stdout: str
    stderr: str
    json: JsonValue | None


@dataclass(frozen=True, slots=True)
class ManagedProcess:
    process: subprocess.Popen[bytes]  # noqa: TID251 - owned child

    @classmethod
    def launch(
        cls, argv: tuple[str, ...], cwd: Path, env: Mapping[str, str], stdout: Path, stderr: Path
    ) -> ManagedProcess:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            process = subprocess.Popen(  # noqa: TID251 - own the service subreaper
                (sys.executable, "-c", _SUPERVISOR, str(_STOP_GRACE), *argv),
                cwd=cwd,
                env={**env, "PYTHONPATH": str(_ROOT / "tests")},
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
        return cls(process)

    def exited(self) -> bool:
        if self.process.returncode is not None:
            return True
        return os.waitid(os.P_PID, self.process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

    def stop(self, sig: int = signal.SIGTERM) -> int:
        if not self.exited():
            # The unreaped direct child still owns its PID. Keep it alive to reap the service tree.
            with suppress(ProcessLookupError):
                os.kill(self.process.pid, signal.SIGUSR1 if sig == signal.SIGKILL else sig)
        return self.process.wait(timeout=_STOP_GRACE + _REAP_GRACE + 2)


def _kill_and_reap() -> None:
    deadline = monotonic() + _REAP_GRACE
    while True:
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return
        # Only this single-threaded subreaper waits on these direct children. Their PIDs
        # cannot be reused until reaped. Killing a parent exposes its surviving children.
        for pid in Path("/proc/thread-self/children").read_text().split():
            with suppress(ProcessLookupError):
                os.kill(int(pid), signal.SIGKILL)
        if monotonic() >= deadline:
            raise TimeoutError("timed out reaping the acceptance process tree")
        sleep(0.01)


def _supervise() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "could not establish an acceptance process subreaper")
    stop_signal = None

    def stop(sig: int, _frame: object) -> None:
        nonlocal stop_signal
        stop_signal = sig

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGUSR1, stop)
    grace, *argv = sys.argv[1:]
    child = subprocess.Popen(argv, start_new_session=True)  # noqa: TID251 - direct, supervised service
    try:
        deadline = None
        while child.poll() is None:
            if stop_signal == signal.SIGUSR1 or (deadline is not None and monotonic() >= deadline):
                child.kill()
                child.wait(timeout=_REAP_GRACE)
                break
            if stop_signal == signal.SIGTERM and deadline is None:
                child.terminate()
                deadline = monotonic() + float(grace)
            sleep(0.01)
        code = child.wait()
        return code if code >= 0 else 128 - code
    finally:
        _kill_and_reap()


def _wait_until(predicate: Callable[[], bool], timeout: float, what: str) -> None:
    deadline = monotonic() + timeout
    while not predicate():
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {what}")
        sleep(min(remaining, 0.2))


def _result(result: CliResult) -> JsonObject:
    return cast("JsonObject", cast("JsonObject", result.json)["result"])


class Instance:
    """A disposable PostgreSQL clone, profile and supervised process tree per service."""

    def __init__(
        self, tmp_path: Path, *, db_dsn: str, runtime: str = "fake", serve: bool = True, worker: bool = True
    ) -> None:
        if runtime != "fake":
            raise ValueError("acceptance instances only support the fake runtime")
        check_admin_dsn(db_dsn)
        self.root = tmp_path.resolve()
        self.state_dir = self.root / "state"
        self.bootstrap_path = self.root / "bootstrap.toml"
        self.owner_token = ""
        self.workspace_id = ""
        self.instance_id = ""
        self.worker_id = ""
        self.host_id = ""
        self.dsn = ""
        self.url = ""
        self._db_dsn = db_dsn
        self._serve, self._worker = serve, worker
        self._stack = ExitStack()
        self._processes: dict[str, ManagedProcess] = {}
        self._logs = self.root / "logs"
        self._env = {
            "PATH": os.defpath,
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "xdg-state"),
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "GIT_ALLOW_PROTOCOL": "file",
            "SKM_BOOTSTRAP": str(self.bootstrap_path),
            "SKM_TEST_FAKE_STATE": str(self.state_dir),
        }

    def __enter__(self) -> Instance:
        with ExitStack() as setup:
            self._logs.mkdir(parents=True)
            Path(self._env["HOME"]).mkdir()
            session = PgSession(worker="m5" + uuid4().hex[:12], pid=os.getpid())
            setup.callback(session.close)
            setup.callback(self._stop_services)
            self.dsn = session.open(self._db_dsn).dsn
            self._env["SKM_DATABASE_URL"] = self.dsn
            init = _result(self.cli("init", "--state-dir", str(self.state_dir), "--host-name", "m5"))
            self.workspace_id = str(cast("JsonObject", init["workspace"])["workspace_id"])
            self.instance_id = str(init["instance_id"])
            self.owner_token = (self.state_dir / "secrets/owner.token").read_text().strip()
            if self._serve:
                self.start("serve")
            if self._worker:
                self.start("worker")
            self._stack = setup.pop_all()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stack.close()

    def cli(
        self, *args: str, json: bool = True, check: bool = True, timeout_seconds: float = 60
    ) -> CliResult:
        name = f"cli-{uuid4().hex}"
        out, err = self._log_paths(name)
        options = ("--json",) if json else ()
        process = ManagedProcess.launch((*_CLI, *options, *args), self.root, self._env, out, err)
        try:
            _wait_until(process.exited, timeout_seconds, f"skm {args[0]}")
        finally:
            code = process.stop()
        stdout, stderr = out.read_text(errors="replace"), err.read_text(errors="replace")
        decoded: JsonValue | None = None
        if json and stdout:
            try:
                decoded = cast("JsonValue", jsonlib.loads(stdout))
            except ValueError:
                if code == 0:
                    raise
        if check and code:
            raise AssertionError(f"skm {args[0]} exited {code}\n{stdout}\n{stderr}")
        return CliResult(code, stdout, stderr, decoded)

    def start(self, name: Service) -> ManagedProcess:
        if name in self._processes:
            raise ValueError(f"{name} has already started")
        env = dict(self._env)
        launched_at = SystemClock().now()
        if name == "serve":
            if not self.url:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    self.url = f"http://127.0.0.1:{listener.getsockname()[1]}"
            argv = (*_CLI, "serve", "--bind", self.url.removeprefix("http://"))
        else:
            self._register_worker()
            self._prepare_fake_scripts()
            env = self._http_worker_env() if self.url else env
            argv = (*_CLI, "worker", "start", "--worker", self.worker_id, "--capacity", "1")
        process = ManagedProcess.launch(argv, self.root, env, *self._log_paths(name))
        self._processes[name] = process
        try:
            with httpx.Client(timeout=1, trust_env=False) as http:
                self.wait_until(
                    lambda: (
                        self._running(name)
                        and (self._ready(http) if name == "serve" else self._heartbeat(launched_at))
                    ),
                    what=f"{name} readiness",
                )
        except BaseException:
            self.kill(name)
            raise
        return process

    def kill(self, name: str, sig: int = signal.SIGKILL) -> None:
        process = self._processes.get(name)
        if process is not None:
            process.stop(sig)
            del self._processes[name]

    def restart(self, name: Service) -> ManagedProcess:
        self.kill(name, signal.SIGTERM)
        return self.start(name)

    def wait_until(self, predicate: Callable[[], bool], *, timeout_seconds: float = 30, what: str) -> None:
        try:
            _wait_until(predicate, timeout_seconds, what)
        except TimeoutError as error:
            for name in self._processes:
                error.add_note(f"{name}:\n{self.logs(name)}")
            raise

    def logs(self, name: str) -> str:
        return "\n".join(path.read_text(errors="replace") for path in self._log_paths(name) if path.exists())

    def _log_paths(self, name: str) -> tuple[Path, Path]:
        return self._logs / f"{name}.stdout", self._logs / f"{name}.stderr"

    def _stop_services(self) -> None:
        with ExitStack() as cleanup:
            for name in self._processes:
                cleanup.callback(self.kill, name, signal.SIGTERM)

    def _running(self, name: Service) -> bool:
        if self._processes[name].exited():
            raise RuntimeError(f"{name} exited before it was ready\n{self.logs(name)}")
        return True

    def _ready(self, http: httpx.Client) -> bool:
        try:
            return http.get(f"{self.url}/health/ready").status_code == 200
        except httpx.TransportError:
            return False

    def _heartbeat(self, launched_at: datetime) -> bool:
        with psycopg.connect(self.dsn, connect_timeout=2) as conn:
            row = conn.execute(
                "SELECT last_heartbeat_at FROM skm_workspace.workers WHERE id = %s", (self.worker_id,)
            ).fetchone()
            return bool(row and row[0] and row[0] >= launched_at)

    def _register_worker(self) -> None:
        if self.worker_id:
            return
        registration = _result(self.cli("host", "register", "m5"))
        self.host_id = str(registration["host_id"])
        registration = _result(
            self.cli(
                "worker",
                "register",
                "m5-worker",
                "--host",
                self.host_id,
                "--runtime",
                "fake",
                "--isolation",
                "worktree",
                "--isolation",
                "landlock",
                "--save-token",
                "--skm-version",
                "2.0.0",
            )
        )
        self.worker_id = str(registration["worker_id"])

    def prepare_project(self) -> str:
        from fixtures.execution.protocol import AUTHOR

        self._register_worker()
        project = _result(self.cli("project", "create", "m5", "--title", "M5 acceptance"))
        project_id = str(project["project_id"])
        git = GitRunner()
        repo = self.root / "repository"
        repo.mkdir()
        git.run(repo, ["init", "-b", "main"])
        (repo / "README.md").write_text("# Synthetic acceptance repository\n")
        git.run(repo, ["add", "README.md"])
        git.run_bytes(repo, ["commit", "-m", "Initial fixture"], env=AUTHOR)
        binding = _result(
            self.cli(
                "repo", "bind", str(repo), "--project", project_id, "--mount", "main", "--register", "--yes"
            )
        )
        # This synthetic browser stand models the local half in its private fixture directory.
        # The HTTP worker still receives an opaque mount from the real control plane.
        locator = checkout_locator(uuid4())
        with psycopg.connect(self.dsn) as connection:
            changed = connection.execute(
                "UPDATE skm_workspace.checkout_bindings SET local_locator = %s WHERE id = %s",
                (locator, UUID(str(binding["binding_id"]))),
            ).rowcount
        assert changed == 1
        (self.state_dir / "m5-checkout.json").write_text(
            jsonlib.dumps({"locator": locator, "root": str(repo.resolve())}), encoding="utf-8"
        )
        git.run(repo, ["branch", "m5-integration"])
        self.cli("ext", "sync")
        settings = self.root / "acceptance-settings.json"
        settings.write_text(
            jsonlib.dumps(
                {
                    "schema": "urn:skm:settings:document:v1",
                    "artifacts": {"storage": {"min_free_bytes": 0}},
                    "runtimes": {
                        "allowed": ["fake"],
                        "preference": ["fake"],
                        "config_isolation": {"required": False},
                        "role_routing": {"executor": {"runtime": "fake"}, "reviewer": {"runtime": "fake"}},
                    },
                    "execution": {
                        "workflow": {"profile": "quick-fix", "profile_by_work_kind": {"code": "quick-fix"}},
                        "integration": {"branch": "m5-integration"},
                        "review": {"max_rounds": 4},
                        "advisor": {"enabled": False},
                    },
                    "worker": {"disk_min_bytes": 0},
                }
            )
        )
        self.cli(
            "config", "import", str(settings), "--scope", "instance", "--reason", "Synthetic M5 run", "--yes"
        )
        self.cli("config", "set", "worker.disk_min_bytes", "0", "--scope", "instance", "--yes")
        return project_id

    def _prepare_fake_scripts(self) -> None:
        source = _ROOT / "tests/fixtures/runtimes/fake"
        scripts = self.state_dir / "m5-scenarios"
        scripts.mkdir(exist_ok=True)
        for name in ("question", "review-green"):
            copyfile(source / f"{name}.toml", scripts / f"{name}.toml")
        for name in ("check-rework", "success"):
            scenario = (source / f"{name}.toml").read_text()
            # Keep the first agent stream open while Chromium opens the attempt page.
            if name == "check-rework":
                scenario = scenario.replace(
                    '[[step]]\naction = "write_file"',
                    '[[step]]\naction = "emit"\n'
                    'event = {type = "text_delta", text = "First synthetic implementation"}\n'
                    '[[step]]\naction = "sleep_ms"\nms = 1600\n[[step]]\naction = "write_file"',
                )
            (scripts / f"{name}.toml").write_text(
                scenario.replace(r"\"performed\": false", r"\"performed\": true")
            )
        (scripts / "script.toml").write_text(
            '[[rule]]\nrole = "executor"\ninvocation = 1\nscenario = "check-rework.toml"\n'
            '[[rule]]\nrole = "executor"\ninvocation = 2\nscenario = "question.toml"\n'
            '[[rule]]\nrole = "reviewer"\nscenario = "review-green.toml"\n'
            '[[rule]]\nrole = "*"\nscenario = "success.toml"\n'
        )

    def _http_worker_env(self) -> dict[str, str]:
        bootstrap = self.root / "worker.toml"
        token_path = self.state_dir / "secrets/workers" / f"{self.worker_id}.token"
        bootstrap.write_text(
            f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{self.instance_id}"\n'
            '[access]\nmode = "http"\n[api]\n'
            f'endpoint = "{self.url}/api/v1"\ncredential = {jsonlib.dumps(f"secret://file/{token_path}")}\n'
            f"[paths]\nstate_dir = {jsonlib.dumps(str(self.state_dir))}\n"
            f'[host]\nid = "{self.host_id}"\nname = "m5"\n'
        )
        env = {**self._env, "SKM_BOOTSTRAP": str(bootstrap)}
        del env["SKM_DATABASE_URL"]
        return env


class _DetectedFake(FakeRuntime):
    @override
    def detect(self, probe: DetectProbe) -> RuntimeInstallation:
        return replace(
            super().detect(probe),
            version="0.1.0",
            binary_locator="/synthetic/fake",
            auth_state=AuthState.OK,
            details={
                "executable_sha256": "sha256:" + "a" * 64,
                "verification_key": "sha256:" + "b" * 64,
                "adapter_version": "0.1.0",
            },
        )


def _loopback_only(event: str, args: tuple[object, ...]) -> None:
    if event == "socket.connect" and isinstance(args[1], tuple):
        host = cast("tuple[str, ...]", args[1])[0]
    elif event == "socket.getaddrinfo" and isinstance(args[0], str):
        host = args[0]
    else:
        return
    if host != "localhost" and not ip_address(host).is_loopback:
        raise RuntimeError("acceptance subprocess tried to connect outside loopback")


_packaged_payloads = PackagedBuiltinPacks.payloads


def _fixture_packs(packs: PackagedBuiltinPacks) -> tuple[PackPayload, ...]:
    from fixtures.execution.harness import CATALOG

    catalog_path = "runtimes/models.toml"
    fixture_catalog = CATALOG[CATALOG.index("[runtimes.fake]") :].encode()

    def fixture_file(file: PayloadFile) -> PayloadFile:
        if file.path == catalog_path:
            return replace(file, content=file.content + b"\n" + fixture_catalog)
        if file.path in {"agent-profiles/executor.toml", "agent-profiles/reviewer.toml"}:
            # Prospective readiness has no host attestation for a synthetic runtime.
            content = file.content.replace(b', "workspace_binding"', b"").replace(
                b', "reliable_cancellation"', b""
            )
            return replace(file, content=content)
        return file

    return tuple(
        replace(pack, files=tuple(fixture_file(file) for file in pack.files))
        for pack in _packaged_payloads(packs)
        if any(file.path == catalog_path for file in pack.files)
    )


_DENY_NETWORK = """
import ctypes as c, errno, os, sys
seccomp = c.CDLL("libseccomp.so.2")
seccomp.seccomp_init.argtypes = [c.c_uint32]
seccomp.seccomp_init.restype = c.c_void_p
seccomp.seccomp_syscall_resolve_name.argtypes = [c.c_char_p]
seccomp.seccomp_rule_add.argtypes = [c.c_void_p, c.c_uint32, c.c_int, c.c_uint]
seccomp.seccomp_load.argtypes = [c.c_void_p]
seccomp.seccomp_release.argtypes = [c.c_void_p]
ctx = seccomp.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
if not ctx:
    raise RuntimeError("could not allocate the check seccomp filter")
for call in (b"socket", b"socketpair", b"socketcall", b"io_uring_setup", b"pidfd_getfd"):
    nr = seccomp.seccomp_syscall_resolve_name(call)
    if nr != -1 and seccomp.seccomp_rule_add(ctx, 0x00050000 | errno.EACCES, nr, 0) != 0:
        raise RuntimeError(f"could not deny {call!r} for the check")
if seccomp.seccomp_load(ctx) != 0:
    raise RuntimeError("could not install the check seccomp filter")
seccomp.seccomp_release(ctx)
os.execv(sys.argv[1], sys.argv[1:])
"""


class _OfflineCheckIsolation:
    profile: ClassVar[str] = "acceptance:offline-check"

    def available(self, host: object) -> JsonObject:
        return {"available": True}

    def wrap(self, argv: Sequence[str], spec: IsolationSpec) -> WrappedCommand:
        if spec.network != "none" or not spec.read_only_root or spec.writable or spec.protected:
            raise ValueError("acceptance checks require a read-only, offline request")
        network = (sys.executable, "-I", "-B", "-c", _DENY_NETWORK)
        sandbox = (sys.executable, "-I", "-B", "-m", "skm.adapters.sandbox.landlock_exec")
        options = ("--no-default-rw", "--min-abi", "3", "--")
        ownership = ProcessOwnership(
            owner=spec.owner, kind="pgroup_best_effort", ref=f"pgroup:{spec.owner.unit_id}"
        )
        return WrappedCommand((*network, *sandbox, *options, *argv), spec.env, spec.workdir, ownership)


def _fixture_checks(**options: Any) -> CheckRunnerRegistry:
    registry = build_isolation_registry()
    isolation = _OfflineCheckIsolation()
    registry.register_plugin(isolation.profile, isolation)
    options.update(
        profile=isolation.profile, isolation_registry=registry, process=TrustedCheckLauncher(allowed=True)
    )
    return build_check_registry(**options)


def _synthetic_checkout_backend(
    options: CliOptions,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None] = lambda _value: None,
) -> Backend:
    """Keep the synthetic upgrade and performance fixtures on their legacy checkout path."""
    backend = replace(production_backend(options, environ, on_secret), checkout_operation=None)
    if backend.state_dir is not None:
        host_path = backend.state_dir / "host.json"
        if host_path.is_file():
            payload = jsonlib.loads(host_path.read_text(encoding="utf-8"))
            raw_host_id = payload.get("host_id")
            if isinstance(raw_host_id, str) and raw_host_id:
                host_id = HostId(UUID(raw_host_id))
                host = HostServices(
                    host_id=host_id,
                    surface=Surface.CLI,
                    gateways=GatewayTable(
                        {RepositoryInspector: GitRepositoryInspector(clock=SystemClock())},
                        "host_gateway",
                    ),
                    host_config=dict,
                    operations={
                        spec.name: spec for manifest in MANIFESTS for spec in manifest.host_operations
                    },
                )
                return replace(backend, host_factory=host_context_factory(host, backend.client))
    return backend


def _fixture_checkout_root(state: Path) -> Callable[[MountView], Path] | None:
    inventory = state / "m5-checkout.json"
    if not inventory.is_file():
        return None
    local = jsonlib.loads(inventory.read_text(encoding="utf-8"))
    root = Path(local["root"])

    def resolve(mount: MountView) -> Path:
        binding = mount.binding
        assert binding is not None
        assert binding.state == "active"
        assert binding.local_locator == local["locator"]
        observed = GitRepositoryInspector().observe(str(root))
        assert observed.toplevel == str(root)
        return root

    return resolve


def _cli_main() -> int:
    from skm.bootstrap.runtimes import WorkerRuntimeSettings

    sys.addaudithook(_loopback_only)
    state = Path(os.environ["SKM_TEST_FAKE_STATE"])
    runtime = _DetectedFake(
        state_dir=state,
        allow_pgroup_best_effort=True,
        script=state / "m5-scenarios/script.toml",
    )
    args = [arg for arg in sys.argv[1:] if arg != "--json"]
    if args[:2] == ["repo", "bind"]:
        return main(backend=_synthetic_checkout_backend)
    capabilities = runtime.capabilities()
    capabilities = replace(
        capabilities,
        records={
            key: replace(record, tested_runtime_version=capabilities.adapter_version)
            for key, record in capabilities.records.items()
        },
    )
    fake_data = RuntimeDataFiles("fake", capabilities, (), "fixture:fake", "fixture:fake")
    machine = WorkerRuntimeSettings(
        allowed=frozenset({"fake"}),
        models={"fake": {"fake-a": frozenset({"high"}), "fake-b": frozenset({"high"})}},
    )
    with (
        ExitStack() as seams,
        patch.object(PackagedBuiltinPacks, "payloads", _fixture_packs),
        patch("skm.bootstrap.worker_runtimes.WorkerRuntimes._items", return_value={"fake": runtime}),
        patch("skm.bootstrap.worker.machine_runtime_settings", return_value=lambda: machine),
        patch("skm.bootstrap.worker.worker_checkout_root", return_value=_fixture_checkout_root(state)),
        patch(
            "skm.bootstrap.composition.builtin_runtime_data",
            return_value=(*builtin_runtime_data(), fake_data),
        ),
    ):
        if args[:2] == ["worker", "start"]:
            seams.enter_context(patch("skm.adapters.checks.registry.build_check_registry", _fixture_checks))
        return main()


def _main() -> None:
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    with (
        TemporaryDirectory(prefix="skm-m5-") as root,
        Instance(
            Path(root), db_dsn=os.environ["SKM_TEST_DATABASE_URL"], serve=False, worker=False
        ) as instance,
    ):
        project_id = instance.prepare_project()
        instance.start("serve")
        instance.start("worker")
        print(
            jsonlib.dumps(
                {
                    "backend": instance.url,
                    "token": instance.owner_token,
                    "workspaceId": instance.workspace_id,
                    "projectId": project_id,
                    "logsDirectory": str(instance.root / "logs"),
                }
            ),
            flush=True,
        )
        sys.stdin.buffer.read()


if __name__ == "__main__":
    _main()
