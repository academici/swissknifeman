"""Process lifecycle of trusted checks: ownership markers, process-group termination and the launcher.

Checks own their processes the way runtimes do and share the runtime marker wire format, but
cross-technology adapter imports are forbidden, so the helpers live here. Numeric PIDs never grant signal
or destructive-cleanup authority."""

from __future__ import annotations

import hashlib
import json
import marshal
import os
import selectors
import signal
import socket
import stat
import struct
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

from skm.kernel.clock import Monotonic
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.runtimes.public import ProcessOwnership
from skm.platform.fs.atomic_write import atomic_write, fsync_dir
from skm.platform.fs.file_lock import FileLock
from skm.platform.process.identity import ProcessIdentity
from skm.platform.process.ownership import ChildPipes, OwnedProcess, launch, require_support

if TYPE_CHECKING:
    from .command import CheckProcess


__all__ = [
    "claim_marker",
    "clear_environment",
    "environment_guard",
    "remove_marker",
    "terminate_group",
    "update_marker",
]


def _ownership_json(ownership: ProcessOwnership) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(json.dumps(asdict(ownership), default=str)))


def _marker_data(path: Path, ownership: ProcessOwnership) -> dict[str, Any]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("unsafe check ownership marker")
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("oversized check ownership marker")
    data = cast("dict[str, Any]", json.loads(raw))
    expected = _ownership_json(ownership)
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError("check ownership marker binding changed")
    return data


def claim_marker(identity_dir: Path, ownership: ProcessOwnership) -> Path:
    if identity_dir.resolve() != Path(ownership.owner.identity_dir).resolve():
        raise ValueError("check marker directory differs from owner")
    identity_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = identity_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError("check ownership directory must be private and owned")
    path = identity_dir / f"{ownership.owner.unit_id}.json"
    with FileLock(path.with_suffix(".launch.lock")).hold(timeout_seconds=1):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        except FileExistsError:
            data = _marker_data(path, ownership)
            if data.get("launching") or data.get("process") is not None:
                raise ValueError("check launch already started or uncertain") from None
            data["launching"] = True
            atomic_write(path, json.dumps(data).encode(), mode=0o600, private=True)
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps({**_ownership_json(ownership), "launching": True}).encode())
                stream.flush()
                os.fsync(stream.fileno())
            fsync_dir(identity_dir)
    return path


def update_marker(path: Path, identity: ProcessIdentity, *, ownership: ProcessOwnership, pgid: int) -> None:
    data = _marker_data(path, ownership)
    if data.get("process") is not None:
        raise ValueError("check marker already launched")
    data.update({"boot_id": identity.boot_id, "process": {**asdict(identity), "pgid": pgid}})
    atomic_write(path, json.dumps(data).encode(), mode=0o600, private=True)


def remove_marker(path: Path, ownership: ProcessOwnership) -> None:
    _marker_data(path, ownership)
    path.unlink()
    path.with_suffix(".launch.lock").unlink(missing_ok=True)
    fsync_dir(path.parent)


@dataclass(frozen=True)
class CleanupOutcome:
    stopped: bool
    reason: str | None = None


def _wait_empty(
    backend: Any, seconds: float, clock: Monotonic, sleeper: Any, drain: Callable[[], None]
) -> bool:
    deadline = clock.monotonic() + seconds
    for _ in range(int(seconds / 0.05) + 2):
        drain()
        if backend.empty() is True:
            return True
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            break
        sleeper.sleep(min(remaining, 0.05))
    return backend.empty() is True


def terminate_group(
    *,
    ownership: ProcessOwnership,
    mode: Literal["cancel", "reap"],
    backend: Any,
    clock: Monotonic,
    sleeper: Any,
    grace_int_seconds: float,
    grace_term_seconds: float,
    drain: Callable[[], None],
) -> CleanupOutcome:
    if mode not in {"cancel", "reap"} or grace_int_seconds < 0 or grace_term_seconds < 0:
        raise ValueError("invalid check termination policy")
    try:
        if not backend.confirmed(ownership):
            return CleanupOutcome(False, "ownership_unconfirmed")
        if backend.empty() is True:
            return CleanupOutcome(True)
        stages = (
            ((signal.SIGINT, grace_int_seconds), (signal.SIGTERM, grace_term_seconds))
            if mode == "cancel"
            else ((signal.SIGTERM, grace_term_seconds),)
        )
        for sig, seconds in (*stages, (signal.SIGKILL, 1.0)):
            # A vanished leader is not containment-empty proof.
            with suppress(ProcessLookupError):
                backend.signal(sig)
            if _wait_empty(backend, seconds, clock, sleeper, drain):
                return CleanupOutcome(True)
        return CleanupOutcome(False, "cleanup_unconfirmed")
    except PermissionError:
        return CleanupOutcome(False, "signal_permission_denied")
    except OSError:
        return CleanupOutcome(False, "cleanup_unconfirmed")


@contextmanager
def environment_guard(state_dir: Path, environment: Any, *, recovery: bool = False) -> Generator[Path]:
    """One check at a time; an uncertain launch survives runner/host restarts as a durable latch."""
    directory = state_dir / "check-environments"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(str(environment.environment_id).encode()).hexdigest()
    quarantine = directory / f"{key}.json"
    with FileLock(directory / f"{key}.lock").hold(timeout_seconds=1):
        if not recovery and (quarantine.exists() or quarantine.is_symlink()):
            raise error_for(ErrorCode.CHECKOUT_BUSY, "check containment requires confirmed reap/reconcile")
        yield quarantine


def clear_environment(quarantine: Path, environment: Any, ownership: ProcessOwnership) -> None:
    data = _marker_data(quarantine, ownership)
    if (
        data.get("environment_id") != str(environment.environment_id)
        or data.get("locator") != environment.locator
    ):
        raise ValueError("check environment latch binding changed")
    quarantine.unlink()
    fsync_dir(quarantine.parent)


# The platform first binds a child-owned pidfd. This second gate holds the actual check until
# capture initialization and peer ownership succeed. The control socket closes on successful exec.
_CHECK_BOOTSTRAP = r"""
import marshal, os, signal, socket, sys
channel = socket.socket(socket.AF_UNIX)
channel.connect(bytes.fromhex(sys.argv[1]))
os.set_inheritable(channel.fileno(), False)
request = bytearray()
while chunk := channel.recv(65536):
    request += chunk
if not request:
    os._exit(125)
try:
    argv, env = marshal.loads(request)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    if null != 0:
        os.close(null)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    os.execvpe(argv[0], argv, env)
except OSError as error:
    channel.sendall(str(error.errno).encode("ascii"))
os._exit(127)
"""


class _GroupCheck:
    def __init__(self, pipes: ChildPipes, owned: OwnedProcess, ownership: ProcessOwnership) -> None:
        # Capture the handle before any fallible selector/pipe initialization.
        self.pipes, self.owned, self.ownership = pipes, owned, ownership
        self.pid, self.identity = owned.pid, owned.identity
        self.selector: selectors.BaseSelector | None = None

    def initialize(self, callbacks: tuple[Callable[[bytes], None], Callable[[bytes], None]]) -> None:
        self.pipes.stdin.close()
        self.selector = selectors.DefaultSelector()
        for stream, callback in zip((self.pipes.stdout, self.pipes.stderr), callbacks, strict=True):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, callback)

    def confirmed(self, ownership: ProcessOwnership) -> bool:
        return ownership == self.ownership and self.owned.held_here()

    def empty(self) -> bool | None:
        return not self.owned.group_alive()

    def signal(self, sig: int) -> None:
        self.owned.signal_group(sig)

    def poll(self) -> int | None:
        return self.owned.exit_code()

    def pump(self) -> None:
        if self.selector is None:
            return
        for _ in range(8):
            ready = self.selector.select(0)
            if not ready:
                return
            for key, _ in ready:
                try:
                    chunk = os.read(key.fd, 65_536)
                except BlockingIOError:
                    continue
                if chunk:
                    key.data(chunk)
                else:
                    self.selector.unregister(key.fileobj)

    def close(self) -> None:
        if self.empty() is not True or self.owned.reap(0) is None:
            raise RuntimeError("check reap/containment empty unconfirmed")
        if self.selector is not None:
            self.selector.close()
        self.pipes.stdin.close()
        self.pipes.stdout.close()
        self.pipes.stderr.close()
        self.owned.close()


class CheckLaunchError(RuntimeError):
    def __init__(self, process: CheckProcess, primary: BaseException) -> None:
        super().__init__(str(primary))
        self.process, self.primary = process, primary


class TrustedCheckLauncher:
    """Explicit trusted-full-access only; obtain ownership before releasing the wrapped check."""

    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed

    def validate(self, command: Any) -> None:
        if not self.allowed or command.ownership.kind != "pgroup_best_effort":
            raise error_for(ErrorCode.SANDBOX_UNAVAILABLE, "required check containment unavailable")
        require_support()

    def spawn(
        self,
        command: Any,
        *,
        marker: Path,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
    ) -> CheckProcess:
        self.validate(command)
        if not marker.is_file():
            raise ValueError("durable check marker required before spawn")
        address = b"\0skm-check-" + uuid4().hex.encode("ascii")
        process: _GroupCheck | None = None
        try:
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(address)
                listener.listen(1)
                listener.settimeout(5)
                pipes, owned = launch(
                    (sys.executable, "-I", "-S", "-B", "-c", _CHECK_BOOTSTRAP, address.hex()),
                    cwd=command.cwd,
                    env=command.env,
                )
                process = _GroupCheck(pipes, owned, command.ownership)
                process.initialize((on_stdout, on_stderr))
                channel, _ = listener.accept()
                with channel:
                    channel.settimeout(5)
                    peer = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    if peer[:2] != (owned.pid, os.geteuid()):
                        raise RuntimeError("check release peer differs from owned child")
                    channel.sendall(marshal.dumps((command.argv, dict(command.env))))
                    channel.shutdown(socket.SHUT_WR)
                    reply = bytearray()
                    while chunk := channel.recv(32):
                        reply += chunk
                        if len(reply) > 32:
                            raise RuntimeError("invalid check exec response")
                    if reply:
                        code = int(reply)
                        raise OSError(code, os.strerror(code), command.argv[0])
        except BaseException as primary:
            if process is not None:
                raise CheckLaunchError(process, primary) from primary
            raise
        return process
