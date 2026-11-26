"""Resolve a worker credential at the bootstrap boundary, before client construction."""

from collections.abc import Callable, Mapping

from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.platform.config.secrets import SecretRef, SecretResolvers

__all__ = ["resolve_worker_credential"]


def resolve_worker_credential(
    reference: str, *, environ: Mapping[str, str], on_reveal: Callable[[str], None]
) -> str:
    resolvers = SecretResolvers((EnvSecretResolver(environ), FileSecretResolver()), on_reveal=on_reveal)
    return resolvers.resolve(SecretRef.parse(reference)).reveal()
