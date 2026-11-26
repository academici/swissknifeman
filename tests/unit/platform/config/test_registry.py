"""SettingsRegistry: REG-01…REG-20, accessors, and the packaged catalog (settings §B.2, §B.14)."""

import copy
import hashlib
import importlib
import inspect
import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.config.keys import Chain, KeySpec, MergeStrategy
from skm.platform.config.registry import SectionValidatorFn, SettingsRegistry
from skm.platform.schema.locator import default_schema_root
from skm.platform.schema.registry import SchemaRegistry

SECRET_REF = "urn:skm:config:secret-ref:v1"
MODULES = [
    "access",
    "workspace",
    "artifacts",
    "policy",
    "execution",
    "runtimes",
    "extensions",
    "planning",
    "context",
    "integrations",
    "knowledge",
    "learning",
    "exports",
]
NO_VALIDATORS: Mapping[str, SectionValidatorFn] = {}


def x_skm(**changes: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "chain": "work",
        "levels": ["instance", "workspace"],
        "merge": "replace",
        "reload": "live",
        "override": False,
        "sensitivity": "public",
        "portable": True,
        "lockable": True,
        "nullable": False,
        "pack": False,
        "confirm": False,
        "ui": {"group": "g", "order": 1, "widget": "number"},
    }
    meta.update(changes)
    return meta


def leaf(schema: dict[str, Any] | None = None, *, default: Any = 1, **meta: Any) -> dict[str, Any]:
    node: dict[str, Any] = dict(schema or {"type": "integer", "minimum": 0})
    if default is not None:
        node["default"] = default
    node["description"] = "d"
    node["x-skm"] = x_skm(**meta)
    return node


def section(
    name: str = "demo",
    properties: dict[str, Any] | None = None,
    validators: list[dict[str, Any]] | None = None,
    kind: str = "settings_view",
) -> dict[str, Any]:
    meta: dict[str, Any] = {"id": name, "owner": "demo", "title": "Demo"}
    if validators is not None:
        meta["validators"] = validators
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:skm:settings:{name}:v1",
        "type": "object",
        "additionalProperties": False,
        "x-skm-section": meta,
        "x-skm-codegen": {"python": {"module": "m", "class": "V", "kind": kind}},
        "properties": properties if properties is not None else {"size": leaf()},
    }


class Built:
    def __init__(self, tmp_path: Path, documents: list[dict[str, Any]]) -> None:
        root = tmp_path / f"schemas{len(list(tmp_path.glob('schemas*')))}"
        (root / "settings").mkdir(parents=True)
        (root / "config").mkdir()
        for name in ("key-spec", "secret-ref"):
            (root / "config" / f"{name}.v1.json").write_bytes(
                (default_schema_root() / "config" / f"{name}.v1.json").read_bytes()
            )
        for index, document in enumerate(documents):
            (root / "settings" / f"s{index}.v1.json").write_text(json.dumps(document), encoding="utf-8")
        self.schemas = SchemaRegistry.load(root)
        self.documents = documents

    def views(self, digest: str | None = None) -> dict[str, type]:
        closure: dict[str, Any] = {}
        for document in self.documents:
            closure[document["$id"]] = copy.deepcopy(document)
            if SECRET_REF in json.dumps(document):
                closure[SECRET_REF] = dict(self.schemas.get(SECRET_REF))
        text = json.dumps(
            dict(sorted(closure.items())), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        expected = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        return {
            document["x-skm-section"]["id"]: type(
                "View", (), {"SCHEMA_URN": document["$id"], "SCHEMA_DIGEST": digest or expected}
            )
            for document in self.documents
        }

    def build(
        self,
        validators: Mapping[str, SectionValidatorFn] = NO_VALIDATORS,
        permissions: frozenset[str] = frozenset({"hook.manage"}),
        views: Mapping[str, type] | None = None,
    ) -> SettingsRegistry:
        urns = [document["$id"] for document in self.documents]
        return SettingsRegistry.build(
            self.schemas,
            urns,
            views=self.views() if views is None else views,
            validators=validators,
            known_permissions=permissions,
        )


def specs(registry: SettingsRegistry, **filters: Any) -> tuple[KeySpec, ...]:
    return registry.keys(**filters)


def problems_of(tmp_path: Path, documents: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    with pytest.raises(InternalError) as caught:
        Built(tmp_path, documents).build(**kwargs)
    assert caught.value.code is ErrorCode.CONFIG_REGISTRY_INVALID
    return cast("list[dict[str, Any]]", caught.value.details["problems"])


def codes_of(tmp_path: Path, documents: list[dict[str, Any]], **kwargs: Any) -> set[str]:
    return {problem["code"] for problem in problems_of(tmp_path, documents, **kwargs)}


def one(name: str, node: dict[str, Any], **section_args: Any) -> list[dict[str, Any]]:
    return [section(properties={name: node}, **section_args)]


def ok_validator(_values: Mapping[str, JsonValue]) -> str | None:
    return None


def test_valid_section_builds_and_serves_accessors(tmp_path: Path) -> None:
    groups = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "limit": leaf(
                default=2,
                merge="narrow",
                narrow={"direction": "min"},
                ui={"group": "g", "order": 2, "widget": "text"},
            ),
            "host_flag": leaf(
                {"type": "boolean"},
                default=False,
                chain="host",
                levels=["instance", "host"],
                ui={"group": "g", "order": 3, "widget": "text"},
            ),
        },
    }
    built = Built(tmp_path, [section(properties={"size": leaf(), "group": groups})])
    registry = built.build()
    assert [spec.key for spec in specs(registry)] == ["demo.size", "demo.group.limit", "demo.group.host_flag"]
    assert [spec.key for spec in specs(registry, chain=Chain.HOST)] == ["demo.group.host_flag"]
    assert [spec.key for spec in specs(registry, section="demo")] == [spec.key for spec in specs(registry)]
    spec = registry.spec("demo.group.limit")
    assert isinstance(spec, KeySpec)
    assert (spec.merge, spec.owner, spec.section, spec.default) == (MergeStrategy.NARROW, "demo", "demo", 2)
    assert registry.find("demo.nothing") is None
    info = registry.section("demo")
    assert info.keys == tuple(spec.key for spec in specs(registry))
    assert registry.section_of_view(info.view) is info
    assert registry.sections() == (info,)
    assert registry.digest.startswith("sha256:")
    assert registry.digest == built.build().digest
    assert registry.value_issues("demo.size", 3) == ()
    assert registry.value_issues("demo.size", -1)


def test_remembered_value_verdicts_keep_json_types_apart(tmp_path: Path) -> None:
    flag = leaf({"type": "boolean"}, default=False, ui={"group": "g", "order": 2, "widget": "text"})
    registry = Built(tmp_path, [section(properties={"size": leaf(), "flag": flag})]).build()
    for _ in range(2):  # the second round is answered from remembered verdicts
        assert registry.value_issues("demo.size", 1) == ()
        assert registry.value_issues("demo.size", True)  # a boolean is not an integer
        assert registry.value_issues("demo.size", 1.5)
        assert registry.value_issues("demo.size", [1])
        assert registry.value_issues("demo.size", (1,))
        assert registry.value_issues("demo.flag", True) == ()
        assert registry.value_issues("demo.flag", 1)


def test_deep_value_is_validated_even_when_a_cache_key_cannot_be_built(tmp_path: Path) -> None:
    registry = Built(tmp_path, [section()]).build()
    value: JsonValue = []
    for _ in range(600):
        value = [value]
    assert registry.value_issues("demo.size", value)[0].code == "type"


def test_unknown_lookups_are_rejected_with_codes(tmp_path: Path) -> None:
    registry = Built(tmp_path, [section()]).build()
    for call in (
        lambda: registry.spec("demo.missing"),
        lambda: registry.section("missing"),
        lambda: registry.validator("missing"),
        lambda: registry.section_of_view(int),
        lambda: registry.value_issues("demo.missing", 1),
    ):
        with pytest.raises(ValidationFailed) as caught:
            call()
        assert caught.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


def test_reg01_duplicate_section_id_and_duplicate_key(tmp_path: Path) -> None:
    twin = section()
    twin["$id"] = "urn:skm:settings:demo2:v1"
    assert "REG-01" in codes_of(tmp_path, [section(), twin])
    nested = section(
        "plugins",
        {"foo": {"type": "object", "additionalProperties": False, "properties": {"x": leaf()}}},
    )
    plugin = section("plugins.foo", {"x": leaf()})
    plugin["$id"] = "urn:skm:settings:plugins-foo:v1"
    problems = problems_of(tmp_path, [nested, plugin])
    assert any(p["code"] == "REG-01" and p["key"] == "plugins.foo.x" for p in problems)


def test_reg02_leaf_without_x_skm_and_open_group(tmp_path: Path) -> None:
    assert "REG-02" in codes_of(tmp_path, one("bare", {"type": "integer"}))
    open_group = {"type": "object", "properties": {"x": leaf()}}
    assert "REG-02" in codes_of(tmp_path, one("grp", open_group))


def test_reg03_invalid_x_skm_and_section_meta(tmp_path: Path) -> None:
    broken = leaf()
    del broken["x-skm"]["ui"]
    assert "REG-03" in codes_of(tmp_path, one("a", broken))
    unknown = leaf()
    unknown["x-skm"]["surprise"] = True
    assert "REG-03" in codes_of(tmp_path, one("a", unknown))
    no_meta = section()
    del no_meta["x-skm-section"]
    assert "REG-03" in codes_of(tmp_path, [no_meta], views={})
    bad_title = section()
    bad_title["x-skm-section"]["title"] = ""
    assert "REG-03" in codes_of(tmp_path, [bad_title])


def test_reg04_levels_outside_chain(tmp_path: Path) -> None:
    assert "REG-04" in codes_of(tmp_path, one("a", leaf(levels=["instance", "host"])))
    assert "REG-04" in codes_of(tmp_path, one("a", leaf(chain="host", levels=["instance", "project"])))


def test_reg05_default_must_match_schema_and_missing_default_needs_nullable(tmp_path: Path) -> None:
    assert "REG-05" in codes_of(tmp_path, one("a", leaf(default=-5)))
    assert "REG-05" in codes_of(tmp_path, one("a", leaf(default=None)))
    Built(tmp_path, one("a", leaf(default=None, nullable=True))).build()


def test_reg06_secret_iff_secret_ref_schema(tmp_path: Path) -> None:
    ref = {"$ref": SECRET_REF}
    assert "REG-06" in codes_of(tmp_path, one("a", leaf(ref, default=None, nullable=True)))
    assert "REG-06" in codes_of(tmp_path, one("a", leaf(sensitivity="secret")))
    Built(tmp_path, one("a", leaf(ref, default=None, nullable=True, sensitivity="secret"))).build()


@pytest.mark.parametrize(
    ("schema", "meta"),
    [
        ({"type": "integer"}, {"merge": "deep_merge"}),
        ({"type": "object", "additionalProperties": False, "properties": {}}, {"merge": "deep_merge"}),
        ({"type": "integer"}, {"merge": "append"}),
        ({"type": "string"}, {"merge": "append_unique"}),
        ({"type": "boolean"}, {"merge": "union"}),
        ({"type": "integer"}, {"merge": "narrow"}),
        ({"type": "integer"}, {"merge": "narrow", "narrow": {"direction": "and"}}),
        ({"type": "boolean"}, {"merge": "narrow", "narrow": {"direction": "min"}}),
        ({"type": "array", "items": {"type": "string"}}, {"merge": "narrow", "narrow": {"direction": "min"}}),
        ({"type": "string", "enum": ["a", "b", "c"]}, {"merge": "narrow", "narrow": {"order": ["a", "b"]}}),
        ({"type": "string"}, {"merge": "narrow", "narrow": {"order": ["a", "b"]}}),
        (
            {"type": "object", "additionalProperties": {"type": "string", "enum": ["a", "b"]}},
            {"merge": "narrow", "narrow": {"order": ["a", "c"]}},
        ),
    ],
)
def test_reg07_strategy_must_fit_value_type(
    tmp_path: Path, schema: dict[str, Any], meta: dict[str, Any]
) -> None:
    default: Any = {} if schema["type"] == "object" else [] if schema["type"] == "array" else None
    node = leaf(
        schema, default=default if default is not None else ("a" if schema["type"] == "string" else 1), **meta
    )
    if schema["type"] == "boolean":
        node["default"] = True
    if schema["type"] == "string" and "enum" not in schema:
        node["default"] = "a"
    assert "REG-07" in codes_of(tmp_path, one("a", node))


@pytest.mark.parametrize(
    ("schema", "default", "meta"),
    [
        ({"type": "object", "additionalProperties": {"type": "string"}}, {}, {"merge": "deep_merge"}),
        ({"type": "array", "items": {"type": "string"}}, [], {"merge": "union"}),
        (
            {"type": "array", "items": {"type": "string"}},
            [],
            {"merge": "narrow", "narrow": {"direction": "intersect"}},
        ),
        ({"type": "number"}, 1, {"merge": "narrow", "narrow": {"direction": "max"}}),
        ({"type": "boolean"}, True, {"merge": "narrow", "narrow": {"direction": "or"}}),
        ({"type": "string", "enum": ["a", "b"]}, "a", {"merge": "narrow", "narrow": {"order": ["b", "a"]}}),
        (
            {"type": "object", "additionalProperties": {"type": "string", "enum": ["a", "b"]}},
            {},
            {"merge": "narrow", "narrow": {"order": ["a", "b"]}},
        ),
    ],
)
def test_reg07_compatible_strategies_build(
    tmp_path: Path, schema: dict[str, Any], default: Any, meta: dict[str, Any]
) -> None:
    Built(tmp_path, one("a", leaf(schema, default=default, **meta))).build()


def test_reg08_validator_declaration_callable_and_keys(tmp_path: Path) -> None:
    declared = [{"id": "demo.check", "keys": ["demo.a"], "rule": "r"}]
    node = leaf(validators=["demo.check"])
    documents = one("a", node, validators=declared)
    assert "REG-08" in codes_of(tmp_path, documents)  # declared, but no callable
    Built(tmp_path, documents).build({"demo.check": ok_validator})
    assert "REG-08" in codes_of(
        tmp_path, one("a", node), validators={"demo.check": ok_validator}
    )  # undeclared
    foreign = [{"id": "demo.check", "keys": ["demo.a", "other.b"], "rule": "r"}]
    assert "REG-08" in codes_of(
        tmp_path, one("a", node, validators=foreign), validators={"demo.check": ok_validator}
    )
    not_listed = [{"id": "demo.check", "keys": ["demo.b"], "rule": "r"}]
    assert "REG-08" in codes_of(
        tmp_path, one("a", node, validators=not_listed), validators={"demo.check": ok_validator}
    )


def test_reg09_deprecated_replacement(tmp_path: Path) -> None:
    def deprecated(target: str) -> dict[str, Any]:
        return {"since": "2.0", "replacement": target}

    props = {"old": leaf(), "new": leaf(ui={"group": "g", "order": 2, "widget": "text"})}
    props["old"]["x-skm"]["deprecated"] = deprecated("demo.new")
    Built(tmp_path, [section(properties=props)]).build()
    props["old"]["x-skm"]["deprecated"] = deprecated("demo.gone")
    assert "REG-09" in codes_of(tmp_path, [section(properties=props)])
    props["old"]["x-skm"]["deprecated"] = deprecated("demo.text")
    props["text"] = leaf({"type": "string"}, default="a", ui={"group": "g", "order": 3, "widget": "text"})
    assert "REG-09" in codes_of(tmp_path, [section(properties=props)])


@pytest.mark.parametrize("name", ["Bad", "1a", "a-b"])
def test_reg10_segment_pattern(tmp_path: Path, name: str) -> None:
    assert "REG-10" in codes_of(tmp_path, one(name, leaf()))


def test_reg10_depth_and_section_prefix(tmp_path: Path) -> None:
    def group(inner: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False, "properties": inner}

    deep = {"a": group({"b": group({"c": group({"d": leaf()})})})}  # demo.a.b.c.d has 5 segments
    assert "REG-10" in codes_of(tmp_path, [section(properties=deep)])
    Built(tmp_path, [section(properties={"a": group({"b": group({"c": leaf()})})})]).build()
    plugin = section("plugins.foo", {"a": leaf()})
    assert [spec.key for spec in Built(tmp_path, [plugin]).build().keys(chain=None)] == ["plugins.foo.a"]


def test_reg11_reserved_ids(tmp_path: Path) -> None:
    for reserved in ("command", "view", "document"):
        assert "REG-11" in codes_of(tmp_path, [section(reserved)])


@pytest.mark.parametrize("plugin_id", ["allowed", "required", "control_plane_allowed", "override_builtin"])
@pytest.mark.parametrize("suffix", ["", ".extra"])
def test_reg11_reserved_plugin_ids_at_any_nesting(tmp_path: Path, plugin_id: str, suffix: str) -> None:
    name = f"plugins.{plugin_id}{suffix}"
    plugin = section(name)
    plugin["$id"] = f"urn:skm:settings:{name.replace('.', '-').replace('_', '-')}:v1"
    assert "REG-11" in codes_of(tmp_path, [plugin])


def test_reg11_unreserved_plugin_id_builds(tmp_path: Path) -> None:
    for name in ("plugins.demo", "plugins.demo.extra"):
        plugin = section(name)
        plugin["$id"] = f"urn:skm:settings:{name.replace('.', '-')}:v1"
        assert Built(tmp_path, [plugin]).build().section(name).id == name


@pytest.mark.parametrize(
    "node",
    [
        leaf({"type": "integer"}, path=True),
        leaf({"type": "array", "items": {"type": "integer"}}, default=[], path=True),
        leaf(
            {"type": "object", "additionalProperties": {"type": "integer"}},
            default={},
            merge="deep_merge",
            path=True,
        ),
    ],
)
def test_reg12_path_only_for_strings(tmp_path: Path, node: dict[str, Any]) -> None:
    assert "REG-12" in codes_of(tmp_path, one("a", node))


def test_reg12_string_shapes_are_fine(tmp_path: Path) -> None:
    props = {
        "one": leaf({"type": "string"}, default="/a", path=True),
        "many": leaf(
            {"type": "array", "items": {"type": "string"}},
            default=[],
            path=True,
            ui={"group": "g", "order": 2, "widget": "text"},
        ),
        "map": leaf(
            {"type": "object", "additionalProperties": {"type": "string"}},
            default={},
            merge="deep_merge",
            path=True,
            ui={"group": "g", "order": 3, "widget": "text"},
        ),
    }
    Built(tmp_path, [section(properties=props)]).build()


def test_reg13_lockable_needs_shared_level(tmp_path: Path) -> None:
    assert "REG-13" in codes_of(tmp_path, one("a", leaf(levels=["project", "run"], lockable=True)))
    Built(tmp_path, one("a", leaf(levels=["project", "run"], lockable=False))).build()


def test_reg14_override_on_sensitive_instance_narrow(tmp_path: Path) -> None:
    narrow = {"merge": "narrow", "narrow": {"direction": "and"}}
    schema = {"type": "boolean"}
    secretish = leaf(schema, default=True, override=True, sensitivity="internal", **narrow)
    assert "REG-14" in codes_of(tmp_path, one("a", secretish))
    Built(tmp_path, one("a", leaf(schema, default=True, override=True, **narrow))).build()
    Built(
        tmp_path,
        one(
            "a",
            leaf(
                schema,
                default=True,
                override=True,
                sensitivity="internal",
                levels=["project"],
                lockable=False,
                **narrow,
            ),
        ),
    ).build()


def test_reg15_view_class_urn_and_digest(tmp_path: Path) -> None:
    built = Built(tmp_path, [section()])
    assert "REG-15" in codes_of(tmp_path, [section()], views={})
    wrong_urn = type("View", (), {"SCHEMA_URN": "urn:skm:settings:other:v1", "SCHEMA_DIGEST": "x"})
    assert "REG-15" in {p["code"] for p in _problems(built, views={"demo": wrong_urn})}
    problems = _problems(built, views=built.views(digest="sha256:" + "0" * 64))
    assert any(p["code"] == "REG-15" and "SCHEMA_DIGEST" in p["message"] for p in problems)


def _problems(built: Built, **kwargs: Any) -> list[dict[str, Any]]:
    with pytest.raises(InternalError) as caught:
        built.build(**kwargs)
    return cast("list[dict[str, Any]]", caught.value.details["problems"])


def test_reg16_unlimited_must_fit_value_schema(tmp_path: Path) -> None:
    bad = leaf(merge="narrow", narrow={"direction": "min", "unlimited": "none"})
    assert "REG-16" in codes_of(tmp_path, one("a", bad))
    Built(tmp_path, one("a", leaf(merge="narrow", narrow={"direction": "min", "unlimited": 0}))).build()


def test_reg17_ui_order_unique_per_group(tmp_path: Path) -> None:
    props = {"a": leaf(), "b": leaf()}
    assert "REG-17" in codes_of(tmp_path, [section(properties=props)])
    props["b"]["x-skm"]["ui"] = {"group": "other", "order": 1, "widget": "number"}
    Built(tmp_path, [section(properties=props)]).build()


def test_reg18_codegen_kind_must_be_settings_view(tmp_path: Path) -> None:
    assert "REG-18" in codes_of(tmp_path, [section(kind="dataclass")])


def test_reg19_write_permission_must_be_known(tmp_path: Path) -> None:
    node = leaf(write_permission="no.such_right")
    assert "REG-19" in codes_of(tmp_path, one("a", node))
    Built(tmp_path, one("a", node)).build(permissions=frozenset({"no.such_right"}))


@pytest.mark.parametrize("name", ["timeout_s", "size_mb", "size_gb", "size_kb"])
def test_reg20_forbidden_unit_suffixes(tmp_path: Path, name: str) -> None:
    assert "REG-20" in codes_of(tmp_path, one(name, leaf()))


@pytest.mark.parametrize(
    "name",
    [
        "wait_ms",
        "ttl_seconds",
        "ttl_minutes",
        "ttl_hours",
        "ttl_days",
        "max_bytes",
        "max_tokens",
        "max_chars",
        "max_usd",
        "count",
    ],
)
def test_reg20_allowed_unit_suffixes(tmp_path: Path, name: str) -> None:
    Built(tmp_path, one(name, leaf())).build()


def test_reg20_ignores_non_numeric_leaves(tmp_path: Path) -> None:
    Built(tmp_path, one("mode_s", leaf({"type": "string"}, default="a"))).build()


def test_all_problems_are_reported_together(tmp_path: Path) -> None:
    props = {"bad_s": leaf(), "plain": {"type": "integer"}}
    found = problems_of(tmp_path, [section(properties=props, kind="dataclass")])
    assert {"REG-02", "REG-18", "REG-20"} <= {problem["code"] for problem in found}


def _packaged_views() -> dict[str, type]:
    views: dict[str, type] = {}
    names = [f"skm.modules.{name}.settings" for name in MODULES] + ["skm.platform.config.generated.settings"]
    for name in names:
        module = importlib.import_module(name)
        generated = (
            importlib.import_module(name.replace(".settings", ".generated.settings"))
            if "modules" in name
            else module
        )
        mapping = getattr(module, "VIEWS", None)
        if mapping is None:
            mapping = {}
            for _, cls in inspect.getmembers(generated, inspect.isclass):
                section_id = getattr(cls, "SECTION", None)
                if isinstance(section_id, str) and cls.__module__ == generated.__name__:
                    mapping[section_id] = cls
        views.update(mapping)
    return views


def _packaged_validators() -> dict[str, SectionValidatorFn]:
    found: dict[str, SectionValidatorFn] = {}
    for name in MODULES:
        found.update(getattr(importlib.import_module(f"skm.modules.{name}.settings"), "VALIDATORS", {}))
    # not under test here: the hook callback needs runtime sets, plugins.subsets belongs to the platform
    found["integrations.hook_subscriptions"] = ok_validator
    found["plugins.subsets"] = ok_validator
    return found


@cache
def packaged_schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def packaged_registry(permissions: frozenset[str] = frozenset({"hook.manage"})) -> SettingsRegistry:
    schemas = packaged_schemas()
    urns = sorted(urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-section"))
    return SettingsRegistry.build(
        schemas,
        urns,
        views=_packaged_views(),
        validators=_packaged_validators(),
        known_permissions=permissions,
    )


def test_every_packaged_section_builds_without_problems() -> None:
    registry = packaged_registry()
    ids = {info.id for info in registry.sections()}
    assert {
        "access",
        "execution",
        "budgets",
        "worker",
        "checks",
        "integrations",
        "hooks",
        "plugins",
        "storage",
        "ui",
    } <= ids
    assert len(ids) == 26
    assert len(specs(registry)) == len({spec.key for spec in specs(registry)})
    assert registry.spec("hooks.subscriptions").write_permission == "hook.manage"
    assert all(registry.validator(v.id) for info in registry.sections() for v in info.validators)


def test_packaged_catalog_rejects_missing_permission_and_view() -> None:
    schemas = packaged_schemas()
    urns = sorted(urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-section"))
    with pytest.raises(InternalError) as caught:
        SettingsRegistry.build(
            schemas,
            urns,
            views=_packaged_views(),
            validators=_packaged_validators(),
            known_permissions=frozenset(),
        )
    codes = {p["code"] for p in cast("list[dict[str, Any]]", caught.value.details["problems"])}
    assert codes == {"REG-19"}
    views = _packaged_views()
    del views["access"]
    with pytest.raises(InternalError) as caught:
        SettingsRegistry.build(
            schemas,
            urns,
            views=views,
            validators=_packaged_validators(),
            known_permissions=frozenset({"hook.manage"}),
        )
    assert {p["section"] for p in cast("list[dict[str, Any]]", caught.value.details["problems"])} == {
        "access"
    }


def test_packaged_catalog_needs_every_declared_validator_callable() -> None:
    schemas = packaged_schemas()
    urns = sorted(urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-section"))
    validators = {k: v for k, v in _packaged_validators().items() if k != "plugins.subsets"}
    with pytest.raises(InternalError) as caught:
        SettingsRegistry.build(
            schemas,
            urns,
            views=_packaged_views(),
            validators=validators,
            known_permissions=frozenset({"hook.manage"}),
        )
    problems = cast("list[dict[str, Any]]", caught.value.details["problems"])
    assert {p["code"] for p in problems} == {"REG-08"}
    assert all("plugins.subsets" in p["message"] for p in problems)
