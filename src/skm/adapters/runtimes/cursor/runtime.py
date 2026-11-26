"""Cursor ``AgentRuntime`` adapter with detect-only probe and honest unknown capability matrix."""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, override

from skm.adapters.runtimes._cli_session.probe import (
    ProbeCommandRunner,
    default_os_kernel,
    default_probe_runner,
)
from skm.adapters.runtimes._cli_session.runtime import load_static_declarations, version_timeout
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes.domain.capability import (
    Capability,
    RuntimeCapabilities,
    SelfLoadedSource,
    SelfLoadKind,
)
from skm.modules.runtimes.domain.detection import CancellationResult, DetectProbe
from skm.modules.runtimes.domain.ids import RuntimeId
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.request import AgentRequest
from skm.modules.runtimes.domain.result import RuntimeResult
from skm.modules.runtimes.domain.session_events import SessionEvent
from skm.modules.runtimes.ports import AgentRuntime, SessionHandle
from skm.platform.system_clock import SystemClock

from .detect import (
    DEFAULT_CURSOR_BINARY,
    CursorDetector,
    compute_launch_config_digest,
)

if TYPE_CHECKING:
    from skm.kernel.clock import Clock

__all__ = ["CursorRuntime"]

_PACKAGE_DIR: Final = Path(__file__).resolve().parent


class CursorRuntime(AgentRuntime):
    """Detect-only ``AgentRuntime`` adapter for Cursor CLI (headless contract unverified in v1)."""

    runtime_id: RuntimeId = "cursor"

    def __init__(
        self,
        *,
        binary: str | None = None,
        environ: Mapping[str, str] | None = None,
        probe_runner: ProbeCommandRunner = default_probe_runner,
        os_kernel_fn: Callable[[], str] = default_os_kernel,
        clock: Clock | None = None,
    ) -> None:
        static_caps, rules = load_static_declarations(_PACKAGE_DIR)
        self._static_caps = static_caps
        self._error_rules = rules
        self._binary = binary
        self._environ: Mapping[str, str] = dict(environ) if environ is not None else {}
        self._detector = CursorDetector(run_cmd=probe_runner, os_kernel_fn=os_kernel_fn)
        self._clock = clock if clock is not None else SystemClock()

    @property
    def launch_config_digest(self) -> str:
        return compute_launch_config_digest(adapter_version=self._static_caps.adapter_version)

    @override
    def capabilities(self) -> RuntimeCapabilities:
        return self._static_caps

    @override
    def detect(self, probe: DetectProbe) -> RuntimeInstallation:
        candidate = probe.binary or self._binary or DEFAULT_CURSOR_BINARY
        probed = self._detector.probe(
            binary=candidate,
            environ=self._environ,
            env_allowlist=probe.env_allowlist,
            adapter_version=self._static_caps.adapter_version,
            launch_config_digest=self.launch_config_digest,
            version_timeout_seconds=version_timeout(probe),
        )
        details: dict[str, str] = {
            "binary_sha256": probed.binary_sha256,
            "launch_config_digest": probed.cache_key.launch_config_digest,
            "headless_contract": "unknown",
        }
        return RuntimeInstallation(
            host_id=probe.host_id,
            runtime_id=self.runtime_id,
            version=probed.version,
            binary_locator=probed.binary_locator,
            auth_state=AuthState.UNKNOWN,
            detected_at=self._clock.now(),
            details=details,
        )

    @override
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:
        norm_workdir = posixpath.normpath(request.workdir)
        return (
            SelfLoadedSource(
                kind=SelfLoadKind.PROJECT_SETTINGS,
                locator=f"{norm_workdir}/.cursor",
                files=(".cursor/**",),
                when="start",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.PROJECT_INSTRUCTIONS,
                locator=norm_workdir,
                files=("AGENTS.md", ".cursor/rules/**"),
                when="start",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.USER_CONFIG,
                locator="~/.cursor",
                files=("cli-config.json",),
                when="start",
                trust="untrusted",
            ),
        )

    @override
    def start(self, request: AgentRequest) -> SessionHandle:
        del request
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "Cursor headless execution is not verified; headless contract unknown",
            details={
                "capability": Capability.HEADLESS_EXECUTION.value,
                "runtime_id": self.runtime_id,
            },
        )

    @override
    def events(self, handle: SessionHandle) -> Iterator[SessionEvent]:
        del handle
        raise ValueError("session handle does not belong to this CursorRuntime instance")

    @override
    def cancel(self, handle: SessionHandle, *, grace_seconds: float) -> CancellationResult:
        del handle, grace_seconds
        raise ValueError("session handle does not belong to this CursorRuntime instance")

    @override
    def result(self, handle: SessionHandle) -> RuntimeResult:
        del handle
        raise ValueError("session handle does not belong to this CursorRuntime instance")
