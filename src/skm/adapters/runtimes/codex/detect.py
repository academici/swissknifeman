"""Codex CLI binary resolution, version/help/auth probing, and 6-tuple identity cache."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from skm.adapters.runtimes._cli_session.probe import (
    HELP_TIMEOUT_SECONDS,
    VERSION_TIMEOUT_SECONDS,
    CliDetector,
    CommandOutput,
    ProbeCacheKey,
    degrade_headless_for_missing_flags,
    find_flags,
)
from skm.modules.runtimes.domain.capability import RuntimeCapabilities
from skm.modules.runtimes.domain.ids import Digest
from skm.modules.runtimes.domain.installation import AuthState
from skm.platform.process.environment import build_env

__all__: list[str] = []

LOGIN_TIMEOUT_SECONDS: Final = 10.0
_VERSION_RE: Final = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9._-]+)?")

REQUIRED_FLAGS: Final[tuple[str, ...]] = (
    "--json",
    "--sandbox",
    "--model",
    "-c",
    "--ephemeral",
    "resume",
    "-a",
)

OPTIONAL_FLAGS: Final[tuple[str, ...]] = (
    "--ask-for-approval",
    "--dangerously-bypass-approvals-and-sandbox",
    "--cd",
    "-C",
)


@dataclass(frozen=True, slots=True)
class ProbedBinary:
    """Immutable probed identity, flag support, and login status of a resolved Codex binary."""

    cache_key: ProbeCacheKey
    binary_locator: str
    version: str | None
    supported_flags: frozenset[str]
    missing_required_flags: tuple[str, ...]
    auth_state: AuthState = AuthState.UNKNOWN

    @property
    def binary_realpath(self) -> str:
        return self.cache_key.binary_realpath

    @property
    def binary_sha256(self) -> Digest:
        return self.cache_key.binary_sha256

    @property
    def bypass_supported(self) -> bool:
        return "--dangerously-bypass-approvals-and-sandbox" in self.supported_flags


def parse_version_output(text: str) -> str | None:
    """Extract first ``X.Y.Z`` semantic version from ``codex --version`` output."""
    match = _VERSION_RE.search(text)
    return None if match is None else match.group(0)


def parse_login_status_output(output: CommandOutput | None) -> AuthState:
    """Classify ``codex login status`` probe output into ``AuthState`` (Dossier §3.1)."""
    if output is None:
        return AuthState.UNKNOWN
    combined = f"{output.stdout}\n{output.stderr}".casefold()
    if any(
        marker in combined
        for marker in (
            "unrecognized subcommand",
            "unknown subcommand",
            "invalid subcommand",
            "found argument 'login'",
            "unknown command",
        )
    ):
        return AuthState.UNKNOWN
    if "not logged in" in combined:
        return AuthState.MISSING
    if output.returncode == 0 and "logged in" in combined:
        return AuthState.OK
    if output.returncode != 0:
        return AuthState.MISSING
    return AuthState.UNKNOWN


def extract_supported_flags(help_text: str) -> frozenset[str]:
    found = find_flags(help_text, (*REQUIRED_FLAGS, *OPTIONAL_FLAGS))
    if "--ask-for-approval" in found:
        found.add("-a")
    if "-a" in found:
        found.add("--ask-for-approval")
    return frozenset(found)


def apply_probe_to_capabilities(
    static: RuntimeCapabilities,
    probed: ProbedBinary | None,
) -> RuntimeCapabilities:
    """Degrade ``headless_execution`` to ``unsupported`` when required CLI flags are missing."""
    return degrade_headless_for_missing_flags(static, probed, evidence="probe:codex_help")


class CodexDetector(CliDetector[ProbedBinary]):
    """Instance-scoped Codex CLI detector with 6-tuple probe cache (no module singletons)."""

    display_name = "Codex"
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
        login_timeout_seconds: float = LOGIN_TIMEOUT_SECONDS,
    ) -> ProbedBinary:
        def details(
            binary_realpath: str, env: Mapping[str, str], cache_key: ProbeCacheKey, version: str | None
        ) -> ProbedBinary:
            root_help = self._run_with_timeout_retry(
                (binary_realpath, "--help"), env=env, timeout_seconds=help_timeout_seconds
            )
            exec_help = self._run_optional((binary_realpath, "exec", "--help"), env, help_timeout_seconds)
            help_parts = [root_help.stdout, root_help.stderr]
            if exec_help is not None:
                help_parts.extend((exec_help.stdout, exec_help.stderr))
            supported = extract_supported_flags("\n".join(help_parts))
            return ProbedBinary(
                cache_key=cache_key,
                binary_locator=binary_realpath,
                version=version,
                supported_flags=supported,
                missing_required_flags=tuple(flag for flag in REQUIRED_FLAGS if flag not in supported),
            )

        identity = self._probe(
            binary=binary,
            environ=environ,
            env_allowlist=env_allowlist,
            adapter_version=adapter_version,
            launch_config_digest=launch_config_digest,
            version_timeout_seconds=version_timeout_seconds,
            details=details,
        )
        return replace(
            identity,
            auth_state=self.login_status((identity.binary_realpath,), environ, timeout=login_timeout_seconds),
        )

    def login_status(
        self,
        program: tuple[str, ...],
        environ: Mapping[str, str],
        *,
        timeout: float = LOGIN_TIMEOUT_SECONDS,
    ) -> AuthState:
        # Account state can change while the executable bytes and every identity cache key stay the same.
        env = build_env(environ, allow=("CODEX_HOME",))
        output = self._run_optional((*program, "login", "status"), env, timeout)
        return parse_login_status_output(output)

    def _run_optional(
        self, argv: tuple[str, ...], env: Mapping[str, str], timeout_seconds: float
    ) -> CommandOutput | None:
        try:
            return self._run_cmd(argv, env=env, timeout_seconds=timeout_seconds)
        except (OSError, subprocess.SubprocessError):
            return None
