"""Private secret files of ``skm init``: the ``secrets/`` directory and the token pepper (security S16).

A secret directory must be a real 0700 directory of the process user and a secret file a regular 0600 file of
that user, checked through the opened descriptor; wrong permissions are refused, never repaired. Files are
created by hard-linking a fully written private temporary file into place, so nothing is ever overwritten and
nobody observes a partial file."""

import errno
import json
import os
import secrets
import stat
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.adapters.secrets.keyring import KeyringSecretResolver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.platform.config.secrets import SecretRef, SecretResolvers, SecretValue
from skm.platform.fs.atomic_write import fsync_dir

if TYPE_CHECKING:
    from skm.adapters.http_client.client import HttpSkmClient
    from skm.platform.config.bootstrap import BootstrapConfig
    from skm.platform.generated.results import DoctorResult

__all__ = [
    "PEPPER_BYTES",
    "check_private_dir",
    "create_exclusive",
    "ensure_pepper",
    "ensure_private_dir",
    "http_credential",
    "instance_details",
    "is_http_client",
    "open_http_client",
    "precheck_pepper",
    "read_private",
]

PEPPER_BYTES: Final = 32


def http_credential(
    bootstrap: "BootstrapConfig", environ: Mapping[str, str], on_secret: Callable[[str], None]
) -> SecretValue:
    credential = bootstrap.api_credential
    if isinstance(credential, SecretRef):
        resolvers = (EnvSecretResolver(environ), FileSecretResolver(), KeyringSecretResolver())
        return SecretResolvers(resolvers, on_reveal=on_secret).resolve(credential)
    if credential:
        on_secret(credential)
        return SecretValue(SecretRef.parse("secret://env/SKM_API_TOKEN"), credential)
    raise PreconditionFailed(ErrorCode.SECRET_UNAVAILABLE, "HTTP API credential is required")


def is_http_client(client: object) -> bool:
    from skm.adapters.http_client.client import HttpSkmClient

    return isinstance(client, HttpSkmClient)


def open_http_client(
    bootstrap: "BootstrapConfig",
    environ: Mapping[str, str],
    *,
    as_token: str | None = None,
    credential: SecretValue | None = None,
    on_secret: Callable[[str], None] = lambda _value: None,
    health_details: bool = False,
    run_scope_id: UUID | None = None,
) -> "HttpSkmClient":
    """Open an HTTP client authenticated as the explicit actor or the selected instance credential."""
    from skm.bootstrap._http_mode import build_http_client

    if credential is not None:
        token = credential
    elif as_token is None:
        token = http_credential(bootstrap, environ, on_secret)
    else:
        on_secret(as_token)
        token = SecretValue(SecretRef.parse("secret://env/SKM_API_TOKEN"), as_token)
    return build_http_client(bootstrap, token, health_details=health_details, run_scope_id=run_scope_id)


def instance_details(doctor: "DoctorResult", expected: UUID | None) -> tuple[UUID, int | None]:
    from skm.application_bus.platform.doctor import INSTANCE_CHECK

    try:
        (check,) = (check for check in doctor.checks if check.id == INSTANCE_CHECK)
        data = json.loads(check.details.detail)
        identity = UUID(data["instance_id"])
        version = data["schema_version"]
        if version is not None and type(version) is not int:
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Backend health did not report valid instance details"
        ) from None
    if expected is not None and identity != expected:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "Backend instance_id differs from the configured instance_id",
            details={"expected": str(expected), "actual": str(identity)},
        )
    return identity, version


def _permissions(path: Path, reason: str) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.SECRET_PERMISSIONS,
        "secret storage must be private to the process user",
        details={
            "path": str(path),
            "reason": reason,
            "hint": "fix the owner and mode by hand (directory 0700, file 0600); skm init never repairs them",
        },
    )


def check_private_dir(path: Path) -> None:
    """Accept ``path`` only as a real directory of this user without group/other bits."""
    try:
        info = path.lstat()
    except OSError:
        raise _permissions(path, "unusable_directory") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise _permissions(path, "not_a_directory")
    if info.st_uid != os.geteuid():
        raise _permissions(path, "owner")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise _permissions(path, "mode")


def ensure_private_dir(path: Path) -> None:
    """Create ``path`` (0700) when missing; an existing one must already be private (never chmod-ed)."""
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        raise _permissions(path, "unusable_directory") from None
    check_private_dir(path)


def precheck_pepper(path: Path) -> None:
    """Read-only checks of what already exists, before the database is contacted or anything is written."""
    if os.path.lexists(path.parent):
        check_private_dir(path.parent)
    if os.path.lexists(path):
        _check_pepper(path)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]
    os.fsync(fd)


def create_exclusive(path: Path, data: bytes) -> bool:
    """Write ``path`` (0600) completely or not at all; never replace an existing entry.

    The bytes go to a private temporary file first and are then hard-linked into place: ``link`` fails on an
    existing name, so a concurrent writer or an earlier file always wins and nobody sees a partial file.
    Returns ``False`` when the name already existed.
    """
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        try:
            _write_all(fd, data)
        finally:
            os.close(fd)
        try:
            os.link(temp, path, follow_symlinks=False)
        except FileExistsError:
            return False
        fsync_dir(path.parent)
        return True
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temp)


def read_private(path: Path, limit: int) -> bytes:
    """``FileSecretResolver``'s metadata rule; up to ``limit`` bytes read through the checked descriptor."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise _permissions(path, "symlink") from None
        raise _permissions(path, "unreadable") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise _permissions(path, "not_regular")
        if info.st_uid != os.geteuid():
            raise _permissions(path, "owner")
        if stat.S_IMODE(info.st_mode) & ~0o600:
            raise _permissions(path, "mode")
        if limit <= 0:
            return b""
        with open(fd, "rb", closefd=False) as stream:
            return stream.read(limit)
    finally:
        os.close(fd)


def _check_pepper(path: Path) -> None:
    """The metadata rule of a secret file and a minimum length."""
    text = read_private(path, 4096)
    if len(text.rstrip(b"\r\n")) < PEPPER_BYTES:
        raise PreconditionFailed(
            ErrorCode.SECRET_UNAVAILABLE,
            "the token pepper file is shorter than 32 bytes",
            details={"ref": str(SecretRef("file", str(path))), "reason": "too_short"},
        )


def ensure_pepper(path: Path, *, may_create: bool) -> bool:
    """Reuse a valid pepper; create one only when nothing can have been hashed with a previous pepper yet."""
    ensure_private_dir(path.parent)
    if not os.path.lexists(path):
        if not may_create:
            raise PreconditionFailed(
                ErrorCode.SECRET_UNAVAILABLE,
                "the token pepper of an initialized instance is missing",
                details={
                    "ref": str(SecretRef("file", str(path))),
                    "reason": "missing",
                    "hint": "restore the pepper file; a new pepper would invalidate every issued token",
                },
            )
        if create_exclusive(path, secrets.token_bytes(PEPPER_BYTES).hex().encode("ascii") + b"\n"):
            return True
    _check_pepper(path)
    return False
