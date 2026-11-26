"""Compiling many validators over one shared registry stays linear (settings registry build)."""

from typing import Any

import pytest
from referencing import Registry

from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator


def test_validators_over_one_registry_merge_the_metaschemas_once(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = SchemaRegistry.load_default().dialect_free_registry()
    merges: list[int] = []
    combine = Registry.combine

    def counting(self: Registry[Any], *others: Registry[Any]) -> Registry[Any]:
        merges.append(len(others))
        return combine(self, *others)

    monkeypatch.setattr(Registry, "combine", counting)
    validators = [
        SchemaValidator({"type": "integer", "minimum": low}, registry, dialect_free_inputs=True)
        for low in range(50)
    ]

    assert len(merges) <= 1
    assert validators[10].issues(9)
    assert not validators[10].issues(10)


def test_validators_still_resolve_registry_and_local_references() -> None:
    schemas = SchemaRegistry.load_default()
    registry = schemas.dialect_free_registry()
    urn = next(iter(schemas.urns()))
    local = SchemaValidator(
        {"$defs": {"n": {"type": "integer"}}, "$ref": "#/$defs/n"}, registry, dialect_free_inputs=True
    )
    remote = SchemaValidator({"$ref": urn}, registry, dialect_free_inputs=True)
    meta = SchemaValidator(
        {"$ref": "https://json-schema.org/draft/2020-12/schema"}, registry, dialect_free_inputs=True
    )

    assert local.issues("x")
    assert not local.issues(3)
    assert isinstance(remote.issues({}), tuple)
    assert meta.issues({"type": 5})
    assert not meta.issues({"type": "string"})
