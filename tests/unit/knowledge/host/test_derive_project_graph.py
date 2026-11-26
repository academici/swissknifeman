"""Manifest ecosystems label a project graph without a KeyError (I-03.3)."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest

from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostContext
from skm.kernel.cancel import CancelSource
from skm.kernel.gateways import Gateways
from skm.kernel.ids import HostId, ProjectId, RepositoryId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.knowledge.host.derive_project_graph import derive_project_graph
from skm.modules.knowledge.ports import GraphCheckoutResolver, ManifestReader

# Contract labels. These are not read from ``ECOSYSTEMS``.
_ECOSYSTEM_LANGUAGES: dict[str, str | None] = {
    "python": "python",
    "node": "javascript",
    "php": "php",
    "cargo": "rust",
    "go": "go",
    "ruby": "ruby",
    "brew": "brew",
    "dart": "dart",
    "jvm": "java",
    "pypi": "python",
    "npm": "javascript",
    "composer": "php",
    "unknown-ecosystem": None,
}


class _Reader:
    def __init__(self, records: tuple[JsonObject, ...]) -> None:
        self.records = records

    def dependencies(self, root: object) -> tuple[JsonObject, ...]:
        del root
        return self.records

    def read_snapshot(self, root: str) -> tuple[str, tuple[JsonObject, ...]]:
        del root
        return "2026-11-23T00:00:00+00:00", self.records


class _Config:
    def get(self, key: str) -> object:
        if key == "knowledge.graph.enabled":
            return True
        if key == "knowledge.graph.import_max_bytes":
            return 1_000_000
        return None

    def for_project(self, project_id: str) -> _Config:
        del project_id
        return self


class _Client:
    def ask(self, query: object) -> object:
        assert type(query).__name__ == "GetProject"
        return type("Project", (), {"workspace_id": UUID(int=2)})()


class _Gateways:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader

    def get(self, port: type) -> object:
        if port is GraphCheckoutResolver:
            return self
        assert port is ManifestReader
        return self.reader

    def has(self, port: type) -> bool:
        return port is GraphCheckoutResolver

    def resolve_graph(self, project_id: ProjectId, mount: str) -> tuple[RepositoryId, str]:
        assert (project_id, mount) == (ProjectId(UUID(int=1)), "main")
        return RepositoryId(UUID(int=3)), "/checkout"


def _record(ecosystem: str) -> JsonObject:
    return {
        "ecosystem": ecosystem,
        "package": f"{ecosystem}-lib",
        "path": f"{ecosystem}.manifest",
        "relationship": "requires",
        "version": "1",
    }


def test_every_known_ecosystem_and_an_unknown_one_label_without_keyerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[JsonObject] = []

    def _capture(*args: object, **kwargs: object) -> JsonObject:
        del kwargs
        captured.append(cast("JsonObject", args[3]))
        return {"generation": 1}

    monkeypatch.setattr("skm.modules.knowledge.host.derive_project_graph.import_snapshot", _capture)
    request: JsonObject = {"project_id": str(ProjectId(UUID(int=1))), "mount": "main"}
    for ecosystem, language in _ECOSYSTEM_LANGUAGES.items():
        captured.clear()
        ctx = HostContext(
            cast(SkmClient, _Client()),
            cast(Gateways, _Gateways(_Reader((_record(ecosystem),)))),
            HostId(UUID(int=9)),
            _Config(),
            None,
            CancelSource().token,
        )
        derive_project_graph(ctx, request)
        expected: list[JsonValue] = [] if language is None else [language]
        assert captured[0]["languages"] == expected
