"""Durable ownership records. PID facts alone never authorize orphan cleanup."""

from __future__ import annotations

import os
import selectors
import stat
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast
from uuid import UUID

from skm.kernel.clock import Monotonic
from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership
from skm.platform.process import markers
from skm.platform.process.identity import ProcessIdentity, identity_of
from skm.platform.process.identity import is_same_process as _same
from skm.platform.process.ownership import ChildPipes, OwnedProcess
from skm.platform.system_clock import SystemMonotonic

if TYPE_CHECKING:
    from .cancel import Sleeper

__all__: list[str] = []


class OwnedContainment(Protocol):
    """Backend authority bound to the complete durable owner, never a bare PID/name."""

    def confirmed(self, ownership: ProcessOwnership) -> bool: ...
    def empty(self) -> bool | None: ...
    def signal(self, sig: int) -> None: ...


def start_ticks(pid: int) -> int | None:
    identity = identity_of(pid)
    return None if identity is None else identity.start_ticks


def boot_id() -> str | None:
    return markers.boot_id()


def is_same_process(identity: ProcessIdentity) -> bool:
    if identity.boot_id is None or identity.start_ticks is None:
        return False
    return _same(identity)


def create_marker(identity_dir: Path, ownership: ProcessOwnership) -> Path:
    return markers.create_marker(identity_dir, asdict(ownership))


def claim_marker(identity_dir: Path, ownership: ProcessOwnership) -> Path:
    return markers.claim_marker(identity_dir, asdict(ownership))


def _read_marker(path: Path) -> dict[str, object]:
    return markers.read_marker(path)


def load_marker(path: Path) -> ProcessOwnership:
    data = _read_marker(path)
    owner = cast("dict[str, str]", data["owner"])
    bound_owner = ProcessOwner(
        UUID(owner["host_id"]),
        UUID(owner["worker_id"]),
        UUID(owner["attempt_id"]),
        UUID(owner["stage_record_id"]),
        cast("Literal['step', 'check', 'git_effect']", owner["unit_kind"]),
        UUID(owner["unit_id"]),
        owner["owner_nonce"],
        owner["identity_dir"],
    )
    return ProcessOwnership(
        bound_owner,
        cast("Literal['cgroup', 'container', 'pgroup_best_effort']", data["kind"]),
        cast("str", data["ref"]),
        cast("str | None", data.get("daemon_identity")),
    )


def update_marker(path: Path, identity: ProcessIdentity, *, pgid: int | None) -> None:
    ownership = load_marker(path)
    markers.update_marker(path, identity, pgid=pgid, ownership=asdict(ownership))


def remove_marker(path: Path) -> None:
    markers.remove_marker(path)


class GroupProcess:
    """Explicit trusted best effort only. The pidfd owner pins signal authority until reap.

    Escaped setsid descendants are outside this proof; this class cannot admit a required backend.
    Drain happens in bounded nonblocking batches and does not allocate an intermediate pipe queue.
    """

    def __init__(
        self,
        pipes: ChildPipes,
        owned: OwnedProcess,
        ownership: ProcessOwnership,
        stdout: Callable[[bytes], None],
        stderr: Callable[[bytes], None],
    ) -> None:
        self.pipes, self.owned, self.ownership = pipes, owned, ownership
        self.pid = self.pgid = owned.pid
        self.identity = owned.identity
        self._callbacks = {"stdout": stdout, "stderr": stderr}
        self._selector = selectors.DefaultSelector()
        for name, source in (("stdout", pipes.stdout), ("stderr", pipes.stderr)):
            os.set_blocking(source.fileno(), False)
            self._selector.register(source, selectors.EVENT_READ, name)
        os.set_blocking(pipes.stdin.fileno(), False)

    def confirmed(self, ownership: ProcessOwnership) -> bool:
        return ownership == self.ownership and self.owned.held_here()

    def empty(self) -> bool | None:
        return not self.owned.group_alive()

    def signal(self, sig: int) -> None:
        self.owned.signal_group(sig)

    def poll(self) -> int | None:
        return self.owned.exit_code()

    def pump(self) -> None:
        for _ in range(16):
            ready = self._selector.select(0)
            if not ready:
                break
            for key, _ in ready:
                try:
                    chunk = os.read(key.fd, 65_536)
                except BlockingIOError:
                    continue
                if chunk:
                    self._callbacks[cast("str", key.data)](chunk)
                else:
                    self._selector.unregister(key.fileobj)

    def write_stdin(self, data: bytes) -> None:
        """Called on the session loop in bounded batches, so a blocked prompt cannot stall cancel."""
        if self.pipes.stdin.closed:
            return
        try:
            written = os.write(self.pipes.stdin.fileno(), data[:65_536]) if data else 0
        except BlockingIOError:
            return
        self.stdin_written += written

    stdin_written: int = 0

    def close_stdin(self) -> None:
        self.pipes.stdin.close()

    def close(self) -> None:
        self._selector.close()
        for stream in (self.pipes.stdin, self.pipes.stdout, self.pipes.stderr):
            stream.close()
        if self.empty() is True:
            self.owned.reap(0)
            self.owned.close()


@dataclass(frozen=True)
class ReapedStep:
    step_id: UUID
    ownership: ProcessOwnership


class _ReapSleeper:
    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)


def reap_orphans(
    identity_dir: Path,
    *,
    resolve: Callable[[ProcessOwnership], OwnedContainment | None] | None = None,
    clock: Monotonic | None = None,
    sleeper: Sleeper | None = None,
) -> tuple[ReapedStep, ...]:
    """Only an exact backend binding and positive empty proof can remove a marker.

    No backend is implicitly rediscovered from untrusted PID/PGID or a container name.
    Unknown/EPERM and process-group-only records remain for the operator.
    """
    if resolve is None:
        return ()
    from .cancel import terminate_group

    info = identity_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        return ()
    reaped: list[ReapedStep] = []
    for path in sorted(identity_dir.glob("*.json")):
        try:
            ownership = load_marker(path)
            if Path(ownership.owner.identity_dir).resolve() != identity_dir.resolve():
                continue
            if ownership.kind == "pgroup_best_effort":
                continue
            backend = resolve(ownership)
            if backend is None or not backend.confirmed(ownership):
                continue
            stopped = terminate_group(
                None,
                ownership=ownership,
                backend=backend,
                mode="reap",
                clock=clock if clock is not None else SystemMonotonic(),
                sleeper=sleeper if sleeper is not None else _ReapSleeper(),
            )
            if stopped.stopped:
                remove_marker(path)
                reaped.append(ReapedStep(ownership.owner.unit_id, ownership))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return tuple(reaped)
