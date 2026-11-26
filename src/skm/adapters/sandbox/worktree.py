"""``worktree`` profile: cwd and client permissions plus the later fence (adapters §7).

On its own it restricts no host read, write, network or process: the fence only detects changes afterwards. It
therefore proves nothing; a request is admitted only when ``companions`` (a native client sandbox, a
container, a cgroup launcher) return, for this exact request, proofs bound to it that cover every required
property, and the wrapped argv starts with their launchers so the proof is enforced before the spawn. A label,
a name or a free-text evidence string is no proof. Otherwise ``wrap`` refuses before the spawn.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, override

from skm.adapters.sandbox.backend import BackendIsolation, Companion, SpecView, WrappedProcess
from skm.modules.execution.ports import Isolation
from skm.modules.policy.domain.render import IsolationProperty

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = ["WorktreeIsolation", "worktree_isolation"]


class WorktreeIsolation(Isolation, Protocol):
    """Technology binding of ``Isolation``; the concrete backend is built by ``worktree_isolation``."""


class _WorktreeBackend(BackendIsolation):
    profile: ClassVar[str] = "worktree"

    @override
    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        return {}

    def available(self, host: object) -> JsonObject:  # noqa: ARG002
        # technically always present; whether it is enough is decided per request by the coverage check
        return {"available": True, "proves": []}

    def wrap(self, argv: list[str] | tuple[str, ...], spec: SpecView) -> WrappedProcess:
        coverage = self.coverage(spec, argv)
        return WrappedProcess(
            (*coverage.launch, *argv), dict(spec.env), spec.workdir, self.ownership(spec, coverage)
        )


def worktree_isolation(
    *, companions: Sequence[Companion] = (), require: Sequence[IsolationProperty] = ()
) -> Isolation:
    return _WorktreeBackend(companions=companions, require=require)  # pyright: ignore[reportReturnType]
