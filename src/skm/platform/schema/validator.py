"""Draft 2020-12 validation of one schema into stable, bounded, sorted ``SchemaIssue`` tuples."""

import copy
import math
import re
from collections.abc import Callable, Iterator, Mapping
from contextvars import ContextVar
from fractions import Fraction
from typing import Any, Final, Self, cast, override

from jsonschema import Draft202012Validator
from jsonschema import validators as jsonschema_validators
from jsonschema.exceptions import ValidationError, best_match  # pyright: ignore[reportUnknownVariableType]
from jsonschema.validators import extend  # pyright: ignore[reportUnknownVariableType]
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.schema.findings import ELLIPSIS, VALUE_LIMIT, SchemaIssue, json_pointer
from skm.platform.schema.formats import FORMAT_CHECKER

__all__ = [
    "REDACTED",
    "SECRET_KEYWORD",
    "SchemaValidator",
    "dialect_free",
    "is_schema_type",
    "scope",
    "subschemas",
    "text_safe",
    "without_dialect",
]

SECRET_KEYWORD: Final = "x-skm-secret"
REDACTED: Final = "<redacted>"

_BRANCHING = frozenset({"oneOf", "anyOf"})
_SECRET_DEPTH: Final = 4  # how far a property schema is followed (ref/allOf/anyOf/oneOf) to find the flag
_SECRETS: ContextVar[list[object] | None] = ContextVar("skm_schema_secrets", default=None)
# The int-to-text limit of an interpreter is 0 (off) or at least sys.int_info.str_digits_check_threshold
# (640 digits): below this bound ``repr`` of an integer is never refused.
_TEXT_SAFE_INT: Final = 10**640
_MAP_KEYWORDS: Final = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
_LIST_KEYWORDS: Final = ("allOf", "anyOf", "oneOf", "prefixItems")
_SINGLE_KEYWORDS: Final = (
    "items",
    "additionalProperties",
    "additionalItems",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "propertyNames",
    "unevaluatedItems",
    "unevaluatedProperties",
    "contentSchema",
)

type _Redact = Callable[[str], str]
type _Document = dict[str, Any]
type _Parts = tuple[str | int, ...]


def is_schema_type(instance: object, name: str) -> bool:
    """Check one type name with the stock Draft 2020-12 semantics, without walking a schema or instance.

    Keep the third-party type checker inside the schema boundary. In particular, booleans are not numbers,
    integral floats are integers, subclasses retain their stock behavior and arbitrary mappings are not
    objects. Callers must supply a known Draft 2020-12 type name.
    """
    return Draft202012Validator.TYPE_CHECKER.is_type(instance, name)


def scope(node: Mapping[str, Any], resolver: Any) -> Any:
    """``resolver`` as seen from inside ``node``: a nested ``$id`` starts a new base URI and fragment
    scope."""
    if resolver is not None and isinstance(node.get("$id"), str):
        return resolver.in_subresource(DRAFT202012.create_resource(node))
    return resolver


def subschemas(
    node: Mapping[str, Any], parts: _Parts, resolver: Any
) -> Iterator[tuple[_Parts, Mapping[str, Any], Any]]:
    """``node`` and every schema nested below it through a known applicator keyword, each with its scope."""
    resolver = scope(node, resolver)
    yield parts, node, resolver
    for keyword in _MAP_KEYWORDS:
        children = node.get(keyword)
        if isinstance(children, dict):
            for name, child in cast("dict[str, Any]", children).items():
                if isinstance(child, dict):
                    yield from subschemas(cast("_Document", child), (*parts, keyword, name), resolver)
    for keyword in (*_LIST_KEYWORDS, *_SINGLE_KEYWORDS):
        children = node.get(keyword)
        if isinstance(children, dict):
            yield from subschemas(cast("_Document", children), (*parts, keyword), resolver)
        elif isinstance(children, list) and keyword in _LIST_KEYWORDS:
            for index, child in enumerate(cast("list[Any]", children)):
                if isinstance(child, dict):
                    yield from subschemas(cast("_Document", child), (*parts, keyword, index), resolver)


def without_dialect(document: Mapping[str, Any]) -> _Document:
    """A copy of ``document`` with ``$schema`` removed from every schema object.

    ``jsonschema`` picks the validator class of each descended schema from its ``$schema``; without
    the keyword
    the secret-aware class that started the validation is kept for the whole ``$ref`` closure.
    Every integer literal of at least ``_TEXT_SAFE_INT`` becomes a ``_WideInt`` (the same value): a message
    quotes ``const``/``enum``/``maximum`` or a whole ``oneOf``/``not`` branch schema.
    """
    clone = copy.deepcopy(dict(document))
    for _, node, _ in subschemas(clone, (), None):
        cast("dict[str, Any]", node).pop("$schema", None)
    return cast("_Document", text_safe(clone))


def dialect_free(schema: Mapping[str, Any], registry: Registry[Any]) -> tuple[_Document, Registry[Any]]:
    """``schema`` and every resource of ``registry`` as dialect-free copies (nothing is fetched or
    retrieved)."""
    resources: list[tuple[str, Resource[Any]]] = []
    for uri in registry:
        contents = registry[uri].contents
        if isinstance(contents, dict):  # boolean schemas (and anything else) are kept as registered
            contents = without_dialect(cast("_Document", contents))
        resources.append((uri, DRAFT202012.create_resource(contents)))
    return without_dialect(schema), Registry[Any]().with_resources(resources)


def _collect_secret(_validator: object, flagged: object, instance: object, _schema: object) -> None:
    """Keyword ``x-skm-secret: true``: remember every instance it is applied to; it never fails validation."""
    collected = _SECRETS.get()
    if flagged is True and collected is not None:
        collected.append(instance)


_STOCK_MULTIPLE_OF: Any = Draft202012Validator.VALIDATORS["multipleOf"]


def _multiple_of(
    validator: object, divisor: object, instance: object, schema: object
) -> Iterator[ValidationError]:
    """Keyword ``multipleOf``: exact remainder under one decimal interpretation for int/float pairs.

    JSON Schema's numeric model is decimal. Integers keep their exact values; finite floats use their
    shortest built-in decimal representation (``float.__repr__``) for both operands, regardless of size
    or binary representability. This cannot recover original JSON token precision already lost during parsing.
    Nonfinite instances fail a positive finite divisor. Other Python numeric types and invalid divisors
    retain the stock behavior.
    """
    if (
        isinstance(instance, int | float)
        and not isinstance(instance, bool)
        and isinstance(divisor, int | float)
        and not isinstance(divisor, bool)
        and divisor > 0
        and (not isinstance(divisor, float) or math.isfinite(divisor))
    ):
        if isinstance(instance, float) and not math.isfinite(instance):
            failed = True
        else:
            # Bypass float subclass display/conversion overrides; int() keeps _WideInt's full value.
            number = Fraction(float.__repr__(instance)) if isinstance(instance, float) else int(instance)
            factor = Fraction(float.__repr__(divisor)) if isinstance(divisor, float) else int(divisor)
            failed = bool(number % factor)
        if failed:
            yield ValidationError(f"{instance!r} is not a multiple of {divisor}")
        return
    yield from cast("Iterator[ValidationError]", _STOCK_MULTIPLE_OF(validator, divisor, instance, schema))


_Validator: Any = extend(Draft202012Validator, {SECRET_KEYWORD: _collect_secret, "multipleOf": _multiple_of})  # pyright: ignore[reportUnknownVariableType]
# The metaschema registry jsonschema merges into every validator's registry when it builds the resolver.
# The stubs omit the module attribute; it is the registry ``__attrs_post_init__`` combines with.
_SPECIFICATIONS = cast("Registry[Any]", vars(jsonschema_validators)["SPECIFICATIONS"])
_combined_last: tuple[Registry[Any], Registry[Any]] | None = None


def _with_specifications(registry: Registry[Any]) -> Registry[Any]:
    """``registry`` merged with the metaschemas, as jsonschema would merge it, reused for the same registry.

    The merge copies every resource of ``registry``. jsonschema repeats it for each validator, which made
    compiling hundreds of leaf validators over the shared schema registry quadratic in practice.
    """
    global _combined_last  # noqa: PLW0603
    last = _combined_last
    if last is not None and last[0] is registry:
        return last[1]
    combined = _SPECIFICATIONS.combine(registry)
    _combined_last = (registry, combined)
    return combined


class _WideInt(int):
    """An integer the interpreter may refuse to write as text; it shows its leading digits instead.

    ``jsonschema`` writes ``repr(instance)`` into every message as it builds an error, also for an
    ``anyOf``/``oneOf`` branch that fails while another one matches; this text keeps that from raising.
    The same holds for a schema literal (``without_dialect``); comparisons stay those of the exact integer.
    """

    _text: str

    def __new__(cls, value: int) -> Self:
        wide = super().__new__(cls, value)
        number = abs(value)
        # a lower bound of the decimal digits (log10(2) > 0.3010299956): the quotient keeps all those shown
        cut = max((number.bit_length() - 1) * 3010299956 // 10**10 + 1 - VALUE_LIMIT, 0)
        head = ("-" if value < 0 else "") + str(number // 10**cut)
        wide._text = head[: VALUE_LIMIT - 1] + ELLIPSIS  # as ``_shorten_instance`` would cut the full text
        return wide

    @override
    def __repr__(self) -> str:
        return self._text

    @override
    def __str__(self) -> str:
        return self._text


def _text_safe_scalar(value: object) -> object:
    if (
        isinstance(value, int)
        and not isinstance(value, bool | _WideInt)
        and not -_TEXT_SAFE_INT < value < _TEXT_SAFE_INT
    ):
        return _WideInt(value)
    return value


def _is_container(value: object) -> bool:
    return isinstance(value, dict | list)


def _children(node: object) -> list[object]:
    if isinstance(node, dict):
        return list(cast("dict[object, object]", node).values())
    return list(cast("list[object]", node)) if isinstance(node, list) else []


def text_safe(instance: object) -> object:
    """``instance`` with every integer of at least ``_TEXT_SAFE_INT`` as a ``_WideInt``; unchanged parts are
    kept as they are (the same objects).

    The walk keeps its own stack: a nesting the schema never descends into (``{}``, a matching ``anyOf``
    branch) must not exhaust the interpreter stack here and turn into a spurious issue.
    """
    if not _is_container(instance):
        return _text_safe_scalar(instance)
    safe: dict[int, object] = {}  # id of a container (alive inside ``instance``) -> its text-safe value
    ancestors: set[int] = set()  # containers being expanded; a cyclic reference is left unchanged

    def convert(child: object) -> object:
        return safe.get(id(child), child) if _is_container(child) else _text_safe_scalar(child)

    stack: list[tuple[object, bool]] = [(instance, False)]
    while stack:
        node, expanded = stack.pop()
        key = id(node)
        if not expanded:
            if key in safe or key in ancestors:
                continue
            ancestors.add(key)
            stack.append((node, True))
            stack.extend(
                (child, False)
                for child in _children(node)
                if _is_container(child) and id(child) not in safe and id(child) not in ancestors
            )
            continue
        ancestors.discard(key)
        if isinstance(node, dict):
            mapping = cast("dict[object, object]", node)
            items = {name: convert(value) for name, value in mapping.items()}
            changed = any(items[name] is not value for name, value in mapping.items())
            safe[key] = items if changed else mapping
        else:
            sequence = cast("list[object]", node)
            values = [convert(item) for item in sequence]
            changed = any(new is not old for new, old in zip(values, sequence, strict=True))
            safe[key] = values if changed else sequence
    return safe[id(instance)]


def _secret_values(value: object) -> Iterator[object]:
    """``value`` and, for an object/array, everything nested in it (messages about a child quote the
    child)."""
    yield value
    if isinstance(value, dict):
        for child in cast("dict[str, object]", value).values():
            yield from _secret_values(child)
    elif isinstance(value, list):
        for child in cast("list[object]", value):
            yield from _secret_values(child)


def _redactor(secrets: list[object]) -> _Redact:
    """A function that hides the ``repr`` of every secret value (as jsonschema embeds it in messages)."""
    patterns: dict[str, str] = {}
    for secret in (nested for flagged in secrets for nested in _secret_values(flagged)):
        if secret is None or isinstance(secret, bool) or secret in ("", {}, []):
            continue
        shown = repr(secret)
        # a number must not be cut out of a longer number/word; strings and containers are delimited already
        bare = isinstance(secret, int | float)
        patterns[shown] = rf"(?<![\w.]){re.escape(shown)}(?![\w.])" if bare else re.escape(shown)
    if not patterns:
        return lambda text: text
    ordered = sorted(patterns, key=len, reverse=True)
    compiled = re.compile("|".join(patterns[shown] for shown in ordered))
    return lambda text: compiled.sub(REDACTED, text)


def _shorten_instance(message: str, instance: object, redact: _Redact) -> str:
    """Replace the repr of an instance longer than ``VALUE_LIMIT`` inside ``message`` by its prefix."""
    shown = redact(repr(instance))
    if len(shown) <= VALUE_LIMIT or shown not in message:
        return message
    return message.replace(shown, shown[: VALUE_LIMIT - 1] + ELLIPSIS)


def _unexpected_properties(error: ValidationError) -> list[str]:
    """Names rejected by ``additionalProperties: false`` (not covered by properties/patternProperties)."""
    schema = cast("Mapping[str, Any]", error.schema)
    instance = cast("Mapping[str, Any]", error.instance)
    declared = cast("Mapping[str, Any]", schema.get("properties", {}))
    pattern_map = cast("Mapping[str, Any]", schema.get("patternProperties", {}))
    patterns = [re.compile(pattern) for pattern in pattern_map]
    return [name for name in instance if name not in declared and not any(p.search(name) for p in patterns)]


def _issue(error: ValidationError, message: str) -> SchemaIssue:
    code = cast("str | None", error.validator)
    return SchemaIssue(
        pointer=json_pointer(error.absolute_path),
        schema_pointer=json_pointer(error.absolute_schema_path),
        code=code if code is not None else "schema",
        message=message,
    )


def _own_issues(error: ValidationError, redact: _Redact) -> Iterator[SchemaIssue]:
    """The issues of one error: one per rejected property for ``additionalProperties``, else one."""
    code = cast("str | None", error.validator)
    if code == "additionalProperties" and isinstance(error.instance, dict):
        names = _unexpected_properties(error)
        if names:
            for name in names:
                yield _issue(error, name)
            return
    yield _issue(error, _shorten_instance(redact(error.message), cast("object", error.instance), redact))  # pyright: ignore[reportUnknownMemberType]


def _issues_of(error: ValidationError, redact: _Redact) -> Iterator[SchemaIssue]:
    """The error itself; for ``oneOf``/``anyOf`` additionally the branch error ``best_match`` selects."""
    yield from _own_issues(error, redact)
    if cast("str | None", error.validator) in _BRANCHING and error.context:
        branch = cast("ValidationError | None", best_match([error]))
        if branch is not None and branch is not error:
            yield from _own_issues(branch, redact)


def _is_secret_schema(schema: Mapping[str, Any], resolver: Any, depth: int = 0) -> bool:
    """Whether ``schema`` is flagged ``x-skm-secret``: itself, via its ``$ref`` or an allOf/anyOf/oneOf
    member."""
    if schema.get(SECRET_KEYWORD) is True:
        return True
    if depth >= _SECRET_DEPTH:
        return False
    for keyword in ("allOf", "anyOf", "oneOf"):
        members = schema.get(keyword)
        if isinstance(members, list) and any(
            isinstance(member, dict) and _is_secret_schema(cast("_Document", member), resolver, depth + 1)
            for member in cast("list[Any]", members)
        ):
            return True
    ref = schema.get("$ref")
    if isinstance(ref, str):
        try:
            resolved = resolver.lookup(ref)
        except Unresolvable:
            return False
        target = resolved.contents
        if isinstance(target, dict):
            return _is_secret_schema(cast("_Document", target), resolved.resolver, depth + 1)
    return False


def secret_property_names(schema: Mapping[str, Any], registry: Registry[Any]) -> frozenset[str]:
    """Names of the properties flagged ``x-skm-secret`` in ``schema`` and the documents it references.

    The keyword handler only sees what ``jsonschema`` evaluates, and a short-circuiting ``if``/``not`` may
    stop before a secret field; these names let the redaction find the value whatever the evaluation order.
    """
    names: set[str] = set()
    seen: set[str] = set()
    pending: list[Mapping[str, Any]] = [schema]
    while pending:
        document = pending.pop()
        root = registry.resolver_with_root(DRAFT202012.create_resource(document))
        for _, node, resolver in subschemas(document, (), root):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for name, child in cast("dict[str, Any]", properties).items():
                    if isinstance(child, dict) and _is_secret_schema(cast("_Document", child), resolver):
                        names.add(name)
            for keyword in ("$ref", "$dynamicRef"):
                ref = node.get(keyword)
                uri = ref.partition("#")[0] if isinstance(ref, str) else ""
                if uri.startswith("urn:skm:") and uri not in seen:
                    seen.add(uri)
                    try:
                        target = registry[uri].contents
                    except KeyError:
                        continue
                    if isinstance(target, dict):
                        pending.append(cast("_Document", target))
    return frozenset(names)


def _values_named(instance: object, names: frozenset[str]) -> Iterator[object]:
    """Every value stored under one of ``names`` anywhere in ``instance``."""
    if isinstance(instance, dict):
        for key, value in cast("dict[str, object]", instance).items():
            if key in names:
                yield value
            yield from _values_named(value, names)
    elif isinstance(instance, list):
        for item in cast("list[object]", instance):
            yield from _values_named(item, names)


def _omit_secret_properties(value: JsonValue, names: frozenset[str]) -> JsonValue:
    if isinstance(value, dict):
        return {key: _omit_secret_properties(item, names) for key, item in value.items() if key not in names}
    if isinstance(value, list):
        return [_omit_secret_properties(item, names) for item in value]
    return value


class SchemaValidator:
    """Validates instances against one schema; resolves ``$ref`` only inside the given registry."""

    def __init__(
        self, schema: Mapping[str, JsonValue], registry: Registry[Any], *, dialect_free_inputs: bool = False
    ) -> None:
        """``dialect_free_inputs``: ``schema`` and ``registry`` already went through ``dialect_free`` (or
        ``without_dialect``), which also makes their wide integer literals text-safe."""
        if not dialect_free_inputs:
            schema, registry = dialect_free(schema, registry)
        self._secret_names = secret_property_names(schema, registry)
        resolver = _with_specifications(registry).resolver_with_root(DRAFT202012.create_resource(schema))
        self._validator: Any = _Validator(
            cast("Mapping[str, Any]", schema),
            registry=registry,
            format_checker=FORMAT_CHECKER,
            _resolver=resolver,
        )

    def without_secret_properties(self, value: JsonObject) -> JsonObject:
        """Strip properties declared secret from a validated result before persisting its receipt."""
        if not self._secret_names:
            return value
        return {
            key: _omit_secret_properties(item, self._secret_names)
            for key, item in value.items()
            if key not in self._secret_names
        }

    def issues(self, instance: object) -> tuple[SchemaIssue, ...]:
        """All findings, deduplicated by ``(pointer, code, message)`` and sorted by ``(pointer, code)``.

        Values of ``x-skm-secret`` fields never appear in a message (conventions §1.2). An integer of any
        width is validated as itself; a message shows its leading digits (``_WideInt``).
        """
        found: list[SchemaIssue] = []
        secrets: list[object] = []
        token = _SECRETS.set(secrets)
        try:
            instance = text_safe(instance)
            errors = cast("list[ValidationError]", list(self._validator.iter_errors(instance)))
            if self._secret_names:
                secrets.extend(_values_named(instance, self._secret_names))
            redact = _redactor(secrets)
            for error in errors:
                found.extend(_issues_of(error, redact))
        except Unresolvable as exc:
            reference = getattr(exc, "ref", None) or str(exc)
            found.append(SchemaIssue("", "", "$ref", f"unresolved reference {reference!r}"))
        except RecursionError:
            found.append(SchemaIssue("", "", "$ref", "references recurse without consuming the instance"))
        finally:
            _SECRETS.reset(token)
        unique = {(issue.pointer, issue.code, issue.message): issue for issue in found}
        return tuple(sorted(unique.values(), key=lambda i: (i.pointer, i.code, i.message, i.schema_pointer)))
