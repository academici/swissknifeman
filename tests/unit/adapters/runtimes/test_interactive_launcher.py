"""Interactive sessions own an actual child PTY and private restart-safe records."""

import json
import os
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import asdict, replace
from io import StringIO
from pathlib import Path
from stat import S_IMODE
from typing import Any
from uuid import uuid4

import pytest

from skm.adapters.runtimes.interactive import InteractiveLauncher, InteractiveSession, interactive_argv
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound, PreconditionFailed, ValidationFailed
from skm.modules.runtimes.public import SecretStr
from skm.platform.process.identity import identity_of, is_same_process

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="interactive sessions use Linux pidfds")


def _start(launcher: InteractiveLauncher, *argv: str) -> InteractiveSession:
    return launcher.start(
        argv,
        project_id=str(uuid4()),
        runtime="claude_code",
        model="example-model",
        checkout=launcher.root.parent,
        environ=os.environ,
    )


def _wait_file(path: Path) -> None:
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.is_file()


def test_lifecycle_and_cleanup_of_a_runtime_ignoring_graceful_signals(tmp_path: Path) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    assert launcher.list() == ()
    assert not launcher.root.exists()
    script = """
import os, signal, subprocess, sys, time
from pathlib import Path
for sig in (signal.SIGHUP, signal.SIGTERM):
    signal.signal(sig, signal.SIG_IGN)
background = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"], process_group=0
)
Path("runtime.tmp").write_text(f"{os.getpid()} {background.pid}")
Path("runtime.tmp").rename("runtime.pid")
while True:
    time.sleep(1)
"""
    session = _start(launcher, sys.executable, "-c", script)
    try:
        _wait_file(tmp_path / "runtime.pid")
        runtime_pid, job_pid = map(int, (tmp_path / "runtime.pid").read_text().split())
        runtime = identity_of(runtime_pid)
        background = identity_of(job_pid)
        assert runtime is not None
        assert background is not None
        assert is_same_process(runtime)
        assert is_same_process(background)
        replica = InteractiveLauncher(launcher.root)
        assert replica.list() == (session,)
        record = launcher.root / f"{session.session_id}.json"
        folder = launcher.root / session.session_id
        assert S_IMODE(launcher.root.stat().st_mode) == 0o700
        assert S_IMODE(folder.stat().st_mode) == 0o700
        assert S_IMODE(record.stat().st_mode) == 0o600
        assert S_IMODE((folder / "control").stat().st_mode) == 0o600
        assert json.loads(record.read_text()) == asdict(session)
        assert replica.stop(session.session_id) == session
        assert not is_same_process(runtime)
        assert not is_same_process(background)
        assert not is_same_process(session.identity)
        assert list(launcher.root.iterdir()) == []
        with pytest.raises(NotFound):
            replica.stop(session.session_id)
    finally:
        with suppress(NotFound):
            launcher.stop(session.session_id)


def test_normal_exit_and_exec_failure_leave_no_session(tmp_path: Path) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    bad_executable = tmp_path / "bad"
    bad_executable.write_text("#!/missing/interpreter\n")
    bad_executable.chmod(0o700)
    with pytest.raises(PreconditionFailed, match="interactive startup"):
        _start(launcher, str(bad_executable))
    assert list(launcher.root.iterdir()) == []
    gate = tmp_path / "exit"
    script = "import time, pathlib\nwhile not pathlib.Path('exit').exists(): time.sleep(.01)"
    session = _start(launcher, sys.executable, "-c", script)
    try:
        gate.touch()
        deadline = time.monotonic() + 5
        while launcher.list() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert launcher.list() == ()
        assert list(launcher.root.iterdir()) == []
    finally:
        with suppress(NotFound):
            launcher.stop(session.session_id)


def test_spawn_failure_removes_the_copied_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    credentials = '{"access_token":"fixture-only"}'

    def cannot_spawn(_argv: object, **kwargs: Any) -> None:
        home = Path(kwargs["env"]["HOME"])
        assert (home / ".codex" / "auth.json").read_text() == credentials
        raise OSError("synthetic pre-spawn failure")

    monkeypatch.setattr(subprocess, "Popen", cannot_spawn)
    with pytest.raises(PreconditionFailed, match="synthetic pre-spawn failure"):
        launcher.start(
            (sys.executable,),
            project_id=str(uuid4()),
            runtime="codex",
            model="example-model",
            checkout=tmp_path,
            environ={"HOME": str(tmp_path)},
            native_auth=SecretStr(credentials),
        )
    assert list(launcher.root.iterdir()) == []


def test_supervisor_survives_the_starting_process(tmp_path: Path) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    script = """
import os, sys
from pathlib import Path
from skm.adapters.runtimes.interactive import InteractiveLauncher

checkout = Path(sys.argv[1])
session = InteractiveLauncher(checkout / "sessions").start(
    ("/bin/cat",), project_id="example", runtime="codex", model=None, checkout=checkout, environ=os.environ,
)
print(session.session_id)
"""
    caller = subprocess.run(
        (sys.executable, "-I", "-c", script, str(tmp_path)),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    session_id = caller.stdout.strip()
    try:
        (session,) = launcher.list()
        assert session.session_id == session_id
        assert is_same_process(session.identity)
    finally:
        launcher.stop(session_id)


def test_stale_pid_or_boot_cannot_stop_an_unrelated_process(tmp_path: Path) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    launcher.root.mkdir(mode=0o700)
    actual = identity_of(os.getpid())
    assert actual is not None
    assert actual.start_ticks is not None
    assert actual.boot_id is not None
    session = InteractiveSession(
        str(uuid4()),
        str(uuid4()),
        "codex",
        None,
        str(tmp_path),
        actual.pid,
        actual.start_ticks,
        actual.boot_id,
        3,
    )
    root = launcher.root / session.session_id
    record = root.with_suffix(".json")

    for stale in (
        replace(session, start_ticks=session.start_ticks + 1),
        replace(session, boot_id="previous-boot"),
    ):
        root.mkdir(mode=0o700)
        record.write_text(json.dumps(asdict(stale)))
        record.chmod(0o600)
        with pytest.raises(NotFound):
            launcher.stop(session.session_id)
        assert is_same_process(actual)
        assert list(launcher.root.iterdir()) == []

    root.mkdir(mode=0o700)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        record.write_text(json.dumps(asdict(replace(session, owner_fd=fd))))
        record.chmod(0o600)
        with pytest.raises(PreconditionFailed, match="does not own"):
            launcher.stop(session.session_id)
        assert is_same_process(actual)
    finally:
        os.close(fd)


def test_unsafe_directories_records_and_invalid_ids_are_rejected(tmp_path: Path) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    other = tmp_path / "other"
    other.mkdir(mode=0o700)
    launcher.root.symlink_to(other, target_is_directory=True)
    with pytest.raises(PreconditionFailed, match="0700"):
        launcher.list()
    launcher.root.unlink()
    launcher.root.mkdir()
    launcher.root.chmod(0o755)
    with pytest.raises(PreconditionFailed, match="0700"):
        launcher.list()
    launcher.root.chmod(0o700)

    with pytest.raises(ValidationFailed, match="session UUID"):
        launcher.stop("../../etc/passwd")
    session_id = str(uuid4())
    outside = tmp_path / "outside"
    outside.write_text("unchanged")
    record = launcher.root / f"{session_id}.json"
    record.symlink_to(outside)
    with pytest.raises(PreconditionFailed):
        launcher.list()
    assert outside.read_text() == "unchanged"
    record.unlink()
    record.write_text("{}")
    record.chmod(0o644)
    with pytest.raises(PreconditionFailed, match="0600"):
        launcher.list()
    record.chmod(0o600)
    with pytest.raises(PreconditionFailed, match="Invalid session record"):
        launcher.list()


def test_attach_requires_terminal(tmp_path: Path) -> None:
    launcher = InteractiveLauncher(tmp_path / "sessions")
    session = _start(launcher, "/bin/cat")
    try:
        with pytest.raises(PreconditionFailed, match="interactive terminal"):
            launcher.attach(session.session_id, StringIO(), StringIO())
        assert launcher.list() == (session,)
    finally:
        launcher.stop(session.session_id)


def test_interactive_argv_validates_local_binary_and_model(tmp_path: Path) -> None:
    binary = tmp_path / "gemini"
    binary.touch(mode=0o700)
    assert interactive_argv("gemini_cli", "test/model", {}, {"PATH": str(tmp_path)}) == (
        str(binary),
        "--model",
        "test/model",
    )
    assert interactive_argv("gemini_cli", "test", {"gemini_cli": str(binary)}, {})[0] == str(binary)
    with pytest.raises(CapabilityUnavailable) as exc:
        interactive_argv("gemini_cli", "test", {}, {"PATH": "."})
    assert exc.value.code is ErrorCode.RUNTIME_NOT_INSTALLED
    with pytest.raises(CapabilityUnavailable, match="no interactive launcher"):
        interactive_argv("fake", "test", {}, {})
    with pytest.raises(ValidationFailed, match="model"):
        interactive_argv("gemini_cli", "--help", {}, {})
    with pytest.raises(ValidationFailed, match="absolute"):
        interactive_argv("gemini_cli", "test", {"gemini_cli": "./gemini"}, {})
