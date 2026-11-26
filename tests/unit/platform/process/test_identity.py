import os
import signal
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from skm.platform.process import identity


def test_current_process_and_reuse_guards() -> None:
    current = identity.identity_of(os.getpid())
    assert current is not None
    assert identity.is_same_process(current)
    if sys.platform == "linux":
        assert current.start_ticks is not None
        assert current.boot_id
        assert not identity.is_same_process(replace(current, start_ticks=current.start_ticks + 1))
        assert not identity.is_same_process(replace(current, boot_id="other-boot"))
        assert not identity.is_same_process(replace(current, start_ticks=None, boot_id=None))


def _proc_stat(state: str = "S", group: int = 42, ticks: int = 123) -> bytes:
    fields = [state, "1", str(group)] + ["0"] * 16 + [str(ticks)]
    return b"42 (odd \xff\xfe) process\nname) " + " ".join(fields).encode("ascii")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux proc stat contract")
def test_proc_stat_field_22_and_zombies(monkeypatch: pytest.MonkeyPatch) -> None:
    state = "S"

    def read(pid: int) -> bytes:
        return _proc_stat(state)

    monkeypatch.setattr(identity, "_read_stat_raw", read)
    monkeypatch.setattr(Path, "read_text", lambda self: "boot\n")
    expected = identity.ProcessIdentity(42, 123, "boot")
    assert identity.identity_of(42) == expected
    assert identity.is_same_process(expected)
    for dead in ("Z", "X"):
        state = dead
        assert not identity.is_same_process(expected)


def test_missing_and_denied_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> str:
        raise ProcessLookupError

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", missing)
        patch.setattr(identity, "_read_stat_raw", missing)
        patch.setattr(os, "kill", missing)
        assert identity.identity_of(12345) is None

    def denied(*args: object, **kwargs: object) -> str:
        raise PermissionError("unobservable")

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(identity, "_read_stat_raw", denied)
    monkeypatch.setattr(os, "kill", denied)
    with pytest.raises(PermissionError):
        identity.is_same_process(identity.ProcessIdentity(12345, 1, "boot"))


@pytest.mark.parametrize("pid", [-1, 0, True])
def test_invalid_ids_never_address_a_broad_group(pid: int) -> None:
    with pytest.raises(ValueError, match="pid"):
        identity.identity_of(pid)
    with pytest.raises(ValueError, match="pgid"):
        identity.kill_group(pid, signal.SIGKILL)


def test_kill_group_ignores_only_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    def absent(pgid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", absent)
    identity.kill_group(42, signal.SIGTERM)

    def denied(pgid: int, sig: int) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "killpg", denied)
    with pytest.raises(PermissionError):
        identity.kill_group(42, signal.SIGTERM)


def test_macos_identity_is_deliberately_weak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert identity.identity_of(os.getpid()) == identity.ProcessIdentity(os.getpid(), None, None)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux group scan")
def test_group_scan_checks_descendants_and_ignores_zombies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "_proc_pids", lambda: ["1", "2"])
    states = {1: _proc_stat("Z"), 2: _proc_stat("S")}
    monkeypatch.setattr(identity, "_read_stat_raw", lambda pid: states[pid])
    assert identity.group_alive(42)
    assert not identity.group_alive(99)
    states[2] = _proc_stat("X")
    assert not identity.group_alive(42)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux group scan")
def test_group_scan_permission_failure_is_not_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(identity, "_proc_pids", lambda: ["1"])

    def denied(pid: int) -> bytes:
        raise PermissionError("no stat")

    monkeypatch.setattr(identity, "_read_stat_raw", denied)
    with pytest.raises(PermissionError):
        identity.group_alive(42)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux identity sources")
@pytest.mark.parametrize(
    "raw",
    [
        b"malformed",
        b"42 (name) S 0",
        _proc_stat().replace(b"123", b"bad"),
        _proc_stat().replace(b") S ", b") \xff "),
    ],
)
def test_malformed_stat_is_observation_failure(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> None:
    monkeypatch.setattr(identity, "_read_stat_raw", lambda pid: raw)
    with pytest.raises(OSError, match="malformed process identity"):
        identity.identity_of(42)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux boot identity")
def test_missing_boot_id_does_not_claim_process_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    def read(self: Path) -> str:
        raise FileNotFoundError

    monkeypatch.setattr(identity, "_read_stat_raw", lambda pid: _proc_stat())
    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(OSError, match="boot identity unavailable"):
        identity.identity_of(42)
