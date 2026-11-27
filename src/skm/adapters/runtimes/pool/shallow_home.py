"""Create private session homes and durably copy credentials from and to the account wallet."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, cast

from skm.adapters.runtimes._cli_session.launch import ensure_private_dir
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.logging.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ShallowHome",
    "fingerprint_credentials",
    "paths_overlap",
    "read_wallet_credentials",
    "validate_directory",
    "validate_host_links",
    "write_wallet_credentials",
]

_LOG = get_logger("adapters.runtimes")
_MAX_CREDENTIAL_BYTES = 1024 * 1024
_LINK_STATE = ".skm-host-links.json"
_CREDENTIALS = {
    "claude_code": ".credentials.json",
    "codex": "auth.json",
    "gemini_cli": ".gemini/oauth_creds.json",
}


def _invalid(message: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, message)


def _is_within(path: Path, directory: Path) -> bool:
    if sys.platform == "darwin":
        return Path(str(path).casefold()).is_relative_to(Path(str(directory).casefold()))
    return path.is_relative_to(directory)


def paths_overlap(first: Path, second: Path) -> bool:
    return _is_within(first, second) or _is_within(second, first)


def validate_directory(path: Path, *, owned_from: Path | None = None) -> Path:
    """Check the lexical path, including pre-existing parents, before mkdir or chmod."""
    if ".." in path.parts or "\0" in str(path):
        raise _invalid("invalid provider directory path")
    path = path.absolute()
    boundary = owned_from.absolute() if owned_from is not None else path
    for candidate in (*reversed(path.parents), path):
        try:
            facts = candidate.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(facts.st_mode):
            raise _invalid("provider directory path includes a symlink or non-directory")
        if candidate.is_relative_to(boundary) and facts.st_uid != os.geteuid():
            raise _invalid("provider directory must be owned by the effective user")
    return path


def _link_path(name: str) -> Path:
    path = Path(name)
    parts = tuple(part.casefold() for part in path.parts)
    if (
        not parts
        or path.is_absolute()
        or PureWindowsPath(name).drive
        or "\\" in name
        or "\0" in name
        or any(
            part in {"..", "library"} or part.startswith((".claude", ".codex", ".gemini")) for part in parts
        )
        or parts[0] in {"tmp", "auth.json", ".credentials.lock", _LINK_STATE}
    ):
        raise _invalid("invalid host file link for shallow home")
    return path


def validate_host_links(names: tuple[str, ...]) -> tuple[Path, ...]:
    paths = tuple(map(_link_path, names))
    for index, path in enumerate(paths):
        if any(paths_overlap(path, other) for other in paths[:index]):
            raise _invalid("overlapping host file links for shallow home")
    return paths


def _read_bounded(path: Path, *, private: bool) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        facts = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(facts.st_mode)
            or facts.st_size > _MAX_CREDENTIAL_BYTES
            or (private and (facts.st_uid != os.geteuid() or facts.st_mode & 0o077 or facts.st_nlink != 1))
        ):
            raise _invalid(
                "provider credential file must be a bounded regular file with appropriate permissions"
            )
        data = stream.read(_MAX_CREDENTIAL_BYTES + 1)
        if len(data) > _MAX_CREDENTIAL_BYTES:
            raise _invalid("provider credential file exceeds 1 MiB")
        return data


def fingerprint_credentials(path: Path) -> str | None:
    """Return a bounded, no-follow credential digest without exposing credential content."""
    try:
        return "sha256:" + hashlib.sha256(_read_bounded(path, private=False)).hexdigest()
    except (OSError, ValidationFailed):
        return None


def _validate_credentials(data: bytes) -> None:
    try:
        if len(data) > _MAX_CREDENTIAL_BYTES or not isinstance(json.loads(data), dict):
            raise ValueError
    except (ValueError, RecursionError):
        raise _invalid("provider credentials contain invalid JSON") from None


def _read_credentials(path: Path) -> bytes | None:
    try:
        data = _read_bounded(path, private=True)
    except FileNotFoundError:
        return None
    _validate_credentials(data)
    return data


def read_wallet_credentials(path: Path) -> bytes | None:
    """Recover from an invalid or missing current file under the caller's wallet lock."""
    validate_directory(path.parent)
    failure = None
    try:
        current = _read_credentials(path)
        if current is not None:
            return current
    except ValidationFailed as exc:
        failure = exc
    previous = _read_credentials(path.with_name(path.name + ".prev"))
    if previous is None:
        if failure is not None:
            raise failure
        return None
    atomic_write(path, previous, mode=0o600, private=True)
    _LOG.warning("runtimes.provider_wallet_recovered", credential=path.name)
    return previous


def write_wallet_credentials(path: Path, data: bytes) -> None:
    """Back up the previous token before replacing it with validated credentials under the wallet lock."""
    _validate_credentials(data)
    current = read_wallet_credentials(path)
    if current == data:
        return
    if current is not None:
        atomic_write(path.with_name(path.name + ".prev"), current, mode=0o600, private=True)
    try:
        atomic_write(path, data, mode=0o600, private=True)
    except OSError:
        # A directory fsync can fail after rename. A partial file is handled on the next read.
        with suppress(OSError, ValidationFailed):
            if current is not None and _read_credentials(path) == data:
                atomic_write(path, current, mode=0o600, private=True)
        raise


def _sync_host_links(home: Path, desired: dict[Path, Path]) -> None:
    record = home / _LINK_STATE
    document = _read_credentials(record)
    existing: dict[Path, Path] = {}
    if document is not None:
        for name, value in cast("dict[str, object]", json.loads(document)).items():
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise _invalid("invalid shallow home link state")
            existing[_link_path(name)] = Path(value)
    for name in existing.keys() | desired.keys():
        target = home / name
        validate_directory(target.parent, owned_from=home)
        try:
            source = target.readlink()
        except FileNotFoundError:
            continue
        except OSError:
            raise _invalid("shallow home link would replace an existing file") from None
        if source not in (existing.get(name), desired.get(name)):
            raise _invalid("shallow home link target is not managed")
        if source != desired.get(name):
            target.unlink()

    if not desired and not existing:
        return
    planned = json.dumps({str(name): str(source) for name, source in (existing | desired).items()})
    atomic_write(record, planned.encode(), mode=0o600, private=True)
    for name, source in desired.items():
        target = home / name
        if target.parent != home:
            ensure_private_dir(target.parent)
        try:
            target.symlink_to(source)
        except FileExistsError:
            if not target.is_symlink() or target.readlink() != source:
                raise _invalid("shallow home link would replace an existing file") from None
    if existing.keys() - desired.keys():
        committed = json.dumps({str(name): str(source) for name, source in desired.items()})
        atomic_write(record, committed.encode(), mode=0o600, private=True)


@dataclass(frozen=True, slots=True)
class ShallowHome:
    session_home: Path
    wallet: Path
    host_home: Path | None = None
    symlink_host_files: tuple[str, ...] = ()
    write_back: bool = True

    def validate(self, *, workdir: Path | None = None, reserved: Iterable[Path] = ()) -> None:
        home = validate_directory(self.session_home)
        wallet = validate_directory(self.wallet)
        forbidden = (*reserved, *((workdir.resolve(),) if workdir is not None else ()))
        if paths_overlap(home, wallet) or any(
            paths_overlap(target, path) for target in (home, wallet) for path in forbidden
        ):
            raise _invalid("provider session home or wallet overlaps another protected directory")
        self._host_links(home, wallet, forbidden)

    def _host_links(self, home: Path, wallet: Path, forbidden: tuple[Path, ...]) -> dict[Path, Path]:
        links = validate_host_links(self.symlink_host_files)
        desired: dict[Path, Path] = {}
        if links and self.host_home is None:
            raise _invalid("host home is required for shallow home links")
        if self.host_home is not None:
            host = self.host_home.resolve()
            if any(_is_within(host, path) for path in (home, wallet)):
                raise _invalid("provider session home or wallet contains the host home")
            for link in links:
                source = (host / link).resolve()
                if not source.is_relative_to(host):
                    raise _invalid("shallow home link escapes the host home")
                resolved = _link_path(str(source.relative_to(host)))
                if ".ssh" in map(str.casefold, resolved.parts) and ".ssh" not in map(
                    str.casefold, link.parts
                ):
                    raise _invalid("shallow home SSH links require explicit .ssh opt-in")
                if any(paths_overlap(source, path) for path in (home, wallet, *forbidden)):
                    raise _invalid("shallow home link overlaps a protected directory")
                parent = (home / link).parent
                validate_directory(parent, owned_from=home)
                if source.exists():
                    desired[link] = source
        return desired

    def prepare(self, runtime_id: str, *, workdir: Path | None = None) -> Path:
        self.validate(workdir=workdir)
        home = self.session_home
        writable_dirs = [home, self.wallet, home / "tmp"]
        if sys.platform == "darwin":
            writable_dirs.append(home / "Library")
        if runtime_id == "gemini_cli":
            writable_dirs.append(home / ".gemini")
        for path in writable_dirs:
            validate_directory(path, owned_from=home if path.is_relative_to(home) else self.wallet)
        for path in writable_dirs:
            ensure_private_dir(path)
        if runtime_id == "claude_code":
            config = home / ".claude.json"
            try:
                _read_credentials(config)
            except OSError:
                raise _invalid("invalid isolated Claude configuration") from None
            if not config.exists():
                atomic_write(config, b"{}\n", mode=0o600, private=True)
        reserved = (workdir.resolve(),) if workdir is not None else ()
        _sync_host_links(home, self._host_links(home, self.wallet, reserved))
        return home

    def stage(self, runtime_id: str) -> bytes | None:
        name = _CREDENTIALS.get(runtime_id)
        if name is None:
            return None
        session_file = self.session_home / name
        validate_directory(session_file.parent, owned_from=self.session_home)
        data = read_wallet_credentials(self.wallet / Path(name).name)
        if data is None:
            session_file.unlink(missing_ok=True)
        else:
            atomic_write(session_file, data, mode=0o600, private=True)
        return data

    def persist(self, runtime_id: str, original: bytes | None) -> None:
        name = _CREDENTIALS.get(runtime_id)
        if not self.write_back or name is None:
            return
        session_file = self.session_home / name
        validate_directory(session_file.parent, owned_from=self.session_home)
        updated = _read_credentials(session_file)
        if updated is not None and updated != original:
            write_wallet_credentials(self.wallet / Path(name).name, updated)
