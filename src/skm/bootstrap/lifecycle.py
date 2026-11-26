"""Composition and host operations for the local CLI lifecycle."""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable, Generator, Mapping
from contextlib import closing, suppress
from dataclasses import asdict, dataclass, replace
from http.client import HTTPConnection, HTTPException
from ipaddress import ip_address
from pathlib import Path
from select import poll
from threading import Thread
from typing import Literal, cast, override
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from skm.adapters.postgres.connection import PgSettings, connect_single, dsn_password
from skm.adapters.postgres.events import EventListener
from skm.application_bus.client import BlobUploader
from skm.bootstrap.composition import App
from skm.bootstrap.composition_resources import database_dsn
from skm.bootstrap.instance_secrets import instance_details
from skm.bootstrap.platform_module import MigrationState, local_migration_runner
from skm.bootstrap.services import BACKGROUND_SERVICES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, SkmError, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.artifacts.application.upload import bind_embedded_upload
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.keys import Chain
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.generated.results import DoctorResult
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process
from skm.platform.system_clock import SystemClock

__all__ = [
    "DEFAULT_BIND",
    "ComponentStatus",
    "LocalProcesses",
    "Role",
    "add_background_services",
    "api_settings",
    "embedded_dsn",
    "event_listener_for_api",
    "follow_log",
    "follow_process_log",
    "local_migrate",
    "parse_bind",
    "ready",
    "runtime_settings",
    "tail",
    "upload_for_api",
]

DEFAULT_BIND = "127.0.0.1:8765"
_LOCAL_LOG_BYTES = 1 << 20
type Role = Literal["serve", "worker"]


def parse_bind(bind: str) -> tuple[str, int]:
    host, sep, port = bind.rpartition(":")
    bracketed = host.startswith("[") and host.endswith("]")
    if bracketed:
        host = host[1:-1]
    if (
        not sep
        or not re.fullmatch(r"[a-zA-Z0-9._:%-]+", host)
        or (":" in host and not bracketed)
        or not re.fullmatch(r"[0-9]{1,5}", port)
        or not 1 <= int(port) <= 65535
    ):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Bind must be HOST:PORT (IPv6 in brackets)")
    return host, int(port)


def api_settings(app: App) -> Mapping[str, JsonValue]:
    process = app.config.process
    return {} if process is None else {**process.work, **process.host}


def runtime_settings(app: App) -> dict[str, JsonValue]:
    meta = RequestMeta("local-runtime-settings", Surface.CLI, None, SystemClock().now())
    with app.uow_factory(meta, readonly=True) as uow:
        store, scopes = uow.repo(ConfigStore), uow.repo(ScopeTree)
        work = app.config.effective(store, scopes, None)
        process = app.config.process
        host = app.config.effective(
            store, scopes, None if process is None else process.host_target, Chain.HOST
        )
        return {
            spec.key: (host if spec.chain is Chain.HOST else work).get(spec.key)
            for spec in app.settings.keys()  # noqa: SIM118 -- SettingsRegistry is not a mapping
        }


def embedded_dsn(
    config: BootstrapConfig, environ: Mapping[str, str], on_secret: Callable[[str], None]
) -> str:
    if config.access_mode != "embedded":
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "An embedded bootstrap profile is required")
    dsn = database_dsn(config, environ)
    on_secret(dsn)
    if password := dsn_password(dsn):
        on_secret(password)
    return dsn


def local_migrate(
    config: BootstrapConfig,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
    *,
    startup: bool = False,
) -> tuple[tuple[int, ...], int]:
    migrator = (
        config
        if config.database_migrator_url is None
        else replace(config, database_url=config.database_migrator_url)
    )
    dsn = embedded_dsn(migrator, environ, on_secret)
    if startup:
        with connect_single(PgSettings(dsn, "skm-startup-migration-check")) as conn:
            host, address = conn.info.host, conn.info.hostaddr
            if not (ip_address(address).is_loopback if address else host.startswith("/")):
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Startup migration requires a local PostgreSQL connection"
                )
    runner = local_migration_runner(dsn)
    applied = runner.migrate()
    current = max(
        (version for _, version, state in runner.status() if state is not MigrationState.PENDING), default=0
    )
    return applied, current


def add_background_services(app: App) -> App:
    bus = app.bus
    registry = bus._registry  # pyright: ignore[reportPrivateUsage] -- composition-owned wiring
    clock = bus._clock  # pyright: ignore[reportPrivateUsage]
    ids = bus._ids  # pyright: ignore[reportPrivateUsage]
    return replace(
        app,
        services=tuple(
            spec.factory(bus, registry=registry, clock=clock, ids=ids)
            for spec in BACKGROUND_SERVICES
            if spec.module not in registry.disabled_modules()
        ),
    )


def event_listener_for_api(app: App) -> EventListener | None:
    """Build a PostgreSQL LISTEN/NOTIFY listener when the composed App uses a PostgreSQL pool."""
    pool = getattr(app.uow_factory, "_pool", None)
    settings = getattr(pool, "settings", None)
    if not isinstance(settings, PgSettings):
        return None
    return EventListener(
        PgSettings(
            settings.dsn,
            f"{settings.application_name}-events",
            pool_timeout_seconds=settings.pool_timeout_seconds,
        )
    )


def upload_for_api(app: App) -> BlobUploader:
    bus = app.bus
    upload, _ = bind_embedded_upload(
        app.uow_factory,
        bus._authorizer,  # pyright: ignore[reportPrivateUsage]
        bus._scopes,  # pyright: ignore[reportPrivateUsage]
        app.config,
        app.gateways,
        bus._clock,  # pyright: ignore[reportPrivateUsage]
        bus._ids,  # pyright: ignore[reportPrivateUsage]
        bus.dispatch,
        bus.ask,
    )
    return upload


class _RejectRedirect(HTTPRedirectHandler):
    @override
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def ready(url: str) -> bool:
    # Probe the local listener without redirects or environment-configured proxies.
    opener = build_opener(ProxyHandler({}), _RejectRedirect())
    request = Request(url + "/health/ready")
    try:
        with opener.open(request, timeout=0.5) as response:
            return response.status == 200
    except (URLError, OSError):
        return False


@dataclass(frozen=True, slots=True)
class _Process:
    identity: ProcessIdentity
    url: str | None
    grace: int


def _proc_address(endpoint: tuple[str, int]) -> str:
    # Linux /proc/net/tcp{,6} encodes each 32-bit address word in host byte order.
    packed = ip_address(endpoint[0]).packed
    words = (packed[i : i + 4] for i in range(0, len(packed), 4))
    return "".join(f"{int.from_bytes(word, sys.byteorder):08X}" for word in words) + f":{endpoint[1]:04X}"


def _owns_peer(identity: ProcessIdentity, sock: socket.socket) -> bool:
    proc = Path("/proc") / str(identity.pid)
    table = proc / "net" / ("tcp6" if sock.family == socket.AF_INET6 else "tcp")
    server, client = _proc_address(sock.getpeername()), _proc_address(sock.getsockname())
    for line in table.read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1:4] == [server, client, "01"] and fields[9] != "0":
            inode = f"socket:[{fields[9]}]"
            for fd in (proc / "fd").iterdir():
                with suppress(FileNotFoundError):
                    if os.readlink(fd) == inode:
                        return is_same_process(identity)
    return False


def _owned_ready(proc: _Process, secret: str, expected: str) -> bool:
    if proc.url is None:
        return False
    address = urlsplit(proc.url)
    try:
        with closing(HTTPConnection(str(address.hostname), address.port, timeout=1)) as conn:
            conn.request("GET", "/health/ready")
            with conn.getresponse() as response:
                if response.status != 200 or len(response.read(4097)) > 4096:
                    return False
            # Pin this TCP connection to the recorded process before sending the bearer credential.
            if conn.sock is None or not _owns_peer(proc.identity, conn.sock):
                return False
            conn.request("GET", "/health/details", headers={"Authorization": "Bearer " + secret})
            with conn.getresponse() as response:
                if response.status != 200:
                    return False
                doctor = DoctorResult.from_json(json.load(response))
                instance_details(doctor, expected=UUID(expected))
            return is_same_process(proc.identity)
    except (OSError, HTTPException, ValueError, KeyError, TypeError, SkmError):
        return False


def _run_local_service(state: Path, record: Path, metadata: dict[str, JsonValue], argv: list[str]) -> None:
    from skm.bootstrap.host_services import build_host_storage

    role = metadata["role"]
    logs = state / "logs"
    if logs.is_symlink():
        raise OSError("local log directory is a symlink")
    path = logs / f"{role}.log"
    with FileLock(record.with_suffix(".log.lock")).hold(timeout_seconds=20):
        budget = build_host_storage(state)
        child = None
        try:
            with budget.reserve(
                logs if logs.is_dir() else state,
                owner_id=f"local-{role}-log",
                max_bytes=_LOCAL_LOG_BYTES,
                min_free_bytes=0,
            ) as hold:
                logs.mkdir(mode=0o700, exist_ok=True)
                with suppress(FileNotFoundError):
                    path.replace(path.with_suffix(".previous.log"))
                log = hold.open_file(path)
                child = subprocess.Popen(  # noqa: TID251 -- the detached log owner drains the service pipe
                    argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                if child.stdout is None:
                    raise RuntimeError("local service has no output pipe")
                with child.stdout as output:
                    identity = identity_of(child.pid)
                    if identity is None or identity.start_ticks is None or identity.boot_id is None:
                        raise BackendUnavailable(
                            ErrorCode.BACKEND_UNAVAILABLE, "Could not identify local service"
                        )
                    atomic_write(record, json.dumps({**asdict(identity), **metadata}).encode(), mode=0o600)
                    sys.stdout.write("ready\n")
                    sys.stdout.flush()
                    remaining = _LOCAL_LOG_BYTES
                    while chunk := os.read(output.fileno(), 65536):
                        if remaining:
                            data = chunk[:remaining]
                            log.write(data)
                            remaining -= len(data)
        except BaseException:
            if child is not None:
                child.kill()
            raise
        finally:
            if child is not None:
                child.wait()


def _local_log_owner() -> None:  # pyright: ignore[reportUnusedFunction] -- subprocess entrypoint
    def terminate(_signal: int, _frame: object) -> None:
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, terminate)
    state, record, metadata, *argv = sys.argv[1:]
    try:
        _run_local_service(Path(state), Path(record), json.loads(metadata), argv)
    except (OSError, SkmError, LockTimeout) as error:
        reason = error.details.get("reason") if isinstance(error, SkmError) else None
        if reason in ("disk_low", "storage_ledger_corrupt", "storage_lock_timeout"):
            with suppress(BrokenPipeError):
                sys.stdout.write(f"{reason}\n")
                sys.stdout.flush()
        raise SystemExit(1) from None


class LocalProcesses:
    def __init__(self, config: BootstrapConfig) -> None:
        self.config = config
        self.pids = config.state_dir / "pids"
        self.logs = config.state_dir / "logs"
        self.instance_id = str(config.instance_id)

    def lock(self) -> FileLock:
        self.pids.mkdir(mode=0o700, parents=True, exist_ok=True)
        return FileLock(self.pids / "lifecycle.lock")

    def _record(self, role: Role) -> Path:
        return self.pids / f"{role}.pid"

    def lookup(self, role: Role) -> _Process | None:
        try:
            raw = cast("object", json.loads(self._record(role).read_text()))
            if not isinstance(raw, dict):
                return None
            record = cast("dict[str, JsonValue]", raw)
            pid, ticks, boot = record["pid"], record["start_ticks"], record["boot_id"]
            if (
                record["role"] != role
                or record["instance_id"] != self.instance_id
                or type(pid) is not int
                or pid < 1
                or type(ticks) is not int
                or ticks < 0
                or not isinstance(boot, str)
                or not boot
            ):
                return None
            url = record.get("url")
            if role == "serve" and (not isinstance(url, str) or not _loopback_url(url)):
                return None
            grace = record.get("grace", 15)
            if type(grace) is not int or not 0 <= grace <= 605:
                return None
        except (FileNotFoundError, KeyError, ValueError):
            return None
        identity = ProcessIdentity(pid, ticks, boot)
        return (
            _Process(identity, url if isinstance(url, str) else None, grace)
            if is_same_process(identity)
            else None
        )

    def start(
        self,
        role: Role,
        argv: list[str],
        environ: Mapping[str, str],
        *,
        url: str | None = None,
        grace: int = 15,
    ) -> _Process:
        if existing := self.lookup(role):
            return existing
        if role == "serve" and url:
            host, port = parse_bind(urlsplit(url).netloc)
            try:
                with socket.create_server(
                    (host, port), family=socket.AF_INET6 if ":" in host else socket.AF_INET
                ):
                    pass
            except OSError:
                raise BackendUnavailable(
                    ErrorCode.BACKEND_UNAVAILABLE, "Local serve address is occupied"
                ) from None
        if not hasattr(os, "pidfd_open"):
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Local supervision requires Linux pidfds")
        self.pids.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = json.dumps({"role": role, "instance_id": self.instance_id, "url": url, "grace": grace})
        owner = subprocess.Popen(  # noqa: TID251 -- owned startup handshake with the detached log writer
            [
                sys.executable,
                "-c",
                "from skm.bootstrap.lifecycle import _local_log_owner; _local_log_owner()",
                str(self.config.state_dir),
                str(self._record(role)),
                metadata,
                *argv,
            ],
            env=environ,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            if owner.stdout is None:
                raise RuntimeError("local log owner has no startup pipe")
            with owner.stdout as startup:
                watcher = poll()
                watcher.register(startup)
                status = startup.readline(100).strip().decode() if watcher.poll(30000) else ""
            process = self.lookup(role) if status == "ready" else None
            if process is None:
                details = (
                    {"reason": status}
                    if status in ("disk_low", "storage_ledger_corrupt", "storage_lock_timeout")
                    else {}
                )
                raise BackendUnavailable(
                    ErrorCode.BACKEND_UNAVAILABLE, f"Could not start local {role}", details=details
                )
        except BaseException:
            owner.terminate()
            owner.wait()
            raise
        Thread(target=owner.wait, daemon=True).start()
        return process

    def wait_ready(self, proc: _Process, secret: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while self.lookup("serve") == proc:
            if _owned_ready(proc, secret, self.instance_id):
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            "Local serve did not become ready",
            details={"hint": "skm local logs serve"},
        )

    def wait_worker(self, timeout: float, healthy: Callable[[], bool]) -> None:
        deadline = time.monotonic() + timeout
        while (proc := self.lookup("worker")) is not None:
            if healthy() and self.lookup("worker") == proc:
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            "Local worker did not start",
            details={"hint": "skm local logs worker"},
        )

    def stop(self, role: Role, *, grace: float | None = None) -> None:
        if (proc := self.lookup(role)) is not None:
            _stop_identity(proc.identity, proc.grace if grace is None else grace)
        self._record(role).unlink(missing_ok=True)


def _loopback_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        port is not None
        and parsed.scheme == "http"
        and parsed.netloc in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        and not (parsed.path or parsed.query or parsed.fragment)
    )


def _stop_identity(identity: ProcessIdentity, grace: float) -> None:
    # Acquire the kernel handle first, then verify the recorded identity before every signal.
    try:
        fd = os.pidfd_open(identity.pid)
    except ProcessLookupError:
        return
    except (AttributeError, OSError) as error:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "Could not pin the local process identity"
        ) from error
    try:
        watcher = poll()
        watcher.register(fd)
        for sig, timeout in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
            if not is_same_process(identity):
                return
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(fd, sig)
            if watcher.poll(round(timeout * 1000)):
                return
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "Local process has not exited")
    finally:
        os.close(fd)


def tail(path: Path, lines: int) -> Generator[str]:
    try:
        with os.fdopen(
            os.open(path, os.O_RDONLY | os.O_NOFOLLOW), encoding="utf-8", errors="replace"
        ) as stream:
            yield from deque(stream, maxlen=lines)
    except FileNotFoundError:
        return


def follow_log(path: Path, alive: Callable[[], bool], lines: int) -> Generator[str]:
    try:
        with os.fdopen(
            os.open(path, os.O_RDONLY | os.O_NOFOLLOW), encoding="utf-8", errors="replace"
        ) as stream:
            yield from deque(stream, maxlen=lines)
            while True:
                line = stream.readline()
                if line:
                    yield line
                elif alive():
                    time.sleep(0.2)
                else:
                    break
    except FileNotFoundError:
        return


def follow_process_log(argv: tuple[str, ...], cwd: Path, environ: Mapping[str, str]) -> Generator[str]:
    child = subprocess.Popen(  # noqa: TID251 -- incremental Compose output under this direct parent
        argv,
        cwd=cwd,
        env=environ,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        if child.stdout is not None:
            with child.stdout:
                yield from child.stdout
        if child.wait():
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "docker compose could not read PostgreSQL logs"
            )
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    component: str
    state: str
    detail: str
