"""Static import-layer, module-facade, declared-dependency, cycle and private-import rules."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from ._layers import Layer
from ._rule_context import DECLARATION_CONTRACTS, VALUE_ANNOTATIONS, RuleContext, Violation, _violation
from ._tree import (
    ImportRef,
    SourceFile,
    imports,
)


@cache
def _target(target: str) -> SourceFile:
    # Symbol suffixes do not change the containing layer.
    return SourceFile.at(Path("src") / (target.replace(".", "/") + ".py"))


def _annotation(file: SourceFile, ref: ImportRef, target: str, ctx: RuleContext) -> bool:
    pair = (file.name, target)
    return ref.annotation_only and (
        (ref.type_checking and pair in ctx.annotation_contracts) or pair in VALUE_ANNOTATIONS
    )


def _under(target: str, *prefixes: str) -> bool:
    return any(target == prefix or target.startswith(prefix + ".") for prefix in prefixes)


def _platform_allowed(file: SourceFile, target: str) -> bool:
    if file.layer == Layer.APPLICATION:
        return _under(target, *(f"skm.platform.{p}" for p in ("config", "schema", "logging", "jsonc")))
    if file.layer == Layer.HOST:
        return _under(target, "skm.platform.logging", "skm.platform.jsonc") or target in {
            "skm.platform.config.EffectiveConfig",
            "skm.platform.fs.FsRoot",
            "skm.platform.process.ProcessResult",
            "skm.platform.process.ProcessSpec",
        }
    if file.layer == Layer.GENERATED:
        return _under(target, "skm.platform.schema")
    return file.layer in {
        Layer.PLATFORM,
        Layer.PUBLIC,
        Layer.MODULE_META,
        Layer.BUS,
        Layer.ADAPTER,
        Layer.BACKGROUND,
        Layer.ENTRYPOINT,
        Layer.BOOTSTRAP,
    }


# These exact core-port symbols are implemented by the memory adapter (adapters §2,
# kernel-platform §4.4). Keep all other adapter-to-bus imports forbidden.
_MEMORY_BUS_PORTS = frozenset(
    {
        "AuditLog",
        "AuditRecord",
        "ConsumerReceipts",
        "EventReader",
        "IdempotencyReceipt",
        "IdempotencyStore",
        "OutboxEntry",
        "OutboxItem",
        "OutboxState",
        "OutboxStore",
    }
)

# The unit-of-work owners route outbox rows by these exact registry constants (adapters §1.3-1.4, §2).
_UOW_REGISTRY_OWNERS = frozenset(
    {"skm.adapters.memory.uow", "skm.adapters.postgres.uow", "skm.adapters.postgres.core.events_store"}
)
_UOW_REGISTRY_SYMBOLS = frozenset(
    {
        "skm.application_bus.registry.SSE_DESTINATION",
        "skm.application_bus.registry.OUTBOX_EXTERNAL_PREFIXES",
    }
)
_POSTGRES_CORE_BUS_PORTS = frozenset(
    {
        "skm.application_bus.ports.ConsumerReceipts",
        "skm.application_bus.ports.EventReader",
        "skm.application_bus.ports.OutboxStore",
    }
)
# Each postgres core adapter imports only the record its own port exchanges (adapters §1.4-1.6).
_POSTGRES_CORE_RECORD_IMPORTS = {
    "skm.adapters.postgres.core.audit": frozenset({"skm.application_bus.ports.AuditRecord"}),
    "skm.adapters.postgres.core.idempotency": frozenset({"skm.application_bus.ports.IdempotencyReceipt"}),
    "skm.adapters.postgres.core.outbox": frozenset(
        {
            "skm.application_bus.ports.OutboxEntry",
            "skm.application_bus.ports.OutboxItem",
            "skm.application_bus.ports.OutboxState",
        }
    ),
}


def _bus_allowed(file: SourceFile, target: str) -> bool:
    if (
        file.name == "skm.adapters.memory.core" or file.name.startswith("skm.adapters.memory.core.")
    ) and target in {f"skm.application_bus.ports.{name}" for name in _MEMORY_BUS_PORTS}:
        return True
    if file.name in _UOW_REGISTRY_OWNERS and target in _UOW_REGISTRY_SYMBOLS:
        return True
    # The postgres core table binds only the bus ports its adapters already implement (adapters §1.1).
    if file.name == "skm.adapters.postgres.core" and target in _POSTGRES_CORE_BUS_PORTS:
        return True
    if target in _POSTGRES_CORE_RECORD_IMPORTS.get(file.name, ()):
        return True
    names = {
        Layer.APPLICATION: ("registry", "context", "ports"),
        Layer.HOST: ("host", "client"),
        Layer.MODULE_META: ("registry",),
        Layer.BACKGROUND: ("dispatch", "ServiceRunner"),
    }.get(file.layer, ())
    return file.layer in {Layer.BUS, Layer.ENTRYPOINT, Layer.BOOTSTRAP} or _under(
        target, *(f"skm.application_bus.{name}" for name in names)
    )


def _module_allowed(file: SourceFile, destination: SourceFile, target: str) -> bool:
    layer = file.layer
    if layer == Layer.BOOTSTRAP:
        return True
    if layer == Layer.ADAPTER:
        return destination.layer in {Layer.DOMAIN, Layer.PORTS, Layer.GENERATED, Layer.PUBLIC}
    if layer == Layer.ENTRYPOINT or layer in {Layer.BACKGROUND, Layer.PLUGIN_API}:
        return destination.layer == Layer.PUBLIC
    if not file.module:
        return False
    if destination.module != file.module:
        return layer in {Layer.APPLICATION, Layer.HOST} and destination.layer == Layer.PUBLIC
    own_layers = {
        Layer.DOMAIN: {Layer.DOMAIN},
        Layer.PORTS: {Layer.DOMAIN, Layer.GENERATED, Layer.PORTS},
        Layer.APPLICATION: {Layer.DOMAIN, Layer.PORTS, Layer.APPLICATION, Layer.GENERATED, Layer.PUBLIC},
        Layer.HOST: {Layer.DOMAIN, Layer.PORTS, Layer.HOST, Layer.GENERATED, Layer.PUBLIC},
        Layer.GENERATED: {Layer.GENERATED},
        Layer.PUBLIC: {Layer.DOMAIN, Layer.PORTS, Layer.APPLICATION, Layer.GENERATED, Layer.PUBLIC},
        Layer.MODULE_META: {
            Layer.DOMAIN,
            Layer.PORTS,
            Layer.APPLICATION,
            Layer.HOST,
            Layer.GENERATED,
            Layer.PUBLIC,
            Layer.MODULE_META,
        },
    }
    if layer == Layer.DOMAIN and destination.layer == Layer.GENERATED:
        return _under(
            target,
            f"skm.modules.{file.module}.generated.events",
            f"skm.modules.{file.module}.generated.documents",
        )
    return destination.layer in own_layers.get(layer, set())


def _allowed(file: SourceFile, target: str) -> bool:
    if (file.name, target) in DECLARATION_CONTRACTS:
        return True
    destination = _target(target)
    if file.layer == Layer.BOOTSTRAP:
        return destination.layer != Layer.ENTRYPOINT
    if target == "skm.__version__":
        return True
    if destination.layer == Layer.KERNEL:
        return True
    if destination.layer == Layer.PLATFORM:
        return _platform_allowed(file, target)
    if target.startswith("skm.modules."):
        return _module_allowed(file, destination, target)
    if destination.layer == Layer.BUS:
        return _bus_allowed(file, target)
    return {
        Layer.ADAPTER: file.layer == Layer.ADAPTER and file.tech == destination.tech,
        Layer.ENTRYPOINT: file.layer == Layer.ENTRYPOINT and file.surface == destination.surface,
        Layer.BOOTSTRAP: file.layer == Layer.ENTRYPOINT,
    }.get(destination.layer, file.layer == destination.layer and file.layer != Layer.PACKAGE)


def rule_layer_imports(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        _violation(
            "layer-imports",
            file,
            ref.line,
            f"import of '{target}' ({_target(target).layer}) is not allowed from {file.layer}",
        )
        for file in tree
        for ref in imports(file)
        for target in ref.targets
        if target.startswith("skm.")
        and not _annotation(file, ref, target, ctx)
        and not _allowed(file, target)
    ]


def rule_module_facade(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = []
    for file in tree:
        if not file.module or file.layer in {Layer.ADAPTER, Layer.BOOTSTRAP}:
            continue
        for ref in imports(file):
            for target in ref.targets:
                destination = _target(target)
                if (
                    target.startswith("skm.modules")
                    and destination.module != file.module
                    and (destination.layer != Layer.PUBLIC or "*" in ref.names)
                ):
                    result.append(
                        _violation(
                            "module-facade",
                            file,
                            ref.line,
                            f"module '{file.module}' imports '{target}': "
                            f"use skm.modules.{destination.module}.public",
                        )
                    )
    return result


def rule_module_graph(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = []
    for file in tree:
        if not file.module or file.layer in {Layer.ADAPTER, Layer.BOOTSTRAP}:
            continue
        for ref in imports(file):
            for target in ref.targets:
                destination = _target(target)
                if (
                    destination.layer == Layer.PUBLIC
                    and destination.module != file.module
                    and (destination.module not in ctx.depends_on.get(file.module, ()))
                ):
                    result.append(
                        _violation(
                            "module-graph",
                            file,
                            ref.line,
                            f"module '{file.module}' depends on '{destination.module}' "
                            "which is not in depends_on",
                        )
                    )
    visited: set[str] = set()
    active: list[str] = []

    def visit(name: str) -> None:
        path = f"src/skm/modules/{name}/module.py"
        if name in active:
            cycle = [*active[active.index(name) :], name]
            result.append(Violation("module-graph", path, 1, "cycle: " + " -> ".join(cycle)))
        elif name not in ctx.depends_on:
            result.append(Violation("module-graph", path, 1, f"unknown module dependency: {name}"))
        elif name not in visited:
            active.append(name)
            for dependency in ctx.depends_on[name]:
                visit(dependency)
            active.pop()
            visited.add(name)

    for name in ctx.depends_on:
        visit(name)
    return result


# Function-local imports may legitimately defer optional or heavy code (plugin registries, cold-start paths),
# but inside a module's pure core they only ever hide a cycle; there every runtime import counts.
_PURE_CORE = frozenset({Layer.DOMAIN, Layer.PORTS})


def _import_edges(tree: list[SourceFile]) -> dict[str, dict[str, int]]:
    files = {file.name: file for file in tree}
    edges: dict[str, dict[str, int]] = {}
    for file in tree:
        for ref in imports(file):
            if ref.type_checking:
                continue
            for target in ref.targets:
                name = target
                while name and name not in files:
                    name = name.rpartition(".")[0]
                destination = files.get(name)
                if destination is None or destination.name == file.name:
                    continue
                pure_pair = (
                    file.layer in _PURE_CORE
                    and destination.layer in _PURE_CORE
                    and file.module is not None
                    and file.module == destination.module
                )
                if not ref.deferred or pure_pair:
                    edges.setdefault(file.name, {}).setdefault(destination.name, ref.line)
    return edges


def _cycles(edges: dict[str, dict[str, int]]) -> list[list[str]]:
    """Strongly connected components with more than one file (iterative Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[list[str]] = []
    for root in sorted(edges):
        if root in index:
            continue
        work = [(root, iter(sorted(edges.get(root, {}))))]
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is None:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component: list[str] = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    if len(component) > 1:
                        result.append(sorted(component))
            elif child not in index:
                index[child] = low[child] = len(index)
                stack.append(child)
                on_stack.add(child)
                work.append((child, iter(sorted(edges.get(child, {})))))
            elif child in on_stack:
                low[node] = min(low[node], index[child])
    return result


def rule_import_cycles(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    """Module-level imports form no cycle; in domain and ports, neither do function-local ones."""
    files = {file.name: file for file in tree}
    edges = _import_edges(tree)
    result = []
    for component in _cycles(edges):
        members = set(component)
        cycle = ", ".join(component)
        for name in component:
            for target, line in sorted(edges[name].items()):
                if target in members:
                    result.append(
                        _violation(
                            "import-cycles",
                            files[name],
                            line,
                            f"import of '{target}' closes an import cycle among {cycle}: "
                            "move the shared values into a lower module",
                        )
                    )
    return result


def _is_private(segment: str) -> bool:
    return segment.startswith("_") and not segment.startswith("__")


def _private_owner(target: str, packages: frozenset[str]) -> str | None:
    """The package that owns the first ``_private`` segment of ``target``, or ``None`` if it has none.

    A private name or module belongs to the package it sits in: ``a.b._c`` is owned by ``a.b`` when ``a.b``
    is a package, and by ``a`` when ``a.b`` is a module defining ``_c``. Inside ``skm.modules.<name>`` the
    whole module owns its internals, because module-facade already guards that boundary from the outside.
    """
    parts = target.split(".")
    index = next((i for i, part in enumerate(parts) if _is_private(part)), None)
    if index is None:
        return None
    container = ".".join(parts[:index])
    owner = container if container in packages else container.rpartition(".")[0]
    if _under(owner, "skm.modules") and len(owner.split(".")) > 3:
        owner = ".".join(owner.split(".")[:3])
    return owner


def _generated_codec(file: SourceFile, target: str) -> bool:
    # Generated records share the emitted conversion runtime; codegen writes both sides.
    return "generated" in file.path.parts and _under(target, "skm.kernel.generated._codec")


def rule_private_imports(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    """A ``_private`` module or name is imported only from inside the package that owns it."""
    packages = frozenset(file.name for file in tree if file.path.name == "__init__.py")
    result = []
    for file in tree:
        for ref in imports(file):
            for target in ref.targets:
                owner = _private_owner(target, packages)
                if owner is None or _under(file.name, owner) or _generated_codec(file, target):
                    continue
                result.append(
                    _violation(
                        "private-imports",
                        file,
                        ref.line,
                        f"import of '{target}' reaches into private code of '{owner}': "
                        "import a public module or make the name public",
                        ref.module,
                    )
                )
    return result
