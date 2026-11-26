"""Host imports over the regular command client."""

from typing import Any, cast

from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.knowledge.generated.host import (
    DeriveProjectGraphRequest,
    DeriveProjectGraphResult,
    ImportCodeGraphRequest,
    ImportCodeGraphResult,
)

from .derive_project_graph import derive_project_graph
from .import_code_graph import import_code_graph

__all__ = ["operations"]


def operations(cli: Any) -> tuple[HostOperationSpec, ...]:
    return (
        HostOperationSpec(
            "knowledge.host.import_code_graph",
            import_code_graph,
            ImportCodeGraphRequest,
            cast("type[object]", ImportCodeGraphResult),
            frozenset({cli}),
        ),
        HostOperationSpec(
            "knowledge.host.derive_project_graph",
            derive_project_graph,
            DeriveProjectGraphRequest,
            cast("type[object]", DeriveProjectGraphResult),
            frozenset({cli}),
        ),
    )
