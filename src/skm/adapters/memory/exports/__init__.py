"""Factories for the memory exports repository ports."""

from types import MappingProxyType

from skm.modules.exports.ports import VaultNoteRepository

from .repositories import MemoryVaultNoteRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: MappingProxyType[type, type] = MappingProxyType(
    {VaultNoteRepository: MemoryVaultNoteRepository}
)
