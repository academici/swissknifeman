"""Unit tests for ``RuntimeInstallation`` and ``diff_installations`` (runtimes §6, §7.1, §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from skm.kernel.ids import HostId
from skm.modules.runtimes.domain.installation import (
    AuthState,
    InstallationDiff,
    RuntimeInstallation,
    diff_installations,
)

HOST_A = HostId(UUID("0193a6f0-0100-7a00-8000-9a8b7c6d5e4f"))
HOST_B = HostId(UUID("0193a6f0-0200-7a00-8000-9a8b7c6d5e4f"))
T0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=15)


def make_inst(
    runtime_id: str = "claude_code",
    *,
    host_id: HostId = HOST_A,
    version: str | None = "2.1.266",
    binary_locator: str | None = "/usr/local/bin/claude",
    auth_state: AuthState = AuthState.OK,
    detected_at: datetime = T0,
    details: dict[str, str] | None = None,
) -> RuntimeInstallation:
    return RuntimeInstallation(
        host_id=host_id,
        runtime_id=runtime_id,
        version=version,
        binary_locator=binary_locator,
        auth_state=auth_state,
        detected_at=detected_at,
        details=details or {},
    )


def test_installation_validates_invariants_and_freezes_details() -> None:
    raw_details = {"channel": "stable", "arch": "x86_64"}
    inst = make_inst(details=raw_details)
    raw_details["channel"] = "mutated"
    assert dict(inst.details) == {"channel": "stable", "arch": "x86_64"}
    with pytest.raises(TypeError):
        inst.details["extra"] = "nope"  # type: ignore[index]

    with pytest.raises(ValueError, match="not a runtime id"):
        make_inst(runtime_id="Invalid-Runtime!")

    with pytest.raises(ValueError, match="version"):
        make_inst(version="")

    with pytest.raises(ValueError, match="version"):
        make_inst(version="x" * 101)

    with pytest.raises(ValueError, match="binary_locator"):
        make_inst(binary_locator="")

    with pytest.raises(ValueError, match="binary_locator"):
        make_inst(binary_locator="x" * 4097)

    with pytest.raises(ValueError, match="UTC"):
        make_inst(detected_at=datetime(2026, 11, 1, 10, 0, 0))  # noqa: DTZ001 - testing naive datetime rejection

    with pytest.raises(ValueError, match="UTC"):
        make_inst(detected_at=datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone(timedelta(hours=3))))

    with pytest.raises(ValueError, match="detail key"):
        make_inst(details={"": "v"})

    with pytest.raises(ValueError, match="detail value"):
        make_inst(details={"k": "v" * 501})


def test_diff_installations_unchanged_when_only_detected_at_advances() -> None:
    current = (
        make_inst("claude_code", version="2.1.266", detected_at=T0, details={"tier": "pro"}),
        make_inst("codex", version="0.48.0", detected_at=T0),
    )
    observed = (
        make_inst("claude_code", version="2.1.266", detected_at=T1, details={"tier": "pro"}),
        make_inst("codex", version="0.48.0", detected_at=T1),
    )
    diff = diff_installations(current, observed)
    assert diff == InstallationDiff(upserted=(), unchanged=current, removed=())
    assert diff.has_changes is False


def test_diff_installations_detects_added_updated_and_removed_runtimes() -> None:
    claude_old = make_inst("claude_code", version="2.1.260", auth_state=AuthState.OK, detected_at=T0)
    codex_same = make_inst("codex", version="0.48.0", auth_state=AuthState.OK, detected_at=T0)
    grok_old = make_inst("grok", version="1.0.0", auth_state=AuthState.EXPIRED, detected_at=T0)

    claude_new = make_inst("claude_code", version="2.1.266", auth_state=AuthState.OK, detected_at=T1)
    codex_obs = make_inst("codex", version="0.48.0", auth_state=AuthState.OK, detected_at=T1)
    cursor_new = make_inst("cursor", version="2026.09.15", auth_state=AuthState.MISSING, detected_at=T1)

    diff = diff_installations((claude_old, codex_same, grok_old), (claude_new, codex_obs, cursor_new))
    assert diff.has_changes is True
    assert diff.upserted == (claude_new, cursor_new)
    assert diff.unchanged == (codex_same,)
    assert diff.removed == ("grok",)


def test_diff_installations_detects_auth_or_detail_mutation() -> None:
    old = make_inst("codex", auth_state=AuthState.OK, details={"org": "alpha"}, detected_at=T0)
    expired = make_inst("codex", auth_state=AuthState.EXPIRED, details={"org": "alpha"}, detected_at=T1)
    assert diff_installations((old,), (expired,)).upserted == (expired,)

    reconfigured = make_inst("codex", auth_state=AuthState.OK, details={"org": "beta"}, detected_at=T1)
    assert diff_installations((old,), (reconfigured,)).upserted == (reconfigured,)


def test_diff_installations_rejects_mixed_hosts_and_duplicates() -> None:
    a = make_inst("claude_code", host_id=HOST_A)
    b = make_inst("codex", host_id=HOST_B)
    with pytest.raises(ValueError, match="multiple hosts"):
        diff_installations((a,), (b,))

    dup = make_inst("claude_code", host_id=HOST_A, detected_at=T1)
    with pytest.raises(ValueError, match="duplicate current"):
        diff_installations((a, dup), ())
    with pytest.raises(ValueError, match="duplicate observed"):
        diff_installations((), (a, dup))
