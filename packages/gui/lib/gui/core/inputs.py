"""Typed input of queries (``params``) and commands (``input``): one validator for both (stdlib + aicore).

``validate`` checks a JSON object of values against the ``field`` list of a contribution descriptor and returns the
normalized values; every problem becomes an issue ``{pointer, code, message}`` and the whole call raises
``INPUT_INVALID`` with all of them. A ``project-path`` value stays inside the project after ``realpath`` (I5) and is
returned relative to the project root.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from aicore.util.paths import is_within

from ..errors import GuiError

MAX_STRING = 4096
Scalar = Union[str, int, float, bool]

REF_PATTERNS = {
    "plan-ref": re.compile(r"^(?:[0-9]{4}\.[0-9]{2}\.[0-9]{2}-№[0-9]+-[A-Z][A-Z0-9-]*|PLAN[0-9]+)$"),
    "item-ref": re.compile(r"^P[0-9]+\.[0-9]+$"),
    "model-ref": re.compile(r"^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    "secret-ref": re.compile(r"^(?:env|keyring)://[A-Za-z0-9._/-]+$"),
}


def _issue(pointer: str, code: str, message: str) -> Dict[str, str]:
    return {"pointer": pointer, "code": code, "message": message}


def _string(value: Any) -> Optional[Dict[str, str]]:
    """``{code, message}`` of the problem of a string value, else ``None``."""
    if not isinstance(value, str):
        return {"code": "type", "message": "expected a string"}
    if len(value) > MAX_STRING:
        return {"code": "max_length", "message": f"longer than {MAX_STRING} characters"}
    if "\x00" in value:
        return {"code": "invalid", "message": "contains a NUL character"}
    return None


def _project_path(value: str, project_root: Optional[Union[str, os.PathLike]]) -> Union[str, Dict[str, str]]:
    if project_root is None:
        return {"code": "path_escape", "message": "a project path needs a project context"}
    if value == "" or os.path.isabs(value):
        return {"code": "path_escape", "message": "expected a path relative to the project root"}
    root = os.path.realpath(project_root)
    candidate = os.path.realpath(os.path.join(root, value))
    if not is_within(candidate, root):
        return {"code": "path_escape", "message": "the path leads outside the project"}
    return os.path.relpath(candidate, root)


def check_value(field: Mapping[str, Any], value: Any, project_root=None) -> Union[Scalar, Dict[str, str]]:
    """The normalized value, or ``{code, message}`` of its problem."""
    kind = field["type"]
    if kind == "boolean":
        return value if isinstance(value, bool) else {"code": "type", "message": "expected true or false"}
    if kind in ("integer", "number"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or \
                (kind == "integer" and not isinstance(value, int)) or \
                (isinstance(value, float) and not math.isfinite(value)):
            return {"code": "type", "message": f"expected an {kind}" if kind == "integer" else "expected a number"}
        if "minimum" in field and value < field["minimum"]:
            return {"code": "minimum", "message": f"less than {field['minimum']}"}
        if "maximum" in field and value > field["maximum"]:
            return {"code": "maximum", "message": f"greater than {field['maximum']}"}
        return value
    problem = _string(value)
    if problem:
        return problem
    if kind == "enum":
        if value not in field.get("enum", ()):
            return {"code": "enum", "message": "not one of the allowed values"}
    elif kind in REF_PATTERNS and not REF_PATTERNS[kind].match(value):
        return {"code": "pattern", "message": f"not a valid {kind}"}
    if "pattern" in field:
        try:
            matched = re.fullmatch(field["pattern"], value) is not None
        except re.error:
            matched = False
        if not matched:
            return {"code": "pattern", "message": "does not match the pattern of the field"}
    if kind == "project-path":
        return _project_path(value, project_root)
    return value


def validate(fields: Sequence[Mapping[str, Any]], values: Any, project_root=None, *,
             pointer: str = "/params") -> Dict[str, Scalar]:
    """Normalized values of ``fields``; ``INPUT_INVALID`` with every issue otherwise."""
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise GuiError("INPUT_INVALID", "expected an object of values",
                       issues=[_issue(pointer, "type", "expected an object")])
    known = {field["name"]: field for field in fields}
    issues: List[Dict[str, str]] = []
    result: Dict[str, Scalar] = {}
    for name in sorted(set(values) - set(known)):
        issues.append(_issue(f"{pointer}/{name}", "unknown", "no such field"))
    for name, field in known.items():
        at = f"{pointer}/{name}"
        if name not in values or values[name] is None:
            if "default" in field:
                result[name] = field["default"]
            elif field.get("required"):
                issues.append(_issue(at, "required", "a value is required"))
            continue
        checked = check_value(field, values[name], project_root)
        if isinstance(checked, dict):
            issues.append(_issue(at, checked["code"], checked["message"]))
        else:
            result[name] = checked
    if issues:
        raise GuiError("INPUT_INVALID", f"{len(issues)} invalid value(s)", issues=issues)
    return result
