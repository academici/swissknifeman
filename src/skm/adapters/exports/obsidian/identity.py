"""Synchronized vault identity and protected local writer authorization."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.ids import HostId
from skm.modules.exports.domain.vault import VaultIdentity

from .vault_fs import LocalVaultFs

__all__ = ["ensure_identity", "read_identity", "require_writer", "update_identity"]

_IDENTITY = ".skm-vault.json"
_MAX_IDENTITY = 8192
_PROBE_VERSION = 1


def _binding_error() -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.INVALID_TRANSITION,
        "Vault requires a current local writer binding and capability probe",
        details={"reason": "vault_writer_unbound"},
    )


def _identity_bytes(identity: VaultIdentity) -> bytes:
    writer = identity.writer_host_id
    return json.dumps(
        {"vault_id": str(identity.vault_id), "writer_host_id": str(writer) if writer else None}
    ).encode()


def read_identity(fs: LocalVaultFs) -> VaultIdentity | None:
    raw = fs.read_bounded(_IDENTITY, max_bytes=_MAX_IDENTITY)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        writer = data["writer_host_id"]
        return VaultIdentity(UUID(data["vault_id"]), HostId(UUID(writer)) if writer is not None else None)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Vault identity is invalid") from None


def ensure_identity(fs: LocalVaultFs) -> VaultIdentity:
    identity = read_identity(fs)
    if identity is None:
        identity = VaultIdentity(uuid4(), None)
        if not fs.create_new(_IDENTITY, _identity_bytes(identity)):
            identity = read_identity(fs)
            if identity is None:
                raise _binding_error()
    return identity


def _binding(fs: LocalVaultFs, identity: VaultIdentity) -> bytes:
    return json.dumps(
        [str(fs.root), str(identity.vault_id), str(identity.writer_host_id), *fs.root_key(), _PROBE_VERSION]
    ).encode()


def require_writer(fs: LocalVaultFs, host_id: HostId) -> VaultIdentity:
    identity = read_identity(fs)
    if identity is None or identity.writer_host_id != host_id:
        raise _binding_error()
    state = fs.state()
    try:
        state.validate_state()
    except FileNotFoundError:
        raise _binding_error() from None
    raw = state.read_bounded(f"vault-{identity.vault_id}.binding", max_bytes=_MAX_IDENTITY)
    if raw != _binding(fs, identity):
        raise _binding_error()
    return identity


def update_identity(
    fs: LocalVaultFs, host_id: HostId, *, fork: bool, deadline_seconds: float
) -> VaultIdentity:
    state = fs.state()
    with state.state_lock("vault-identity.lock", deadline_seconds):
        fs.root_key()
        current = read_identity(fs)
        if fork and current is None:
            raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Vault has no identity to fork")
        if current is None:
            fs.probe()
            return _bind(fs, state, ensure_identity(fs), host_id, probe=False)
        with fs.lock(current.vault_id, deadline_seconds=deadline_seconds):
            if read_identity(fs) != current:
                raise _binding_error()
            if fork:
                forked = VaultIdentity(uuid4(), None)
                fs.write_atomic(_IDENTITY, _identity_bytes(forked), replace=True)
                return forked
            return _bind(fs, state, current, host_id, probe=True)


def _bind(
    fs: LocalVaultFs, state: LocalVaultFs, current: VaultIdentity, host_id: HostId, *, probe: bool
) -> VaultIdentity:
    root_key = fs.root_key()
    if probe:
        fs.probe()
    if read_identity(fs) != current or fs.root_key() != root_key:
        raise _binding_error()
    bound = VaultIdentity(current.vault_id, host_id)
    if bound != current:
        fs.write_atomic(_IDENTITY, _identity_bytes(bound), replace=True)
    state.write_atomic(f"vault-{bound.vault_id}.binding", _binding(fs, bound), replace=True)
    return bound
