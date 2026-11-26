"""Resolve keyring references on demand without exposing backend diagnostics."""

from importlib import import_module

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.platform.config.secrets import SecretRef

__all__ = ["KeyringSecretResolver"]


class KeyringSecretResolver:
    scheme = "keyring"

    def resolve(self, ref: SecretRef) -> str:
        if ref.scheme != self.scheme:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Invalid secret reference", details={"reason": "secret_ref_invalid"}
            )
        service, name = ref.path.split("/", 1)
        try:
            value = import_module("keyring").get_password(service, name)
        except Exception:  # noqa: BLE001 - optional module, OS backend and its errors are untrusted
            failure = CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE, "Keyring backend is unavailable"
            )
        else:
            if value is None:
                raise PreconditionFailed(ErrorCode.SECRET_UNAVAILABLE, "Keyring entry is unavailable")
            if type(value) is str:
                return value
            failure = CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Invalid keyring response")
        raise failure
