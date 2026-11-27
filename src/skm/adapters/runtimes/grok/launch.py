"""Grok CLI launch plan, containment invariants, and Landlock wrapping."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skm.adapters.runtimes._cli_session.launch import (
    LaunchCommand,
    apply_proxy_env,
    base_child_env,
    ensure_private_dir,
    home_from_env,
    landlock_argv,
    reject_secrets_in_argv,
    resolve_workdir,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.isolation import IsolationProfile
from skm.modules.policy.public import ScopeRoots
from skm.modules.runtimes.domain.classes import RoleId
from skm.modules.runtimes.domain.ids import Digest
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
from skm.platform.process.argv_rules import check_argv

from .permissions import RenderedPermissions, render_permission_flags

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.proxy_bridge import LocalProxyBridge

__all__: list[str] = []

_CONTAINED_ISOLATION_PROFILES: Final = frozenset({IsolationProfile.LANDLOCK, IsolationProfile.CONTAINER})
_VENDOR_CACHE_ROLES: Final = frozenset({RoleId.REVIEWER, RoleId.TRIAGER})


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Complete verified Grok CLI launch specification for a single step."""

    command: LaunchCommand
    grok_argv: tuple[str, ...]
    stdin: bytes
    permissions: RenderedPermissions
    step_tmp: Path
    scope_roots: ScopeRoots


def compute_launch_config_digest(*, adapter_version: str) -> Digest:
    """Canonical SHA-256 digest of static Grok launch template without per-step entropy."""
    template = {
        "adapter_version": adapter_version,
        "base_flags": [
            "--cwd",
            "--prompt-file",
            "/dev/stdin",
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "streaming-messages-json",
        ],
        "contained_profiles": sorted(p.value for p in _CONTAINED_ISOLATION_PROFILES),
        "landlock_no_default_rw": True,
    }
    encoded = json.dumps(template, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def enforce_containment_invariants(
    request: AgentRequest,
    *,
    wrap_landlock: bool = True,
) -> None:
    """Fail closed before spawn if role or host isolation violates Grok v2 containment rules."""
    if request.role is RoleId.REGISTRAR:
        raise CapabilityUnavailable(
            ErrorCode.SANDBOX_UNAVAILABLE,
            "Grok adapter forbids registrar role: writes outside workdir cannot be confined",
            details={
                "runtime_id": "grok",
                "role": request.role.value,
                "reason": "role_forbidden",
            },
        )
    if request.isolation_profile not in _CONTAINED_ISOLATION_PROFILES or (
        request.isolation_profile is IsolationProfile.LANDLOCK and not wrap_landlock
    ):
        raise CapabilityUnavailable(
            ErrorCode.SANDBOX_UNAVAILABLE,
            "Grok --permission-mode bypassPermissions requires landlock or container isolation",
            details={
                "runtime_id": "grok",
                "isolation_profile": str(request.isolation_profile),
                "reason": "bypass_containment_required",
            },
        )


def build_child_environment(
    request: AgentRequest,
    *,
    host_environ: Mapping[str, str],
    user_home: Path | None,
    step_tmp: Path,
    proxy_bridge: LocalProxyBridge | None = None,
) -> Mapping[str, str]:
    """Construct allowlisted child environment preserving read-only ``~/.grok`` auth access."""
    env = base_child_env(request, host_environ=host_environ, home=home_from_env(user_home, host_environ))
    env["TMPDIR"] = str(step_tmp)
    apply_proxy_env(env, proxy_bridge)
    return MappingProxyType(env)


def _wrap_landlock_argv(
    grok_argv: Sequence[str],
    *,
    request: AgentRequest,
    workdir: Path,
    roots: ScopeRoots,
    python_executable: str,
    min_abi: int = 3,
) -> tuple[str, ...]:
    """Wrap Grok command with ``landlock_exec --no-default-rw`` and never grant ``~/.grok`` writes."""
    rw_dirs: list[Path] = []
    protected_dirs: list[str] = []
    if request.permissions.fs_write.allow:
        rw_dirs.append(workdir)
        for rule in request.permissions.fs_write.allow:
            if rule.root == "*":
                continue
            candidate = Path(rule.root)
            if candidate.is_dir() and not candidate.is_symlink():
                rw_dirs.append(candidate)
    else:
        protected_dirs.append(str(workdir))
        if request.role in _VENDOR_CACHE_ROLES:
            vendor_dir = workdir / "vendor"
            if vendor_dir.is_dir() and not vendor_dir.is_symlink():
                rw_dirs.append(vendor_dir)
    if roots.tmp is not None:
        rw_dirs.append(Path(roots.tmp))
    return landlock_argv(
        grok_argv,
        rw_dirs,
        python_executable=python_executable,
        protected=protected_dirs,
        min_abi=min_abi,
    )


def build_launch_plan(  # noqa: PLR0913 - explicit launch boundary without ambient reads
    request: AgentRequest,
    *,
    binary_path: str,
    step_dir: Path,
    ownership: ProcessOwnership,
    host_environ: Mapping[str, str],
    user_home: Path | None = None,
    python_executable: str = sys.executable,
    wrap_landlock: bool = True,
    proxy_bridge: LocalProxyBridge | None = None,
) -> LaunchPlan:
    """Assemble Grok argv, Landlock confinement wrapper, environment, and stdin payload."""
    enforce_containment_invariants(request, wrap_landlock=wrap_landlock)

    resolved_workdir = resolve_workdir(request)
    resolved_step_dir = ensure_private_dir(step_dir)
    if resolved_step_dir.is_relative_to(resolved_workdir) or resolved_workdir.is_relative_to(
        resolved_step_dir
    ):
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "step_dir must not overlap with workdir",
            details={"reason": "step_dir_inside_worktree"},
        )
    step_tmp = ensure_private_dir(resolved_step_dir / "tmp")
    roots = ScopeRoots(
        worktrees={"main": str(resolved_workdir)},
        materials=None,
        tmp=str(step_tmp),
        home=None,
        safe_dirs=(),
        protected=(str(resolved_step_dir),),
        remote_hosts=frozenset(),
    )

    rendered_perms = render_permission_flags(request)
    env = build_child_environment(
        request,
        host_environ=host_environ,
        user_home=user_home,
        step_tmp=step_tmp,
        proxy_bridge=proxy_bridge,
    )

    argv_list: list[str] = [
        binary_path,
        "--cwd",
        str(resolved_workdir),
        "--prompt-file",
        "/dev/stdin",
        "--model",
        request.model,
    ]
    if request.effort is not None:
        argv_list.extend(("--effort", request.effort.value))
    argv_list.extend(("--permission-mode", "bypassPermissions"))
    argv_list.extend(("--output-format", "streaming-messages-json"))
    if request.resume_session_ref is not None:
        argv_list.extend(("--resume", request.resume_session_ref))
    # Append read-only/network restrictions (--disallowed-tools, --disable-web-search) after base flags.
    argv_list.extend(rendered_perms.argv[2:])

    grok_argv = check_argv(argv_list)

    reject_secrets_in_argv(request, grok_argv, "Grok")

    final_argv = grok_argv
    if wrap_landlock and request.isolation_profile is IsolationProfile.LANDLOCK:
        final_argv = _wrap_landlock_argv(
            grok_argv,
            request=request,
            workdir=resolved_workdir,
            roots=roots,
            python_executable=python_executable,
        )

    command = LaunchCommand(
        argv=final_argv,
        env=env,
        cwd=resolved_workdir,
        ownership=ownership,
    )
    return LaunchPlan(
        command=command,
        grok_argv=grok_argv,
        stdin=request.rendered_prompt.encode("utf-8"),
        permissions=rendered_perms,
        step_tmp=step_tmp,
        scope_roots=roots,
    )
