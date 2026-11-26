"""Normalization and the specification digest (planning §5.6).

``normalize_document`` returns a new document in which the defaults that carry meaning are written explicitly
(§5.1), an empty optional array is dropped (its absence means the same) except ``phase.depends_on`` (absent:
after the previous phase; ``[]``: no prerequisite), and an empty ``extensions`` is dropped. Array order,
strings, entity ids and the members a ``work_policy`` declares are kept exactly. The written defaults are the
ones ``to_document`` writes, so ``to_document(from_document(d)[0]) == normalize_document(d)``; a default the
model does not write back (``global: false``, an empty phase ``contract``, empty external ``params``) is
dropped instead.

The digest covers the whole normalized document, ``schema`` and entity ids included: the document holds no
generated member to exclude. Canonical JSON v1 is the one of ``platform.jsonc`` (UTF-8, keys in code point
order, compact separators, no floats, arrays in order); domain code may not import ``platform``, so the
serialization is written here and a test pins it to ``skm.platform.jsonc``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from skm.kernel.json_types import JsonObject, JsonValue

type _Rule = Callable[[Mapping[str, JsonValue]], JsonObject]

CANONICALIZATION_VERSION: Final = 1

_NOTHING: Final[Mapping[str, JsonValue]] = MappingProxyType({})
_NO_RULES: Final[Mapping[str, _Rule]] = MappingProxyType({})


def _plain(value: object) -> JsonValue:
    """A fresh JSON copy of ``value``: any mapping becomes a dict, a list or tuple a list.

    A float, a non-string object key or a non-JSON value is a ``TypeError``: it has no canonical form.
    """
    if value is None or isinstance(value, str | int):  # bool is an int
        return cast("JsonValue", value)
    if isinstance(value, float):
        raise TypeError("canonical JSON values must not use floats")
    if isinstance(value, Mapping):
        return {_name(key): _plain(item) for key, item in cast("Mapping[object, object]", value).items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in cast("list[object] | tuple[object, ...]", value)]
    raise TypeError("value is not canonical JSON data")


def _name(key: object) -> str:
    if not isinstance(key, str):
        raise TypeError("canonical JSON object keys must be strings")
    return key


def _empty_array(value: object) -> bool:
    return isinstance(value, list | tuple) and not value


def _object(
    doc: Mapping[str, JsonValue],
    *,
    defaults: Mapping[str, JsonValue] = _NOTHING,
    optional: frozenset[str] = frozenset(),
    members: Mapping[str, _Rule] = _NO_RULES,
    elements: Mapping[str, _Rule] = _NO_RULES,
) -> JsonObject:
    """A normalized copy of one schema object.

    ``optional`` names the array members whose empty value is dropped; ``members`` normalizes a nested object,
    ``elements`` each object of an array member; ``defaults`` are written where the member is absent. A value
    of an unexpected shape is copied as is: the schema checks the shape, not this function.
    """
    out: JsonObject = {}
    for key, value in cast("Mapping[object, JsonValue]", doc).items():
        name = _name(key)
        if name in optional and _empty_array(value):
            continue
        rule, element = members.get(name), elements.get(name)
        if rule is not None and isinstance(value, Mapping):
            out[name] = rule(value)
        elif element is not None and isinstance(value, list | tuple):
            out[name] = [element(e) if isinstance(e, Mapping) else _plain(e) for e in value]
        else:
            out[name] = _plain(value)
    for name, value in defaults.items():
        if name not in out:
            out[name] = _plain(value)
    return out


def _without(out: JsonObject, name: str, dropped: JsonValue) -> JsonObject:
    """``out`` without ``name`` when it holds the default ``to_document`` does not write back."""
    if name in out and out[name] == dropped and type(out[name]) is type(dropped):
        del out[name]
    return out


# ------------------------------------------------------------------------------------------- checks


def _cwd(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, defaults={"path": "."})


def _runnable(doc: Mapping[str, JsonValue]) -> JsonObject:
    """``command`` and ``shell`` definitions (of a check or a unit command)."""
    return _object(
        doc, defaults={"timeout_seconds": 600}, optional=frozenset({"env_allow"}), members={"cwd": _cwd}
    )


def _manual(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, defaults={"allowed_verdicts": ["pass", "fail"]})


def _external(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _without(_object(doc), "params", {})


_DEFINITIONS: Final[Mapping[str, _Rule]] = MappingProxyType(
    {"command": _runnable, "shell": _runnable, "manual": _manual, "external": _external}
)


def _definition(kind: JsonValue) -> _Rule:
    return _DEFINITIONS.get(kind, _object) if isinstance(kind, str) else _object


def _evidence(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, defaults={"stdout": True, "stderr": True}, optional=frozenset({"report_files"}))


def _check(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(
        doc,
        defaults={
            "required": doc.get("category") == "acceptance",
            "rerun_after_integration": False,
            "evidence": {"stdout": True, "stderr": True},
        },
        members={"evidence": _evidence, "definition": _definition(doc.get("kind"))},
    )


# ------------------------------------------------------------------------------------------- entities

_PHASE_ARRAYS: Final = frozenset(
    {"pitfalls", "deliverables", "supporting", "batches", "sections"}
)  # not depends_on
_ITEM_ARRAYS: Final = frozenset(
    {
        "depends_on", "relations", "implements", "decisions", "skills", "reads", "examples", "change_hints",
        "artifacts", "rules", "deliverables", "sections",
    }
)  # fmt: skip
_UNIT_ARRAYS: Final = frozenset(
    {"write_scope", "reads", "depends_on", "checks", "outputs", "implements", "sections"}
)
_DECISION_ARRAYS: Final = frozenset(
    {"options", "consequences", "applies_to", "supersedes", "evidence", "sections"}
)


def _contract(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, optional=frozenset({"consumes", "produces", "boundaries"}))


def _assurance(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, optional=frozenset({"seams"}))


def _phase(doc: Mapping[str, JsonValue]) -> JsonObject:
    out = _object(
        doc,
        defaults={"strategy": "dag"},
        optional=_PHASE_ARRAYS,
        members={"contract": _contract, "assurance": _assurance},
    )
    return _without(out, "contract", {})


def _review(doc: Mapping[str, JsonValue]) -> JsonObject:
    defaults: Mapping[str, JsonValue] = (
        {"independence": "separate_session"} if doc.get("mode") == "required" else _NOTHING
    )
    return _object(doc, defaults=defaults, optional=frozenset({"covers", "required_evidence"}))


def _item(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(
        doc,
        defaults={"work_kind": "code", "authority": {"kind": "routine"}, "unit_strategy": "dag"},
        optional=_ITEM_ARRAYS,
        members={"review": _review},
    )


def _unit_command(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, members={"definition": _definition(doc.get("kind"))})


def _unit(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(
        doc,
        defaults={"unit_kind": "implementation", "mode": "either"},
        optional=_UNIT_ARRAYS,
        members={"command": _unit_command},
    )


def _requirement(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, optional=frozenset({"owners"}))


def _criterion(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, optional=frozenset({"checks", "requirements"}))


def _decision(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _without(_object(doc, optional=_DECISION_ARRAYS), "global", False)


def _material(doc: Mapping[str, JsonValue]) -> JsonObject:
    out = _object(
        doc, defaults={"freshness": {"policy": "pinned"}}, optional=frozenset({"required_for", "applies_to"})
    )
    return _without(out, "global", False)


# ------------------------------------------------------------------------------------------- document

_ROOT_ARRAYS: Final = frozenset(
    {
        "non_goals", "rules", "requirements", "units", "criteria", "checks", "decisions", "materials",
        "plan_relations", "sections",
    }
)  # fmt: skip
_ENTITIES: Final[Mapping[str, _Rule]] = MappingProxyType(
    {
        "requirements": _requirement,
        "phases": _phase,
        "items": _item,
        "units": _unit,
        "criteria": _criterion,
        "checks": _check,
        "decisions": _decision,
        "materials": _material,
    }
)


def _brief(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, optional=frozenset({"constraints", "environment", "out_of_scope"}))


def _constraints(doc: Mapping[str, JsonValue]) -> JsonObject:
    return _object(doc, defaults={"strategy": "dag"}, optional=frozenset({"forbidden_paths"}))


def normalize_document(doc: Mapping[str, JsonValue]) -> JsonObject:
    """The normalized copy of a schema-valid specification document; ``doc`` is not mutated.

    Mappings and tuples of the input become dicts and lists; the result shares no container with ``doc``.
    Normalizing twice changes nothing.
    """
    out = _object(
        doc,
        defaults={"execution_constraints": {"strategy": "dag"}},
        optional=_ROOT_ARRAYS,
        members={"brief": _brief, "execution_constraints": _constraints},
        elements=_ENTITIES,
    )
    return _without(out, "extensions", {})


def _canonical_bytes(normalized: JsonObject) -> bytes:
    """Canonical JSON v1 of a normalized document (it holds no float: ``_plain`` refused them)."""
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def specification_digest(doc: Mapping[str, JsonValue]) -> str:
    """``sha256:<hex>`` of the canonical bytes of the normalized document."""
    return "sha256:" + hashlib.sha256(_canonical_bytes(normalize_document(doc))).hexdigest()


def document_bytes(doc: Mapping[str, JsonValue]) -> int:
    """Length of the canonical bytes of the normalized document (``planning.drafts.max_document_bytes``)."""
    return len(_canonical_bytes(normalize_document(doc)))
