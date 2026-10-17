"""The backend process without its HTTP layer (stdlib + aicore): state, single instance, sessions (decision D13).

``gui serve`` holds ``state_dir/backend.lock`` (``flock``) for its whole life, so a second backend on the same
``gui.db`` is refused with ``BACKEND_RUNNING``. After the socket is bound it writes ``backend.json`` (``0600``:
pid, port, epoch, session secret) for ``gui open``. :class:`Sessions` keeps the browser credentials in memory: the
256-bit session secret (``Authorization: Bearer``), one-time URL tokens (sha256 only, TTL 300 s, gone after first
use) and session cookies (sha256 only). Every comparison of a secret is ``hmac.compare_digest``.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import hmac
import json
import os
import platform
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from aicore.state.locations import ensure_dir, state_dir
from aicore.util.digest import digest_json
from aicore.util.redact import env_secrets

from . import __version__, contracts
from .catalog import resolve, sources
from .core.broker import Broker
from .core.config import ConfigService
from .core.events import EventHub
from .core.plugins import PluginHost, failing
from .core.projects import ProjectRegistry
from .core.runs import RunStore, frame_run, prune_logs
from .settings import Settings
from .storage import db

LOCK_NAME = "backend.lock"
RUNTIME_NAME = "backend.json"
LOG_NAME = "backend.log"
TOKEN_TTL_S = 300
COOKIE = "skm_gui_session"
GUI_PROTOCOL = {"min": resolve.HOST_PROTOCOL[0], "max": resolve.HOST_PROTOCOL[1]}
FRONTEND_DIR = contracts.SCHEMAS.parent / "frontend" / "dist"
FEATURES = ("queries", "projects", "runs", "events", "config", "plugins")


class BackendError(Exception):
    """A CLI-level failure of the backend host: ``BACKEND_RUNNING`` or ``BACKEND_START_FAILED``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def gui_state_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    folder = ensure_dir(state_dir("gui", env=env))
    os.chmod(folder, 0o700)
    return folder


class InstanceLock:
    """``flock(LOCK_EX | LOCK_NB)`` on ``backend.lock``; held until :meth:`release` or process exit."""

    def __init__(self, folder: Path) -> None:
        self.path = folder / LOCK_NAME
        self.fd: Optional[int] = None

    def acquire(self) -> "InstanceLock":
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise BackendError("BACKEND_RUNNING", "another gui backend runs on this machine; use `gui open`") \
                    from None
            raise
        self.fd = fd
        return self

    def release(self) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def write_runtime(folder: Path, info: Mapping[str, Any]) -> Path:
    """Write ``backend.json`` with mode ``0600`` through a temporary file and ``os.replace``."""
    target = folder / RUNTIME_NAME
    temporary = folder / f".{RUNTIME_NAME}.{os.getpid()}.tmp"
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(dict(info), handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target


def read_runtime(folder: Path) -> Optional[Dict[str, Any]]:
    try:
        info = json.loads((folder / RUNTIME_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = {"pid": int, "port": int, "epoch": str, "session_secret": str}
    if not isinstance(info, dict) or any(not isinstance(info.get(k), t) for k, t in required.items()):
        return None
    return info


def remove_runtime(folder: Path, epoch: str) -> None:
    """Remove ``backend.json`` when it still belongs to this process (``epoch``)."""
    info = read_runtime(folder)
    if info is not None and info.get("epoch") == epoch:
        try:
            (folder / RUNTIME_NAME).unlink()
        except OSError:
            pass


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


class Sessions:
    """Credentials of one backend process; values are never stored, only their sha256."""

    def __init__(self, secret: Optional[str] = None, *, clock=time.monotonic) -> None:
        self.secret = secret or secrets.token_urlsafe(32)
        self._clock = clock
        self._tokens: Dict[bytes, float] = {}
        self._cookies: set = set()
        self._lock = threading.Lock()

    def bearer_ok(self, presented: str) -> bool:
        return hmac.compare_digest(presented.encode("utf-8"), self.secret.encode("utf-8"))

    def new_token(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = self._clock()
            self._tokens = {key: expiry for key, expiry in self._tokens.items() if expiry > now}
            self._tokens[_digest(token)] = now + TOKEN_TTL_S
        return token

    def redeem(self, token: str) -> Optional[str]:
        """A new cookie value for a valid unused token (which is then gone), else ``None``."""
        presented = _digest(token)
        with self._lock:
            match = next((key for key in self._tokens if hmac.compare_digest(key, presented)), None)
            if match is None:
                return None
            expiry = self._tokens.pop(match)
            if expiry <= self._clock():
                return None
            cookie = secrets.token_urlsafe(32)
            self._cookies.add(_digest(cookie))
        return cookie

    def cookie_ok(self, value: str) -> bool:
        presented = _digest(value)
        with self._lock:
            return any(hmac.compare_digest(known, presented) for known in self._cookies)


@dataclass
class Catalog:
    document: Dict[str, Any]
    owners: Dict[str, resolve.Owner]
    queries: Dict[str, Tuple[str, Dict[str, Any]]]  # query id -> (owner, descriptor)
    commands: Dict[str, Tuple[str, Dict[str, Any]]]  # command id -> (owner, descriptor)
    sources: Dict[str, sources.Source] = field(default_factory=dict)  # owner -> declared source, rejected ones too


def build_catalog(collected: sources.Collected) -> Catalog:
    document, owners = resolve.resolve_indexed(collected)
    queries: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    commands: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    for owner, entry in owners.items():
        for query in entry.document.get("queries", ()):
            queries[query["id"]] = (owner, query)
        for command in entry.document.get("commands", ()):
            commands[command["id"]] = (owner, command)
    declared: Dict[str, sources.Source] = {}
    for source in sorted(collected.sources, key=sources.Source.sort_key):
        if source.owner:
            declared.setdefault(source.owner, source)
    return Catalog(document, owners, queries, commands, declared)


def _journal_read(root: str, offset: Optional[int]) -> Tuple[List[Dict[str, Any]], int]:
    """New events of a project journal after ``offset`` (``None``: start at the current end) and the next offset."""
    from aicore.ext import journal
    from aicore.ext.events import parse_line

    jdir = journal.journal_dir(root)
    if offset is None:
        return [], journal.size(jdir)
    found: List[Dict[str, Any]] = []
    following = offset
    for start, line, problem in journal.iter_lines(jdir, offset):
        if line is not None:
            following = start + len(line) + 1
            event, _problem = parse_line(start, line, problem)
            if event is not None:
                found.append(event.to_json())
        elif problem == "empty":
            following = start + 1
        else:  # a line too long to read: continue after the data seen now
            following = max(following, journal.size(jdir))
    return found, following


def platform_info() -> Dict[str, str]:
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return {"os": "darwin" if sys.platform == "darwin" else "linux" if sys.platform.startswith("linux") else
            sys.platform, "arch": arch}


def unit_contracts() -> List[Dict[str, str]]:
    unit = json.loads((contracts.SCHEMAS.parent / "unit.json").read_text(encoding="utf-8"))
    return [{"id": entry["id"], "version": entry["version"]} for entry in unit["provides"]["contracts"]]


@dataclass
class BackendState:
    """Everything a request needs; built once by ``gui serve`` (or by a test with its own pieces)."""

    settings: Settings
    conn: sqlite3.Connection
    env: Mapping[str, str]
    port: int = 0
    sessions: Sessions = field(default_factory=Sessions)
    epoch: str = field(default_factory=lambda: uuid.uuid4().hex)
    frontend_dir: Path = FRONTEND_DIR
    state_folder: Optional[Path] = None
    catalog: Optional[Catalog] = None
    collect: Any = None  # () -> sources.Collected; default: sources.collect(None, env)
    features: Tuple[str, ...] = FEATURES
    db_lock: threading.RLock = field(default_factory=threading.RLock)
    query_cache: Dict[Tuple[str, ...], Tuple[float, Any]] = field(default_factory=dict)
    loop: Any = None  # the event loop of the running backend (set by start)

    def __post_init__(self) -> None:
        self.registry = ProjectRegistry(self.conn)
        self.hub = EventHub(self.epoch, ring_frames=self.settings.events.ring_frames,
                            queue_frames=self.settings.events.queue_frames)
        self.store = RunStore(self.conn, lock=self.db_lock,
                              publish=lambda doc: self.hub.publish_run(doc, frame_run(doc)))
        self.broker = Broker(store=self.store, hub=self.hub, settings=lambda: self.settings, conn=self.conn,
                             db_lock=self.db_lock, env=self.env, runs_dir=self.runs_dir, secrets=self.secrets,
                             emit=self.emit)
        self.config = ConfigService(self.env, lambda: self.settings.config, audit=self._config_audit,
                                    emit_project=lambda type_, data, subject, root: self.emit(
                                        type_, data, subject=subject, project=root),
                                    emit_machine=self._config_publish)
        self.plugins = PluginHost(
            self.conn, self.db_lock, lambda: self.settings, self._config_publish, self._config_audit,
            lambda owner: [run_id for run_id, active in list(self.broker.active.items()) if active.owner == owner],
            lambda run_id: self.broker.cancel(run_id, system=True), self._conformance)
        self.tasks: List[Any] = []
        if self.catalog is None:
            self.refresh_catalog()
        else:
            self.plugins.sync(self.plugins.observe(self.catalog))

    @property
    def runs_dir(self) -> Path:
        base = self.state_folder if self.state_folder is not None else state_dir("gui", env=self.env)
        return Path(base) / "runs"

    def emit(self, type_: str, data: Mapping[str, Any], *, subject: str, project: str) -> None:
        """Journal a ``gui.*`` event in the project (blocking; the broker calls it in a worker thread)."""
        from aicore.ext.events import emit

        emit(type_, data, source="gui", subject=subject, project=project, env=dict(self.env))

    def _config_audit(self, action: str, target: str, decision: str, details: Mapping[str, Any]) -> None:
        with self.db_lock:
            db.audit(self.conn, actor="user", action=action, target=target, decision=decision, details=details)

    def _config_publish(self, type_: str, data: Mapping[str, Any], subject: str) -> None:
        """A machine-wide ``gui.config.changed`` frame (no project journal); safe to call from a worker thread."""
        from aicore.ext.events import build_event

        event = build_event(type_, data, source="gui", subject=subject).to_json()
        loop = self.loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self.hub.publish_event, event, None)
        else:
            self.hub.publish_event(event, None)

    def _conformance(self, observed: Any) -> List[Dict[str, str]]:
        """The failing checks of ``gui check`` for a plugin (the conformance gate of Enable); blocking."""
        return failing(resolve.check(Path(observed.root), env=dict(self.env), conformance=True))

    async def start(self) -> None:
        """Before the first request: runs of an earlier backend become ``lost``; heartbeats and journals start."""
        import asyncio

        self.loop = asyncio.get_running_loop()
        self.plugins.sync(self.plugins.observe(self.catalog))
        lost = self.store.mark_lost(grace_s=self.settings.runs.cancel_grace_s)
        for run_id in lost:
            run = self.store.get(run_id)
            project_id = run["context"].get("project_id")
            if project_id:
                try:
                    root = str(self.registry.resolve(project_id))
                    await asyncio.to_thread(self.emit, "gui.run.lost", {"run_id": run_id, "command": run["command"],
                                                                        "owner": run["owner"], "state": "lost"},
                                            subject=run_id, project=root)
                except Exception:  # noqa: BLE001 - journaling never blocks the start
                    pass
        prune_logs(self.runs_dir, max_age_days=self.settings.retention.log_days,
                   max_total_mb=self.settings.retention.log_total_mb)
        self.tasks = [asyncio.create_task(self._heartbeats()), asyncio.create_task(self._journals())]

    async def stop(self) -> None:
        import asyncio

        await self.broker.shutdown()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    async def _heartbeats(self) -> None:
        import asyncio

        while True:
            await asyncio.sleep(self.settings.events.heartbeat_s)
            self.hub.heartbeat()

    async def _journals(self) -> None:
        """Each registered project's event journal, read from its end at start, as ``event`` frames."""
        import asyncio

        offsets: Dict[str, int] = {}
        while True:
            with self.db_lock:
                projects = self.registry.list()
            for project in projects:
                try:
                    events, offsets[project.id] = await asyncio.to_thread(_journal_read, project.root,
                                                                          offsets.get(project.id))
                except Exception:  # noqa: BLE001 - a broken journal never stops the stream
                    continue
                for event in events:
                    self.hub.publish_event(event, project.id)
            await asyncio.sleep(self.settings.events.journal_poll_s)

    def refresh_catalog(self) -> Catalog:
        collected = self.collect() if self.collect is not None else sources.collect(None, dict(self.env))
        self.catalog = build_catalog(collected)
        self.query_cache.clear()
        self.plugins.sync(self.plugins.observe(self.catalog))
        return self.catalog

    def visible_catalog(self) -> Dict[str, Any]:
        """The ``catalog/v1`` document for the UI: contributions of plugins that are not ``ui_enabled`` are left out
        and the digest is computed again over the rest by the algorithm of the resolver."""
        document = self.catalog.document
        entries = [entry for entry in document["contributions"] if self.plugins.visible(entry["owner"])]
        if len(entries) == len(document["contributions"]):
            return document
        digest = digest_json({"host": document["host"], "contributions": [
            {"owner": entry["owner"], "source": entry["source"], "digest": entry["digest"]} for entry in entries]})
        return {**document, "contributions": entries, "digest": digest}

    @property
    def log_path(self) -> Optional[Path]:
        return None if self.state_folder is None else self.state_folder / LOG_NAME

    def secrets(self) -> List[str]:
        """Values that must never leave the backend: secret-named environment values and the session secret."""
        return [*env_secrets(self.env), self.sessions.secret]

    def bootstrap(self) -> Dict[str, Any]:
        units = []
        for owner in sorted(self.catalog.owners.values(), key=lambda entry: entry.source.owner) if self.catalog else ():
            if owner.version:
                units.append({"id": owner.source.owner, "version": owner.version})
        return {"$schema": "urn:swissknifeman:gui:bootstrap:v1", "mode": "browser", "epoch": self.epoch,
                "backend": {"version": __version__, "python": platform.python_version()},
                "gui_protocol": dict(GUI_PROTOCOL), "contracts": unit_contracts(), "units": units,
                "features": list(self.features), "platform": platform_info()}

    def url(self, token: str) -> str:
        return f"http://127.0.0.1:{self.port}/?t={token}"

    def runtime_info(self) -> Dict[str, Any]:
        return {"pid": os.getpid(), "port": self.port, "epoch": self.epoch, "session_secret": self.sessions.secret,
                "started_at": db.now(), "version": __version__}


# --- gui open: the client side (stdlib) ------------------------------------------------------------------------

START_TIMEOUT_S = 10.0
REQUEST_TIMEOUT_S = 5.0


def request(info: Mapping[str, Any], method: str, path: str, body: Optional[Mapping[str, Any]] = None,
            timeout: float = REQUEST_TIMEOUT_S) -> Tuple[int, Any]:
    """One bearer request to the backend of ``info``; proxies are never used. ``(status, JSON or None)``."""
    import urllib.error
    import urllib.request

    data = None if body is None else json.dumps(dict(body)).encode("utf-8")
    headers = {"Authorization": f"Bearer {info['session_secret']}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{int(info['port'])}{path}", data=data, method=method,
                                 headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        return status, json.loads(raw.decode("utf-8")) if raw else None
    except ValueError:
        return status, None


def alive(info: Optional[Mapping[str, Any]]) -> bool:
    """Whether ``backend.json`` names a running backend that accepts its secret (``GET /v1/bootstrap`` = 200)."""
    if info is None or not pid_alive(int(info["pid"])):
        return False
    try:
        status, _ = request(info, "GET", "/v1/bootstrap")
    except OSError:
        return False
    return status == 200


def project_marker_root(start: Path) -> Optional[Path]:
    """The project above ``start`` that has ``.swissknifeman/`` (what ``gui serve``/``open`` register by cwd)."""
    from aicore.state.locations import PROJECT_DIRNAME, resolve_project

    context = resolve_project(start, env={k: os.environ[k] for k in ("HOME",) if k in os.environ},
                              markers=(PROJECT_DIRNAME,), stop_at_home=True)
    return context.root if context else None


def tail(path: Path, lines: int = 10) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def start_detached(folder: Path, port: Optional[int] = None, *, timeout: float = START_TIMEOUT_S) -> Dict[str, Any]:
    """Start ``gui serve`` as a detached process (its output goes to ``backend.log``) and wait for it to answer."""
    import subprocess

    command = [sys.executable, "-m", "gui.cli", "serve", "--detached"]
    if port is not None:
        command += ["--port", str(port)]
    log_path = folder / LOG_NAME
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=fd, stderr=fd, cwd=str(folder),
                                 start_new_session=True, close_fds=True)
    finally:
        os.close(fd)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = read_runtime(folder)
        if info is not None and info.get("pid") == child.pid and alive(info):
            return info
        if child.poll() is not None:
            break
        time.sleep(0.1)
    if child.poll() is None:
        child.terminate()
    raise BackendError("BACKEND_START_FAILED", f"the backend did not start in {timeout:.0f} s; "
                                               f"{log_path}:\n{tail(log_path)}")
