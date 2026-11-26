"""File classification shared by the AST rules (tooling §6.2)."""

from enum import StrEnum
from pathlib import PurePath

MODULE_NAMES = frozenset(
    {
        "access",
        "settings",
        "workspace",
        "artifacts",
        "extensions",
        "policy",
        "runtimes",
        "planning",
        "context",
        "execution",
        "integrations",
        "knowledge",
        "learning",
        "exports",
    }
)


class Layer(StrEnum):
    KERNEL = "kernel"
    PLATFORM = "platform"
    DOMAIN = "domain"
    PORTS = "ports"
    APPLICATION = "application"
    HOST = "host"
    GENERATED = "generated"
    PUBLIC = "public"
    MODULE_META = "module_meta"
    BUS = "bus"
    ADAPTER = "adapter"
    BACKGROUND = "background"
    ENTRYPOINT = "entrypoint"
    BOOTSTRAP = "bootstrap"
    PLUGIN_API = "plugin_api"
    PACKAGE = "package"


def package_parts(path: PurePath) -> tuple[str, ...]:
    parts = path.with_suffix("").parts
    if "skm" in parts:
        return parts[parts.index("skm") + 1 :]
    return parts


def classify(path: PurePath) -> Layer:
    parts = package_parts(path)
    if not parts:
        return Layer.PACKAGE
    if parts[0] == "modules":
        if len(parts) < 3 or parts[2] == "__init__":
            return Layer.PACKAGE
        if parts[1:3] == ("knowledge", "contracts"):
            return Layer.PUBLIC
        if parts[2] in {"module", "settings", "permissions", "errors"}:
            return Layer.MODULE_META
        return Layer(parts[2]) if parts[2] in Layer else Layer.PACKAGE
    return {
        "application_bus": Layer.BUS,
        "adapters": Layer.ADAPTER,
        "entrypoints": Layer.ENTRYPOINT,
        "sdk": Layer.ENTRYPOINT,
    }.get(parts[0], Layer(parts[0]) if parts[0] in Layer else Layer.PACKAGE)
