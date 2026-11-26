"""Settings registry: key metadata of every section, built and checked once (settings §B.2, REG-01…REG-20).

``SettingsRegistry.build`` reads the ``x-skm`` / ``x-skm-section`` metadata of the section schemas and either
returns an immutable registry or raises ``InternalError(CONFIG_REGISTRY_INVALID)`` that lists *all*
``RegistryProblem`` at once. The package imports no module: views and validators arrive as arguments.
"""

import hashlib
import json
import re
from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config.keys import (
    CHAIN_STORED_LEVELS,
    MISSING,
    SECRET_REF_URN,
    Chain,
    KeySpec,
    Level,
    MergeStrategy,
    NarrowDirection,
    SectionInfo,
    Sensitivity,
    ValidatorSpec,
)
from skm.platform.schema.findings import SchemaIssue
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator, without_dialect

__all__ = ["RegistryProblem", "SectionValidatorFn", "SettingsRegistry", "schema_closure_digest"]

type SectionValidatorFn = Callable[[Mapping[str, JsonValue]], str | None]

KEY_SPEC_URN: Final = "urn:skm:config:key-spec:v1"
RESERVED_SECTION_IDS: Final = frozenset({"command", "result", "query", "view", "event", "defs", "document"})
RESERVED_PLUGIN_IDS: Final = frozenset({"allowed", "required", "control_plane_allowed", "override_builtin"})
FORBIDDEN_UNIT_SUFFIXES: Final = ("_s", "_mb", "_gb", "_kb")
MAX_KEY_SEGMENTS: Final = 4
_SEGMENT: Final = re.compile(r"[a-z][a-z0-9_]*")
_PLUGIN_SECTION: Final = re.compile(r"plugins\.([a-z][a-z0-9_]*)(\.[a-z][a-z0-9_]*)?")
_LEAF_EXCLUDED: Final = frozenset({"default", "description", "x-skm"})
_NUMERIC: Final = frozenset({"integer", "number"})
# Remembered schema verdicts per registry; resolving a chain checks every key, mostly with unchanged values.
_VERDICTS_MAX: Final = 8192


@dataclass(frozen=True, slots=True)
class RegistryProblem:
    code: str
    section: str
    key: str | None
    message: str

    def to_json(self) -> JsonObject:
        return {"code": self.code, "section": self.section, "key": self.key, "message": self.message}


def _value_key(value: object) -> Hashable:
    """A hashable stand-in equal only for values of identical types, order and content.

    Every node is tagged with its exact type: ``1``, ``1.0`` and ``True`` stay distinct, as do a list and a
    tuple or a dict and another mapping, because the schema type checks tell them apart.
    """
    kind: type = type(value)
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value).items()
        return (kind, tuple((name, _value_key(item)) for name, item in items))
    if isinstance(value, list | tuple):
        members = cast("list[object] | tuple[object, ...]", value)
        return (kind, tuple(_value_key(item) for item in members))
    return (kind, value)


def _digest(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=dict)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refs(node: object) -> Iterable[str]:
    if isinstance(node, Mapping):
        for name, child in cast("Mapping[str, object]", node).items():
            if name == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from _refs(child)
    elif isinstance(node, list):
        for child in cast("list[object]", node):
            yield from _refs(child)


def _closure(schemas: SchemaRegistry, urns: Iterable[str]) -> dict[str, Mapping[str, JsonValue]]:
    """The schemas reachable through ``$ref`` from ``urns``, the same set the view generator digests."""
    found: dict[str, Mapping[str, JsonValue]] = {}
    pending = list(urns)
    while pending:
        urn = pending.pop()
        if urn in found:
            continue
        found[urn] = schemas.get(urn)
        pending.extend(ref.split("#")[0] or urn for ref in _refs(found[urn]))
    return dict(sorted(found.items()))


def schema_closure_digest(schemas: SchemaRegistry, urns: Iterable[str]) -> str:
    """The ``SCHEMA_DIGEST`` a generated settings view declares for the schemas of ``urns`` and their refs."""
    return "sha256:" + _digest(_closure(schemas, urns))


def _is_string_schema(schema: object) -> bool:
    return isinstance(schema, dict) and cast("dict[str, object]", schema).get("type") == "string"


def _path_compatible(spec: KeySpec) -> bool:
    """``path = true`` fits a string, an array of strings or a map of strings (REG-12)."""
    schema = spec.value_schema
    kind = spec.value_type
    if kind == "string":
        return True
    if kind == "array":
        return _is_string_schema(schema.get("items"))
    if kind == "object":
        return _is_string_schema(schema.get("additionalProperties"))
    return False


def _enum_of(schema: object) -> tuple[str, ...] | None:
    """The members of a string-enum schema (also one under ``anyOf``), or ``None``."""
    if not isinstance(schema, dict):
        return None
    typed = cast("dict[str, JsonValue]", schema)
    members = typed.get("enum")
    if isinstance(members, list) and all(isinstance(item, str) for item in members):
        return tuple(cast("list[str]", members))
    return None


def _strategy_problem(spec: KeySpec) -> str | None:  # noqa: PLR0911
    """Why the merge strategy does not fit the value type, or ``None`` (REG-07)."""
    try:
        kind = spec.value_type
    except ValueError as exc:
        return str(exc)
    schema = spec.value_schema
    merge = spec.merge
    if merge is MergeStrategy.REPLACE:
        return None
    if merge is MergeStrategy.DEEP_MERGE:
        if kind != "object" or not isinstance(schema.get("additionalProperties"), dict):
            return "deep_merge needs an object with an additionalProperties schema"
        return None
    if merge in (MergeStrategy.APPEND, MergeStrategy.APPEND_UNIQUE, MergeStrategy.UNION):
        return None if kind == "array" else f"{merge.value} needs an array"
    narrow = spec.narrow
    if narrow is None:
        return "narrow needs x-skm.narrow"
    direction = narrow.direction
    if kind == "array":
        return (
            None if direction is NarrowDirection.INTERSECT else "narrow of an array needs direction intersect"
        )
    if kind in ("integer", "number"):
        ok = direction in (NarrowDirection.MIN, NarrowDirection.MAX)
        return None if ok else "narrow of a number needs direction min or max"
    if kind == "boolean":
        ok = direction in (NarrowDirection.AND, NarrowDirection.OR)
        return None if ok else "narrow of a boolean needs direction and or or"
    if kind == "string":
        members = _enum_of(schema)
    elif kind == "object":
        members = _enum_of(schema.get("additionalProperties"))
    else:
        return f"narrow does not apply to {kind}"
    if members is None:
        return "narrow of a string or a map needs a string-enum value schema"
    if narrow.order is None or sorted(narrow.order) != sorted(members) or len(members) != len(set(members)):
        return "narrow.order must be a permutation of all enum members"
    return None


@dataclass(frozen=True, slots=True)
class _Leaf:
    spec: KeySpec
    node: Mapping[str, JsonValue]


class SettingsRegistry:
    """Immutable catalog of settings keys and sections. Build it with ``build``."""

    def __init__(
        self,
        specs: Mapping[str, KeySpec],
        sections: Mapping[str, SectionInfo],
        validators: Mapping[str, SectionValidatorFn],
        compiled: Mapping[str, SchemaValidator],
        digest: str,
    ) -> None:
        self._specs = dict(specs)
        self._sections = dict(sections)
        self._validators = dict(validators)
        self._compiled = dict(compiled)
        self._verdicts: dict[tuple[str, Hashable], tuple[SchemaIssue, ...]] = {}
        self._digest = digest
        self._by_view = {info.view: info for info in self._sections.values()}
        for info in self._sections.values():
            host_view = getattr(info.view, "_HOST_VIEW", None)
            if host_view is not None:
                self._by_view[host_view] = info

    @classmethod
    def build(
        cls,
        schemas: SchemaRegistry,
        section_urns: Iterable[str],
        *,
        views: Mapping[str, type],
        validators: Mapping[str, SectionValidatorFn],
        known_permissions: frozenset[str],
    ) -> "SettingsRegistry":
        builder = _Builder(schemas, views, validators, known_permissions)
        for urn in section_urns:
            builder.add_section(urn)
        return builder.finish()

    def spec(self, key: str) -> KeySpec:
        found = self._specs.get(key)
        if found is None:
            raise ValidationFailed(
                ErrorCode.CONFIG_UNKNOWN_KEY, f"unknown settings key {key!r}", details={"key": key}
            )
        return found

    def find(self, key: str) -> KeySpec | None:
        return self._specs.get(key)

    def keys(self, *, chain: Chain | None = None, section: str | None = None) -> tuple[KeySpec, ...]:
        return tuple(
            spec
            for spec in self._specs.values()
            if (chain is None or spec.chain is chain) and (section is None or spec.section == section)
        )

    def sections(self) -> tuple[SectionInfo, ...]:
        return tuple(self._sections.values())

    def section(self, section_id: str) -> SectionInfo:
        found = self._sections.get(section_id)
        if found is None:
            raise ValidationFailed(
                ErrorCode.CONFIG_UNKNOWN_KEY,
                f"unknown settings section {section_id!r}",
                details={"section": section_id},
            )
        return found

    def section_of_view(self, view: type) -> SectionInfo:
        found = self._by_view.get(view)
        if found is None:
            raise ValidationFailed(
                ErrorCode.CONFIG_UNKNOWN_KEY,
                f"{view.__name__} is not a settings view",
                details={"view": view.__name__},
            )
        return found

    def validator(self, validator_id: str) -> SectionValidatorFn:
        found = self._validators.get(validator_id)
        if found is None:
            raise ValidationFailed(
                ErrorCode.CONFIG_UNKNOWN_KEY,
                f"unknown section validator {validator_id!r}",
                details={"validator": validator_id},
            )
        return found

    def value_issues(self, key: str, value: object) -> tuple[SchemaIssue, ...]:
        """Findings of ``value`` against the schema of ``key`` (compiled once at build time).

        The verdict is a pure function of the key and the value, so it is remembered per value: resolving a
        chain re-checks every key, almost always with the same default or stored value.
        """
        self.spec(key)
        try:
            memo = (key, _value_key(value))
            found = self._verdicts.get(memo)
        except (RecursionError, TypeError):
            # Deep or unhashable inputs still go through the schema validator.
            return self._compiled[key].issues(value)
        if found is None:
            found = self._compiled[key].issues(value)
            if len(self._verdicts) >= _VERDICTS_MAX:
                self._verdicts.clear()
            self._verdicts[memo] = found
        return found

    @property
    def digest(self) -> str:
        return self._digest


class _Builder:
    def __init__(
        self,
        schemas: SchemaRegistry,
        views: Mapping[str, type],
        validators: Mapping[str, SectionValidatorFn],
        known_permissions: frozenset[str],
    ) -> None:
        self._schemas = schemas
        self._views = views
        self._validators = validators
        self._permissions = known_permissions
        self._problems: list[RegistryProblem] = []
        self._specs: dict[str, KeySpec] = {}
        self._compiled: dict[str, SchemaValidator] = {}
        self._sections: dict[str, SectionInfo] = {}
        self._documents: dict[str, Mapping[str, JsonValue]] = {}
        self._ui_orders: dict[tuple[str, str], set[int]] = {}
        # the schema registry's one dialect-free copy serves every leaf schema and both metadata checkers
        self._free_registry = schemas.dialect_free_registry()
        self._section_checker = SchemaValidator(
            {"$ref": f"{KEY_SPEC_URN}#/$defs/section"}, self._free_registry, dialect_free_inputs=True
        )
        self._key_checker = schemas.validator(KEY_SPEC_URN)

    def problem(self, code: str, section: str, key: str | None, message: str) -> None:
        self._problems.append(RegistryProblem(code, section, key, message))

    def add_section(self, urn: str) -> None:
        document = self._schemas.get(urn)
        meta = document.get("x-skm-section")
        label = urn
        if not isinstance(meta, dict):
            self.problem("REG-03", label, None, "x-skm-section is missing")
            return
        issues = self._section_checker.issues(meta)
        if issues:
            self.problem("REG-03", label, None, f"x-skm-section: {issues[0].message}")
            return
        section_id = cast("str", meta["id"])
        if section_id in self._sections:
            self.problem("REG-01", section_id, None, f"section id {section_id!r} is declared twice")
            return
        self._check_section_id(section_id)
        codegen = cast("dict[str, Any]", document.get("x-skm-codegen") or {})
        if cast("dict[str, Any]", codegen.get("python") or {}).get("kind") != "settings_view":
            self.problem("REG-18", section_id, None, "x-skm-codegen.python.kind must be settings_view")
        self._documents[section_id] = document
        declared = {
            cast("str", item["id"]): item for item in cast("list[dict[str, Any]]", meta.get("validators", []))
        }
        leaves: list[KeySpec] = []
        self._walk(document, section_id, cast("str", meta["owner"]), section_id, 0, leaves)
        own_keys = {spec.key for spec in leaves}
        validator_specs = self._check_validators(section_id, declared, leaves, own_keys)
        view = self._views.get(section_id)
        if view is None:
            self.problem("REG-15", section_id, None, "no view class for the section")
            view = object
        elif getattr(view, "SCHEMA_URN", None) != urn:
            self.problem("REG-15", section_id, None, f"{view.__name__}.SCHEMA_URN is not {urn}")
        self._sections[section_id] = SectionInfo(
            id=section_id,
            owner=cast("str", meta["owner"]),
            title=cast("str", meta["title"]),
            schema_urn=urn,
            view=view,
            validators=validator_specs,
            keys=tuple(spec.key for spec in leaves),
        )

    def _check_section_id(self, section_id: str) -> None:
        if section_id in RESERVED_SECTION_IDS:
            self.problem("REG-11", section_id, None, "section id is reserved")
        plugin = _PLUGIN_SECTION.fullmatch(section_id)
        if plugin is not None and plugin.group(1) in RESERVED_PLUGIN_IDS:
            self.problem("REG-11", section_id, None, f"plugin id {plugin.group(1)!r} is reserved")

    def _walk(
        self,
        node: Mapping[str, JsonValue],
        prefix: str,
        owner: str,
        section_id: str,
        depth: int,
        out: list[KeySpec],
    ) -> None:
        properties = node.get("properties")
        if not isinstance(properties, dict):
            return
        for name, child in properties.items():
            path = f"{prefix}.{name}"
            if not isinstance(child, dict):
                self.problem("REG-02", section_id, path, "property schema must be an object")
            elif "x-skm" in child:
                self._add_leaf(path, child, owner, section_id, out)
            elif child.get("type") == "object" and isinstance(child.get("properties"), dict):
                if child.get("additionalProperties") is not False:
                    self.problem("REG-02", section_id, path, "a group needs additionalProperties: false")
                self._walk(child, path, owner, section_id, depth + 1, out)
            else:
                self.problem(
                    "REG-02", section_id, path, "a leaf needs x-skm; a group is an object with properties"
                )

    def _check_path(self, key: str, section_id: str) -> None:
        segments = key.split(".")
        if len(segments) > MAX_KEY_SEGMENTS:
            self.problem(
                "REG-10", section_id, key, f"key has {len(segments)} segments, at most {MAX_KEY_SEGMENTS}"
            )
        if not all(_SEGMENT.fullmatch(segment) for segment in segments):
            self.problem("REG-10", section_id, key, "every segment must match ^[a-z][a-z0-9_]*$")
        if not (key == section_id or key.startswith(section_id + ".")):
            self.problem("REG-10", section_id, key, "key must start with the section id")
        if key in self._specs:
            self.problem("REG-01", section_id, key, "key is declared twice")

    def _add_leaf(
        self, key: str, node: Mapping[str, JsonValue], owner: str, section_id: str, out: list[KeySpec]
    ) -> None:
        self._check_path(key, section_id)
        x_skm = node["x-skm"]
        issues = self._key_checker.issues(x_skm)
        if issues:
            self.problem("REG-03", section_id, key, f"x-skm: {issues[0].pointer or '/'} {issues[0].message}")
            return
        value_schema = {name: value for name, value in node.items() if name not in _LEAF_EXCLUDED}
        default = node.get("default", MISSING)
        try:
            spec = KeySpec.from_metadata(
                key=key,
                section=section_id,
                owner=owner,
                value_schema=value_schema,
                default=default,
                description=cast("str", node.get("description", "")),
                x_skm=cast("Mapping[str, JsonValue]", x_skm),
            )
        except (ValueError, TypeError, KeyError) as exc:
            self.problem("REG-03", section_id, key, f"x-skm: {exc}")
            return
        compiled = SchemaValidator(
            without_dialect(value_schema), self._free_registry, dialect_free_inputs=True
        )
        self._compiled[key] = compiled
        if key not in self._specs:
            self._specs[key] = spec
        out.append(spec)
        self._check_leaf(spec, compiled)

    def _check_leaf(self, spec: KeySpec, compiled: SchemaValidator) -> None:  # noqa: PLR0912
        key, section_id = spec.key, spec.section
        stored = CHAIN_STORED_LEVELS[spec.chain]
        if not spec.levels <= stored:
            extra = sorted(level.value for level in spec.levels - stored)
            self.problem(
                "REG-04", section_id, key, f"levels {extra} are not stored levels of chain {spec.chain.value}"
            )
        if spec.default is not MISSING:
            issues = compiled.issues(spec.default)
            if issues:
                self.problem("REG-05", section_id, key, f"default is invalid: {issues[0].message}")
        elif not spec.nullable:
            self.problem("REG-05", section_id, key, "a key without default must be nullable")
        is_secret_schema = spec.value_schema.get("$ref") == SECRET_REF_URN
        if (spec.sensitivity is Sensitivity.SECRET) != is_secret_schema:
            self.problem(
                "REG-06",
                section_id,
                key,
                "sensitivity secret requires (and only allows) the secret-ref schema",
            )
        reason = _strategy_problem(spec)
        if reason is not None:
            self.problem("REG-07", section_id, key, reason)
        if spec.path:
            try:
                fits = _path_compatible(spec)
            except ValueError:
                fits = False
            if not fits:
                self.problem(
                    "REG-12",
                    section_id,
                    key,
                    "path applies to strings, arrays of strings and maps of strings",
                )
        if spec.lockable and not spec.levels & {Level.INSTANCE, Level.WORKSPACE}:
            self.problem("REG-13", section_id, key, "a lockable key needs instance or workspace in levels")
        if (
            spec.override
            and spec.merge is MergeStrategy.NARROW
            and Level.INSTANCE in spec.levels
            and spec.sensitivity is not Sensitivity.PUBLIC
        ):
            self.problem(
                "REG-14",
                section_id,
                key,
                "override is forbidden for a sensitive narrow key settable at instance",
            )
        if spec.narrow is not None and spec.narrow.unlimited is not MISSING:
            issues = compiled.issues(spec.narrow.unlimited)
            if issues:
                self.problem("REG-16", section_id, key, f"narrow.unlimited is invalid: {issues[0].message}")
        orders = self._ui_orders.setdefault((section_id, spec.ui.group), set())
        if spec.ui.order in orders:
            self.problem(
                "REG-17", section_id, key, f"ui.order {spec.ui.order} repeats in group {spec.ui.group!r}"
            )
        orders.add(spec.ui.order)
        if spec.write_permission is not None and spec.write_permission not in self._permissions:
            self.problem("REG-19", section_id, key, f"unknown permission {spec.write_permission!r}")
        try:
            numeric = spec.value_type in _NUMERIC
        except ValueError:
            numeric = False
        last = spec.key.rsplit(".", 1)[-1]
        if numeric and last.endswith(FORBIDDEN_UNIT_SUFFIXES):
            self.problem("REG-20", section_id, key, f"unit suffix of {last!r} is forbidden")

    def _check_validators(
        self,
        section_id: str,
        declared: Mapping[str, Mapping[str, Any]],
        leaves: list[KeySpec],
        own_keys: set[str],
    ) -> tuple[ValidatorSpec, ...]:
        for spec in leaves:
            for validator_id in spec.validators:
                if validator_id not in declared:
                    self.problem(
                        "REG-08",
                        section_id,
                        spec.key,
                        f"validator {validator_id!r} is not declared by the section",
                    )
                elif spec.key not in declared[validator_id]["keys"]:
                    self.problem(
                        "REG-08", section_id, spec.key, f"validator {validator_id!r} does not list the key"
                    )
        result: list[ValidatorSpec] = []
        for validator_id, item in declared.items():
            if validator_id not in self._validators:
                self.problem("REG-08", section_id, None, f"validator {validator_id!r} has no callable")
            for key in cast("list[str]", item["keys"]):
                if key not in own_keys:
                    self.problem(
                        "REG-08",
                        section_id,
                        key,
                        f"validator {validator_id!r} names a key outside the section",
                    )
            result.append(
                ValidatorSpec(validator_id, tuple(cast("list[str]", item["keys"])), cast("str", item["rule"]))
            )
        return tuple(result)

    def _check_replacements(self) -> None:
        for spec in self._specs.values():
            if spec.deprecated is None or spec.deprecated.replacement is None:
                continue
            target = self._specs.get(spec.deprecated.replacement)
            if target is None:
                self.problem(
                    "REG-09",
                    spec.section,
                    spec.key,
                    f"replacement {spec.deprecated.replacement!r} does not exist",
                )
                continue
            try:
                same = target.value_type == spec.value_type
            except ValueError:
                same = False
            if not same:
                self.problem("REG-09", spec.section, spec.key, "replacement has another type")

    def _check_digests(self) -> None:
        groups: dict[str, list[SectionInfo]] = {}
        for info in self._sections.values():
            if info.view is not object:
                groups.setdefault(info.view.__module__, []).append(info)
        for infos in groups.values():
            expected = schema_closure_digest(self._schemas, (info.schema_urn for info in infos))
            for info in infos:
                declared = getattr(info.view, "SCHEMA_DIGEST", None)
                if declared != expected:
                    self.problem(
                        "REG-15",
                        info.id,
                        None,
                        f"{info.view.__name__}.SCHEMA_DIGEST does not match the schema",
                    )

    def finish(self) -> SettingsRegistry:
        self._check_replacements()
        self._check_digests()
        if self._problems:
            raise InternalError(
                ErrorCode.CONFIG_REGISTRY_INVALID,
                f"settings registry is invalid: {len(self._problems)} problem(s)",
                details={"problems": [problem.to_json() for problem in self._problems]},
            )
        digest = "sha256:" + _digest(
            {info.schema_urn: self._documents[info.id] for info in self._sections.values()}
        )
        return SettingsRegistry(self._specs, self._sections, self._validators, self._compiled, digest)
