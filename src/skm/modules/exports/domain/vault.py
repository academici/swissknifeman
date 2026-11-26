"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from skm.kernel.ids import HostId


@dataclass(frozen=True, slots=True)
class VaultIdentity:
    vault_id: UUID
    writer_host_id: HostId | None


@dataclass(frozen=True, slots=True)
class VaultLocation:
    root: str
    source: Literal["config", "candidate"]
    obsidian: bool
