"""Keep optional modules downstream of core and host operations off the HTTP surface."""

from pathlib import Path
from typing import cast

import pytest

from skm.application_bus.registry import AnyCommandSpec, AnyQuerySpec
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ports_uow import Surface

from ._tree import collect, imports
from .test_surface_coverage import SURFACES

_ROOT = Path(__file__).resolve().parents[2]
_CORE = (
    "access",
    "settings",
    "workspace",
    "artifacts",
    "policy",
    "extensions",
    "runtimes",
    "planning",
    "context",
    "execution",
    "integrations",
)
_OPTIONAL = {"knowledge", "learning", "exports"}


@pytest.mark.parametrize("module", _CORE)
def test_required_module_does_not_import_optional_modules(module: str) -> None:
    prefix = f"skm.modules.{module}"
    sources = [
        source for source in collect(_ROOT) if source.name == prefix or source.name.startswith(prefix + ".")
    ]
    assert sources, module
    forbidden = tuple(f"skm.modules.{name}." for name in sorted(_OPTIONAL))
    assert not [
        (source.display_path, ref.line, target)
        for source in sources
        for ref in imports(source)
        for target in ref.targets
        if (target + ".").startswith(forbidden)
    ]


def test_optional_operations_are_routed_or_internal() -> None:
    assert {manifest.id for manifest in MANIFESTS if not manifest.optional} == set(_CORE)
    assert {manifest.id for manifest in MANIFESTS if manifest.optional} == _OPTIONAL
    operations = {
        spec.name: spec
        for manifest in MANIFESTS
        if manifest.optional
        for raw in (*manifest.commands, *manifest.queries)
        for spec in (cast("AnyCommandSpec | AnyQuerySpec", raw),)
    }
    ledger = {name: routes for name, (_, routes) in SURFACES.items() if name.split(".")[0] in _OPTIONAL}
    assert set(ledger) == {name for name, spec in operations.items() if not spec.internal}
    assert all(ledger.values())

    expected = {(name, method, path) for name, routes in ledger.items() for method, path in routes}
    actual = [
        route
        for route in build_route_table(MODULE_IDS).describe()
        if route.bus_name.split(".")[0] in _OPTIONAL
    ]
    assert {(route.bus_name, route.method, route.path) for route in actual} == expected
    for route in actual:
        assert not route.internal


def test_api_routes_exclude_host_operations() -> None:
    host_ops = [operation for manifest in MANIFESTS for operation in manifest.host_operations]
    assert host_ops
    assert all(Surface.API not in operation.surfaces for operation in host_ops)
    host_names = {operation.name for operation in host_ops}
    host_requests = {operation.request for operation in host_ops}
    for route in build_route_table(MODULE_IDS).describe():
        assert route.bus_name not in host_names
        assert route.dto_type not in host_requests
        assert route.dto_type.SCHEMA_URN.split(":")[3] in {"command", "query"}
