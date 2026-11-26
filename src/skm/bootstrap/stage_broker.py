"""Private assignment MCP channels gated by live project authority and process ownership."""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager, suppress
from dataclasses import replace
from io import TextIOBase
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING, TextIO, cast, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.execution.host.context import StageToolBinding, StageToolChannel, WorkerServices
from skm.modules.execution.public import VerifyStageAccess
from skm.modules.runtimes.public import McpServerSpec
from skm.platform.logging.setup import register_secret
from skm.platform.process.identity import identity_of, is_same_process

if TYPE_CHECKING:
    from io import BufferedReader
    from uuid import UUID

    from skm.application_bus.client import SkmClient
    from skm.application_bus.host import HostServices
    from skm.modules.runtimes.public import SecretStr, SessionHandle
    from skm.platform.process.identity import ProcessIdentity

__all__ = ["StageMcpServer", "bind_stage_broker", "request_stage_tools", "run_stage_mcp_proxy"]

type StageMcpServer = Callable[[SkmClient, UUID, frozenset[str], Callable[[], None], TextIO, TextIO], int]
_MAX_MESSAGE = 1_048_576


def _peer_pid(channel: socket.socket) -> int:
    if sys.platform == "linux":
        credentials = struct.Struct("=iII")
        pid, uid, _ = credentials.unpack(
            channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, credentials.size)
        )
        if uid != os.geteuid():
            raise PermissionError("Stage tools require a local process of this worker")
        return pid
    if sys.platform == "darwin":
        # Darwin exposes peer pid through LOCAL_PEERPID at SOL_LOCAL. The socket directory is owner-only.
        return struct.unpack("=i", channel.getsockopt(0, 2, struct.calcsize("=i")))[0]
    raise PermissionError("Stage tools require Unix peer process credentials")


class _BoundedInput(TextIOBase):
    def __init__(self, stream: BufferedReader) -> None:
        self._stream = stream

    @override
    def readline(self, size: int = -1) -> str:
        limit = _MAX_MESSAGE if size < 0 else min(size, _MAX_MESSAGE)
        line = self._stream.readline(limit + 1)
        if len(line) > limit:
            raise OSError("Stage MCP input exceeds its maximum message length")
        return line.decode("utf-8")


class _StageSocket:
    def __init__(
        self,
        listener: socket.socket,
        binding: StageToolBinding,
        worker: SkmClient,
        client: SkmClient,
        serve: StageMcpServer,
    ) -> None:
        self._listener, self._binding, self._worker, self._client, self._serve = (
            listener,
            binding,
            worker,
            client,
            serve,
        )
        self._started, self._closed = Event(), Event()
        self._leader: ProcessIdentity | None = None
        self._lock = Lock()
        self._peers: set[socket.socket] = set()
        self._threads: set[Thread] = set()

    def process_started(self, handle: SessionHandle) -> None:
        owner = None if handle.ownership is None else handle.ownership.owner
        binding = self._binding
        if (
            owner is not None
            and handle.pid is not None
            and (owner.worker_id, owner.attempt_id, owner.stage_record_id, owner.unit_id)
            == (binding.claim.worker_id, binding.claim.attempt_id, binding.stage_record_id, binding.step_id)
        ):
            identity = identity_of(handle.pid)
            if identity is not None and identity.start_ticks == handle.process_start_ticks:
                self._leader = identity
        self._started.set()

    def _admit(self, peer_pid: int) -> None:
        leader = self._leader
        if (
            self._closed.is_set()
            or leader is None
            or not is_same_process(leader)
            or os.getpgid(peer_pid) != leader.pid
        ):
            raise PermissionError("Process does not own this stage MCP channel")
        binding = self._binding
        identity = cast("WhoAmIView", self._worker.ask(WhoAmI(scope_id=binding.workspace_id)))
        if "worker.claim" not in identity.effective_permissions:
            raise Forbidden(ErrorCode.FORBIDDEN, "Worker authority was revoked")
        self._client.ask(
            VerifyStageAccess(
                assignment_id=binding.claim.assignment_id,
                attempt_id=binding.claim.attempt_id,
                worker_id=binding.claim.worker_id,
                fencing_token=binding.claim.fencing_token,
                stage_record_id=binding.stage_record_id,
                step_id=binding.step_id,
            )
        )

    def _handle(self, peer: socket.socket) -> None:
        from threading import current_thread

        try:
            with peer:
                pid = _peer_pid(peer)
                if not self._started.wait(timeout=3):
                    return

                def admit() -> None:
                    self._admit(pid)

                admit()
                with peer.makefile("rb") as reader, peer.makefile("w", encoding="utf-8") as output:
                    self._serve(
                        self._client,
                        self._binding.project_id,
                        self._binding.tools,
                        admit,
                        cast("TextIO", _BoundedInput(reader)),
                        output,
                    )
        except (OSError, SkmError):
            # A stopped stage or denied caller cannot continue on this connection.
            pass
        finally:
            with self._lock:
                self._peers.discard(peer)
                self._threads.discard(current_thread())

    def run(self) -> None:
        while not self._closed.is_set():
            try:
                peer, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with self._lock:
                if self._closed.is_set() or len(self._peers) >= 4:
                    peer.close()
                    continue
                thread = Thread(target=self._handle, args=(peer,), name="skm-stage-mcp-session", daemon=True)
                self._peers.add(peer)
                self._threads.add(thread)
                thread.start()

    def close(self) -> None:
        self._closed.set()
        self._started.set()
        self._listener.close()
        with self._lock:
            peers, threads = tuple(self._peers), tuple(self._threads)
        for peer in peers:
            with suppress(OSError):
                peer.shutdown(socket.SHUT_RDWR)
        for thread in threads:
            thread.join(timeout=1)


def bind_stage_broker(host: HostServices, serve: StageMcpServer) -> HostServices:
    services = host.gateways.get(WorkerServices)
    make_client = services.stage_tool_client
    if make_client is None:
        return host

    @contextmanager
    def channel(
        binding: StageToolBinding, secret: SecretStr, worker: SkmClient
    ) -> Generator[StageToolChannel]:
        register_secret(secret.reveal())
        with ExitStack() as stack:
            client = stack.enter_context(make_client(binding, secret))
            # AF_UNIX path limits are much shorter than supported installation paths.
            root = Path(stack.enter_context(TemporaryDirectory(prefix="skm-stage-", dir="/tmp")))
            path = str(root / "mcp.sock")
            listener = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
            listener.bind(path)
            os.chmod(path, 0o600)
            listener.listen(4)
            listener.settimeout(0.2)
            broker = _StageSocket(listener, binding, worker, client, serve)
            thread = Thread(target=broker.run, name="skm-stage-mcp", daemon=True)
            thread.start()
            stack.callback(thread.join, 1)
            stack.callback(broker.close)
            yield StageToolChannel(
                path,
                McpServerSpec(
                    "skm",
                    (sys.executable, "-m", "skm.entrypoints.cli.main", "mcp"),
                    {"SKM_STAGE_SOCKET": path},
                    (),
                ),
                broker.process_started,
            )

    gateways = GatewayTable(
        {**host.gateways.entries, WorkerServices: replace(services, stage_tools=channel)}, "host_gateway"
    )
    return replace(host, gateways=gateways)


@contextmanager
def _connect(path: str) -> Generator[socket.socket]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.connect(path)
        yield channel


def run_stage_mcp_proxy(path: str, stdin: TextIO, stdout: TextIO) -> int:
    with _connect(path) as channel:

        def send() -> None:
            with suppress(OSError):
                for line in stdin:
                    channel.sendall(line.encode("utf-8"))
                channel.shutdown(socket.SHUT_WR)

        Thread(target=send, name="skm-stage-mcp-input", daemon=True).start()
        with channel.makefile("r", encoding="utf-8") as output:
            for line in output:
                stdout.write(line)
                stdout.flush()
    return 0


def request_stage_tools(path: str) -> tuple[JsonObject, ...]:
    with _connect(path) as channel:
        channel.sendall(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
        with channel.makefile("rb") as reader:
            line = _BoundedInput(reader).readline()
            if not line:
                raise PermissionError("Stage MCP channel is no longer authorized")
            data = json.loads(line)
    return tuple(data["result"]["tools"])
