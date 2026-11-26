"""Repository: the logical identity of code, and its remotes (workspace §4.2, §4.3, §5.3).

A repository is identified by its module ID. Title, remote URL and ``external_id`` are facts about it, never
its identity: two repositories with the same title or even the same remote are never merged by this module."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import RepositoryId, WorkspaceId

from .remote_url import NormalizedRemote, RepositoryProvider, normalize_remote, provider_of, redact_remote
from .workspace import valid_title

__all__ = [
    "EXTERNAL_ID_MAX",
    "REMOTE_URL_MAX",
    "AddRemoteResult",
    "Repository",
    "RepositoryProvider",
    "RepositoryRemote",
    "add_remote",
    "new_repository",
    "set_primary",
]

EXTERNAL_ID_MAX = 200
REMOTE_URL_MAX = 2048


@dataclass(frozen=True, slots=True)
class Repository:
    id: RepositoryId
    workspace_id: WorkspaceId
    title: str
    canonical_remote: NormalizedRemote | None
    provider: RepositoryProvider
    external_id: str | None
    row_version: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RepositoryRemote:
    repository_id: RepositoryId
    normalized: NormalizedRemote
    display_url: str  # redact_remote(original URL): no user info
    is_primary: bool


@dataclass(frozen=True, slots=True)
class AddRemoteResult:
    repository: Repository
    remotes: tuple[RepositoryRemote, ...]
    changed: bool  # False: the URL was already a remote of this repository, nothing to save or record


def _not_a_network_remote(field: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "the URL is not a network remote",
        details={"field": field, "reason": "not_a_network_remote"},
    )


def _checked_remote(url: str, field: str) -> NormalizedRemote:
    remote = normalize_remote(url) if len(url) <= REMOTE_URL_MAX else None
    if remote is None:
        raise _not_a_network_remote(field)
    return remote


def new_repository(
    *,
    repository_id: RepositoryId,
    workspace_id: WorkspaceId,
    title: str,
    remote_url: str | None,
    external_id: str | None,
    now: datetime,
) -> Repository:
    """``remote_url=None`` is a local repository; a URL that does not normalize is rejected."""
    canonical = None if remote_url is None else _checked_remote(remote_url, "remote_url")
    if external_id is not None and not 1 <= len(external_id) <= EXTERNAL_ID_MAX:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"external_id must be 1..{EXTERNAL_ID_MAX} characters",
            details={"field": "external_id"},
        )
    return Repository(
        id=repository_id,
        workspace_id=workspace_id,
        title=valid_title(title),
        canonical_remote=canonical,
        provider=provider_of(canonical),
        external_id=external_id,
        row_version=1,
        created_at=now,
    )


def _with_primary(
    repository: Repository, remotes: Sequence[RepositoryRemote], primary: NormalizedRemote
) -> tuple[Repository, tuple[RepositoryRemote, ...]]:
    marked = tuple(replace(item, is_primary=item.normalized == primary) for item in remotes)
    if repository.canonical_remote == primary:
        return repository, marked
    updated = replace(
        repository,
        canonical_remote=primary,
        provider=provider_of(primary),
        row_version=repository.row_version + 1,
    )
    return updated, marked


def add_remote(
    repository: Repository, remotes: Sequence[RepositoryRemote], url: str, make_primary: bool
) -> AddRemoteResult:
    """A duplicate is a no-op; ``make_primary`` or the first remote becomes primary and canonical."""
    normalized = _checked_remote(url, "url")
    current = tuple(remotes)
    if any(item.normalized == normalized for item in current):
        return AddRemoteResult(repository, current, changed=False)
    primary = normalized if make_primary or not current else None
    added = RepositoryRemote(
        repository_id=repository.id, normalized=normalized, display_url=redact_remote(url), is_primary=False
    )
    if primary is None:
        return AddRemoteResult(repository, (*current, added), changed=True)
    updated, marked = _with_primary(repository, (*current, added), primary)
    return AddRemoteResult(updated, marked, changed=True)


def set_primary(
    repository: Repository, remotes: Sequence[RepositoryRemote], normalized: NormalizedRemote
) -> AddRemoteResult:
    """Exactly one primary remote, equal to ``canonical_remote``; an unknown remote is ``NOT_FOUND``."""
    current = tuple(remotes)
    if all(item.normalized != normalized for item in current):
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "the repository has no such remote",
            details={"kind": "remote", "ref": normalized.value},
        )
    updated, marked = _with_primary(repository, current, normalized)
    return AddRemoteResult(updated, marked, changed=updated != repository or marked != current)
