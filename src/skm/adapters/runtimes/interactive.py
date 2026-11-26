"""Host-local interactive sessions with an independent PTY supervisor."""

from __future__ import annotations

import fcntl
import json
import os
import signal
import stat
import subprocess
import sys
from collections.abc import Mapping
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from select import poll, select
from shutil import rmtree
from threading import Thread
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, PreconditionFailed, ValidationFailed
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process

from . import _interactive_terminal as terminal
from ._cli_session.probe import resolve_binary_path

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import TextIO

    from skm.modules.runtimes.public import SecretStr

__all__ = ["NATIVE_ACCOUNT_FILES", "InteractiveLauncher", "InteractiveSession", "interactive_argv"]

_START_TIMEOUT = 10
_STOP_TIMEOUT_MS = 5000
_MAX_RECORD = 64 * 1024
_BINARIES = {
    "antigravity": "agy",
    "claude_code": "claude",
    "codex": "codex",
    "cursor": "cursor-agent",
    "gemini_cli": "gemini",
    "grok": "grok",
}
NATIVE_ACCOUNT_FILES = {
    "claude_code": Path(".claude/.credentials.json"),
    "codex": Path(".codex/auth.json"),
}


def interactive_argv(
    runtime: str, model: str, binaries: Mapping[str, object], environ: Mapping[str, str]
) -> tuple[str, ...]:
    default = _BINARIES.get(runtime)
    if default is None:
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, f"Runtime {runtime!r} has no interactive launcher"
        )
    if not model or model.startswith("-") or any(ord(char) < 32 for char in model):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid interactive model")
    binary = binaries.get(runtime, default)
    if not isinstance(binary, str) or ("/" in binary and not Path(binary).is_absolute()):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Expected a binary name or absolute path")
    try:
        executable = resolve_binary_path(binary, environ=environ, display_name=runtime)
    except FileNotFoundError as exc:
        raise CapabilityUnavailable(ErrorCode.RUNTIME_NOT_INSTALLED, str(exc)) from exc
    return str(executable), "--model", model


@dataclass(frozen=True, slots=True)
class InteractiveSession:
    session_id: str
    project_id: str
    runtime: str
    model: str | None
    checkout: str
    pid: int
    start_ticks: int
    boot_id: str
    owner_fd: int

    @property
    def identity(self) -> ProcessIdentity:
        return ProcessIdentity(self.pid, self.start_ticks, self.boot_id)


def _session_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Expected a session UUID") from exc


@contextmanager
def _state_errors() -> Generator[None]:
    try:
        yield
    except (OSError, ValueError) as exc:
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, f"Interactive session: {exc}") from exc


def _check_root(root: Path, *, create: bool = False) -> bool:
    if sys.platform != "linux" or not hasattr(os, "pidfd_open"):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE, "Interactive sessions require Linux pidfds"
        )
    if create:
        root.mkdir(mode=0o700, exist_ok=True)
    try:
        info = root.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
        raise OSError("Expected a user-owned 0700 session directory")
    return True


@contextmanager
def _open_record(path: Path) -> Generator[int]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if info.st_nlink == 0:
            raise FileNotFoundError(path)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
        ):
            raise OSError("Expected a user-owned 0600 session record")
        yield fd
    finally:
        os.close(fd)


def _owns_session(session: InteractiveSession, folder: Path) -> bool:
    if not is_same_process(session.identity):
        return False
    try:
        expected = folder.lstat()
        actual = Path(f"/proc/{session.pid}/fd/{session.owner_fd}").stat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISDIR(expected.st_mode)
        and stat.S_IMODE(expected.st_mode) == 0o700
        and expected.st_uid == os.geteuid()
        and os.path.samestat(expected, actual)
    )


def _remove(folder: Path, record: Path) -> None:
    with suppress(FileNotFoundError):
        rmtree(folder)
    record.unlink(missing_ok=True)


class InteractiveLauncher:
    """Start, attach and stop sessions belonging to this local SKM profile."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()

    def _record(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def _read(self, session_id: str) -> InteractiveSession | None:
        path = self._record(session_id)
        try:
            with _open_record(path) as fd, open(fd, "rb", closefd=False) as stream:
                return _decode_record(session_id, stream.read(_MAX_RECORD + 1))
        except FileNotFoundError:
            return None

    def _lookup(self, session_id: str) -> InteractiveSession | None:
        session = self._read(session_id) if _check_root(self.root) else None
        folder = self.root / session_id
        if session is not None and not _owns_session(session, folder):
            if not is_same_process(session.identity):
                _remove(folder, self._record(session_id))
            elif folder.exists():
                raise OSError("Session supervisor does not own its terminal directory")
            return None
        return session

    def list(self) -> tuple[InteractiveSession, ...]:
        with _state_errors():
            if not _check_root(self.root):
                return ()
            return tuple(
                session
                for path in sorted(self.root.glob("*.json"))
                if (session := self._lookup(_session_id(path.stem))) is not None
            )

    def start(
        self,
        argv: tuple[str, ...],
        *,
        project_id: str,
        runtime: str,
        model: str | None,
        checkout: Path,
        environ: Mapping[str, str],
        account_home: Path | None = None,
        native_auth: SecretStr | None = None,
    ) -> InteractiveSession:
        with _state_errors():
            _check_root(self.root, create=True)
            if not checkout.is_absolute() or not argv or not Path(argv[0]).is_absolute():
                raise ValueError("An absolute checkout and runtime executable are required")
            session_id = str(uuid4())
            folder = self.root / session_id
            folder.mkdir(mode=0o700)
            try:
                home = account_home
                if home is None:
                    home = folder / "home"
                    home.mkdir(mode=0o700)
                if native_auth is not None:
                    target = home / NATIVE_ACCOUNT_FILES[runtime]
                    target.parent.mkdir(mode=0o700)
                    atomic_write(target, native_auth.reveal().encode(), mode=0o600, private=True)
            except BaseException:
                # The supervisor has not started. No other process owns these files.
                _remove(folder, self._record(session_id))
                raise
            return self._launch(
                folder, argv, project_id, runtime, model, checkout, {**environ, "HOME": str(home)}
            )

    def _launch(
        self,
        folder: Path,
        argv: tuple[str, ...],
        project_id: str,
        runtime: str,
        model: str | None,
        checkout: Path,
        environ: Mapping[str, str],
    ) -> InteractiveSession:
        with ExitStack() as before_spawn, ExitStack() as pipes:
            before_spawn.callback(_remove, folder, self._record(folder.name))
            caller, worker = os.pipe()
            pipes.callback(os.close, caller)
            try:
                proc = subprocess.Popen(  # noqa: TID251 - detached PTY owner with a startup descriptor
                    (
                        sys.executable,
                        "-I",
                        "-m",
                        __name__,
                        str(worker),
                        str(folder),
                        project_id,
                        runtime,
                        model or "",
                        *argv,
                    ),
                    cwd=checkout,
                    env={**environ, "TERM": environ.get("TERM") or "xterm-256color"},
                    pass_fds=(worker,),
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # The supervisor and the launch handshake now own teardown.
                before_spawn.pop_all()
            finally:
                os.close(worker)
            try:
                if (
                    not select([caller], [], [], _START_TIMEOUT)[0]
                    or os.read(caller, 1) != b"1"
                    or (session := self._lookup(folder.name)) is None
                ):
                    raise OSError("Runtime exited during interactive startup")
            except BaseException as exc:
                with suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    proc.wait(timeout=_STOP_TIMEOUT_MS / 1000)
                except subprocess.TimeoutExpired:
                    exc.add_note("Interactive supervisor did not finish startup cleanup")
                    Thread(target=proc.wait, daemon=True).start()
                else:
                    _remove(folder, self._record(folder.name))
                raise
        Thread(target=proc.wait, daemon=True).start()
        return session

    def attach(self, session_id: str, stdin: TextIO, stdout: TextIO) -> None:
        with _state_errors():
            session = self._require(session_id)
            if not stdin.isatty() or not stdout.isatty():
                raise ValueError("Attach requires an interactive terminal")
            try:
                with _open_record(self._record(session.session_id)) as fd:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as exc:
                        raise ValueError("Session already has an attached terminal") from exc
                    terminal.attach(self.root / session.session_id, stdin.fileno(), stdout.fileno())
            except FileNotFoundError as exc:
                raise _missing(session.session_id) from exc

    def stop(self, session_id: str) -> InteractiveSession:
        with _state_errors():
            session = self._require(session_id)
            folder = self.root / session.session_id
            with suppress(ProcessLookupError):
                fd = os.pidfd_open(session.pid)
                try:
                    if _owns_session(session, folder):
                        signal.pidfd_send_signal(fd, signal.SIGTERM)
                        watcher = poll()
                        watcher.register(fd)
                        if not watcher.poll(_STOP_TIMEOUT_MS):
                            raise TimeoutError("Session supervisor did not stop")
                    elif is_same_process(session.identity) and folder.exists():
                        raise OSError("Session supervisor does not own its terminal directory")
                finally:
                    os.close(fd)
            _remove(folder, self._record(session.session_id))
            return session

    def _require(self, value: str) -> InteractiveSession:
        session_id = _session_id(value)
        if (session := self._lookup(session_id)) is None:
            raise _missing(session_id)
        return session


def _missing(session_id: str) -> NotFound:
    return NotFound(
        ErrorCode.NOT_FOUND, "Interactive session is no longer running", details={"session_id": session_id}
    )


def _decode_record(session_id: str, raw: bytes) -> InteractiveSession:
    try:
        if len(raw) > _MAX_RECORD:
            raise ValueError
        parsed: object = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError
        data = cast("dict[str, object]", parsed)
        if set(data) != {field.name for field in fields(InteractiveSession)}:
            raise ValueError
        if data["session_id"] != session_id or not all(
            type(data[key]) is str and data[key] for key in ("project_id", "runtime", "checkout", "boot_id")
        ):
            raise ValueError
        if data["model"] is not None and type(data["model"]) is not str:
            raise ValueError
        pid, ticks, owner_fd = data["pid"], data["start_ticks"], data["owner_fd"]
        if (
            type(pid) is not int
            or type(ticks) is not int
            or type(owner_fd) is not int
            or pid <= 0
            or ticks <= 0
            or owner_fd < 3
        ):
            raise ValueError
        return InteractiveSession(
            session_id,
            cast("str", data["project_id"]),
            cast("str", data["runtime"]),
            data["model"],
            cast("str", data["checkout"]),
            pid,
            ticks,
            cast("str", data["boot_id"]),
            owner_fd,
        )
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError(f"Invalid session record {session_id}") from exc


def _supervise(ready: int, folder: Path, session: InteractiveSession, argv: tuple[str, ...]) -> None:
    stopping = False

    def stop(_sig: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, stop)
    record = folder.with_suffix(".json")
    try:
        with (
            open(ready, "wb", buffering=0) as startup,
            terminal.control_pipe(folder) as control,
            terminal.open_terminal(argv) as child,
        ):
            if stopping or child.exited():
                return
            atomic_write(record, json.dumps(asdict(session)).encode(), mode=0o600)
            startup.write(b"1")
            startup.close()
            terminal.serve(folder, control, child, lambda: stopping)
    finally:
        _remove(folder, record)


def _main() -> None:
    fd, locator, project, runtime, model, *argv = sys.argv[1:]
    folder = Path(locator)
    session_id = _session_id(folder.name)
    identity = identity_of(os.getpid())
    if identity is None or identity.start_ticks is None or identity.boot_id is None:
        raise OSError("Session process identity unavailable")
    if not _check_root(folder.parent) or not _check_root(folder):
        raise OSError("Session state directory unavailable")
    ready = int(fd)
    os.set_inheritable(ready, False)
    owner_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        session = InteractiveSession(
            session_id,
            project,
            runtime,
            model or None,
            os.getcwd(),
            identity.pid,
            identity.start_ticks,
            identity.boot_id,
            owner_fd,
        )
        _supervise(ready, folder, session, tuple(argv))
    finally:
        os.close(owner_fd)


if __name__ == "__main__":
    _main()
