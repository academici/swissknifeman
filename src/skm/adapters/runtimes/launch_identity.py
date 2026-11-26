"""Read-only verification of an observed worker CLI executable."""

from collections.abc import Mapping

from ._cli_session.probe import resolve_binary_path, sha256_file

__all__ = ["matches_cli_binary"]


def matches_cli_binary(
    candidate: str,
    *,
    locator: str,
    digest: str,
    environ: Mapping[str, str],
    runtime_id: str,
) -> bool:
    """Resolve and hash the selected binary without invoking it."""
    try:
        binary = resolve_binary_path(candidate, environ=environ, display_name=runtime_id)
        return str(binary) == locator and sha256_file(binary) == digest
    except (OSError, RuntimeError, ValueError):
        return False
