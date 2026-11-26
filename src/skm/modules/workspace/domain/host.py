"""Host: a registered machine (workspace §4.2). Pure facts; the server never looks at the machine itself."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId

__all__ = [
    "Host",
    "HostArch",
    "HostName",
    "HostOs",
    "HostPlatform",
    "HostState",
    "new_host",
    "require_active",
]

# Same language as the ``host_name`` definition of ``urn:skm:workspace:defs:v1``.
_HOST_NAME: Final = re.compile(r"[a-z0-9][a-z0-9.-]{0,62}")


class HostOs(StrEnum):
    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"


class HostArch(StrEnum):
    X86_64 = "x86_64"
    ARM64 = "arm64"
    OTHER = "other"


class HostState(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class HostName:
    value: str

    def __post_init__(self) -> None:
        if not _HOST_NAME.fullmatch(self.value):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "host name must match ^[a-z0-9][a-z0-9.-]{0,62}$",
                details={"field": "name", "value": self.value},
            )

    @override
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HostPlatform:
    os: HostOs
    arch: HostArch


@dataclass(frozen=True, slots=True)
class Host:
    id: HostId
    name: str
    platform: HostPlatform
    state: HostState
    registered_at: datetime
    last_seen_at: datetime | None
    row_version: int


def new_host(*, host_id: HostId, name: HostName, platform: HostPlatform, now: datetime) -> Host:
    return Host(
        id=host_id,
        name=name.value,
        platform=platform,
        state=HostState.ACTIVE,
        registered_at=now,
        last_seen_at=None,
        row_version=1,
    )


def require_active(host: Host) -> None:
    if host.state is not HostState.ACTIVE:
        raise PreconditionFailed(
            ErrorCode.INVALID_TRANSITION,
            "the host is retired",
            details={"reason": "host_retired", "host_id": str(host.id)},
        )
