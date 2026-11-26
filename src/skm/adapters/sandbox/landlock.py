"""``landlock`` profile: the ``landlock_exec`` prefix around the command (adapters §7.1).

The ruleset restricts writes only, so on its own this backend proves ``fs_write`` and nothing else; read
confinement, network, credentials and the lifecycle must come from companions or the request is refused before
the spawn; a companion counts only with a proof bound to this exact request and a launcher that wraps the
prefix (registry module doc). ``fs_write`` is proven only on ABI >= 3: before it ``truncate(2)`` is not
handled and destroys any same-UID file. Even then the ruleset restricts content writes, not ``chmod``,
``chown``, ``utime`` or ``setxattr`` (landlock.h), and cannot carve a file out of a writable directory, so
same-UID protection of metadata is not provable here. The ruleset binds only the process tree the launcher
starts (``--min-abi`` makes the launcher itself refuse an unsupported kernel): unconfined processes of the
same UID stay unconstrained and a confined command may still ask them to act, so nothing here protects the
user's files from "the same UID" in general. Pre-spawn refusals: a missing or too old ABI, a grant that
reaches ``/tmp``, ``/var/tmp``, ``/dev`` or a personal home, a symlink escaping a protected directory,
any ``protected`` path and any writable root holding Git metadata (a ``.git`` entry, the locator of a linked
worktree included, or a git-dir itself): such requests need a backend that proves the protection (container).
"""

from __future__ import annotations

import os
import platform
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol, override

from skm.adapters.sandbox.backend import BackendIsolation, Companion, SpecView, WrappedProcess, unavailable
from skm.adapters.sandbox.landlock_exec import WrapperError, check_grants, landlock_abi, probe_enforcement
from skm.modules.execution.ports import Isolation
from skm.modules.policy.domain.render import IsolationProperty

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = ["LandlockIsolation", "git_metadata_dirs", "landlock_isolation"]

WRITE_MIN_ABI = 3  # ABI 3 handles TRUNCATE; below it truncate(2) bypasses the ruleset everywhere
_SHARED_DIRS = ("/tmp", "/var/tmp", "/dev")  # noqa: S108 - names of the directories a grant must not reach
_PERSONAL_DIRS = (".claude", ".grok", ".codex", ".cursor")  # whole client directories of the personal home


class LandlockIsolation(Isolation, Protocol):
    """Technology binding of ``Isolation``; the concrete backend is built by ``landlock_isolation``."""


def _inside(path: str, root: str) -> bool:
    return os.path.commonpath((path, root)) == root


def git_metadata_dirs(root: Path) -> tuple[Path, ...]:
    """Resolved git-dir and common-dir of the checkout at ``root`` (``root/.git`` dir or ``gitdir:`` file)."""
    entry = root / ".git"
    if entry.is_dir():
        return (entry.resolve(),)
    if not entry.is_file():
        return ()
    first = entry.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if not first or not first[0].startswith("gitdir:"):
        return ()
    git_dir = (root / first[0].removeprefix("gitdir:").strip()).resolve()
    found = [git_dir]
    marker = git_dir / "commondir"
    if marker.is_file():
        found.append((git_dir / marker.read_text(encoding="utf-8", errors="replace").strip()).resolve())
    return tuple(dict.fromkeys(found))


def _git_entry(root: Path) -> Path | None:
    """The Git metadata that ``root`` is, holds or lies in: a ``.git`` entry (dir, locator file or symlink), a
    git-dir itself (``HEAD`` + ``objects``) or a ``.git`` path component; ``None`` if there is none."""
    entry = root / ".git"
    if entry.is_symlink() or entry.exists():
        return entry
    if (root / "HEAD").is_file() and (root / "objects").is_dir():
        return root
    return next((parent for parent in (root, *root.parents) if parent.name == ".git"), None)


class _LandlockBackend(BackendIsolation):
    profile: ClassVar[str] = "landlock"

    def __init__(
        self,
        *,
        companions: Sequence[Companion],
        require: Sequence[IsolationProperty],
        abi_probe: Callable[[], int],
        home: Path | None,
        python: str,
        enforcement_probe: Callable[[], str | None],
    ) -> None:
        super().__init__(companions=companions, require=require)
        self._abi_probe = abi_probe
        self._home = home
        self._python = python
        self._enforcement_probe = enforcement_probe

    def _abi(self) -> int:
        return self._abi_probe() if platform.system() == "Linux" else 0

    @override
    def proven(self, spec: SpecView) -> Mapping[IsolationProperty, str]:
        abi = self._abi()
        if abi < WRITE_MIN_ABI:  # an unknown or old ABI proves nothing: truncate(2) is not handled
            return {}
        return {
            IsolationProperty.FS_WRITE: f"landlock ABI {abi}: content writes of the wrapped process tree "
            "only beneath explicit grants, inherited by every child; other same-UID processes are not "
            "constrained; no chmod/chown/utime/xattr, read, network, signal, socket, process or quota "
            "guarantee"
        }

    def available(self, host: object) -> JsonObject:  # noqa: ARG002
        if platform.system() != "Linux":
            return {"available": False, "reason": "Landlock is a Linux kernel feature"}
        abi = self._abi()
        if abi < 1:
            return {"available": False, "reason": "the kernel offers no Landlock"}
        if abi < WRITE_MIN_ABI:
            return {
                "available": False,
                "abi": abi,
                "reason": f"Landlock ABI {abi} does not handle truncate; ABI {WRITE_MIN_ABI} is required",
            }
        try:
            failure = self._enforcement_probe()  # the version query alone shows no enforcement
        except OSError as error:  # a probe that cannot even set up is no enforcement, never a crash
            failure = f"the enforcement probe failed ({type(error).__name__}: {error.strerror})"
        if failure is not None:
            return {
                "available": False,
                "abi": abi,
                "reason": f"Landlock ABI {abi} did not confine: {failure}",
            }
        return {
            "available": True,
            "abi": abi,
            "proves": [IsolationProperty.FS_WRITE.value],
            "enforcement": "canary confined by the launcher on this host",
            "constrains": "the process tree started by the launcher, nothing else",
            "does_not_cover": [
                "fs_read",
                "network",
                "chmod_chown_utime_xattr",
                "signals",
                "unix_sockets",
                "quota",
            ],
        }

    def _broad_grant(self, grant: str) -> str | None:
        """Why ``grant`` (resolved) reaches a shared directory or a personal home; ``None`` if narrow."""
        forbidden = [*_SHARED_DIRS]
        if self._home is not None:
            forbidden.append(str(self._home))
            forbidden.extend(str(self._home / name) for name in _PERSONAL_DIRS)
        for directory in forbidden:
            real = os.path.realpath(directory)
            if _inside(real, grant):  # equal to it or an ancestor, so the whole directory is granted
                return real
        return None

    def _check(self, spec: SpecView) -> list[str]:
        writable = [os.path.realpath(path) for path in spec.writable]
        protected = [os.path.realpath(path) for path in spec.protected]
        for original, grant in zip(spec.writable, writable, strict=True):
            broad = self._broad_grant(grant)
            if broad is not None:
                raise unavailable(
                    self.profile,
                    "grant_too_broad",
                    f"write grant {original} would include {broad}",
                    path=str(original),
                    includes=broad,
                )
        for root in writable:
            entry = _git_entry(Path(root))
            if entry is not None:
                metadata = [str(path) for path in git_metadata_dirs(Path(root))]
                raise unavailable(
                    self.profile,
                    "git_metadata_unprotectable",
                    f"Git metadata {entry} lies inside writable {root}"
                    + (f" (it resolves to {', '.join(metadata)})" if metadata else "")
                    + "; Landlock cannot carve a file or directory out of a grant and does not restrict "
                    "chmod/chown/utime/xattr, so a same-UID writer can replace or alter it",
                    path=str(entry),
                )
        try:
            check_grants(writable, protected, [str(path) for path in spec.writable], [])
        except WrapperError as error:
            raise unavailable(self.profile, error.code, error.message, wrapper_code=error.code) from error
        for original, grant in zip(spec.writable, writable, strict=True):
            if not os.path.isdir(grant):  # the ruleset would silently grant less than the request names
                raise unavailable(
                    self.profile,
                    "grant_not_directory",
                    f"write grant {original} is not an existing directory",
                    path=str(original),
                )
        if protected:
            raise unavailable(
                self.profile,
                "protected_metadata_unprovable",
                f"Landlock cannot prove protection of {', '.join(protected)} against the same UID: it does "
                "not restrict chmod, chown, utime or setxattr; use a backend that proves it (container)",
                path=protected[0],
            )
        return writable

    def wrap(self, argv: list[str] | tuple[str, ...], spec: SpecView) -> WrappedProcess:
        if not argv:
            raise ValueError("argv must not be empty")
        abi = self._abi()
        if abi < 1:
            raise unavailable(
                self.profile,
                "LANDLOCK_UNAVAILABLE",
                "the kernel offers no Landlock",
                wrapper_code="LANDLOCK_UNAVAILABLE",
            )
        if abi < WRITE_MIN_ABI:
            raise unavailable(
                self.profile,
                "LANDLOCK_ABI_TOO_OLD",
                f"Landlock ABI {WRITE_MIN_ABI} is required (no truncate control below it), kernel has {abi}",
                wrapper_code="LANDLOCK_ABI_TOO_OLD",
                abi=abi,
            )
        writable = self._check(
            spec
        )  # the grants themselves first: a proof is only asked for a grantable request
        coverage = self.coverage(spec, argv)
        prefix: list[str] = [
            self._python,
            "-P",  # the worktree is cwd and untrusted: it must not shadow the skm package
            "-m",
            "skm.adapters.sandbox.landlock_exec",
            "--no-default-rw",
            "--min-abi",  # the launcher refuses an unsupported kernel itself, whatever was probed here
            str(WRITE_MIN_ABI),
        ]
        for path in writable:
            prefix += ["--rw", path]
        prefix.append("--")
        return WrappedProcess(
            (*coverage.launch, *prefix, *argv), dict(spec.env), spec.workdir, self.ownership(spec, coverage)
        )


def landlock_isolation(
    *,
    companions: Sequence[Companion] = (),
    require: Sequence[IsolationProperty] = (),
    abi_probe: Callable[[], int] = landlock_abi,
    home: Path | None = None,
    python: str = sys.executable,
    enforcement_probe: Callable[[], str | None] | None = None,
) -> Isolation:
    """The Landlock backend; ``home`` (default: the user's) and its client directories are never granted.

    ``enforcement_probe`` (default: the launcher on a canary command) returns ``None`` or why it did not
    confine."""
    resolved_home = home if home is not None else Path.home()
    return _LandlockBackend(  # pyright: ignore[reportReturnType]
        companions=companions,
        require=require,
        abi_probe=abi_probe,
        home=resolved_home,
        python=python,
        enforcement_probe=enforcement_probe or (lambda: probe_enforcement(python, WRITE_MIN_ABI)),
    )
