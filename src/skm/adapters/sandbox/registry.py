"""Registry of the built-in isolation profiles (adapters §7).

The registry includes worktree, Landlock and the namespaced Bubblewrap and Seatbelt backends. The host
flag enables unconfined execution. Container registration requires a configured backend from the caller.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from skm.adapters.sandbox.backend import Companion, unavailable
from skm.adapters.sandbox.bubblewrap import BubblewrapSandbox
from skm.adapters.sandbox.landlock import landlock_isolation
from skm.adapters.sandbox.none import none_isolation
from skm.adapters.sandbox.seatbelt import SeatbeltSandbox
from skm.adapters.sandbox.worktree import worktree_isolation
from skm.kernel.isolation import IsolationProfile, is_plugin_isolation_profile

if TYPE_CHECKING:
    from skm.modules.execution.ports import Isolation

__all__ = ["build_isolation_registry"]


class IsolationRegistry:
    """``profiles()``/``get()`` of the built-in profiles plus plugin keys ``<id>:<name>``."""

    def __init__(self, builtin: Mapping[str, Isolation]) -> None:
        self._items: dict[str, Isolation] = {}
        for key, isolation in builtin.items():
            if key not in {item.value for item in IsolationProfile}:
                raise ValueError(f"{key!r} is not a built-in isolation profile")
            self._add(key, isolation)

    def _add(self, key: str, isolation: Isolation) -> None:
        if getattr(isolation, "profile", None) != key:
            raise ValueError(f"isolation registered as {key!r} declares profile {isolation.profile!r}")
        self._items[key] = isolation

    def register_plugin(self, key: str, isolation: Isolation) -> None:
        """A plugin profile; built-in names and collisions are refused, so a plugin cannot shadow ``none``."""
        if not is_plugin_isolation_profile(key):
            raise ValueError(f"plugin isolation key must be '<plugin_id>:<name>', got {key!r}")
        if key in self._items:
            raise ValueError(f"isolation profile {key!r} is already registered")
        self._add(key, isolation)

    def profiles(self) -> frozenset[str]:
        return frozenset(self._items)

    def get(self, profile: str) -> Isolation:
        try:
            return self._items[profile]
        except KeyError:
            raise unavailable(profile, "profile_not_registered", "no such profile on this host") from None


def build_isolation_registry(
    *,
    allow_unconfined: bool = False,
    worktree_companions: Sequence[Companion] = (),
    landlock_companions: Sequence[Companion] = (),
    bubblewrap_companions: Sequence[Companion] = (),
    seatbelt_companions: Sequence[Companion] = (),
    container: Isolation | None = None,
) -> IsolationRegistry:
    """Built-in registry; ``none`` is registered only with the host flag, ``container`` only when constructed
    (settings with a pinned image) by the caller. An unregistered profile is ``SANDBOX_UNAVAILABLE``."""
    items: dict[str, Isolation] = {
        IsolationProfile.WORKTREE.value: worktree_isolation(companions=worktree_companions),
        IsolationProfile.LANDLOCK.value: landlock_isolation(companions=landlock_companions),
    }
    if allow_unconfined:
        items[IsolationProfile.NONE.value] = none_isolation(allow_unconfined=True)
    if container is not None:
        items[IsolationProfile.CONTAINER.value] = container
    registry = IsolationRegistry(items)
    sandbox = BubblewrapSandbox(companions=bubblewrap_companions)
    registry.register_plugin(sandbox.profile, cast("Isolation", sandbox))
    seatbelt = SeatbeltSandbox(companions=seatbelt_companions)
    registry.register_plugin(seatbelt.profile, cast("Isolation", seatbelt))
    return registry
