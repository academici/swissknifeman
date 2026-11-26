"""Trusted, repository-local Git excludes and index-only service file removal."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Collection, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed, ValidationFailed
from skm.modules.integrations.domain.conflict_names import DEFAULT_CONFLICT_SUFFIX, conflict_path
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.ports import CheckoutGitExcludes

from .runner import GitCommandFailed, GitRunner, validate_repository_trust
from .status import display_path

__all__ = ["GitInfoExcludes"]

_BEGIN = b"# BEGIN SKM MANAGED EXCLUDES"
_END = b"# END SKM MANAGED EXCLUDES"
_LOCK = "exclude.lock"
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_MAX_BYTES = 1_048_576
_VALID_SUFFIX = re.compile(r"\.[a-z0-9.-]{1,20}")
_SERVICE_PATHS = (".skm", ".skm-dev")
_OPTIONAL_EXCLUDES = {".codegraph/"}
_SERVICE_BYTES = tuple(path.encode() for path in _SERVICE_PATHS)
_SERVICE_PREFIXES = tuple(root + b"/" for root in _SERVICE_BYTES)


def _unsafe(message: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.REPOSITORY_UNSAFE, message)


def _safe_path(path: str) -> bool:
    return (
        is_safe_relative_path(path)
        and all(ord(char) >= 32 and ord(char) != 127 for char in path)
        and all(part.lower() != ".git" for part in path.split("/"))
    )


def _patterns(paths: Collection[str]) -> set[bytes]:
    # A leading slash anchors the match at the worktree root. Quote wildmatch
    # metacharacters and spaces so each pattern matches the literal path.
    return {b"/" + re.sub(rb"([*?\[\] ])", rb"\\\1", os.fsencode(path)) for path in paths}


def _merge(before: bytes, add: set[bytes], remove: set[bytes]) -> bytes:
    lines = before.split(b"\n")
    starts = [i for i, line in enumerate(lines) if line.removesuffix(b"\r") == _BEGIN]
    ends = [i for i, line in enumerate(lines) if line.removesuffix(b"\r") == _END]
    if not starts and not ends:
        return b"\n".join((_BEGIN, *sorted(add), _END, before)) if add else before
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise Conflict(ErrorCode.PROJECTION_CONFLICT, "the SKM block in Git info/exclude is malformed")
    start, end = starts[0], ends[0]
    entries = lines[start + 1 : end]
    existing = {line.removesuffix(b"\r") for line in entries}
    new = add - existing
    if not new and not (remove & existing):
        return before
    remaining = [line for line in entries if line.removesuffix(b"\r") not in remove]
    if remaining or new:
        newline = b"\r" if lines[start].endswith(b"\r") else b""
        block = [lines[start], *remaining, *(line + newline for line in sorted(new)), lines[end]]
    else:
        block = []
    return b"\n".join((*lines[:start], *block, *lines[end + 1 :]))


def _check_owner(info: os.stat_result) -> None:
    if info.st_uid != os.geteuid():
        raise _unsafe("Git info/exclude metadata belongs to another user")


def _snapshot(directory: int) -> tuple[bytes, os.stat_result | None]:
    try:
        fd = os.open("exclude", os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    except FileNotFoundError:
        return b"", None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        _check_owner(info)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _unsafe("Git info/exclude must be a regular file with one link")
        content = stream.read(_MAX_BYTES + 1)
        if len(content) > _MAX_BYTES:
            raise _unsafe("Git info/exclude exceeds the size limit")
        return content, info


@contextmanager
def _locked_exclude(directory: int) -> Generator[int, None, None]:
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(_LOCK, flags, 0o600, dir_fd=directory)
    except FileExistsError as exc:
        raise Conflict(ErrorCode.VERSION_CONFLICT, "Git info/exclude is locked by another writer") from exc
    try:
        yield fd
    finally:
        try:
            held = os.stat(_LOCK, dir_fd=directory, follow_symlinks=False)
            if os.path.samestat(held, os.fstat(fd)):
                os.unlink(_LOCK, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(fd)


def _replace(directory: int, path: Path, fd: int, add: set[bytes], remove: set[bytes]) -> bool:
    before, previous = _snapshot(directory)
    after = _merge(before, add, remove)
    if after == before:
        return False
    if len(after) > _MAX_BYTES:
        raise _unsafe("updated Git info/exclude exceeds the size limit")
    with os.fdopen(os.dup(fd), "wb") as stream:
        stream.write(after)
        stream.flush()
        if previous is not None:
            os.fchmod(fd, stat.S_IMODE(previous.st_mode) & 0o777)
        os.fsync(fd)
    current, current_stat = _snapshot(directory)
    staged = os.stat(_LOCK, dir_fd=directory, follow_symlinks=False)
    if (
        current != before
        or (current_stat is None) != (previous is None)
        or (
            current_stat is not None
            and previous is not None
            and (current_stat.st_mode != previous.st_mode or not os.path.samestat(current_stat, previous))
        )
        or staged.st_nlink != 1
        or not os.path.samestat(staged, os.fstat(fd))
        or not os.path.samestat(path.lstat(), os.fstat(directory))
    ):
        raise Conflict(ErrorCode.VERSION_CONFLICT, "Git info/exclude changed during update")
    os.replace(_LOCK, "exclude", src_dir_fd=directory, dst_dir_fd=directory)
    os.fsync(directory)
    return True


class GitInfoExcludes(CheckoutGitExcludes):
    """Update a trusted checkout's common Git exclude file and its worktree index."""

    def __init__(self, git: GitRunner | None = None) -> None:
        self._git = git if git is not None else GitRunner()

    def _metadata_path(self, checkout: str, *args: str) -> Path:
        validate_repository_trust(checkout)
        root = Path(checkout)
        if not (root / ".git").exists():
            raise _unsafe("SKM Git excludes require a Git checkout root")
        top = self._git.run_bytes(root, ("rev-parse", "--show-toplevel")).stdout.removesuffix(b"\n")
        if Path(os.fsdecode(top)) != root:
            raise _unsafe("SKM Git excludes require the Git checkout root")
        value = self._git.run_bytes(root, ("rev-parse", "--path-format=absolute", *args)).stdout
        path = Path(os.fsdecode(value.removesuffix(b"\n")))
        if not path.is_absolute():
            raise _unsafe("Git returned a non-absolute metadata path")
        return path

    @override
    def sync(
        self,
        checkout: str,
        *,
        conflict_sources: Collection[str] = (),
        conflict_suffix: str = DEFAULT_CONFLICT_SUFFIX,
    ) -> bool:
        conflicts = self._conflict_paths(conflict_sources, conflict_suffix)
        return self._update(checkout, add=set(_SERVICE_PATHS) | conflicts, remove=set())

    def update(
        self,
        checkout: str,
        *,
        add: Collection[str] = (),
        remove: Collection[str] = (),
        conflict_sources: Collection[str] = (),
        conflict_suffix: str = DEFAULT_CONFLICT_SUFFIX,
    ) -> bool:
        """Add or remove selected, allowlisted entries in the managed block."""
        allowed = (
            set(_SERVICE_PATHS) | _OPTIONAL_EXCLUDES | self._conflict_paths(conflict_sources, conflict_suffix)
        )
        added, removed = set(add), set(remove)
        if (added | removed) - allowed or added & removed:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET, "requested paths are outside the SKM exclude allowlist"
            )
        return self._update(checkout, add=added, remove=removed)

    @staticmethod
    def _conflict_paths(sources: Collection[str], suffix: str) -> set[str]:
        if not _VALID_SUFFIX.fullmatch(suffix) or any(not _safe_path(path) for path in sources):
            raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "unsafe projection conflict name")
        return {conflict_path(path, suffix=suffix) for path in sources}

    def _update(self, checkout: str, *, add: set[str], remove: set[str]) -> bool:
        common = self._metadata_path(checkout, "--git-common-dir")
        validate_repository_trust(common)
        try:
            parent = os.open(common, _DIRECTORY)
            try:
                if add:
                    try:
                        os.mkdir("info", dir_fd=parent)
                    except FileExistsError:
                        pass
                    else:
                        os.fsync(parent)
                try:
                    directory = os.open("info", _DIRECTORY, dir_fd=parent)
                except FileNotFoundError:
                    if not add:
                        return False
                    raise
            finally:
                os.close(parent)
            try:
                _check_owner(os.fstat(directory))
                with _locked_exclude(directory) as lock:
                    return _replace(directory, common / "info", lock, _patterns(add), _patterns(remove))
            finally:
                os.close(directory)
        except OSError as exc:
            raise _unsafe("cannot safely update Git info/exclude") from exc

    def _tracked_entries(self, checkout: str) -> dict[bytes, bool]:
        index = self._metadata_path(checkout, "--git-path", "index")
        try:
            info = index.lstat()
        except FileNotFoundError:
            return {}
        _check_owner(info)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _unsafe("the Git index must be a regular file with one link")
        raw = self._git.run_bytes(
            checkout, ("--literal-pathspecs", "ls-files", "--stage", "-z", "--", *_SERVICE_PATHS)
        ).stdout
        entries: dict[bytes, bool] = {}
        for entry in raw.split(b"\0"):
            if entry:
                header, path = entry.split(b"\t", 1)
                mode, _, stage = header.split()
                if path in _SERVICE_BYTES or path.startswith(_SERVICE_PREFIXES):
                    entries[path] = entries.get(path, True) and mode != b"160000" and stage == b"0"
        return entries

    @override
    def require_untracked(self, checkout: str) -> None:
        if entries := self._tracked_entries(checkout):
            raise PreconditionFailed(
                ErrorCode.TRACKED_SERVICE_FILE,
                "The Git index tracks SKM service files",
                details={"paths": [display_path(path) for path in sorted(entries)]},
            )

    @override
    def untrack_service_files(self, checkout: str) -> tuple[str, ...]:
        entries = self._tracked_entries(checkout)
        if not entries:
            return ()
        paths = tuple(display_path(path) for path in sorted(entries))
        if not all(entries.values()):
            raise PreconditionFailed(
                ErrorCode.TRACKED_SERVICE_FILE,
                "resolve unmerged SKM service paths or Git submodules before untracking",
                details={"paths": list(paths)},
            )
        try:
            self._git.run_bytes(
                checkout,
                (
                    "--literal-pathspecs",
                    "rm",
                    "--cached",
                    "--ignore-unmatch",
                    "--pathspec-from-file=-",
                    "--pathspec-file-nul",
                ),
                stdin=b"\0".join(sorted(entries)) + b"\0",
            )
        except GitCommandFailed as exc:
            raise PreconditionFailed(
                ErrorCode.TRACKED_SERVICE_FILE,
                "Git refused to untrack SKM service files. Review staged changes and retry.",
                details={"paths": list(paths), "git_exit_code": exc.exit_code},
            ) from exc
        return paths
