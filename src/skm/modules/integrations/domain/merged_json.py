"""Pure codec for owned key paths and tagged hook lists in JSON documents (integrations §4.6)."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

__all__ = [
    "HOOK_COMMAND_PREFIX",
    "OwnedKeyPath",
    "dumps_merged_json",
    "dumps_merged_json_bytes",
    "ensure_mapping",
    "extract_owned",
    "extract_owned_json",
    "has_jsonc_comments",
    "is_tagged_item",
    "lookup_owned_path",
    "merge_owned",
    "merge_owned_json",
    "parse_json_document",
]

HOOK_COMMAND_PREFIX: Final[str] = "skm-hook "


@dataclass(frozen=True, slots=True)
class OwnedKeyPath:
    path: tuple[str, ...]
    mode: Literal["replace", "list_union_tagged"]


def _reject_json_constant(token: str) -> Any:
    raise ValueError(f"non-standard JSON constant {token!r}")


def has_jsonc_comments(raw_json: str) -> bool:
    """Return True if ``raw_json`` contains ``//`` or ``/*`` comments outside quoted strings."""
    in_string = False
    escaped = False
    length = len(raw_json)
    idx = 0
    while idx < length:
        ch = raw_json[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            idx += 1
            continue
        if ch == '"':
            in_string = True
            idx += 1
            continue
        if ch == "/" and idx + 1 < length and raw_json[idx + 1] in ("/", "*"):
            return True
        idx += 1
    return False


def parse_json_document(raw: str | bytes) -> dict[str, Any]:
    """Parse strict top-level JSON object; reject JSONC comments, invalid UTF-8, or non-object roots."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID") from exc
    else:
        text = raw

    if has_jsonc_comments(text):
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")

    try:
        parsed: Any = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID") from exc

    if not isinstance(parsed, dict):
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    return cast("dict[str, Any]", parsed)


def dumps_merged_json(value: Any) -> str:
    """Render JSON with two-space indentation, UTF-8 characters preserved, and trailing newline."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def dumps_merged_json_bytes(value: Any) -> bytes:
    """Render UTF-8 bytes of ``dumps_merged_json(value)``."""
    return dumps_merged_json(value).encode("utf-8")


def is_tagged_item(item: Any) -> bool:
    """Return True if ``item`` represents an SKM-owned hook entry (``skm-hook `` command prefix)."""
    if not isinstance(item, Mapping):
        return False
    mapping_item = cast("Mapping[str, Any]", item)
    direct_cmd = mapping_item.get("command")
    if isinstance(direct_cmd, str) and direct_cmd.startswith(HOOK_COMMAND_PREFIX):
        return True
    nested_hooks = mapping_item.get("hooks")
    if isinstance(nested_hooks, Sequence) and not isinstance(nested_hooks, (str, bytes)):
        for hook in cast("Sequence[Any]", nested_hooks):
            if isinstance(hook, Mapping):
                cmd = cast("Mapping[str, Any]", hook).get("command")
                if isinstance(cmd, str) and cmd.startswith(HOOK_COMMAND_PREFIX):
                    return True
    return False


def _deep_mutable_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        mapping_val = cast("Mapping[Any, Any]", value)
        return {str(k): _deep_mutable_copy(v) for k, v in mapping_val.items()}
    if isinstance(value, list):
        return [_deep_mutable_copy(v) for v in cast("list[Any]", value)]
    return copy.deepcopy(value)


def lookup_owned_path(
    document: Mapping[str, Any], path: tuple[str, ...], *, strict_containers: bool = True
) -> tuple[bool, Any]:
    if not path:
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    current_map: Mapping[str, Any] = document
    for segment in path[:-1]:
        if segment not in current_map:
            return False, None
        next_val: Any = current_map[segment]
        if not isinstance(next_val, Mapping):
            if strict_containers:
                raise ValueError("INTEGRATION_BOUNDARY_INVALID")
            return False, None
        current_map = cast("Mapping[str, Any]", next_val)
    leaf = path[-1]
    if leaf not in current_map:
        return False, None
    return True, current_map[leaf]


def _set_nested(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = target
    for segment in path[:-1]:
        if segment not in current:
            current[segment] = {}
        elif not isinstance(current[segment], dict):
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        current = cast("dict[str, Any]", current[segment])
    current[path[-1]] = value


def _delete_and_prune(target: dict[str, Any], path: tuple[str, ...]) -> None:
    ancestors: list[tuple[dict[str, Any], str]] = []
    current = target
    for segment in path[:-1]:
        if segment not in current:
            return
        next_obj: Any = current[segment]
        if not isinstance(next_obj, dict):
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        ancestors.append((current, segment))
        current = cast("dict[str, Any]", next_obj)
    leaf = path[-1]
    if leaf not in current:
        return
    del current[leaf]
    for parent, key in reversed(ancestors):
        child: Any = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]
        else:
            break


def ensure_mapping(obj: object) -> None:
    """Validate that ``obj`` is a ``Mapping``, else raise ``INTEGRATION_BOUNDARY_INVALID``."""
    if not isinstance(obj, Mapping):
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")


def extract_owned(document: Mapping[str, Any], owned: tuple[OwnedKeyPath, ...]) -> dict[str, Any]:
    """Extract only the SKM-owned subset of ``document`` declared by ``owned``."""
    ensure_mapping(document)
    extracted: dict[str, Any] = {}
    for spec in owned:
        if not spec.path:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        found, value = lookup_owned_path(document, spec.path, strict_containers=True)
        if not found:
            continue
        if spec.mode == "replace":
            _set_nested(extracted, spec.path, _deep_mutable_copy(value))
        elif spec.mode == "list_union_tagged":
            if not isinstance(value, list):
                raise ValueError("INTEGRATION_BOUNDARY_INVALID")
            tagged = [_deep_mutable_copy(item) for item in cast("list[Any]", value) if is_tagged_item(item)]
            if tagged:
                _set_nested(extracted, spec.path, tagged)
        else:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    return extracted


def _merge_list_union_tagged(
    merged: dict[str, Any],
    path: tuple[str, ...],
    *,
    has_managed: bool,
    managed_val: Any,
) -> None:
    new_tagged: list[Any] = []
    if has_managed:
        if not isinstance(managed_val, Sequence) or isinstance(managed_val, (str, bytes)):
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        for item in cast("Sequence[Any]", managed_val):
            if not is_tagged_item(item):
                raise ValueError("INTEGRATION_BOUNDARY_INVALID")
            new_tagged.append(_deep_mutable_copy(item))

    has_existing, existing_val = lookup_owned_path(merged, path, strict_containers=True)
    if not has_existing:
        if new_tagged:
            _set_nested(merged, path, new_tagged)
        return

    if not isinstance(existing_val, list):
        raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    existing_list = cast("list[Any]", existing_val)
    foreign = [_deep_mutable_copy(item) for item in existing_list if not is_tagged_item(item)]
    had_tagged = len(foreign) != len(existing_list)
    combined = foreign + new_tagged
    if combined or not had_tagged:
        _set_nested(merged, path, combined)
    else:
        _delete_and_prune(merged, path)


def merge_owned(
    document: Mapping[str, Any],
    managed: Mapping[str, Any],
    owned: tuple[OwnedKeyPath, ...],
) -> dict[str, Any]:
    """Merge ``managed`` values into ``document`` at ``owned`` paths, preserving foreign keys and order."""
    ensure_mapping(document)
    ensure_mapping(managed)

    merged: dict[str, Any] = _deep_mutable_copy(document)
    for spec in owned:
        if not spec.path:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
        has_managed, managed_val = lookup_owned_path(managed, spec.path, strict_containers=True)
        if spec.mode == "replace":
            lookup_owned_path(merged, spec.path, strict_containers=True)
            if has_managed:
                _set_nested(merged, spec.path, _deep_mutable_copy(managed_val))
            else:
                _delete_and_prune(merged, spec.path)
        elif spec.mode == "list_union_tagged":
            _merge_list_union_tagged(merged, spec.path, has_managed=has_managed, managed_val=managed_val)
        else:
            raise ValueError("INTEGRATION_BOUNDARY_INVALID")
    return merged


def extract_owned_json(raw: str | bytes, owned: tuple[OwnedKeyPath, ...]) -> dict[str, Any]:
    """Parse strict JSON text/bytes and extract ``owned`` paths."""
    return extract_owned(parse_json_document(raw), owned)


def merge_owned_json(
    raw: str | bytes,
    managed: Mapping[str, Any],
    owned: tuple[OwnedKeyPath, ...],
) -> str:
    """Parse strict JSON text/bytes, merge ``owned`` paths, and render formatted JSON."""
    doc = parse_json_document(raw)
    return dumps_merged_json(merge_owned(doc, managed, owned))
