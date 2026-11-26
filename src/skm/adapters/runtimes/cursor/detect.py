"""Cursor CLI binary resolution, version probing, and 6-tuple identity cache."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from skm.adapters.runtimes._cli_session.probe import VERSION_TIMEOUT_SECONDS, CliDetector, ProbeCacheKey
from skm.modules.runtimes.domain.ids import Digest

__all__: list[str] = []

DEFAULT_CURSOR_BINARY: Final = "cursor-agent"
_VERSION_RE: Final = re.compile(r"\d+(?:\.\d+)+(?:-[A-Za-z0-9._-]+)?")


@dataclass(frozen=True, slots=True)
class ProbedBinary:
    """Immutable probed identity of a resolved Cursor binary."""

    cache_key: ProbeCacheKey
    binary_locator: str
    version: str | None

    @property
    def binary_realpath(self) -> str:
        return self.cache_key.binary_realpath

    @property
    def binary_sha256(self) -> Digest:
        return self.cache_key.binary_sha256


def compute_launch_config_digest(*, adapter_version: str) -> Digest:
    """Canonical SHA-256 digest of Cursor detect-only v1 configuration."""
    template = {
        "adapter_version": adapter_version,
        "default_binary": DEFAULT_CURSOR_BINARY,
        "headless_execution": "unknown",
    }
    encoded = json.dumps(template, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def parse_version_output(text: str) -> str | None:
    """Extract first numeric/dotted version string from ``cursor-agent --version`` output."""
    match = _VERSION_RE.search(text)
    return None if match is None else match.group(0)


class CursorDetector(CliDetector[ProbedBinary]):
    """Instance-scoped Cursor CLI detector with 6-tuple probe cache (no module singletons)."""

    display_name = "Cursor"
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
    ) -> ProbedBinary:
        def details(
            binary_realpath: str, env: Mapping[str, str], cache_key: ProbeCacheKey, version: str | None
        ) -> ProbedBinary:
            del env
            return ProbedBinary(cache_key=cache_key, binary_locator=binary_realpath, version=version)

        return self._probe(
            binary=binary,
            environ=environ,
            env_allowlist=env_allowlist,
            adapter_version=adapter_version,
            launch_config_digest=launch_config_digest,
            version_timeout_seconds=version_timeout_seconds,
            details=details,
        )
