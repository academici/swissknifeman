"""Linux mount-namespace confinement for one checkout and one private step temporary directory."""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import ClassVar, override

from skm.adapters.sandbox.backend import BackendIsolation, SpecView, WrappedProcess, unavailable
from skm.adapters.sandbox.landlock import git_metadata_dirs
from skm.kernel.json_types import JsonObject
from skm.modules.policy.domain.render import IsolationProperty
from skm.platform.config.sources.hookd_runtime import runtime_overlaps
from skm.platform.process.runner import run

__all__ = ["BubblewrapSandbox"]

_SYSTEM = tuple(Path(path) for path in ("/usr/bin", "/usr/lib", "/usr/lib64", "/bin", "/lib", "/lib64"))
_STATE_NAMES = frozenset({".git", ".skm", ".swissknifeman"})
_SHARED = (Path("/tmp"), Path("/var/tmp"))  # noqa: S108 - directories which must never be granted
_PROFILE = "skm:bubblewrap"


def _base(binary: str) -> list[str]:
    args = [
        binary,
        "--unshare-all",
        "--unshare-user",
        "--disable-userns",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--tmpfs",
        "/",
    ]
    for path in _SYSTEM:
        if path.is_dir():
            args.extend(("--ro-bind", str(path), str(path)))
    return args


def _directory(path: Path) -> Path:
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
        raise unavailable(_PROFILE, "unsafe_mount", f"expected a canonical directory: {path}")
    if path == Path("/") or any(p.is_relative_to(path) for p in (Path.home(), *_SHARED, *_SYSTEM)):
        raise unavailable(_PROFILE, "unsafe_mount", f"mount is too broad: {path}")
    if path.parts[1] in {"bin", "lib", "lib64", "usr", "dev", "proc", "sys", "etc"} or (
        _STATE_NAMES.intersection(path.parts)
    ):
        raise unavailable(_PROFILE, "unsafe_mount", f"reserved mount path: {path}")
    return path


def _mount_points() -> Iterator[Path]:
    for record in Path("/proc/self/mountinfo").read_bytes().splitlines():
        field = record.split(b" ")[4]
        unescaped = re.sub(rb"\\([0-7]{3})", lambda match: bytes([int(match[1], 8)]), field)
        yield Path(os.fsdecode(unescaped))


def _check_submounts(roots: tuple[Path, ...], protected: Sequence[Path]) -> None:
    # Recursive binds would also expose a host filesystem mounted inside an otherwise owned tree.
    for mount in _mount_points():
        if any(mount.is_relative_to(root) and mount != root for root in roots) and (
            not _STATE_NAMES.intersection(mount.parts) and mount not in protected
        ):
            raise unavailable(_PROFILE, "nested_mount", f"unexpected host mount in a sandbox grant: {mount}")


def _raise_walk_error(error: OSError) -> None:
    raise error


def _masks(root: Path, protected: Sequence[Path], *, git_entry: Path) -> list[str]:
    """Reject aliases of external inodes and mask state before starting the child."""
    args: list[str] = []
    if root in protected:
        raise unavailable(_PROFILE, "protected_mount", f"mount is protected: {root}")
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=_raise_walk_error):
        parent = Path(directory)
        for name in (*dirs, *files):
            path = parent / name
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise unavailable(_PROFILE, "linked_file", f"cannot confine a multiply linked file: {path}")
            if name in _STATE_NAMES or path in protected:
                if stat.S_ISDIR(info.st_mode):
                    dirs.remove(name)
                    args.extend(("--tmpfs", str(path), "--remount-ro", str(path)))
                elif stat.S_ISREG(info.st_mode):
                    args.extend(("--ro-bind", str(path) if path == git_entry else "/dev/null", str(path)))
                else:
                    raise unavailable(_PROFILE, "unsafe_mask", f"invalid protected mount point: {path}")
            elif not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                raise unavailable(_PROFILE, "special_file", f"special file in sandbox grant: {path}")
    return args


class BubblewrapSandbox(BackendIsolation):
    profile: ClassVar[str] = _PROFILE

    def _binary(self) -> str:
        if platform.system() != "Linux" or not (binary := shutil.which("bwrap", path=os.defpath)):
            raise unavailable(
                self.profile, "bwrap_missing", "Linux and a system bwrap executable are required"
            )
        return binary

    def available(self, host: object = None) -> JsonObject:  # noqa: ARG002
        from skm.kernel.errors import CapabilityUnavailable

        try:
            binary = self._binary()
            result = run(
                [*_base(binary), "--remount-ro", "/", "--", "/bin/true"],
                cwd=Path("/"),
                env={},
                timeout_seconds=5,
                max_stderr_bytes=2048,
            )
        except (OSError, TimeoutError, CapabilityUnavailable) as error:
            return {"available": False, "reason": str(error)}
        if result.exit_code:
            return {
                "available": False,
                "reason": result.stderr.decode(errors="replace").strip()
                or "bwrap could not create the sandbox namespaces",
            }
        return {"available": True}

    @override
    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        if self.available()["available"] is not True:
            return {}
        return {
            IsolationProperty.FS_READ: "private tmpfs root and allowlisted binds",
            IsolationProperty.FS_WRITE: "writable task directories and read-only state masks",
            IsolationProperty.NETWORK_NONE: "private network namespace",
        }

    def filesystem_argv(
        self,
        argv: Sequence[str],
        *,
        worktree: Path,
        step_tmp: Path,
        protected: Sequence[Path] = (),
        writable_worktree: bool = True,
    ) -> tuple[str, ...]:
        """Build the confined command. The host launches it with a sanitized environment."""
        if not argv:
            raise ValueError("argv must not be empty")
        probe = self.available()
        if probe["available"] is not True:
            raise unavailable(self.profile, "bwrap_unavailable", str(probe["reason"]))
        try:
            worktree, step_tmp = _directory(worktree), _directory(step_tmp)
            if worktree.is_relative_to(step_tmp) or step_tmp.is_relative_to(worktree):
                raise unavailable(
                    self.profile, "overlapping_mounts", "worktree and step_tmp must be disjoint"
                )
            info = step_tmp.stat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise unavailable(self.profile, "unsafe_tmp", "step_tmp must be private and worker-owned")
            for path in protected:
                if not path.is_absolute() or path != path.resolve():
                    raise unavailable(self.profile, "unsafe_mask", f"protected path is not canonical: {path}")
            git_entry = worktree / ".git"
            if not git_entry.exists() or git_entry.is_symlink():
                raise unavailable(self.profile, "unsafe_git", "worktree requires a real Git metadata entry")
            git_dirs = git_metadata_dirs(worktree)
            if not git_dirs:
                raise unavailable(self.profile, "unsafe_git", "worktree requires a valid Git metadata entry")
            roots = (worktree, step_tmp)
            if any(runtime_overlaps(path) for path in (*roots, *_SYSTEM)):
                raise unavailable(self.profile, "protected_mount", "sandbox grant overlaps hookd runtime")
            if any(root.is_relative_to(meta) for root in roots for meta in git_dirs):
                raise unavailable(self.profile, "unsafe_git", "sandbox grant is inside Git metadata")
            protected = (*protected, *git_dirs)
            for path in protected:
                if any(path.is_relative_to(root) for root in roots) and not os.path.lexists(path):
                    raise unavailable(self.profile, "unsafe_mask", f"protected path does not exist: {path}")
            if any(
                p.is_relative_to(sysdir.resolve()) or sysdir.resolve().is_relative_to(p)
                for p in protected
                for sysdir in _SYSTEM
            ):
                raise unavailable(
                    self.profile, "protected_system_path", "system bind overlaps protected state"
                )
            _check_submounts(roots, protected)
            masks = [arg for root in roots for arg in _masks(root, protected, git_entry=git_entry)]
        except (OSError, RuntimeError) as error:
            raise unavailable(self.profile, "unsafe_mount", str(error)) from error
        return (
            *_base(self._binary()),
            "--dev",
            "/dev",
            "--remount-ro",
            "/dev",
            "--bind" if writable_worktree else "--ro-bind",
            str(worktree),
            str(worktree),
            "--bind",
            str(step_tmp),
            str(step_tmp),
            *masks,
            "--remount-ro",
            "/",
            "--unsetenv",
            "XDG_RUNTIME_DIR",
            "--setenv",
            "TMPDIR",
            str(step_tmp),
            "--chdir",
            str(worktree),
            "--",
            *argv,
        )

    def wrap(self, argv: Sequence[str], spec: SpecView) -> WrappedProcess:
        temporary = set(spec.writable) - {spec.workdir}
        if len(temporary) != 1:
            raise unavailable(self.profile, "unsupported_mounts", "expected a worktree and private step_tmp")
        (tmp,) = temporary
        if spec.env.get("TMPDIR", str(tmp)) != str(tmp):
            raise unavailable(self.profile, "unsafe_tmp", "TMPDIR differs from the host grant")
        roots = {spec.workdir, tmp}
        if (
            not set(spec.readable).issubset(roots)
            or spec.materials_dir is not None
            or spec.workdir not in (*spec.readable, *spec.writable)
            or spec.credential_mounts
        ):
            raise unavailable(self.profile, "unsupported_mounts", "expected a worktree and private step_tmp")
        # Only a fixed launcher environment may affect the host-side dynamic loader.
        if set(spec.env) - {"PATH", "TMPDIR", "LANG", "LC_ALL"}:
            raise unavailable(self.profile, "unsupported_environment", "unrecognized launcher environment")
        command = self.filesystem_argv(
            argv,
            worktree=spec.workdir,
            step_tmp=tmp,
            protected=spec.protected,
            writable_worktree=spec.workdir in spec.writable,
        )
        coverage = self.coverage(spec, argv)
        return WrappedProcess(
            (*coverage.launch, *command), dict(spec.env), spec.workdir, self.ownership(spec, coverage)
        )
