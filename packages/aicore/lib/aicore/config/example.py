"""Generate ``config.example.toml`` from a module schema.

The text is deterministic: tables are active headers, leaves are commented lines in schema order
(leaves of a table first, then its sub-tables), so a copy of the example is a valid, empty layer.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Tuple

from . import ConfigError, toml_edit
from .model import Leaf, MapSpec, ModuleSchema, load_module_schema
from .units import UnitInfo

Key = Tuple[str, ...]

_SPACE = re.compile(r"\s+")
_EXAMPLE_NAMES = ("example", "module:example")


def _sentence(text: str) -> str:
    text = _SPACE.sub(" ", text).strip()
    return text if text[-1:] in ".!?" else text + "."


def _bounds(node: Dict[str, Any]) -> str:
    parts = []
    if "minimum" in node:
        parts.append(f">= {node['minimum']}")
    if "maximum" in node:
        parts.append(f"<= {node['maximum']}")
    return " and ".join(parts)


def _kind(leaf: Leaf) -> str:
    node = leaf.node
    if leaf.secret:
        return "Secret reference of the form <scheme>://<name>."
    if "enum" in node:
        return "One of: " + ", ".join(toml_edit.render_value(item) for item in node["enum"]) + "."
    if leaf.type == "array":
        item = (leaf.item_node or {}).get("type", "value")
        bounds = _bounds(leaf.item_node or {})
        return f"Array of {item}s" + (f" {bounds}" if bounds else "") + "."
    word = leaf.type.capitalize()
    bounds = _bounds(node)
    return f"{word} {bounds}." if bounds else f"{word}."


def _leaf_lines(leaf: Leaf) -> List[str]:
    name = leaf.key[-1]
    lines = [f"# {_sentence(leaf.description)} {_kind(leaf)}"]
    if leaf.layers is not None:
        lines.append("# Allowed in layers: " + ", ".join(leaf.layers) + ".")
    if leaf.has_default:
        shown = toml_edit.render_value(leaf.default)
    elif leaf.secret:
        shown = '"env://NAME"'
    else:
        shown = f"<{leaf.type}>"
    lines.append(f"# {toml_edit.render_key(name)} = {shown}")
    return lines


def _header(schema: ModuleSchema, key: Key) -> str:
    return ".".join([schema.module_id] + [toml_edit.render_key(part) for part in key])


def _example_name(spec: MapSpec, source: str) -> str:
    """The entry name shown in the example: the first of ``example``, ``module:example`` the pattern accepts."""
    for name in _EXAMPLE_NAMES:
        if spec.matches(name):
            return name
    raise ConfigError("CONFIG_SCHEMA_INVALID", f"cannot render an example key: the pattern {spec.pattern!r} "
                      f"accepts neither {' nor '.join(repr(n) for n in _EXAMPLE_NAMES)}",
                      file=source, key=".".join(spec.key))


def _map_block(schema: ModuleSchema, spec: MapSpec) -> List[str]:
    """An empty table for the map, then a commented sample entry (its leaves with their defaults)."""
    name = _example_name(spec, schema.source)
    block = [f"[{_header(schema, spec.key)}]", f"# {_sentence(spec.description)}"]
    if spec.value_leaf is not None:
        template = spec.value_leaf
        lines = _leaf_lines(replace(template, key=spec.key + (name,)))
        block.extend(lines[:-1])  # the sample line below is written with the entry name as the key
        shown = toml_edit.render_value(template.default) if template.has_default else "[]"
        block.append(f"# {toml_edit.render_key(name)} = {shown}")
        return block
    block.append(f"# [{_header(schema, spec.key + (name,))}]")
    for template in (spec.value_table or {}).values():
        block.append("")
        block.extend(_leaf_lines(template))
    return block


def _tables(schema: ModuleSchema, node: Dict[str, Any], key: Key, out: List[List[str]]) -> None:
    block = [f"[{_header(schema, key)}]"]
    children: List[Tuple[Key, Dict[str, Any]]] = []
    for name, child in node.get("properties", {}).items():
        child_key = key + (name,)
        leaf = schema.leaves.get(child_key)
        if leaf is not None:
            if len(block) > 1:
                block.append("")
            block.extend(_leaf_lines(leaf))
        else:
            children.append((child_key, child))
    out.append(block)
    for child_key, child in children:
        if child_key in schema.maps:
            out.append(_map_block(schema, schema.maps[child_key]))
        else:
            _tables(schema, child, child_key, out)


def render_sections(schema: ModuleSchema) -> str:
    """The table part of the example (no ``schema_version`` line, no header comment), ending with a newline."""
    blocks: List[List[str]] = []
    _tables(schema, schema._root, (), blocks)  # noqa: SLF001  (same package)
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


def render(schema: ModuleSchema, source: str = "configs/config.schema.json") -> str:
    """The full ``config.example.toml`` text of a module."""
    head = (f"# {schema.module_id} configuration, generated from {source}; do not edit by hand.\n"
            "# Copy into ~/.config/swissknifeman/config.toml or <project>/.swissknifeman/config.toml\n"
            "# (swissknifeman config init does it) and uncomment the keys you change.\n")
    return head + "schema_version = 1\n\n" + render_sections(schema)


def render_unit(info: UnitInfo) -> str:
    """The example of a discovered module (loads and checks its schema)."""
    return render(load_module_schema(info.schema_path, info.id), info.schema_rel)
