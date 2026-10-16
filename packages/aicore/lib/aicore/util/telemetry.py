"""Names for traces and metrics (the ``telemetry-conventions/v1`` contract).

The canonical data is ``configs/telemetry-conventions.json``: the span names and how they nest, and the
attributes with their cardinality. Modules take span names from :func:`span_name` and check the labels of a
metric with :func:`metric_label_problems`, so that an id of a run or a request never becomes a metric label
(one time series per value would grow without bound). Nothing is exported here: no OpenTelemetry dependency.
stdlib and ``aicore.util`` only.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from . import schema

CONVENTIONS_FILE = "telemetry-conventions.json"
# Attributes of the OpenTelemetry GenAI conventions that metrics may carry next to the ``skm.`` ones.
GENAI_LABELS = ("gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model")
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "telemetry-conventions" / "v1"
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
_cache: Dict[Path, Dict[str, Any]] = {}

PathLike = Union[str, "Path"]


class ConventionsError(ValueError):
    """The conventions file is unreadable or does not satisfy ``telemetry-conventions/v1``."""


def default_conventions_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / CONVENTIONS_FILE


def _read(path: Path) -> Dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConventionsError(f"telemetry conventions unreadable: {path.name}: {exc}") from exc
    registry, kind = schema.load_contract(_SCHEMA_DIR)
    issues = schema.validate(doc, kind, registry)
    if issues:
        first = issues[0]
        raise ConventionsError(f"telemetry conventions invalid: {first.path or '/'}: {first.code}: {first.message}")
    return doc


def load_conventions(path: Optional[PathLike] = None) -> Dict[str, Any]:
    """The validated conventions document; ``None`` reads the packaged one. The caller owns the copy."""
    target = default_conventions_path() if path is None else Path(path)
    if path is not None:
        return _read(target)
    if target not in _cache:
        _cache[target] = _read(target)
    return copy.deepcopy(_cache[target])


def _conventions(conventions: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if conventions is not None:
        return conventions
    target = default_conventions_path()
    if target not in _cache:
        _cache[target] = _read(target)
    return _cache[target]


def metric_label_problems(labels: Iterable[str], conventions: Optional[Dict[str, Any]] = None) -> List[str]:
    """Why each of ``labels`` may not label a metric; an empty list means all may.

    A label is allowed when the conventions declare it with low cardinality, or when it is one of
    :data:`GENAI_LABELS`. Anything else is a problem: an id (high cardinality), a name without the ``skm.``
    prefix (``run_id``) and an undeclared ``skm.`` name.
    """
    declared = {item["name"]: item for item in _conventions(conventions)["attributes"]}
    problems = []
    for label in labels:
        if not isinstance(label, str):
            problems.append(f"label {label!r} is not a string")
        elif label in GENAI_LABELS:
            continue
        elif label in declared:
            if declared[label]["cardinality"] != "low":
                problems.append(f"label {label} has high cardinality; keep it on spans, not on metrics")
        elif not label.startswith("skm."):
            problems.append(f"label {label} must start with 'skm.' (or be a gen_ai.* attribute of the GenAI "
                            "conventions)")
        else:
            problems.append(f"label {label} is not declared in the telemetry conventions")
    return problems


def span_name(name: str, target: Optional[str] = None, conventions: Optional[Dict[str, Any]] = None) -> str:
    """The name to give a span of the conventions; ``ValueError`` for a name that is not one of them.

    A span that is also an OpenTelemetry GenAI span has a template such as ``invoke_agent {agent}``: with
    ``target`` (the agent or tool name) the result is that template filled in, without it the ``skm.`` name.
    ``target`` for a span without a template is an error.
    """
    spans = {item["name"]: item for item in _conventions(conventions)["spans"]}
    if name not in spans:
        raise ValueError(f"{name!r} is not a span name of the telemetry conventions")
    template = spans[name]["genai"]
    if target is None:
        return name
    if template is None:
        raise ValueError(f"span {name} takes no target")
    if not isinstance(target, str) or not target.strip() or not target.isprintable():
        raise ValueError("target must be a non-empty printable string")
    return _PLACEHOLDER.sub(lambda _match: target, template, count=1)
