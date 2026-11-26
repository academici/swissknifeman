"""Early test-composition boundaries; full layer rules belong to P00.05."""

import ast
from pathlib import PurePosixPath


def violations(path: str, source: str) -> list[str]:
    parts = PurePosixPath(path).parts
    check_overrides = bool({"entrypoints", "background"} & set(parts))
    if (
        "maybe_fail" not in source
        and "tests" not in source
        and not (check_overrides and "overrides" in source)
    ):
        return []
    tree = ast.parse(source, filename=path)
    errors: list[str] = []
    if "maybe_fail" in source:
        errors.append(f"{path}: fault injection belongs to test port wrappers")
    aliases = {"build_app"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            aliases.update(alias.asname or alias.name for alias in node.names if alias.name == "build_app")
            if node.module and (node.module == "tests" or node.module.startswith("tests.")):
                errors.append(f"{path}:{node.lineno}: product imports test infrastructure")
        if isinstance(node, ast.Import) and any(
            alias.name == "tests" or alias.name.startswith("tests.") for alias in node.names
        ):
            errors.append(f"{path}:{node.lineno}: product imports test infrastructure")
    parts = PurePosixPath(path).parts
    if not ({"entrypoints", "background"} & set(parts)):
        return errors
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else (node.func.attr if isinstance(node.func, ast.Attribute) else "")
        )
        if name in aliases and any(keyword.arg == "overrides" for keyword in node.keywords):
            errors.append(f"{path}:{node.lineno}: CompositionOverrides is test-only")
    return errors
