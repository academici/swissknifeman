"""Compose and manage the backend-independent loopback LLM router."""

from __future__ import annotations

import json
import math
import os
import select
import signal
import socket
import ssl
import stat
import subprocess
import sys
import tomllib
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

from skm.adapters.http_client.router_upstream import RouterUpstream, UpstreamError, UpstreamResponse
from skm.adapters.runtimes import LocalProxyBridge
from skm.adapters.runtimes.router.cli_bridge import (
    CliBridge,
    CliRequest,
    CliUnavailable,
    ConversationBusy,
    InternalHop,
    tool_grants,
    worker_home,
)
from skm.adapters.runtimes.router.dedup import DedupKey, Inflight, dedup_key
from skm.adapters.runtimes.router.scheduler import Route, Scheduler, failover_policy, valid_success
from skm.adapters.runtimes.router.translator import (
    CHAT,
    COUNT,
    MESSAGES,
    RESPONSES,
    cli_prompt,
    cli_result,
    json_schema,
    translate_request,
    translate_response,
    upstream_path,
)
from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.adapters.secrets.keyring import KeyringSecretResolver
from skm.bootstrap.provider_accounts import ProviderAccounts, load_provider_accounts
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, SkmError, ValidationFailed
from skm.modules.runtimes.domain.catalog import parse_pricing
from skm.modules.runtimes.public import Pricing, SecretStr
from skm.platform.config.secrets import SecretResolvers
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping
    from typing import IO

__all__ = [
    "CHAT",
    "COUNT",
    "DEFAULT_PORT",
    "LOOPBACK",
    "MESSAGES",
    "RESPONSES",
    "CliRequest",
    "CliUnavailable",
    "ConversationBusy",
    "DedupKey",
    "Inflight",
    "Route",
    "RouterGeneration",
    "RouterState",
    "UpstreamError",
    "UpstreamResponse",
    "cli_prompt",
    "cli_result",
    "control_router",
    "dedup_key",
    "json_schema",
    "router_status",
    "serve_router",
    "start_router",
    "translate_request",
    "translate_response",
    "valid_success",
    "validate_bind",
]

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 8317
_MAX_CONFIG_BYTES = 1024 * 1024
_CONFIG_KEYS = {
    "bind",
    "port",
    "client_keys",
    "management_key",
    "hold_max_s",
    "floor_model",
    "failover",
    "floor_pricing",
    "allow_hot_pool_tools",
    "allowed_cwds",
    "ca_file",
    "cli_via_router",
}


def validate_bind(host: str, port: int) -> None:
    if host != LOOPBACK or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("router requires literal 127.0.0.1 and a port from 1 to 65535")


def _table(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected router config table")
    return cast("dict[str, Any]", value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError("expected nonempty string")
    return value


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("expected boolean")
    return value


def _secret(value: object, resolvers: SecretResolvers) -> SecretStr:
    text = _text(value)
    if text.startswith("secret://"):
        text = resolvers.resolve(text).reveal()
    if not text.isascii() or not text or any(not 33 <= ord(char) <= 126 for char in text):
        raise ValueError("invalid HTTP credential")
    return SecretStr(text)


def _regular(path: Path) -> IO[bytes]:
    return os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC), "rb")


def _registry(path: Path, env: Mapping[str, str], home: Path) -> tuple[dict[str, Any], ProviderAccounts]:
    with _regular(path) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_CONFIG_BYTES:
            raise ValueError("invalid provider pool file")
        raw = stream.read(_MAX_CONFIG_BYTES + 1)
    if len(raw) > _MAX_CONFIG_BYTES:
        raise ValueError("provider pool exceeds the config limit")
    config = _table(tomllib.loads(raw.decode()).get("router"))
    if (before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600) and any(
        not _text(value).startswith("secret://")
        for value in (*_table(config.get("client_keys")).values(), config.get("management_key"))
    ):
        raise ValueError("router configuration with literal keys requires owner-only mode 0600")
    accounts = load_provider_accounts(path, env, home)
    after = path.lstat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        or accounts.schema_version != 2
        or not accounts.slots
        or set(config) - _CONFIG_KEYS
    ):
        raise ValueError("expected a stable version 2 pool with router config and slots")
    return config, accounts


@dataclass(slots=True)
class RouterGeneration:
    """One fully validated router configuration and all its owned resources."""

    number: int
    port: int
    client_keys: Mapping[str, SecretStr]
    management_key: SecretStr
    scheduler: Scheduler
    cli: CliBridge | None
    routes: tuple[Route, ...]
    remotes: Mapping[str, RouterUpstream] = field(repr=False)
    floor_model: str | None
    floor_pricing: Pricing | None
    resources: ExitStack = field(repr=False)
    users: int = 0
    retired: bool = False

    def path_for(self, route: Route, path: str) -> str | None:
        if route.slot.transport == "cli_subprocess":
            return path if path != COUNT else None
        return upstream_path(self.remotes[route.slot.slot_id].protocol, path)

    def upstream(self, route: Route) -> RouterUpstream:
        return self.remotes[route.slot.slot_id].prepare()

    def permits_floor(self, route: Route, body_length: int, body: Mapping[str, object]) -> bool:
        if route.slot.transport == "cli_subprocess":
            return False
        limit = body.get("max_output_tokens", body.get("max_completion_tokens", body.get("max_tokens")))
        if type(limit) is not int or limit < 1:
            return False
        return self.scheduler.permits_floor(route, self.floor_pricing, body_length, limit)


def _remotes(
    accounts: ProviderAccounts,
    resolvers: SecretResolvers,
    verify: ssl.SSLContext | bool,
    resources: ExitStack,
) -> dict[str, RouterUpstream]:
    remotes: dict[str, RouterUpstream] = {}
    for slot in accounts.slots:
        private = accounts.config_for(slot.slot_id)
        if slot.transport == "cli_subprocess":
            if slot.runtime_id != "claude_code":
                raise ValueError("router CLI slots require the Claude Code stream-json protocol")
            continue
        base, provider = _text(private.base_url), _text(private.provider)
        parts = urlsplit(base)
        if parts.hostname is None or parts.query:
            raise ValueError("HTTP slots require models and an upstream base URL without query")
        protocol = {
            "anthropic": "anthropic",
            "openai": "openai",
            "openrouter": "openrouter",
            "openai-responses": "responses",
            "responses": "responses",
        }.get(provider.casefold(), "chat")
        if private.provider_routing and provider.casefold() != "openrouter":
            raise ValueError("provider_routing requires an OpenRouter slot")
        bridge_url = None
        if private.proxy is not None:
            proxy = LocalProxyBridge(private.proxy, allowed_hosts=frozenset({parts.hostname}))
            bridge_url = resources.enter_context(proxy).url
        key = _secret(str(private.api_key_ref), resolvers).reveal() if private.api_key_ref else None
        remotes[slot.slot_id] = RouterUpstream(
            base,
            credential=key,
            protocol=protocol,
            bridge_url=bridge_url,
            token_file=private.token_file,
            provider_routing=private.provider_routing,
            verify=verify,
        )
    return remotes


class RouterState:
    """Publish validated generations and retire resources after their final request."""

    def __init__(
        self, path: Path, state_dir: Path, env: Mapping[str, str], home: Path, *, port: int | None = None
    ) -> None:
        self.path, self.state_dir, self.env, self.home, self.port = path, state_dir, dict(env), home, port
        self.hop = InternalHop()
        self._lock, self._reload_lock = Lock(), Lock()
        self._current = self._build(1)

    def _build(self, number: int) -> RouterGeneration:
        try:
            return self._build_config(number)
        except (ValueError, TypeError, KeyError, OSError, RecursionError, SkmError):
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "invalid router configuration") from None

    def _build_config(self, number: int) -> RouterGeneration:
        config, accounts = _registry(self.path, self.env, self.home)
        configured_port = config.get("port", DEFAULT_PORT)
        validate_bind(_text(config.get("bind", LOOPBACK)), configured_port)
        port = configured_port if self.port is None else self.port
        validate_bind(LOOPBACK, port)
        resolvers = SecretResolvers(
            (EnvSecretResolver(self.env), FileSecretResolver(), KeyringSecretResolver()),
            on_reveal=lambda _: None,
        )
        clients = {key: _secret(value, resolvers) for key, value in _table(config.get("client_keys")).items()}
        management = _secret(config.get("management_key"), resolvers)
        if (
            not clients
            or any(not key.strip() for key in clients)
            or len(set(clients.values()) | {management}) != len(clients) + 1
        ):
            raise ValueError("router keys must be distinct and client names nonempty")
        hold = config.get("hold_max_s", 0)
        if type(hold) not in (int, float) or not math.isfinite(hold) or not 0 <= hold <= 60:
            raise ValueError("invalid hold_max_s")
        policy = failover_policy(_table(config.get("failover", {})))
        floor = _text(config["floor_model"]) if "floor_model" in config else None
        pricing = parse_pricing(_table(config["floor_pricing"])) if "floor_pricing" in config else None
        routes = tuple(
            Route(slot, model, accounts.config_for(slot.slot_id).worker_mode == "hot_pool")
            for slot in accounts.slots
            for model in slot.models
        )
        if any(not slot.models for slot in accounts.slots) or (
            floor is not None and (pricing is None or not any(route.model.name == floor for route in routes))
        ):
            raise ValueError("router slots require models and floor_model requires registered pricing")
        grants = tool_grants(
            _table(config.get("allowed_cwds", {})),
            clients.keys(),
            enabled=_bool(config.get("allow_hot_pool_tools", False)),
        )
        ca = config.get("ca_file")
        verify = ssl.create_default_context(cafile=_text(ca)) if ca is not None else True
        via_router = _bool(config.get("cli_via_router", True))
        with ExitStack() as resources:
            remotes = _remotes(accounts, resolvers, verify, resources)
            cli = None
            if any(route.slot.transport == "cli_subprocess" for route in routes):
                cli = CliBridge(
                    _private_dir(self.state_dir / "workers"),
                    worker_home(
                        self.env,
                        accounts.host_home,
                        {
                            slot.slot_id: (accounts.config_for(slot.slot_id), accounts.pool_root)
                            for slot in accounts.slots
                            if slot.transport == "cli_subprocess"
                        },
                        {
                            slot.slot_id: resources.enter_context(LocalProxyBridge(private.proxy))
                            for slot in accounts.slots
                            if not via_router
                            and slot.transport == "cli_subprocess"
                            and (private := accounts.config_for(slot.slot_id)).proxy is not None
                        },
                        direct=not via_router,
                    ),
                    self.hop,
                    generation=number,
                    base_url=f"http://{LOOPBACK}:{port}" if via_router else None,
                    allowed_cwds=grants,
                )
                resources.callback(cli.close)
            return RouterGeneration(
                number,
                port,
                clients,
                management,
                Scheduler(policy, hold),
                cli,
                routes,
                remotes,
                floor,
                pricing,
                resources.pop_all(),
            )

    @property
    def binding(self) -> tuple[str, int]:
        with self._lock:
            return LOOPBACK, self._current.port

    @contextmanager
    def lease(self, generation: RouterGeneration | None = None) -> Generator[RouterGeneration]:
        with self._lock:
            current = generation or self._current
            current.users += 1
        try:
            yield current
        finally:
            with self._lock:
                current.users -= 1
                dispose = current.retired and current.users == 0
            if dispose:
                current.resources.close()

    def reload(self) -> int:
        with self._reload_lock:
            with self._lock:
                old = self._current
            replacement = self._build(old.number + 1)
            if replacement.port != old.port:
                replacement.resources.close()
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "router reload cannot change the listener")
            with self._lock:
                self._current = replacement
                old.retired = True
                dispose = old.users == 0
            if dispose:
                old.resources.close()
            return replacement.number

    def close(self) -> None:
        with self._reload_lock, self._lock:
            current = self._current
            current.retired = True
            dispose = current.users == 0
        if dispose:
            current.resources.close()


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("router state directory must be private and owned by the current user")
    return path


def _state_dir(env: Mapping[str, str], home: Path) -> Path:
    return Path(env.get("XDG_STATE_HOME") or home / ".local/state") / "skm/router"


@dataclass(slots=True)
class _Daemon:
    identity: ProcessIdentity
    port: int
    reloads: int = 0
    reload_ok: bool = True


def _record(path: Path) -> _Daemon | None:
    try:
        with _regular(path) as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                return None
            values = json.loads(stream.read(2048))
        current = ProcessIdentity(**values.pop("identity"))
        if type(current.start_ticks) is int and isinstance(current.boot_id, str) and is_same_process(current):
            return _Daemon(current, **values)
    except (OSError, ValueError, AttributeError, TypeError, KeyError, RecursionError):
        return None
    return None


def _write_record(path: Path, record: _Daemon) -> None:
    atomic_write(path, json.dumps(asdict(record)).encode(), mode=0o600)


def serve_router(
    config: Path | None,
    port: int | None,
    serve: Callable[[RouterState, socket.socket, Callable[[], None]], None],
) -> None:
    env, home = dict(os.environ), Path.home()
    directory = _private_dir(_state_dir(env, home))
    registry = config or Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "skm/provider-pool.toml"
    pid_file = directory / "router.pid"
    with FileLock(directory / "listener.lock").hold(timeout_seconds=0), ExitStack() as resources:
        state = RouterState(registry, directory, env, home, port=port)
        resources.callback(state.close)
        listener = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(state.binding)
        listener.listen(128)
        identity = identity_of(os.getpid())
        if identity is None or identity.start_ticks is None or identity.boot_id is None:
            raise OSError("router requires a verifiable process identity")
        record = _Daemon(identity, state.binding[1])
        wake, stopping = Event(), Event()

        def request_reload(_sig: int, _frame: object) -> None:
            wake.set()

        previous = signal.signal(signal.SIGHUP, request_reload)
        resources.callback(signal.signal, signal.SIGHUP, previous)

        def reload_loop() -> None:
            while wake.wait():
                wake.clear()
                if stopping.is_set():
                    return
                try:
                    state.reload()
                except ValidationFailed:
                    record.reload_ok = False
                else:
                    record.reload_ok = True
                record.reloads += 1
                _write_record(pid_file, record)

        watcher = Thread(target=reload_loop, name="skm-router-reload", daemon=True)
        watcher.start()

        def end_watcher() -> None:
            stopping.set()
            wake.set()
            watcher.join()

        resources.callback(pid_file.unlink, missing_ok=True)
        resources.callback(end_watcher)
        serve(state, listener, lambda: _write_record(pid_file, record))


def router_status(env: Mapping[str, str], home: Path) -> dict[str, Any]:
    record = _record(_state_dir(env, home) / "router.pid")
    if record is None:
        return {"status": "stopped"}
    return {"status": "running", "host": LOOPBACK, "port": record.port, "pid": record.identity.pid}


def _signal_daemon(record: _Daemon, sig: int) -> int:
    # A pidfd pins the process across verification and signal delivery, even if the PID is recycled.
    pidfd = os.pidfd_open(record.identity.pid)
    try:
        if not is_same_process(record.identity):
            raise ProcessLookupError("router process identity changed")
        signal.pidfd_send_signal(pidfd, sig)
    except BaseException:
        os.close(pidfd)
        raise
    return pidfd


def start_router(
    env: Mapping[str, str],
    home: Path,
    *,
    config: Path | None,
    port: int | None,
    daemon: bool,
) -> dict[str, Any]:
    argv = [sys.executable, "-m", "skm.entrypoints.api.router.app"]
    if config is not None:
        argv.extend(("--config", str(config.absolute())))
    if port is not None:
        argv.extend(("--port", str(port)))
    directory = _private_dir(_state_dir(env, home))
    argv_env = {**env, "HOME": str(home)}
    try:
        if not daemon:
            with subprocess.Popen(argv, env=argv_env) as child:  # noqa: TID251 - foreground listener inherits terminal
                if child.wait() != 0:
                    raise OSError("router exited unsuccessfully")
            return {"status": "stopped"}
        # A detached daemon intentionally outlives the initiating CLI. The private identity record
        # allows later CLI processes to signal its dedicated pidfd without retaining its numeric PID.
        with FileLock(directory / "control.lock").hold(timeout_seconds=12):
            if _record(directory / "router.pid") is not None:
                raise OSError("router already running")
            child = subprocess.Popen(  # noqa: TID251 - detached service, outside a task-runner lifetime
                argv,
                env=argv_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = monotonic() + 10
            while child.poll() is None and monotonic() < deadline:
                record = _record(directory / "router.pid")
                if record is not None and record.identity.pid == child.pid:
                    return router_status(env, home)
                sleep(0.03)
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=3)
            raise OSError("router failed to start")
    except (OSError, LockTimeout, subprocess.SubprocessError):
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "router failed to start") from None


def control_router(env: Mapping[str, str], home: Path, *, reload: bool) -> dict[str, Any]:
    directory = _private_dir(_state_dir(env, home))
    pid_file = directory / "router.pid"
    try:
        with FileLock(directory / "control.lock").hold(timeout_seconds=12):
            record = _record(pid_file)
            if record is None:
                if reload:
                    raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "router is not running")
                return {"status": "stopped"}
            pidfd = _signal_daemon(record, signal.SIGHUP if reload else signal.SIGTERM)
            try:
                if reload:
                    return _await_reload(pid_file, record)
                poll = select.poll()
                poll.register(pidfd, select.POLLIN)
                if not poll.poll(15_000):
                    raise OSError("router stop timed out")
                return {"status": "stopped"}
            finally:
                os.close(pidfd)
    except (OSError, LockTimeout):
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "router control failed") from None


def _await_reload(path: Path, previous: _Daemon) -> dict[str, Any]:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        current = _record(path)
        if current is None or current.identity != previous.identity:
            break
        if current.reloads > previous.reloads:
            if not current.reload_ok:
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "router reload rejected the configuration")
            return {"status": "reloaded"}
        sleep(0.03)
    raise OSError("router reload timed out")
