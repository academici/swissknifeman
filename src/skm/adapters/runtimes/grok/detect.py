"""Grok CLI binary resolution, version/help probing, and 6-tuple identity cache."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

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

_VERSION_RE: Final = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?")

REQUIRED_FLAGS: Final[tuple[str, ...]] = (
    "--cwd",
    "--prompt-file",
    "--model",
    "--effort",
    "--permission-mode",
    "--output-format",
)

OPTIONAL_FLAGS: Final[tuple[str, ...]] = (
    "--resume",
    "--disallowed-tools",
    "--disable-web-search",
)


@dataclass(frozen=True, slots=True)
class ProbedBinary:
    """Immutable probed identity and flag support of a resolved Grok binary."""

    cache_key: ProbeCacheKey
    binary_locator: str
    version: str | None
    supported_flags: frozenset[str]
    missing_required_flags: tuple[str, ...]

    @property
    def binary_realpath(self) -> str:
        return self.cache_key.binary_realpath

    @property
    def binary_sha256(self) -> Digest:
        return self.cache_key.binary_sha256


def parse_version_output(text: str) -> str | None:
    """Extract first semantic version from ``grok --version`` output."""
    match = _VERSION_RE.search(text)
    return None if match is None else match.group(0)


def extract_supported_flags(help_text: str) -> frozenset[str]:
    return frozenset(find_flags(help_text, (*REQUIRED_FLAGS, *OPTIONAL_FLAGS)))


def apply_probe_to_capabilities(
    static: RuntimeCapabilities,
    probed: ProbedBinary | None,
) -> RuntimeCapabilities:
    """Degrade ``headless_execution`` to ``unsupported`` when required CLI flags are missing."""
    return degrade_headless_for_missing_flags(static, probed, evidence="probe:grok_help")


class GrokDetector(CliDetector[ProbedBinary]):
    """Instance-scoped Grok CLI detector with 6-tuple probe cache (no module singletons)."""

    display_name = "Grok"
    version_pattern = _VERSION_RE

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
            binary_realpath: str, env: Mapping[str, str], cache_key: ProbeCacheKey, version: str | None
        ) -> ProbedBinary:
            help_out = self._run_with_timeout_retry(
                (binary_realpath, "--help"), env=env, timeout_seconds=help_timeout_seconds
            )
            supported = extract_supported_flags(f"{help_out.stdout}\n{help_out.stderr}")
            return ProbedBinary(
                cache_key=cache_key,
                binary_locator=binary_realpath,
                version=version,
                supported_flags=supported,
                missing_required_flags=tuple(flag for flag in REQUIRED_FLAGS if flag not in supported),
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
