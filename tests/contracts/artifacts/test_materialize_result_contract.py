"""Artifact host result declarations agree with their domain and wire contracts."""

import json
from dataclasses import fields
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from skm.application_bus.client import StagedBlobRef
from skm.kernel.ids import FileVersionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.materialization import MaterialEntry
from skm.modules.artifacts.host.materialize_files import MaterializeFilesOperation

SCHEMAS = Path(__file__).resolve().parents[3] / "src/skm/schemas"
KERNEL_DEFS: JsonObject = json.loads((SCHEMAS / "kernel/defs.v1.json").read_text())
ARTIFACT_DEFS: JsonObject = json.loads((SCHEMAS / "artifacts/defs.v1.json").read_text())
RESULT_SCHEMA: JsonObject = json.loads(
    (SCHEMAS / "artifacts/host-results/materialize-files.v1.json").read_text()
)
REGISTRY = Registry[Schema]().with_resources(
    (str(document["$id"]), Resource[Schema].from_contents(document))
    for document in (KERNEL_DEFS, ARTIFACT_DEFS)
)


def test_materialize_operation_returns_artifact_owned_entries() -> None:
    assert get_type_hints(MaterializeFilesOperation.__call__)["return"] == tuple[MaterialEntry, ...]


def test_materialize_result_entry_fields_match_domain() -> None:
    items = RESULT_SCHEMA["items"]
    assert isinstance(items, dict)
    properties = items["properties"]
    required = items["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    assert {field.name for field in fields(MaterialEntry)} == set(properties) == set(required)


@pytest.mark.parametrize("entry_count", [0, 2])
def test_materialize_result_accepts_arrays_of_domain_entries(entry_count: int) -> None:
    entries = tuple(
        MaterialEntry(
            file_version_id=FileVersionId(UUID(f"01900000-0000-7000-8000-{index + 1:012x}")),
            relative_path=f"01900000-0000-7000-8000-{index + 1:012x}/content.txt",
            size_bytes=index,
            digest=ContentDigest("sha256:" + "a" * 64),
        )
        for index in range(entry_count)
    )
    wire: list[JsonValue] = [
        {
            "file_version_id": str(entry.file_version_id),
            "relative_path": entry.relative_path,
            "size_bytes": entry.size_bytes,
            "digest": entry.digest.value,
        }
        for entry in entries
    ]
    Draft202012Validator(RESULT_SCHEMA, registry=REGISTRY).validate(wire)


@pytest.mark.parametrize("result", [{}, {"entries": []}])
def test_materialize_result_rejects_object_results(result: JsonObject) -> None:
    with pytest.raises(ValidationError):
        Draft202012Validator(RESULT_SCHEMA, registry=REGISTRY).validate(result)


def test_staged_blob_ref_docstring_resolves_actual_owner_definition() -> None:
    reference = "urn:skm:artifacts:defs:v1#/$defs/staged_blob_ref"
    assert reference in (StagedBlobRef.__doc__ or "")
    definitions = ARTIFACT_DEFS["$defs"]
    assert isinstance(definitions, dict)
    assert REGISTRY.resolver().lookup(reference).contents == definitions["staged_blob_ref"]
