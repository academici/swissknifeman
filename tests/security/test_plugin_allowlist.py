"""S16 (mechanisms/08-security-enforcement): an untrusted plugin is not executed.

A plugin outside ``plugins.allowed`` is never imported and its files are not read; discovery, the allowlist
and the runtime data of step 2a execute no plugin code; the control plane does not import a host plugin yet
sees its runtime in ``CapabilityCatalog.registered()``; an incompatible allowed manifest may be imported but
no factory of it runs; a key conflict stops the bootstrap before any factory. Separate sentinels record import
and factory effects."""

import sys
from collections.abc import Iterator, Mapping, Sequence
from importlib.metadata import Distribution, EntryPoint, PathDistribution
from pathlib import Path

import pytest

from skm.bootstrap.plugins import (
    LoadedPlugin,
    PluginSchema,
    PluginSchemas,
    PluginStatus,
    capability_catalog,
    default_entry_points,
    load_plugins,
)
from skm.kernel.errors import InternalError
from skm.platform.schema.registry import SchemaRegistry
from skm.plugin_api import Side

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "plugins" / "skm-plugin-fixture" / "src"
PACKAGE = "skm_plugin_fixture"


def install(
    site: Path, *, package: str = PACKAGE, plugin_id: str = "acme.fixture", **edits: str
) -> Distribution:
    """The fixture as an installed distribution; ``edits`` maps a package-relative file to new text."""
    changes = {"acme.fixture": plugin_id, PACKAGE: package, "acme_fixture": plugin_id.replace(".", "_")}
    if package != PACKAGE:
        changes["plugin-fixture"] = package.replace("_", "-")
    listed: list[str] = []
    for path in sorted(
        p for p in (FIXTURE / PACKAGE).rglob("*") if p.is_file() and "__pycache__" not in p.parts
    ):
        relative = path.relative_to(FIXTURE / PACKAGE).as_posix()
        text = edits.get(relative, path.read_text(encoding="utf-8"))
        for old, new in changes.items():
            relative, text = relative.replace(old, new), text.replace(old, new)
        (site / package / relative).parent.mkdir(parents=True, exist_ok=True)
        (site / package / relative).write_text(text, encoding="utf-8")
        listed.append(f"{package}/{relative}")
    info = site / f"{package}-0.1.0.dist-info"
    info.mkdir()
    name = package.replace("_", "-")
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n", encoding="utf-8")
    (info / "entry_points.txt").write_text(f"[skm.plugins]\n{plugin_id} = {package}.plugin:MANIFEST\n")
    (info / "RECORD").write_text("".join(f"{entry},,\n" for entry in listed) + f"{info.name}/RECORD,,\n")
    return PathDistribution(info)


def entries(*dists: Distribution) -> list[EntryPoint]:
    return [entry for dist in dists for entry in dist.entry_points if entry.group == "skm.plugins"]


def effects(package: str = PACKAGE) -> list[str]:
    """The sentinel of ``package``: absent (nothing ran) unless the plugin module was imported."""
    return list(getattr(sys.modules.get(f"{package}.sentinel"), "EVENTS", []))


def imported(package: str = PACKAGE) -> bool:
    return f"{package}.plugin" in sys.modules


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in [name for name in sys.modules if name.startswith("skm_plugin_")]:
        del sys.modules[name]


@pytest.fixture(scope="module")
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def load(
    schemas: SchemaRegistry,
    found: list[EntryPoint],
    allowed: Sequence[str],
    side: Side,
    control_plane_allowed: frozenset[str] = frozenset(),
) -> Mapping[str, LoadedPlugin]:
    def phase2(_documents: Sequence[PluginSchema], _urns: Sequence[str]) -> PluginSchemas:
        return PluginSchemas(schemas)

    plugins = load_plugins(
        allowed=allowed,
        required=frozenset(),
        side=side,
        skm_version="0.1.0",
        schemas=schemas,
        settings_phase2=phase2,
        discover=lambda: found,
        control_plane_allowed=control_plane_allowed,
    )
    return {plugin.plugin_id: plugin for plugin in plugins}


def test_real_discovery_reads_metadata_only(site: Path) -> None:
    install(site)
    assert "acme.fixture" in {entry.name for entry in default_entry_points()}
    assert not imported()
    assert effects() == []


@pytest.mark.parametrize("side", list(Side))
def test_plugin_outside_the_allowlist_is_never_imported(
    site: Path, schemas: SchemaRegistry, side: Side
) -> None:
    plugin = load(schemas, entries(install(site)), ["acme.other"], side)["acme.fixture"]
    assert plugin.status is PluginStatus.NOT_ALLOWED
    assert plugin.manifest is None
    assert plugin.runtime_data == {}  # not even its data files are read
    assert not imported()
    assert effects() == []


def test_control_plane_sees_a_host_runtime_without_importing_it(site: Path, schemas: SchemaRegistry) -> None:
    plugins = load(schemas, entries(install(site)), ["acme.fixture"], Side.CONTROL_PLANE)
    assert plugins["acme.fixture"].status is PluginStatus.DATA_ONLY
    assert capability_catalog(tuple(plugins.values())).registered() == frozenset({"fixture_rt"})
    assert not imported()
    assert effects() == []


def test_control_plane_allowed_still_constructs_no_host_component(
    site: Path, schemas: SchemaRegistry
) -> None:
    allowed = frozenset({"acme.fixture"})
    plugins = load(schemas, entries(install(site)), ["acme.fixture"], Side.CONTROL_PLANE, allowed)
    assert plugins["acme.fixture"].components == ()
    assert effects() == ["import:acme.fixture"]  # imported by permission, no factory of a host component ran


def test_runtime_data_is_read_without_executing_the_plugin(site: Path, schemas: SchemaRegistry) -> None:
    hostile = "import sys\nsys.modules['skm_plugin_fixture.sentinel'].EVENTS.append('import:hostile')\n"
    dist = install(site, **{"plugin.py": "from . import sentinel\n" + hostile + "raise SystemExit(3)\n"})
    plugins = load(schemas, entries(dist), ["acme.fixture"], Side.CONTROL_PLANE)
    assert set(plugins["acme.fixture"].runtime_data) == {"fixture_rt"}
    assert not imported()
    assert effects() == []


def test_incompatible_allowed_manifest_runs_import_but_no_factory(
    site: Path, schemas: SchemaRegistry
) -> None:
    text = (FIXTURE / PACKAGE / "plugin.py").read_text().replace("plugin_api=API_VERSION", "plugin_api=99")
    plugin = load(schemas, entries(install(site, **{"plugin.py": text})), ["acme.fixture"], Side.HOST)[
        "acme.fixture"
    ]
    assert plugin.status is PluginStatus.INCOMPATIBLE
    assert plugin.instances == {}
    assert effects() == ["import:acme.fixture"]  # import-time code is not sandboxed; factories never ran


@pytest.mark.parametrize("order", [["acme.fixture", "acme.twin"], ["acme.twin", "acme.fixture"]])
def test_conflict_stops_bootstrap_before_any_factory(
    site: Path, schemas: SchemaRegistry, order: list[str]
) -> None:
    found = entries(install(site), install(site, package="skm_plugin_twin", plugin_id="acme.twin"))
    with pytest.raises(InternalError) as caught:
        load(schemas, found, order, Side.BOTH)
    assert caught.value.details["reason_code"] == "PLUGIN_CONFLICT"
    produced = effects() + effects("skm_plugin_twin")
    assert not [event for event in produced if event.startswith("factory:")]
