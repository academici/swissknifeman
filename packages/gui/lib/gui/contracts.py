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
