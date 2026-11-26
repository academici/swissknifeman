"""Vault discovery and note delivery on trusted hosts."""

from typing import Any, cast

from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.exports.generated.host import (
    LocateVaultRequest,
    LocateVaultResult,
    PushVaultDocsRequest,
    PushVaultDocsResult,
    PushVaultNotesRequest,
    PushVaultNotesResult,
)

from . import locate_vault, push_vault_docs, push_vault_notes

__all__ = ["operations"]


def operations(cli: Any, worker: Any) -> tuple[HostOperationSpec, ...]:
    return (
        HostOperationSpec(
            "exports.host.locate_vault",
            locate_vault.run,
            LocateVaultRequest,
            cast("type[object]", LocateVaultResult),
            frozenset({cli}),
        ),
        HostOperationSpec(
            "exports.host.push_vault_notes",
            push_vault_notes.run,
            PushVaultNotesRequest,
            cast("type[object]", PushVaultNotesResult),
            frozenset({cli, worker}),
        ),
        HostOperationSpec(
            "exports.host.push_vault_docs",
            push_vault_docs.run,
            PushVaultDocsRequest,
            cast("type[object]", PushVaultDocsResult),
            frozenset({cli}),
        ),
    )
