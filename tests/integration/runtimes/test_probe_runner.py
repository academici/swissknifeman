"""The default CLI probe runner: answered probes return at once, hung ones time out (runtimes §4)."""

import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

from skm.adapters.runtimes._cli_session import probe
from skm.adapters.runtimes._cli_session.probe import default_probe_runner
from skm.platform.process.ownership import OwnershipUnavailable


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-cli"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _env() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}


def test_a_helper_left_holding_the_output_does_not_hold_the_probe(tmp_path: Path) -> None:
    try:
        probe.require_support()
    except OwnershipUnavailable as exc:
        pytest.skip(str(exc))
    # Node-based CLIs fork update checkers that inherit stdout; the CLI itself answered and exited.
    cli = _script(tmp_path, "sleep 3 &\nprintf 'fake-cli 1.2.3\\r\\n'\nexit 0\n")
    started = time.monotonic()
    output = default_probe_runner((cli, "--version"), env=_env(), timeout_seconds=5.0)
    assert time.monotonic() - started < 2.5
    assert (output.returncode, output.stdout, output.stderr) == (0, "fake-cli 1.2.3\n", "")


def test_output_that_is_not_utf8_is_replaced_not_raised(tmp_path: Path) -> None:
    cli = _script(tmp_path, "printf 'v\\377 1.0\\n'; printf 'warn\\376\\n' >&2; exit 3\n")
    output = default_probe_runner((cli,), env=_env(), timeout_seconds=5.0)
    assert (output.returncode, output.stdout, output.stderr) == (3, "v\ufffd 1.0\n", "warn\ufffd\n")


def test_a_cli_that_never_answers_times_out() -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        default_probe_runner(("sleep", "30"), env=_env(), timeout_seconds=0.5)


def test_an_inventory_probe_can_run_without_pidfd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported() -> None:
        raise OwnershipUnavailable("no pidfd")

    monkeypatch.setattr(probe, "require_support", unsupported)
    cli = _script(tmp_path, "read -r input && exit 9\nprintf '%s\\377\\r\\n' \"$PROBE_VERSION\"\nexit 3\n")
    output = default_probe_runner((cli,), env={"PROBE_VERSION": "1.2.3"}, timeout_seconds=5.0)
    assert (output.returncode, output.stdout, output.stderr) == (3, "1.2.3\ufffd\n", "")


def test_ownership_failure_after_preflight_does_not_repeat_the_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed_start(*_args: object, **_kwargs: object) -> None:
        raise OwnershipUnavailable("child did not bind")

    monkeypatch.setattr(probe, "require_support", lambda: None)
    monkeypatch.setattr(probe, "run", failed_start)
    cli = _script(tmp_path, "printf '1.2.3\\n'\n")
    with pytest.raises(OwnershipUnavailable, match="child did not bind"):
        default_probe_runner((cli,), env=_env(), timeout_seconds=5.0)
