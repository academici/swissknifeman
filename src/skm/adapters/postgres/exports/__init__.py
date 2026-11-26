"""Factories for the PostgreSQL exports repository ports."""

from types import MappingProxyType

from skm.modules.exports.ports import VaultNoteRepository

from .repositories import PostgresVaultNoteRepository

__all__ = ["REPOSITORIES"]

REPOSITORIES: MappingProxyType[type, type] = MappingProxyType(
    {VaultNoteRepository: PostgresVaultNoteRepository}
)
