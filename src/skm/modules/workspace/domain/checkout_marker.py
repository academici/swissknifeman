"""Checkout marker ``urn:skm:workspace:checkout-marker:v1`` (workspace §4.2).

The marker is a hint written by the client into ``<checkout>/.skm/project.json``. It names IDs but is never
an authority: the server decides (``attach.decide_attach``) after checking that the named target exists in
its own instance and workspace."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.json_types import JsonObject

from .mount import MountName

__all__ = ["MARKER_SCHEMA", "CheckoutMarker", "marker_for", "marker_from_document", "marker_to_document"]

MARKER_SCHEMA: Final = "urn:skm:workspace:checkout-marker:v1"
_FIELDS: Final = frozenset(
    {"schema", "instance_id", "workspace_id", "project_id", "repository_id", "mount_name"}
)


@dataclass(frozen=True, slots=True)
class CheckoutMarker:
    instance_id: UUID
    workspace_id: WorkspaceId
    project_id: ProjectId
    repository_id: RepositoryId
    mount_name: MountName


def marker_for(
    *,
    instance_id: UUID,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    repository_id: RepositoryId,
    mount_name: MountName,
) -> CheckoutMarker:
    return CheckoutMarker(
        instance_id=instance_id,
        workspace_id=workspace_id,
        project_id=project_id,
        repository_id=repository_id,
        mount_name=mount_name,
    )


def marker_to_document(marker: CheckoutMarker) -> JsonObject:
    """The JSON document written to the marker file."""
    return {
        "schema": MARKER_SCHEMA,
        "instance_id": str(marker.instance_id),
        "workspace_id": str(marker.workspace_id),
        "project_id": str(marker.project_id),
        "repository_id": str(marker.repository_id),
        "mount_name": marker.mount_name.value,
    }


def _invalid(reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, "invalid checkout marker", details={"field": "marker", "reason": reason}
    )


def _uuid(value: object, field: str) -> UUID:
    # The schema's uuid format is the canonical lower-case hyphenated form.
    if isinstance(value, str):
        try:
            parsed = UUID(value)
        except ValueError:
            parsed = None
        if parsed is not None and str(parsed) == value:
            return parsed
    raise _invalid(f"{field}_not_a_uuid")


def marker_from_document(document: Mapping[str, object]) -> CheckoutMarker:
    """Strict reader: the schema URN, exactly the six fields, canonical UUIDs and a valid mount name."""
    if document.get("schema") != MARKER_SCHEMA:
        raise _invalid("wrong_schema")
    if frozenset(document) != _FIELDS:
        raise _invalid("unexpected_or_missing_fields")
    mount_name = document["mount_name"]
    if not isinstance(mount_name, str):
        raise _invalid("mount_name_not_a_string")
    return CheckoutMarker(
        instance_id=_uuid(document["instance_id"], "instance_id"),
        workspace_id=WorkspaceId(_uuid(document["workspace_id"], "workspace_id")),
        project_id=ProjectId(_uuid(document["project_id"], "project_id")),
        repository_id=RepositoryId(_uuid(document["repository_id"], "repository_id")),
        mount_name=MountName(mount_name),
    )
