"""Run isolated single-turn or persistent Claude Code workers for the HTTP router."""

from __future__ import annotations

import hmac
import json
from collections import OrderedDict
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass, field, replace
from pathlib import Path
from secrets import token_bytes, token_urlsafe
from tempfile import NamedTemporaryFile, TemporaryDirectory
from threading import Event, Lock, Thread
from time import monotonic
from typing import TYPE_CHECKING, Any, cast

from skm.adapters.runtimes import apply_proxy_env
from skm.adapters.runtimes.pool.shallow_home import ShallowHome, read_wallet_credentials, validate_directory
from skm.kernel.errors import SkmError
from skm.platform.fs.atomic_write import assert_safe_replace_target
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.process.environment import build_env
from skm.platform.process.runner import spawn
from skm.platform.schema.user_schema import load_user_json_schema, validate_user_json

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Generator, Mapping
    from contextlib import AbstractContextManager

    from skm.adapters.runtimes import LocalProxyBridge
    from skm.adapters.runtimes.pool.provider_pool import SlotRuntimeConfig
    from skm.platform.process.runner import ProcessHandle

__all__ = [
    "CliBridge",
    "CliRequest",
    "CliResult",
    "CliUnavailable",
    "ConversationBusy",
    "InternalHop",
    "tool_grants",
    "worker_home",
]

type WorkerKey = tuple[str, str, str, int]
type WorkerHome = Callable[[str, Path, Path], AbstractContextManager[dict[str, str]]]

_MAX_STDOUT_LINE_BYTES = 16 * 1024 * 1024


def tool_grants(
    config: Mapping[str, object],
    clients: Collection[str],
    *,
    enabled: bool,
) -> dict[str, tuple[Path, ...]]:
    grants: dict[str, tuple[Path, ...]] = {}
    for client, dirs in config.items():
        if client not in clients or not isinstance(dirs, list):
            raise ValueError("invalid hot-pool cwd grants")
        paths: list[Path] = []
        for value in cast("list[object]", dirs):
            if not isinstance(value, str):
                raise ValueError("hot-pool cwd grants require paths")
            path = Path(value)
            if not path.is_absolute() or not path.is_dir():
                raise ValueError("hot-pool cwd grants require absolute existing directories")
            paths.append(path.resolve(strict=True))
        grants[client] = tuple(paths)
    return grants if enabled else {}


def worker_home(
    environ: Mapping[str, str],
    host_home: Path | None,
    slots: Mapping[str, tuple[SlotRuntimeConfig, Path | None]],
    bridges: Mapping[str, LocalProxyBridge],
    *,
    direct: bool,
) -> WorkerHome:
    """Prepare a distinct home for every worker and serialize direct credential writes."""
    for config, pool in slots.values():
        if config.shallow_home is not None:
            validate_directory(config.shallow_home)
            if config.wallet_path is not None:
                ShallowHome(config.shallow_home, config.wallet_path, host_home).validate()
        if pool is not None:
            validate_directory(pool)

    @contextmanager
    def provision(slot: str, root: Path, cwd: Path) -> Generator[dict[str, str]]:
        config, pool = slots[slot]
        with ExitStack() as cleanup:
            parent = config.shallow_home
            if parent is not None:
                parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                validate_directory(parent)
                owner = Path(cleanup.enter_context(TemporaryDirectory(prefix="router-", dir=parent)))
            else:
                owner = root
            wallet = config.wallet_path or (
                pool / "claude_code" / slot / "wallet" if pool else root / "wallet"
            )
            layout = ShallowHome(
                owner / "client", wallet, host_home, config.symlink_host_files, config.write_back
            )
            # A per-worker temporary cwd is already private. A client grant must never overlap the home.
            home = layout.prepare("claude_code", workdir=cwd if cwd != root else None)
            if direct:
                lock_path = wallet.resolve(strict=True) / ".credentials.lock"
                assert_safe_replace_target(lock_path)
                lock = FileLock(lock_path)
                with lock.hold(timeout_seconds=3):
                    original = layout.stage("claude_code")
                if config.write_back:
                    cleanup.callback(_persist_wallet, lock, layout, original)
            env = build_env(environ, home=home)
            env.update(CLAUDE_CONFIG_DIR=str(home), TMPDIR=str(home / "tmp"))
            for key, suffix in (
                ("XDG_CONFIG_HOME", ".config"),
                ("XDG_STATE_HOME", ".local/state"),
                ("XDG_DATA_HOME", ".local/share"),
                ("XDG_CACHE_HOME", ".cache"),
            ):
                env[key] = str(home / suffix)
            apply_proxy_env(env, bridges.get(slot))
            yield env

    return provision


def _persist_wallet(lock: FileLock, layout: ShallowHome, original: bytes | None) -> None:
    assert_safe_replace_target(lock.path)
    with lock.hold(timeout_seconds=30):
        # Another worker or accounts exec may have refreshed the wallet during this turn.
        if read_wallet_credentials(layout.wallet / ".credentials.json") == original:
            layout.persist("claude_code", original)


class ConversationBusy(Exception):
    """A conversation is busy or its worker settings cannot change during the session."""


class CliUnavailable(Exception):
    """The worker could not complete the turn."""


class InternalHop:
    """Ephemeral per-worker credentials paired with a process-local signed hop marker."""

    def __init__(self) -> None:
        self._secret = token_bytes(32)
        self._clients: dict[str, str] = {}
        self._lock = Lock()

    def _signature(self, token: str) -> str:
        return hmac.digest(self._secret, token.encode(), "sha256").hex()

    def issue(self, client: str, resources: ExitStack) -> dict[str, str]:
        token = "skm-hop-" + token_urlsafe(32)
        with self._lock:
            self._clients[token] = client
        resources.callback(self._revoke, token)
        return {
            "ANTHROPIC_API_KEY": token,
            "ANTHROPIC_CUSTOM_HEADERS": (
                f"X-SKM-Internal-Hop: 1\nX-SKM-Internal-Signature: {self._signature(token)}"
            ),
        }

    def _revoke(self, token: str) -> None:
        with self._lock:
            self._clients.pop(token, None)

    def authenticate(self, token: str, marker: str, signature: str) -> str | None:
        if marker != "1" or not token.startswith("skm-hop-") or not signature.isascii():
            return None
        if not hmac.compare_digest(self._signature(token), signature):
            return None
        with self._lock:
            return self._clients.get(token)


@dataclass(frozen=True, slots=True)
class CliRequest:
    client_id: str
    conversation_id: str | None
    slot_id: str
    model: str
    system: str
    prompt: str
    cwd: Path | None = None
    schema: dict[str, Any] | bool | None = None
    hot: bool = False
    initial_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class CliResult:
    text: str
    refusal: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


def _private_text(resources: ExitStack, root: Path, content: str) -> Path:
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as stream:
        path = Path(stream.name)
        resources.callback(path.unlink, missing_ok=True)
        stream.write(content)
    return path


class _Worker:
    def __init__(
        self,
        bridge: CliBridge,
        request: CliRequest,
        cwd: Path | None,
        cancel: Event,
    ) -> None:
        self.settings = (request.model, request.system, cwd)
        self.resources = ExitStack()
        self.answer: dict[str, Any] | None = None
        self._stdout_line: bytearray | None = bytearray()
        self.ready = Event()
        self.writer: Thread | None = None
        try:
            root = Path(
                self.resources.enter_context(TemporaryDirectory(prefix="skm-router-", dir=bridge.root))
            )
            env = self.resources.enter_context(bridge.home(request.slot_id, root, cwd or root))
            argv = [
                bridge.executable,
                "-p",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
                "--model",
                request.model,
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--settings",
                '{"disableAllHooks":true}',
                "--setting-sources",
                "",
            ]
            if bridge.base_url is not None:
                argv.append("--bare")
                env.update(bridge.hop.issue(request.client_id, self.resources))
                env["ANTHROPIC_BASE_URL"] = bridge.base_url
                env["NO_PROXY"] = "127.0.0.1"
                env["no_proxy"] = "127.0.0.1"
            if not request.hot:
                argv.append("--no-session-persistence")
            if cwd is None:
                argv.extend(("--tools", "", "--permission-mode", "plan"))
            if request.system:
                system = _private_text(self.resources, root, request.system)
                argv.extend(("--system-prompt-file", str(system)))
            if cancel.is_set():
                raise CliUnavailable("worker turn was cancelled")
            self.process: ProcessHandle = spawn(
                argv,
                cwd=cwd or root,
                env=env,
                on_stdout=self._stdout,
                on_stderr=lambda _: None,
            )
            self.resources.callback(self._stop)
        except BaseException:
            self.resources.close()
            raise

    def _stdout(self, raw: bytes) -> None:
        # ProcessStreams can split a single line into 64 KiB fragments.
        complete = raw.endswith(b"\n")
        line = self._stdout_line
        if line is None or len(line) + len(raw) > _MAX_STDOUT_LINE_BYTES:
            self._stdout_line = bytearray() if complete else None
            return
        line.extend(raw)
        if not complete:
            return
        self._stdout_line = bytearray()
        try:
            message: object = json.loads(line)
        except (ValueError, RecursionError):
            return
        if not isinstance(message, dict):
            return
        result = cast("dict[str, Any]", message)
        if result.get("type") == "result" and not self.ready.is_set():
            self.answer = result
            self.ready.set()

    def turn(self, prompt: str, cancel: Event, deadline: float) -> CliResult:
        self.answer = None
        self.ready.clear()
        event = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}}
        wire = json.dumps(event).encode() + b"\n"
        write_failed = Event()

        def write() -> None:
            try:
                self.process.write_stdin(wire)
            except (OSError, ValueError, SkmError):
                write_failed.set()

        self.writer = Thread(target=write, name="skm-router-cli-input", daemon=True)
        self.writer.start()
        while not self.ready.wait(0.05):
            if (
                cancel.is_set()
                or write_failed.is_set()
                or monotonic() >= deadline
                or self.process.wait(0) is not None
            ):
                raise CliUnavailable("worker did not produce a result")
        if cancel.is_set():
            raise CliUnavailable("worker turn was cancelled")
        self.writer.join(timeout=0.5)
        if self.writer.is_alive():
            raise CliUnavailable("worker did not consume the turn")
        self.writer = None
        answer = cast("dict[str, Any] | None", self.answer)
        if (
            not answer
            or answer.get("is_error")
            or not isinstance(text := answer.get("result"), str)
            or not text
        ):
            raise CliUnavailable("worker returned an invalid result")
        usage = answer.get("usage", {})
        return CliResult(
            text, input_tokens=_tokens(usage, "input_tokens"), output_tokens=_tokens(usage, "output_tokens")
        )

    def _stop(self) -> None:
        try:
            self.process.terminate(grace_seconds=0.5)
        finally:
            if self.writer is not None:
                self.writer.join(timeout=1)

    def close(self) -> None:
        self.resources.close()


def _tokens(usage: object, key: str) -> int:
    count: object = cast("dict[str, object]", usage).get(key) if isinstance(usage, dict) else None
    return count if type(count) is int and count >= 0 else 0


@dataclass(slots=True)
class _Turn:
    worker: _Worker | None = None
    busy: bool = True
    used: float = field(default_factory=monotonic)


class CliBridge:
    """Own workers by client, conversation, slot and validated configuration generation."""

    def __init__(  # noqa: PLR0913 - independent host bindings
        self,
        root: Path,
        home: WorkerHome,
        hop: InternalHop,
        *,
        base_url: str | None,
        generation: int,
        allowed_cwds: Mapping[str, tuple[Path, ...]],
        executable: str = "claude",
        capacity: int = 16,
        ttl: float = 300,
    ) -> None:
        self.root, self.home, self.hop = root, home, hop
        self.base_url, self.executable = base_url, executable
        self._generation, self._grants, self._capacity, self._ttl = (
            generation,
            dict(allowed_cwds),
            capacity,
            ttl,
        )
        self._workers: OrderedDict[WorkerKey, _Turn] = OrderedDict()
        self._lock = Lock()
        self._closed = Event()
        self._sweeper = Thread(target=self._sweep, name="skm-router-cli", daemon=True)
        self._sweeper.start()

    def _cwd(self, request: CliRequest) -> Path | None:
        if request.cwd is None:
            return None
        cwd = request.cwd.resolve()
        if (
            not request.hot
            or not request.cwd.is_absolute()
            or not cwd.is_dir()
            or not any(cwd.is_relative_to(root) for root in self._grants.get(request.client_id, ()))
        ):
            raise ValueError("cwd is outside this client's hot-pool grant")
        return cwd

    def _reserve(self, key: WorkerKey) -> tuple[_Turn, _Worker | None]:
        with self._lock:
            if (turn := self._workers.get(key)) is not None:
                if turn.busy:
                    raise ConversationBusy("conversation already has a turn in progress")
                turn.busy = True
                self._workers.move_to_end(key)
                return turn, None
            evicted = None
            if len(self._workers) >= self._capacity:
                idle = next((candidate for candidate, entry in self._workers.items() if not entry.busy), None)
                if idle is None:
                    raise CliUnavailable("all hot-pool workers are busy")
                evicted = self._workers.pop(idle).worker
            self._workers[key] = turn = _Turn()
            return turn, evicted

    def _sweep(self) -> None:
        while not self._closed.wait(min(self._ttl, 5)):
            with self._lock:
                cutoff = monotonic() - self._ttl
                expired = [
                    key for key, turn in self._workers.items() if not turn.busy and turn.used <= cutoff
                ]
                workers = [self._workers.pop(key).worker for key in expired]
            for worker in workers:
                if worker is not None:
                    with suppress(OSError, ValueError, SkmError, LockTimeout):
                        worker.close()

    def run(self, request: CliRequest, cancel: Event) -> CliResult:
        cwd = self._cwd(request)
        if request.hot and not request.conversation_id:
            raise ValueError("hot-pool requests require a conversation ID")
        key = (
            (request.client_id, request.conversation_id or "", request.slot_id, self._generation)
            if request.hot
            else None
        )
        turn, evicted = self._reserve(key) if key is not None else (_Turn(), None)
        reusable = False
        try:
            if evicted is not None:
                evicted.close()
            if turn.worker is None:
                turn.worker = _Worker(self, request, cwd, cancel)
                if request.initial_prompt is not None:
                    request = replace(request, prompt=request.initial_prompt)
            elif turn.worker.settings != (request.model, request.system, cwd):
                reusable = True
                raise ConversationBusy("worker model, system prompt and cwd are fixed for a conversation")
            result = self._complete(turn.worker, request, cancel)
        except LockTimeout:
            raise CliUnavailable("worker wallet is busy") from None
        else:
            reusable = not cancel.is_set()
            return result
        finally:
            if key is not None:
                with self._lock:
                    if reusable:
                        turn.used = monotonic()
                        turn.busy = False
                    else:
                        del self._workers[key]
            if turn.worker is not None and (key is None or not reusable):
                try:
                    turn.worker.close()
                except LockTimeout:
                    raise CliUnavailable("timed out saving worker credentials") from None

    def _complete(self, worker: _Worker, request: CliRequest, cancel: Event) -> CliResult:
        deadline = monotonic() + 120
        if request.schema is None:
            return worker.turn(request.prompt, cancel, deadline)
        with ExitStack() as resources:
            encoded = json.dumps(request.schema, ensure_ascii=False, allow_nan=False)
            schema = _private_text(resources, self.root, encoded)
            load_user_json_schema(schema)
            prompt = f"{request.prompt}\nReturn only JSON matching this schema:\n{encoded}"
            for _ in range(4):  # Initial attempt plus at most three retries.
                result = worker.turn(prompt, cancel, deadline)
                try:
                    data: object = json.loads(result.text)
                    json.dumps(data, allow_nan=False)
                except (ValueError, RecursionError):
                    data = None
                    parsed = False
                else:
                    parsed = True
                if parsed and validate_user_json(data, schema)[0]:
                    return result
                prompt = (
                    f"{request.prompt}\nThe output failed validation. Return only JSON matching:\n{encoded}"
                )
        return CliResult("The worker could not produce valid structured output.", refusal=True)

    def close(self) -> None:
        self._closed.set()
        self._sweeper.join()
        with self._lock:
            workers = [turn.worker for turn in self._workers.values()]
            self._workers.clear()
        for worker in workers:
            if worker is not None:
                worker.close()
