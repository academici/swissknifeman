"""Host operations of the ``extensions`` module (extensions §4.8, §4.9)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.modules.extensions.host.check_upstream import SPEC as CHECK_UPSTREAM_SPEC
from skm.modules.extensions.host.install_pack import SPEC as INSTALL_PACK_SPEC

if TYPE_CHECKING:
    from skm.kernel.module_manifest import HostOperationSpec

__all__ = ["HOST_OPERATIONS"]

HOST_OPERATIONS: tuple[HostOperationSpec, ...] = (
    INSTALL_PACK_SPEC,
    CHECK_UPSTREAM_SPEC,
)
