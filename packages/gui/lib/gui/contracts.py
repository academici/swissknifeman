"""Contracts of the gui module (``schemas/<contract>/v<N>/``), loaded through the aicore validator.

``load`` returns the registry of one contract; references to ``urn:swissknifeman:aicore:*`` resolve in the
foundation. ``validate`` reports the issues of a document. For a document with several kinds (a root ``oneOf``
whose branches differ by a ``const`` field such as ``view`` or ``kind``) it validates against the branch the
document names, so the issues say which field to change instead of only ``one_of``; pass and fail stay the same
as validating the whole ``oneOf``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aicore.util import schema

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
URN_PREFIX = "urn:swissknifeman:gui:"
VERSION = "v1"

# Root keywords that do not constrain a document: with only these next to oneOf the branch alone decides.
_PASSIVE_ROOT = frozenset({"$schema", "$id", "title", "description", "$defs", "oneOf"})


def contract_dir(contract: str, version: str = VERSION) -> Path:
    return SCHEMAS / contract / version


def urn(contract: str, version: str = VERSION) -> str:
    return f"{URN_PREFIX}{contract}:{version}"


def load(contract: str, version: str = VERSION) -> Tuple[schema.Registry, str]:
    """Registry and kind of one gui contract; ``SchemaProfileError`` when it is missing or leaves the profile."""
    directory = contract_dir(contract, version)
    if not directory.is_dir():
        raise schema.SchemaProfileError(f"unknown gui contract {contract}/{version}")
    return schema.load_contract(directory, urn_prefix=URN_PREFIX)


def validate(document: Any, contract: str, version: str = VERSION) -> List[schema.ValidationIssue]:
    """Every issue of ``document`` against the gui contract; an empty list means valid."""
    registry, kind = load(contract, version)
    root, root_id = registry.for_kind(kind)
    branch = _named_branch(registry, root, root_id, document)
    if branch is None:
        return schema.validate(document, kind, registry)
    node, owner = branch
    return schema.validate_node(registry, node, owner, document)


def discriminator(contract: str, version: str = VERSION) -> Optional[Tuple[str, Dict[str, int]]]:
    """The const field that tells the kinds of a several-kind contract apart and its value per branch index."""
    registry, kind = load(contract, version)
    root, root_id = registry.for_kind(kind)
    found = _discriminator(registry, root, root_id)
    return None if found is None else (found[0], {value: index for index, (value, _) in enumerate(found[1])})


def _named_branch(registry: schema.Registry, root: dict, root_id: str,
                  document: Any) -> Optional[Tuple[dict, str]]:
    if not isinstance(document, dict):
        return None
    found = _discriminator(registry, root, root_id)
    if found is None:
        return None
    name, branches = found
    matches = [branch for value, branch in branches if document.get(name) == value]
    return matches[0] if len(matches) == 1 else None


def _discriminator(registry: schema.Registry, root: dict,
                   root_id: str) -> Optional[Tuple[str, List[Tuple[Any, Tuple[dict, str]]]]]:
    if not isinstance(root.get("oneOf"), list) or set(root) - _PASSIVE_ROOT:
        return None
    branches: List[Tuple[dict, str]] = []
    for branch in root["oneOf"]:
        if set(branch) - {"$ref", "description"} or "$ref" not in branch:
            return None
        branches.append(registry.resolve(branch["$ref"], root_id))
    consts = [{name: prop["const"] for name, prop in (node.get("properties") or {}).items()
               if isinstance(prop, dict) and isinstance(prop.get("const"), str)} for node, _ in branches]
    for name in sorted(set.intersection(*(set(c) for c in consts))):
        values = [c[name] for c in consts]
        if len(set(values)) == len(values) and all(name in (node.get("required") or ()) for node, _ in branches):
            return name, list(zip(values, branches))
    return None


# --- bundle: one self-contained schema per contract (for type generators) ------------------------------------

_SCHEMA_MAPS = ("properties", "patternProperties", "$defs")
_SCHEMA_LISTS = ("oneOf", "anyOf", "allOf", "prefixItems")
_SCHEMA_NODES = ("items", "not", "contains", "if", "then", "else", "additionalProperties", "propertyNames")


def _short(owner: str) -> str:
    """``urn:swissknifeman:aicore:common:v1`` → ``aicore_common``."""
    parts = owner.split(":")[2:]
    if parts and parts[-1].startswith("v") and parts[-1][1:].isdigit():
        parts = parts[:-1]
    return "_".join(part.replace("-", "_") for part in parts)


def bundle(contract: str, version: str = VERSION) -> Dict[str, Any]:
    """The contract as one JSON Schema without external references: every ``$ref`` (to this contract, another gui
    contract or the foundation) points at ``#/$defs/<key>``; keys of other schemas are prefixed with their short id.
    The result is deterministic (sorted ``$defs``), so generated types can be compared with the ones in git."""
    registry, kind = load(contract, version)
    root, root_id = registry.for_kind(kind)
    defs: Dict[str, Any] = {}
    pending: set = set()

    def key_of(ref: str, base: str) -> str:
        document, _, fragment = ref.partition("#")
        owner = document or base
        name = fragment[len("/$defs/"):] if fragment else ""
        if owner == root_id:
            return name or _short(owner)
        return f"{_short(owner)}_{name}" if name else _short(owner)

    def rewrite(node: Any, base: str) -> Any:
        if isinstance(node, list):
            return [rewrite(item, base) for item in node]
        if not isinstance(node, dict):
            return node
        out: Dict[str, Any] = {}
        for name, value in node.items():
            if name == "$ref":
                key = key_of(value, base)
                if key not in defs and key not in pending:
                    pending.add(key)
                    target, owner = registry.resolve(value, base)
                    resolved = rewrite({k: v for k, v in target.items() if k not in ("$defs", "$id", "$schema")},
                                       owner)
                    defs[key] = resolved
                    pending.discard(key)
                out["$ref"] = f"#/$defs/{key}"
            elif name in _SCHEMA_MAPS and isinstance(value, dict):
                if name == "$defs":
                    continue  # only referenced definitions are kept, under their bundle keys
                out[name] = {child: rewrite(schema, base) for child, schema in value.items()}
            elif name in _SCHEMA_LISTS and isinstance(value, list):
                out[name] = [rewrite(item, base) for item in value]
            elif name in _SCHEMA_NODES and isinstance(value, dict):
                out[name] = rewrite(value, base)
            elif name in ("$id", "$schema"):
                continue
            else:
                out[name] = value
        return out

    document = rewrite(root, root_id)
    document = {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": contract, **document}
    if defs:
        document["$defs"] = {key: defs[key] for key in sorted(defs)}
    return document
