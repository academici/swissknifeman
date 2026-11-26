"""Parse sources without importing them; preserve symbol, alias and annotation edges."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property
from importlib.util import resolve_name
from pathlib import Path

from ._layers import MODULE_NAMES, Layer, classify, package_parts


@dataclass
class SourceFile:
    """Lazy source snapshot shared by rules; create a new instance after editing a file.

    Trees and node tuples are read-only by convention. Fact helpers return fresh
    lists or dicts so a rule cannot mutate another rule's cached results.
    """

    path: Path
    layer: Layer
    module: str | None = None
    tech: str | None = None
    surface: str | None = None
    source: str | None = field(default=None, repr=False)

    @classmethod
    def at(cls, path: Path, source: str | None = None) -> SourceFile:
        parts = package_parts(path)
        module = parts[1] if len(parts) > 1 and parts[0] == "modules" else None
        if len(parts) > 3 and parts[0] == "adapters" and parts[2] in MODULE_NAMES:
            module = parts[2]
        return cls(
            path,
            classify(path),
            module,
            parts[1] if len(parts) > 1 and parts[0] == "adapters" else None,
            parts[1]
            if len(parts) > 1 and parts[0] == "entrypoints"
            else "sdk"
            if parts[:1] == ("sdk",)
            else None,
            source,
        )

    @cached_property
    def text(self) -> str:
        return self.source if self.source is not None else self.path.read_text(encoding="utf-8")

    @cached_property
    def tree(self) -> ast.Module:
        return ast.parse(self.text, filename=str(self.path))

    @cached_property
    def nodes(self) -> tuple[ast.AST, ...]:
        return tuple(ast.walk(self.tree))

    @cached_property
    def parents(self) -> Mapping[ast.AST, ast.AST]:
        from types import MappingProxyType

        return MappingProxyType({child: node for node in self.nodes for child in ast.iter_child_nodes(node)})

    @cached_property
    def name(self) -> str:
        parts = package_parts(self.path)
        return ".".join(("skm", *(parts[:-1] if parts[-1] == "__init__" else parts)))

    @cached_property
    def display_path(self) -> str:
        parts = self.path.parts
        if "src" in parts:
            return Path(*parts[parts.index("src") :]).as_posix()
        return self.path.as_posix()

    @cached_property
    def _imports_cache(self) -> tuple[ImportRef, ...]:
        return _compute_imports(self)

    @cached_property
    def _aliases_cache(self) -> Mapping[str, str]:
        from types import MappingProxyType

        return MappingProxyType(_compute_aliases(self))

    @cached_property
    def _calls_cache(self) -> tuple[CallRef, ...]:
        bindings = self._aliases_cache
        return tuple(
            CallRef(resolve(dotted(node.func), bindings), node.lineno)
            for node in self.nodes
            if isinstance(node, ast.Call)
        )

    @cached_property
    def _strings_cache(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            (node.value, node.lineno)
            for node in self.nodes
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )

    @cached_property
    def _async_cache(self) -> tuple[ast.AST, ...]:
        return tuple(
            node
            for node in self.nodes
            if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncWith, ast.AsyncFor))
            or (isinstance(node, ast.comprehension) and node.is_async)
        )


def collect(root: Path) -> list[SourceFile]:
    """Accept a repository root, src root or package root; exclude test packages."""
    package = root / "src/skm" if (root / "src/skm").is_dir() else root
    if (package / "skm").is_dir():
        package /= "skm"
    return [
        SourceFile.at(path)
        for path in sorted(package.rglob("*.py"))
        if not {"tests", "__pycache__"}.intersection(path.relative_to(package).parts)
    ]


@dataclass(frozen=True)
class ImportRef:
    module: str
    line: int
    names: tuple[str, ...] = ()
    bindings: tuple[str, ...] = ()
    type_checking: bool = False
    annotation_only: bool = False
    # Executed when a function body runs rather than when the module is imported.
    deferred: bool = False

    @property
    def targets(self) -> tuple[str, ...]:
        return tuple(f"{self.module}.{name}" for name in self.names) or (self.module,)


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return dotted(node.func)
    if isinstance(node, ast.Subscript):
        return dotted(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return dotted(node.left)
    return ""


def _annotation_nodes(nodes: tuple[ast.AST, ...]) -> set[ast.AST]:
    result: set[ast.AST] = set()
    for node in nodes:
        annotation = None
        if isinstance(node, (ast.arg, ast.AnnAssign)):
            annotation = node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotation = node.returns
        elif isinstance(node, ast.TypeAlias):
            annotation = node.value
        if annotation:
            result.update(ast.walk(annotation))
    # A constructor/call inside an annotation is executable, not a type reference.
    for node in tuple(result):
        if isinstance(node, ast.Call):
            result.difference_update(ast.walk(node))
    return result


def imports(file: SourceFile) -> list[ImportRef]:
    return list(file._imports_cache)


def _compute_imports(file: SourceFile) -> tuple[ImportRef, ...]:
    annotations = _annotation_nodes(file.nodes)
    runtime_names: set[str] = set()
    guards: set[str] = set()
    assigned: set[str] = set()
    for node in file.nodes:
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load) and node not in annotations:
                runtime_names.add(node.id)
            elif isinstance(node.ctx, ast.Store):
                assigned.add(node.id)
        elif isinstance(node, ast.arg):
            assigned.add(node.arg)
        elif isinstance(node, ast.ImportFrom) and node.module == "typing":
            guards.update(a.asname or a.name for a in node.names if a.name == "TYPE_CHECKING")
        elif isinstance(node, ast.Import):
            guards.update(f"{a.asname or a.name}.TYPE_CHECKING" for a in node.names if a.name == "typing")
    guards = {guard for guard in guards if guard.split(".")[0] not in assigned}
    result: list[ImportRef] = []

    def visit(node: ast.AST, guarded: bool = False, deferred: bool = False) -> None:
        if isinstance(node, ast.If):
            for child in node.body:
                visit(child, guarded or dotted(node.test) in guards, deferred)
            for child in node.orelse:
                visit(child, guarded, deferred)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                binding = alias.asname or alias.name.split(".")[0]
                result.append(
                    ImportRef(
                        alias.name,
                        node.lineno,
                        (),
                        (binding,),
                        guarded,
                        binding not in runtime_names,
                        deferred,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                package = file.name if file.path.name == "__init__.py" else file.name.rpartition(".")[0]
                module = resolve_name("." * node.level + module, package)
            # One ref per imported name keeps mixed type/runtime imports independent.
            for alias in node.names:
                binding = alias.asname or alias.name
                result.append(
                    ImportRef(
                        module,
                        node.lineno,
                        (alias.name,),
                        (binding,),
                        guarded,
                        alias.name != "*" and binding not in runtime_names,
                        deferred,
                    )
                )
        nested = deferred or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        for child in ast.iter_child_nodes(node):
            visit(child, guarded, nested)

    visit(file.tree)
    return tuple(result)


def _is_path_annotation(node: ast.AST, bindings: Mapping[str, str]) -> bool:
    """Recognize a Path value type, including unions and unevaluated forward references."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            expression = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return False
        return _is_path_annotation(expression, bindings)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_path_annotation(node.left, bindings) or _is_path_annotation(node.right, bindings)
    return isinstance(node, (ast.Name, ast.Attribute)) and resolve(dotted(node), bindings) == "pathlib.Path"


def aliases(file: SourceFile) -> dict[str, str]:
    return dict(file._aliases_cache)


def _compute_aliases(file: SourceFile) -> dict[str, str]:
    result: dict[str, str] = {}
    for ref in imports(file):
        for binding, target in zip(ref.bindings, ref.targets, strict=True):
            # Unaliased `import a.b` binds a, whereas `import a.b as c` binds a.b.
            result[binding] = target if ref.names or binding != target.split(".")[0] else binding
    for node in file.nodes:
        if (
            isinstance(node, (ast.arg, ast.AnnAssign))
            and node.annotation is not None
            and _is_path_annotation(node.annotation, result)
        ):
            binding = node.arg if isinstance(node, ast.arg) else dotted(node.target)
            result.setdefault(binding, "pathlib.Path")
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                result.setdefault(f"self.{binding}", "pathlib.Path")
        if isinstance(node, ast.Assign):
            value = resolve(dotted(node.value), result)
            if value:
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id not in result
                        and not hasattr(builtins, target.id)
                    ):
                        result[target.id] = value
    return result


def resolve(name: str, bindings: Mapping[str, str]) -> str:
    if name in bindings:
        return bindings[name]
    if "." in name and any("." in key for key in bindings):
        # Attribute bindings include annotated Path fields (e.g. self.root).
        for binding in sorted((k for k in bindings if "." in k), key=len, reverse=True):
            if name == binding or name.startswith(binding + "."):
                return bindings[binding] + name[len(binding) :]
    head, separator, tail = name.partition(".")
    return bindings.get(head, head) + (separator + tail if separator else "")


@dataclass(frozen=True)
class CallRef:
    name: str
    line: int


def calls(file: SourceFile) -> list[CallRef]:
    return list(file._calls_cache)


def string_constants(file: SourceFile) -> list[tuple[str, int]]:
    return list(file._strings_cache)


def async_defs(file: SourceFile) -> list[ast.AST]:
    return list(file._async_cache)
