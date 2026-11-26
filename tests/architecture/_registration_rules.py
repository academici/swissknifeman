"""Materialized bus, repository, settings and database ownership rules."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from pathlib import Path

from ._boundary_rules import _Symbols
from ._layers import Layer
from ._rule_context import RuleContext, Violation, _violation
from ._tree import (
    SourceFile,
    aliases,
    dotted,
    resolve,
)


def _assigned(file: SourceFile, name: str) -> ast.expr | None:
    for node in file.tree.body:
        if isinstance(node, ast.Assign) and any(dotted(target) == name for target in node.targets):
            return node.value
        if isinstance(node, ast.AnnAssign) and dotted(node.target) == name:
            return node.value
    return None


def _canonical(file: SourceFile, node: ast.AST) -> str:
    name = resolve(dotted(node), aliases(file))
    return name if name.startswith("skm.") else f"{file.name}.{name}"


def _value(
    file: SourceFile, node: ast.expr, files: Mapping[str, SourceFile], seen: frozenset[str] = frozenset()
) -> tuple[SourceFile, ast.expr]:
    if isinstance(node, (ast.Name, ast.Attribute)):
        name = _canonical(file, node)
        owner, _, symbol = name.rpartition(".")
        target = files.get(owner)
        if name not in seen and target is not None and (value := _assigned(target, symbol)) is not None:
            return _value(target, value, files, seen | {name})
    return file, node


def _references(file: SourceFile, node: ast.expr, files: Mapping[str, SourceFile]) -> set[str]:
    if isinstance(node, (ast.Name, ast.Attribute)) and _canonical(file, node).endswith(".SPEC"):
        return {_canonical(file, node)}
    file, node = _value(file, node, files)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return {name for item in node.elts for name in _references(file, item, files)}
    if isinstance(node, ast.Starred):
        return _references(file, node.value, files)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _references(file, node.left, files) | _references(file, node.right, files)
    return {_canonical(file, node)}


def _call_keyword(node: ast.expr, name: str) -> ast.expr | None:
    return (
        next((kw.value for kw in node.keywords if kw.arg == name), None)
        if isinstance(node, ast.Call)
        else None
    )


def rule_bus_registration(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    files = {file.name: file for file in tree}
    catalog = files.get("skm.modules.access.permissions")
    declared = _assigned(catalog, "PERMISSIONS") if catalog is not None else None
    if isinstance(declared, ast.Call) and dotted(declared.func) == "frozenset" and declared.args:
        declared = declared.args[0]
    permissions = (
        {
            node.value
            for node in declared.elts
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        if isinstance(declared, (ast.Tuple, ast.List, ast.Set))
        else set()
    )
    result = []
    for file in tree:
        if (
            file.layer != Layer.APPLICATION
            or file.path.parent.name not in {"commands", "queries"}
            or file.path.name == "__init__.py"
        ):
            continue
        registry = files.get(f"skm.modules.{file.module}.application.registry")
        group = "COMMANDS" if file.path.parent.name == "commands" else "QUERIES"
        entries = _assigned(registry, group) if registry else None
        spec = _assigned(file, "SPEC")
        # Inspect registry references before expanding SPEC into its constructor.
        registered = (
            registry is not None
            and entries is not None
            and any(
                _canonical(registry, node) == f"{file.name}.SPEC"
                for node in ast.walk(entries)
                if isinstance(node, (ast.Name, ast.Attribute))
            )
        )
        if not registered and registry is not None and entries is not None:
            registered = f"{file.name}.SPEC" in _references(registry, entries, files)
        if spec is None or not registered:
            result.append(
                _violation("bus-registration", file, 1, f"{file.path.name}: SPEC missing or not registered")
            )
        if spec is not None:
            owner, expression = _value(file, spec, files)
            permission = _call_keyword(expression, "permission")
            if permission is not None:
                _, permission = _value(owner, permission, files)
            if not isinstance(permission, ast.Constant) or (
                permission.value not in permissions and not (group == "QUERIES" and permission.value is None)
            ):
                result.append(
                    _violation(
                        "bus-registration",
                        file,
                        getattr(spec, "lineno", 1),
                        "SPEC.permission is not in the permission catalog",
                    )
                )
            alternatives = _call_keyword(expression, "permission_alternatives")
            if alternatives is not None:
                _, alternatives = _value(owner, alternatives, files)
                if not isinstance(alternatives, ast.Tuple) or any(
                    not isinstance(item, ast.Constant) or item.value not in permissions
                    for item in alternatives.elts
                ):
                    result.append(
                        _violation(
                            "bus-registration",
                            file,
                            spec.lineno,
                            "SPEC.permission_alternatives must contain catalogued permission names",
                        )
                    )
    return result


def _protocol(node: ast.AST | None, file: SourceFile) -> bool:
    return isinstance(node, ast.ClassDef) and any(
        resolve(dotted(base), aliases(file)) in {"typing.Protocol", "typing_extensions.Protocol"}
        for base in node.bases
    )


def _factory(file: SourceFile, node: ast.expr, files: Mapping[str, SourceFile], symbols: _Symbols) -> bool:
    file, node = _value(file, node, files)
    if isinstance(node, ast.Lambda):
        return not isinstance(node.body, ast.Constant)
    canonical, declaration = symbols.find(_canonical(file, node))
    if isinstance(declaration, ast.ClassDef):
        return not _protocol(declaration, files[canonical.rpartition(".")[0]])
    return isinstance(declaration, ast.FunctionDef) and not any(
        isinstance(child, ast.Raise) and child.exc is not None and "NotImplementedError" in dotted(child.exc)
        for child in ast.walk(declaration)
    )


def _repository_table(
    file: SourceFile, files: Mapping[str, SourceFile], symbols: _Symbols
) -> tuple[dict[str, bool], list[Violation]]:
    table = _assigned(file, "REPOSITORIES") if file.path.name == "__init__.py" else None
    if table is None:
        return {}, []
    owner, table = _value(file, table, files)
    if isinstance(table, ast.Call) and dotted(table.func).endswith("MappingProxyType") and table.args:
        owner, table = _value(owner, table.args[0], files)
    message = ""
    if not isinstance(table, ast.Dict):
        message = "REPOSITORIES must be a statically inspectable mapping"
    elif any(key is None for key in table.keys):
        message = "REPOSITORIES unpacking is not statically inspectable"
    if message:
        return {}, [_violation("repository-ports-implemented", file, table.lineno, message)]
    assert isinstance(table, ast.Dict)
    return {
        symbols.find(_canonical(owner, key))[0]: _factory(owner, value, files, symbols)
        for key, value in zip(table.keys, table.values, strict=True)
        if key is not None
    }, []


def rule_repository_ports_implemented(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    files = {file.name: file for file in tree}
    symbols = _Symbols(tree)
    ports = {
        f"{file.name}.{node.name}": file
        for file in tree
        if file.layer == Layer.PORTS
        for node in file.tree.body
        if isinstance(node, ast.ClassDef)
        if symbols.kind(f"{file.name}.{node.name}") == "repository_port"
    }
    registered: dict[tuple[str, str], bool] = {}
    active = set(ctx.implemented_ports)
    backends: set[tuple[str | None, str]] = set()
    result = []
    for file in tree:
        if file.layer != Layer.ADAPTER or file.tech not in {"memory", "postgres"}:
            continue
        entries, errors = _repository_table(file, files, symbols)
        if file.path.name == "__init__.py" and _assigned(file, "REPOSITORIES") is not None:
            backends.add((file.module, file.tech))
        result.extend(errors)
        active.update(entries)
        registered.update({(port, file.tech): factory for port, factory in entries.items()})
        for node in file.tree.body:
            if not isinstance(node, ast.ClassDef) or _protocol(node, file):
                continue
            for name, port_file in ports.items():
                if port_file.module == file.module and (
                    node.name in {"Memory" + name.rsplit(".", 1)[-1], "Postgres" + name.rsplit(".", 1)[-1]}
                    or any(symbols.find(_canonical(file, base))[0] == name for base in node.bases)
                ):
                    active.add(name)
                    backends.add((file.module, file.tech))
    result.extend(
        _violation(
            "repository-ports-implemented", ports[port], 1, f"port {port} has no {tech} implementation"
        )
        for port in sorted(active & ports.keys())
        for tech in ("memory", "postgres")
        if port in ctx.implemented_ports or (ports[port].module, tech) in backends
        if not registered.get((port, tech), False)
    )
    return result


def _settings_catalog(root: Path | None) -> tuple[frozenset[str], frozenset[str]]:
    keys: set[str] = set()
    views: set[str] = set()

    def visit(node: dict, prefix: str) -> None:
        if "x-skm" in node:
            keys.add(prefix)
        else:
            for name, child in node.get("properties", {}).items():
                visit(child, prefix + "." + name)

    if root is not None:
        for path in sorted((root / "src/skm/schemas/settings").glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if "x-skm-section" not in document:
                continue
            visit(document, document["x-skm-section"]["id"])
            python = document.get("x-skm-codegen", {}).get("python", {})
            if python.get("kind") == "settings_view":
                views.add(python["module"] + "." + python["class"])
    return frozenset(keys), frozenset(views)


def rule_settings_declared(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    keys, views = _settings_catalog(ctx.root)
    keys = ctx.config_keys if ctx.config_keys is not None else keys
    views = ctx.config_views if ctx.config_views is not None else views
    symbols = _Symbols(tree)
    result = []
    for file in tree:
        bindings = aliases(file)
        receivers = {"config", "ctx.config", "self.config"}
        receivers.update(
            node.arg if isinstance(node, ast.arg) else dotted(node.target)
            for node in file.nodes
            if isinstance(node, (ast.arg, ast.AnnAssign))
            and node.annotation is not None
            and resolve(dotted(node.annotation), bindings).rsplit(".", 1)[-1] == "EffectiveConfig"
        )
        for node in file.nodes:
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = resolve(dotted(node.func.value), bindings)
            if receiver not in receivers and not receiver.endswith(".config"):
                continue
            argument = (
                node.args[0]
                if node.args
                else _call_keyword(node, "key" if node.func.attr == "get" else "view")
            )
            if argument is None:
                continue
            if (
                node.func.attr == "get"
                and isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
                and argument.value not in keys
            ):
                result.append(
                    _violation(
                        "settings-declared",
                        file,
                        node.lineno,
                        f"unknown config key '{argument.value}'",
                        argument.value,
                    )
                )
            if node.func.attr == "section":
                view = symbols.find(resolve(dotted(argument), bindings))[0]
                if view not in views:
                    result.append(
                        _violation(
                            "settings-declared", file, node.lineno, f"unknown config view '{view}'", view
                        )
                    )
    return result


_TABLE_OR_REFERENCE = re.compile(
    r"(?P<create>\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)"
    r"|(?P<alter>\bALTER\s+TABLE\s+(?:ONLY\s+)?)|(?P<reference>\bREFERENCES\s+)",
    re.IGNORECASE,
)
_QUALIFIED_TABLE = re.compile(r'(?:"?(?P<schema>\w+)"?\s*\.\s*)?"?(?P<table>\w+)"?')


def _module_schema(module: str) -> str:
    return "skm_config" if module == "settings" else f"skm_{module}"


def _migration_ownership(path: Path, ctx: RuleContext, *, machine: bool = False) -> list[Violation]:
    if ctx.root is None:
        return []
    relative = path.relative_to(ctx.root).as_posix()
    packaged_baseline = not machine and path.name == "0001_core_baseline.sql"
    file_module = path.stem.split("_")[1]
    if (file_module == "host") != machine:
        return [
            Violation("db-ownership", relative, 1, f"migration of {file_module} is in the wrong database")
        ]
    schema_owners = {_module_schema(module): module for module in ("core", *ctx.depends_on)}
    sql = re.sub(
        r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'",
        lambda match: "\n" * match.group().count("\n") + " ",
        path.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    violations: list[Violation] = []
    module = file_module
    for match in _TABLE_OR_REFERENCE.finditer(sql):
        table = _QUALIFIED_TABLE.match(sql, match.end())
        if table is None:
            continue
        schema = table["schema"] or ""
        line = sql[: match.start()].count("\n") + 1
        if match["reference"] is not None:
            allowed = {_module_schema(module)}
            if not machine:
                allowed.add("skm_core")
                allowed.update(_module_schema(dep) for dep in ctx.depends_on.get(module, ()))
            if schema not in allowed:
                violations.append(
                    Violation(
                        "db-ownership",
                        relative,
                        line,
                        f"reference to '{schema}' is outside depends_on of {module}",
                    )
                )
        elif packaged_baseline:
            owner = schema_owners.get(schema)
            if owner is None:
                violations.append(
                    Violation(
                        "db-ownership",
                        relative,
                        line,
                        f"table {schema}.{table['table']} has no project owner",
                    )
                )
            else:
                module = owner
        elif (machine or match["create"] is not None) and schema != _module_schema(module):
            violations.append(
                Violation(
                    "db-ownership",
                    relative,
                    line,
                    f"table {schema}.{table['table']} in migration of module {module}",
                )
            )
    return violations


def rule_db_ownership(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    if ctx.root is None:
        return []
    directory = ctx.root / "src/skm/adapters/postgres/migrations"
    return [
        violation
        for location, machine in (("sql", False), ("machine_sql", True))
        for path in sorted((directory / location).glob("[0-9][0-9][0-9][0-9]_*.sql"))
        for violation in _migration_ownership(path, ctx, machine=machine)
    ]
