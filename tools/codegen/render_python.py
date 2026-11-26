"""Render frozen value objects, raw documents and converters from the normalized model."""

import json

from .model import Declaration, Model, Type, snake
from .parse import Parser

# A decimal literal past the interpreter's int-to-text limit does not compile. No limit is below 640 digits
# (sys.int_info.str_digits_check_threshold) and hexadecimal is exempt, so a wider integer is written in hex.
_DECIMAL_BOUND = 10**640


def literal(value) -> str:
    """``repr(value)`` of a schema constant, except that an integer of more than 640 digits is hexadecimal."""
    if isinstance(value, bool) or not isinstance(value, (int, tuple, list, dict)):
        return repr(value)
    if isinstance(value, int):
        return int.__repr__(value) if -_DECIMAL_BOUND < value < _DECIMAL_BOUND else hex(value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{literal(k)}: {literal(v)}" for k, v in value.items()) + "}"
    items = [literal(v) for v in value]
    if isinstance(value, list):
        return "[" + ", ".join(items) + "]"
    return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"


def _wide(t: Type) -> bool:
    if any(isinstance(v, int) and not -_DECIMAL_BOUND < v < _DECIMAL_BOUND for v in t.values):
        return True
    return any(_wide(a) for a in t.args)


def descriptor(t: Type, model: Model) -> tuple:
    reference = ()
    if t.ref:
        d = model.declarations[t.ref]
        reference = (d.module, d.name)
    return t.tag, tuple(descriptor(a, model) for a in t.args), t.values, reference


def _admits_none(t: Type) -> bool:
    return t.tag == "null" or (t.tag == "union" and any(_admits_none(a) for a in t.args))


def type_text(t: Type, model: Model, module: str, json_mode: bool = False) -> str:
    if t.tag in ("ref", "record"):
        d = model.declarations[t.ref]
        return d.name if d.module == module else "_" + d.module.replace(".", "_") + "." + d.name
    primitive = {
        "any": "Any",
        "never": "Never",
        "object": "JsonObject",
        "null": "None",
        "uuid": "str" if json_mode else "UUID",
        "date": "str" if json_mode else "date",
        "datetime": "str" if json_mode else "datetime",
        "secret": "SecretRef",
    }
    if t.tag in primitive:
        return primitive[t.tag]
    parts = [type_text(a, model, module, json_mode) for a in t.args]
    if t.tag == "literal":
        return "Literal[" + ", ".join(literal(v) for v in t.values) + "]"
    if t.tag == "union":
        return " | ".join(dict.fromkeys(parts))
    if t.tag == "array":
        return f"list[{parts[0]}]" if json_mode else f"tuple[{parts[0]}, ...]"
    if t.tag == "tuple":
        return (
            "list[" + " | ".join(dict.fromkeys(parts)) + "]"
            if json_mode
            else "tuple[" + ", ".join(parts) + "]"
        )
    if t.tag == "map":
        return f"{'dict' if json_mode else 'Mapping'}[str, {parts[0]}]"
    return t.tag


def render(model: Model, declarations: list[Declaration], header: str, digest: str) -> str:
    module = declarations[0].module
    # Python materializes foreign JSON shapes locally instead of importing private
    # module/platform implementations. The shared model and TypeScript stay intact.
    if model.python_model is None:
        model.python_model = Parser(model.documents, python_boundaries=True).run()
        from .scoped_settings import project

        project(model.python_model)
    model = model.python_model
    declarations = [d for d in {d.key: d for d in model.declarations.values()}.values() if d.module == module]
    imports = set()

    def collect(t):
        if t.ref:
            other = model.declarations[t.ref].module
            if other != module:
                imports.add(other)
        for a in t.args:
            collect(a)

    for d in declarations:
        collect(d.type)
        for f in d.fields:
            collect(f.type)
    lines = [
        header,
        "from __future__ import annotations",
        "",
        "from collections.abc import Mapping",
        "from dataclasses import dataclass",
        "from datetime import date, datetime",
        "from enum import StrEnum",
        "from typing import Any, ClassVar, ForwardRef, Literal, Never, NotRequired, Self, TypedDict",
        "from uuid import UUID",
        "",
        "from skm.kernel.json_types import JsonObject",
        "from skm.kernel.generated._codec import "
        "SecretRef, convert, from_settings, record_from_json, record_to_json",
    ]
    lines += [f"import {other} as _{other.replace('.', '_')}" for other in sorted(imports)]
    # Only pure kernel values are imported by generated value/document modules.
    exports = [d.name for d in declarations]
    exports += [
        snake(d.name) + suffix
        for d in declarations
        if d.kind not in ("dataclass", "settings_view")
        for suffix in ("_from_json", "_to_json")
    ]
    lines += ["", "__all__ = " + repr(sorted(exports)), ""]
    for d in model.ordered(declarations):
        lines += block(model, d, digest)
    for d in declarations:
        if d.kind == "settings_view" and d.config_chain == "work" and d.key.endswith("@scope:work"):
            host = model.declarations[d.key.removesuffix("@scope:work") + "@scope:host"]
            lines += [f"{d.name}._HOST_VIEW = {host.name}"]
    return "\n".join(lines).rstrip() + "\n"


def block(model: Model, d: Declaration, digest: str) -> list[str]:  # noqa: PLR0912
    lines: list[str] = [""]
    typ = type_text(d.type, model, d.module, d.json_mode)
    if d.kind == "enum":
        lines += [f"class {d.name}(StrEnum):"]
        if d.description:
            lines += ["    " + repr(d.description)]
        lines += [f"    {v.upper().replace('-', '_').replace('.', '_')} = {v!r}" for v in d.type.values]
    elif d.type.tag == "record":
        conditional = [(f.wire, *rule) for f in d.fields for rule in f.required_when]
        if d.json_mode:
            # Functional TypedDict preserves arbitrary wire keys and forward references.
            fields = {}
            for f in d.fields:
                ft = type_text(f.type, model, d.module, True)
                fields[f.wire] = f"ForwardRef({ft!r})" if f.required else f"NotRequired[ForwardRef({ft!r})]"
            lines += [f"{d.name} = TypedDict({d.name!r}, {{"]
            lines += [f"    {wire!r}: {text}," for wire, text in fields.items()]
            lines += ["})", f"{d.name}._JSON_MODE = True"]
        else:
            lines += ["@dataclass(frozen=True, slots=True)", f"class {d.name}:"]
            if d.description:
                lines += ["    " + repr(d.description)]
            for f in d.fields:
                ft = type_text(f.type, model, d.module)
                default = ""
                if not f.required and not f.has_default and not _admits_none(f.type):
                    # Absence is ``None`` on the object; the conversion spec stays the schema's own type.
                    ft += " | None"
                if not f.required:
                    value = () if f.default == [] else f.default
                    # Typed scalar defaults are converted after class creation when needed.
                    default = " = " + literal(value if f.has_default else None)
                # A postponed annotation is compiled back to decimal text; a quoted one keeps hex exact.
                lines += [f"    {f.name}: {repr(ft) if _wide(f.type) else ft}{default}"]
            lines += [f"    SCHEMA_URN: ClassVar[str] = {d.urn!r}", "    _FIELDS: ClassVar[tuple]"]
            if d.section:
                lines += [
                    f"    SECTION: ClassVar[str] = {d.section!r}",
                    f"    SCHEMA_DIGEST: ClassVar[str] = {'sha256:' + digest!r}",
                    "",
                    "    @classmethod",
                    "    def from_settings(cls, values: Mapping[str, Any]) -> Self:",
                    "        return from_settings(cls, values)",
                ]
                if d.config_chain:
                    lines += [f"    CONFIG_CHAIN: ClassVar[str] = {d.config_chain!r}"]
                if d.kind == "settings_view" and d.key.endswith("@scope:work"):
                    lines += ["    _HOST_VIEW: ClassVar[type]"]
            extra = f", required_when=_REQUIRED_WHEN_{d.name}" if conditional else ""
            lines += [
                "",
                "    @classmethod",
                "    def from_json(cls, data: Mapping[str, Any]) -> Self:",
                f"        return record_from_json(cls, data{extra})",
                "",
                "    def to_json(self) -> dict[str, Any]:",
                f"        return record_to_json(self{extra})",
            ]
        specs = [
            (f.wire, f.name, descriptor(f.type, model), f.required, f.default, f.has_default, f.settings_key)
            for f in d.fields
        ]
        lines += [f"{d.name}._FIELDS = ("]
        for spec in specs:
            wire = spec[0].replace("~", "~0").replace("/", "~1")
            source = json.dumps(f"{d.location}/properties/{wire}", ensure_ascii=True)
            lines += [f"    # schema field: {source}", f"    {literal(spec)},"]
        lines += [")"]
        if conditional and not d.json_mode:
            lines += [f"_REQUIRED_WHEN_{d.name} = {literal(tuple(conditional))}"]
    else:
        lines += [f"type {d.name} = {typ}"]
    lines += [
        f"_SPEC_{d.name} = {literal(descriptor(d.type, model))}",
        f"_JSON_MODE_{d.name} = {d.json_mode!r}",
    ]
    if d.kind not in ("dataclass", "settings_view") or d.type.tag != "record":
        function = snake(d.name)
        if d.type.tag == "record":
            expr = f"record_from_json({d.name}, data, json_mode={d.json_mode})"
            encode = (
                f"record_from_json({d.name}, data, json_mode=True)" if d.json_mode else "record_to_json(data)"
            )
        elif d.kind == "enum":
            expr, encode = f"{d.name}(data)", f"{d.name}(data).value"
        else:
            expr = f"convert(_SPEC_{d.name}, data, json_mode={d.json_mode})"
            encode = f"convert(_SPEC_{d.name}, data, encode=True, json_mode={d.json_mode})"
        lines += [
            "",
            f"def {function}_from_json(data: Any) -> {d.name}:",
            f"    return {expr}",
            "",
            f"def {function}_to_json(data: {d.name}) -> Any:",
            f"    return {encode}",
        ]
    return lines
