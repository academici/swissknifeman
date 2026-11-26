"""Host-side contract of command isolation: what a wrapped command may read, write and reach."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Literal

    from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership


@dataclass(frozen=True, slots=True)
class IsolationSpec:
    workdir: Path
    readable: tuple[Path, ...]
    writable: tuple[Path, ...]
    protected: tuple[Path, ...]
    read_only_root: bool
    network: Literal["none", "allowlist", "full"]
    network_hosts: tuple[str, ...]
    env: Mapping[str, str]
    materials_dir: Path | None
    credential_mounts: tuple[JsonObject, ...]
    owner: ProcessOwner


@dataclass(frozen=True, slots=True)
class WrappedCommand:
    argv: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path
    ownership: ProcessOwnership
    exec_bound: bool = False
