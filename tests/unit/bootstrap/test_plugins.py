"""Plugin loader steps 1-11 (mechanisms/02-plugins §4, kernel-platform §5.4): one case per refusal, order,
conflicts.

The fixture distribution ``tests/fixtures/plugins/skm-plugin-fixture`` is laid out as an installed
distribution (dist-info with METADATA, RECORD and entry_points.txt) under ``tmp_path``; ``discover`` returns
its entry points. Side effects are read from the fixture's sentinel module: ``import:<id>`` and
``factory:<kind>``."""

import importlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from importlib.metadata import Distribution, EntryPoint, PathDistribution
from pathlib import Path
from typing import Protocol, cast

import pytest

from skm.bootstrap import composition
from skm.bootstrap.plugins import (
    LoadedPlugin,
    PluginAllowlist,
    PluginSchema,
    PluginSchemas,
    PluginSettingsView,
    PluginStatus,
    ProcessPlugins,
    SettingsPhase2,
    capability_catalog,
    load_plugins,
)
from skm.entrypoints.cli.main import main
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, InternalError, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import EmptyPackConfigSource
from skm.platform.logging import setup
from skm.platform.schema.registry import SchemaRegistry
from skm.plugin_api import API_VERSION, ComponentKind, PluginManifest, Side
from skm.plugin_api.manifest import requires_skm_matches
from skm.plugin_api.testing import manifest_contract_suite, plugin_test_context

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "plugins" / "skm-plugin-fixture"
PACKAGE = "skm_plugin_fixture"
SKM_VERSION = "0.1.0"


class FixtureLike(Protocol):
    runtime_id: str


def install(
    site: Path,
    *,
    package: str = PACKAGE,
    plugin_id: str = "acme.fixture",
    rename: Mapping[str, str] | None = None,
    files: Mapping[str, str | None] | None = None,
    record_extra: Sequence[str] = (),
) -> Distribution:
    """Lay the fixture out as an installed distribution; ``rename`` rewrites names in paths and text."""
    changes = {"acme.fixture": plugin_id, PACKAGE: package, "acme_fixture": plugin_id.replace(".", "_")}
    changes.update(rename or {})
    source = FIXTURE / "src" / PACKAGE
    listed: list[str] = []
    for path in sorted(source.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        name = f"{PACKAGE}/{path.relative_to(source).as_posix()}"
        text = path.read_text(encoding="utf-8")
        for old, new in changes.items():
            name, text = name.replace(old, new), text.replace(old, new)
        target = site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        listed.append(name)
    for original, text in (files or {}).items():
        relative = original.replace(PACKAGE, package)
        if text is None:
            (site / relative).unlink()
            listed.remove(relative)
            continue
        (site / relative).parent.mkdir(parents=True, exist_ok=True)
        (site / relative).write_text(text, encoding="utf-8")
        listed.append(relative) if relative not in listed else None
    name = package.replace("_", "-")
    info = site / f"{package}-0.1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n", encoding="utf-8")
    (info / "entry_points.txt").write_text(
        f"[skm.plugins]\n{plugin_id} = {package}.plugin:MANIFEST\n", encoding="utf-8"
    )
    (info / "INSTALLER").write_text("fixture-test\n", encoding="utf-8")
    entries = [
        *listed,
        *record_extra,
        *(f"{info.name}/{n}" for n in ("METADATA", "entry_points.txt", "INSTALLER")),
    ]
    (info / "RECORD").write_text("".join(f"{entry},,\n" for entry in entries) + f"{info.name}/RECORD,,\n")
    return PathDistribution(info)


def entries(*dists: Distribution) -> list[EntryPoint]:
    return [entry for dist in dists for entry in dist.entry_points if entry.group == "skm.plugins"]


def events(package: str = PACKAGE) -> list[str]:
    module = sys.modules.get(f"{package}.sentinel")
    return list(getattr(module, "EVENTS", []))


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "site"
    root.mkdir()
    monkeypatch.syspath_prepend(str(root))
    yield root
    for name in [name for name in sys.modules if name.startswith("skm_plugin_")]:
        del sys.modules[name]


@pytest.fixture(scope="module")
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@pytest.fixture(autouse=True)
def logging_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)  # main() reconfigures logging


class Phase2:
    """A settings phase 2 that records its calls and keeps the base registry."""

    def __init__(self, schemas: SchemaRegistry) -> None:
        self.schemas = schemas
        self.calls: list[tuple[list[str], list[str]]] = []

    def __call__(self, documents: Sequence[PluginSchema], urns: Sequence[str]) -> PluginSchemas:
        self.calls.append(([item.urn for item in documents], list(urns)))
        return PluginSchemas(self.schemas)


def load(
    schemas: SchemaRegistry,
    found: list[EntryPoint],
    allowed: Sequence[str],
    *,
    side: Side = Side.BOTH,
    phase2: SettingsPhase2 | None = None,
    required: frozenset[str] = frozenset(),
    control_plane_allowed: frozenset[str] = frozenset(),
    override_builtin: frozenset[str] = frozenset(),
) -> tuple[LoadedPlugin, ...]:
    return load_plugins(
        allowed=allowed,
        required=required,
        side=side,
        skm_version=SKM_VERSION,
        schemas=schemas,
        settings_phase2=phase2 or Phase2(schemas),
        discover=lambda: found,
        control_plane_allowed=control_plane_allowed,
        override_builtin=override_builtin,
    )


def by_id(plugins: Sequence[LoadedPlugin]) -> dict[str, LoadedPlugin]:
    return {plugin.plugin_id: plugin for plugin in plugins}


def codes(plugin: LoadedPlugin) -> list[str]:
    return [item.code for item in plugin.diagnostics]


# --------------------------------------------------------------------------------------------- steps 1-2a, 8


def test_allowed_plugin_loads_every_step(site: Path, schemas: SchemaRegistry) -> None:
    phase2 = Phase2(schemas)
    (plugin,) = load(schemas, entries(install(site)), ["acme.fixture"], phase2=phase2)
    assert plugin.status is PluginStatus.LOADED
    assert plugin.diagnostics == ()
    assert [(spec.kind, spec.key) for spec in plugin.components] == [
        (ComponentKind.RUNTIME, "fixture_rt"),
        (ComponentKind.ISOLATION, "acme.fixture:jail"),
    ]
    assert (
        cast("FixtureLike", plugin.instances[(ComponentKind.RUNTIME, "fixture_rt")]).runtime_id
        == "fixture_rt"
    )
    assert events() == ["import:acme.fixture", "factory:runtime", "factory:isolation"]
    assert set(plugin.runtime_data) == {"fixture_rt"}
    assert plugin.settings_urn == "urn:skm:plugin-fixture:settings:v1"
    assert phase2.calls == [(["urn:skm:plugin-fixture:settings:v1"], ["urn:skm:plugin-fixture:settings:v1"])]
    assert (plugin.dist_name, plugin.dist_version) == ("skm-plugin-fixture", "0.1.0")
    assert plugin.record_digest.startswith("sha256:")
    assert plugin.provenance.install == "fixture-test"
    assert plugin.provenance.unknown_fields() == ("source", "dependency_lock")  # unknown stays explicit


def test_not_allowed_plugin_is_neither_imported_nor_read(site: Path, schemas: SchemaRegistry) -> None:
    (plugin,) = load(schemas, entries(install(site)), [])
    assert plugin.status is PluginStatus.NOT_ALLOWED
    assert plugin.manifest is None
    assert codes(plugin) == ["PLUGIN_NOT_ALLOWED"]
    assert plugin.runtime_data == {}
    assert events() == []
    assert f"{PACKAGE}.plugin" not in sys.modules


def test_runtime_data_is_read_through_record_without_import(site: Path, schemas: SchemaRegistry) -> None:
    broken = {f"{PACKAGE}/plugin.py": "raise RuntimeError('import-time failure')\n"}
    (plugin,) = load(schemas, entries(install(site, files=broken)), ["acme.fixture"])
    assert plugin.status is PluginStatus.FAILED
    assert codes(plugin) == ["PLUGIN_LOAD_FAILED"]
    assert plugin.diagnostics[0].details["reason"] == "import_error"
    caps = plugin.runtime_data["fixture_rt"].capabilities
    assert caps.adapter_version == "0.1.0"  # step 2a ran although the code never imported


def test_data_file_outside_record_is_ignored(site: Path, schemas: SchemaRegistry) -> None:
    dist = install(site, files={f"{PACKAGE}/skm_runtimes/fixture_rt/error_rules.toml": None})
    (site / PACKAGE / "skm_runtimes" / "fixture_rt" / "error_rules.toml").write_text("rules = []\n")
    (plugin,) = load(schemas, entries(dist), ["acme.fixture"])
    assert "fixture_rt" not in plugin.runtime_data  # present on disk, absent from RECORD
    assert plugin.status is PluginStatus.FAILED
    assert [item.details["reason"] for item in plugin.diagnostics] == ["runtime_data_invalid", "runtime_data"]


def test_invalid_capabilities_is_load_failed_and_no_factory_runs(site: Path, schemas: SchemaRegistry) -> None:
    path = FIXTURE / "src" / PACKAGE / "skm_runtimes" / "fixture_rt" / "capabilities.toml"
    bad = path.read_text().replace('status = "native"', 'status = "sometimes"')
    dist = install(site, files={f"{PACKAGE}/skm_runtimes/fixture_rt/capabilities.toml": bad})
    (plugin,) = load(schemas, entries(dist), ["acme.fixture"])
    data = plugin.diagnostics[0]
    assert (data.code, data.target, data.details["step"]) == ("PLUGIN_LOAD_FAILED", "fixture_rt", "data")
    assert plugin.runtime_data == {}
    assert plugin.status is PluginStatus.FAILED
    assert events() == ["import:acme.fixture"]  # the runtime factory never ran


@pytest.mark.parametrize(
    ("needle", "replacement", "reason"),
    [
        ("plugin_api=API_VERSION", "plugin_api=API_VERSION + 1", "plugin_api"),
        ('requires_skm=">=0.1.0,<1"', 'requires_skm=">=3"', "requires_skm"),
        ('requires_skm=">=0.1.0,<1"', 'requires_skm="not a specifier"', "requires_skm"),
    ],
)
def test_incompatible_manifest_is_imported_but_never_constructed(
    site: Path, schemas: SchemaRegistry, needle: str, replacement: str, reason: str
) -> None:
    text = (FIXTURE / "src" / PACKAGE / "plugin.py").read_text().replace(needle, replacement)
    (plugin,) = load(schemas, entries(install(site, files={f"{PACKAGE}/plugin.py": text})), ["acme.fixture"])
    assert plugin.status is PluginStatus.INCOMPATIBLE
    assert codes(plugin) == ["PLUGIN_INCOMPATIBLE"]
    assert plugin.diagnostics[0].details["reason"] == reason
    assert events() == ["import:acme.fixture"]
    assert plugin.components == ()


@pytest.mark.parametrize(
    ("needle", "replacement", "reason"),
    [
        ('id="acme.fixture"', 'id="acme.other"', "id"),
        (
            'capabilities="skm_runtimes/fixture_rt/capabilities.toml"',
            "capabilities=None",
            "capabilities_path",
        ),
        ('key="acme.fixture:jail"', 'key="jail"', "key"),
        ("MANIFEST = PluginManifest(", "MANIFEST = object()\nUNUSED = PluginManifest(", "not_a_manifest"),
        (
            'settings_schema="schemas/settings/plugin-fixture.v1.json"',
            'settings_schema="missing.v1.json"',
            "schema_missing",
        ),
    ],
)
def test_invalid_declaration_is_load_failed(
    site: Path, schemas: SchemaRegistry, needle: str, replacement: str, reason: str
) -> None:
    text = (FIXTURE / "src" / PACKAGE / "plugin.py").read_text().replace(needle, replacement)
    (plugin,) = load(schemas, entries(install(site, files={f"{PACKAGE}/plugin.py": text})), ["acme.fixture"])
    assert plugin.status is PluginStatus.FAILED
    assert plugin.diagnostics[-1].details["reason"] == reason
    assert "factory:runtime" not in events()


def test_settings_section_must_be_the_plugin_section(site: Path, schemas: SchemaRegistry) -> None:
    path = FIXTURE / "src" / PACKAGE / "schemas" / "settings" / "plugin-fixture.v1.json"
    text = path.read_text().replace('"id": "plugins.acme.fixture"', '"id": "plugins.someone.else"')
    dist = install(site, files={f"{PACKAGE}/schemas/settings/plugin-fixture.v1.json": text})
    (plugin,) = load(schemas, entries(dist), ["acme.fixture"])
    assert plugin.status is PluginStatus.FAILED
    assert plugin.diagnostics[-1].details["reason"] == "section_id"


def test_failing_factory_and_protocol_mismatch_skip_the_plugin(site: Path, schemas: SchemaRegistry) -> None:
    path = FIXTURE / "src" / PACKAGE / "isolation.py"
    without_wrap = path.read_text().replace("def wrap(self, argv, spec):", "def unwrap(self, argv, spec):")
    first = install(site, files={f"{PACKAGE}/isolation.py": without_wrap})
    (plugin,) = load(schemas, entries(first), ["acme.fixture"])
    assert plugin.status is PluginStatus.FAILED
    assert plugin.diagnostics[0].details["reason"] == "protocol"
    assert "wrap" in plugin.diagnostics[0].message
    assert plugin.instances == {}


def test_factory_error_is_load_failed(site: Path, schemas: SchemaRegistry) -> None:
    text = (FIXTURE / "src" / PACKAGE / "plugin.py").read_text()
    text = text.replace("    return FixtureIsolation()", "    raise RuntimeError('factory failure')")
    (plugin,) = load(schemas, entries(install(site, files={f"{PACKAGE}/plugin.py": text})), ["acme.fixture"])
    assert plugin.status is PluginStatus.FAILED
    assert plugin.diagnostics[0].details["reason"] == "factory_error"
    assert plugin.components == ()
    assert plugin.instances == {}


def test_runtime_id_must_equal_the_key(site: Path, schemas: SchemaRegistry) -> None:
    text = (
        (FIXTURE / "src" / PACKAGE / "runtime.py")
        .read_text()
        .replace('runtime_id = "fixture_rt"', 'runtime_id = "other"')
    )
    (plugin,) = load(schemas, entries(install(site, files={f"{PACKAGE}/runtime.py": text})), ["acme.fixture"])
    assert plugin.status is PluginStatus.FAILED
    assert plugin.diagnostics[0].details["reason"] == "runtime_id"


def test_unhealthy_component_is_degraded_not_removed(site: Path, schemas: SchemaRegistry) -> None:
    text = (
        FIXTURE / "src" / PACKAGE / "isolation.py"
    ).read_text() + "\n    def health(self):\n        return False\n"
    (plugin,) = load(
        schemas, entries(install(site, files={f"{PACKAGE}/isolation.py": text})), ["acme.fixture"]
    )
    assert plugin.status is PluginStatus.DEGRADED
    assert plugin.diagnostics[0].details == {"step": "health", "reason": "degraded"}
    assert (ComponentKind.ISOLATION, "acme.fixture:jail") in plugin.instances


def test_process_side_filters_construction(site: Path, schemas: SchemaRegistry) -> None:
    allowed = frozenset({"acme.fixture"})
    (plugin,) = load(
        schemas,
        entries(install(site)),
        ["acme.fixture"],
        side=Side.CONTROL_PLANE,
        control_plane_allowed=allowed,
    )
    assert plugin.status is PluginStatus.LOADED
    assert plugin.components == ()
    assert events() == ["import:acme.fixture"]


# ------------------------------------------------------------------------------------------ steps 5, 7, 10


def twin(site: Path, **rename: str) -> Distribution:
    return install(site, package="skm_plugin_twin", plugin_id="acme.twin", rename=rename)


@pytest.mark.parametrize("order", [["acme.fixture", "acme.twin"], ["acme.twin", "acme.fixture"]])
def test_duplicate_runtime_id_stops_bootstrap_before_factories(
    site: Path, schemas: SchemaRegistry, order: list[str]
) -> None:
    found = entries(install(site), twin(site, **{"plugin-fixture": "plugin-twin"}))
    with pytest.raises(InternalError) as caught:
        load(schemas, found, order)
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID
    assert caught.value.details["reason_code"] == "PLUGIN_CONFLICT"
    assert caught.value.details["conflicts"] == [
        {"key": "runtime:fixture_rt", "plugins": ["acme.fixture", "acme.twin"], "with": "plugin"}
    ]
    assert not [event for event in events() + events("skm_plugin_twin") if event.startswith("factory:")]


@pytest.mark.parametrize("order", [["acme.fixture", "acme.twin"], ["acme.twin", "acme.fixture"]])
def test_duplicate_schema_id_stops_bootstrap_before_factories(
    site: Path, schemas: SchemaRegistry, order: list[str]
) -> None:
    found = entries(install(site), twin(site, fixture_rt="twin_rt"))  # same settings $id, own runtime
    with pytest.raises(InternalError) as caught:
        load(schemas, found, order)
    assert caught.value.details["conflicts"] == [
        {
            "schema": "urn:skm:plugin-fixture:settings:v1",
            "plugins": ["acme.fixture", "acme.twin"],
            "with": "plugin",
        }
    ]
    assert not [event for event in events() + events("skm_plugin_twin") if event.startswith("factory:")]


def test_schema_id_of_the_core_is_a_conflict(site: Path, schemas: SchemaRegistry) -> None:
    dist = install(site, rename={"urn:skm:plugin-fixture:settings:v1": "urn:skm:settings:plugins:v1"})
    with pytest.raises(InternalError) as caught:
        load(schemas, entries(dist), ["acme.fixture"])
    assert caught.value.details["conflicts"] == [
        {"schema": "urn:skm:settings:plugins:v1", "plugins": ["acme.fixture"], "with": "core"}
    ]


def test_builtin_key_needs_a_single_explicit_override(site: Path, schemas: SchemaRegistry) -> None:
    found = entries(install(site, rename={"fixture_rt": "codex"}))
    with pytest.raises(InternalError) as caught:
        load(schemas, found, ["acme.fixture"])
    assert caught.value.details["conflicts"] == [
        {"key": "runtime:codex", "plugins": ["acme.fixture"], "with": "builtin"}
    ]
    for name in [name for name in sys.modules if name.startswith("skm_plugin_")]:
        del sys.modules[name]
    (plugin,) = load(schemas, found, ["acme.fixture"], override_builtin=frozenset({"runtime:codex"}))
    assert plugin.status is PluginStatus.LOADED
    assert "codex" in plugin.runtime_data


def test_two_replacements_of_one_builtin_stay_a_conflict(site: Path, schemas: SchemaRegistry) -> None:
    found = entries(
        install(site, rename={"fixture_rt": "codex"}),
        twin(site, fixture_rt="codex", **{"plugin-fixture": "plugin-twin"}),
    )
    with pytest.raises(InternalError) as caught:
        load(schemas, found, ["acme.fixture", "acme.twin"], override_builtin=frozenset({"runtime:codex"}))
    assert caught.value.details["conflicts"] == [
        {"key": "runtime:codex", "plugins": ["acme.fixture", "acme.twin"], "with": "plugin"}
    ]


def test_required_plugin_that_did_not_load_stops_the_start(site: Path, schemas: SchemaRegistry) -> None:
    broken = {f"{PACKAGE}/plugin.py": "raise ImportError('missing dependency')\n"}
    found = entries(install(site, files=broken))
    with pytest.raises(CapabilityUnavailable) as caught:
        load(
            schemas,
            found,
            ["acme.fixture", "acme.absent"],
            required=frozenset({"acme.fixture", "acme.absent"}),
        )
    assert caught.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert caught.value.details == {
        "reason_code": "plugin_required",
        "plugins": [
            {"plugin": "acme.absent", "status": "not_installed"},
            {"plugin": "acme.fixture", "status": "failed"},
        ],
    }


def test_optional_failure_does_not_stop_the_start(site: Path, schemas: SchemaRegistry) -> None:
    broken = {f"{PACKAGE}/plugin.py": "raise ImportError('missing dependency')\n"}
    plugins = by_id(
        load(
            schemas,
            entries(
                install(site, files=broken),
                twin(site, fixture_rt="twin_rt", **{"plugin-fixture": "plugin-twin"}),
            ),
            ["acme.fixture", "acme.twin"],
        )
    )
    assert plugins["acme.fixture"].status is PluginStatus.FAILED
    assert plugins["acme.twin"].status is PluginStatus.LOADED


def test_settings_registry_refusal_skips_only_that_plugin(site: Path, schemas: SchemaRegistry) -> None:
    def phase2(documents: Sequence[PluginSchema], urns: Sequence[str]) -> PluginSchemas:
        if "urn:skm:plugin-fixture:settings:v1" in urns:
            problems: list[JsonValue] = [
                {"code": "REG-02", "section": "plugins.acme.fixture", "key": None, "message": "bad"}
            ]
            raise InternalError(ErrorCode.CONFIG_REGISTRY_INVALID, "invalid", details={"problems": problems})
        return PluginSchemas(schemas)

    found = entries(install(site), twin(site, fixture_rt="twin_rt", **{"plugin-fixture": "plugin-twin"}))
    plugins = by_id(load(schemas, found, ["acme.fixture", "acme.twin"], phase2=phase2))
    assert plugins["acme.fixture"].status is PluginStatus.FAILED
    assert plugins["acme.fixture"].diagnostics[-1].details["reason"] == "section_invalid"
    assert plugins["acme.twin"].status is PluginStatus.LOADED


def test_allowlist_from_restart_values() -> None:
    values: JsonObject = {"plugins.allowed": ["acme.fixture"], "plugins.required": ["acme.fixture"]}
    allow = PluginAllowlist.from_values(values)
    assert allow.allowed == ("acme.fixture",)
    assert allow.required == frozenset({"acme.fixture"})
    assert PluginAllowlist.from_values({}) == PluginAllowlist()
    with pytest.raises(ValidationFailed):
        PluginAllowlist.from_values({"plugins.allowed": "acme.fixture"})


# ------------------------------------------------------------------------------- phase 2 and the catalog


def test_phase2_registers_the_plugin_section_and_its_view(site: Path) -> None:
    schemas, settings = composition._default_registries()
    found = entries(install(site))
    plugins = ProcessPlugins(
        schemas=schemas,
        settings=settings,
        host_surface=True,
        build_settings=composition._settings_registry,
        loader=lambda final: ConfigLoader(final, EmptyPackConfigSource(), ()),
        discover=lambda: found,
    )
    assert plugins.load({"plugins.allowed": ["acme.fixture"]}) is True
    section = plugins.settings.section("plugins.acme.fixture")
    assert section.keys == ("plugins.acme.fixture.mode",)
    assert cast("type[PluginSettingsView]", section.view).SCHEMA_URN == "urn:skm:plugin-fixture:settings:v1"
    assert "urn:skm:plugin-fixture:settings:v1" in plugins.schemas.urns()
    assert plugins.settings.spec("plugins.allowed")  # the core sections stay
    (loaded,) = plugins.plugins
    assert loaded.status is PluginStatus.LOADED


def test_no_plugin_keeps_the_phase1_registries() -> None:
    schemas, settings = composition._default_registries()
    plugins = ProcessPlugins(
        schemas=schemas,
        settings=settings,
        host_surface=False,
        build_settings=composition._settings_registry,
        loader=lambda final: ConfigLoader(final, EmptyPackConfigSource(), ()),
        discover=lambda: [],
    )
    assert plugins.load({}) is False
    assert plugins.settings is settings
    assert plugins.schemas is schemas
    assert plugins.plugins == ()


def test_capability_catalog_holds_plugin_runtime_data(site: Path, schemas: SchemaRegistry) -> None:
    catalog = capability_catalog(load(schemas, entries(install(site)), ["acme.fixture"]))
    assert catalog.registered() == frozenset({"fixture_rt"})
    assert catalog.error_rules("fixture_rt")[0].code is ErrorCode.RATE_LIMITED


# ------------------------------------------------------------------------------ plugin_api and the CLI


@pytest.mark.parametrize(
    ("version", "specifier", "expected"),
    [
        ("2.0.0.dev0", ">=2.0.0.dev0,<3", True),
        ("2.0.0.dev0", ">=2.0,<3", False),  # a dev release precedes 2.0
        ("2.1.0", ">=2.0,<3", True),
        ("3.0.0.dev1", "<3", False),  # "<3" admits no pre-release of 3
        ("3.0.0", ">=2.0,<3", False),
        ("2.4.1", "~=2.4", True),
        ("3.0", "~=2.4", False),
        ("2.4.1", "==2.4.*", True),
        ("2.5.0", "!=2.4.*", True),
        ("2.0", "==2.0.0", True),
        ("2.0.post1", ">2.0", False),
        ("2.0.1", ">2.0", True),
        ("2.0rc1", ">=2.0a1", True),
    ],
)
def test_requires_skm_follows_pep440(version: str, specifier: str, expected: bool) -> None:
    assert requires_skm_matches(version, specifier) is expected


@pytest.mark.parametrize("specifier", ["", "2.0", ">=two", "~=2"])
def test_requires_skm_rejects_unsupported_specifiers(specifier: str) -> None:
    with pytest.raises(ValueError, match=r"PEP 440|segments"):
        requires_skm_matches("2.0.0", specifier)


def test_manifest_contract_suite_passes_for_the_fixture(site: Path) -> None:
    install(site)
    manifest = importlib.import_module(f"{PACKAGE}.plugin").MANIFEST
    assert isinstance(manifest, PluginManifest)
    report = manifest_contract_suite(manifest)
    report.raise_for_failures()
    assert report.passed[:4] == ("plugin_id", "api_version", "unique_keys", "runtime_data_paths")
    broken = manifest_contract_suite(replace(manifest, plugin_api=API_VERSION + 1))
    assert [failure.case for failure in broken.failures] == ["api_version"]
    assert plugin_test_context("acme.fixture").config() == {}


def test_cli_lint_flags_imports_outside_plugin_api(capsys: pytest.CaptureFixture[str]) -> None:
    source = FIXTURE / "src" / PACKAGE
    assert main(["plugins", "lint", str(source)]) == 1
    err = capsys.readouterr().err
    assert "PLUGIN_UNSTABLE_IMPORT" in err
    assert "unstable.py" in err
    assert "skm.modules.runtimes.public" in err
    assert "plugin.py" not in err
    assert main(["plugins", "lint", str(source / "plugin.py")]) == 0


def test_cli_lint_of_an_installed_distribution_checks_entry_points_and_data(
    site: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install(site)
    assert main(["plugins", "lint", "skm-plugin-fixture", "--json"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert [item["code"] for item in document["diagnostics"]] == ["PLUGIN_UNSTABLE_IMPORT"]
    assert document["result"]["target"] == "skm-plugin-fixture"
    assert f"{PACKAGE}.plugin" not in sys.modules  # lint never imports


def test_cli_lint_reports_an_unresolvable_entry_point(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = (FIXTURE / "src" / PACKAGE / "plugin.py").read_text().replace("MANIFEST = ", "RENAMED = ")
    install(site, files={f"{PACKAGE}/plugin.py": text, f"{PACKAGE}/unstable.py": None})
    assert main(["plugins", "lint", "skm-plugin-fixture", "--json"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert [item["code"] for item in document["diagnostics"]] == ["PLUGIN_LOAD_FAILED"]


def test_cli_list_and_show_do_not_import(
    site: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    found = entries(install(site))
    monkeypatch.setattr("skm.entrypoints.cli.commands.plugins.default_entry_points", lambda: found)
    assert main(["plugins", "list"]) == 0
    listed = capsys.readouterr().out
    assert "acme.fixture" in listed
    assert "fixture_rt" in listed
    assert main(["plugins", "show", "acme.fixture"]) == 0
    shown = capsys.readouterr().out
    assert "not imported" in shown
    assert "sha256:" in shown
    assert "unknown" in shown
    assert main(["plugins", "show", "acme.absent"]) != 0
    assert f"{PACKAGE}.plugin" not in sys.modules
    assert events() == []
