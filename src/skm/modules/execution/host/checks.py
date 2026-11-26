"""Host-side contract of one check run: its request, dependencies and result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from skm.kernel.cancel import CancelToken
    from skm.kernel.clock import Clock, Monotonic
    from skm.modules.execution.domain.ids import CheckExecutionId
    from skm.modules.execution.host.environment import PreparedEnvironment
    from skm.modules.execution.host.evidence import BlobUploader
    from skm.modules.execution.host.isolation import IsolationSpec
    from skm.platform.logging.logger import StructLogger


@dataclass(frozen=True, slots=True)
class CheckRequest:
    check_execution_id: CheckExecutionId
    definition: JsonObject
    cwd: Path
    env_allow: Mapping[str, str]
    timeout_seconds: int
    idle_timeout_seconds: int
    isolation: IsolationSpec
    output_limits: JsonObject


@dataclass(frozen=True, slots=True)
class CheckDeps:
    environment: PreparedEnvironment
    uploader: BlobUploader
    clock: Clock
    monotonic: Monotonic
    log: StructLogger
    cancel: CancelToken


@dataclass(frozen=True, slots=True)
class CheckResult:
    exit_code: int | None
    timed_out: bool
    spawn_error: str | None
    interrupted: bool
    stdout_path: Path
    stderr_path: Path
    report_files: tuple[Path, ...]
    duration_seconds: float
