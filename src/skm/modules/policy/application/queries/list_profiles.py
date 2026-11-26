"""``policy.list_profiles`` (policy §8): the built-in permission profiles and the custom configured ones."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.policy.application.composition import builtin_profiles
from skm.modules.policy.domain.profiles import PolicyProfile, parse_profile
from skm.modules.policy.generated.queries import ListProfiles
from skm.modules.policy.generated.results import ListProfilesResult
from skm.modules.policy.generated.views import ProfileView

__all__ = ["SPEC", "handle"]


def _view(profile: PolicyProfile, *, builtin: bool) -> ProfileView:
    return ProfileView.from_json(
        {
            "id": profile.id,
            "version": profile.version,
            "description": profile.description,
            "builtin": builtin,
            "requires_host_flag": profile.requires_host_flag,
            "allowed_isolation": sorted(profile.permissions.allowed_isolation),
        }
    )


def handle(query: ListProfiles, ctx: QueryContext, uow: UnitOfWork) -> ListProfilesResult:
    del query, uow
    profiles = [_view(profile, builtin=True) for profile in builtin_profiles().values()]
    custom = ctx.config.get("policy.profiles")
    if isinstance(custom, Mapping):
        for profile_id, document in sorted(cast("Mapping[str, object]", custom).items()):
            if profile_id in builtin_profiles():
                continue  # a custom profile cannot shadow a built-in one (composition refuses it)
            profiles.append(_view(parse_profile(cast("Mapping[str, object]", document)), builtin=False))
    return ListProfilesResult(profiles=tuple(profiles))


SPEC = QuerySpec(
    name="policy.list_profiles",
    dto=ListProfiles,
    result=ListProfilesResult,
    permission="policy.read",
    scope_of=None,
    handler=handle,
)
