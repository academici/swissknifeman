"""TR reproduction through the check gateway: bounded capture, DEVNULL and owned cleanup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID, uuid5

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.ids import CheckExecutionId
from skm.modules.execution.host.checks import CheckDeps, CheckRequest, CheckResult
from skm.modules.execution.host.evidence import EvidenceFile
from skm.modules.execution.host.isolation import IsolationSpec
from skm.modules.execution.host.stages.base import CleanupUnconfirmed

if TYPE_CHECKING:
    from skm.modules.execution.host.stages.base import StageRequest

__all__ = ["run_reproduction"]


def run_reproduction(
    request: StageRequest,
    deps: CheckDeps | None,
    reproduction: JsonObject,
    *,
    run_check: Callable[[CheckRequest, CheckDeps], CheckResult],
    timeout_seconds: object = None,
    finding_id: str,
    remaining_seconds: int | None,
) -> tuple[JsonObject, tuple[EvidenceFile, ...]]:
    """Request a read-only boundary; an unavailable boundary never authorizes rejection.

    The check gateway owns sanitization, stdin=/dev/null, shared capture quota,
    mandatory wrapping and terminate_group. Soft warnings never enter its timeout.
    """
    agent = request.runtime_request
    unavailable: JsonObject = {"verified": False}
    if agent is None or deps is None or deps.cancel.cancelled:
        return unavailable, ()
    environment = deps.environment
    timeout = timeout_seconds if type(timeout_seconds) is int else 300
    if remaining_seconds is not None:
        timeout = min(timeout, remaining_seconds)
    if timeout <= 0:
        return {**unavailable, "timed_out": True}, ()
    check_id = CheckExecutionId(uuid5(UUID(str(request.begin["stage_record_id"])), finding_id))
    owner = replace(agent.process_owner, unit_kind="check", unit_id=check_id)
    cwd = next((root for root in environment.mounts.values() if str(root) == agent.workdir), None)
    if cwd is None:
        return unavailable, ()
    spec = IsolationSpec(
        cwd,
        tuple(environment.mounts.values()),
        (),
        tuple(environment.mounts.values()),
        True,
        "none",
        (),
        {},
        None,
        (),
        owner,
    )
    check = CheckRequest(
        check_id,
        {"argv": reproduction.get("argv")},
        cwd,
        {},
        timeout,
        0,
        spec,
        {"capture_max_bytes": 1024 * 1024},
    )
    try:
        deps.cancel.raise_if_cancelled()
        facts = run_check(check, deps)
    except SkmError as error:
        if error.code is ErrorCode.CHECKOUT_BUSY:
            raise CleanupUnconfirmed("reproduction environment requires reconciliation") from error
        return unavailable, ()
    except OSError as error:
        raise CleanupUnconfirmed("reproduction IO failed; retain ownership for reconciliation") from error
    except (ValueError, KeyError):
        return unavailable, ()
    if facts.interrupted:
        raise CleanupUnconfirmed("reproduction containment did not confirm an uninterrupted reap")
    files = tuple(
        EvidenceFile(path, f"step:{agent.request_id}", "log", f"repro-{finding_id}-{name}.txt", "text/plain")
        for name, path in (("stdout", facts.stdout_path), ("stderr", facts.stderr_path))
    )
    return {
        "verified": facts.exit_code is not None
        and not facts.spawn_error
        and not facts.interrupted
        and not facts.timed_out,
        "exit_code": facts.exit_code,
        "timed_out": facts.timed_out,
        "spawn_error": facts.spawn_error,
        "interrupted": facts.interrupted,
        "duration_seconds": facts.duration_seconds,
    }, files
