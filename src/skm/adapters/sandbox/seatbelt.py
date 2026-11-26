"""Deny-default macOS Seatbelt backend. Enforcement awaits a real macOS canary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, override

from skm.adapters.sandbox.backend import BackendIsolation, SpecView, WrappedProcess, unavailable
from skm.platform.config.sources.hookd_runtime import runtime_overlaps

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.json_types import JsonObject
    from skm.modules.policy.domain.render import IsolationProperty

__all__ = ["SeatbeltSandbox"]

_PROFILE = "skm:seatbelt"
_BINARY = Path("/usr/bin/sandbox-exec")
_SYSTEM_READ = ("/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/lib", "/usr/libexec", "/System/Library")
_SHARED = (Path("/private/tmp"), Path("/private/var/tmp"), Path("/private/var/folders"))
_STATE_NAMES = frozenset({".git", ".skm", ".swissknifeman"})
_STATE_RULE = (
    '(deny file-write* (regex #"/[.]([Gg][Ii][Tt]|[Ss][Kk][Mm]|'
    '[Ss][Ww][Ii][Ss][Ss][Kk][Nn][Ii][Ff][Ee][Mm][Aa][Nn])(/|$)"))'
)
_BASE = (
    "(version 1)",
    "(deny default)",
    "(allow process-exec process-fork)",
    '(allow file-read-metadata (literal "/"))',
    "(allow file-read* file-map-executable " + " ".join(f'(subpath "{path}")' for path in _SYSTEM_READ) + ")",
    '(allow file-read* (literal "/dev/null") (literal "/dev/zero") (literal "/dev/urandom"))',
)
_NETWORK = (
    '(allow network-outbound (remote ip "*:*"))',
    '(allow network-inbound network-bind (local ip "*:*"))',
)


def _absolute(path: Path, *, strict: bool = False) -> Path:
    if not path.is_absolute():
        raise unavailable(_PROFILE, "unsafe_path", f"expected an absolute path: {path}")
    return path.resolve(strict=strict)


def _directory(path: Path) -> Path:
    real = _absolute(path, strict=True)
    if (
        not real.is_dir()
        or any(root.is_relative_to(real) for root in (Path.home().resolve(), *_SHARED))
        or real.parts[1].casefold() in {"bin", "sbin", "usr", "system", "dev", "etc"}
        or any(part.casefold() in _STATE_NAMES for part in real.parts)
    ):
        raise unavailable(_PROFILE, "unsafe_grant", f"expected a narrow task directory: {path}")
    return real


def _profile_args(
    worktree: Path,
    step_tmp: Path,
    protected: Sequence[Path],
    *,
    writable_worktree: bool,
    allow_network: bool,
) -> tuple[str, ...]:
    # Keep `python -m skm.adapters.sandbox.landlock_exec` independent of package import.
    from skm.adapters.sandbox.landlock import git_metadata_dirs

    params: dict[Path, str] = {}

    def match(kind: str, path: Path) -> str:
        # sandbox-exec passes -D values as data. Paths never become Scheme source.
        key = params.setdefault(path, f"PATH_{len(params)}")
        return f'({kind} (param "{key}"))'

    work = match("subpath", worktree)
    temp = match("subpath", step_tmp)
    writable = (worktree, step_tmp) if writable_worktree else (step_tmp,)
    rules = [
        *_BASE,
        f"(allow file-read* file-map-executable {work} {temp})",
        f"(allow file-write* {' '.join(match('subpath', path) for path in writable)})",
        _STATE_RULE,
    ]

    git_entry = worktree / ".git"
    git_paths = dict.fromkeys((git_entry, git_entry.resolve(), *git_metadata_dirs(worktree)))
    rules.extend(f"(deny file-write* {match('subpath', path)})" for path in git_paths)
    protected_paths = dict.fromkeys(
        candidate for path in protected for candidate in (_absolute(path), path.parent.resolve() / path.name)
    )
    rules.extend(
        f"(deny file-read* file-write* file-map-executable {match('subpath', path)})"
        for path in protected_paths
    )

    # Keep a writable ancestor from being renamed away along with the protected entry.
    protected_ancestors = dict.fromkeys(
        parent
        for path in (*git_paths, *protected_paths)
        for parent in path.parents
        if any(parent.is_relative_to(root) for root in writable)
    )
    rules.extend(f"(deny file-write-unlink {match('literal', path)})" for path in protected_ancestors)

    rules.extend(_NETWORK if allow_network else ("(deny network*)",))
    return ("-p", "\n".join(rules), *(f"-D{key}={path}" for path, key in params.items()), "--")


class SeatbeltSandbox(BackendIsolation):
    profile: ClassVar[str] = _PROFILE
    verification_status: ClassVar[str] = "unverified"

    def available(self, host: object = None) -> JsonObject:  # noqa: ARG002
        result: JsonObject = {"available": False, "verification_status": self.verification_status}
        if sys.platform != "darwin":
            return {**result, "reason": "macOS is required"}
        if not _BINARY.is_file() or not os.access(_BINARY, os.X_OK):
            return {**result, "reason": f"{_BINARY} is missing or not executable"}
        return {**result, "available": True}

    @override
    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        # The launcher probe checks platform and executable availability.
        return {}

    def filesystem_argv(
        self,
        argv: Sequence[str],
        *,
        worktree: Path,
        step_tmp: Path,
        protected: Sequence[Path] = (),
        writable_worktree: bool = True,
        allow_network: bool = False,
    ) -> tuple[str, ...]:
        """Build a Seatbelt command for a caller that supplies cwd and a sanitized environment."""
        if not argv:
            raise ValueError("argv must not be empty")
        probe = self.available()
        if probe["available"] is not True:
            raise unavailable(self.profile, "seatbelt_unavailable", str(probe["reason"]))
        try:
            worktree, step_tmp = _directory(worktree), _directory(step_tmp)
            if any(runtime_overlaps(path) for path in (worktree, step_tmp, *map(Path, _SYSTEM_READ))):
                raise unavailable(self.profile, "protected_grant", "sandbox grant overlaps hookd runtime")
            if worktree.is_relative_to(step_tmp) or step_tmp.is_relative_to(worktree):
                raise unavailable(
                    self.profile, "overlapping_grants", "worktree and step_tmp must be disjoint"
                )
            info = step_tmp.stat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise unavailable(self.profile, "unsafe_tmp", "step_tmp must be private and worker-owned")
            profile_args = _profile_args(
                worktree,
                step_tmp,
                protected,
                writable_worktree=writable_worktree,
                allow_network=allow_network,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise unavailable(self.profile, "unsafe_path", str(error)) from error
        return (str(_BINARY), *profile_args, *argv)

    def wrap(self, argv: Sequence[str], spec: SpecView) -> WrappedProcess:
        temporary = set(spec.writable) - {spec.workdir}
        if len(temporary) != 1:
            raise unavailable(self.profile, "unsupported_grants", "expected a worktree and private step_tmp")
        (step_tmp,) = temporary
        if spec.env.get("TMPDIR", str(step_tmp)) != str(step_tmp):
            raise unavailable(self.profile, "unsafe_tmp", "TMPDIR differs from the host grant")
        if (
            not set(spec.readable).issubset({spec.workdir, step_tmp})
            or spec.workdir not in (*spec.readable, *spec.writable)
            or spec.materials_dir is not None
            or spec.credential_mounts
        ):
            raise unavailable(self.profile, "unsupported_grants", "expected a worktree and private step_tmp")
        if set(spec.env) - {"PATH", "TMPDIR", "LANG", "LC_ALL"}:
            raise unavailable(self.profile, "unsupported_environment", "unrecognized launcher environment")
        if spec.network == "allowlist":
            raise unavailable(self.profile, "unsupported_network", "unsupported Seatbelt network allowlist")
        command = self.filesystem_argv(
            argv,
            worktree=spec.workdir,
            step_tmp=step_tmp,
            protected=spec.protected,
            writable_worktree=spec.workdir in spec.writable,
            allow_network=spec.network == "full",
        )
        coverage = self.coverage(spec, argv)
        return WrappedProcess(
            (*coverage.launch, *command),
            {**spec.env, "TMPDIR": str(step_tmp)},
            spec.workdir,
            self.ownership(spec, coverage),
        )
