"""Exercise local socket admission, fail-closed client output, and daemon lifecycle."""

from __future__ import annotations

import argparse
import ctypes
import errno
import io
import json
import os
import pwd
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
from typing import Any

import pytest

from fixtures.hooks.subprocess.harness import runtime_environment
from skm.adapters.integrations import hookd
from skm.bootstrap import hook
from skm.bootstrap import hookd as bootstrap
from skm.platform.config.sources import hookd_runtime

PROJECT = "01900000-0000-7000-8000-000000000001"


@pytest.fixture
def environ(tmp_path: Path) -> Iterator[dict[str, str]]:
    # Keep the pathname short enough for sockaddr_un on platforms without /proc/self/fd.
    with tempfile.TemporaryDirectory(prefix="skm-hd-", dir=Path("/tmp").resolve()) as base:  # noqa: S108
        runtime = Path(base) / "runtime"
        runtime.mkdir(mode=0o700)
        yield {"XDG_RUNTIME_DIR": str(runtime), "PATH": str(tmp_path / "bin")}


@pytest.fixture
def socket_host(environ: dict[str, str]) -> None:
    """Probe host restrictions independently of the product listener."""
    with socket.socket(socket.AF_UNIX) as probe:
        try:
            probe.bind(str(Path(environ["XDG_RUNTIME_DIR"]) / "probe"))
        except PermissionError as error:
            pytest.skip(f"host forbids Unix socket bind: {error}")


@contextmanager
def serving(environ: dict[str, str], evaluate: Callable[[bytes], bytes]) -> Iterator[None]:
    with hookd.listen(environ) as listener:
        stopped = threading.Event()
        thread = threading.Thread(target=hookd.serve, args=(listener, evaluate, stopped.is_set))
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(3)
            assert not thread.is_alive()


@pytest.mark.usefixtures("socket_host")
def test_socket_permissions_peer_credentials_and_concurrent_start(environ: dict[str, str]) -> None:
    folder = hookd_runtime.runtime_dir(environ)
    endpoint = folder / "hookd.sock"
    with serving(environ, lambda payload: payload):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
        assert stat.S_IMODE(endpoint.stat().st_mode) == 0o600
        assert stat.S_ISSOCK(endpoint.lstat().st_mode)
        assert endpoint.stat().st_uid == folder.stat().st_uid == os.geteuid()
        assert hookd.exchange(environ, b"round trip", timeout=1) == b"round trip"
        with pytest.raises(OSError, match="Address already in use") as caught, hookd.listen(environ):
            pytest.fail("second listener started")
        assert caught.value.errno == errno.EADDRINUSE
        assert hookd.exchange(environ, b"still listening", timeout=1) == b"still listening"
    assert not endpoint.exists()


def test_actual_peer_uid() -> None:
    left, right = socket.socketpair()
    with left, right:
        if sys.platform == "linux":
            try:
                left.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            except PermissionError as error:
                pytest.skip(f"host forbids SO_PEERCRED: {error}")
        assert hookd._peer_uid(left) == os.geteuid()


@pytest.mark.parametrize("failure", ["foreign_uid", "unverifiable"])
@pytest.mark.usefixtures("socket_host")
def test_server_rejects_peer_before_evaluation(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    def uid(_peer: socket.socket) -> int:
        if failure == "unverifiable":
            raise OSError("no credentials")
        return os.geteuid() + 1

    monkeypatch.setattr(hookd, "_peer_uid", uid)
    with serving(environ, lambda _: pytest.fail("unauthenticated request reached evaluator")):
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(1)
            peer.connect(str(hookd_runtime.runtime_dir(environ) / "hookd.sock"))
            assert peer.recv(1) == b""
        with pytest.raises(PermissionError, match="peer"):
            hookd.exchange(environ, b"request", timeout=1)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux SO_PEERCRED")
@pytest.mark.parametrize("peer", ["same_uid", "foreign_uid", "missing", "truncated"])
def test_linux_peer_admission_decodes_kernel_credentials(peer: str) -> None:
    def getsockopt(level: int, option: int, size: int) -> bytes:
        assert (level, option, size) == (socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        if peer == "missing":
            raise OSError("credentials unavailable")
        if peer == "truncated":
            return b""
        return struct.pack("=iII", 123, os.geteuid() + (peer == "foreign_uid"), os.getegid())

    connection = SimpleNamespace(getsockopt=getsockopt)
    if peer == "same_uid":
        hookd._authenticate(connection)  # type: ignore[arg-type]
    else:
        with pytest.raises(PermissionError, match="peer"):
            hookd._authenticate(connection)  # type: ignore[arg-type]


@pytest.mark.parametrize("result", ["same_uid", "foreign_uid", "error"])
def test_bsd_getpeereid_admission(monkeypatch: pytest.MonkeyPatch, result: str) -> None:
    def getpeereid(fd: int, uid: Any, _gid: object) -> int:
        assert fd == 42
        if result == "error":
            return -1
        ctypes.cast(uid, ctypes.POINTER(ctypes.c_uint)).contents.value = os.geteuid() + (
            result == "foreign_uid"
        )
        return 0

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(getpeereid=getpeereid))
    connection = SimpleNamespace(fileno=lambda: 42)
    if result == "same_uid":
        hookd._authenticate(connection)  # type: ignore[arg-type]
    else:
        with pytest.raises(PermissionError, match="peer"):
            hookd._authenticate(connection)  # type: ignore[arg-type]


def test_runtime_directory_is_private_at_creation(environ: dict[str, str]) -> None:
    with hookd._open_runtime(environ, create=True) as (path, fd):
        assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o700
        assert os.path.samestat(path.lstat(), os.fstat(fd))


def test_subprocess_runtime_is_admitted_under_group_writable_umask() -> None:
    umask = os.umask(0o002)
    try:
        with runtime_environment({}) as environ, hookd._open_runtime(environ, create=True) as (path, fd):
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
            assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o700
    finally:
        os.umask(umask)


@pytest.mark.usefixtures("socket_host")
def test_secure_fallback_uses_account_home(environ: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    home = Path(environ["XDG_RUNTIME_DIR"])
    account = SimpleNamespace(pw_dir=str(home))
    monkeypatch.setattr(pwd, "getpwuid", lambda _: account)
    env = {"HOME": "/ignored"}
    with serving(env, lambda payload: payload):
        endpoint = home / ".skm-hookd" / "hookd.sock"
        assert stat.S_IMODE(endpoint.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(endpoint.stat().st_mode) == 0o600
        assert hookd.exchange(env, b"fallback", timeout=1) == b"fallback"


@pytest.mark.parametrize("location", ["ancestor", "runtime", "socket"])
def test_symlink_rejected_without_touching_target(
    environ: dict[str, str], tmp_path: Path, location: str
) -> None:
    folder = hookd_runtime.runtime_dir(environ)
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o700)
    if location == "ancestor":
        folder.parent.rmdir()
        folder.parent.symlink_to(victim, target_is_directory=True)
    elif location == "runtime":
        folder.symlink_to(victim, target_is_directory=True)
    else:
        folder.mkdir(mode=0o700)
        (folder / "hookd.sock").symlink_to(victim)
    with (
        pytest.raises(OSError, match=r"Not a directory|Too many levels|Address already in use|not permitted"),
        hookd.listen(environ),
    ):
        pytest.fail("listener followed symlink")
    with pytest.raises(OSError, match=r"Not a directory|Too many levels|endpoint must"):
        hookd.exchange(environ, b"request", timeout=1)
    assert list(victim.iterdir()) == []


def test_rejects_insecure_runtime_permissions(environ: dict[str, str]) -> None:
    folder = hookd_runtime.runtime_dir(environ)
    folder.mkdir()
    folder.chmod(0o755)
    with pytest.raises(PermissionError, match="0700"), hookd.listen(environ):
        pytest.fail("listener accepted public runtime directory")
    assert stat.S_IMODE(folder.stat().st_mode) == 0o755


@pytest.mark.usefixtures("socket_host")
def test_rejects_insecure_socket_permissions(environ: dict[str, str]) -> None:
    folder = hookd_runtime.runtime_dir(environ)
    with hookd.listen(environ):
        (folder / "hookd.sock").chmod(0o666)
        with pytest.raises(PermissionError, match="0600"):
            hookd.exchange(environ, b"request", timeout=1)


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux fd-relative socket paths")
@pytest.mark.usefixtures("socket_host")
def test_directory_swap_during_bind_cannot_redirect_socket(
    environ: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    moved = tmp_path / "moved"
    address = hookd._address

    def swapped(path: Path, fd: int) -> str:
        path.rename(moved)
        path.symlink_to(victim, target_is_directory=True)
        return address(path, fd)

    monkeypatch.setattr(hookd, "_address", swapped)
    with pytest.raises(PermissionError, match="changed"), hookd.listen(environ):
        pytest.fail("listener accepted a swapped directory")
    assert list(victim.iterdir()) == list(moved.iterdir()) == []


@pytest.mark.usefixtures("socket_host")
def test_shutdown_leaves_replacement_entry_intact(environ: dict[str, str]) -> None:
    endpoint = hookd_runtime.runtime_dir(environ) / "hookd.sock"
    with hookd.listen(environ):
        endpoint.rename(endpoint.with_suffix(".previous"))
        endpoint.write_text("replacement")
    assert endpoint.read_text() == "replacement"


def _args(target: str, event: str) -> argparse.Namespace:
    return argparse.Namespace(
        target=target, surface="lifecycle.git_guardrails", project=PROJECT, event_name=event
    )


def _invoke(environ: dict[str, str], target: str, event: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = hook.invoke(_args(target, event), io.StringIO("{}"), stdout, stderr, environ)
    return code, stdout.getvalue(), stderr.getvalue()


def _claude(environ: dict[str, str], monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    folder = Path(environ["PATH"])
    folder.mkdir()
    binary = folder / "claude"
    binary.touch(mode=0o700)

    def probe(argv: list[str], *, cwd: Path, **_options: object) -> SimpleNamespace:
        assert argv == [str(binary), "--version"]
        assert cwd == Path("/")
        return SimpleNamespace(exit_code=0, stdout=(version + "\n").encode())

    monkeypatch.setattr(bootstrap, "run", probe)


@pytest.mark.parametrize(
    ("target", "event", "status", "native_deny"),
    [
        ("claude_code", "PreToolUse", 0, '"permissionDecision": "deny"'),
        ("claude_code", "UserPromptSubmit", 0, '"decision": "block"'),
        ("codex", "PreToolUse", 2, ""),
        ("codex", "PermissionRequest", 0, '"behavior": "deny"'),
        ("cursor", "beforeShellExecution", 0, '"permission": "deny"'),
        ("grok", "PreToolUse", 2, ""),
    ],
)
def test_daemon_down_uses_native_denial(
    environ: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    event: str,
    status: int,
    native_deny: str,
) -> None:
    _claude(environ, monkeypatch, "2.1.295 (Claude Code)")
    code, stdout, stderr = _invoke(environ, target, event)
    assert code == status
    assert "HOOK_BACKEND_UNAVAILABLE" in stdout + stderr
    assert native_deny in stdout if native_deny else stdout == ""


@pytest.mark.parametrize("version", ["2.1.294", "2.1.295-preview", "unknown", None])
def test_claude_below_floor_or_unknown_version_is_refused(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch, version: str | None
) -> None:
    if version is not None:
        _claude(environ, monkeypatch, version)
    monkeypatch.setattr(
        bootstrap, "exchange", lambda *a, **kw: pytest.fail("unsupported Claude reached daemon")
    )
    code, stdout, stderr = _invoke(environ, "claude_code", "PreToolUse")
    assert (code, stdout) == (2, "")
    assert "Claude Code >= 2.1.295 required" in stderr


@pytest.mark.parametrize("version", ["2.1.295", "2.1.300", "2.2.0 (Claude Code)"])
def test_claude_at_or_above_floor_can_use_live_verdict(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    _claude(environ, monkeypatch, version)
    monkeypatch.setattr(bootstrap, "exchange", lambda *a, **kw: _decision())
    assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")


def _counting_claude(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch, versions: list[str]
) -> list[str]:
    """Install a claude whose probe answers ``versions`` in turn; returns the probes that ran."""
    folder = Path(environ["PATH"])
    folder.mkdir()
    (folder / "claude").touch(mode=0o700)
    (Path(environ["XDG_RUNTIME_DIR"]) / "skm").mkdir(mode=0o700)  # what a running daemon provides
    ran: list[str] = []

    def probe(argv: list[str], **_options: object) -> SimpleNamespace:
        ran.append(argv[0])
        return SimpleNamespace(
            exit_code=0, stdout=(versions[min(len(ran), len(versions)) - 1] + "\n").encode()
        )

    monkeypatch.setattr(bootstrap, "run", probe)
    monkeypatch.setattr(bootstrap, "exchange", lambda *a, **kw: _decision())
    return ran


def test_a_proven_claude_is_not_probed_again_within_the_minute(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = _counting_claude(environ, monkeypatch, ["2.1.295"])
    for _ in range(5):
        assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")
    assert len(ran) == 1  # Before: five `claude --version` processes for five hooks.


def test_a_replaced_claude_is_probed_again_and_refused_below_the_floor(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = _counting_claude(environ, monkeypatch, ["2.1.295", "2.1.1"])
    assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")
    binary = Path(environ["PATH"]) / "claude"
    binary.write_text("#!/bin/sh\n# a different build\n", encoding="utf-8")
    code, stdout, stderr = _invoke(environ, "claude_code", "PreToolUse")
    assert (code, stdout) == (2, "")
    assert "Claude Code >= 2.1.295 required" in stderr
    assert len(ran) == 2


def test_a_failed_probe_is_never_remembered(environ: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    ran = _counting_claude(environ, monkeypatch, ["2.1.1", "2.1.1", "2.1.295"])
    assert _invoke(environ, "claude_code", "PreToolUse")[0] == 2
    assert _invoke(environ, "claude_code", "PreToolUse")[0] == 2
    assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")
    assert len(ran) == 3


def test_an_expired_or_untrusted_capability_record_is_ignored(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = _counting_claude(environ, monkeypatch, ["2.1.295"])
    assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")
    path = Path(environ["XDG_RUNTIME_DIR"]) / "skm/claude-capability"
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    old = path.stat().st_mtime - 120
    os.utime(path, (old, old))
    assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")
    assert len(ran) == 2  # the record is older than a minute
    path.chmod(0o644)
    assert _invoke(environ, "claude_code", "PreToolUse") == (0, "", "")
    assert len(ran) == 3  # a record anyone else could have written is not trusted


def _decision(**updates: object) -> bytes:
    return json.dumps(
        {
            "schema": "urn:skm:integrations:host:hook-decision:v1",
            "surface": "lifecycle.git_guardrails",
            "mode": "strict",
            "verdict": "none",
            "reason_code": None,
            "user_message": None,
            "agent_message": None,
            "additional_context": None,
            **updates,
        }
    ).encode()


@pytest.mark.parametrize(
    "reply",
    [
        b"",
        b'{"error":"credential detail"}',
        _decision(error="credential detail"),
        _decision(verdict="bogus"),
        _decision(surface="security.safe_dirs"),
        _decision(mode="warn", reason_code="HOOK_BACKEND_UNAVAILABLE"),
    ],
)
def test_invalid_or_failed_decision_denies_even_when_daemon_is_reachable(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch, reply: bytes
) -> None:
    monkeypatch.setattr(bootstrap, "exchange", lambda *a, **kw: reply)
    code, stdout, stderr = _invoke(environ, "cursor", "beforeShellExecution")
    assert (code, stderr) == (0, "")
    assert json.loads(stdout)["permission"] == "deny"
    assert "credential detail" not in stdout


def test_unblockable_event_is_refused(environ: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap, "exchange", lambda *a, **kw: pytest.fail("unsupported event reached daemon")
    )
    code, stdout, stderr = _invoke(environ, "cursor", "sessionEnd")
    assert (code, stdout) == (2, "")
    assert "HOOK_BLOCKING_UNAVAILABLE" in stderr


def test_transport_deadline_produces_native_deny(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def timed_out(_environ: object, _request: bytes, *, timeout: float) -> bytes:
        assert 0 < timeout <= 0.05
        raise TimeoutError

    environ["SKM__INTEGRATIONS__HOOK__TIMEOUT_MS"] = "50"
    monkeypatch.setattr(bootstrap, "exchange", timed_out)
    code, stdout, stderr = _invoke(environ, "cursor", "beforeShellExecution")
    assert (code, stderr) == (0, "")
    assert json.loads(stdout)["permission"] == "deny"
    assert "HOOK_BACKEND_UNAVAILABLE" in stdout


@pytest.mark.usefixtures("socket_host")
def test_daemon_entrypoint_serves_and_unlinks_socket_on_sigterm(environ: dict[str, str]) -> None:
    endpoint = hookd_runtime.runtime_dir(environ) / "hookd.sock"
    proc = subprocess.Popen(  # noqa: TID251 - deliver SIGTERM to the foreground console process
        [sys.executable, "-m", "skm.entrypoints.hook.daemon"],
        env={**os.environ, **environ},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = monotonic() + 5
        while not endpoint.is_socket() and proc.poll() is None and monotonic() < deadline:
            sleep(0.01)
        assert endpoint.is_socket()
        assert _invoke(environ, "codex", "PreToolUse")[0] == 2
    finally:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
    assert (proc.returncode, stdout, stderr) == (0, b"", b"")
    assert not endpoint.exists()


def test_daemon_call_uses_daemon_bootstrap_and_live_policy(
    environ: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def evaluate(
        args: argparse.Namespace,
        raw: bytes,
        daemon_env: object,
        path: str,
        *,
        live: bool,
        embedded_app: object,
    ) -> dict:
        assert live
        assert embedded_app is None
        assert path == "/daemon/bootstrap.toml"
        assert daemon_env is environ
        assert (args.target, args.project, raw) == ("codex", PROJECT, b"{}")
        return {**json.loads(_decision()), "client_output": {"exit_code": 2}}

    monkeypatch.setattr(bootstrap, "evaluate_native", evaluate)
    monkeypatch.setattr(
        bootstrap, "exchange", lambda env, raw, **kw: bootstrap._reply(raw, env, "/daemon/bootstrap.toml")
    )
    assert _invoke(environ, "codex", "PreToolUse") == (0, "", "")
