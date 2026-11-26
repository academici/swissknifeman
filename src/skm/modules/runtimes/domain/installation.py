"""Host runtime installation model and diffing (runtimes §6, §7.1, §11)."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from skm.kernel.ids import HostId

from .ids import RuntimeId, is_runtime_id, require_utc

__all__ = [
    "AuthState",
    "InstallationDiff",
    "RuntimeInstallation",
    "diff_installations",
    "public_installation_details",
    "public_runtime_version",
]


_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
_VERSION = re.compile(r"v?[0-9][0-9A-Za-z.+_-]{0,99}")
_PUBLIC_DETAILS = {
    "adapter_version": _VERSION,
    "binary_sha256": _DIGEST,
    "executable_sha256": _DIGEST,
    "launch_config_digest": _DIGEST,
    "verification_key": _DIGEST,
    "launch_config_kind": re.compile(r"inventory_probe"),
    "os_kernel": re.compile(r"[A-Za-z]+[:/][0-9A-Za-z][0-9A-Za-z.+_-]{0,99}"),
    "os": re.compile(r"[A-Za-z]+"),
    "kernel": re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,99}"),
}


def public_installation_details(
    details: Mapping[str, str], redact: Callable[[str], str] | None = None
) -> dict[str, str]:
    """The safe installation facts required for worker capability and route binding."""
    return {
        name: value
        for name, pattern in _PUBLIC_DETAILS.items()
        if (value := details.get(name)) is not None
        and pattern.fullmatch(value)
        and (redact is None or redact(value) == value)
    }


def public_runtime_version(version: str | None, redact: Callable[[str], str] | None = None) -> str | None:
    if (
        version is None
        or not _VERSION.fullmatch(version)
        or (redact is not None and redact(version) != version)
    ):
        return None
    return version


class AuthState(StrEnum):
    OK = "ok"
    MISSING = "missing"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RuntimeInstallation:
    host_id: HostId
    runtime_id: RuntimeId
    version: str | None
    binary_locator: str | None
    auth_state: AuthState
    detected_at: datetime
    details: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.host_id, UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"host_id must be a UUID, got {type(self.host_id).__name__}")
        if not is_runtime_id(self.runtime_id):
            raise ValueError(f"not a runtime id: {self.runtime_id!r}")
        if self.version is not None and (
            not isinstance(self.version, str)  # pyright: ignore[reportUnnecessaryIsInstance]
            or not (1 <= len(self.version) <= 100)
        ):
            raise ValueError("version must be None or a non-empty string of at most 100 characters")
        if self.binary_locator is not None and (
            not isinstance(self.binary_locator, str)  # pyright: ignore[reportUnnecessaryIsInstance]
            or not (1 <= len(self.binary_locator) <= 4096)
        ):
            raise ValueError("binary_locator must be None or a non-empty string of at most 4096 characters")
        object.__setattr__(self, "auth_state", AuthState(self.auth_state))
        require_utc(self.detected_at, "detected_at")
        if not isinstance(self.details, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("details must be a mapping of string keys to string values")
        copied: dict[str, str] = {}
        for key, value in self.details.items():
            if not isinstance(key, str) or not (1 <= len(key) <= 100):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValueError(f"invalid installation detail key: {key!r}")
            if not isinstance(value, str) or len(value) > 500:  # pyright: ignore[reportUnnecessaryIsInstance]
                raise ValueError(f"invalid installation detail value for {key!r}")
            copied[key] = value
        object.__setattr__(self, "details", MappingProxyType(copied))

    def __deepcopy__(self, _memo: object) -> RuntimeInstallation:
        return self


@dataclass(frozen=True, slots=True)
class InstallationDiff:
    """Result of comparing currently stored installations on a host against newly observed ones."""

    upserted: tuple[RuntimeInstallation, ...]
    unchanged: tuple[RuntimeInstallation, ...]
    removed: tuple[RuntimeId, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.upserted or self.removed)


def _same_installation_facts(left: RuntimeInstallation, right: RuntimeInstallation) -> bool:
    """Two observations represent the same installation state when all facts except ``detected_at`` match."""
    return (
        left.host_id == right.host_id
        and left.runtime_id == right.runtime_id
        and left.version == right.version
        and left.binary_locator == right.binary_locator
        and left.auth_state == right.auth_state
        and dict(left.details) == dict(right.details)
    )


def diff_installations(
    current: Sequence[RuntimeInstallation],
    observed: Sequence[RuntimeInstallation],
) -> InstallationDiff:
    """Compute changed/new, unchanged, and missing runtime installations for one host (§7.1)."""
    host_ids = {item.host_id for item in current} | {item.host_id for item in observed}
    if len(host_ids) > 1:
        raise ValueError("cannot diff installations belonging to multiple hosts")

    by_id: dict[RuntimeId, RuntimeInstallation] = {}
    for item in current:
        if item.runtime_id in by_id:
            raise ValueError(f"duplicate current installation for {item.runtime_id!r}")
        by_id[item.runtime_id] = item

    seen: set[RuntimeId] = set()
    upserted: list[RuntimeInstallation] = []
    unchanged: list[RuntimeInstallation] = []
    for item in observed:
        if item.runtime_id in seen:
            raise ValueError(f"duplicate observed installation for {item.runtime_id!r}")
        seen.add(item.runtime_id)
        previous = by_id.get(item.runtime_id)
        if previous is not None and _same_installation_facts(previous, item):
            unchanged.append(previous)
        else:
            upserted.append(item)

    removed = tuple(sorted(set(by_id) - seen))
    return InstallationDiff(
        upserted=tuple(upserted),
        unchanged=tuple(unchanged),
        removed=removed,
    )
