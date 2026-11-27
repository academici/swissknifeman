"""Bounded pipe draining shared by synchronous and streaming process supervision."""

import os
import selectors
from collections.abc import Callable
from contextlib import suppress
from typing import IO

from skm.platform.process.ownership import ChildPipes, add_note, describe_failure

__all__ = ["BoundedCapture", "ProcessStreams"]

_CHUNK = 65_536


class BoundedCapture:
    def __init__(self, limit: int, *, capture_tail: bool = False) -> None:
        self.limit = limit
        self.capture_tail = capture_tail
        self.data = bytearray()
        self.truncated = False

    def feed(self, chunk: bytes) -> None:
        remaining = self.limit - len(self.data)
        if self.capture_tail:
            del self.data[: max(0, len(chunk) - remaining)]
            self.data.extend(chunk[max(0, len(chunk) - self.limit) :])
        else:
            self.data.extend(chunk[:remaining])
        self.truncated |= len(chunk) > remaining


class _Sink:
    def __init__(self, callback: Callable[[bytes], None], line_mode: bool) -> None:
        self.callback = callback
        self.line_mode = line_mode
        self.pending = bytearray()

    def feed(self, chunk: bytes) -> None:
        if not self.line_mode:
            self.callback(chunk)
            return
        self.pending.extend(chunk)
        while self.pending:
            newline = self.pending.find(b"\n", 0, _CHUNK)
            length = newline + 1 if newline >= 0 else _CHUNK
            if len(self.pending) < length:
                break
            data = bytes(self.pending[:length])
            del self.pending[:length]
            # A hostile unterminated line is delivered in bounded fragments.
            self.callback(data)

    def finish(self) -> None:
        if self.pending:
            data = bytes(self.pending)
            self.pending.clear()
            self.callback(data)


class ProcessStreams:
    """One selector for both output pipes and optional nonblocking one-shot input.

    Callbacks execute on the supervisor thread and should return promptly. Lines retain
    newlines; a final partial line is flushed at EOF. Lines over 64 KiB are fragmented.
    """

    def __init__(
        self,
        proc: ChildPipes,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
        *,
        line_mode: bool,
        stdin: bytes | None,
        manage_stdin: bool,
    ) -> None:
        self.selector = selectors.DefaultSelector()
        self.files: dict[str, IO[bytes]] = {}
        self.sinks = {"stdout": _Sink(on_stdout, line_mode), "stderr": _Sink(on_stderr, line_mode)}
        self.input = memoryview(stdin or b"")
        try:
            for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                self.files[name] = pipe
                os.set_blocking(pipe.fileno(), False)
                self.selector.register(pipe.fileno(), selectors.EVENT_READ, name)
            if manage_stdin:
                self.files["stdin"] = proc.stdin
                if self.input:
                    os.set_blocking(proc.stdin.fileno(), False)
                    self.selector.register(proc.stdin.fileno(), selectors.EVENT_WRITE, "stdin")
                else:
                    self.drop("stdin")
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup:  # noqa: BLE001 - retain the primary setup failure
                add_note(primary, f"pipe setup cleanup failed: {describe_failure(cleanup)}")
            raise

    @property
    def has_output(self) -> bool:
        return bool(self.files.keys() & self.sinks.keys())

    def drop(self, name: str, *, flush: bool = False) -> None:
        pipe = self.files.pop(name, None)
        if pipe is None:
            return
        primary: BaseException | None = None
        try:
            with suppress(KeyError):
                self.selector.unregister(pipe.fileno())
        except BaseException as error:  # noqa: BLE001 - still close the descriptor
            primary = error
        try:
            pipe.close()
        except BaseException as error:  # noqa: BLE001 - retain unregister failure
            if primary is None:
                primary = error
            else:
                add_note(primary, f"pipe close failed: {describe_failure(error)}")
        if primary is not None:
            raise primary
        if flush:
            self.sinks[name].finish()

    def step(self, timeout: float) -> None:
        for key, _ in self.selector.select(timeout):
            name: str = key.data
            if name == "stdin":
                self._write_input(key.fd)
                continue
            try:
                data = os.read(key.fd, _CHUNK)
            except BlockingIOError:
                continue
            if data:
                self.sinks[name].feed(data)
            else:
                self.drop(name, flush=True)

    def _write_input(self, fd: int) -> None:
        try:
            written = os.write(fd, self.input[:4096])
        except BlockingIOError:
            return
        except BrokenPipeError:
            self.drop("stdin")
            return
        self.input = self.input[written:]
        if not self.input:
            self.drop("stdin")

    def finish(self) -> None:
        for sink in self.sinks.values():
            sink.finish()

    def close(self) -> None:
        primary: BaseException | None = None
        for name in tuple(self.files):
            try:
                self.drop(name)
            except BaseException as error:  # noqa: BLE001 - close all descriptors, then raise
                if primary is None:
                    primary = error
                else:
                    add_note(primary, f"pipe close failed: {describe_failure(error)}")
        try:
            self.selector.close()
        except BaseException as error:  # noqa: BLE001 - retain earlier descriptor close failure
            if primary is None:
                primary = error
            else:
                add_note(primary, f"selector close failed: {describe_failure(error)}")
        if primary is not None:
            raise primary
