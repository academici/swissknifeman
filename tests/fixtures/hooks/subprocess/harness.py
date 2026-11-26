"""Real native command invocation and cache preparation shared by hook acceptance tests."""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from time import monotonic, perf_counter, sleep
from typing import TYPE_CHECKING, Any, TextIO

import pytest

from skm.adapters.integrations.hookd import exchange, listen, serve
from skm.bootstrap import hook, hookd
from skm.modules.integrations.host.evaluate_hook import run

if TYPE_CHECKING:
    from skm.application_bus.host import HostContext

TARGETS = ("claude_code", "codex", "cursor", "grok")
ROOT = Path(__file__).resolve().parents[4]
HOOK = Path(sys.executable).parent / "skm-hook"


@contextmanager
def runtime_environment(environ: Mapping[str, str]) -> Iterator[dict[str, str]]:
    # pytest's ancestor directories may be group-writable under umask 0002.
    with tempfile.TemporaryDirectory(prefix="skm-hd-", dir=Path("/tmp").resolve()) as runtime:  # noqa: S108
        yield {**environ, "XDG_RUNTIME_DIR": runtime}


def claude_on_path(environ: dict[str, str]) -> None:
    bin_dir = Path(environ["XDG_RUNTIME_DIR"]) / "bin"
    bin_dir.mkdir(mode=0o700, exist_ok=True)
    executable = bin_dir / "claude"
    executable.write_text('#!/bin/sh\ntest "$1" = --version && printf "%s\\n" "2.1.295 (Claude Code)"\n')
    executable.chmod(0o700)
    environ["PATH"] = os.pathsep.join((str(bin_dir), environ.get("PATH", os.defpath)))


def _require_unix_bind(environ: Mapping[str, str]) -> None:
    probe = Path(environ["XDG_RUNTIME_DIR"]) / "probe.sock"
    with socket.socket(socket.AF_UNIX) as listener:
        try:
            listener.bind(str(probe))
        except PermissionError as error:
            pytest.skip(f"host forbids Unix socket bind: {error}")
    probe.unlink()


def _wait_for_daemon(
    process: subprocess.Popen[bytes],  # noqa: TID251 - subprocess type only
    environ: Mapping[str, str],
    diagnostics: TextIO,
) -> None:
    deadline = monotonic() + 12
    while process.poll() is None and monotonic() < deadline:
        try:
            exchange(environ, b"", timeout=0.25)
        except (FileNotFoundError, ConnectionRefusedError, TimeoutError):
            sleep(0.01)
        else:
            return
    diagnostics.seek(0)
    pytest.fail(f"skm-hookd failed to become ready: {diagnostics.read(4096)}")


@contextmanager
def installed_daemon(
    environ: Mapping[str, str], *, cwd: Path, bootstrap: Path | None = None
) -> Iterator[None]:
    _require_unix_bind(environ)
    argv = [str(HOOK.with_name("skm-hookd")), *(("--bootstrap", str(bootstrap)) if bootstrap else ())]
    with (
        tempfile.TemporaryFile(mode="w+t") as diagnostics,
        subprocess.Popen(  # noqa: TID251 - supervise the installed foreground daemon
            argv, cwd=cwd, env=environ, stdout=subprocess.DEVNULL, stderr=diagnostics
        ) as process,
    ):
        try:
            _wait_for_daemon(process, environ, diagnostics)
            yield
        finally:
            process.terminate()
            try:
                status = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                pytest.fail("skm-hookd did not stop after SIGTERM")
            if status:
                diagnostics.seek(0)
                pytest.fail(f"skm-hookd exited with {status}: {diagnostics.read(4096)}")


@contextmanager
def memory_daemon(
    environ: Mapping[str, str],
    context: HostContext,
    monkeypatch: pytest.MonkeyPatch,
    *,
    bootstrap: Path | None = None,
) -> Iterator[None]:
    """Run production socket and evaluation code against the fixture's in-memory bus."""
    _require_unix_bind(environ)

    @contextmanager
    def context_factory(
        daemon_env: Mapping[str, str], bootstrap_path: str | None, **_options: object
    ) -> Iterator[HostContext]:
        if bootstrap_path is not None:
            hook.hook_bootstrap(daemon_env, bootstrap_path)
        yield context

    def reply(data: bytes) -> bytes:
        return hookd._reply(data, environ, str(bootstrap) if bootstrap else None)

    with monkeypatch.context() as patch, listen(environ) as listener:
        patch.setattr(hook, "hook_context", context_factory)
        stopped = Event()
        thread = Thread(target=serve, args=(listener, reply, stopped.is_set))
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(10)
            assert not thread.is_alive()


def native_payload(target: str, event: str, cwd: Path, command: str = "git status") -> dict[str, Any]:
    if target == "grok":
        return {
            "hookEventName": event,
            "sessionId": "startup-test",
            "cwd": str(cwd),
            "source": "startup",
            "toolName": "Bash",
            "toolInput": {"command": command},
        }
    return {
        "hook_event_name": event,
        "session_id": "startup-test",
        "conversation_id": "startup-test",
        "cwd": str(cwd),
        "source": "startup",
        "model": "test",
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "command": command,
        "status": "success",
        "exit_code": 0,
        "duration": 0,
        "sandbox": False,
    }


def child_environment(state: Path, home: Path) -> dict[str, str]:
    return {
        **{key: value for key, value in os.environ.items() if not key.startswith("SKM_")},
        "PATH": str(HOOK.parent) + os.pathsep + os.environ.get("PATH", ""),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "SKM_STATE_DIR": str(state),
        "SKM_DATABASE_URL": "postgresql://skm:unused@127.0.0.1:1/missing?connect_timeout=1",
    }


@dataclass
class Invocation:
    argv: list[str]
    payload: dict[str, Any]
    environ: dict[str, str]
    cwd: Path

    def execute(
        self, *, importtime: bool = False, executable: Path = HOOK
    ) -> tuple[subprocess.CompletedProcess[str], float]:
        assert executable.is_file(), "uv sync --frozen must install skm-hook"
        assert self.argv[0] == "skm-hook"
        argv = [str(executable), *self.argv[1:]]
        if importtime:
            argv = [str(executable.with_name("python")), "-X", "importtime", *argv]
        start = perf_counter()
        result = subprocess.run(
            argv,
            input=json.dumps(self.payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
            env=self.environ,
            cwd=self.cwd,
        )
        return result, (perf_counter() - start) * 1000


def native_invocation(
    env: Any, target: str, *, surface: str = "lifecycle.git_guardrails", command: str = "git status"
) -> Invocation:
    event = "beforeShellExecution" if target == "cursor" else "PreToolUse"
    return Invocation(
        ["skm-hook", event, "--target", target, "--surface", surface, "--project", str(env.project_id)],
        native_payload(target, event, env.checkout_dir, command),
        child_environment(env.state_dir, env.checkout_dir.parent / "child-home"),
        env.checkout_dir,
    )


def cached_invocation(env: Any, target: str) -> Invocation:
    """Exercise the policy cache through a nonblocking surface."""
    invocation = native_invocation(env, target, surface="lifecycle.command_log")
    result = run(
        env.ctx,
        {
            "target": target,
            "surface": "lifecycle.command_log",
            "project_id": str(env.project_id),
            "event_name": invocation.argv[1],
            "payload": invocation.payload,
        },
    )
    assert result["verdict"] == "none", result
    assert result.get("reason_code") is None, result
    (env.state_dir / "host.json").write_text(json.dumps({"host_id": str(env.ctx.host_id)}))
    # An observation invocation must stay independent of both the daemon and the current login.
    invocation.environ.pop("XDG_RUNTIME_DIR", None)
    return invocation


def commands(document: Any) -> list[list[str]]:
    """Read registrations from native JSON, including Cursor's ungrouped shape."""
    found: list[list[str]] = []
    if isinstance(document, dict):
        command = document.get("command")
        if isinstance(command, str) and command.startswith("skm-hook "):
            found.append(shlex.split(command))
        for value in document.values():
            found.extend(commands(value))
    elif isinstance(document, list):
        for item in document:
            found.extend(commands(item))
    return found
