"""``SIGTERM`` runs a command's cleanup like Ctrl-C does and exits 143 (backup/restore scenario)."""

import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from skm.entrypoints.cli.errors import EXIT_TERMINATED, sigterm_unwinds

_DRIVER = textwrap.dedent(
    """
    import shutil, sys, time
    from pathlib import Path
    from skm.entrypoints.cli.commands import CommandGroup
    from functools import partial
    from skm.entrypoints.cli import main as cli

    work = Path(sys.argv[1])

    def run(args, ctx):
        partial = work / "partial-archive"
        partial.mkdir()  # like create_backup: the output exists from here on
        (work / "ready").write_text("1")
        try:
            time.sleep(30)
        except BaseException:
            shutil.rmtree(partial)  # the cleanup under test
            raise
        return 0

    def register(sub):
        sub.add_parser("slow").set_defaults(run=run, command_name="test.slow")

    group = CommandGroup(name="slow", help="fixture", register=register, requires_backend=False)
    cli.main = partial(cli.main, ["slow"], environ={}, groups=[group])
    sys.exit(cli.console_main())
    """
)


def _run_and_terminate(tmp_path: Path) -> int:
    process = subprocess.Popen(  # noqa: TID251 - deliver a real SIGTERM to a fixture process
        [sys.executable, "-c", _DRIVER, str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "ready").exists():
            assert process.poll() is None, "the command exited before it started"
            assert time.monotonic() < deadline, "the command never started"
            time.sleep(0.02)
        process.send_signal(signal.SIGTERM)
        return process.wait(timeout=20)
    finally:
        if process.poll() is None:
            process.kill()


def test_sigterm_removes_the_partial_output_and_exits_143(tmp_path: Path) -> None:
    # Before: the default SIGTERM action ended the process (-15) and left partial-archive behind.
    assert _run_and_terminate(tmp_path) == EXIT_TERMINATED == 143
    assert not (tmp_path / "partial-archive").exists()


def test_an_existing_sigterm_handler_is_left_alone() -> None:
    def mine(_signum: int, _frame: object) -> None:  # pragma: no cover - never fires here
        raise AssertionError

    previous = signal.signal(signal.SIGTERM, mine)
    try:
        with sigterm_unwinds():
            assert signal.getsignal(signal.SIGTERM) is mine
        assert signal.getsignal(signal.SIGTERM) is mine
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_the_default_action_is_restored_afterwards() -> None:
    previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        with sigterm_unwinds():
            assert signal.getsignal(signal.SIGTERM) not in (signal.SIG_DFL, signal.SIG_IGN)
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    finally:
        signal.signal(signal.SIGTERM, previous)


@pytest.mark.parametrize("ignored", [signal.SIG_IGN])
def test_an_ignored_sigterm_stays_ignored(ignored: signal.Handlers) -> None:
    previous = signal.signal(signal.SIGTERM, ignored)
    try:
        with sigterm_unwinds():
            assert signal.getsignal(signal.SIGTERM) is ignored
    finally:
        signal.signal(signal.SIGTERM, previous)
