"""Permission profiles and host-constrained profile resolution (integrations §5.4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.outcomes import Diagnostic, Severity

__all__ = [
    "PROFILE_ORDER",
    "PermissionProfile",
    "ProfileResolution",
    "is_at_most_profile",
    "narrow_profile",
    "resolve_profile",
]


class PermissionProfile(StrEnum):
    OBSERVE = "observe"
    WORKSPACE_CONTAINED = "workspace_contained"
    TRUSTED_FULL_ACCESS = "trusted_full_access"

    @property
    def rank(self) -> int:
        return PROFILE_ORDER.index(self)


PROFILE_ORDER: Final[tuple[PermissionProfile, ...]] = (
    PermissionProfile.OBSERVE,
    PermissionProfile.WORKSPACE_CONTAINED,
    PermissionProfile.TRUSTED_FULL_ACCESS,
)


def is_at_most_profile(candidate: PermissionProfile, ceiling: PermissionProfile) -> bool:
    """Return True if ``candidate`` is no broader than ``ceiling`` in ``PROFILE_ORDER``."""
    return PermissionProfile(candidate).rank <= PermissionProfile(ceiling).rank


def narrow_profile(first: PermissionProfile, second: PermissionProfile) -> PermissionProfile:
    """Return the narrower (more restrictive) of two permission profiles."""
    p1 = PermissionProfile(first)
    p2 = PermissionProfile(second)
    return p1 if p1.rank <= p2.rank else p2


@dataclass(frozen=True, slots=True)
class ProfileResolution:
    profile: PermissionProfile
    diagnostics: tuple[Diagnostic, ...] = ()


def _require_bool(value: object) -> None:
    if not isinstance(value, bool):
        raise TypeError("host_allows_trusted must be a bool")


def resolve_profile(requested: PermissionProfile, *, host_allows_trusted: bool) -> ProfileResolution:
    """Resolve ``requested`` profile strictly from explicit inputs without auto-detection."""
    _require_bool(host_allows_trusted)
    profile = PermissionProfile(requested)
    if profile is PermissionProfile.TRUSTED_FULL_ACCESS and not host_allows_trusted:
        warning = Diagnostic(
            code=ErrorCode.INTEGRATION_TRUSTED_REFUSED,
            message=(
                "trusted_full_access profile is not permitted on this host; narrowed to workspace_contained"
            ),
            severity=Severity.WARNING,
            target="integrations.profile",
            details={
                "requested": PermissionProfile.TRUSTED_FULL_ACCESS.value,
                "effective": PermissionProfile.WORKSPACE_CONTAINED.value,
            },
        )
        return ProfileResolution(
            profile=PermissionProfile.WORKSPACE_CONTAINED,
            diagnostics=(warning,),
        )
    return ProfileResolution(profile=profile, diagnostics=())
