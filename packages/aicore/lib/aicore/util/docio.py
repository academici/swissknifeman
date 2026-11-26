"""A JSON document on disk, checked against its schema both ways: parse -> migrate -> validate on read, validate ->
serialize -> ``durable_replace`` on write. The caller maps the errors to its own reason codes. stdlib + aicore only."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union, cast

from .io import durable_replace
from .schema import Registry, ValidationIssue, validate

PathLike = Union[str, "os.PathLike[str]"]


class DocumentCorrupt(Exception):
    """The file is not readable JSON (bad bytes, bad syntax)."""

    def __init__(self, path: PathLike, error: Exception):
        self.path, self.error = Path(path), error
        super().__init__(f"{self.path}: not a readable JSON document: {error}")


class DocumentInvalid(Exception):
    """The document does not match its schema; ``issues`` are the ``ValidationIssue`` found."""

    def __init__(self, path: PathLike, issues: Sequence[Union[ValidationIssue, str]]):
        self.path, self.issues = Path(path), list(issues)
        first = self.issues[0] if self.issues else ""
        super().__init__(f"{self.path}: does not match its schema ({len(self.issues)} issues): {first}")


def read_document(path: PathLike, *, kind: str, registry: Registry,
                  migrate: Optional[Callable[[object], object]] = None) -> Optional[dict[str, Any]]:
    """The validated document at ``path``; ``None`` when the file does not exist. ``migrate`` (old shape -> current
    shape) runs before validation. ``DocumentCorrupt`` for bytes that are not JSON, ``DocumentInvalid`` for a mismatch;
    other ``OSError`` (no access, a directory) propagate."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as error:
        raise DocumentCorrupt(path, error) from None
    try:
        document = json.loads(text, parse_constant=_no_constant, parse_float=_finite_float)
    except ValueError as error:
        raise DocumentCorrupt(path, error) from None
    if migrate is not None:
        document = migrate(document)
    issues: list[ValidationIssue] = validate(document, kind, registry)
    if issues:
        raise DocumentInvalid(path, issues)
    return cast(dict[str, Any], document)


def write_document(path: PathLike, document: object, *, kind: str, registry: Registry, mode: int = 0o600) -> None:
    """Validate ``document`` and replace ``path`` with it crash-safely (``durable_replace``); an invalid document
    raises ``DocumentInvalid`` and the file is not touched."""
    issues = validate(document, kind, registry)
    if issues:
        raise DocumentInvalid(path, issues)
    try:
        text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except ValueError as error:  # NaN or an infinity: not JSON, and a schema bound never rejects it
        raise DocumentInvalid(path, [f"not a JSON number: {error}"]) from None
    durable_replace(path, text.encode("utf-8"), mode=mode)


def _no_constant(name: str) -> float:
    """``NaN``, ``Infinity`` and ``-Infinity`` are not JSON: a document that holds one is corrupt."""
    raise ValueError(f"{name} is not a JSON number")


def _finite_float(text: str) -> float:
    """A float literal that overflows to an infinity (``1e999``) is not a JSON number this module accepts."""
    value = float(text)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{text} is not a finite JSON number")
    return value
