"""Purity rules and static resolution of host/application port boundaries."""

from __future__ import annotations

import ast

from ._import_rules import _annotation, _target, _under
from ._layers import Layer
from ._rule_context import DECLARATION_CONTRACTS, PATH_CONTRACTS, RuleContext, Violation, _violation
from ._tree import (
    SourceFile,
    aliases,
    calls,
    dotted,
    imports,
    resolve,
)

FORBIDDEN_IMPORTS = (
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "tempfile",
    "io",
    "threading",
    "asyncio",
    "time",
    "random",
    "secrets",
    "logging",
    "pathlib",
    "psycopg",
    "psycopg_pool",
    "starlette",
    "uvicorn",
    "httpx",
    "keyring",
    "jsonschema",
    "referencing",
    "requests",
    "urllib.request",
    "http",
)
FORBIDDEN_CALLS = frozenset(
    {
        "print",
        "open",
        "input",
        "exec",
        "eval",
        "compile",
        "__import__",
        "builtins.print",
        "builtins.open",
        "builtins.input",
        "builtins.exec",
        "builtins.eval",
        "builtins.compile",
        "builtins.__import__",
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
        "datetime.datetime.today",
        "datetime.date.today",
        "uuid.uuid1",
        "uuid.uuid4",
        "time.time",
        "time.monotonic",
        "time.sleep",
        "datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "date.today",
    }
)


def _cancel_primitive(file: SourceFile, target: str) -> bool:
    # Bounded P01.06.c exception: kernel-platform §2.11b requires Event-based
    # cancellation. Whole threading/time imports and every other purity rule stay forbidden.
    return file.display_path == "src/skm/kernel/cancel.py" and target in {
        "threading.Event",
        "threading.Lock",
        "time.monotonic",
    }


def _purity(tree: list[SourceFile], layers: set[Layer], rule: str) -> list[Violation]:
    result = []
    for file in tree:
        if file.layer not in layers:
            continue
        for ref in imports(file):
            for target in ref.targets:
                path_annotation = (
                    target == "pathlib.Path" and file.name in PATH_CONTRACTS and ref.annotation_only
                )
                if _under(target, *FORBIDDEN_IMPORTS) and not (
                    path_annotation or _cancel_primitive(file, target)
                ):
                    result.append(
                        _violation(
                            rule, file, ref.line, f"import of '{target}' is forbidden in {file.layer}", target
                        )
                    )
        result.extend(
            _violation(
                rule,
                file,
                call.line,
                f"call of '{call.name}' is forbidden in {file.layer}: use a gateway",
                call.name,
            )
            for call in calls(file)
            if (call.name in FORBIDDEN_CALLS or _under(call.name, "pathlib.Path"))
            and not _cancel_primitive(file, call.name)
        )
    return result


def rule_domain_purity(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return _purity(tree, {Layer.DOMAIN, Layer.PORTS, Layer.GENERATED, Layer.KERNEL}, "domain-purity")


def rule_host_io(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    return [
        *_purity(tree, {Layer.HOST}, "host-io"),
        *(
            _violation("host-io", file, call.line, "direct SQL in host operation: use ctx.client")
            for file in tree
            if file.layer == Layer.HOST
            for call in calls(file)
            if call.name.rsplit(".", 1)[-1] in {"execute", "executemany"}
        ),
    ]


class _Symbols:
    """Resolve reexports to port markers and facade definitions, with cycle protection."""

    def __init__(self, tree: list[SourceFile]):
        self.files = {file.name: file for file in tree}
        self._find_cache: dict[str, tuple[str, ast.AST | None]] = {}
        self._kind_cache: dict[str, str | None] = {}
        self._expanded_cache: dict[str, tuple[str, ...]] = {}

    def find(self, target: str, seen: frozenset[str] = frozenset()) -> tuple[str, ast.AST | None]:
        if not seen and target in self._find_cache:
            return self._find_cache[target]
        if target in seen:
            return target, None
        module, _, symbol = target.rpartition(".")
        file = self.files.get(module)
        if file is None:
            return target, None
        for node in file.tree.body:
            if (
                isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == symbol
            ):
                if not seen:
                    self._find_cache[target] = (target, node)
                return target, node
        binding = aliases(file).get(symbol)
        if binding:
            local_names = {
                node.name
                for node in file.tree.body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            }
            local_names.update(
                target.id
                for node in file.tree.body
                if isinstance(node, ast.Assign)
                for target in node.targets
                if isinstance(target, ast.Name)
            )
            if binding.split(".")[0] in local_names:
                binding = f"{file.name}.{binding}"
        res = self.find(binding, seen | {target}) if binding else (target, None)
        if not seen:
            self._find_cache[target] = res
        return res

    def expanded(self, target: str, seen: frozenset[str] = frozenset()) -> list[str]:
        if not seen and target in self._expanded_cache:
            return list(self._expanded_cache[target])
        # A namespace import grants access to every symbol, so check the namespace too.
        target_resolved = self.find(target)[0]
        if target_resolved in seen:
            return []
        if target_resolved in self.files:
            file = self.files[target_resolved]
            out = [
                target_resolved,
                *(
                    f"{target_resolved}.{n.name}"
                    for n in file.tree.body
                    if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                ),
                *(
                    candidate
                    for binding in aliases(file).values()
                    for candidate in self.expanded(binding, seen | {target_resolved})
                ),
            ]
        else:
            out = [target_resolved]
        if not seen:
            self._expanded_cache[target] = tuple(out)
        return out

    def kind(self, target: str, seen: frozenset[str] = frozenset()) -> str | None:
        if not seen and target in self._kind_cache:
            return self._kind_cache[target]
        canonical, node = self.find(target)
        if canonical in seen:
            return None
        res: str | None = None
        if isinstance(node, ast.ClassDef):
            file = self.files[canonical.rpartition(".")[0]]
            bindings = aliases(file)
            for decorator in node.decorator_list:
                name = resolve(dotted(decorator), bindings).rsplit(".", 1)[-1]
                if name in {"repository_port", "host_gateway", "control_plane_gateway", "shared_gateway"}:
                    res = name
                    break
            if res is None:
                for base in node.bases:
                    name = resolve(dotted(base), bindings)
                    if "." not in name:
                        name = f"{file.name}.{name}"
                    inherited = self.kind(name, seen | {canonical})
                    if inherited:
                        res = inherited
                        break
        if not seen:
            self._kind_cache[target] = res
        return res


def _host_forbidden(file: SourceFile, target: str, symbols: _Symbols) -> bool:
    canonical, node = symbols.find(target)
    destination = _target(canonical)
    if destination.layer == Layer.PORTS and symbols.kind(target) not in {"host_gateway", "shared_gateway"}:
        return (file.name, target) not in DECLARATION_CONTRACTS
    if _under(canonical, "skm.kernel.ports_uow", "skm.adapters", "skm.application_bus.bus"):
        return True
    if destination.layer == Layer.APPLICATION or symbols.kind(target) in {
        "repository_port",
        "control_plane_gateway",
    }:
        return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        arg.arg == "uow" for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    ):
        return True
    if ".host.stages." in file.name:
        return canonical in {
            "skm.application_bus.host",
            "skm.application_bus.client",
            "skm.application_bus.host.HostContext",
            "skm.application_bus.client.SkmClient",
        }
    return False


def rule_host_boundary(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = []
    symbols = _Symbols(tree)
    for file in tree:
        if file.layer != Layer.HOST:
            continue
        for ref in imports(file):
            for target in ref.targets:
                if _annotation(file, ref, target, ctx):
                    continue
                candidates = symbols.expanded(target.removesuffix(".*"))
                if any(_host_forbidden(file, candidate, symbols) for candidate in candidates):
                    result.append(
                        _violation(
                            "host-boundary",
                            file,
                            ref.line,
                            f"host operation imports '{target}': talk to the control plane via ctx.client",
                        )
                    )
        result.extend(
            _violation(
                "host-boundary",
                file,
                node.lineno,
                "host operation has control-plane access: use StageDeps/ctx.client",
            )
            for node in file.nodes
            if (
                (isinstance(node, ast.Name) and node.id == "uow")
                or (isinstance(node, ast.arg) and node.arg == "uow")
                or (isinstance(node, ast.Attribute) and node.attr == "uow")
                or (
                    ".host.stages." in file.name and isinstance(node, ast.Attribute) and node.attr == "client"
                )
            )
        )
    return result


def rule_application_boundary(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    symbols = _Symbols(tree)
    return [
        _violation(
            "application-boundary",
            file,
            ref.line,
            f"bus handler uses host gateway '{target}': move the IO into a host operation",
        )
        for file in tree
        if file.layer == Layer.APPLICATION
        for ref in imports(file)
        for target in ref.targets
        if any(
            symbols.kind(candidate) == "host_gateway"
            or _under(symbols.find(candidate)[0], "skm.application_bus.host")
            for candidate in symbols.expanded(target.removesuffix(".*"))
        )
    ]
