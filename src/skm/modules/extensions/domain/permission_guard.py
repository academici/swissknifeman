"""A profile asks for permissions, it never grants them (extensions §4.6 rule 4, ADR 0015).

Pure: the comparator comes from the application layer (``policy.public.is_subset``), so this domain imports no
other module. An empty result means the request stays inside the ceiling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from skm.kernel.json_types import JsonValue
    from skm.modules.extensions.domain.agent_profile import AgentPermissions

__all__ = ["permission_request", "widens_permissions"]


def permission_request(permissions: AgentPermissions) -> dict[str, JsonValue]:
    """The ``urn:skm:policy:permission-request:v1`` document of a profile's layer. ``profile_id`` only names
    the policy profile: what that profile permits is a separate request (``application.permission_proof``)."""
    return {"profile_id": permissions.policy_profile, **dict(permissions.layer or {})}


def widens_permissions[C, V](
    requested: Mapping[str, JsonValue],
    ceiling: C,
    *,
    is_subset: Callable[[Mapping[str, JsonValue], C], tuple[V, ...]],
) -> tuple[V, ...]:
    return tuple(is_subset(requested, ceiling))
