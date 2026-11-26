"""MANIFEST of the fixture plugin (mechanisms/02-plugins §10); importing it is the import sentinel."""

from skm.plugin_api import API_VERSION, ComponentKind, ComponentSpec, PluginContext, PluginManifest, Side

from . import sentinel
from .isolation import FixtureIsolation
from .runtime import FixtureRuntime

sentinel.EVENTS.append("import:acme.fixture")


def _runtime(ctx: PluginContext) -> FixtureRuntime:
    sentinel.EVENTS.append("factory:runtime")
    return FixtureRuntime(ctx)


def _isolation(ctx: PluginContext) -> FixtureIsolation:
    sentinel.EVENTS.append("factory:isolation")
    return FixtureIsolation()


MANIFEST = PluginManifest(
    id="acme.fixture",
    version="0.1.0",
    plugin_api=API_VERSION,
    requires_skm=">=0.1.0,<1",
    title="Fixture runtime and sandbox",
    publisher="acme",
    components=(
        ComponentSpec(
            kind=ComponentKind.RUNTIME,
            key="fixture_rt",
            side=Side.HOST,
            factory=_runtime,
            capabilities="skm_runtimes/fixture_rt/capabilities.toml",
        ),
        ComponentSpec(kind=ComponentKind.ISOLATION, key="acme.fixture:jail", side=Side.HOST, factory=_isolation),
    ),
    settings_schema="schemas/settings/plugin-fixture.v1.json",
)
