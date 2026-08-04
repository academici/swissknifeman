"""Bounded, fresh POSIX provider process runner for the P3.4 activity port."""
from __future__ import annotations

import hashlib
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable


class WorkerRefusal(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _terminate(proc: subprocess.Popen[bytes], *, grace_seconds: float,
               clock: Callable[[], float], sleeper: Callable[[float], None]) -> bool:
    """TERM then KILL the whole fresh process group; return whether death was verified."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return proc.poll() is not None
    deadline = clock() + grace_seconds
    while proc.poll() is None and clock() < deadline:
        sleeper(0.01)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=max(grace_seconds, 0.01))
    except subprocess.TimeoutExpired:
        return False
    return proc.poll() is not None


def run(argv: list[str], *, cwd: str | Path, env: dict[str, str], stdin: bytes,
        timeout_ms: int, max_output_bytes: int, max_event_count: int,
        kill_grace_seconds: float = 1.0, clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep) -> dict:
    """Run one new process without retaining raw output or reusing a carrier/session."""
    if (not isinstance(argv, list) or not argv or any(not isinstance(v, str) for v in argv)
            or timeout_ms < 1 or max_output_bytes < 1 or max_event_count < 1):
        raise WorkerRefusal("MAPPING_UNKNOWN")
    started = clock()
    try:
        proc = subprocess.Popen(argv, cwd=str(Path(cwd)), env=dict(env), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except OSError:
        return {"kind": "provider_failure", "reason_code": "PROVIDER_UNAVAILABLE", "process_count": 0}
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(stdin)
        proc.stdin.close()
        output = bytearray()
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        deadline = started + timeout_ms / 1000
        overflow = None
        while selector.get_map():
            remaining = deadline - clock()
            if remaining <= 0:
                dead = _terminate(proc, grace_seconds=kill_grace_seconds, clock=clock, sleeper=sleeper)
                return {"kind": "orphaned" if not dead else "timeout",
                        "reason_code": "ORPHAN_IDENTITY_UNKNOWN" if not dead else "WALL_TIMEOUT",
                        "process_count": 1, "duration_ms": int((clock() - started) * 1000)}
            for key, _ in selector.select(min(remaining, 0.05)):
                chunk = os.read(key.fd, min(4096, max_output_bytes + 1 - len(output)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output.extend(chunk)
                if len(output) > max_output_bytes:
                    overflow = "BUDGET_OUTPUT_BYTES"
                    break
                if output.count(b"\n") > max_event_count:
                    overflow = "BUDGET_EVENT_COUNT"
                    break
            if overflow is not None:
                dead = _terminate(proc, grace_seconds=kill_grace_seconds, clock=clock, sleeper=sleeper)
                if not dead:
                    return {"kind": "orphaned", "reason_code": "ORPHAN_IDENTITY_UNKNOWN", "process_count": 1,
                            "duration_ms": int((clock() - started) * 1000)}
                return {"kind": "budget_exhausted", "reason_code": overflow, "process_count": 1,
                        "duration_ms": int((clock() - started) * 1000), "output_hash": _digest(bytes(output))}
        proc.wait(timeout=max(kill_grace_seconds, 0.01))
    except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
        dead = _terminate(proc, grace_seconds=kill_grace_seconds, clock=clock, sleeper=sleeper)
        return {"kind": "orphaned" if not dead else "provider_failure",
                "reason_code": "ORPHAN_IDENTITY_UNKNOWN" if not dead else "PROVIDER_PROTOCOL_UNKNOWN",
                "process_count": 1, "duration_ms": int((clock() - started) * 1000)}
    finally:
        try:
            selector.close()
        except UnboundLocalError:
            pass
        if proc.stdout is not None:
            proc.stdout.close()
    duration = int((clock() - started) * 1000)
    out = bytes(output)
    return {"kind": "success", "process_count": 1, "exit_code": proc.returncode,
            "duration_ms": duration, "output_hash": _digest(out), "event_count": len(out.splitlines())}


def transient_carrier(payload: bytes) -> tuple[int, Path]:
    """Create a 0600 one-attempt carrier; callers must unlink it after observation."""
    fd, name = tempfile.mkstemp(prefix="artifex-p3-", text=False)
    os.fchmod(fd, 0o600)
    os.write(fd, payload)
    os.lseek(fd, 0, os.SEEK_SET)
    return fd, Path(name)
