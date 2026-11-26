"""Secret handles and explicitly composed resolvers (settings §B.9).

Configuration keeps references. Only a consumer at the adapter/bootstrap boundary resolves one;
the revealed value is registered with its redactor before the handle leaves that boundary.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, SupportsIndex, cast, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.kernel.generated._codec import SecretRef
from skm.kernel.json_types import JsonValue

if TYPE_CHECKING:
    from skm.platform.schema.registry import SchemaRegistry

__all__ = ["SecretRef", "SecretResolver", "SecretResolvers", "SecretValue", "mask_secret_refs"]

_MASK = "<redacted>"
_SECRET_REF_URN = "urn:skm:config:secret-ref:v1"
_REFERENCES = ("$ref", "$dynamicRef")
# Draft 2020-12 in-place applicators whose successful branches mark members evaluated for ``unevaluated*``.
_IN_PLACE = (*_REFERENCES, "allOf", "anyOf", "oneOf", "if", "dependentSchemas")
# Schema visits of one ``mask_secret_refs`` call. Branching references can expand exponentially without a
# cycle (a chain of ``anyOf`` pairs) and the depth bound limits only the length of a path, not their number.
_VISITS = 100_000
# Separately bound the literal data inspected for metaschema checks. Applicator children are checked
# only when reached, so neither an unused definition nor repeated references cause an eager subtree scan.
_SCHEMA_VISITS = 100_000
_SCHEMA_MAPS = ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas")
_SCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_MEMBER_SCHEMAS = ("additionalProperties", "unevaluatedProperties", "items", "unevaluatedItems", "contains")

_SCHEMA_SINGLES = (*_MEMBER_SCHEMAS, "if", "then", "else", "not")

# (id(target), id(its base resource), dynamic scope oldest first without repeats, annotations_only)
type _Context = tuple[int, int | None, tuple[str, ...], bool]
# Subschemas that apply to one member, each with the ``annotations_only`` of its walk.
type _Declarations = list[tuple[Any, bool]]


class SecretValue:
    """A non-serializable handle. Plaintext is available only through explicit ``reveal``."""

    __slots__ = ("__ref", "__value")

    def __init__(self, ref: SecretRef, value: str) -> None:
        if type(ref) is not SecretRef or type(value) is not str:
            raise TypeError("a secret requires a SecretRef and a string")
        self.__ref = ref
        self.__value = value

    def reveal(self) -> str:
        return self.__value

    @override
    def __repr__(self) -> str:
        return f"<secret {self.__ref}>"

    @override
    def __reduce__(self) -> Any:
        raise TypeError("secret values cannot be serialized")

    @override
    def __reduce_ex__(self, _protocol: SupportsIndex) -> Any:
        raise TypeError("secret values cannot be serialized")

    @override
    def __getstate__(self) -> Any:
        raise TypeError("secret values cannot be serialized")


class SecretResolver(Protocol):
    @property
    def scheme(self) -> str: ...

    def resolve(self, ref: SecretRef) -> str: ...


def _unavailable(ref: SecretRef) -> BackendUnavailable:
    return BackendUnavailable(
        ErrorCode.BACKEND_UNAVAILABLE, "Secret backend unavailable", details={"ref": str(ref)}
    )


@dataclass(frozen=True, slots=True, init=False)
class SecretResolvers:
    """Immutable dispatch snapshot: duplicates fail, missing backends never fall back.

    Capture bound methods as well as scheme names, so later registry inputs or a resolver's scheme
    attribute cannot replace an admitted backend. Backend exceptions are untrusted secret-bearing data.
    """

    _resolvers: Mapping[str, Callable[[SecretRef], str]] = field(repr=False)
    _on_reveal: Callable[[str], None] = field(repr=False)

    def __init__(self, resolvers: Iterable[SecretResolver], *, on_reveal: Callable[[str], None]) -> None:
        admitted: dict[str, Callable[[SecretRef], str]] = {}
        for resolver in resolvers:
            scheme = resolver.scheme
            if scheme not in ("env", "file", "keyring") or scheme in admitted:
                raise ValueError("invalid or duplicate secret resolver scheme")
            admitted[scheme] = resolver.resolve
        if not callable(on_reveal):
            raise TypeError("on_reveal must be callable")
        object.__setattr__(self, "_resolvers", MappingProxyType(admitted))
        object.__setattr__(self, "_on_reveal", on_reveal)

    def resolve(self, ref: SecretRef | str) -> SecretValue:
        if type(ref) is str:
            ref = SecretRef.parse(ref)
        if type(ref) is not SecretRef:
            raise TypeError("secret resolution requires a SecretRef or reference string")
        backend = self._resolvers.get(ref.scheme)
        if backend is None:
            raise _unavailable(ref)
        failure: Exception | None = None
        try:
            value = backend(ref)
        except ValidationFailed as error:
            # Reconstruct documented diagnostics; a backend can attach plaintext to its exception.
            reason = error.details.get("reason")
            if error.code == ErrorCode.CONFIG_INVALID and reason in (
                "secret_unresolved",
                "secret_file_permissions",
                "secret_ref_invalid",
            ):
                failure = ValidationFailed(
                    ErrorCode.CONFIG_INVALID,
                    "Secret reference could not be resolved",
                    details={"ref": str(ref), "reason": reason},
                )
        except CapabilityUnavailable as error:
            if ref.scheme == "keyring" and error.code == ErrorCode.CAPABILITY_UNAVAILABLE:
                failure = CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Keyring unavailable")
        except PreconditionFailed as error:
            if ref.scheme == "keyring" and error.code == ErrorCode.SECRET_UNAVAILABLE:
                failure = PreconditionFailed(ErrorCode.SECRET_UNAVAILABLE, "Keyring entry unavailable")
        except Exception:  # noqa: BLE001 - discard untrusted diagnostics
            failure = _unavailable(ref)
        else:
            if type(value) is str:
                try:
                    self._on_reveal(value)
                except Exception:  # noqa: BLE001 - the callback may disclose its argument
                    failure = _unavailable(ref)
                else:
                    return SecretValue(ref, value)
        # Raise outside except: even __context__ must not retain a secret.
        raise failure if failure is not None else _unavailable(ref)


@lru_cache(maxsize=1)
def _schemas() -> SchemaRegistry:
    from skm.platform.schema.registry import SchemaRegistry

    return SchemaRegistry.load_default()


def mask_secret_refs(value: JsonValue, schema: Mapping[str, JsonValue]) -> JsonValue:
    """Mask secret literals while preserving references. Inspect conditional annotations conservatively.

    Resolve references offline in their declaring resource. Invalid or cyclic declarations and an
    exhausted visit budget fail closed.
    """
    if not isinstance(schema.get("$id", ""), str):
        return _MASK
    try:
        resolver = _schemas().resolver_for(schema)
    except Exception:  # noqa: BLE001 - an uninterpretable schema must not disclose diagnostic data
        return _MASK
    try:
        return _mask(value, schema, resolver, _Walk(_VISITS, _SCHEMA_VISITS), frozenset(), 0)
    except _Exhausted:
        return _MASK


class _Exhausted(Exception):
    """The visit budget of one call ran out; what was not visited may hold a secret."""


@dataclass(slots=True)
class _Walk:
    """Per-call state: each call has its own budget, so one caller's schema never limits another's."""

    visits: int
    schema_visits: int
    checked: dict[int, tuple[Mapping[str, Any], bool]] = field(
        default_factory=dict[int, tuple[Mapping[str, Any], bool]]
    )

    def schema_visit(self) -> None:
        self.schema_visits -= 1
        if self.schema_visits < 0:
            raise _Exhausted

    def check(self, node: Mapping[str, Any]) -> bool:
        """Check local keywords once per call; the walk owns the applicability of child declarations.

        Replace child contents with boolean schemas, preserving their container constraints. A malformed
        member is checked at its own instance location, so it cannot erase a safe public sibling. Literal
        data and keywords the walk does not descend into retain their full metaschema checks.
        """
        if not node:
            return True
        cached = self.checked.get(id(node))
        if cached is not None:
            return cached[1]
        local: dict[str, Any] = {}
        for keyword, child in node.items():
            self.schema_visit()
            projected = child
            if keyword in _SCHEMA_MAPS and isinstance(child, Mapping):
                if keyword == "patternProperties":
                    patterns: dict[str, bool] = {}
                    for pattern in cast("Mapping[str, Any]", child):
                        self.schema_visit()
                        patterns[pattern] = True
                    projected = patterns
                else:
                    projected = {}
            elif keyword in _SCHEMA_LISTS and isinstance(child, list):
                projected = [True] if child else []
            elif keyword in _SCHEMA_SINGLES:
                # Containers apply malformed member declarations locally to preserve safe siblings.
                # Scalars have no member walk; _mask_container must reject those shapes itself.
                projected = True
            local[keyword] = projected
        # Bound the input to text_safe and metaschema validation, including repeated/cyclic literal data.
        pending: list[Iterator[object]] = [iter((local,))]
        while pending:
            try:
                item = next(pending[-1])
            except StopIteration:
                pending.pop()
                continue
            self.schema_visit()
            if isinstance(item, Mapping):
                pending.append(iter(cast("Mapping[str, object]", item).values()))
            elif isinstance(item, list):
                pending.append(iter(cast("list[object]", item)))
        try:
            valid = _schemas().is_valid_schema(local)
        except Exception:  # noqa: BLE001 - schema diagnostics must not disclose values or exceptions
            valid = False
        # Retain the node as well as its id: resolved temporary objects must not reuse a cached id.
        self.checked[id(node)] = (node, valid)
        return valid


def _context(target: object, resolver: Any, annotations_only: bool) -> _Context:
    """Identify a reference by target, base and outermost occurrence of each dynamic scope URI."""
    try:
        base: int | None = id(resolver.lookup("#").contents)
    except Exception:  # noqa: BLE001 - an unknown base only makes contexts coincide, which masks more
        base = None
    oldest_first = reversed([uri for uri, _ in resolver.dynamic_scope()])
    return (id(target), base, tuple(dict.fromkeys(oldest_first)), annotations_only)


def _schema_object(declaration: object) -> Mapping[str, Any] | None:
    return cast("Mapping[str, Any]", declaration) if isinstance(declaration, Mapping) else None


def _is_secret(schema: Mapping[str, Any]) -> bool:
    """Flagged ``x-skm-secret``, or the packaged SecretRef schema: referenced by URN or reached itself."""
    return (
        schema.get("x-skm-secret") is True
        or schema.get("$id") == _SECRET_REF_URN
        or any(schema.get(keyword) == _SECRET_REF_URN for keyword in _REFERENCES)
    )


def _mask_secret(value: JsonValue) -> JsonValue:
    if type(value) is str:
        try:
            return str(SecretRef.parse(value))
        except ValidationFailed:
            pass
    return _MASK


def _descend(
    value: JsonValue,
    schema: object,
    resolver: Any,
    walk: _Walk,
    active: frozenset[_Context],
    depth: int,
    annotations_only: bool,
) -> JsonValue:
    """``_mask`` of a subschema reached in place; its own ``$id`` rebases its references.

    A reference target needs no such step: its lookup already returns the resolver of the target resource.
    """
    node = _schema_object(schema)
    if node is not None and "$id" in node:
        if not isinstance(node["$id"], str):
            return _MASK
        try:
            from skm.platform.schema.validator import scope

            resolver = scope(node, resolver)
        except Exception:  # noqa: BLE001 - an unusable base URI is as uninterpretable as an unresolved one
            return _MASK
    return _mask(value, schema, resolver, walk, active, depth, annotations_only)


def _follow_references(
    value: JsonValue,
    schema: Mapping[str, Any],
    resolver: Any,
    walk: _Walk,
    active: frozenset[_Context],
    depth: int,
    annotations_only: bool,
) -> JsonValue:
    """Apply each reference target; ``active`` holds the contexts entered at this instance location."""
    for keyword in _REFERENCES:
        if keyword not in schema:
            continue
        reference = schema[keyword]
        if not isinstance(reference, str):
            return _MASK  # a malformed (even null) reference is as uninterpretable as an unresolved one
        try:
            # As in validation, $dynamicRef is looked up like $ref: ``referencing`` follows a
            # $dynamicAnchor through the dynamic scope that the lookups on this path recorded.
            resolved = resolver.lookup(reference)
        except Exception:  # noqa: BLE001 - an uninterpretable schema must not disclose diagnostic data
            return _MASK
        target: object = resolved.contents
        if type(target) is not bool and _schema_object(target) is None:
            return _MASK
        context = _context(target, resolved.resolver, annotations_only)
        if context in active:
            return _MASK  # back in a context still being walked without consuming the instance: a cycle
        value = _mask(value, target, resolved.resolver, walk, active | {context}, depth + 1, annotations_only)
    return value


def _mask(
    value: JsonValue,
    schema: object,
    resolver: Any,
    walk: _Walk,
    active: frozenset[_Context],
    depth: int,
    annotations_only: bool = False,
) -> JsonValue:
    walk.visits -= 1
    if walk.visits < 0:
        raise _Exhausted
    if depth > 64 or (schema is False and not annotations_only):
        return _MASK
    node = _schema_object({} if isinstance(schema, bool) else schema)
    if node is None or not walk.check(node):
        return _MASK  # a declaration that is not a schema is uninterpretable
    if value is None:
        return None
    if _is_secret(node):
        return _mask_secret(value)
    original = value
    value = _follow_references(value, node, resolver, walk, active, depth, annotations_only)
    if value != _MASK:
        value = _compose(original, value, node, resolver, walk, active, depth, annotations_only)
    return _MASK if value == _MASK else _mask_container(value, node, resolver, walk, depth, annotations_only)


def _compose(
    original: JsonValue,
    value: JsonValue,
    schema: Mapping[str, Any],
    resolver: Any,
    walk: _Walk,
    active: frozenset[_Context],
    depth: int,
    annotations_only: bool,
) -> JsonValue:
    """Apply the in-place applicators. A whole mask absorbs every later branch, so stop at the first.

    ``allOf`` and a ``dependentSchemas`` entry whose property is present always apply. Which alternative,
    conditional branch or negation applies depends on validation, so inspect each of them for annotations.
    """
    composed = {keyword: schema.get(keyword, []) for keyword in ("allOf", "anyOf", "oneOf")}
    dependent = schema.get("dependentSchemas", {})
    if not all(isinstance(branches, list) for branches in composed.values()) or not isinstance(
        dependent, Mapping
    ):
        return _MASK
    applied = list(composed["allOf"])
    if type(original) is dict:
        dependent = cast("Mapping[str, Any]", dependent)
        applied += [branch for name, branch in dependent.items() if name in original]
    for branch in applied:
        value = _descend(value, branch, resolver, walk, active, depth + 1, annotations_only)
        if value == _MASK:
            return _MASK
    # Without ``if``, ``then`` and ``else`` are ignored; ``not`` keeps no annotations, but a declaration
    # there still names the data as secret.
    conditional = [schema[key] for key in ("if", "then", "else") if key in schema] if "if" in schema else []
    if "not" in schema:
        conditional.append(schema["not"])
    for branch in [*composed["anyOf"], *composed["oneOf"], *conditional]:
        # An alternative's closed shape cannot erase another alternative's public fields.
        # Inspect the original even when invalid secrets prevent every branch from validating;
        # combine only the masks, so neither branch order nor a permissive branch restores secrets.
        candidate = _descend(original, branch, resolver, walk, active, depth + 1, annotations_only=True)
        value = _merge_masks(value, candidate)
        if value == _MASK:
            return _MASK
    return value


def _merge_masks(value: JsonValue, candidate: JsonValue) -> JsonValue:
    if candidate == _MASK:
        return _MASK
    if type(value) is dict and type(candidate) is dict:
        return {key: _merge_masks(item, candidate[key]) for key, item in value.items()}
    if type(value) is list and type(candidate) is list:
        return [_merge_masks(item, candidate[i]) for i, item in enumerate(value)]
    return value


def _apply(item: JsonValue, declarations: _Declarations, resolver: Any, walk: _Walk, depth: int) -> JsonValue:
    for declaration, annotations_only in declarations:
        item = _descend(item, declaration, resolver, walk, frozenset(), depth + 1, annotations_only)
    return item


def _simple_validity(value: JsonValue, declaration: object) -> bool | None:
    """Prove only boolean, empty and type-only schemas; ``None`` means success is uncertain.

    Full validation could expand references or recurse outside the masker's visit budget. This proof
    examines at most seven type names and never follows a schema, reference or regular expression.
    """
    if type(declaration) is bool:
        return declaration
    node = _schema_object(declaration)
    if node is None:
        return None
    if not node:
        return True
    if len(node) != 1 or "type" not in node:
        return None
    declared = node["type"]
    types = [declared] if isinstance(declared, str) else declared
    names = ("null", "boolean", "object", "array", "number", "integer", "string")
    if not isinstance(types, list):
        return None
    types = cast("list[Any]", types)
    if not 1 <= len(types) <= len(names) or any(
        not isinstance(name, str) or name not in names for name in types
    ):
        return None
    from skm.platform.schema.validator import is_schema_type

    return any(is_schema_type(value, name) for name in types)


def _remaining_declarations(
    item: JsonValue,
    schema: Mapping[str, Any],
    applied: str,
    unevaluated: str,
    annotations_only: bool,
    uncertain: bool,
) -> _Declarations:
    """Keep unevaluated annotations unless a local declaration is proven to evaluate this member."""
    declarations: _Declarations = []
    if applied in schema:
        declarations.append((schema[applied], annotations_only))
        if unevaluated not in schema:
            return declarations
        valid = _simple_validity(item, schema[applied])
        if valid is True:
            return declarations
        # Unknown success proves only that annotations may apply, so a boolean false must not erase
        # otherwise public data. A proven failure of additionalProperties leaves its member unevaluated.
        uncertain = uncertain or valid is None
    if unevaluated in schema:
        declarations.append((schema[unevaluated], uncertain))
    return declarations or [({}, annotations_only)]


def _member_declarations(
    key: str,
    item: JsonValue,
    schema: Mapping[str, Any],
    properties: Mapping[str, Any],
    patterns: Mapping[str, Any],
    annotations_only: bool,
    uncertain: bool,
) -> _Declarations | None:
    """``None`` when an invalid pattern may have been meant to match ``key``."""
    declarations: _Declarations = []
    if key in properties:
        declarations.append((properties[key], annotations_only))
    for pattern, declaration in patterns.items():
        try:
            if re.search(pattern, key):
                declarations.append((declaration, annotations_only))
        except re.error:
            return None
    if declarations:
        return declarations
    return _remaining_declarations(
        item, schema, "additionalProperties", "unevaluatedProperties", annotations_only, uncertain
    )


def _item_declarations(
    index: int,
    item: JsonValue,
    schema: Mapping[str, Any],
    prefix: list[Any],
    annotations_only: bool,
    uncertain: bool,
) -> _Declarations:
    if index < len(prefix):
        declarations = [(prefix[index], annotations_only)]
    else:
        # Unlike additionalProperties, sibling items marks indexes evaluated even on failure in the
        # validator. Conservatively inspect unevaluated annotations, without applying a rejecting false.
        declarations = _remaining_declarations(
            item, schema, "items", "unevaluatedItems", annotations_only, uncertain or "items" in schema
        )
    if "contains" in schema:
        declarations.append((schema["contains"], True))
    return declarations


def _mask_container(
    value: JsonValue,
    schema: Mapping[str, Any],
    resolver: Any,
    walk: _Walk,
    depth: int,
    annotations_only: bool,
) -> JsonValue:
    """Mask each member against its declarations; a member is a new instance location, so no context is
    active there yet.

    A sibling ``additionalProperties``/``items`` is enough to skip ``unevaluated*`` annotations only when
    it provably succeeds. A known additionalProperties failure keeps the local unevaluated declaration
    applicable; otherwise inspect its annotations conservatively. An in-place applicator (or ``contains``)
    may also evaluate a member: without proof either way, inspect ``unevaluated*`` for annotations only.
    """
    uncertain = annotations_only or any(keyword in schema for keyword in _IN_PLACE)
    if type(value) is dict:
        properties = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        if not isinstance(properties, Mapping) or not isinstance(patterns, Mapping):
            return _MASK
        properties = cast("Mapping[str, Any]", properties)
        patterns = cast("Mapping[str, Any]", patterns)
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            declarations = _member_declarations(
                key, item, schema, properties, patterns, annotations_only, uncertain
            )
            result[key] = _MASK if declarations is None else _apply(item, declarations, resolver, walk, depth)
        return result
    if type(value) is list:
        prefix = schema.get("prefixItems", [])
        if not isinstance(prefix, list):
            return _MASK
        prefix = cast("list[Any]", prefix)
        uncertain = uncertain or "contains" in schema
        return [
            _apply(
                item,
                _item_declarations(i, item, schema, prefix, annotations_only, uncertain),
                resolver,
                walk,
                depth,
            )
            for i, item in enumerate(value)
        ]
    if type(value) in (str, bool, int, float):
        if any(
            keyword in schema
            and type(schema[keyword]) is not bool
            and not isinstance(schema[keyword], Mapping)
            for keyword in _MEMBER_SCHEMAS
        ):
            return _MASK
        return value
    return _MASK
