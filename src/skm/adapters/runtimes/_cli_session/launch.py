"""Launch-plan building blocks shared by the CLI runtime adapters.

Each adapter keeps its own argv, permission rendering and isolation overrides; the private directory
rules, the isolated client home layout, the base child environment and the Landlock wrapper are the
same for all of them.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
from skm.platform.process.argv_rules import check_argv
from skm.platform.process.environment import build_env

if TYPE_CHECKING:
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.ids import Digest

__all__ = [
    "base_child_env",
    "ensure_private_dir",
    "env_auth_present",
    "home_from_env",
    "landlock_argv",
    "prepare_client_home",
    "reject_secrets_in_argv",
    "require_client_credentials",
    "resolve_workdir",
    "write_allow_dirs",
]

_TLS_ENV: tuple[str, ...] = ("SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS")


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    """Adapter-owned command envelope matching ``WrappedCommand`` without host-layer imports."""

    argv: tuple[str, ...]
    env: Mapping[str, str] = field(repr=False)
    cwd: Path
    ownership: ProcessOwnership
    verification_template: Digest | None = None

    def as_wrapped(self) -> WrappedCommand:
        return cast("WrappedCommand", self)


def _symlink_dir(path: Path) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.RUNTIME_INVALID_REQUEST,
        f"private runtime directory must not be a symlink: {path}",
        details={"reason": "symlink_directory"},
    )


def ensure_private_dir(path: Path) -> Path:
    """Create ``path`` with mode 0700 and return its realpath; a symlink is rejected before and after."""
    if path.is_symlink():
        raise _symlink_dir(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise _symlink_dir(path)
    os.chmod(path, 0o700)
    return path.resolve(strict=True)


def resolve_workdir(request: AgentRequest) -> Path:
    """The realpath of the request workdir, which must exist."""
    workdir = Path(request.workdir)
    if not workdir.is_dir():
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            f"request workdir does not exist: {workdir}",
            details={"reason": "workdir_missing"},
        )
    return workdir.resolve(strict=True)


def home_from_env(explicit: Path | None, host_environ: Mapping[str, str], key: str = "HOME") -> Path | None:
    """``explicit`` when given, else the non-empty ``key`` of the host environment."""
    if explicit is not None:
        return explicit
    raw = host_environ.get(key)
    return Path(raw) if raw else None


def prepare_client_home(
    request: AgentRequest, *, workdir: Path, writable_dirs: Iterable[str], credential_filename: str
) -> tuple[Path, Path]:
    """Create the ``0700`` isolated client home and its writable subdirectories outside ``workdir``.

    Returns the home and the credential target inside it, which must not be a symlink.
    """
    if request.client_home is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "isolated config_mode requires client_home",
            details={"reason": "client_home_mismatch"},
        )
    raw_home = Path(request.client_home)
    if raw_home.is_symlink():
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "client_home must not be a symlink",
            details={"reason": "client_home_symlink"},
        )
    client_home = ensure_private_dir(raw_home)
    if client_home.is_relative_to(workdir):
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "resolved client_home must be outside workdir",
            details={"reason": "client_home_inside_worktree"},
        )
    for subdir in writable_dirs:
        ensure_private_dir(client_home / subdir)
    target_cred = client_home / credential_filename
    if target_cred.is_symlink():
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "isolated credentials target must not be a symlink",
            details={"reason": "credentials_symlink"},
        )
    return client_home, target_cred


def env_auth_present(request: AgentRequest, host_environ: Mapping[str, str], names: Iterable[str]) -> bool:
    """Whether the child gets an auth variable: from the host allowlist, ``extra_env`` or a secret."""
    return any(
        (name in request.env_allowlist and bool(host_environ.get(name)))
        or bool(request.extra_env.get(name))
        or name in request.secret_env
        for name in names
    )


def require_client_credentials(
    target_cred: Path, *, has_env_auth: bool, runtime_id: str, display_name: str
) -> None:
    """Force ``0600`` on the copied credentials, or fail with ``RUNTIME_AUTH_EXPIRED`` without any auth."""
    if target_cred.is_file():
        os.chmod(target_cred, 0o600)
    elif not has_env_auth:
        raise CapabilityUnavailable(
            ErrorCode.RUNTIME_AUTH_EXPIRED,
            f"{display_name} credentials missing in isolated client home",
            details={"runtime_id": runtime_id, "reason": "credentials_missing"},
        )


def base_child_env(
    request: AgentRequest,
    *,
    host_environ: Mapping[str, str],
    home: Path | None,
    stripped: Iterable[str] = (),
) -> dict[str, str]:
    """The allowlisted child environment with the request secrets; ``stripped`` names drop unless set
    explicitly in ``extra_env``. Adapters add their mandatory overrides on top."""
    env = build_env(
        host_environ, allow=(*request.env_allowlist, *_TLS_ENV), extra=request.extra_env, home=home
    )
    for key in stripped:
        if key not in request.extra_env:
            env.pop(key, None)
    for secret_name, secret_val in request.secret_env.items():
        env[secret_name] = secret_val.reveal()
    return env


def reject_secrets_in_argv(request: AgentRequest, argv: Sequence[str], display_name: str) -> None:
    secret_values = tuple(secret.reveal() for secret in request.secret_env.values())
    if any(secret and secret in arg for secret in secret_values for arg in argv):
        raise ValueError(f"secret values must never appear in {display_name} argv")


def write_allow_dirs(request: AgentRequest, workdir: Path) -> list[Path]:
    """``workdir`` plus the existing directory roots of ``fs_write.allow``; empty for a read-only step."""
    if not request.permissions.fs_write.allow:
        return []
    dirs = [workdir]
    for rule in request.permissions.fs_write.allow:
        if rule.root == "*":
            continue
        candidate = Path(rule.root)
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


def landlock_argv(
    argv: Sequence[str],
    rw_dirs: Iterable[Path],
    *,
    python_executable: str,
    protected: Iterable[str] = (),
    min_abi: int = 3,
) -> tuple[str, ...]:
    """Wrap ``argv`` with ``landlock_exec --no-default-rw``, granting each distinct realpath once."""
    resolved: list[str] = []
    for directory in rw_dirs:
        path = str(directory.resolve(strict=True))
        if path not in resolved:
            resolved.append(path)
    prefix: list[str] = [
        python_executable,
        "-P",
        "-m",
        "skm.adapters.sandbox.landlock_exec",
        "--no-default-rw",
        "--min-abi",
        str(min_abi),
    ]
    for item in protected:
        prefix.extend(("--protect", item))
    for path in resolved:
        prefix.extend(("--rw", path))
    prefix.append("--")
    prefix.extend(argv)
    return check_argv(prefix)
