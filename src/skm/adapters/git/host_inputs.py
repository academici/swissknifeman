"""Pre-Git config admission and durable checkout filesystem bindings."""

from __future__ import annotations

import errno
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import cache
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.json_types import JsonValue

if TYPE_CHECKING:
    from skm.modules.context.ports import ReadOutcome

__all__ = ["GitCheckoutReader", "capture_checkout", "validate_config"]


@cache
def _measured_outcome_type() -> type[Any]:
    from skm.modules.context.ports import ReadOutcome

    @dataclass(frozen=True, slots=True)
    class _MeasuredReadOutcome(ReadOutcome):
        """Keep actual IO cost separate from stat size, including rejected content."""

        bytes_read: int

    return _MeasuredReadOutcome


class GitCheckoutReader:
    """Bounded reads pinned to mount directories, independent of checked pathnames."""

    def __init__(self, mounts: Mapping[str, str | Path], *, baseline: Mapping[str, str] | None = None):
        self._roots = {name: Path(path).resolve(strict=True) for name, path in mounts.items()}
        self._identities = {name: _identity(root) for name, root in self._roots.items()}
        self.baseline = dict(baseline or {})

    def mount_root(self, mount: str) -> str:
        return str(self._roots[mount])

    def _open(self, mount: str, parts: Sequence[str], *, directory: bool = False) -> int:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(self._roots[mount], flags | os.O_DIRECTORY)
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self._identities[mount]:
                raise OSError(errno.ELOOP, "mount identity changed")
            for index, part in enumerate(parts):
                dir_flag = os.O_DIRECTORY if directory or index < len(parts) - 1 else os.O_NONBLOCK
                child = os.open(part, flags | dir_flag, dir_fd=fd)
                os.close(fd)
                fd = child
        except BaseException:
            os.close(fd)
            raise
        else:
            return fd

    def read(self, mount: str, rel_path: str, *, max_bytes: int, follow_symlinks: bool) -> ReadOutcome:
        from skm.modules.context.ports import ReadOutcome
        from skm.platform.fs.atomic_write import UnsafePathError
        from skm.platform.fs.safe_paths import safe_join

        resolved: str | None = None
        try:
            if max_bytes < 0 or "\\" in rel_path or ".." in rel_path.split("/"):
                return ReadOutcome("path_invalid", None, None, None)
            root = self._roots[mount]
            candidate = safe_join(root, rel_path, allow_symlinks=follow_symlinks)
            relative = (candidate.resolve(strict=True) if follow_symlinks else candidate).relative_to(root)
            resolved = relative.as_posix()
            fd = self._open(mount, relative.parts)
            return self._read_fd(fd, resolved, max_bytes)
        except UnsafePathError as error:
            status = (
                "symlink_refused"
                if error.reason == "symlink"
                else "symlink_outside"
                if error.reason == "escapes_root"
                else "path_invalid"
            )
            return ReadOutcome(status, None, None, None)
        except (KeyError, ValueError, RuntimeError):
            return ReadOutcome("path_invalid", None, None, resolved)
        except OSError as error:
            status = (
                "missing"
                if error.errno == errno.ENOENT
                else "symlink_refused"
                if error.errno in {errno.ELOOP, errno.ENOTDIR}
                else "path_invalid"
            )
            return ReadOutcome(status, None, None, resolved)

    @staticmethod
    def _read_fd(fd: int, resolved: str, max_bytes: int) -> ReadOutcome:
        measured = _measured_outcome_type()
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return measured("path_invalid", None, info.st_size, resolved, 0)
            if info.st_size > max_bytes:
                return measured("too_large", None, info.st_size, resolved, 0)
            data = stream.read(max_bytes + 1) if max_bytes else b""
        if len(data) > max_bytes:
            return measured("too_large", None, len(data), resolved, len(data))
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return measured("binary", None, len(data), resolved, len(data))
        if b"\x00" in data[:8192]:
            return measured("binary", None, len(data), resolved, len(data))
        return measured("ok", data, len(data), resolved, len(data))

    def first_existing(
        self, mount: str, rel_dir: str, names: Sequence[str], *, max_bytes: int, follow_symlinks: bool
    ) -> ReadOutcome:
        from skm.modules.context.ports import ReadOutcome

        for name in names:
            if not name or name in {".", ".."} or "/" in name or "\\" in name:
                return ReadOutcome("path_invalid", None, None, None)
            path = f"{rel_dir.rstrip('/')}/{name}" if rel_dir else name
            outcome = self.read(mount, path, max_bytes=max_bytes, follow_symlinks=follow_symlinks)
            if outcome.status != "missing":
                return outcome
        return ReadOutcome("missing", None, None, None)

    def expand(self, mount: str, glob: str, *, limit: int) -> tuple[tuple[str, ...], bool]:
        from skm.modules.context.domain.globs import path_matches

        if (
            limit < 0
            or mount not in self._roots
            or glob.startswith("/")
            or ".." in glob.split("/")
            or "\\" in glob
        ):
            return (), False
        matches: list[str] = []
        scanned = 0

        def visit(parts: tuple[str, ...]) -> bool:
            nonlocal scanned
            if len(parts) >= 64 or scanned >= 10000:
                return True
            try:
                fd = self._open(mount, parts, directory=True)
            except OSError:
                return True
            try:
                with os.scandir(fd) as entries:
                    names = sorted(entry.name for entry in islice(entries, 10001 - scanned))
                for name in names:
                    scanned += 1
                    if scanned > 10000:
                        return True
                    if name == ".git":
                        continue
                    try:
                        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    except OSError:
                        return True
                    child = (*parts, name)
                    if stat.S_ISDIR(info.st_mode):
                        if visit(child):
                            return True
                    elif (
                        stat.S_ISREG(info.st_mode)
                        and info.st_nlink == 1
                        and path_matches("/".join(child), glob)
                    ):
                        matches.append("/".join(child))
                        if len(matches) > limit:
                            return True
            except OSError:
                return True
            finally:
                os.close(fd)
            return False

        truncated = visit(())
        return tuple(matches[:limit]), truncated


_ALLOWED = {
    "core": {
        "repositoryformatversion",
        "filemode",
        "bare",
        "logallrefupdates",
        "ignorecase",
        "precomposeunicode",
    },
    "extensions": {"objectformat", "worktreeconfig"},
}


def read_metadata(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_size > 1_048_576:
            raise ValueError("unsafe metadata file")
        return stream.read(1_048_577)


def _fast_validate_git_config(text: str) -> bool:
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if raw_line.startswith((" ", "\t")) and stripped.startswith("["):
            return False
        if ";" in stripped or "#" in stripped or "\\" in stripped:
            return False
        if stripped.startswith("[") and stripped.endswith("]") and "=" not in stripped:
            section = stripped[1:-1]
            if not section or section == "DEFAULT" or section in sections:
                return False
            current = {}
            sections[section] = current
            continue
        if current is None or "=" not in stripped or ":" in stripped.partition("=")[0]:
            return False
        key, _, val = stripped.partition("=")
        norm_key = key.strip().lower()
        if not norm_key or not norm_key.isalnum() or norm_key in current:
            return False
        current[norm_key] = val.strip()
    for section, mapping in sections.items():
        keys = set(mapping)
        if section in _ALLOWED and keys <= _ALLOWED[section]:
            continue
        if section.startswith('remote "') and section.endswith('"') and keys <= {"url", "fetch", "tagopt"}:
            if "tagopt" in keys and mapping["tagopt"] not in {"--no-tags", "--tags"}:
                return False
            continue
        if section.startswith('branch "') and section.endswith('"') and keys <= {"remote", "merge"}:
            continue
        return False
    return True


def validate_config(path: Path) -> None:
    """Parse data without Git. Unknown directives/includes/helpers are rejected before exec."""
    try:
        if not path.exists() and not path.is_symlink():
            return
        text = read_metadata(path).decode("utf-8")
        if _fast_validate_git_config(text):
            return
    except (OSError, UnicodeError, ValueError) as error:
        raise error_for(
            ErrorCode.REPOSITORY_UNSAFE, "untrusted Git configuration", details={"path": str(path)}
        ) from error
    import configparser

    try:
        parser = configparser.RawConfigParser(strict=True, interpolation=None)
        parser.read_string(text)
        for section in parser.sections():
            keys = set(parser[section])
            if section in _ALLOWED and keys <= _ALLOWED[section]:
                continue
            if (
                section.startswith('remote "')
                and section.endswith('"')
                and keys <= {"url", "fetch", "tagopt"}
            ):
                if "tagopt" in keys and parser[section]["tagopt"] not in {"--no-tags", "--tags"}:
                    raise ValueError("untrusted remote tag option")
                continue  # URLs are inert data; network calls have a separate host policy.
            if section.startswith('branch "') and section.endswith('"') and keys <= {"remote", "merge"}:
                continue
            raise ValueError("config directive is outside the data-only allowlist")
        if parser.defaults():
            raise ValueError("config defaults are not supported")
    except (OSError, UnicodeError, ValueError, configparser.Error) as error:
        raise error_for(
            ErrorCode.REPOSITORY_UNSAFE, "untrusted Git configuration", details={"path": str(path)}
        ) from error


def _identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("checkout metadata is not a real directory")
    return info.st_dev, info.st_ino


def _pair(value: object) -> tuple[int, int]:
    values = cast("list[int]", value)
    return values[0], values[1]


@dataclass(frozen=True)
class CheckoutDescriptor:
    root: str
    git_dir: str
    common_dir: str
    root_identity: tuple[int, int]
    git_identity: tuple[int, int]
    common_identity: tuple[int, int]
    metadata_digest: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> CheckoutDescriptor:
        return cls(
            str(raw["root"]),
            str(raw["git_dir"]),
            str(raw["common_dir"]),
            _pair(raw["root_identity"]),
            _pair(raw["git_identity"]),
            _pair(raw["common_identity"]),
            str(raw["metadata_digest"]),
        )

    def verify(self) -> None:
        try:
            if capture_checkout(Path(self.root)) != self:
                raise ValueError("checkout binding changed")
        except (OSError, ValueError, SkmError) as error:
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "checkout filesystem binding changed") from error


def capture_checkout(root: Path) -> CheckoutDescriptor:
    import hashlib

    from .runner import validate_repository_trust

    validate_repository_trust(root)
    dot = root / ".git"
    pointer = b""
    git_dir = dot
    if dot.is_file():
        pointer = read_metadata(dot)
        target = pointer.decode("utf-8").strip().removeprefix("gitdir:").strip()
        git_dir = Path(os.path.abspath(root / target))
    common_dir = git_dir
    common_pointer = b""
    if (git_dir / "commondir").exists():
        common_pointer = read_metadata(git_dir / "commondir")
        common_dir = Path(os.path.abspath(git_dir / common_pointer.decode().strip()))
    facts: list[object] = []
    for path in (dot, git_dir / "commondir"):
        if path.is_file():
            info = path.lstat()
            facts.append(
                [
                    str(path),
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    hashlib.sha256(read_metadata(path)).hexdigest(),
                ]
            )
    for directory in dict.fromkeys((git_dir, common_dir)):
        for name in ("config", "config.worktree"):
            path = directory / name
            validate_config(path)
            if path.exists():
                info = path.lstat()
                facts.append(
                    [
                        str(path),
                        info.st_dev,
                        info.st_ino,
                        info.st_mode,
                        hashlib.sha256(read_metadata(path)).hexdigest(),
                    ]
                )
    return CheckoutDescriptor(
        str(root),
        str(git_dir),
        str(common_dir),
        _identity(root),
        _identity(git_dir),
        _identity(common_dir),
        hashlib.sha256(json.dumps(facts, separators=(",", ":")).encode()).hexdigest(),
    )


def _pointer_unsafe(message: str, **details: JsonValue) -> NoReturn:
    raise error_for(ErrorCode.REPOSITORY_UNSAFE, message, details=details or None)


def _require_owned_by_current_uid(info: os.stat_result, path: Path) -> None:
    if info.st_uid != os.geteuid():
        _pointer_unsafe("metadata is not owned", path=str(path))


def read_pointer(path: Path, *, max_bytes: int) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        _pointer_unsafe("unable to open git metadata file safely", path=str(path), errno=exc.errno)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            _pointer_unsafe("git metadata pointer is not a regular file", path=str(path))
        _require_owned_by_current_uid(st, path)
        if st.st_size <= 0 or st.st_size > max_bytes:
            _pointer_unsafe(
                "git metadata pointer file size is out of bounds",
                path=str(path),
                size=st.st_size,
                max_bytes=max_bytes,
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, max_bytes + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                _pointer_unsafe(
                    "git metadata pointer file exceeds maximum size",
                    path=str(path),
                    max_bytes=max_bytes,
                )
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if b"\x00" in raw:
        _pointer_unsafe("git metadata pointer contains NUL byte", path=str(path))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        _pointer_unsafe("git metadata pointer is not valid UTF-8", path=str(path))
