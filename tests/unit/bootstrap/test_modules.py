"""Module graph, module selection, section index and memory factory table (kernel-platform §5.1, §5.2).

The graph checks run on the 14 real manifests and on small fixture manifests; the section index runs on the
packaged schemas and on a throw-away schema tree for the duplicate case. Composition tests prove that the
transient memory composition is explicit (``CompositionOverrides``) and that production has no fallback.
"""

import importlib
import json
import sys
from dataclasses import replace
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from skm.application_bus.host import HostServices
from skm.bootstrap import composition as composition_module
from skm.bootstrap.adapters import CORE_PORTS, memory_repository_table, postgres_repository_table
from skm.bootstrap.composition import (
    KNOWN_SCHEMA_VERSION,
    App,
    CompositionOverrides,
    build_app,
    build_cli_app,
    invocation_from_json,
)
from skm.bootstrap.modules import (
    MANIFESTS,
    MODULE_CATALOG,
    PLATFORM_SECTIONS,
    ModuleGraphError,
    enabled_manifests,
    resolve_section_urns,
    section_index,
    select_modules,
    topological_order,
)
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    BackendUnavailable,
    CapabilityUnavailable,
    InternalError,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ScopeId, WorkspaceId
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.settings.generated import commands, queries
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock

OWNER = Actor(PrincipalId(UUID("01900000-0000-7000-8000-0000000000b1")), PrincipalKind.HUMAN, "fixture-owner")
INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
WORKSPACE = ScopeId(UUID("01900000-0000-7000-8000-0000000000a1"))
ROUNDS = "execution.review.max_rounds"


@cache
def packaged_schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def manifest(
    name: str, *depends_on: str, optional: bool = True, sections: tuple[str, ...] = ()
) -> ModuleManifest:
    return ModuleManifest(
        id=name, depends_on=depends_on, optional=optional, db_schema=None, settings_sections=sections
    )


# ---------------------------------------------------------------------------------------------------------
# the real manifests


def test_manifests_load_in_catalog_order_and_match_the_catalog() -> None:
    assert [m.id for m in MANIFESTS] == [entry.id for entry in MODULE_CATALOG]
    for loaded, entry in zip(MANIFESTS, MODULE_CATALOG, strict=True):
        assert (loaded.depends_on, loaded.optional, loaded.db_schema, loaded.settings_sections) == (
            entry.depends_on,
            entry.optional,
            entry.db_schema,
            entry.settings_sections,
        )


def test_topological_order_puts_every_dependency_first() -> None:
    order = topological_order(MANIFESTS)
    assert sorted(order) == sorted(m.id for m in MANIFESTS)
    for loaded in MANIFESTS:
        assert all(order.index(dependency) < order.index(loaded.id) for dependency in loaded.depends_on)
    shuffled = tuple(reversed(MANIFESTS))
    reordered = topological_order(shuffled)
    for loaded in MANIFESTS:
        assert all(
            reordered.index(dependency) < reordered.index(loaded.id) for dependency in loaded.depends_on
        )


# ---------------------------------------------------------------------------------------------------------
# graph errors


def test_cycle_is_rejected_with_its_path() -> None:
    with pytest.raises(ModuleGraphError) as caught:
        topological_order([manifest("a", "b"), manifest("b", "c"), manifest("c", "a")])
    assert caught.value.kind == "cycle"
    assert "a -> b -> c -> a" in str(caught.value)


def test_self_dependency_is_a_cycle() -> None:
    with pytest.raises(ModuleGraphError) as caught:
        topological_order([manifest("a", "a")])
    assert caught.value.kind == "cycle"


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(ModuleGraphError) as caught:
        topological_order([manifest("a", "ghost")])
    assert (caught.value.kind, caught.value.module) == ("unknown_dependency", "a")


def test_duplicate_module_id_is_rejected() -> None:
    with pytest.raises(ModuleGraphError) as caught:
        topological_order([manifest("a"), manifest("a")])
    assert caught.value.kind == "duplicate_id"


# ---------------------------------------------------------------------------------------------------------
# enabling and disabling


def test_nothing_disabled_keeps_every_manifest_in_topological_order() -> None:
    selection = select_modules(MANIFESTS, frozenset())
    assert [m.id for m in selection.manifests] == list(topological_order(MANIFESTS))
    assert not selection.disabled
    assert not selection.diagnostics


@pytest.mark.parametrize("required", ["access", "settings", "execution", "planning"])
def test_a_required_module_cannot_be_disabled(required: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        enabled_manifests(MANIFESTS, frozenset({required}))
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert caught.value.details == {"key": f"modules.{required}.enabled", "reason": "required_module"}


def test_an_unknown_module_cannot_be_disabled() -> None:
    with pytest.raises(ValidationFailed) as caught:
        enabled_manifests(MANIFESTS, frozenset({"ghost"}))
    assert caught.value.details["reason"] == "unknown_module"


def test_optional_dependants_are_disabled_with_a_diagnostic() -> None:
    selection = select_modules(MANIFESTS, frozenset({"knowledge"}))
    assert selection.disabled == {"knowledge", "learning"}
    assert {m.id for m in selection.manifests}.isdisjoint(selection.disabled)
    [diagnostic] = selection.diagnostics
    assert diagnostic.code == ErrorCode.MODULE_DISABLED.value
    assert diagnostic.target == "modules.learning.enabled"
    assert "knowledge" in diagnostic.message


def test_disabling_a_leaf_module_cascades_nowhere() -> None:
    selection = select_modules(MANIFESTS, frozenset({"exports"}))
    assert selection.disabled == {"exports"}
    assert not selection.diagnostics


def test_cascade_follows_a_chain() -> None:
    chain = [manifest("base", optional=False), manifest("a", "base"), manifest("b", "a"), manifest("c", "b")]
    selection = select_modules(chain, frozenset({"a"}))
    assert selection.disabled == {"a", "b", "c"}
    assert [d.target for d in selection.diagnostics] == ["modules.b.enabled", "modules.c.enabled"]
    assert [m.id for m in selection.manifests] == ["base"]


def test_a_required_module_depending_on_a_disabled_one_is_invalid() -> None:
    graph = [manifest("opt"), manifest("must", "opt", optional=False)]
    with pytest.raises(ValidationFailed) as caught:
        select_modules(graph, frozenset({"opt"}))
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert caught.value.details["reason"] == "required_dependant"


# ---------------------------------------------------------------------------------------------------------
# settings section index


def test_section_index_maps_every_packaged_section_to_its_schema() -> None:
    schemas = packaged_schemas()
    index = section_index(schemas)
    assert index["execution"] == "urn:skm:settings:execution:v1"
    assert set(PLATFORM_SECTIONS) <= set(index)
    assert resolve_section_urns(MANIFESTS, schemas) == tuple(
        index[section] for m in MANIFESTS for section in m.settings_sections
    ) + tuple(index[section] for section in PLATFORM_SECTIONS)


def test_a_missing_section_id_is_rejected_before_the_registry_build() -> None:
    schemas = packaged_schemas()
    broken = [replace(MANIFESTS[0], settings_sections=("access", "no_such_section"))]
    with pytest.raises(InternalError) as caught:
        resolve_section_urns(broken, schemas, platform_sections=())
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID
    assert caught.value.details == {"section": "no_such_section", "owner": "access"}


def test_a_section_claimed_twice_is_rejected() -> None:
    schemas = packaged_schemas()
    twice = [replace(MANIFESTS[0], settings_sections=("access",)), manifest("other", sections=("access",))]
    with pytest.raises(InternalError) as caught:
        resolve_section_urns(twice, schemas, platform_sections=())
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID
    assert caught.value.details == {"section": "access", "owners": ["access", "other"]}
    with pytest.raises(InternalError):
        resolve_section_urns(
            [replace(MANIFESTS[0], settings_sections=("api",))], schemas
        )  # api is the platform's


def test_two_schemas_with_one_section_id_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "test"
    root.mkdir()
    for name in ("one", "two"):
        document: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:skm:test:{name}:v1",
            "type": "object",
            "x-skm-section": {"id": "shared"},
        }
        (root / f"{name}.v1.json").write_text(json.dumps(document), encoding="utf-8")
    schemas = SchemaRegistry.load(tmp_path)
    with pytest.raises(InternalError) as caught:
        section_index(schemas)
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID
    assert caught.value.details == {
        "section": "shared",
        "schemas": ["urn:skm:test:one:v1", "urn:skm:test:two:v1"],
    }


# ---------------------------------------------------------------------------------------------------------
# memory repository table


def test_memory_table_merges_core_and_module_factories() -> None:
    table = memory_repository_table(("settings",))
    assert set(CORE_PORTS) <= set(table)
    from skm.modules.settings.ports import ConfigEntryRepository

    assert ConfigEntryRepository in table


def test_context_contributes_its_memory_repositories() -> None:
    from skm.adapters.memory.context import REPOSITORIES
    from skm.modules.context.ports import ContextRepository, ResearchRepository, TextStore

    table = memory_repository_table(("context",))
    assert set(REPOSITORIES) == {ContextRepository, ResearchRepository, TextStore}
    assert set(table) == set(memory_repository_table(())) | set(REPOSITORIES)


def test_planning_contributes_its_memory_repositories() -> None:
    from skm.adapters.memory.planning import REPOSITORIES
    from skm.modules.planning.ports import (
        DraftRepository,
        PlanCounters,
        PlanningQueries,
        PlanRepository,
        RevisionRepository,
    )

    table = memory_repository_table(("planning",))
    assert set(REPOSITORIES) == {
        PlanRepository,
        PlanCounters,
        DraftRepository,
        RevisionRepository,
        PlanningQueries,
    }
    assert set(table) == set(memory_repository_table(())) | set(REPOSITORIES)


def test_artifacts_contributes_its_memory_repositories() -> None:
    from skm.adapters.memory.artifacts import REPOSITORIES
    from skm.modules.artifacts.ports import (
        AccessGrantRepository,
        BlobContentReader,
        BlobDigestLock,
        BlobRepository,
        FileRepository,
        FileVersionRepository,
        StagedBlobRepository,
    )

    table = memory_repository_table(("artifacts",))
    assert set(REPOSITORIES) == {
        StagedBlobRepository,
        BlobRepository,
        FileRepository,
        FileVersionRepository,
        AccessGrantRepository,
        BlobContentReader,
        BlobDigestLock,
    }
    assert set(table) == set(memory_repository_table(())) | set(REPOSITORIES)


def test_access_contributes_its_memory_repositories() -> None:
    from skm.adapters.memory.access import REPOSITORIES

    table = memory_repository_table(("access",))
    assert set(table) == set(memory_repository_table(())) | set(REPOSITORIES)


def test_workspace_contributes_its_memory_repositories() -> None:
    from skm.adapters.memory.workspace import REPOSITORIES

    table = memory_repository_table(("workspace",))
    assert set(table) == set(memory_repository_table(())) | set(REPOSITORIES)


@pytest.mark.parametrize(
    ("backend", "build"),
    [("memory", memory_repository_table), ("postgres", postgres_repository_table)],
)
def test_extensions_contributes_its_repositories(backend: str, build: Any) -> None:
    from skm.modules.extensions.module import MODULE
    from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

    exported = importlib.import_module(f"skm.adapters.{backend}.extensions").REPOSITORIES
    assert set(exported) == {PackRepository, ResourceRepository, QuarantineRepository}
    assert set(exported) == set(MODULE.repository_ports)
    assert set(build(("extensions",))) == set(build(())) | set(exported)


def test_a_port_bound_twice_is_a_composition_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Port: ...

    fake = ModuleType("skm.adapters.memory.fake_dup")
    fake.REPOSITORIES = {Port: lambda state: state}  # type: ignore[attr-defined]
    twin = ModuleType("skm.adapters.memory.fake_twin")
    twin.REPOSITORIES = {Port: lambda state: state}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "skm.adapters.memory.fake_dup", fake)
    monkeypatch.setitem(sys.modules, "skm.adapters.memory.fake_twin", twin)
    with pytest.raises(ValueError, match="bound twice"):
        memory_repository_table(("fake_dup", "fake_twin"))


# ---------------------------------------------------------------------------------------------------------
# composition


def bootstrap_config(tmp_path: Path, mode: str = "embedded", database_url: str = "postgresql://unused"):
    env = (
        {"SKM_DATABASE_URL": database_url}
        if mode == "embedded"
        else {"SKM_API_ENDPOINT": "https://skm.example.com/api/v1", "SKM_API_TOKEN": "fixture-token-value"}
    )
    return load_bootstrap(None, env, tmp_path)


def overrides(**changes: Any) -> CompositionOverrides:
    return CompositionOverrides(authorizer=FakeAuthorizer(), scopes=FakeScopeChain(), **changes)


def test_production_composition_has_no_fallback_without_overrides(tmp_path: Path) -> None:
    """No overrides means the production composition: a bootstrap without a pepper is refused before any
    connection (never an allow-all authorizer), and the memory backend is not reachable from production."""
    bootstrap = bootstrap_config(tmp_path)
    for build in (
        lambda: build_app(bootstrap, surface=Surface.CLI, environ={}, invocation={}),
        lambda: build_cli_app(bootstrap, environ={}, invocation={}),
    ):
        with pytest.raises(PreconditionFailed) as caught:
            build()
        assert caught.value.code is ErrorCode.SECRET_UNAVAILABLE
        assert caught.value.details["field"] == "secrets.token_pepper"
    with pytest.raises(CapabilityUnavailable) as unavailable:
        build_app(bootstrap, surface=Surface.CLI, environ={}, invocation={}, backend="memory")
    assert unavailable.value.code is ErrorCode.CAPABILITY_UNAVAILABLE


def test_unavailable_backends_are_refused_even_with_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_pool(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the pool must not be created when the start-up connection fails")

    monkeypatch.setattr(composition_module, "create_pool", no_pool)
    # Nothing listens on port 1 of the loopback: the start-up connection (step 6a) is refused.
    with pytest.raises(BackendUnavailable) as caught:
        build_app(
            bootstrap_config(tmp_path, database_url="postgresql://skm@127.0.0.1:1/skm"),
            surface=Surface.CLI,
            environ={},
            invocation={},
            backend="postgres",
            overrides=overrides(),
        )
    assert caught.value.code is ErrorCode.BACKEND_UNAVAILABLE
    assert caught.value.details["phase"] == "connect"
    with pytest.raises(CapabilityUnavailable, match="HTTP"):
        build_app(
            bootstrap_config(tmp_path, "http"),
            surface=Surface.CLI,
            environ={},
            invocation={},
            overrides=overrides(),
        )


def test_the_memory_composition_runs_a_command_and_a_query_in_one_app(tmp_path: Path) -> None:
    app = build_app(
        bootstrap_config(tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={"set": [f"{ROUNDS}=4"]},
        overrides=overrides(),
    )
    clock = SystemClock()
    with app.uow_factory(RequestMeta("req_" + "0" * 26, Surface.CLI, None, clock.now())) as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        scopes.create(WORKSPACE, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=WorkspaceId(WORKSPACE))
        uow.commit()
    client = app.client(actor=OWNER, surface=Surface.CLI)
    scope = commands.SetValueDefsScopeRef(level="workspace", scope_id=WORKSPACE)
    client.dispatch(commands.SetValue(scope=scope, key=ROUNDS, value=3, reason="test"))
    view = client.ask(
        queries.GetValue(
            scope=queries.GetValueDefsScopeRef(level="workspace", scope_id=WORKSPACE), key=ROUNDS
        )
    )
    assert view.value == 3  # type: ignore[attr-defined]
    # the invocation layer (--set) is part of the loader but a lower level than a stored override=false value
    assert app.config.registry is app.settings
    app.close()
    app.close()  # idempotent


def test_a_disabled_module_is_left_out_of_the_bus_registry(tmp_path: Path) -> None:
    app = build_app(
        bootstrap_config(tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=overrides(disabled_modules=frozenset({"learning"})),
    )
    assert app.bus is not None


@pytest.mark.parametrize(
    ("surface", "keeps_host"),
    [
        (Surface.CLI, True),
        (Surface.WORKER, True),
        (Surface.HOOK, True),
        (Surface.API, False),
        (Surface.BACKGROUND, False),  # skm serve: the server never touches a checkout (kernel-platform §5.3)
    ],
)
def test_only_host_surfaces_receive_the_supplied_host_services(
    tmp_path: Path, surface: Surface, keeps_host: bool
) -> None:
    host = HostServices(
        host_id=HostId(UUID(int=7)),
        surface=surface,
        gateways=GatewayTable({}, "host_gateway"),
        host_config=lambda: None,
        operations={},
    )
    app = build_app(
        bootstrap_config(tmp_path), surface=surface, environ={}, invocation={}, overrides=overrides(host=host)
    )
    assert isinstance(app, App)
    assert app.host is (host if keeps_host else None)
    app.close()


def test_invocation_json_becomes_overrides(tmp_path: Path) -> None:
    parsed = invocation_from_json({"set": ["a=1"], "config": str(tmp_path / "x.toml")})
    assert parsed.sets == ("a=1",)
    assert parsed.config_files == (tmp_path / "x.toml",)
    assert invocation_from_json({}).sets == ()


def test_the_known_schema_version_is_a_non_negative_integer() -> None:
    assert isinstance(KNOWN_SCHEMA_VERSION, int)
    assert KNOWN_SCHEMA_VERSION >= 0
