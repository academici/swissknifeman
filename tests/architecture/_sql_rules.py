"""SQL syntax safety with lexical binding and identifier allowlist analysis."""

from __future__ import annotations

import ast
from collections.abc import Mapping

from ._layers import Layer
from ._rule_context import RuleContext, Violation, _violation
from ._tree import (
    SourceFile,
    aliases,
    dotted,
    resolve,
)


def _sql_bindings(file: SourceFile, call: ast.Call) -> dict[str, list[ast.expr]]:
    """Track local SQL assignments; arguments shadow constants from outer scopes."""
    parents = file.parents
    scopes: list[ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda] = [file.tree]
    parent: ast.AST = call
    enclosing = []
    while parent in parents:
        parent = parents[parent]
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            enclosing.append(parent)
    scopes.extend(reversed(enclosing))
    values: dict[str, list[ast.expr]] = {}
    for scope in scopes:
        local: dict[str, list[ast.expr]] = {}
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for arg in (
                *scope.args.posonlyargs,
                *scope.args.args,
                *scope.args.kwonlyargs,
                scope.args.vararg,
                scope.args.kwarg,
            ):
                if arg is not None:
                    local[arg.arg] = [ast.Constant(value=None)]

        def visit(node: ast.AST, local: dict[str, list[ast.expr]] = local) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                if not isinstance(node, ast.Lambda):
                    local.setdefault(node.name, []).append(ast.Constant(value=None))
                return
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        local.setdefault(target.id, []).extend([node.value] if node.value is not None else [])
                    else:
                        for name in ast.walk(target):
                            if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                                local.setdefault(name.id, []).append(ast.Constant(value=None))
                if node.value is not None:
                    visit(node.value)
                return
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                local.setdefault(node.id, []).append(ast.Constant(value=None))
            if isinstance(node, ast.ExceptHandler) and node.name:
                local.setdefault(node.name, []).append(ast.Constant(value=None))
            for child in ast.iter_child_nodes(node):
                visit(child)

        for node in [scope.body] if isinstance(scope, ast.Lambda) else scope.body:
            visit(node)
        values.update(local)
    return values


def _constant_sql(
    node: ast.AST, values: Mapping[str, list[ast.expr]], seen: frozenset[str] = frozenset()
) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Name) and node.id not in seen:
        return bool(values.get(node.id)) and all(
            _constant_sql(value, values, seen | {node.id}) for value in values[node.id]
        )
    if isinstance(node, ast.JoinedStr):
        return all(
            _constant_sql(part.value, values, seen)
            and (part.format_spec is None or _constant_sql(part.format_spec, values, seen))
            if isinstance(part, ast.FormattedValue)
            else _constant_sql(part, values, seen)
            for part in node.values
        )
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Add)
        and _constant_sql(node.left, values, seen)
        and _constant_sql(node.right, values, seen)
    )


def _identifier_allowlist(
    node: ast.AST, values: Mapping[str, list[ast.expr]], seen: frozenset[str] = frozenset()
) -> bool:
    if isinstance(node, ast.Subscript):
        return _identifier_allowlist(node.value, values, seen)
    if isinstance(node, ast.Name) and node.id not in seen:
        return (
            node.id.isupper()
            and bool(values.get(node.id))
            and all(_identifier_allowlist(value, values, seen | {node.id}) for value in values[node.id])
        )
    if isinstance(node, ast.Dict):
        return all(
            isinstance(key, ast.Constant) and _constant_sql(value, values)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return bool(node.elts) and all(_constant_sql(value, values) for value in node.elts)
    return _constant_sql(node, values, seen)


def _safe_sql(
    node: ast.expr,
    values: Mapping[str, list[ast.expr]],
    bindings: dict[str, str],
    seen: frozenset[str] = frozenset(),
) -> bool:
    if _constant_sql(node, values):
        return True
    if isinstance(node, ast.Name) and node.id not in seen:
        return bool(values.get(node.id)) and all(
            _safe_sql(value, values, bindings, seen | {node.id}) for value in values[node.id]
        )
    if not isinstance(node, ast.Call):
        return False
    name = resolve(dotted(node.func), bindings)
    if name == "psycopg.sql.SQL":
        return len(node.args) == 1 and _constant_sql(node.args[0], values)
    if name == "psycopg.sql.Identifier":
        return bool(node.args) and all(_identifier_allowlist(arg, values) for arg in node.args)
    if name == "psycopg.sql.Placeholder":
        return all(_constant_sql(arg, values) for arg in node.args)
    if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return _safe_sql(node.func.value, values, bindings, seen) and all(
            _safe_sql(arg, values, bindings, seen)
            for arg in [*node.args, *(kw.value for kw in node.keywords)]
        )
    return False


def rule_no_fstring_sql(tree: list[SourceFile], ctx: RuleContext) -> list[Violation]:
    result = []
    for file in tree:
        if file.layer != Layer.ADAPTER or file.tech != "postgres":
            continue
        bindings = aliases(file)
        for node in file.nodes:
            if not isinstance(node, ast.Call) or resolve(dotted(node.func), bindings).rsplit(".", 1)[
                -1
            ] not in {"execute", "executemany"}:
                continue
            query = (
                node.args[0]
                if node.args
                else next((kw.value for kw in node.keywords if kw.arg in {"query", "operation"}), None)
            )
            if (query is None and any(kw.arg is None for kw in node.keywords)) or (
                query is not None and not _safe_sql(query, _sql_bindings(file, node), bindings)
            ):
                result.append(
                    _violation(
                        "no-fstring-sql",
                        file,
                        node.lineno,
                        "SQL uses external data as syntax: bind values as parameters; "
                        "use constant identifier allowlists",
                    )
                )
    return result
