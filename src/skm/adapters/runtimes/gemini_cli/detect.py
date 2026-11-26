"""Gemini CLI identity and launch flag detection."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from skm.adapters.runtimes._cli_session.probe import (
    HELP_TIMEOUT_SECONDS,
    VERSION_TIMEOUT_SECONDS,
    CliDetector,
    ProbeCacheKey,
    degrade_headless_for_missing_flags,
    find_flags,
)
from skm.modules.runtimes.domain.capability import RuntimeCapabilities
from skm.modules.runtimes.domain.ids import Digest

__all__: list[str] = []

REQUIRED_FLAGS = ("--model", "--output-format", "--approval-mode", "--prompt")


@dataclass(frozen=True, slots=True)
class ProbedBinary:
    cache_key: ProbeCacheKey
    binary_locator: str
    version: str | None
    missing_required_flags: tuple[str, ...]

    @property
    def binary_realpath(self) -> str:
        return self.cache_key.binary_realpath

    @property
    def binary_sha256(self) -> Digest:
        return self.cache_key.binary_sha256


def apply_probe_to_capabilities(
    static: RuntimeCapabilities, probed: ProbedBinary | None
) -> RuntimeCapabilities:
    return degrade_headless_for_missing_flags(static, probed, evidence="probe:gemini_help")


class GeminiCliDetector(CliDetector[ProbedBinary]):
    display_name = "Gemini CLI"
    version_pattern = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?")

    def probe(
        self,
        *,
        binary: str,
        environ: Mapping[str, str],
        env_allowlist: tuple[str, ...],
        adapter_version: str,
        launch_config_digest: Digest,
        version_timeout_seconds: float = VERSION_TIMEOUT_SECONDS,
        help_timeout_seconds: float = HELP_TIMEOUT_SECONDS,
    ) -> ProbedBinary:
        def details(
            path: str, env: Mapping[str, str], key: ProbeCacheKey, version: str | None
        ) -> ProbedBinary:
            help_out = self._run_with_timeout_retry(
                (path, "--help"), env=env, timeout_seconds=help_timeout_seconds
            )
            flags: set[str] = (
                find_flags(f"{help_out.stdout}\n{help_out.stderr}", REQUIRED_FLAGS)
                if help_out.returncode == 0
                else set()
            )
            return ProbedBinary(
                key, path, version, tuple(flag for flag in REQUIRED_FLAGS if flag not in flags)
            )

        return self._probe(
            binary=binary,
            environ=environ,
            env_allowlist=env_allowlist,
            adapter_version=adapter_version,
            launch_config_digest=launch_config_digest,
            version_timeout_seconds=version_timeout_seconds,
            details=details,
        )
