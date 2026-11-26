"""``none`` profile: argv unchanged, no confinement (adapters §7). Reachable only with the host flag.

``policy.host.allow_unconfined`` is read by the host, which passes it here; without it the profile is
unavailable and ``wrap`` refuses. The profile proves nothing, so coverage is not assessed: the flag together
with the ``trusted-full-access`` policy profile (``requires_host_flag``) is the explicit consent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar, Protocol, override

from skm.adapters.sandbox.backend import BackendIsolation, Coverage, SpecView, WrappedProcess, unavailable
from skm.modules.execution.ports import Isolation
from skm.modules.policy.domain.render import IsolationProperty

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = ["NoneIsolation", "none_isolation"]


class NoneIsolation(Isolation, Protocol):
    """Technology binding of ``Isolation``; the concrete backend is built by ``none_isolation``."""


class _NoneBackend(BackendIsolation):
    profile: ClassVar[str] = "none"
    confined: ClassVar[bool] = False

    def __init__(self, *, allow_unconfined: bool) -> None:
        super().__init__()
        self._allowed = allow_unconfined

    @override
    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        return {}

    def available(self, host: object) -> JsonObject:  # noqa: ARG002
        if not self._allowed:
            return {"available": False, "reason": "policy.host.allow_unconfined is not set on this host"}
        return {"available": True, "unconfined": True}

    def wrap(self, argv: list[str] | tuple[str, ...], spec: SpecView) -> WrappedProcess:
        if not self._allowed:
            raise unavailable(
                self.profile, "unconfined_not_allowed", "policy.host.allow_unconfined is not set on this host"
            )
        coverage = Coverage(self.profile, frozenset(), {})
        return WrappedProcess(tuple(argv), dict(spec.env), spec.workdir, self.ownership(spec, coverage))


def none_isolation(*, allow_unconfined: bool = False) -> Isolation:
    """The unconfined profile; ``allow_unconfined`` is the host flag, never defaulted on."""
    return _NoneBackend(allow_unconfined=allow_unconfined)  # pyright: ignore[reportReturnType]
