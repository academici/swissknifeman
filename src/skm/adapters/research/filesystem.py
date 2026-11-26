"""Confined, git-visible local research with descriptor-relative file access."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import monotonic

from skm.adapters.research.command import ProcessSession
from skm.adapters.research.retry import SourceBusy, SourceFailed
from skm.kernel.cancel import CancelToken
from skm.kernel.languages import RESEARCH_SECRET_NAMES, RESEARCH_SKIPPED_DIRS
from skm.modules.context.domain.research import RawDocument, RawSourceReply, ResearchSourceConfig, SourceQuery
from skm.platform.fs.atomic_write import UnsafePathError
from skm.platform.fs.safe_paths import safe_join
from skm.platform.logging.redaction import Redactor

__all__ = ["FilesystemResearchSource"]

SKIPPED_DIRS = RESEARCH_SKIPPED_DIRS
_SECRET_BASENAMES = "|".join(re.escape(name) for name in RESEARCH_SECRET_NAMES if "/" not in name)
SECRET_FILE = re.compile(
    "(?i)("
    r"^\.env($|\.)|"
    rf"^(?:{_SECRET_BASENAMES})$|"
    r"secret|credential|password|token|"
    r"^id_[a-z0-9]+|"
    r"\.(pem|key|p12|pfx|keystore)$"
    ")"
)
FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW


@contextmanager
def directory(path: Path) -> Generator[int]:
    """Open even the trusted absolute root one component at a time without symlinks."""
    fd = os.open("/", FLAGS | os.O_DIRECTORY)
    try:
        for part in path.absolute().parts[1:]:
            child = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextmanager
def file_at(root_fd: int, relative: str) -> Generator[int]:
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise ValueError("path escape")
    parent = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], FLAGS | os.O_NONBLOCK, dir_fd=parent)
        try:
            yield fd
        finally:
            os.close(fd)
    finally:
        os.close(parent)


class FilesystemResearchSource:
    kind = "filesystem"

    def __init__(
        self, *, fs_roots_allow: tuple[str, ...] = (), redact: Callable[[str], str] | None = None
    ) -> None:
        if any(not Path(root).is_absolute() or ".." in Path(root).parts for root in fs_roots_allow):
            raise ValueError("filesystem allow roots must be absolute and canonical")
        self.allowed = tuple(Path(root) for root in fs_roots_allow)
        self.redact = redact or Redactor().text

    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        return () if config.roots and 0 < config.timeout_seconds <= 3600 else ("roots_or_timeout",)

    def roots(self, config: ResearchSourceConfig, query: SourceQuery) -> tuple[tuple[str, Path, Path], ...]:
        roots: list[tuple[str, Path, Path]] = []
        for value in config.roots:
            if ".." in Path(value.split(":", 1)[-1]).parts:
                raise SourceFailed("RESEARCH_SOURCE_INVALID")
            if Path(value).is_absolute():
                root = Path(value).absolute()
                if any(part in SKIPPED_DIRS or SECRET_FILE.search(part) for part in root.parts):
                    raise SourceFailed("RESEARCH_SOURCE_INVALID")
                if not any(root.is_relative_to(allowed) for allowed in self.allowed):
                    raise SourceFailed("RESEARCH_SOURCE_INVALID")
                # Absolute allowlisted host files do not gain repository provenance.
                roots.append(("", root, root))
            else:
                mount, separator, relative = value.partition(":")
                if not separator or mount not in query.mounts:
                    raise SourceFailed("RESEARCH_SOURCE_INVALID")
                base = Path(query.mounts[mount])
                if not base.is_absolute() or ".." in base.parts:
                    raise SourceFailed("RESEARCH_SOURCE_INVALID")
                try:
                    root = safe_join(base, relative or ".")
                except UnsafePathError:
                    raise SourceFailed("RESEARCH_SOURCE_INVALID") from None
                if any(
                    part in SKIPPED_DIRS or SECRET_FILE.search(part) for part in root.relative_to(base).parts
                ):
                    raise SourceFailed("RESEARCH_SOURCE_INVALID")
                roots.append((mount, base, root))
        return tuple(roots)

    def visible(self, root: Path, cancel: CancelToken, timeout: float) -> tuple[str, ...]:
        deadline = monotonic() + timeout
        session = ProcessSession(
            ("git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"),
            {
                "PATH": os.defpath,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_OPTIONAL_LOCKS": "0",
            },
            cancel,
            timeout,
        )
        try:
            raw = session.exchange(b"", allowed_exit_codes=(0, 128))
            in_git = session.owned.exit_code() == 0
        finally:
            session.close()
        if not in_git:
            local_names: list[str] = []
            for index, (parent, dirs, files) in enumerate(os.walk(root, followlinks=False)):
                cancel.raise_if_cancelled()
                if index >= 5000 or len(local_names) >= 5000 or monotonic() >= deadline:
                    break
                dirs[:] = sorted(
                    name for name in dirs if name not in SKIPPED_DIRS and not SECRET_FILE.search(name)
                )
                local_names.extend(
                    str((Path(parent) / name).relative_to(root))
                    for name in sorted(files)[: 5000 - len(local_names)]
                )
            return tuple(local_names)
        names = tuple(name for name in dict.fromkeys(raw.decode("utf-8").split("\0")) if name)
        # --exclude-standard alone does not exclude ignored files already present in the index.
        ignored = ProcessSession(
            ("git", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"),
            {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
            cancel,
            max(0.001, deadline - monotonic()),
        )
        try:
            excluded: set[str] = (
                set(
                    ignored.exchange("\0".join(names).encode() + b"\0", allowed_exit_codes=(0, 1))
                    .decode()
                    .split("\0")
                )
                if names
                else set()
            )
        finally:
            ignored.close()
        return tuple(name for name in names if name not in excluded)

    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply:
        cancel.raise_if_cancelled()
        if self.validate_config(config):
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        deadline = monotonic() + config.timeout_seconds
        terms = set(re.findall(r"\w{2,}", query.text.casefold())) - {"the", "for", "and", "this", "with"}
        matches: list[tuple[int, str, RawDocument]] = []
        examined = 0
        hits = 0
        for mount, base, root in self.roots(config, query):
            with directory(base) as root_fd:
                names = self.visible(base, cancel, max(0.001, deadline - monotonic()))
                for name in names:
                    cancel.raise_if_cancelled()
                    if monotonic() >= deadline:
                        raise SourceBusy("Research source timed out")
                    if examined >= 5000 or hits >= 50:
                        break
                    examined += 1
                    parts = Path(name).parts
                    if any(part in SKIPPED_DIRS or SECRET_FILE.search(part) for part in parts):
                        continue
                    if not (base / name).is_relative_to(root):
                        continue
                    try:
                        with file_at(root_fd, name) as fd:
                            info = os.fstat(fd)
                            if (
                                not stat.S_ISREG(info.st_mode)
                                or info.st_size > 1_000_000
                                or info.st_nlink != 1
                            ):
                                continue
                            data = os.read(fd, 1_000_001)
                        if len(data) > 1_000_000 or b"\0" in data:
                            continue
                        lines = data.decode("utf-8").splitlines()
                    except (OSError, UnicodeError, ValueError):
                        continue
                    selected: list[tuple[int, str, int]] = []
                    for number, line in enumerate(lines, 1):
                        score = sum(term in line.casefold() for term in terms)
                        if score:
                            selected.append((number, line, score))
                            if len(selected) + hits >= 50:
                                break
                    if selected:
                        hits += len(selected)
                        text = self.redact("\n".join(f"{name}:{n}: {line}" for n, line, _ in selected))
                        # Host absolute roots remain external data, even with a repository trust cap.
                        origin = (
                            f"repo:{mount}/{name}"
                            if mount
                            else f"mcp:filesystem/{sha256(str(base).encode()).hexdigest()}/{name}"
                        )
                        locator = {"line_from": selected[0][0], "line_to": selected[-1][0]}
                        matches.append(
                            (
                                sum(score for _, _, score in selected),
                                origin,
                                RawDocument(origin, name, text, locator),
                            )
                        )
        documents = tuple(
            item[2]
            for item in sorted(matches, key=lambda item: (-item[0], item[1]))[: min(query.max_documents, 50)]
        )
        digest = "sha256:" + sha256(repr(documents).encode()).hexdigest()
        return RawSourceReply(documents, None, (), None, digest)

    def checkout_state(
        self, mounts: Mapping[str, str], cancel: CancelToken, *, roots: tuple[str, ...] = ()
    ) -> str | None:
        """Hash complete bounded visible bytes; unknown/incomplete snapshots bypass cache."""
        # A mount-only digest cannot attest to host files outside those mounts.
        if any(Path(root).is_absolute() for root in roots):
            return None
        digest = sha256()
        try:
            for mount, path in sorted(mounts.items()):
                base = Path(path).absolute()
                session = ProcessSession(
                    ("git", "-C", str(base), "rev-parse", "HEAD"), {"PATH": os.defpath}, cancel, 10
                )
                try:
                    digest.update(mount.encode() + b"\0" + session.exchange(b""))
                finally:
                    session.close()
                names = self.visible(base, cancel, 10)
                if len(names) > 5000:
                    return None
                with directory(base) as root_fd:
                    for name in sorted(names):
                        cancel.raise_if_cancelled()
                        if any(part in SKIPPED_DIRS or SECRET_FILE.search(part) for part in Path(name).parts):
                            continue
                        with file_at(root_fd, name) as fd:
                            info = os.fstat(fd)
                            if not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000:
                                return None
                            data = os.read(fd, 1_000_001)
                        if len(data) > 1_000_000:
                            return None
                        digest.update(name.encode() + b"\0" + sha256(data).digest())
            return "sha256:" + digest.hexdigest() if mounts else None
        except (OSError, ValueError, TimeoutError):
            return None
