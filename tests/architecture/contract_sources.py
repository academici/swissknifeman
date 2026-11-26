"""Contract source discovery and inventory parsing shared by architecture assertions."""

import ast
import importlib
import importlib.util
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource
from referencing.jsonschema import DRAFT202012, Schema

from skm.kernel.module_manifest import ModuleManifest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
MODULES = SOURCE / "skm/modules"


def _cross_imports(source: str, package: str, *, nodes: Iterable[ast.AST] | None = None) -> Iterator[str]:
    walked = nodes if nodes is not None else ast.walk(ast.parse(source))
    for node in walked:
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = importlib.util.resolve_name("." * node.level + name, package)
            if name == "skm.modules" or (name.count(".") == 2 and name.startswith("skm.modules.")):
                yield from (name + "." + alias.name for alias in node.names)
            else:
                yield name


def _inventory_owners(inventory: str) -> dict[str, str]:
    rows = {}
    declaration_table = False
    for line in inventory.splitlines():
        if not line.startswith("|"):
            declaration_table = False
            continue
        cells = line.split("|")
        if len(cells) != 5:
            continue
        if [cell.strip() for cell in cells[1:-1]] == [
            "Schema",
            "Previous declaration",
            "Generated declaration",
        ]:
            declaration_table = True
        if not declaration_table and line.startswith(("| `src/skm/", "| `resources/")):
            rows[cells[1].strip().strip("`")] = cells[3]
    return rows


def _manifests() -> tuple[ModuleManifest, ...]:
    return tuple(
        cast(ModuleManifest, importlib.import_module(_module_name(path)).MODULE)
        for path in sorted(MODULES.glob("*/module.py"))
    )


def _module_name(path: Path) -> str:
    parts = path.relative_to(SOURCE).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _no_retrieve(uri: str) -> Resource[Schema]:
    raise NoSuchResource(ref=uri)


def _schema_registry(documents: Iterable[tuple[str, dict[str, Any]]]) -> Registry[Schema]:
    resources: dict[str, Resource[Schema]] = {}
    for path, document in documents:
        Draft202012Validator.check_schema(document)
        urn = document.get("$id")
        assert isinstance(urn, str), path
        assert urn.startswith("urn:skm:"), path
        assert urn not in resources, f"duplicate schema id: {urn} ({path})"
        resources[urn] = Resource[Schema].from_contents(document)
    return Registry[Schema](retrieve=_no_retrieve).with_resources(resources.items()).crawl()


def _validate_graph(manifests: Iterable[ModuleManifest]) -> None:
    manifests = tuple(manifests)
    graph = {manifest.id: manifest.depends_on for manifest in manifests}
    assert len(graph) == len(manifests), "duplicate module id"
    visited: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        assert name in graph, f"unknown module dependency: {name}"
        assert name not in active, f"module cycle: {name}"
        if name in visited:
            return
        active.add(name)
        for dependency in graph[name]:
            visit(dependency)
        active.remove(name)
        visited.add(name)

    for name in graph:
        visit(name)


def _validate_imports(
    source: str, package: str, owner: ModuleManifest, *, nodes: Iterable[ast.AST] | None = None
) -> None:
    for name in _cross_imports(source, package, nodes=nodes):
        parts = name.split(".")
        if parts[:2] != ["skm", "modules"]:
            continue
        assert len(parts) >= 3, f"unbounded module import: {name}"
        if parts[2] == owner.id:
            continue
        assert parts[2] in owner.depends_on, f"undeclared direct dependency: {name}"
        assert len(parts) >= 4, f"unbounded module import: {name}"
        assert parts[3] == "public", f"private module import: {name}"


def _validate_references(document: dict[str, Any], registry: Registry[Schema]) -> None:
    def visit(node: Any, resolver: Any) -> None:
        if isinstance(node, dict):
            node = cast(dict[str, Any], node)
            if "$id" in node:
                resolver = resolver.in_subresource(
                    Resource.from_contents(node, default_specification=DRAFT202012)
                )
            for keyword in ("$ref", "$dynamicRef"):
                if keyword in node:
                    resolved = resolver.lookup(node[keyword]).contents
                    assert isinstance(resolved, (dict, bool)), node[keyword]
            for child in node.values():
                visit(child, resolver)
        elif isinstance(node, list):
            for child in cast(list[Any], node):
                visit(child, resolver)

    visit(document, registry.resolver(document["$id"]))
