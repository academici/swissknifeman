"""Claude Code CLI binary resolution, version/help probing, and 6-tuple identity cache."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
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

from .launch import without_ambient_auth

__all__: list[str] = []

_VERSION_RE: Final = re.compile(r"\d+\.\d+\.\d+")

REQUIRED_FLAGS: Final[tuple[str, ...]] = (
    "--output-format",
    "--effort",
    "--permission-prompts",
    "--no-session-persistence",
    "--settings",
    "--tools",
    "--disallowedTools",
    "--allowedTools",
    "--setting-sources",
    "--resume",
    "--add-dir",
    "--mcp-config",
)

OPTIONAL_FLAGS: Final[tuple[str, ...]] = (
    "--safe-mode",
    "--permission-mode",
    "--strict-mcp-config",
    "--verbose",
    "--model",
)


@dataclass(frozen=True, slots=True)
class ProbedBinary:
    """Immutable probed identity and flag support of a resolved Claude binary."""

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

    @property
    def safe_mode_supported(self) -> bool:
        return "--safe-mode" in self.supported_flags

    @property
    def permission_mode_supported(self) -> bool:
        return "--permission-mode" in self.supported_flags

    @property
    def strict_mcp_supported(self) -> bool:
        return "--strict-mcp-config" in self.supported_flags


def parse_version_output(text: str) -> str | None:
    """Extract first ``X.Y.Z`` semantic version from ``claude --version`` output."""
    match = _VERSION_RE.search(text)
    return None if match is None else match.group(0)


def extract_supported_flags(help_text: str) -> frozenset[str]:
    return frozenset(find_flags(help_text, (*REQUIRED_FLAGS, *OPTIONAL_FLAGS)))


def apply_probe_to_capabilities(
    static: RuntimeCapabilities,
    probed: ProbedBinary | None,
) -> RuntimeCapabilities:
    """Degrade ``headless_execution`` to ``unsupported`` when required CLI flags are missing."""
    return degrade_headless_for_missing_flags(static, probed, evidence="probe:claude_help")


class ClaudeDetector(CliDetector[ProbedBinary]):
    """Instance-scoped Claude CLI detector with 6-tuple probe cache (no module singletons)."""

    display_name = "Claude Code"
    version_pattern = _VERSION_RE
    probe_env_extra = MappingProxyType(
        {
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
        }
    )

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
            environ=without_ambient_auth(environ),
            env_allowlist=env_allowlist,
            adapter_version=adapter_version,
            launch_config_digest=launch_config_digest,
            version_timeout_seconds=version_timeout_seconds,
            details=details,
        )
