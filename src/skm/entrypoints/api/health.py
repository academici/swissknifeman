"""Read-only schema admission and minimal unauthenticated health responses."""

from collections.abc import Callable
from threading import Lock

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from skm.application_bus.platform.migrations import SchemaVersionReader
from skm.bootstrap.composition import App
from skm.bootstrap.platform_module import MigrationRunner
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemClock, SystemMonotonic

__all__ = ["Health", "read_schema_error", "runner_schema_error"]


def runner_schema_error(runner: MigrationRunner) -> ErrorCode | None:
    states = {state.value for _, _, state in runner.status()}
    if "unknown" in states:
        return ErrorCode.SCHEMA_TOO_NEW
    if "pending" in states:
        return ErrorCode.SCHEMA_NOT_MIGRATED
    if "modified" in states:
        return ErrorCode.MIGRATION_CHECKSUM_MISMATCH
    return _baseline_error(runner.check_baseline)


def read_schema_error(app: App) -> ErrorCode | None:
    meta = RequestMeta("api-schema-status", Surface.API, None, SystemClock().now())
    with app.uow_factory(meta, readonly=True) as uow:
        reader = uow.repo(SchemaVersionReader)
        packaged, applied = tuple(reader.packaged()), tuple(reader.applied())
        known = max((row.version for row in packaged), default=0)
        newest = max((row.version for row in applied), default=0)
        if newest > known:
            return ErrorCode.SCHEMA_TOO_NEW
        if not applied or newest < known:
            return ErrorCode.SCHEMA_NOT_MIGRATED
        history = {row.version: (row.name, row.checksum) for row in applied}
        if any(row.version not in history for row in packaged):
            return ErrorCode.SCHEMA_NOT_MIGRATED
        if any((row.name, row.checksum) != history[row.version] for row in packaged):
            return ErrorCode.MIGRATION_CHECKSUM_MISMATCH
        return _baseline_error(reader.check_baseline)


def _baseline_error(check: Callable[[], None]) -> ErrorCode | None:
    try:
        check()
    except SkmError as error:
        if error.code is ErrorCode.MIGRATION_CHECKSUM_MISMATCH:
            return error.code
        raise
    return None


class Health:
    def __init__(self, check: Callable[[], ErrorCode | None], interval: float = 30) -> None:
        self.check, self.interval = check, interval
        self.schema_error: ErrorCode | None = None
        self.database_ok = True
        self.background_ok = True
        self.background_enabled = True
        self._clock = SystemMonotonic()
        self._last = float("-inf")
        self._lock = Lock()
        self.on_incompatible: Callable[[], None] | None = None
        self.update()

    def update(self) -> None:
        with self._lock:
            now = self._clock.monotonic()
            if now - self._last < self.interval:
                return
            try:
                self.schema_error = self.check()
                self.database_ok = True
            except Exception as error:  # noqa: BLE001 -- readiness must survive unexpected probe failures
                if isinstance(error, SkmError) and error.code in {
                    ErrorCode.SCHEMA_NOT_MIGRATED,
                    ErrorCode.SCHEMA_TOO_NEW,
                }:
                    self.schema_error = error.code
                    self.database_ok = True
                else:
                    self.database_ok = False
                    get_logger("entrypoints.api.health").error("api.health.check_failed", exc=error)
            self._last = now
            if self.schema_error is not None and self.on_incompatible is not None:
                self.on_incompatible()

    async def refresh(self) -> None:
        if self._clock.monotonic() - self._last < self.interval:
            return
        await run_in_threadpool(self.update)

    async def live(self, request: Request) -> JSONResponse:
        del request
        return JSONResponse({"status": "live"})

    async def ready(self, request: Request) -> JSONResponse:
        del request
        await self.refresh()
        schema = (
            "ok"
            if self.schema_error is None
            else {
                ErrorCode.SCHEMA_NOT_MIGRATED: "not_migrated",
                ErrorCode.SCHEMA_TOO_NEW: "too_new",
            }.get(self.schema_error, "invalid")
        )
        ok = self.database_ok and self.schema_error is None and self.background_ok
        return JSONResponse(
            {
                "status": "ready" if ok else "not_ready",
                "checks": {
                    "database": "ok" if self.database_ok else "fail",
                    "schema": schema,
                    "background": "ok" if self.background_ok else "fail",
                },
            },
            status_code=200 if ok else 503,
            headers={} if self.background_enabled else {"SKM-Background": "disabled"},
        )
