"""Check factories and canonical immutable-closure reuse rules (execution §4.12)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.modules.execution.domain.check_execution import CheckExecution, may_reuse
from skm.modules.execution.ports import CheckRunner
from skm.platform.fs.storage_budget import StorageBudget

from .command import command_check_runner
from .external import external_check_runner
from .manual import manual_check_runner
from .shell import shell_check_runner

if TYPE_CHECKING:
    from .command import CheckLauncher

__all__ = ["build_check_registry", "can_reuse", "check_fingerprint"]

_REQUIRED = frozenset(
    {
        "host_id",
        "checkout_binding",
        "executable",
        "toolchain",
        "dependencies",
        "path",
        "environment",
        "isolation_profile",
        "backend",
        "image",
        "network",
        "credentials",
        "external_inputs",
    }
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def check_fingerprint(
    output_tree_digest: str,
    check_spec_digest: str,
    env_manifest: Mapping[str, object],
    *,
    trusted_current_closure: bool = False,
    post_integration: bool = False,
) -> str | None:
    """Pure rule for trusted server-known facts. Worker labels alone never authorize reuse.

    The ordinary host path supplies no current immutable toolchain proof, so its default is fresh.
    Empty arrays explicitly represent inapplicable credentials/dependencies/external inputs.
    """
    if not trusted_current_closure or post_integration:
        return None
    if not env_manifest.keys() >= _REQUIRED or any(env_manifest.get(key) is None for key in _REQUIRED):
        return None
    if any(
        env_manifest.get(flag) is not True for flag in ("immutable", "closure_verified", "path_immutable")
    ):
        return None
    for key in _REQUIRED - {"dependencies", "credentials", "external_inputs", "environment"}:
        if not env_manifest[key]:
            return None
    for value in (output_tree_digest, check_spec_digest):
        if (
            not value.startswith("sha256:")
            or len(value) != 71
            or any(c not in "0123456789abcdef" for c in value[7:])
        ):
            return None
    # Only declared per-check entropy is normalized, never arbitrary paths/flags/environment keys.
    normalized = dict(env_manifest)
    environment = normalized.get("environment")
    if not isinstance(environment, dict):
        return None
    normalized["environment"] = {
        k: v
        for k, v in cast("dict[str, object]", environment).items()
        if k
        not in {"SKM_CHECK_ID", "SKM_CHECK_RUN", "SKM_CHECK_TASK", "SKM_CHECK_ATTEMPT", "SKM_CHECK_OUTPUT"}
    }
    try:
        encoded = _canonical(["skm-check-v2", output_tree_digest, check_spec_digest, normalized]).encode(
            "utf-8"
        )
    except (ValueError, TypeError, UnicodeError):
        return None
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def can_reuse(  # noqa: PLR0913 - scope and receipt proof are independent inputs
    source: CheckExecution,
    *,
    project_id: object,
    source_project_id: object,
    workspace_id: Any,
    check_spec_id: Any,
    fingerprint: str | None,
    evidence_available: bool,
    post_integration: bool,
    attested: bool = False,
) -> bool:
    return project_id == source_project_id and may_reuse(
        source,
        workspace_id=workspace_id,
        check_spec_id=check_spec_id,
        fingerprint=fingerprint,
        evidence_available=evidence_available,
        post_integration=post_integration,
        attested=attested,
    )


class CheckRunnerRegistry:
    def __init__(self, runners: Mapping[str, CheckRunner]) -> None:
        self.runners = dict(runners)
        if any(key != runner.kind for key, runner in self.runners.items()):
            raise ValueError("check kind differs from registry key")

    def kinds(self) -> frozenset[str]:
        return frozenset(self.runners)

    def get(self, kind: str) -> CheckRunner:
        if kind not in self.runners:
            raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "check runner is not installed")
        return self.runners[kind]


def build_check_registry(  # noqa: PLR0913 - explicit host factory dependencies
    *,
    storage: StorageBudget,
    capture_floor_bytes: int,
    state_dir: Path,
    isolation_registry: Any,
    profile: str,
    host: Any,
    sanitized_env: Mapping[str, str],
    shell_allowed: bool = False,
    process: CheckLauncher | None = None,
    allow_pgroup_best_effort: bool = False,
    max_timeout_seconds: int = 7200,
    external: Mapping[str, CheckRunner] | None = None,
) -> CheckRunnerRegistry:
    common = {
        "storage": storage,
        "capture_floor_bytes": capture_floor_bytes,
        "state_dir": state_dir,
        "isolation_registry": isolation_registry,
        "profile": profile,
        "host": host,
        "sanitized_env": sanitized_env,
        "process": process,
        "allow_pgroup_best_effort": allow_pgroup_best_effort,
        "max_timeout_seconds": max_timeout_seconds,
    }
    return CheckRunnerRegistry(
        {
            "command": command_check_runner(**common),
            "shell": shell_check_runner(shell_allowed=shell_allowed, **common),
            "manual": manual_check_runner(),
            "external": external_check_runner(external),
        }
    )
