"""Recursive compatibility comparison for JSON Schema contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .schema_graph import (
    ANNOTATIONS,
    LISTS,
    MAPPINGS,
    RULES,
    SINGLE,
    Change,
    Graph,
    RefError,
)
from .schema_graph import (
    BOUNDS as _BOUNDS,
)
from .schema_graph import (
    compile_pattern as _compile,
)
from .schema_graph import (
    digits as _digits,
)
from .schema_graph import (
    dumps as _dumps,
)
from .schema_graph import (
    equal as _equal,
)


class Comparer:
    def __init__(self, old: Graph, new: Graph):
        self.old = old
        self.new = new
        self.changes: list[Change] = []
        self._visited: set[tuple[Any, ...]] = set()  # target pairs plus sibling fingerprints
        self._context = "value"

    def run(self, old_id: str, new_id: str) -> list[Change]:
        old_root, old_owner = self.old.resolve(old_id, old_id)
        new_root, new_owner = self.new.resolve(new_id, new_id)
        self._walk(old_root, old_owner, new_root, new_owner, "")
        return self.changes

    def _add(self, path: str, rule: str, message: str, breaking: bool | None = None) -> None:
        self.changes.append(Change(path, rule, RULES[rule] if breaking is None else breaking, message))

    def _walk(self, old: dict, old_base: str, new: dict, new_base: str, path: str) -> None:
        old, old_base, old_target, old_extra, old_conflicts = _expand(self.old, old, old_base)
        new, new_base, new_target, new_extra, new_conflicts = _expand(self.new, new, new_base)
        if old_target is not None or new_target is not None:
            # a target is compared once per distinct set of keywords written next to its $ref
            pair = (
                id(self.old),
                id(self.new),
                self._context,
                old_target or id(old),
                new_target or id(new),
                old_extra,
                new_extra,
            )
            if pair in self._visited:
                return
            self._visited.add(pair)
        if old is False:
            if new is not False:
                self._add(path, "schema-widened", "schema no longer forbids every value")
            return
        if new is True:
            if old is not True:
                self._add(path, "schema-widened", "schema is now unconstrained")
            return
        if new is False:
            self._add(path, "constraint-changed", "schema now forbids every value")
            return
        if old is True:
            old = {}
        for keyword, _target, _sibling in sorted(set(new_conflicts) - set(old_conflicts)):
            self._add(
                path,
                "ref-sibling-conflict",
                f"{keyword} changed in conflicting $ref target and sibling constraints",
            )
        if old_target is not None and new_target is not None and old_target[0] != new_target[0]:
            self._add(path, "ref-changed", f"$ref target moved from {old_target[0]} to {new_target[0]}")
        self._type(old, new, path)
        self._enum(old, new, path)
        self._const_pattern(old, new, path)
        self._bounds(old, new, path)
        if new.get("uniqueItems") is True and old.get("uniqueItems") is not True:
            self._add(path, "unique-added", "uniqueItems is now required")
        self._conditions(old, new, path)
        self._sensitive(old, old_base, new, new_base, path)
        self._objects(old, old_base, new, new_base, path)
        if "items" in old or "items" in new:
            self._walk(old.get("items", {}), old_base, new.get("items", {}), new_base, f"{path}/items")
        self._one_of(old, old_base, new, new_base, path)
        self._other(old, old_base, new, new_base, path, direct=not (old_target or new_target))

    def _other(self, old: dict, old_base: str, new: dict, new_base: str, path: str, *, direct: bool) -> None:
        # Draft 2020-12 constraints beyond the donor profile are conservative.
        for keyword in (
            "format",
            "multipleOf",
            "contentEncoding",
            "contentMediaType",
            "unevaluatedProperties",
            "unevaluatedItems",
            "$dynamicRef",
        ):
            if keyword in new and not _equal(old.get(keyword), new[keyword]):
                self._add(path, "constraint-changed", f"{keyword} added or changed")
        for keyword in ("anyOf", "allOf", "then", "else", "dependentSchemas", "prefixItems"):
            here = f"{path}/{keyword}"
            if not _equal(old.get(keyword), new.get(keyword)):
                if keyword == "then" and direct and _then_widened(old, new):
                    self._add(here, "schema-widened", "required property alternatives relaxed")
                else:
                    self._add(path, "constraint-changed", f"{keyword} changed; compatibility is not proven")
            elif keyword in new:
                # Unchanged ref text can hide a changed target on either side.
                before, after = old[keyword], new[keyword]
                if isinstance(after, list):
                    for index, child in enumerate(after):
                        self._walk(before[index], old_base, child, new_base, f"{here}/{index}")
                elif keyword == "dependentSchemas":
                    for name, child in after.items():
                        self._walk(before[name], old_base, child, new_base, f"{here}/{escape(name)}")
                else:
                    self._walk(before, old_base, after, new_base, here)

    def _child(self, old, old_base, new, new_base, path, context, *, reverse=False):
        """Share termination state, but distinguish polarity and applicator context."""
        child = Comparer(self.new, self.old) if reverse else Comparer(self.old, self.new)
        child._visited = self._visited
        child._context = context
        if reverse:
            child._walk(new, new_base, old, old_base, path)
        else:
            child._walk(old, old_base, new, new_base, path)
        self.changes.extend(child.changes)

    def _sensitive(self, old, old_base, new, new_base, path):
        for keyword in ("not", "propertyNames"):
            if keyword in old and keyword in new and _equal(old[keyword], new[keyword]):
                self._child(
                    old[keyword],
                    old_base,
                    new[keyword],
                    new_base,
                    f"{path}/{keyword}",
                    keyword,
                    reverse=keyword == "not",
                )
        if "contains" in new:
            if "contains" not in old:
                self._add(path, "constraint-changed", "contains constraint added")
            else:
                # Lower match counts are covariant in the child predicate; upper
                # match counts are contravariant. A finite interval needs both.
                contains = (old["contains"], old_base, new["contains"], new_base, f"{path}/contains")
                if old.get("minContains", 1) > 0 or new.get("minContains", 1) > 0:
                    self._child(*contains, "contains-min")
                if "maxContains" in old or "maxContains" in new:
                    self._child(*contains, "contains-max", reverse=True)
        self._conditional(old, old_base, new, new_base, path)

    def _conditional(self, old, old_base, new, new_base, path):
        if "if" not in old and "if" not in new:
            return
        old_then, old_else = old.get("then", True), old.get("else", True)
        new_then, new_else = new.get("then", True), new.get("else", True)
        if "if" not in old or "if" not in new:
            active_then, active_else = (old_then, old_else) if "if" in old else (new_then, new_else)
            if active_then is not True or active_else is not True:
                self._add(f"{path}/if", "constraint-changed", "conditional predicate added or removed")
            return
        # Identical branches cannot be affected by switching the predicate.
        if _equal(
            _assertions(self.old, old_then, old_base), _assertions(self.old, old_else, old_base)
        ) and _equal(_assertions(self.new, new_then, new_base), _assertions(self.new, new_else, new_base)):
            return
        before = _assertions(self.old, old["if"], old_base)
        after = _assertions(self.new, new["if"], new_base)
        if _equal(before, after):
            return
        if old_then is False and new_then is False and old_else is True and new_else is True:
            # if P then false else true is exactly not P.
            self._child(old["if"], old_base, new["if"], new_base, f"{path}/if", "if-predicate", reverse=True)
        elif old_then is True and new_then is True and old_else is False and new_else is False:
            self._child(old["if"], old_base, new["if"], new_base, f"{path}/if", "if-predicate")
        else:
            self._add(
                f"{path}/if",
                "constraint-changed",
                "predicate ref graph changed; safe then/else switching is not proven",
            )

    def _type(self, old: dict, new: dict, path: str) -> None:
        old_types, new_types = _types(old), _types(new)
        if old_types == new_types:
            return
        if new_types is None:
            self._add(path, "type-widened", "type restriction removed")
        elif old_types is None or not all(_covered(t, new_types) for t in old_types):
            self._add(path, "type-changed", f"type {_show_types(old_types)} is now {_show_types(new_types)}")
        else:
            self._add(path, "type-widened", f"type {_show_types(old_types)} is now {_show_types(new_types)}")

    def _enum(self, old: dict, new: dict, path: str) -> None:
        old_enum, new_enum = old.get("enum"), new.get("enum")
        if new_enum is None and old_enum is not None:
            self._add(path, "enum-widened", "enum removed")
        elif old_enum is None and new_enum is not None:
            self._add(path, "enum-added", "enum now restricts the values")
        elif old_enum is not None and new_enum is not None:
            dropped = [v for v in old_enum if not _contains(new_enum, v)]
            gained = [v for v in new_enum if not _contains(old_enum, v)]
            if dropped:
                self._add(path, "enum-narrowed", "enum lost " + _show(dropped))
            if gained:
                self._add(path, "enum-widened", "enum gained " + _show(gained))

    def _const_pattern(self, old: dict, new: dict, path: str) -> None:
        if "const" in new and ("const" not in old or not _equal(old["const"], new["const"])):
            self._add(path, "const-changed", f"const is now {_show(new['const'])}")
        old_pattern, new_pattern = old.get("pattern"), new.get("pattern")
        if new_pattern is not None and new_pattern != old_pattern:
            self._add(
                path, "pattern-changed", f"pattern is now {new_pattern!r}"
            )  # regex equality is not proven
        elif new_pattern is None and old_pattern is not None:
            self._add(path, "pattern-removed", "pattern removed")

    def _bounds(self, old: dict, new: dict, path: str) -> None:
        bounds = _BOUNDS
        if "contains" in old and "contains" in new:
            bounds += (("minContains", 1, "min"), ("maxContains", None, "max"))
        for keyword, default, direction in bounds:
            old_value, new_value = old.get(keyword, default), new.get(keyword, default)
            if old_value == new_value:
                continue
            grows = direction == "min"
            if new_value is not None and (old_value is None or (new_value > old_value) == grows):
                self._add(
                    path, "bound-tightened", f"{keyword} is now {_bound(new_value)} (was {_bound(old_value)})"
                )
            else:
                self._add(
                    path, "bound-relaxed", f"{keyword} is now {_bound(new_value)} (was {_bound(old_value)})"
                )

    def _conditions(self, old: dict, new: dict, path: str) -> None:
        """New ``not`` and ``dependentRequired`` constraints narrow the valid set."""
        if "not" in new and new["not"] != old.get("not"):
            self._add(path, "not-changed", "a not constraint was added or changed")
        old_deps, new_deps = old.get("dependentRequired", {}), new.get("dependentRequired", {})
        for name, needed in new_deps.items():
            gained = [other for other in needed if other not in old_deps.get(name, ())]
            if gained:
                self._add(
                    f"{path}/dependentRequired/{escape(name)}",
                    "dependent-required-added",
                    f"property {name!r} now requires {gained}",
                )

    def _objects(self, old: dict, old_base: str, new: dict, new_base: str, path: str) -> None:  # noqa: PLR0912
        old_props, new_props = old.get("properties", {}), new.get("properties", {})
        old_patterns, new_patterns = old.get("patternProperties", {}), new.get("patternProperties", {})
        closed = new.get("additionalProperties") is False
        if closed and old.get("additionalProperties") is not False:
            self._add(path, "additional-closed", "additionalProperties is now false")
        if not closed and old.get("additionalProperties") is not False:
            self._walk(
                old.get("additionalProperties", True),
                old_base,
                new.get("additionalProperties", True),
                new_base,
                f"{path}/additionalProperties",
            )
        for name in old_props:
            if name in new_props:
                continue
            here = f"{path}/properties/{escape(name)}"
            covering = [pattern for pattern in new_patterns if _compile(pattern).search(name)]
            for pattern in covering:  # the pattern's value schema now governs the old property
                self._walk(old_props[name], old_base, new_patterns[pattern], new_base, here)
            if not covering and closed:
                self._add(here, "property-removed", f"property {name!r} removed from a closed object")
            elif not covering and isinstance(new.get("additionalProperties"), dict):
                self._walk(old_props[name], old_base, new.get("additionalProperties", True), new_base, here)
        for name, child in new_props.items():
            here = f"{path}/properties/{escape(name)}"
            if name in old_props:
                self._walk(old_props[name], old_base, child, new_base, here)
                continue
            earlier = [pattern for pattern in old_patterns if _compile(pattern).search(name)]
            for pattern in earlier:  # the name was already governed by an old pattern
                self._walk(old_patterns[pattern], old_base, child, new_base, here)
            if not earlier:
                self._add(here, "property-added", f"property {name!r} added")
                if old.get("additionalProperties") is not False:
                    self._walk(old.get("additionalProperties", True), old_base, child, new_base, here)
        old_required, new_required = old.get("required", ()), new.get("required", ())
        for name in new_required:
            if name not in old_required:
                self._add(path, "required-added", f"property {name!r} is now required")
        for name in old_required:
            if name not in new_required:
                self._add(path, "required-removed", f"property {name!r} is no longer required")
        for pattern in old_patterns:
            if pattern not in new_patterns:
                self._add(
                    f"{path}/patternProperties/{escape(pattern)}",
                    "pattern-property-removed",
                    f"patternProperties key {pattern!r} removed",
                )
        for pattern, child in new_patterns.items():
            here = f"{path}/patternProperties/{escape(pattern)}"
            if pattern in old_patterns:
                self._walk(old_patterns[pattern], old_base, child, new_base, here)
                continue
            meets = _compile(pattern)
            safe = (
                old.get("additionalProperties") is False
                and not old_patterns
                and not any(meets.search(name) and name in new_props for name in old_props)
            )
            self._add(
                here,
                "pattern-property-added",
                f"patternProperties key {pattern!r} added"
                + ("" if safe else " (it can apply to names the old schema accepted)"),
                breaking=not safe,
            )
        if "propertyNames" in new and (
            "propertyNames" not in old or not _equal(old["propertyNames"], new["propertyNames"])
        ):
            self._add(path, "property-names-changed", "propertyNames is now " + _show(new["propertyNames"]))

    def _one_of(self, old: dict, old_base: str, new: dict, new_base: str, path: str) -> None:
        old_branches, new_branches = old.get("oneOf"), new.get("oneOf")
        if old_branches is None and new_branches is None:
            return
        if old_branches is None or new_branches is None or len(old_branches) != len(new_branches):
            self._add(
                f"{path}/oneOf",
                "oneof-changed",
                f"oneOf has {len(old_branches or ())} branches, now {len(new_branches or ())}",
            )
            return
        outer = self.changes
        found: dict[int, list[Change]] = {}
        for index, (before, after) in enumerate(zip(old_branches, new_branches, strict=False)):
            self.changes = []
            self._walk(before, old_base, after, new_base, f"{path}/oneOf/{index}")
            inner, self.changes = self.changes, outer
            if not inner and not _equal(
                _assertions(self.old, before, old_base), _assertions(self.new, after, new_base)
            ):
                # Removals such as const/not/uniqueItems are harmless in isolation,
                # but can introduce oneOf overlap, including through unchanged refs.
                inner = [
                    Change(f"{path}/oneOf/{index}", "schema-widened", False, "branch constraints relaxed")
                ]
            if inner:
                found[index] = inner
        # Conflicting ref siblings provide no proof of branch disjointness.
        expanded = [
            (body, owner) if not conflicts else None
            for body, owner, _, _, conflicts in (
                _expand(self.new, branch, new_base) for branch in new_branches
            )
        ]
        for index, inner in found.items():
            # A branch that only widened keeps every document it accepted; a document of another branch cannot
            # start matching it too when the branches provably share no document.
            if not any(change.breaking for change in inner) and all(
                _disjoint(self.new, expanded[index], expanded[other])
                for other in range(len(new_branches))
                if other != index
            ):
                self.changes.extend(inner)
                continue
            rules = ", ".join(sorted({change.rule for change in inner}))
            self._add(f"{path}/oneOf/{index}", "oneof-changed", f"oneOf branch {index} changed ({rules})")


_ANNOTATIONS = ANNOTATIONS | {"$id", "$schema", "$defs", "$anchor"}
_LOWER_BOUNDS = frozenset({"minLength", "minItems", "minimum"})
_UPPER_BOUNDS = frozenset({"maximum", "maxLength", "maxItems"})


def _then_widened(old: dict, new: dict) -> bool:
    predicate = old.get("if")
    if predicate is None or not _equal(predicate, new.get("if")) or not _reference_free(predicate):
        return False
    before = _required_alternatives(old.get("then"))
    after = _required_alternatives(new.get("then"))
    # Every old minimum set of required keys must contain at least one new minimum set.
    return bool(before) and all(any(option <= required for option in after) for required in before)


def _required_alternatives(branch: Any) -> list[set[str]]:
    if isinstance(branch, dict) and branch.keys() == {"required"}:
        return [set(branch["required"])]
    if isinstance(branch, dict) and branch.keys() == {"anyOf"}:
        options = branch["anyOf"]
        if all(isinstance(option, dict) and option.keys() == {"required"} for option in options):
            return [set(option["required"]) for option in options]
    return []


def _reference_free(node: Any) -> bool:
    if isinstance(node, dict):
        return not {"$ref", "$dynamicRef"}.intersection(node) and all(map(_reference_free, node.values()))
    return not isinstance(node, list) or all(map(_reference_free, node))


def _assertions(graph: Graph, node: Any, base: str, seen: frozenset[str] = frozenset()) -> Any:
    """Reachable assertion shape, preserving recursive edges and ignoring annotations."""
    if not isinstance(node, dict):
        return node
    result = {}
    for key, value in node.items():
        if _is_annotation(key):
            continue
        if key == "$ref":
            if value in seen:
                result[key] = value
            else:
                target, owner = graph.resolve(value, base)
                result[key] = _assertions(graph, target, owner, seen | {value})
        elif key in MAPPINGS:
            result[key] = {name: _assertions(graph, child, base, seen) for name, child in value.items()}
        elif key in SINGLE:
            result[key] = _assertions(graph, value, base, seen)
        elif key in LISTS:
            result[key] = [_assertions(graph, child, base, seen) for child in value]
        else:
            result[key] = value
    return result


def _disjoint(registry: Graph, first: tuple[dict, str] | None, second: tuple[dict, str] | None) -> bool:
    """Prove that two expanded schemas accept disjoint sets of documents.

    Conflicting ref siblings give no proof. Types, forbidden required properties,
    and required discriminator values can establish disjointness.
    """
    if first is None or second is None:
        return False
    (a, a_base), (b, b_base) = first, second
    if isinstance(a, bool) or isinstance(b, bool):
        return a is False or b is False
    if "type" in a and "type" in b and not _merge_types(a["type"], b["type"]):
        return True
    for this, other in ((a, b), (b, a)):
        if _types(this) == {"object"} and any(_forbids(other, name) for name in this.get("required", ())):
            return True
        # A required phase document cannot overlap the context pack's maxProperties: 0 sentinel.
        # Count distinct names: duplicate required entries must not manufacture a proof of disjointness.
        if (
            _types(this) == {"object"}
            and isinstance(other.get("maxProperties"), int)
            and len(set(this.get("required", ()))) > other["maxProperties"]
        ):
            return True
    if _types(a) != {"object"} or _types(b) != {"object"}:
        return False
    for name in set(a.get("required", ())) & set(b.get("required", ())):
        if name not in a.get("properties", {}) or name not in b.get("properties", {}):
            continue
        a_values = _values(_expand(registry, a["properties"][name], a_base)[0])
        b_values = _values(_expand(registry, b["properties"][name], b_base)[0])
        if (
            a_values is not None
            and b_values is not None
            and not any(_contains(b_values, v) for v in a_values)
        ):
            return True
    return False


def _forbids(node: dict, name: str) -> bool:
    """Whether a closed object forbids ``name`` without any covering pattern."""
    return (
        node.get("additionalProperties") is False
        and name not in node.get("properties", {})
        and not any(_compile(pattern).search(name) for pattern in node.get("patternProperties", {}))
    )


def _values(node: dict) -> list[Any] | None:
    """The only values ``node`` allows (``const``, else ``enum``), or ``None`` when it does not list them."""
    if isinstance(node, bool):
        return None if node else []
    if "const" in node:
        return [node["const"]]
    return list(node["enum"]) if isinstance(node.get("enum"), list) else None


def _is_annotation(keyword: str) -> bool:
    return keyword in _ANNOTATIONS or keyword.startswith("x-")


def _merge_types(first: Any, second: Any) -> list[str]:
    a = {first} if isinstance(first, str) else set(first)
    b = {second} if isinstance(second, str) else set(second)
    return sorted({t for t in a if _covered(t, b)} | {t for t in b if _covered(t, a)})


def _expand(
    registry: Graph, node: dict, base: str, seen: set[tuple[str, str]] | None = None
) -> tuple[Any, str, tuple[str, str] | None, str, list[tuple[str, str, str]]]:
    """Resolve ``$ref`` chains: the merged body, the owner of its children, the final target ``(owner, ref)``,
    a fingerprint of the keywords written next to the references and the keywords that could not be merged.

    A validator applies the target and the keywords next to the ``$ref`` together, so the merge keeps the
    stricter bound, joins ``required``, intersects ``type`` and ``enum``; any other keyword set on both sides
    with different values is returned as a conflict.
    """
    if isinstance(node, bool):
        return node, base, None, "", []
    ref = node.get("$ref")
    if ref is None:
        return node, base, None, "", []
    target, owner = registry.resolve(ref, base)
    key = (owner, ref.partition("#")[2])
    seen = set() if seen is None else seen
    if key in seen:
        raise RefError(f"$ref {ref!r} refers to itself")
    seen.add(key)
    body, owner, final, extra, conflicts = _expand(registry, target, owner, seen)
    if body is False:
        return False, owner, final or key, extra, conflicts
    if body is True:
        body = {}
    merged = dict(body)
    siblings = {k: v for k, v in node.items() if k != "$ref"}
    for keyword, value in siblings.items():
        if keyword not in body or _is_annotation(keyword) or _equal(body[keyword], value):
            merged[keyword] = value
        elif keyword in _LOWER_BOUNDS:
            merged[keyword] = max(body[keyword], value)
        elif keyword in _UPPER_BOUNDS:
            merged[keyword] = min(body[keyword], value)
        elif keyword == "required":
            merged[keyword] = list(dict.fromkeys(list(body[keyword]) + list(value)))
        elif keyword == "uniqueItems":
            merged[keyword] = bool(body[keyword] or value)
        elif keyword == "type" and _merge_types(body[keyword], value):
            merged[keyword] = _merge_types(body[keyword], value)
        elif keyword == "enum":
            merged[keyword] = [item for item in body[keyword] if _contains(value, item)]
        else:  # not mergeable (or an empty type intersection): remember both values, the sibling is kept
            conflicts = [*conflicts, (keyword, _show(body[keyword]), _show(value))]
            merged[keyword] = value
    fingerprint = extra + _dumps(
        {k: v for k, v in siblings.items() if not _is_annotation(k)}, sort_keys=True, default=str
    )
    return merged, owner, final or key, fingerprint, conflicts


def _types(node: dict) -> set[str] | None:
    value = node.get("type")
    if value is None:
        return None
    return {value} if isinstance(value, str) else set(value)


def _covered(name: str, types: set[str]) -> bool:
    return name in types or (name == "integer" and "number" in types)


def _show_types(types: set[str] | None) -> str:
    return "any" if types is None else "/".join(sorted(types))


def _contains(values: Sequence[Any], value: Any) -> bool:
    return any(_equal(value, other) for other in values)


def _show(value: Any) -> str:
    return _dumps(value, ensure_ascii=False, sort_keys=True)


def _bound(value: Any) -> str:
    if value is None:
        return "unbounded"
    return _digits(value) if isinstance(value, int) and not isinstance(value, bool) else str(value)


def escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")
