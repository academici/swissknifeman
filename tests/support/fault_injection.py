"""Fault scheduling for test-only port wrappers (testing spec §8).

``faulty_uow_factory`` wraps a ``UnitOfWorkFactory``: ``UOW_BEFORE_COMMIT`` fails before the inner
COMMIT, so the inner unit of work rolls back; ``UOW_AFTER_COMMIT`` fails after it, so the effects are
committed and only the response is lost. Port owners add faulty_blob_store, faulty_client and faulty_vcs
when they need them. Inject them with CompositionOverrides in test builds (or
``TestBackend.app(uow_factory=…)``); the product must never call maybe_fail or read fault environment flags.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, Self, override

from skm.kernel.events import DomainEvent
from skm.kernel.ports_uow import Isolation, OutboxEnqueuer, RequestMeta, UnitOfWork, UnitOfWorkFactory
from skm.modules.execution.host.stages.base import StageOutcome, StageRequest


class FaultPoint(StrEnum):
    UOW_BEFORE_COMMIT = "uow.before_commit"
    UOW_AFTER_COMMIT = "uow.after_commit"
    BLOB_AFTER_STAGE = "blob.after_stage"
    BLOB_AFTER_PROMOTE = "blob.after_promote"
    OUTBOX_AFTER_HANDLER = "outbox.after_handler"
    CLIENT_AFTER_SERVER_COMMIT = "client.after_server_commit"
    VCS_AFTER_PUSH = "vcs.after_push"
    RUNTIME_DURING_STEP = "runtime.during_step"
    WORKER_HEARTBEAT_LOST = "worker.heartbeat_lost"


class InjectedFault(Exception):
    def __init__(self, point: FaultPoint) -> None:
        self.point = point
        super().__init__(f"injected fault: {point.value}")


@dataclass
class FaultPlan:
    points: dict[FaultPoint, int]
    hits: dict[FaultPoint, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.points = dict(self.points)
        self.hits = dict(self.hits)
        for point, occurrence in self.points.items():
            if not isinstance(point, FaultPoint):
                raise ValueError("fault points must be FaultPoint values")
            if type(occurrence) is not int or occurrence < 1:
                raise ValueError("fault occurrence must be a positive integer")
        for point, count in self.hits.items():
            if not isinstance(point, FaultPoint) or type(count) is not int or count < 0:
                raise ValueError("fault hits must be nonnegative integers keyed by FaultPoint")

    def maybe_fail(self, point: FaultPoint) -> None:
        self.hits[point] = self.hits.get(point, 0) + 1
        if self.hits[point] == self.points.get(point):
            raise InjectedFault(point)


class _FaultyUnitOfWork:
    """Delegates to a real unit of work; ``commit`` passes the two UoW fault points around the inner one."""

    def __init__(self, inner: UnitOfWork, plan: FaultPlan) -> None:
        self._inner = inner
        self._plan = plan

    def __enter__(self) -> Self:
        self._inner.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._inner.__exit__(exc_type, exc, tb)

    def repo[R](self, port: type[R]) -> R:
        return self._inner.repo(port)

    def record(self, event: DomainEvent) -> None:
        self._inner.record(event)

    @property
    def outbox(self) -> OutboxEnqueuer:
        return self._inner.outbox

    @property
    def readonly(self) -> bool:
        return self._inner.readonly

    def savepoint(self) -> AbstractContextManager[None]:
        return self._inner.savepoint()

    def commit(self) -> None:
        self._plan.maybe_fail(FaultPoint.UOW_BEFORE_COMMIT)
        self._inner.commit()
        self._plan.maybe_fail(FaultPoint.UOW_AFTER_COMMIT)

    def rollback(self) -> None:
        self._inner.rollback()

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)  # e.g. ``connection`` of the PostgreSQL unit of work


class _FaultyUowFactory:
    def __init__(self, inner: UnitOfWorkFactory, plan: FaultPlan) -> None:
        self._inner = inner
        self._plan = plan

    def __call__(
        self,
        meta: RequestMeta,
        *,
        readonly: bool = False,
        isolation: Isolation = Isolation.READ_COMMITTED,
    ) -> UnitOfWork:
        return _FaultyUnitOfWork(self._inner(meta, readonly=readonly, isolation=isolation), self._plan)


def faulty_uow_factory(inner: UnitOfWorkFactory, plan: FaultPlan) -> UnitOfWorkFactory:
    """Units of work of ``inner`` that fail at ``UOW_BEFORE_COMMIT``/``UOW_AFTER_COMMIT`` as ``plan`` says."""
    return _FaultyUowFactory(inner, plan)


class FaultyClient:
    """Transport boundary: commit on the server, then lose a selected response.

    ``operations`` limits injection to the named DTOs. Heartbeat failures are consecutive
    transport losses before dispatch; other faults happen after the real dispatch.
    """

    def __init__(
        self,
        inner: Any,
        plan: FaultPlan,
        *,
        operations: tuple[str, ...] = (),
        heartbeat_losses: int = 0,
        heartbeat_after_process: bool = False,
        diagnostics: bool = False,
    ) -> None:
        self.inner, self.plan = inner, plan
        self.operations, self.heartbeat_losses = operations, heartbeat_losses
        self.heartbeat_after_process = heartbeat_after_process
        self.diagnostics = diagnostics
        self.calls: list[tuple[object, str | None]] = []

    def dispatch(self, command: Any, *, idempotency_key: str | None = None) -> Any:
        from skm.kernel.error_codes import ErrorCode
        from skm.kernel.errors import BackendUnavailable

        self.calls.append((command, idempotency_key))
        if (
            type(command).__name__ == "RenewLease"
            and self.heartbeat_losses
            and (not self.heartbeat_after_process or command.get("progress", {}).get("process"))
        ):
            self.heartbeat_losses -= 1
            self.plan.hits[FaultPoint.WORKER_HEARTBEAT_LOST] = (
                self.plan.hits.get(FaultPoint.WORKER_HEARTBEAT_LOST, 0) + 1
            )
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "injected heartbeat transport loss")
        try:
            result = self.inner.dispatch(command, idempotency_key=idempotency_key)
        except Exception as error:
            if self.diagnostics:
                import sys
                import traceback

                traceback.print_exc()
                current = error
                while current is not None:
                    details = getattr(current, "details", {})
                    if "issues" in details:
                        print(details["issues"], file=sys.stderr)
                    current = current.__cause__
            raise
        if not self.operations or type(command).__name__ in self.operations:
            self.plan.maybe_fail(FaultPoint.CLIENT_AFTER_SERVER_COMMIT)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class FaultyBlobStore:
    """Delegate every byte to the real store; lose only the stage/promote acknowledgement."""

    def __init__(self, inner: Any, plan: FaultPlan) -> None:
        self.inner, self.plan = inner, plan

    def stage(self, *args: Any, **kwargs: Any) -> Any:
        result = self.inner.stage(*args, **kwargs)
        self.plan.maybe_fail(FaultPoint.BLOB_AFTER_STAGE)
        return result

    def promote(self, *args: Any, **kwargs: Any) -> Any:
        result = self.inner.promote(*args, **kwargs)
        self.plan.maybe_fail(FaultPoint.BLOB_AFTER_PROMOTE)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class StageDiagnostics:
    """Delegate a real stage unchanged while preserving test-only exception diagnostics."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.stage_type: str = inner.stage_type
        self.side: str = inner.side
        self.params_schema_urn: str = inner.params_schema_urn

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def run(self, request: StageRequest, deps: Any) -> StageOutcome:
        import traceback

        try:
            return self.inner.run(request, deps)
        except Exception:
            traceback.print_exc()
            raise


class MissingRuntimeVisibility:
    """Lose stdout/transcript after a real provider call; retain its measured usage."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def result(self, handle: Any) -> Any:
        result = self.inner.result(handle)
        if result.transcript_path is not None:
            Path(result.transcript_path).unlink(missing_ok=True)
        return replace(result, final_text="", structured=None, transcript_path=None, observation=None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def event_fault_factory(inner: UnitOfWorkFactory, event_suffix: str) -> UnitOfWorkFactory:
    """Fail the mandatory event record after a real handler's preceding SQL mutations."""

    class EventFault(_FaultyUnitOfWork):
        @override
        def record(self, event: DomainEvent) -> None:
            self._inner.record(event)
            if event.event_type.endswith(f":{event_suffix}:v1"):
                raise InjectedFault(FaultPoint.UOW_BEFORE_COMMIT)

    def factory(
        meta: RequestMeta, *, readonly: bool = False, isolation: Isolation = Isolation.READ_COMMITTED
    ) -> UnitOfWork:
        return EventFault(inner(meta, readonly=readonly, isolation=isolation), FaultPlan({}))

    return factory
