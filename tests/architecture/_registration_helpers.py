"""Registration and annotation helpers for the repository contract guard."""

import ast
import importlib
import inspect
from typing import Any

from skm.kernel.module_manifest import ModuleManifest

from .contract_registrations import _IMPLEMENTED_REGISTRATIONS


def _assert_registrations(manifest: ModuleManifest) -> None:
    for field in (
        "commands",
        "queries",
        "subscribers",
        "external_consumers",
        "events",
        "host_operations",
    ):
        registered = tuple(_spec_name(item) for item in getattr(manifest, field))
        expected = _IMPLEMENTED_REGISTRATIONS.get((manifest.id, field), ())
        assert registered == expected, f"premature registration: {manifest.id}.{field}"


def _spec_name(item: object) -> str:
    name = getattr(item, "name", getattr(item, "consumer_id", None))
    return name if isinstance(name, str) else getattr(item, "__name__", repr(item))


def _type_checking_names(module: Any) -> dict[str, Any]:
    """Resolve the ``if TYPE_CHECKING:`` imports of ``module`` so its annotations evaluate at runtime."""
    names: dict[str, Any] = {}
    for node in ast.parse(inspect.getsource(module)).body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            for statement in node.body:
                assert isinstance(statement, ast.ImportFrom), ast.dump(statement)
                assert statement.module, ast.dump(statement)
                source = importlib.import_module(statement.module)
                for alias in statement.names:
                    names[alias.asname or alias.name] = getattr(source, alias.name)
    return names
