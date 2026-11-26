"""P00 contract declarations; behavior belongs to the owning implementation leaf."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.kernel.module_manifest import HostOperationSpec

HOST_OPERATIONS: tuple[HostOperationSpec, ...] = ()

HOST_OPERATION_NAMES = ("context.host.research_query",)
