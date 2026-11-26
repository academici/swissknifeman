"""Checkout marker document (workspace §4.2): a hint with a strict reader, never an authority."""

import json
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.modules.workspace.domain.checkout_marker import (
    MARKER_SCHEMA,
    CheckoutMarker,
    marker_for,
    marker_from_document,
    marker_to_document,
)
from skm.modules.workspace.domain.mount import MountName
from skm.modules.workspace.generated.documents import checkout_marker_doc_from_json

INSTANCE = UUID(int=10)
WORKSPACE = WorkspaceId(UUID(int=11))
PROJECT = ProjectId(UUID(int=12))
REPOSITORY = RepositoryId(UUID(int=13))


def _marker() -> CheckoutMarker:
    return marker_for(
        instance_id=INSTANCE,
        workspace_id=WORKSPACE,
        project_id=PROJECT,
        repository_id=REPOSITORY,
        mount_name=MountName("main"),
    )


def test_document_round_trips() -> None:
    marker = _marker()
    assert marker_from_document(marker_to_document(marker)) == marker


def test_document_survives_json_text() -> None:
    text = json.dumps(marker_to_document(_marker()))
    assert marker_from_document(json.loads(text)) == _marker()


def test_document_is_accepted_by_the_generated_schema_codec() -> None:
    document = marker_to_document(_marker())
    assert document["schema"] == MARKER_SCHEMA
    decoded = checkout_marker_doc_from_json(document)
    assert decoded["mount_name"] == "main"
    assert decoded["repository_id"] == str(REPOSITORY)


def _document() -> dict[str, Any]:
    return dict(marker_to_document(_marker()))


def _without(field: str) -> dict[str, Any]:
    document = _document()
    del document[field]
    return document


def _with(**changes: Any) -> dict[str, Any]:
    return {**_document(), **changes}


@pytest.mark.parametrize(
    "document",
    [
        _with(schema="urn:skm:workspace:checkout-marker:v2"),
        _without("schema"),
        _without("instance_id"),
        _without("mount_name"),
        _with(extra="x"),
        _with(instance_id="not-a-uuid"),
        _with(workspace_id=str(WORKSPACE).upper()),  # the schema's uuid is the canonical lower-case form
        _with(project_id=42),
        _with(repository_id=None),
        _with(mount_name="Bad Name"),
        _with(mount_name=""),
        _with(mount_name="x" * 33),
        _with(mount_name=7),
    ],
)
def test_reader_rejects_anything_but_the_exact_document(document: dict[str, Any]) -> None:
    with pytest.raises(ValidationFailed) as err:
        marker_from_document(document)
    assert err.value.code is ErrorCode.SCHEMA_INVALID


def test_mount_name_language() -> None:
    for good in ("main", "a", "docs_2", "x-y", "0" * 32):
        assert MountName(good).value == good
    for bad in ("", "-a", "_a", "A", "a b", "a.b", "x" * 33):
        with pytest.raises(ValidationFailed):
            MountName(bad)
