"""Prompt block manifest and variable extraction/validation (extensions §4.8)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = [
    "ALLOWED_NAMESPACES",
    "PromptBlockManifest",
    "extract_variables",
    "validate_prompt_block_variables",
]

ALLOWED_NAMESPACES: Final = frozenset(
    {
        "task",
        "plan",
        "run",
        "role",
        "runtime",
        "permissions",
        "block",
    }
)
_ESCAPED_BRACES_RE: Final = re.compile(r"""\{\{\s*["']\{\{["']\s*\}\}""")
_VARIABLE_RE: Final = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_VAR_FORMAT_RE: Final = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True, slots=True)
class PromptBlockManifest:
    block_type: str
    variables: tuple[str, ...] = ()


def _check_namespace(variable: str) -> None:
    if _VAR_FORMAT_RE.fullmatch(variable) is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unknown variable namespace: {variable}",
            details={"reason": "unknown_variable_namespace", "variable": variable},
        )
    ns, _ = variable.split(".", 1)
    if ns not in ALLOWED_NAMESPACES:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unknown variable namespace: {variable}",
            details={"reason": "unknown_variable_namespace", "variable": variable},
        )


def extract_variables(text: str) -> frozenset[str]:
    """Extract all ``{{ namespace.name }}`` variables from ``text``, ignoring escaped ``{{"{{"}}``."""
    cleaned = _ESCAPED_BRACES_RE.sub("", text)
    found: set[str] = set()
    for match in _VARIABLE_RE.finditer(cleaned):
        var = match.group(1).strip()
        _check_namespace(var)
        found.add(var)
    return frozenset(found)


def validate_prompt_block_variables(
    manifest: Mapping[str, object], body: str, *, key: str = ""
) -> frozenset[str]:
    """Validate prompt block body variables against ``ALLOWED_NAMESPACES`` and declared ``variables``."""
    extracted = extract_variables(body)
    raw_vars = manifest.get("variables", ()) if manifest else ()
    declared: set[str] = set()
    if isinstance(raw_vars, (list, tuple, set, frozenset)):
        for item in cast("Iterable[object]", raw_vars):
            var = str(item)
            _check_namespace(var)
            declared.add(var)
    for var in sorted(extracted):
        if var not in declared:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"undeclared variable in prompt block: {var}",
                details={"reason": "undeclared_variable", "variable": var, "key": key},
            )
    return extracted
