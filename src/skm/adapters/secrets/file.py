"""Read a process-owned, private regular file through the descriptor whose metadata was checked."""

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.platform.config.secrets import SecretRef

__all__ = ["FileSecretResolver"]


@dataclass(frozen=True, slots=True)
class FileSecretResolver:
    scheme: str = field(default="file", init=False)

    def resolve(self, ref: SecretRef) -> str:
        if ref.scheme != self.scheme:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Invalid secret reference", details={"reason": "secret_ref_invalid"}
            )
        permissions = False
        value = None
        try:
            path = Path(ref.path).expanduser()
            if not path.is_absolute():
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID,
                    "Invalid secret reference",
                    details={"reason": "secret_ref_invalid"},
                )
            # Nonblocking open lets fstat reject FIFOs without waiting for a writer.
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
            try:
                metadata = os.fstat(descriptor)
                permissions = (
                    metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) & ~0o600 != 0
                    or not stat.S_ISREG(metadata.st_mode)
                )
                if not permissions:
                    # The enclosing finally owns the descriptor, including on decode errors.
                    with open(descriptor, encoding="utf-8", newline="", closefd=False) as stream:
                        value = stream.read().rstrip("\r\n")
            finally:
                os.close(descriptor)
        except (OSError, ValueError, RuntimeError):
            # OS/decoder errors can carry data. Do not retain them as cause or context.
            value = None
        if permissions:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                "Secret file must be private and owned by the process user",
                details={"ref": str(ref), "reason": "secret_file_permissions"},
            )
        if value is None:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "Secret file unavailable", details={"ref": str(ref)}
            )
        return value
