"""Shared CLI binary probing: resolution, version/help capture and the 6-tuple identity cache.

Every CLI runtime adapter identifies its binary the same way: resolve it against the injected
``PATH``, hash it, run ``--version`` and cache the probed facts by ``ProbeCacheKey``. Adapters only
differ in what they read beyond the version (help flags, login status), which they supply through
the ``details`` builder given to ``CliDetector._probe``.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Final, Protocol

from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
)
from skm.modules.runtimes.domain.ids import Digest
from skm.platform.process.environment import build_env
from skm.platform.process.ownership import OwnershipUnavailable, require_support
from skm.platform.process.runner import run

from .launch import apply_proxy_env

__all__: list[str] = []

VERSION_TIMEOUT_SECONDS: Final = 10.0
HELP_TIMEOUT_SECONDS: Final = 20.0


@dataclass(frozen=True, slots=True)
class CommandOutput:
    """Captured output of a short non-interactive CLI probe command."""

    returncode: int
    stdout: str
    stderr: str


class ProbeCommandRunner(Protocol):
    """Injectable subprocess runner for deterministic offline probe testing."""

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> CommandOutput: ...


@dataclass(frozen=True, slots=True)
class ProbeCacheKey:
    """Normative 6-tuple cache key for CLI probe facts."""

    binary_realpath: str
    binary_sha256: Digest
    version: str
    os_kernel: str
    adapter_version: str
    launch_config_digest: Digest


class FlagProbe(Protocol):
    """Probed facts needed to degrade headless execution when required flags are missing."""

    @property
    def version(self) -> str | None: ...

    @property
    def missing_required_flags(self) -> tuple[str, ...]: ...


def _probe_text(data: bytes) -> str:
    """Probe output as text with universal newlines; bytes that are not UTF-8 never fail the probe."""
    return data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")


def default_probe_runner(
    argv: tuple[str, ...],
    *,
    env: Mapping[str, str],
    timeout_seconds: float,
) -> CommandOutput:
    """Probe configured CLI binaries even on hosts without pidfd group ownership.

    With ownership support, output is bounded and the probe ends when the CLI exits even if a helper
    holds its pipes open. Both paths report a timeout as ``subprocess.TimeoutExpired``.
    """
    try:
        require_support()
    except OwnershipUnavailable:
        # These inventory commands can run on hosts that cannot supervise a runtime session.
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=dict(env),
            check=False,
        )
        return CommandOutput(completed.returncode, completed.stdout, completed.stderr)
    result = run(argv, cwd=Path.cwd(), env=env, timeout_seconds=timeout_seconds)
    if result.timed_out:
        raise subprocess.TimeoutExpired(argv, timeout_seconds, output=result.stdout, stderr=result.stderr)
    return CommandOutput(
        returncode=result.exit_code,
        stdout=_probe_text(result.stdout),
        stderr=_probe_text(result.stderr),
    )


def default_os_kernel() -> str:
    return f"{platform.system()}:{platform.release()}"


def sha256_file(path: Path) -> Digest:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65_536):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def resolve_binary_path(candidate: str, *, environ: Mapping[str, str], display_name: str) -> Path:
    """Resolve binary name or path against injected ``PATH`` without reading ``os.environ``."""
    cleaned = candidate.strip()
    if not cleaned:
        raise FileNotFoundError(f"{display_name} binary name is empty")
    if "/" in cleaned:
        target = Path(cleaned)
        if not target.is_file() or not os.access(target, os.X_OK):
            raise FileNotFoundError(f"{display_name} binary not executable: {cleaned}")
        return target.resolve(strict=True)
    # An empty or relative entry is the working directory, which may be a checkout the agent writes.
    entries = (environ.get("PATH") or "").split(os.pathsep)
    searched = os.pathsep.join(entry for entry in entries if os.path.isabs(entry))
    located = shutil.which(cleaned, path=searched) if searched else None
    if located is None:
        raise FileNotFoundError(f"{display_name} binary not found on PATH: {cleaned}")
    return Path(located).resolve(strict=True)


def find_flags(help_text: str, flags: Iterable[str]) -> set[str]:
    """Return ``flags`` that appear as standalone tokens (not prefixes of longer flags) in help text."""
    found: set[str] = set()
    for flag in flags:
        pattern = re.compile(rf"(?<!\w){re.escape(flag)}(?![\w-])")
        if pattern.search(help_text) is not None:
            found.add(flag)
    return found


def degrade_headless_for_missing_flags(
    static: RuntimeCapabilities,
    probed: FlagProbe | None,
    *,
    evidence: str,
) -> RuntimeCapabilities:
    """Degrade ``headless_execution`` to ``unsupported`` when required CLI flags are missing."""
    if probed is None or not probed.missing_required_flags:
        return static
    limitation = f"missing required CLI flags: {', '.join(probed.missing_required_flags)}"
    existing = static.records.get(Capability.HEADLESS_EXECUTION)
    updated = (
        replace(
            existing,
            status=CapabilityStatus.UNSUPPORTED,
            limitations=limitation,
            tested_runtime_version=probed.version or existing.tested_runtime_version,
        )
        if existing is not None
        else CapabilityRecord(
            capability=Capability.HEADLESS_EXECUTION,
            status=CapabilityStatus.UNSUPPORTED,
            evidence=evidence,
            tested_runtime_version=probed.version,
            limitations=limitation,
            last_verified_at=None,
        )
    )
    records = dict(static.records)
    records[Capability.HEADLESS_EXECUTION] = updated
    return replace(static, records=records)


type ProbeDetails[ProbedT] = Callable[[str, Mapping[str, str], ProbeCacheKey, str | None], ProbedT]
"""Builds the adapter probe record from ``(binary_realpath, probe_env, cache_key, version)``."""


class CliDetector[ProbedT]:
    """Instance-scoped CLI detector with a 6-tuple probe cache (no module singletons).

    Subclasses declare the binary's display name, version pattern and probe environment, and pass
    ``_probe`` the builder of their adapter-specific record, called only on a cache miss.
    """

    display_name: ClassVar[str]
    version_pattern: ClassVar[re.Pattern[str]]
    probe_env_extra: ClassVar[Mapping[str, str]] = MappingProxyType({})

    def __init__(
        self,
        *,
        run_cmd: ProbeCommandRunner = default_probe_runner,
        os_kernel_fn: Callable[[], str] = default_os_kernel,
    ) -> None:
        self._run_cmd = run_cmd
        self._os_kernel_fn = os_kernel_fn
        self._lock = threading.RLock()
        self._version_by_binary: dict[tuple[str, Digest], str | None] = {}
        self._cache: dict[ProbeCacheKey, ProbedT] = {}
        self._last_probed: ProbedT | None = None

    @property
    def last_probed(self) -> ProbedT | None:
        with self._lock:
            return self._last_probed

    def parse_version(self, text: str) -> str | None:
        match = self.version_pattern.search(text)
        return None if match is None else match.group(0)

    def _probe(
        self,
        *,
        binary: str,
        environ: Mapping[str, str],
        env_allowlist: tuple[str, ...],
        adapter_version: str,
        launch_config_digest: Digest,
        version_timeout_seconds: float,
        details: ProbeDetails[ProbedT],
    ) -> ProbedT:
        resolved = resolve_binary_path(binary, environ=environ, display_name=self.display_name)
        realpath_str = str(resolved)
        digest = sha256_file(resolved)
        os_kernel = self._os_kernel_fn()
        probe_env = build_env(environ, allow=env_allowlist, extra=self.probe_env_extra)
        apply_proxy_env(probe_env)

        def key_for(version: str | None) -> ProbeCacheKey:
            return ProbeCacheKey(
                binary_realpath=realpath_str,
                binary_sha256=digest,
                version=version or "unknown",
                os_kernel=os_kernel,
                adapter_version=adapter_version,
                launch_config_digest=launch_config_digest,
            )

        with self._lock:
            if (realpath_str, digest) in self._version_by_binary:
                cached = self._cache.get(key_for(self._version_by_binary[(realpath_str, digest)]))
                if cached is not None:
                    self._last_probed = cached
                    return cached

        version_out = self._run_cmd(
            (realpath_str, "--version"),
            env=probe_env,
            timeout_seconds=version_timeout_seconds,
        )
        version = self.parse_version(f"{version_out.stdout}\n{version_out.stderr}")
        cache_key = key_for(version)

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._version_by_binary[(realpath_str, digest)] = version
                self._last_probed = cached
                return cached

        probed = details(realpath_str, probe_env, cache_key, version)
        with self._lock:
            self._version_by_binary[(realpath_str, digest)] = version
            self._cache[cache_key] = probed
            self._last_probed = probed
        return probed

    def _run_with_timeout_retry(
        self,
        argv: tuple[str, ...],
        *,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> CommandOutput:
        """Run a probe command, retrying once when a cold binary times out."""
        try:
            return self._run_cmd(argv, env=env, timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired:
            return self._run_cmd(argv, env=env, timeout_seconds=timeout_seconds)
