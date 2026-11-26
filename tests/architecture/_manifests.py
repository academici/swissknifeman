"""Read the materialized module declarations, without starting application services."""

from importlib import import_module

from skm.kernel.module_manifest import ModuleManifest


def load_manifests() -> tuple[ModuleManifest, ...]:
    # bootstrap.modules.MANIFESTS is not materialized yet (P00.04.f excludes that file).
    from skm.bootstrap import modules

    manifests = vars(modules).get("MANIFESTS")
    if manifests is not None:
        return tuple(manifests)
    return tuple(import_module(f"skm.modules.{entry.id}.module").MODULE for entry in modules.MODULE_CATALOG)


def dependencies() -> dict[str, tuple[str, ...]]:
    return {manifest.id: manifest.depends_on for manifest in load_manifests()}
