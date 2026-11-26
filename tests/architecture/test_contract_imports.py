"""P00 declarations, actual module graph and offline product-schema closure; no handlers run."""

import importlib
import inspect
import json
import re
from collections.abc import Sequence
from dataclasses import fields, replace
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest
from jsonschema import SchemaError
from referencing.exceptions import Unresolvable

from skm.bootstrap.modules import MODULE_CATALOG
from skm.kernel.ports_uow import PORT_KIND_ATTRIBUTE

from ._registration_helpers import _assert_registrations, _type_checking_names
from .adapter_inventory import _ADAPTER_IMPLEMENTATIONS
from .contract_registrations import EXPECTED_DEPENDENCIES
from .contract_sources import (
    _inventory_owners,
    _manifests,
    _module_name,
    _schema_registry,
    _validate_graph,
    _validate_imports,
    _validate_references,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
PACKAGE = SOURCE / "skm"
MODULES = PACKAGE / "modules"
SCHEMAS = PACKAGE / "schemas"


def test_all_public_boundaries_and_declarations_import() -> None:
    for filename in ("public.py", "ports.py", "module.py"):
        paths = sorted(MODULES.glob(f"*/{filename}"))
        assert len(paths) == 14
        for path in paths:
            module = importlib.import_module(_module_name(path))
            for name in getattr(module, "__all__", ()):
                assert hasattr(module, name), f"{path}: {name}"
    # Import every materialized declaration, including domain/host contracts, without calling it.
    for path in sorted(PACKAGE.rglob("*.py")):
        if "tests" in path.relative_to(PACKAGE).parts:
            continue
        module = importlib.import_module(_module_name(path))
        if (
            path.relative_to(PACKAGE).parts[0] in {"adapters", "background", "bootstrap", "entrypoints"}
            and path != PACKAGE / "entrypoints/cli/main.py"
        ):
            assert hasattr(module, "__all__"), path
        for name in getattr(module, "__all__", ()):
            assert hasattr(module, name), f"{path}: {name}"


def test_actual_manifests_match_normative_graph_and_port_inventory() -> None:
    manifests = _manifests()
    assert len(manifests) == 14
    assert {m.id: m.depends_on for m in manifests} == EXPECTED_DEPENDENCIES
    _validate_graph(manifests)
    assert {m.id for m in manifests if m.optional} == {"knowledge", "learning", "exports"}
    catalog = {entry.id: entry for entry in MODULE_CATALOG}
    assert set(catalog) == set(EXPECTED_DEPENDENCIES)
    for manifest in manifests:
        for field in fields(catalog[manifest.id]):
            assert getattr(manifest, field.name) == getattr(catalog[manifest.id], field.name)
        ports = importlib.import_module(f"skm.modules.{manifest.id}.ports")
        declared_ports = {
            value
            for value in vars(ports).values()
            if inspect.isclass(value)
            and value.__module__ == ports.__name__
            and getattr(value, PORT_KIND_ATTRIBUTE, None) is not None
        }
        assert declared_ports == set(manifest.repository_ports) | set(manifest.gateway_ports)
        for port in manifest.repository_ports:
            assert getattr(port, PORT_KIND_ATTRIBUTE) == "repository"
        for port in manifest.gateway_ports:
            assert getattr(port, PORT_KIND_ATTRIBUTE) in {
                "control_plane_gateway",
                "host_gateway",
                "shared_gateway",
            }
        _assert_registrations(manifest)


# Only the registrations implemented by their owning leaves are permitted, in manifest order.


@pytest.mark.parametrize(
    ("module_id", "field", "change"),
    [
        ("settings", "commands", lambda items: (*items, items[0])),  # an unowned extra registration
        ("settings", "queries", lambda items: items[:-1]),  # a missing registration
        ("settings", "subscribers", lambda _items: (object(),)),  # settings has no subscribers
        ("settings", "host_operations", lambda _items: (object(),)),
        ("access", "commands", lambda _items: (object(),)),  # other modules stay unregistered
        ("artifacts", "commands", lambda items: (*items, items[0])),  # an unowned extra registration
        ("artifacts", "queries", lambda items: items[:-1]),  # a missing registration
        ("artifacts", "subscribers", lambda _items: (object(),)),  # artifacts has no subscribers
        ("artifacts", "host_operations", lambda items: (*items, items[0])),  # an unowned extra registration
        ("artifacts", "host_operations", lambda items: items[:-1]),  # a missing registration
        ("planning", "commands", lambda items: (*items, items[0])),  # an unowned extra registration
        ("planning", "commands", lambda items: items[:-1]),  # a missing registration
        ("planning", "queries", lambda items: (*items, items[0])),  # an unowned extra registration
        ("planning", "queries", lambda items: items[:-1]),  # a missing registration
        ("extensions", "commands", lambda items: (*items, items[0])),  # an unowned extra registration
        ("extensions", "queries", lambda items: items[:-1]),  # a missing registration
        ("extensions", "host_operations", lambda items: (*items, items[0])),  # an unowned extra registration
        ("extensions", "host_operations", lambda items: items[:-1]),  # a missing registration
    ],
)
def test_registration_guard_rejects_unowned_or_missing_registrations(
    module_id: str, field: str, change: Any
) -> None:
    manifest = next(m for m in _manifests() if m.id == module_id)
    _assert_registrations(manifest)
    with pytest.raises(AssertionError, match="premature registration"):
        _assert_registrations(replace(manifest, **{field: change(getattr(manifest, field))}))


@pytest.mark.parametrize("defect", ["unknown", "cycle", "duplicate"])
def test_graph_checker_rejects_invalid_manifests(defect: str) -> None:
    manifest = _manifests()[0]
    invalid = {
        "unknown": (replace(manifest, depends_on=("missing",)),),
        "cycle": (replace(manifest, depends_on=(manifest.id,)),),
        "duplicate": (manifest, manifest),
    }
    with pytest.raises(AssertionError):
        _validate_graph(invalid[defect])


def test_cross_module_imports_use_direct_dependencies_and_public_boundaries(session_root_tree) -> None:
    by_module: dict[str, list[Any]] = {}
    for file in session_root_tree:
        if file.module and file.layer.name != "ADAPTER":
            by_module.setdefault(file.module, []).append(file)
    for manifest in _manifests():
        for file in by_module.get(manifest.id, ()):
            package = _module_name(file.path.parent / "__init__.py")
            _validate_imports(file.text, package, manifest, nodes=file.nodes)


@pytest.mark.parametrize(
    "source",
    [
        "from skm.modules.policy.public import require_permission",  # undeclared dependency
        "from skm.modules.planning.domain import plan",  # private module
        "from ...planning.domain import plan",  # relative private import
        "import skm.modules.planning",  # unbounded dependency
        "from skm.modules import planning",  # unbounded from-import
        "from skm.modules.planning.ports import PlanRepository",  # private port
        "if TYPE_CHECKING:\n    from skm.modules.planning.domain.plan import Plan",
    ],
)
def test_import_checker_rejects_forbidden_boundaries(source: str) -> None:
    context = next(m for m in _manifests() if m.id == "context")
    with pytest.raises(AssertionError):
        _validate_imports(source, "skm.modules.context.domain", context)


def test_import_checker_accepts_public_and_own_relative_imports() -> None:
    context = next(m for m in _manifests() if m.id == "context")
    _validate_imports(
        "from skm.modules.planning import public\n"
        "from skm.modules.artifacts import public as artifacts\n"
        "from . import blocks\n",
        "skm.modules.context.domain",
        context,
    )


def test_all_product_schemas_and_reference_fragments_close_offline() -> None:
    documents = [
        (str(path.relative_to(ROOT)), cast(dict[str, Any], json.loads(path.read_text())))
        for path in sorted(SCHEMAS.rglob("*.json"))
        if path != SCHEMAS / "schema-lock.json" and "data" not in path.relative_to(SCHEMAS).parts
    ]
    assert documents
    registry = _schema_registry(documents)
    for path, document in documents:
        try:
            _validate_references(document, registry)
        except Unresolvable as error:
            pytest.fail(f"{path}: unresolved product schema reference: {error}")


def test_architecture_discovery_excludes_only_the_exact_root_lock(tmp_path: Path, monkeypatch) -> None:
    module = importlib.import_module(__name__)
    monkeypatch.setattr(module, "SCHEMAS", tmp_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "demo").mkdir()
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:skm:demo:sample:v1",
        "type": "string",
    }
    (tmp_path / "demo/sample.v1.json").write_text(json.dumps(document))
    (tmp_path / "schema-lock.json").write_text("not a schema")
    test_all_product_schemas_and_reference_fragments_close_offline()
    for name in ("demo/schema-lock.json", "other-lock.json"):
        path = tmp_path / name
        path.write_text("{}")
        with pytest.raises(AssertionError, match=re.escape(name)):
            test_all_product_schemas_and_reference_fragments_close_offline()
        path.unlink()


@pytest.mark.parametrize(
    "reference",
    [
        "urn:skm:missing:defs:v1",
        "#/$defs/missing",
        "https://example.invalid/schema.json",
    ],
)
def test_schema_checker_rejects_missing_targets_fragments_and_remote_retrieve(reference: str) -> None:
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:skm:test:defs:v1",
        "$ref": reference,
    }
    registry = _schema_registry((("test.json", document),))
    with pytest.raises(Unresolvable):
        _validate_references(document, registry)


def test_schema_checker_rejects_duplicate_ids_and_accepts_local_escaped_pointer() -> None:
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:skm:test:defs:v1",
        "$defs": {"a/b~c": {"type": "string"}},
        "$ref": "#/$defs/a~1b~0c",
    }
    with pytest.raises(AssertionError, match="duplicate schema id"):
        _schema_registry((("first.json", document), ("second.json", document)))
    _validate_references(document, _schema_registry((("test.json", document),)))


def test_schema_checker_rejects_invalid_draft_schema() -> None:
    with pytest.raises(SchemaError):
        _schema_registry((("invalid.json", {"$id": "urn:skm:test:invalid:v1", "type": "invalid"}),))


def test_execution_transition_symbols_are_typed_and_callable() -> None:
    run = importlib.import_module("skm.modules.execution.domain.run")
    task = importlib.import_module("skm.modules.execution.domain.task")
    for module, names in ((run, ("start", "pause", "resume", "cancel", "finish")), (task, ("transition",))):
        localns = _type_checking_names(module)
        for name in names:
            function = getattr(module, name)
            assert callable(function)
            assert name in module.__all__
            hints = get_type_hints(function, localns=localns)
            signature = inspect.signature(function)
            assert set(hints) == set(signature.parameters) | {"return"}


def _assert_discovered_groups(groups: Sequence[Any]) -> None:
    """P02.08.a materializes discovery and the backend-free ``version`` group; later groups add their file.

    So the registry is checked for its invariants (all ``CommandGroup``, unique names, discovery order) and
    for the required ``version`` group, never for the absence of other legitimate groups.
    """
    from skm.entrypoints.cli.commands import CommandGroup

    assert all(isinstance(group, CommandGroup) for group in groups)
    names = [group.name for group in groups]
    assert len(set(names)) == len(names)
    assert list(groups) == sorted(groups, key=lambda group: (group.order, group.name))
    version = [group for group in groups if group.name == "version"]
    assert [(group.requires_backend, group.module) for group in version] == [(False, None)]


def test_a_new_valid_group_does_not_break_the_registry_check() -> None:
    from skm.entrypoints.cli.commands import GROUPS, CommandGroup

    later = CommandGroup(
        name="zz-later", help="h", register=lambda sub: None, requires_backend=True, order=10**6
    )
    _assert_discovered_groups((*GROUPS, later))
    with pytest.raises(AssertionError):
        _assert_discovered_groups(tuple(group for group in GROUPS if group.name != "version"))
    with pytest.raises(AssertionError):
        _assert_discovered_groups((*GROUPS, *GROUPS))


def test_manual_registries_have_no_registrations() -> None:
    from skm.adapters.integrations.registry import TARGETS
    from skm.bootstrap.adapters import REPOSITORY_TABLE
    from skm.bootstrap.runtimes import RUNTIME_FACTORIES
    from skm.bootstrap.services import BACKGROUND_SERVICES
    from skm.entrypoints.api.routes import ROUTES
    from skm.entrypoints.cli.commands import GROUPS, CommandGroup

    assert set(TARGETS) == {"antigravity", "claude_code", "codex", "cursor", "gemini_cli", "grok"}
    assert not REPOSITORY_TABLE
    assert set(RUNTIME_FACTORIES) == {
        "antigravity",
        "claude_code",
        "claude-code",
        "codex",
        "codex-cli",
        "cursor",
        "cursor-agent",
        "gemini_cli",
        "grok",
    }  # P08.03-P08.05
    from skm.background.learning_recompute import LearningRecompute
    from skm.background.lease_sweeper import LeaseSweeper
    from skm.background.memory_expirer import MemoryExpirer
    from skm.background.scheduler import Scheduler
    from skm.background.timeout_enforcer import TimeoutEnforcer
    from skm.bootstrap.services import _janitor, _learning_recompute

    assert [(s.name, s.factory, s.module) for s in BACKGROUND_SERVICES] == [
        ("janitor", _janitor, "exports"),
        ("scheduler", Scheduler, "execution"),
        ("lease_sweeper", LeaseSweeper, "execution"),
        ("timeout_enforcer", TimeoutEnforcer, "execution"),
        ("memory_expirer", MemoryExpirer, "knowledge"),
        (LearningRecompute.name, _learning_recompute, "learning"),
    ]
    from skm.entrypoints.api.routing import Route

    assert isinstance(ROUTES, tuple)
    assert all(isinstance(r, Route) for r in ROUTES)
    _assert_discovered_groups(GROUPS)
    assert {field.name for field in fields(CommandGroup)} == {
        "name",
        "help",
        "register",
        "requires_backend",
        "module",
        "order",
    }


def test_production_composition_has_no_fallback_authorizer() -> None:
    """Without CompositionOverrides ``build_app`` is the production composition (``RbacAuthorizer``, stored
    scope chain, a token pepper required); no production module names AllowAll."""
    from skm.bootstrap.composition import build_app
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import PreconditionFailed
    from skm.kernel.ports_uow import Surface
    from skm.platform.config.bootstrap import load_bootstrap

    bootstrap = load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, ROOT)
    with pytest.raises(PreconditionFailed) as caught:
        build_app(bootstrap, surface=Surface.CLI, environ={}, invocation={})
    assert caught.value.code is ErrorCode.SECRET_UNAVAILABLE
    for path in PACKAGE.rglob("*.py"):
        assert "allowall" not in path.read_text().lower().replace("_", ""), path


# Only the concrete exports implemented by their owning leaves are permitted.


def _assert_adapter_bindings(module: object, expected: set[str]) -> None:
    actual = set()
    for name in vars(module)["__all__"]:
        declaration = getattr(module, name)
        if not inspect.isclass(declaration):
            continue
        if getattr(declaration, "_is_protocol", False):
            with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
                declaration()
        else:
            if name in expected:
                assert not inspect.isabstract(declaration), f"{name} must be a concrete implementation"
            actual.add(name)
    assert actual == expected, f"unexpected concrete adapter exports: {actual ^ expected}"


def test_adapter_bindings_are_non_instantiable_port_declarations() -> None:
    for path in sorted((PACKAGE / "adapters").rglob("*.py")):
        name = _module_name(path)
        _assert_adapter_bindings(importlib.import_module(name), _ADAPTER_IMPLEMENTATIONS.get(name, set()))


def test_postgres_unit_of_work_bus_imports_are_symbol_and_owner_scoped() -> None:
    from ._tree import SourceFile
    from .rules import RuleContext, rule_layer_imports

    def findings(path: str, statement: str) -> list[object]:
        return list(rule_layer_imports([SourceFile.at(Path("src/skm") / path, statement)], RuleContext()))

    registry = "from skm.application_bus.registry import SSE_DESTINATION, OUTBOX_EXTERNAL_PREFIXES"
    for path, statement in (
        ("adapters/postgres/uow.py", registry),
        ("adapters/postgres/core/events_store.py", registry),
        ("adapters/postgres/core/__init__.py", "from skm.application_bus.ports import EventReader"),
        ("adapters/postgres/core/audit.py", "from skm.application_bus.ports import AuditRecord"),
        ("adapters/postgres/core/idempotency.py", "from skm.application_bus.ports import IdempotencyReceipt"),
        ("adapters/postgres/core/__init__.py", "from skm.application_bus.ports import OutboxStore"),
        ("adapters/postgres/core/__init__.py", "from skm.application_bus.ports import ConsumerReceipts"),
        (
            "adapters/postgres/core/outbox.py",
            "from skm.application_bus.ports import OutboxEntry, OutboxItem, OutboxState",
        ),
    ):
        assert not findings(path, statement), (path, statement)
    for path, statement in (
        ("adapters/postgres/uow.py", "from skm.application_bus.registry import BusRegistry"),
        ("adapters/postgres/uow.py", "from skm.application_bus.ports import EventReader"),
        ("adapters/postgres/core/events_store.py", "from skm.application_bus.bus import Bus"),
        ("adapters/postgres/core/scopes.py", "from skm.application_bus.registry import SSE_DESTINATION"),
        ("adapters/postgres/core/__init__.py", "from skm.application_bus.ports import AuditLog"),
        ("adapters/postgres/core/scopes.py", "from skm.application_bus.ports import EventReader"),
        (
            "adapters/postgres/connection.py",
            "from skm.application_bus.registry import OUTBOX_EXTERNAL_PREFIXES",
        ),
        ("adapters/postgres/core/audit.py", "from skm.application_bus.ports import IdempotencyReceipt"),
        ("adapters/postgres/core/audit.py", "from skm.application_bus.ports import AuditLog"),
        ("adapters/postgres/core/idempotency.py", "from skm.application_bus.ports import AuditRecord"),
        ("adapters/postgres/core/idempotency.py", "from skm.application_bus.ports import IdempotencyStore"),
        ("adapters/postgres/core/scopes.py", "from skm.application_bus.ports import AuditRecord"),
        ("adapters/postgres/core/outbox.py", "from skm.application_bus.ports import OutboxStore"),
        ("adapters/postgres/core/outbox.py", "from skm.application_bus.ports import ConsumerReceipts"),
        ("adapters/postgres/core/outbox.py", "from skm.application_bus.registry import SSE_DESTINATION"),
        (
            "adapters/postgres/core/consumer_receipts.py",
            "from skm.application_bus.ports import ConsumerReceipts",
        ),
        ("adapters/postgres/core/consumer_receipts.py", "from skm.application_bus.ports import OutboxState"),
        ("adapters/postgres/core/scopes.py", "from skm.application_bus.ports import OutboxItem"),
    ):
        assert findings(path, statement), (path, statement)


def test_adapter_binding_guard_rejects_unowned_concrete_exports() -> None:
    from types import SimpleNamespace

    with pytest.raises(AssertionError, match="unexpected concrete adapter exports"):
        _assert_adapter_bindings(SimpleNamespace(__all__=["Unexpected"], Unexpected=object), set())
    with pytest.raises(AssertionError, match="unexpected concrete adapter exports"):
        _assert_adapter_bindings(
            SimpleNamespace(__all__=["Allowed", "Unexpected"], Allowed=object, Unexpected=object),
            {"Allowed"},
        )
    with pytest.raises(AssertionError, match="unexpected concrete adapter exports"):
        _assert_adapter_bindings(SimpleNamespace(__all__=[], Missing=object), {"Missing"})
    from abc import ABC, abstractmethod

    class Stub(ABC):
        @abstractmethod
        def run(self) -> None: ...

    with pytest.raises(AssertionError, match="must be a concrete implementation"):
        _assert_adapter_bindings(SimpleNamespace(__all__=["Stub"], Stub=Stub), {"Stub"})


def test_local_vault_fs_implements_the_host_gateway(tmp_path: Path) -> None:
    from skm.adapters.exports.obsidian import vault_fs
    from skm.modules.exports.ports import VaultFs

    assert hasattr(vault_fs, "LocalVaultFs"), "exports §3 requires LocalVaultFs"
    declaration = vars(vault_fs)["LocalVaultFs"]
    assert VaultFs in inspect.getmro(declaration)
    assert "LocalVaultFs" in vault_fs.__all__
    assert declaration(tmp_path).is_dir(".")


def test_cli_draft_id_uses_the_existing_type_through_planning_public() -> None:
    from skm.entrypoints.cli import context
    from skm.modules.planning import public
    from skm.modules.planning.domain.draft import DraftId

    assert vars(context)["DraftId"] is public.DraftId is DraftId
    assert "DraftId" in public.__all__
    assert get_type_hints(context.CliContext.resolve_draft)["return"] is DraftId


def _entrypoint_import_violations(path: Path, text: str) -> list[str]:
    from ._tree import SourceFile
    from .rules import RuleContext, rule_layer_imports

    return [v.render() for v in rule_layer_imports([SourceFile.at(path, text)], RuleContext())]


def test_entrypoints_import_module_contracts_through_public_facades() -> None:
    for path in sorted((PACKAGE / "entrypoints").rglob("*.py")):
        assert not _entrypoint_import_violations(path, path.read_text()), str(path)


@pytest.mark.parametrize(
    "statement",
    [
        "from skm.modules.planning.domain.draft import DraftId",
        "from skm.modules.planning import domain as planning",
        "from ...modules.planning.domain import draft",
        "import skm.modules.planning.ports as ports",
        "if TYPE_CHECKING:\n    from skm.modules.planning.domain.draft import DraftId",
    ],
)
def test_entrypoint_checker_rejects_private_imports_independently_of_all(statement: str) -> None:
    path = PACKAGE / "entrypoints/cli/context.py"
    assert _entrypoint_import_violations(path, statement)
    assert not _entrypoint_import_violations(path, "from skm.modules.planning.public import DraftId")


def _contract_inventory() -> str:
    path = ROOT / "docs/architecture/contracts.md"
    index = path.read_text()
    parts = sorted(set(re.findall(r"\]\((contracts-[0-9]+\.md)\)", index)))
    return index + "\n" + "\n".join((path.parent / name).read_text() for name in parts)


def test_inventory_covers_every_materialized_contract_file() -> None:
    inventory = _contract_inventory()
    assert "leaf: unassigned" not in inventory
    rows = _inventory_owners(inventory)
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json"} and "__pycache__" not in path.parts:
            relative = str(path.relative_to(ROOT))
            assert relative in rows, relative
            assert re.search(r"P\d{2}\.\d+(?:\.[a-z])?", rows[relative]), relative
    for path in sorted((ROOT / "resources").rglob("README.md")):
        if path.is_file():
            assert f"| `{path.relative_to(ROOT)}` |" in inventory, path


def test_inventory_declaration_table_cannot_replace_or_supply_owners() -> None:
    path = "src/skm/schemas/demo/thing.v1.json"
    inventory = (
        f"| `{path}` | wire schema | P01.05.b |\n\n"
        "| Schema | Previous declaration | Generated declaration |\n"
        "|---|---|---|\n"
        f"| `{path}` | Old / dataclass | New / alias |\n"
        "| `src/skm/missing.py` | Old | New |\n"
    )
    assert _inventory_owners(inventory) == {path: " P01.05.b "}
    assert _inventory_owners("| `src/skm/missing.py` | contract | missing-owner |\n") == {
        "src/skm/missing.py": " missing-owner "
    }


@pytest.mark.parametrize(("backend", "owner"), [("memory", "P06.03.a"), ("postgres", "P06.03.b")])
def test_artifact_repository_inventory_uses_only_its_backend_owner(backend: str, owner: str) -> None:
    """P06.03.a/b write their backend directories; .c owns blob_coordination.py separately."""
    path = f"src/skm/adapters/{backend}/artifacts/repositories.py"
    inventory = _contract_inventory()
    row = next(line for line in inventory.splitlines() if line.startswith(f"| `{path}` |"))
    owners = re.findall(r"P\d{2}\.\d+(?:\.[a-z])?", row.split("|")[-2])
    assert owners == ["P00.04.f", owner]


def test_composition_inventory_and_slices_follow_owner_dependency_order() -> None:
    """Composition owners retain dependency order, including approved research policy wiring.

    In particular P04.02.c -> P04.04.a -> P01.10 makes access an indirect plugin prerequisite.
    P09.09.a additionally owns the approved run-policy loader binding after P09.04.d.
    The remaining frozen card closure is preserved without loading plan files at runtime.
    """
    expected = [
        "P02.08.a",
        "P03.03.c",
        "P04.02.c",
        "P01.10",
        "P06.03.c",
        "P09.03",
        "P09.04.d",
        "P09.09.a",
        "P11.04.a",
        "P15.01.b",
    ]
    lines = _contract_inventory().splitlines()
    row = next(line for line in lines if line.startswith("| `src/skm/bootstrap/composition.py` |"))
    owners = re.findall(r"P\d{2}\.\d+(?:\.[a-z])?", row.split("|")[-2])
    assert owners == ["P00.04.f", *expected]
    slices = next(line for line in lines if line.startswith("| bootstrap/composition.py |"))
    slice_owners = re.findall(r"(?:^|;)\s*(P\d{2}\.\d+(?:\.[a-z])?):", slices.split("|")[2])
    assert slice_owners == expected
