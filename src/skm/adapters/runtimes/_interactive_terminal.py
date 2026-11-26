"""Terminal transport between the session supervisor and its one attached client."""

import errno
import fcntl
import os
import pty
import signal
import stat
import termios
import time
import tty
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path
from select import select
from shutil import rmtree
from typing import NamedTuple
from uuid import UUID, uuid4

__all__ = ["attach", "control_pipe", "open_terminal", "serve"]

_BUFFER = 4096
_HISTORY = 64 * 1024
_INTERVAL = 0.1
_DETACH = b"\x1d"
_HEADER = 4
_PAYLOAD = _BUFFER - _HEADER
_REQUEST_SIZE = 32
_READY = b"\x00"


class Terminal(NamedTuple):
    pid: int
    fd: int

    def exited(self) -> bool:
        return os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

    def close(self) -> None:
        # Keep the leader unreaped until cleanup finishes, so the terminal session ID cannot be reused.
        os.close(self.fd)
        try:
            self._signal_session(signal.SIGTERM)
            deadline = time.monotonic() + 1
            while not self.exited() and time.monotonic() < deadline:
                time.sleep(_INTERVAL)
        finally:
            try:
                self._signal_session(signal.SIGKILL)
            finally:
                os.waitpid(self.pid, 0)

    def _signal_session(self, sig: int) -> None:
        # A terminal application can create additional foreground or background process groups.
        with os.scandir("/proc") as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                pid = int(entry.name)
                with suppress(ProcessLookupError, PermissionError):
                    if os.getsid(pid) != self.pid:
                        continue
                    pidfd = os.pidfd_open(pid)
                    try:
                        if os.getsid(pid) == self.pid:
                            signal.pidfd_send_signal(pidfd, sig)
                    finally:
                        os.close(pidfd)


@contextmanager
def open_terminal(argv: tuple[str, ...]) -> Generator[Terminal]:
    # The close-on-exec pipe distinguishes a successful exec from an unavailable binary.
    reader, writer = os.pipe()
    try:
        pid, fd = pty.fork()
    except OSError:
        os.close(reader)
        os.close(writer)
        raise
    if pid == 0:
        os.close(reader)
        try:
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGPIPE, signal.SIGHUP):
                signal.signal(sig, signal.SIG_DFL)
            termios.tcsetwinsize(0, (24, 80))
            os.execv(argv[0], argv)
        except (OSError, ValueError):
            with suppress(OSError):
                os.write(writer, b"error")
        os._exit(127)
    terminal = Terminal(pid, fd)
    try:
        os.close(writer)
        with os.fdopen(reader, "rb") as stream:
            if stream.read(1):
                raise OSError("Interactive runtime could not be executed")
        os.set_blocking(fd, False)
        yield terminal
    finally:
        terminal.close()


def _write(fd: int, data: bytes) -> None:
    while data:
        if not select([], [fd], [], _INTERVAL)[1]:
            raise TimeoutError("Interactive terminal is blocked")
        data = data[os.write(fd, data) :]


def _fifo(path: Path, mode: int, stack: ExitStack) -> int:
    fd = os.open(path, mode | os.O_NOFOLLOW | os.O_NONBLOCK)
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    if not stat.S_ISFIFO(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
        raise OSError("Expected a user-owned 0600 session FIFO")
    return fd


def _make_fifo(path: Path) -> None:
    os.mkfifo(path, 0o600)
    path.chmod(0o600)


class _Attachment(NamedTuple):
    source: int
    sink: int
    resources: ExitStack
    pending: bytearray

    def close(self) -> None:
        self.resources.close()


def _receive(terminal: Terminal, attachment: _Attachment) -> None:
    data = os.read(attachment.source, _BUFFER)
    if not data:
        raise EOFError
    pending = attachment.pending
    pending.extend(data)
    while len(pending) >= _HEADER:
        size = int.from_bytes(pending[1:_HEADER], "big")
        if size > _PAYLOAD:
            raise OSError("Invalid terminal input frame")
        end = size + _HEADER
        if len(pending) < end:
            return
        kind, payload = pending[0], bytes(pending[_HEADER:end])
        del pending[:end]
        if kind == ord("i"):
            _write(terminal.fd, payload)
        elif kind == ord("w") and size == 8:
            fcntl.ioctl(terminal.fd, termios.TIOCSWINSZ, payload)
        else:
            raise OSError("Invalid terminal input frame")


def _accept(folder: Path, control: int, history: bytes) -> _Attachment | None:
    requests = os.read(control, _REQUEST_SIZE * 16)
    # A client writes a single atomic request. Latest requests supersede detached clients.
    try:
        name = UUID(requests[-_REQUEST_SIZE:].decode("ascii")).hex
    except ValueError:
        return None
    path = folder / f"attach-{name}"
    try:
        with ExitStack() as resources:
            source = _fifo(path / "input", os.O_RDONLY, resources)
            sink = _fifo(path / "output", os.O_WRONLY, resources)
            _write(sink, _READY + history)
            return _Attachment(source, sink, resources.pop_all(), bytearray())
    except OSError:
        return None


@contextmanager
def control_pipe(folder: Path) -> Generator[int]:
    path = folder / "control"
    _make_fifo(path)
    with ExitStack() as resources:
        # Linux permits O_RDWR on FIFOs. Keep both ends open so idle periods do not report EOF.
        yield _fifo(path, os.O_RDWR, resources)


def _output(fd: int) -> bytes:
    try:
        return os.read(fd, _BUFFER)
    except OSError as exc:
        if exc.errno == errno.EIO:
            return b""  # Linux reports EIO when the last slave closes.
        raise


def serve(folder: Path, control: int, terminal: Terminal, stopping: Callable[[], bool]) -> None:
    attachment: _Attachment | None = None
    history = b""
    try:
        while not stopping():
            watched = [control, terminal.fd]
            if attachment is not None:
                watched.append(attachment.source)
            ready, _, _ = select(watched, [], [], _INTERVAL)
            if attachment is not None and attachment.source in ready:
                try:
                    _receive(terminal, attachment)
                except (OSError, EOFError):
                    attachment.close()
                    attachment = None
            if control in ready:
                if attachment is not None:
                    attachment.close()
                attachment = _accept(folder, control, history)
            if terminal.fd in ready:
                output = _output(terminal.fd)
                if not output:
                    break
                history = (history + output)[-_HISTORY:]
                if attachment is not None:
                    try:
                        _write(attachment.sink, output)
                    except OSError:
                        attachment.close()
                        attachment = None
            if terminal.exited():
                break
    finally:
        if attachment is not None:
            attachment.close()


def _frame(kind: bytes, data: bytes) -> bytes:
    return kind + len(data).to_bytes(_HEADER - 1, "big") + data


def _relay(source: int, sink: int, input_fd: int, output_fd: int) -> None:
    try:
        size = b""
        while True:
            ready, _, _ = select([input_fd, source], [], [], _INTERVAL)
            current = fcntl.ioctl(output_fd, termios.TIOCGWINSZ, bytes(8))
            if current != size:
                _write(sink, _frame(b"w", current))
                size = current
            if source in ready:
                data = os.read(source, _BUFFER)
                if not data:
                    return
                _write(output_fd, data)
            if input_fd in ready:
                data = os.read(input_fd, _PAYLOAD)
                before, detach, _ = data.partition(_DETACH)
                if before:
                    _write(sink, _frame(b"i", before))
                if detach or not data:
                    return
    except BrokenPipeError:
        return


@contextmanager
def _attachment_dir(folder: Path) -> Generator[tuple[str, Path]]:
    key = uuid4().hex
    path = folder / f"attach-{key}"
    path.mkdir(mode=0o700)
    try:
        yield key, path
    finally:
        with suppress(FileNotFoundError):
            rmtree(path)


def attach(folder: Path, input_fd: int, output_fd: int) -> None:
    with _attachment_dir(folder) as (key, path), ExitStack() as resources:
        _make_fifo(path / "input")
        _make_fifo(path / "output")
        # Keep input readable until the supervisor opens its read descriptor.
        sink = _fifo(path / "input", os.O_RDWR, resources)
        source = _fifo(path / "output", os.O_RDONLY, resources)
        control = _fifo(folder / "control", os.O_WRONLY, resources)
        # Set raw mode before sending the request so type-ahead, including detach, is unbuffered.
        original = termios.tcgetattr(input_fd)
        try:
            tty.setraw(input_fd)
            _write(control, key.encode("ascii"))
            if not select([source], [], [], 2)[0] or os.read(source, 1) != _READY:
                raise OSError("Session terminal is no longer available")
            _relay(source, sink, input_fd, output_fd)
        finally:
            termios.tcsetattr(input_fd, termios.TCSADRAIN, original)
