"""Shared, deterministic settings import/export and invocation documents (§B.11.4)."""

from __future__ import annotations

import json
import math
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue

if TYPE_CHECKING:
    from skm.platform.config.layers import Contribution
    from skm.platform.config.registry import SettingsRegistry

__all__ = [
    "ConfigDocument",
    "DocEntry",
    "DocumentProblem",
    "decode_document",
    "decode_toml",
    "parse_document",
    "render_document",
]

_SCHEMA = "urn:skm:settings:document:v1"
type Format = Literal["toml", "json"]
# A JSON integer is read without the interpreter's int-to-text limit (sys.set_int_max_str_digits): that
# limit is 0 (off) or at least sys.int_info.str_digits_check_threshold (640 digits), so a part of 512 digits
# is always read. An integer token longer than a stored value may be (64 KiB canonical JSON) is syntax.
_INT_PART_DIGITS: Final = 512
_INT_TEXT_MAX: Final = 65536


@dataclass(frozen=True, slots=True)
class DocEntry:
    op: Literal["set", "unset", "append"]
    value: JsonValue

    def __post_init__(self) -> None:
        from skm.platform.config.keys import freeze_json

        if self.op not in ("set", "unset", "append") or (self.op == "unset" and self.value is not None):
            raise ValueError("invalid document operation")
        object.__setattr__(self, "value", freeze_json(self.value, "document"))


@dataclass(frozen=True, slots=True)
class DocumentProblem:
    code: str
    key: str
    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class ConfigDocument:
    entries: Mapping[str, DocEntry]
    locks: frozenset[str]
    problems: tuple[DocumentProblem, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))
        object.__setattr__(self, "locks", frozenset(self.locks))
        object.__setattr__(self, "problems", tuple(self.problems))


def _pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _json_int(text: str) -> int:
    """A JSON integer token (``-?digits``, as the scanner matched it) of any width up to ``_INT_TEXT_MAX``."""
    if len(text) <= _INT_PART_DIGITS:
        return int(text)
    if len(text) > _INT_TEXT_MAX:
        raise ValueError("a JSON integer is longer than a configuration value may be")
    digits = text.removeprefix("-")
    number = 0
    for start in range(0, len(digits), _INT_PART_DIGITS):
        part = digits[start : start + _INT_PART_DIGITS]
        number = number * 10 ** len(part) + int(part)
    return -number if len(digits) < len(text) else number


def copy_json(value: object, path: str) -> JsonValue:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path}: non-finite float is not JSON")
        return value
    if isinstance(value, list):
        return [copy_json(item, f"{path}[{idx}]") for idx, item in enumerate(cast("list[object]", value))]
    if isinstance(value, Mapping):
        copied: dict[str, JsonValue] = {}
        for key, item in cast("Mapping[object, object]", value).items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: object keys must be strings")
            copied[key] = copy_json(item, f"{path}.{key}")
        return copied
    raise TypeError(f"{path}: {type(value).__name__} is not a JSON value")


def decode_toml(document: str) -> dict[str, object]:
    """Parse TOML syntax, retaining native dates and times for provider configuration."""
    return tomllib.loads(document)


def decode_document(document: str | Mapping[str, object], fmt: Format) -> dict[str, JsonValue]:
    """Decode strict JSON/TOML syntax, shared with bootstrap before its separate v1 validation."""
    if fmt not in ("toml", "json"):
        raise ValueError("unsupported configuration document format")
    value = document
    if isinstance(value, str):
        if fmt == "toml":
            value = decode_toml(value)
        else:
            value = json.loads(value, object_pairs_hook=_pairs, parse_int=_json_int)
    copied = copy_json(value, "document")
    if not isinstance(copied, dict):
        raise ValueError("a configuration document must be an object")
    return copied


class _Parser:
    def __init__(self, registry: SettingsRegistry) -> None:
        self.registry = registry
        self.entries: dict[str, DocEntry] = {}
        self.problems: list[DocumentProblem] = []
        self.conflicts: set[str] = set()

    def problem(self, key: str, reason: str, *, code: str = "CONFIG_INVALID") -> None:
        self.problems.append(DocumentProblem(code, key, reason, "Invalid configuration document entry"))

    def add(self, key: str, op: Literal["set", "unset", "append"], value: JsonValue) -> None:
        if self.registry.find(key) is None:
            self.problem(key, "unknown_key", code="CONFIG_UNKNOWN_KEY")
            return
        if key in self.entries or key in self.conflicts:
            self.entries.pop(key, None)
            self.conflicts.add(key)
            self.problem(key, "conflicting_ops")
            return
        self.entries[key] = DocEntry(op, value)

    def walk(self, node: Mapping[str, JsonValue], prefix: str = "") -> None:
        for name, value in sorted(node.items()):
            key = f"{prefix}.{name}" if prefix else name
            # Every registered leaf is atomic, including deep_merge maps and their $unset markers.
            if self.registry.find(key) is not None:
                self.add(key, "set", value)
            elif isinstance(value, dict) and (
                value or any(spec.key.startswith(key + ".") for spec in self.registry.keys(chain=None))
            ):
                self.walk(value, key)
            else:
                self.problem(key, "unknown_key", code="CONFIG_UNKNOWN_KEY")

    def names(self, document: Mapping[str, JsonValue], field: str) -> frozenset[str]:
        value = document.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            self.problem(field, "key_list_required")
            return frozenset()
        names = cast("list[str]", value)
        if len(set(names)) != len(names):
            self.problem(field, "duplicate_keys")
        return frozenset(names)


def parse_document(
    document: str | Mapping[str, object], fmt: Format, registry: SettingsRegistry
) -> ConfigDocument:
    parser = _Parser(registry)
    try:
        data = decode_document(document, fmt)
    except (ValueError, TypeError, RecursionError):
        return ConfigDocument(
            {},
            frozenset(),
            (
                DocumentProblem(
                    "CONFIG_INVALID", "", "document_syntax", "Invalid configuration document syntax"
                ),
            ),
        )
    if "schema" in data and data["schema"] != _SCHEMA:
        parser.problem("schema", "document_schema")
    parser.walk({k: v for k, v in data.items() if k not in ("schema", "unset", "lock", "append")})
    for key in sorted(parser.names(data, "unset")):
        parser.add(key, "unset", None)
    append = data.get("append", {})
    if isinstance(append, dict):
        for key, value in sorted(append.items()):
            parser.add(key, "append", value)
    else:
        parser.problem("append", "object_required")
    locks = parser.names(data, "lock")
    for key in sorted(locks):
        if registry.find(key) is None:
            parser.problem(key, "unknown_key", code="CONFIG_UNKNOWN_KEY")
        elif key not in parser.entries:
            parser.problem(key, "lock_without_entry")
    return ConfigDocument(dict(sorted(parser.entries.items())), locks, tuple(parser.problems))


class _StoredEntry(Protocol):
    @property
    def key(self) -> str: ...
    @property
    def op(self) -> str: ...
    @property
    def value(self) -> JsonValue: ...
    @property
    def locked(self) -> bool: ...


def _toml_string(value: str) -> str:
    """JSON escapes fit TOML basic strings when DEL is escaped and non-BMP scalars stay literal."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _literal(value: JsonValue) -> str:
    if value is None:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "TOML cannot represent JSON null", details={"reason": "toml_null"}
        )
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_toml_string(k)} = {_literal(v)}" for k, v in sorted(value.items())) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    if isinstance(value, str):
        return _toml_string(value)
    return json.dumps(value, allow_nan=False)


def render_document(
    entries: Iterable[_StoredEntry] | Mapping[str, DocEntry | Contribution],
    registry: SettingsRegistry,
    *,
    fmt: Format,
) -> str | dict[str, JsonValue]:
    """Render entries, never effective defaults. JSON returns a document object; TOML returns text."""
    rows: Iterable[tuple[str, _StoredEntry | DocEntry | Contribution]]
    if isinstance(entries, Mapping):
        rows = cast("Mapping[str, DocEntry | Contribution]", entries).items()
    else:
        rows = ((entry.key, entry) for entry in entries)
    data: dict[str, JsonValue] = {"schema": _SCHEMA}
    sets: dict[str, dict[str, JsonValue]] = {}
    unset: list[JsonValue] = []
    locks: list[JsonValue] = []
    append: dict[str, JsonValue] = {}
    for key, entry in sorted(rows, key=lambda row: row[0]):
        registry.spec(key)
        if getattr(entry, "locked", False):
            locks.append(key)
        if entry.op == "unset":
            unset.append(key)
        elif entry.op == "append":
            append[key] = copy_json(entry.value, key)
        elif entry.op == "set":
            section, tail = key.split(".", 1)
            sets.setdefault(section, {})[tail] = copy_json(entry.value, key)
        else:
            raise ValueError("only stored document operations can be rendered")
    if unset:
        data["unset"] = unset
    if locks:
        data["lock"] = locks
    if append:
        data["append"] = append
    data.update(sets)
    if fmt == "json":
        return data
    if fmt != "toml":
        raise ValueError("unsupported configuration document format")
    lines = [f"schema = {_toml_string(_SCHEMA)}"]
    lines.extend(f"{special} = {_literal(data[special])}" for special in ("unset", "lock") if special in data)
    for section in (["append"] if append else []) + sorted(sets):
        lines.extend(("", f"[{_toml_string(section)}]"))
        values = append if section == "append" else sets[section]
        lines.extend(f"{_toml_string(key)} = {_literal(value)}" for key, value in sorted(values.items()))
    return "\n".join(lines) + "\n"
