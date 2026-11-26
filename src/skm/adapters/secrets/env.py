"""Resolve only the explicitly supplied environment snapshot; never consult process globals."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.config.secrets import SecretRef

__all__ = ["EnvSecretResolver"]


@dataclass(frozen=True, slots=True, init=False)
class EnvSecretResolver:
    scheme: str = field(default="env", init=False)
    _environ: Mapping[str, str] = field(repr=False)

    def __init__(self, environ: Mapping[str, str]) -> None:
        object.__setattr__(self, "scheme", "env")
        object.__setattr__(self, "_environ", MappingProxyType(dict(environ)))

    def resolve(self, ref: SecretRef) -> str:
        if ref.scheme != self.scheme:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Invalid secret reference", details={"reason": "secret_ref_invalid"}
            )
        value = self._environ.get(ref.path)
        if type(value) is not str:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                "Secret environment variable unavailable",
                details={"ref": str(ref), "reason": "secret_unresolved"},
            )
        return value
