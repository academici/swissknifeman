"""Emit ``kernel/generated/error_codes.py`` from the canonical error catalog (stdlib only).

The input is ``src/skm/schemas/kernel/data/error-codes.json``
(schema ``urn:skm:kernel:error-catalog:v1``). The emitter validates the document against the structural rules
of ``error-catalog.v1.json`` without importing
``skm`` or ``jsonschema``, so it runs on a bare scaffold before any kernel module exists. Output is
deterministic: member order follows the data document and a second run rewrites nothing.

Usage: ``python tools/codegen/error_catalog.py [--check] [--root PATH]``.
"""

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypeGuard

__all__ = [
    "CATALOG_RELPATH",
    "OUTPUT_DIR_RELPATH",
    "SCHEMA_RELPATH",
    "CatalogError",
    "generate",
    "load_catalog",
    "main",
    "render_error_codes",
    "render_package_marker",
    "render_typescript",
    "validate_catalog",
]

ROOT = Path(__file__).resolve().parents[2]
CATALOG_RELPATH = Path("src/skm/schemas/kernel/data/error-codes.json")
SCHEMA_RELPATH = Path("src/skm/schemas/kernel/error-catalog.v1.json")
OUTPUT_DIR_RELPATH = Path("src/skm/kernel/generated")
SCHEMA_URN = "urn:skm:kernel:error-catalog:v1"

_CATALOG_KEYS = frozenset({"schema", "version", "categories", "codes"})
_CATEGORY_KEYS = frozenset({"category", "http_status", "cli_exit"})
_CODE_KEYS = frozenset({"code", "category", "http_status", "cli_exit", "retryable", "description"})


class CatalogError(ValueError):
    """The catalog document or its schema is unusable; the message lists every problem found."""


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_exact_keys(path: str, row: object, keys: frozenset[str], problems: list[str]) -> bool:
    if not isinstance(row, dict):
        problems.append(f"{path}: must be an object")
        return False
    present = set(row)
    problems.extend(f"{path}: missing required field {missing!r}" for missing in sorted(keys - present))
    problems.extend(f"{path}: unexpected field {extra!r}" for extra in sorted(present - keys))
    return True


def _check_int_range(
    path: str, row: Mapping[str, Any], key: str, low: int, high: int, problems: list[str]
) -> None:
    value = row.get(key)
    if key in row and not (_is_int(value) and low <= value <= high):
        problems.append(f"{path}.{key}: must be an integer in [{low}, {high}], got {value!r}")


def _schema_rules(schema: Mapping[str, Any]) -> tuple[list[str], re.Pattern[str], int]:
    try:
        categories = list(schema["$defs"]["category"]["enum"])
        code_props = schema["properties"]["codes"]["items"]["properties"]
        pattern = re.compile(code_props["code"]["pattern"])
        max_description = int(code_props["description"]["maxLength"])
    except (KeyError, TypeError, ValueError, re.error) as error:
        raise CatalogError(f"error-catalog schema is unusable: {error!r}") from error
    return categories, pattern, max_description


def validate_catalog(document: object, schema: Mapping[str, Any]) -> list[str]:  # noqa: PLR0912
    """Return every structural problem of ``document`` (empty: valid); mirrors ``error-catalog.v1.json``."""
    categories, code_pattern, max_description = _schema_rules(schema)
    problems: list[str] = []
    if not isinstance(document, dict):
        return ["catalog: must be an object"]
    _check_exact_keys("catalog", document, _CATALOG_KEYS, problems)
    if "schema" in document and document["schema"] != SCHEMA_URN:
        problems.append(f"catalog.schema: must be {SCHEMA_URN!r}, got {document['schema']!r}")
    version = document.get("version")
    if "version" in document and not (_is_int(version) and version >= 1):
        problems.append(f"catalog.version: must be an integer >= 1, got {version!r}")

    declared: dict[str, tuple[object, object]] = {}
    rows = document.get("categories")
    if "categories" in document:
        if not isinstance(rows, list) or not rows:
            problems.append("catalog.categories: must be a non-empty array")
        else:
            for index, row in enumerate(rows):
                path = f"catalog.categories[{index}]"
                if not _check_exact_keys(path, row, _CATEGORY_KEYS, problems):
                    continue
                name = row.get("category")
                known = isinstance(name, str) and name in categories
                if not known:
                    problems.append(f"{path}.category: unknown category {name!r}")
                elif name in declared:
                    problems.append(f"{path}.category: duplicate category {name!r}")
                _check_int_range(path, row, "http_status", 200, 599, problems)
                _check_int_range(path, row, "cli_exit", 0, 255, problems)
                if known and name not in declared:
                    declared[name] = (row.get("http_status"), row.get("cli_exit"))
            problems.extend(
                f"catalog.categories: category {name!r} has no default mapping"
                for name in categories
                if name not in declared
            )

    codes = document.get("codes")
    if "codes" in document:
        if not isinstance(codes, list) or not codes:
            problems.append("catalog.codes: must be a non-empty array")
        else:
            seen: set[object] = set()
            for index, row in enumerate(codes):
                path = f"catalog.codes[{index}]"
                if not _check_exact_keys(path, row, _CODE_KEYS, problems):
                    continue
                _check_code_row(path, row, categories, code_pattern, max_description, seen, problems)
    return problems


def _check_code_row(
    path: str,
    row: Mapping[str, Any],
    categories: Sequence[str],
    code_pattern: re.Pattern[str],
    max_description: int,
    seen: set[object],
    problems: list[str],
) -> None:
    code = row.get("code")
    if not isinstance(code, str) or code_pattern.fullmatch(code) is None:
        problems.append(f"{path}.code: must match {code_pattern.pattern!r}, got {code!r}")
    elif code in seen:
        problems.append(f"{path}.code: duplicate code {code!r}")
    else:
        seen.add(code)
    category = row.get("category")
    if not isinstance(category, str) or category not in categories:
        problems.append(f"{path}.category: unknown category {row.get('category')!r}")
    _check_int_range(path, row, "http_status", 200, 599, problems)
    _check_int_range(path, row, "cli_exit", 0, 255, problems)
    if not isinstance(row.get("retryable"), bool):
        problems.append(f"{path}.retryable: must be a boolean, got {row.get('retryable')!r}")
    description = row.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= max_description:
        problems.append(f"{path}.description: must be a string of 1..{max_description} characters")


def load_catalog(root: Path = ROOT) -> dict[str, Any]:
    """Read and validate the canonical catalog under ``root``; raise ``CatalogError`` when it is invalid."""
    try:
        schema = json.loads((root / SCHEMA_RELPATH).read_text(encoding="utf-8"))
        document = json.loads((root / CATALOG_RELPATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError(f"cannot read the error catalog under {root}: {error}") from error
    problems = validate_catalog(document, schema)
    if problems:
        raise CatalogError("invalid error catalog:\n" + "\n".join(f"  - {problem}" for problem in problems))
    return document


def _literal(text: str) -> str:
    # A JSON string literal is a valid Python string literal; keeping non-ASCII text readable.
    return json.dumps(text, ensure_ascii=False)


def render_package_marker() -> str:
    return '"""Generated modules of the kernel (tools/codegen); do not edit by hand."""\n'


def render_error_codes(document: Mapping[str, Any]) -> str:
    """Render the text of ``generated/error_codes.py`` for a validated catalog document."""
    category_rows: list[Mapping[str, Any]] = list(document["categories"])
    code_rows: list[Mapping[str, Any]] = list(document["codes"])
    lines = [
        "# generated by tools/codegen/error_catalog.py; do not edit",
        '"""Error catalog (generated; do not edit).',
        "",
        f"Source: {CATALOG_RELPATH.as_posix()} ({document['schema']}).",
        "Generator: tools/codegen/error_catalog.py (`uv run python tools/codegen/error_catalog.py`).",
        '"""',
        "",
        "from collections.abc import Mapping",
        "from dataclasses import dataclass",
        "from enum import StrEnum",
        "from types import MappingProxyType",
        "from typing import Final",
        "",
        '__all__ = ["CATALOG", "CATALOG_VERSION", "ErrorCategory", "ErrorCode", "ErrorCodeInfo"]',
        "",
        f"CATALOG_VERSION: Final = {document['version']}",
        "",
        "",
        "class ErrorCategory(StrEnum):",
    ]
    lines.extend(f"    {row['category'].upper()} = {_literal(row['category'])}" for row in category_rows)
    lines.extend(["", "", "class ErrorCode(StrEnum):"])
    lines.extend(f"    {row['code']} = {_literal(row['code'])}" for row in code_rows)
    lines.extend(
        [
            "",
            "",
            "@dataclass(frozen=True, slots=True)",
            "class ErrorCodeInfo:",
            "    code: ErrorCode",
            "    category: ErrorCategory",
            "    http_status: int",
            "    cli_exit: int",
            "    retryable: bool",
            "    description: str",
            "",
            "",
            "_INFOS: Final = (",
        ]
    )
    lines.extend(
        f"    ErrorCodeInfo(ErrorCode.{row['code']}, ErrorCategory.{row['category'].upper()}, "
        f"{row['http_status']}, {row['cli_exit']}, {row['retryable']}, {_literal(row['description'])}),"
        for row in code_rows
    )
    lines.extend(
        [
            ")",
            "",
            "CATALOG: Final[Mapping[ErrorCode, ErrorCodeInfo]] = MappingProxyType(",
            "    {info.code: info for info in _INFOS}",
            ")",
            "",
        ]
    )
    return "\n".join(lines)


def render_typescript(document: Mapping[str, Any]) -> str:
    """Emit literal error metadata and types from the validated catalog."""
    lines = [
        f"// generated by tools/gen.py from {CATALOG_RELPATH.as_posix()}; do not edit",
        "",
        f"export const ERROR_CATALOG_VERSION = {document['version']};",
        "",
        "export const ERROR_CATEGORIES = {",
    ]
    for row in document["categories"]:
        defaults = {key: row[key] for key in ("http_status", "cli_exit")}
        lines.append(f"  {json.dumps(row['category'])}: {json.dumps(defaults)},")
    lines.extend(["} as const;", "", "export const ERROR_CATALOG = {"])
    for row in document["codes"]:
        info = {key: value for key, value in row.items() if key != "code"}
        lines.append(f"  {json.dumps(row['code'])}: {json.dumps(info, sort_keys=True)},")
    lines.extend(
        [
            "} as const;",
            "",
            "export type ErrorCategory = keyof typeof ERROR_CATEGORIES;",
            "export type ErrorCode = keyof typeof ERROR_CATALOG;",
        ]
    )
    return "\n".join(lines) + "\n"


def _outputs(root: Path) -> dict[Path, str]:
    document = load_catalog(root)
    target = root / OUTPUT_DIR_RELPATH
    return {
        target / "__init__.py": render_package_marker(),
        target / "error_codes.py": render_error_codes(document),
    }


def generate(root: Path = ROOT, *, check: bool = False) -> list[Path]:
    """Write the generated files under ``root`` and return the paths that changed.

    With ``check=True`` nothing is written; the paths that are missing or stale are returned instead.
    """
    changed: list[Path] = []
    for path, text in _outputs(root).items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        changed.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate kernel/generated/error_codes.py from the catalog.")
    parser.add_argument("--check", action="store_true", help="do not write; exit 1 when files are stale")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    args = parser.parse_args(argv)
    try:
        changed = generate(args.root, check=args.check)
    except CatalogError as error:
        print(f"error_catalog: {error}", file=sys.stderr)
        return 2
    if args.check:
        for path in changed:
            print(f"error_catalog: stale or missing: {path}", file=sys.stderr)
        return 1 if changed else 0
    for path in changed:
        print(f"error_catalog: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
