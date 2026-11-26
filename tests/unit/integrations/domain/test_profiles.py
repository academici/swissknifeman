"""Unit tests for permission profile ordering and resolution (integrations §5.4)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.outcomes import Severity
from skm.modules.integrations.domain.profiles import (
    PROFILE_ORDER,
    PermissionProfile,
    ProfileResolution,
    is_at_most_profile,
    narrow_profile,
    resolve_profile,
)


def test_profile_order_is_strictly_increasing_in_privilege() -> None:
    assert PROFILE_ORDER == (
        PermissionProfile.OBSERVE,
        PermissionProfile.WORKSPACE_CONTAINED,
        PermissionProfile.TRUSTED_FULL_ACCESS,
    )
    assert PermissionProfile.OBSERVE.rank < PermissionProfile.WORKSPACE_CONTAINED.rank
    assert PermissionProfile.WORKSPACE_CONTAINED.rank < PermissionProfile.TRUSTED_FULL_ACCESS.rank


def test_is_at_most_and_narrow_profile() -> None:
    obs = PermissionProfile.OBSERVE
    ws = PermissionProfile.WORKSPACE_CONTAINED
    trusted = PermissionProfile.TRUSTED_FULL_ACCESS

    assert is_at_most_profile(obs, obs) is True
    assert is_at_most_profile(obs, ws) is True
    assert is_at_most_profile(obs, trusted) is True
    assert is_at_most_profile(ws, obs) is False
    assert is_at_most_profile(ws, ws) is True
    assert is_at_most_profile(ws, trusted) is True
    assert is_at_most_profile(trusted, ws) is False
    assert is_at_most_profile(trusted, trusted) is True

    assert narrow_profile(trusted, ws) is ws
    assert narrow_profile(ws, trusted) is ws
    assert narrow_profile(trusted, obs) is obs
    assert narrow_profile(obs, ws) is obs


def test_resolve_profile_trusted_refused_narrows_to_workspace_contained() -> None:
    resolution = resolve_profile(
        PermissionProfile.TRUSTED_FULL_ACCESS,
        host_allows_trusted=False,
    )
    assert resolution.profile is PermissionProfile.WORKSPACE_CONTAINED
    assert len(resolution.diagnostics) == 1
    diag = resolution.diagnostics[0]
    assert diag.code is ErrorCode.INTEGRATION_TRUSTED_REFUSED
    assert diag.severity is Severity.WARNING
    assert diag.details == {
        "requested": "trusted_full_access",
        "effective": "workspace_contained",
    }


@pytest.mark.parametrize(
    ("requested", "host_allows_trusted"),
    [
        (PermissionProfile.OBSERVE, False),
        (PermissionProfile.OBSERVE, True),
        (PermissionProfile.WORKSPACE_CONTAINED, False),
        (PermissionProfile.WORKSPACE_CONTAINED, True),
        (PermissionProfile.TRUSTED_FULL_ACCESS, True),
    ],
)
def test_resolve_profile_permitted_requests_produce_no_diagnostics(
    requested: PermissionProfile,
    host_allows_trusted: bool,
) -> None:
    resolution = resolve_profile(requested, host_allows_trusted=host_allows_trusted)
    assert resolution == ProfileResolution(profile=requested, diagnostics=())


def test_resolve_profile_has_no_auto_detection_and_validates_explicit_inputs() -> None:
    with pytest.raises(TypeError, match="host_allows_trusted"):
        resolve_profile(
            PermissionProfile.WORKSPACE_CONTAINED,
            host_allows_trusted=cast(Any, "yes"),
        )
    with pytest.raises(ValueError, match="auto"):
        resolve_profile(
            cast(PermissionProfile, "auto"),
            host_allows_trusted=True,
        )

    res = resolve_profile(PermissionProfile.OBSERVE, host_allows_trusted=False)
    with pytest.raises(FrozenInstanceError):
        res.profile = PermissionProfile.WORKSPACE_CONTAINED  # type: ignore[misc]
