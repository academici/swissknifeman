"""Resolver: layer order, levels/ops, deprecated aliases, final schema, MISSING vs null, digest (§B.6).

Ported scenarios (aicore ``test_model.py``): defaults come from the schema, a missing key falls through,
unset without a default removes the value, the merged value is validated again, a forbidden layer and an
unknown key do not apply, resolved values do not alias the inputs and cannot be changed.
"""

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Self, cast
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.config.effective import EffectiveConfig, normalize_numbers, values_digest
from skm.platform.config.keys import MISSING, Chain, Level, MergeStrategy
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SectionValidatorFn, SettingsRegistry
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.validation import check_section_validators, run_section_validators, validate_value
from skm.platform.config.validators import SECTION_URNS, VALIDATORS, VIEWS
from skm.platform.jsonc.digest import digest
from skm.platform.schema.locator import default_schema_root
from skm.platform.schema.registry import SchemaRegistry

SECRET_REF = "urn:skm:config:secret-ref:v1"
WORK_LEVELS = (Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN)
IDS = {level: UUID(int=index + 1) for index, level in enumerate((*WORK_LEVELS, Level.HOST))}


# ---------------------------------------------------------------------------------------------------------
# A small registry built from schema documents (pattern of test_registry.py)


class _Order:
    value = 0


def leaf(schema: dict[str, Any], *, default: Any = MISSING, **meta: Any) -> dict[str, Any]:
    _Order.value += 1
    x_skm: dict[str, Any] = {
        "chain": "work",
        "levels": ["instance", "workspace", "project", "plan", "run"],
        "merge": "replace",
        "reload": "live",
        "override": False,
        "sensitivity": "public",
        "portable": True,
        "lockable": True,
        "nullable": default is MISSING,
        "pack": True,
        "confirm": False,
        "ui": {"group": "g", "order": _Order.value, "widget": "json"},
    }
    x_skm.update(meta)
    node = dict(schema)
    if default is not MISSING:
        node["default"] = default
    node["description"] = "d"
    node["x-skm"] = x_skm
    return node


DEMO: dict[str, Any] = {
    "size": leaf({"type": "integer", "minimum": 0, "maximum": 10}, default=1, override=True),
    "tags": leaf({"type": "array", "items": {"type": "string"}, "maxItems": 3}, default=[]),
    "note": leaf({"type": "string"}),
    "label": leaf({"type": ["string", "null"]}),
    "ratio": leaf({"type": "number"}, default=0.5),
    "old_size": leaf(
        {"type": "integer", "minimum": 0, "maximum": 10},
        default=1,
        deprecated={"replacement": "demo.size", "since": "2.1"},
    ),
    "legacy": leaf({"type": "string"}, default="x", deprecated={"since": "2.1"}),
    "rounds": leaf({"type": "integer", "minimum": 0}, default=2, merge="narrow", narrow={"direction": "min"}),
    "token": leaf({"$ref": SECRET_REF}, sensitivity="secret", portable=False),
    "dir": leaf({"type": "string", "maxLength": 40}, path=True),
    "names": leaf({"type": "array", "items": {"type": "string"}}, default=["~/a", "b"], path=True),
    "plain": leaf({"type": "string"}, default="~/not-a-path"),
    "members": leaf({"type": "array", "items": {"type": "string"}}, default=["a"], merge="union"),
    "access": leaf(
        {"type": "string", "enum": ["open", "contained", "confined"]},
        default="contained",
        merge="narrow",
        narrow={"order": ["open", "contained", "confined"]},
        override=True,
    ),
    "host_only": leaf({"type": "integer"}, default=7, chain="host", levels=["instance", "host"]),
}


class DemoView:
    SCHEMA_URN: ClassVar[str] = "urn:skm:settings:demo:v1"
    SCHEMA_DIGEST: ClassVar[str] = ""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self.values = dict(values)

    @classmethod
    def from_settings(cls, values: Mapping[str, Any]) -> Self:
        return cls(values)


def build_registry(
    tmp_path: Path,
    properties: Mapping[str, Any] = DEMO,
    rules: Mapping[str, tuple[tuple[str, ...], SectionValidatorFn]] | None = None,
) -> SettingsRegistry:
    """``rules``: section validators ``{id: (keys, callback)}`` declared on the demo section."""
    rules = rules or {}
    section: dict[str, Any] = {"id": "demo", "owner": "demo", "title": "Demo"}
    leaves = copy.deepcopy(dict(properties))
    if rules:
        section["validators"] = [
            {"id": key, "keys": list(keys), "rule": "r"} for key, (keys, _fn) in rules.items()
        ]
        for rule, (keys, _fn) in rules.items():
            for key in keys:
                leaves[key.removeprefix("demo.")]["x-skm"].setdefault("validators", []).append(rule)
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:skm:settings:demo:v1",
        "type": "object",
        "additionalProperties": False,
        "x-skm-section": section,
        "x-skm-codegen": {"python": {"module": "m", "class": "V", "kind": "settings_view"}},
        "properties": leaves,
    }
    root = tmp_path / "schemas"
    (root / "settings").mkdir(parents=True)
    (root / "config").mkdir()
    for name in ("key-spec", "secret-ref"):
        (root / "config" / f"{name}.v1.json").write_bytes(
            (default_schema_root() / "config" / f"{name}.v1.json").read_bytes()
        )
    (root / "settings" / "demo.v1.json").write_text(json.dumps(document), encoding="utf-8")
    schemas = SchemaRegistry.load(root)
    closure = {document["$id"]: document, SECRET_REF: dict(schemas.get(SECRET_REF))}
    text = json.dumps(
        dict(sorted(closure.items())), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    DemoView.SCHEMA_DIGEST = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    return SettingsRegistry.build(
        schemas,
        [document["$id"]],
        views={"demo": DemoView},
        validators={key: fn for key, (_keys, fn) in rules.items()},
        known_permissions=frozenset(),
    )


@pytest.fixture
def registry(tmp_path: Path) -> SettingsRegistry:
    return build_registry(tmp_path)


# ---------------------------------------------------------------------------------------------------------
# Layers


def work_chain(depth: int = 1) -> ScopeChain:
    return ScopeChain(
        Chain.WORK, tuple(ScopeRef(level, IDS[level], level.value) for level in WORK_LEVELS[:depth])
    )


def host_chain() -> ScopeChain:
    return ScopeChain(
        Chain.HOST, (ScopeRef(Level.INSTANCE, IDS[Level.INSTANCE]), ScopeRef(Level.HOST, IDS[Level.HOST]))
    )


def ref(level: Level, name: str = "core", priority: int | None = None, source: str = "cli") -> LayerRef:
    if level is Level.PACK:
        return LayerRef(Level.PACK, pack_id=name, pack_priority=priority)
    if level is Level.INVOCATION:
        return LayerRef(Level.INVOCATION, source=source)
    if level is Level.DEFAULT:
        return LayerRef(Level.DEFAULT)
    return LayerRef(level, IDS[level], label=level.value)


def layer(at: LayerRef, entries: Mapping[str, JsonValue | Contribution] | None = None) -> Layer:
    contributions: dict[str, Contribution] = {}
    for key, entry in (entries or {}).items():
        contributions[key] = entry if isinstance(entry, Contribution) else Contribution(at, "set", entry)
    return Layer(at, contributions)


def defaults(registry: SettingsRegistry, chain: Chain = Chain.WORK) -> Layer:
    at = LayerRef(Level.DEFAULT)
    return Layer(
        at,
        {
            spec.key: Contribution(at, "default", cast("JsonValue", spec.default))
            for spec in registry.keys(chain=chain)
            if spec.default is not MISSING
        },
    )


def stored(chain: ScopeChain, entries: Mapping[Level, Mapping[str, JsonValue | Contribution]]) -> list[Layer]:
    return [layer(ref(scope.level), entries.get(scope.level)) for scope in chain.scopes]


def run(registry: SettingsRegistry, chain: ScopeChain, layers: list[Layer], **kwargs: Any) -> EffectiveConfig:
    return resolve(
        registry, chain, layers, generation=kwargs.pop("generation", 1), pack_generation=0, **kwargs
    )


def codes(effective: EffectiveConfig) -> list[str]:
    return [item.code for item in effective.diagnostics]


# ---------------------------------------------------------------------------------------------------------
# Step 1-2: keys and layer order


def test_defaults_come_from_the_schema_and_a_missing_key_falls_through(registry: SettingsRegistry) -> None:
    chain = work_chain(3)
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.WORKSPACE: {"demo.size": 4}})]
    )
    assert effective.get("demo.size") == 4
    assert effective.get("demo.tags") == []
    assert effective.get("demo.ratio") == 0.5
    assert effective.resolution("demo.tags").winner == LayerRef(Level.DEFAULT)
    assert effective.chain is chain
    assert (effective.generation, effective.pack_generation) == (1, 0)
    assert "demo.host_only" not in effective.resolved_keys()


def test_the_full_layer_order_is_accepted_and_nearest_wins(registry: SettingsRegistry) -> None:
    chain = work_chain(2)
    layers = [
        defaults(registry),
        layer(ref(Level.PACK, "a", 0), {"demo.size": 2}),
        layer(ref(Level.PACK, "b", 0), {"demo.size": 3}),
        layer(ref(Level.PACK, "a2", 5), {"demo.size": 4}),
        *stored(chain, {Level.INSTANCE: {"demo.size": 5}, Level.WORKSPACE: {"demo.size": 6}}),
        layer(ref(Level.INVOCATION, source="env"), {"demo.size": 7}),
        layer(ref(Level.INVOCATION, source="config-file:./x.toml"), {"demo.size": 8}),
        layer(ref(Level.INVOCATION, source="cli"), {"demo.size": 9}),
    ]
    effective = run(registry, chain, layers)
    assert effective.get("demo.size") == 9
    statuses = [item.status for item in effective.resolution("demo.size").trace]
    assert statuses == ["shadowed"] * 8 + ["winner"]


@pytest.mark.parametrize(
    "case",
    [
        "default_not_first",
        "pack_priority_descending",
        "pack_tie_not_by_id",
        "pack_twice",
        "stored_scope_missing",
        "stored_scope_extra",
        "stored_wrong_scope_id",
        "invocation_before_stored",
        "cli_before_env",
        "pack_after_stored",
        "provenance_only_level",
        "contribution_of_another_scope",
    ],
)
def test_wrong_layer_order_is_a_programming_error(registry: SettingsRegistry, case: str) -> None:
    chain = work_chain(2)
    base = defaults(registry)
    instance, workspace = stored(chain, {})
    other = UUID(int=99)
    layers: dict[str, list[Layer]] = {
        "default_not_first": [instance, base, workspace],
        "pack_priority_descending": [
            layer(ref(Level.PACK, "a", 5)),
            layer(ref(Level.PACK, "b", 1)),
            instance,
            workspace,
        ],
        "pack_tie_not_by_id": [
            layer(ref(Level.PACK, "b", 1)),
            layer(ref(Level.PACK, "a", 1)),
            instance,
            workspace,
        ],
        "pack_twice": [layer(ref(Level.PACK, "a")), layer(ref(Level.PACK, "a")), instance, workspace],
        "stored_scope_missing": [base, instance],
        "stored_scope_extra": [base, instance, workspace, layer(ref(Level.PROJECT))],
        "stored_wrong_scope_id": [base, instance, layer(LayerRef(Level.WORKSPACE, other))],
        "invocation_before_stored": [base, layer(ref(Level.INVOCATION)), instance, workspace],
        "cli_before_env": [
            base,
            instance,
            workspace,
            layer(ref(Level.INVOCATION)),
            layer(ref(Level.INVOCATION, source="env")),
        ],
        "pack_after_stored": [base, instance, layer(ref(Level.PACK)), workspace],
        "provenance_only_level": [base, instance, workspace, layer(LayerRef(Level.RUN_BUNDLE))],
        "contribution_of_another_scope": [
            base,
            instance,
            Layer(
                ref(Level.WORKSPACE), {"demo.size": Contribution(LayerRef(Level.WORKSPACE, other), "set", 1)}
            ),
        ],
    }
    with pytest.raises(ValueError, match=r"order|exactly|belong|provenance|first|priority|then"):
        run(registry, chain, layers[case])


def test_requested_keys_of_the_other_chain_or_unknown_are_refused(registry: SettingsRegistry) -> None:
    chain = work_chain()
    with pytest.raises(ValidationFailed) as other:
        run(registry, chain, [defaults(registry), *stored(chain, {})], keys=["demo.host_only"])
    assert other.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert other.value.details["key_chain"] == "host"
    with pytest.raises(ValidationFailed) as unknown:
        run(registry, chain, [defaults(registry), *stored(chain, {})], keys=["demo.nope"])
    assert unknown.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


def test_selected_keys_resolve_only_those_and_reading_others_is_refused(registry: SettingsRegistry) -> None:
    chain = work_chain()
    effective = run(registry, chain, [defaults(registry), *stored(chain, {})], keys=["demo.size"])
    assert effective.resolved_keys() == ("demo.size",)
    with pytest.raises(ValidationFailed) as refused:
        effective.get("demo.tags")
    assert refused.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert refused.value.details["reason"] == "not_resolved"
    with pytest.raises(ValidationFailed) as section:
        effective.section(DemoView)
    assert section.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED


def test_selected_keys_bring_the_whole_validator_slice() -> None:
    registry = SettingsRegistry.build(
        SchemaRegistry.load_default(),
        SECTION_URNS,
        views=VIEWS,
        validators=VALIDATORS,
        known_permissions=frozenset(),
    )
    chain = work_chain()
    effective = run(registry, chain, [defaults(registry), *stored(chain, {})], keys=["plugins.required"])
    assert set(effective.resolved_keys()) == {
        "plugins.allowed",
        "plugins.required",
        "plugins.control_plane_allowed",
    }


def test_host_chain_reads_host_keys_and_refuses_work_keys(registry: SettingsRegistry) -> None:
    chain = host_chain()
    effective = run(
        registry, chain, [defaults(registry, Chain.HOST), *stored(chain, {Level.HOST: {"demo.host_only": 8}})]
    )
    assert effective.get("demo.host_only") == 8
    with pytest.raises(ValidationFailed) as refused:
        effective.get("demo.size")
    assert refused.value.details["reason"] == "other_chain"


# ---------------------------------------------------------------------------------------------------------
# Step 3-4: levels, ops, unknown and deprecated keys


def test_forbidden_levels_and_ops_are_ignored_with_diagnostics(registry: SettingsRegistry) -> None:
    chain = work_chain(1)
    layers = [
        defaults(registry),
        *stored(chain, {Level.INSTANCE: {"demo.members": Contribution(ref(Level.INSTANCE), "unset", None)}}),
        layer(ref(Level.INVOCATION), {"demo.tags": ["x"], "demo.size": 3}),
    ]
    effective = run(registry, chain, layers)
    assert effective.get("demo.tags") == []  # override = false: invocation is ignored
    assert effective.get("demo.size") == 3  # override = true
    assert effective.get("demo.members") == ["a"]
    assert {"CONFIG_OVERRIDE_NOT_ALLOWED", "CONFIG_OP_NOT_ALLOWED"} <= set(codes(effective))


def test_unknown_entries_are_ignored_with_a_warning_and_other_chain_entries_silently(
    registry: SettingsRegistry,
) -> None:
    chain = work_chain()
    layers = [
        defaults(registry),
        *stored(chain, {Level.INSTANCE: {"demo.gone": 1, "demo.host_only": 3, "demo.size": 2}}),
    ]
    effective = run(registry, chain, layers)
    unknown = [item for item in effective.diagnostics if item.code == "CONFIG_UNKNOWN_KEY"]
    assert [item.target for item in unknown] == ["demo.gone"]
    assert unknown[0].severity == "warning"
    assert effective.get("demo.size") == 2
    assert not effective.invalid_keys()


def test_other_chain_entries_at_a_level_their_chain_lacks_are_reported(registry: SettingsRegistry) -> None:
    chain = work_chain(3)
    misplaced = run(
        registry,
        chain,
        [
            defaults(registry),
            *stored(chain, {Level.PROJECT: {"demo.host_only": 3}}),
            layer(ref(Level.INVOCATION, source="env"), {"demo.host_only": 4}),  # env serves both chains
        ],
    )
    [note] = [item for item in misplaced.diagnostics if item.code == "CONFIG_SCOPE_NOT_ALLOWED"]
    assert (note.target, note.severity) == ("demo.host_only", "warning")
    assert note.details["layers"] == [ref(Level.PROJECT).to_json()]
    assert not misplaced.invalid_keys()

    host = host_chain()
    found = run(
        registry,
        host,
        [defaults(registry, Chain.HOST), *stored(host, {Level.HOST: {"demo.size": 2, "demo.host_only": 9}})],
    )
    assert found.get("demo.host_only") == 9
    [note] = [item for item in found.diagnostics if item.code == "CONFIG_SCOPE_NOT_ALLOWED"]
    assert note.target == "demo.size"

    selected = run(
        registry,
        chain,
        [defaults(registry), *stored(chain, {Level.PROJECT: {"demo.tags": ["x"]}})],
        keys=["demo.size"],
    )
    assert "CONFIG_SCOPE_NOT_ALLOWED" not in codes(selected)  # same chain, only not requested


def test_deprecated_entries_move_to_the_replacement(registry: SettingsRegistry) -> None:
    chain = work_chain(2)
    layers = [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.old_size": 5}})]
    effective = run(registry, chain, layers)
    assert effective.get("demo.size") == 5
    assert effective.resolution("demo.size").winner == ref(Level.INSTANCE)
    assert effective.get("demo.old_size") == 1  # only its default is left
    [note] = [item for item in effective.diagnostics if item.code == "CONFIG_DEPRECATED_KEY"]
    assert note.target == "demo.old_size"
    assert note.details["replacement"] == "demo.size"


def test_the_replacement_entry_of_the_same_layer_wins_over_the_alias(registry: SettingsRegistry) -> None:
    chain = work_chain(2)
    layers = [
        defaults(registry),
        *stored(
            chain,
            {Level.INSTANCE: {"demo.old_size": 5, "demo.size": 6}, Level.WORKSPACE: {"demo.old_size": 4}},
        ),
    ]
    effective = run(registry, chain, layers)
    assert effective.get("demo.size") == 4  # the nearer alias entry still applies
    trace = [
        (item.contribution.layer.level, item.contribution.value)
        for item in effective.resolution("demo.size").trace
    ]
    assert trace == [(Level.DEFAULT, 1), (Level.INSTANCE, 6), (Level.WORKSPACE, 4)]
    [note] = [item for item in effective.diagnostics if item.code == "CONFIG_DEPRECATED_KEY"]
    assert note.details["ignored"] == [ref(Level.INSTANCE).to_json()]


def test_a_deprecated_key_without_replacement_keeps_its_entries(registry: SettingsRegistry) -> None:
    chain = work_chain()
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.legacy": "y"}})]
    )
    assert effective.get("demo.legacy") == "y"
    [note] = [item for item in effective.diagnostics if item.code == "CONFIG_DEPRECATED_KEY"]
    assert note.details["replacement"] is None


def test_deprecated_aliases_follow_a_chain_of_replacements(tmp_path: Path) -> None:
    properties = dict(DEMO)
    properties["older"] = leaf(
        {"type": "integer"}, default=0, deprecated={"since": "2.0", "replacement": "demo.old_size"}
    )
    registry = build_registry(tmp_path, properties)
    chain = work_chain()
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.older": 3}})]
    )
    assert effective.get("demo.size") == 3


def test_narrow_scenario_of_the_explain_example(registry: SettingsRegistry) -> None:
    chain = work_chain(4)
    workspace = ref(Level.WORKSPACE)
    layers = [
        defaults(registry),
        layer(ref(Level.PACK, "example-overlay", 10), {"demo.rounds": 3}),
        *stored(
            chain,
            {
                Level.INSTANCE: {"demo.rounds": 4},
                Level.WORKSPACE: {"demo.rounds": Contribution(workspace, "set", 3, locked=True)},
                Level.PROJECT: {"demo.rounds": 5},
                Level.PLAN: {"demo.rounds": 1},
            },
        ),
    ]
    effective = run(registry, chain, layers)
    provenance = effective.provenance("demo.rounds")
    assert effective.get("demo.rounds") == 3
    assert provenance.winner == workspace
    assert provenance.locked_by == workspace
    assert [(item.status, item.reason) for item in provenance.trace] == [
        ("shadowed", None),
        ("shadowed", None),
        ("used", None),
        ("winner", None),
        ("ignored", "locked_above"),
        ("ignored", "locked_above"),
    ]
    assert provenance.to_json()["locked_by"] == workspace.to_json()


def _statuses(effective: EffectiveConfig, key: str) -> list[tuple[str, str, str | None]]:
    return [
        (item.contribution.layer.display, item.status, item.reason)
        for item in effective.resolution(key).trace
    ]


@pytest.mark.parametrize(
    ("near", "env"),
    [
        ({"demo.access": "open"}, None),
        ({"demo.access": Contribution(ref(Level.PROJECT), "unset", None)}, None),
        ({}, "open"),
        ({"demo.access": Contribution(ref(Level.PROJECT), "unset", None)}, "open"),
    ],
    ids=["project_open", "project_unset", "environment_open", "project_unset_and_environment_open"],
)
def test_an_authority_ceiling_survives_project_resets_and_environment_overrides(
    registry: SettingsRegistry, near: Mapping[str, JsonValue | Contribution], env: str | None
) -> None:
    # ported scenario: orch test_authority_monotonic ACCESS_WEAKENINGS
    chain = work_chain(3)
    layers = [
        defaults(registry),
        *stored(chain, {Level.INSTANCE: {"demo.access": "confined"}, Level.PROJECT: near}),
    ]
    if env is not None:
        layers.append(layer(ref(Level.INVOCATION, source="env"), {"demo.access": env}))
    effective = run(registry, chain, layers)
    assert effective.get("demo.access") == "confined"
    assert effective.resolution("demo.access").winner == ref(Level.INSTANCE)
    reasons = {
        reason for _label, status, reason in _statuses(effective, "demo.access") if status == "ignored"
    }
    assert reasons <= {"narrowing_violation", "op_not_allowed"}
    assert reasons
    assert not effective.invalid_keys()


def test_without_an_explicit_ceiling_only_shared_and_override_levels_may_widen_the_base(
    registry: SettingsRegistry,
) -> None:
    chain = work_chain(3)
    project = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.PROJECT: {"demo.access": "open"}})]
    )
    assert project.get("demo.access") == "contained"  # base value, not a free choice for the project
    assert _statuses(project, "demo.access")[-1] == ("project", "ignored", "narrowing_violation")
    assert "CONFIG_NARROWING_VIOLATION" in codes(project)
    workspace = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.WORKSPACE: {"demo.access": "open"}})]
    )
    assert workspace.get("demo.access") == "open"  # a shared level starts the chain (§B.5.3 step 2)
    stricter = run(
        registry,
        chain,
        [
            defaults(registry),
            *stored(
                chain, {Level.WORKSPACE: {"demo.access": "open"}, Level.PROJECT: {"demo.access": "confined"}}
            ),
            layer(ref(Level.INVOCATION, source="cli"), {"demo.access": "contained"}),
        ],
    )
    assert stricter.get("demo.access") == "confined"  # nearer levels only tighten


def test_a_lock_holds_against_stricter_and_wider_invocation(registry: SettingsRegistry) -> None:
    chain = work_chain(2)
    locked = Contribution(ref(Level.INSTANCE), "set", "contained", locked=True)
    for value in ("open", "confined"):
        effective = run(
            registry,
            chain,
            [
                defaults(registry),
                *stored(chain, {Level.INSTANCE: {"demo.access": locked}}),
                layer(ref(Level.INVOCATION, source="cli"), {"demo.access": value}),
            ],
        )
        assert effective.get("demo.access") == "contained"
        assert _statuses(effective, "demo.access")[-1] == ("cli", "ignored", "locked_above")
        assert effective.provenance("demo.access").locked_by == ref(Level.INSTANCE)


def test_union_members_and_number_ceilings_cannot_be_removed_or_raised(registry: SettingsRegistry) -> None:
    # ported scenarios: test_unset_does_not_remove_extra_gates_or_lower_confidence, project weakening
    chain = work_chain(5)
    unset = Contribution(ref(Level.PROJECT), "unset", None)
    effective = run(
        registry,
        chain,
        [
            defaults(registry),
            *stored(
                chain,
                {
                    Level.INSTANCE: {"demo.members": ["gate"], "demo.rounds": 4},
                    Level.PROJECT: {"demo.members": unset, "demo.rounds": unset},
                    Level.PLAN: {"demo.members": [], "demo.rounds": 5},
                    Level.RUN: {"demo.rounds": 3},
                },
            ),
            layer(ref(Level.INVOCATION, source="cli"), {"demo.members": [], "demo.rounds": 9}),
        ],
    )
    assert effective.get("demo.members") == ["a", "gate"]
    assert effective.get("demo.rounds") == 3
    assert ("project", "ignored", "op_not_allowed") in _statuses(effective, "demo.members")
    assert ("cli", "ignored", "override_not_allowed") in _statuses(effective, "demo.members")
    assert ("plan", "ignored", "narrowing_violation") in _statuses(effective, "demo.rounds")
    assert ("project", "ignored", "op_not_allowed") in _statuses(effective, "demo.rounds")


# ---------------------------------------------------------------------------------------------------------
# Step 5-6: paths and the final schema


def test_the_merged_value_is_validated_again(registry: SettingsRegistry) -> None:
    chain = work_chain(2)
    append = Contribution(ref(Level.WORKSPACE), "append", ["c", "d"])
    layers = [
        defaults(registry),
        *stored(chain, {Level.INSTANCE: {"demo.tags": ["a", "b"]}, Level.WORKSPACE: {"demo.tags": append}}),
    ]
    effective = run(registry, chain, layers)
    problem = effective.invalid_keys()["demo.tags"]
    assert problem.reason == "schema"
    assert problem.provenance.winner == ref(Level.WORKSPACE)
    assert effective.resolution("demo.tags").value == ["a", "b", "c", "d"]
    with pytest.raises(ValidationFailed) as refused:
        effective.get("demo.tags")
    assert refused.value.code is ErrorCode.CONFIG_INVALID
    assert refused.value.details["reason"] == "schema"
    assert cast("Any", refused.value.details)["provenance"]["winner"] == ref(Level.WORKSPACE).to_json()


def test_an_out_of_range_value_is_invalid_not_clamped(registry: SettingsRegistry) -> None:
    chain = work_chain()
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.size": 11}})]
    )
    assert effective.invalid_keys()["demo.size"].issues
    with pytest.raises(ValidationFailed):
        effective.present("demo.size")


def test_path_keys_are_expanded_before_validation(registry: SettingsRegistry) -> None:
    chain = work_chain()
    home = "/home/someone"

    def expand(text: str) -> str:
        return text.replace("~", home, 1) if text.startswith("~") else text

    effective = run(
        registry,
        chain,
        [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.dir": "~/x"}})],
        expand=expand,
    )
    assert effective.get("demo.dir") == "/home/someone/x"
    assert effective.get("demo.names") == ["/home/someone/a", "b"]
    assert effective.get("demo.plain") == "~/not-a-path"
    # the stored contribution keeps the unexpanded text
    assert effective.resolution("demo.dir").trace[-1].contribution.value == "~/x"
    too_long = run(
        registry,
        chain,
        [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.dir": "~/" + "y" * 30}})],
        expand=expand,
    )
    assert too_long.invalid_keys()["demo.dir"].reason == "schema"


def test_a_failing_path_expansion_makes_only_that_key_invalid(registry: SettingsRegistry) -> None:
    chain = work_chain()

    def expand(text: str) -> str:
        raise KeyError(text)

    effective = run(
        registry,
        chain,
        [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.dir": "${nope}"}})],
        expand=expand,
    )
    assert effective.invalid_keys()["demo.dir"].issues[0]["code"] == "path"
    assert set(effective.invalid_keys()) == {"demo.dir", "demo.names"}
    assert effective.get("demo.size") == 1


# ---------------------------------------------------------------------------------------------------------
# MISSING differs from JSON null


def test_missing_nullable_key_is_absent_and_differs_from_null(registry: SettingsRegistry) -> None:
    chain = work_chain()
    absent = run(registry, chain, [defaults(registry), *stored(chain, {})])
    null = run(registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.label": None}})])
    assert absent.present("demo.label") is False
    assert absent.get("demo.label") is None
    assert absent.resolution("demo.label").value is MISSING
    assert null.present("demo.label") is True
    assert null.get("demo.label") is None
    assert null.resolution("demo.label").value is None
    assert absent.digest != null.digest
    assert not absent.invalid_keys()
    assert not null.invalid_keys()


def test_null_is_a_value_checked_by_the_schema(registry: SettingsRegistry) -> None:
    chain = work_chain()
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.note": None}})]
    )
    assert effective.invalid_keys()["demo.note"].reason == "schema"
    absent = run(registry, chain, [defaults(registry), *stored(chain, {})])
    assert absent.present("demo.note") is False


def test_unset_without_default_removes_the_value(registry: SettingsRegistry) -> None:
    chain = work_chain(2)
    unset = Contribution(ref(Level.WORKSPACE), "unset", None)
    effective = run(
        registry,
        chain,
        [
            defaults(registry),
            *stored(chain, {Level.INSTANCE: {"demo.note": "a"}, Level.WORKSPACE: {"demo.note": unset}}),
        ],
    )
    assert effective.present("demo.note") is False


def test_required_key_without_any_value_is_invalid_missing(registry: SettingsRegistry) -> None:
    chain = work_chain()
    effective = run(registry, chain, stored(chain, {}))  # no default layer
    problem = effective.invalid_keys()["demo.size"]
    assert problem.reason == "missing"
    with pytest.raises(ValidationFailed) as refused:
        effective.present("demo.size")  # absence of a required key is never "not present"
    assert refused.value.details["reason"] == "missing"
    assert effective.present("demo.note") is False  # nullable: absence is valid
    assert "CONFIG_INVALID" in codes(effective)
    assert next(d for d in effective.diagnostics if d.code == "CONFIG_INVALID").severity == "error"


SINGLE_CHAIN = {name: node for name, node in DEMO.items() if name != "host_only"}  # section() needs one chain


def dumped(value: object) -> str:
    """JSON text of a document that may hold read-only mappings and tuples."""
    return json.dumps(value, default=lambda item: dict(item) if isinstance(item, Mapping) else list(item))


def test_a_secret_reference_is_read_back_as_the_reference(tmp_path: Path) -> None:
    registry = build_registry(tmp_path, SINGLE_CHAIN)
    chain = work_chain()
    good = run(
        registry,
        chain,
        [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.token": "secret://env/API_TOKEN"}})],
    )
    assert good.get("demo.token") == "secret://env/API_TOKEN"
    assert not good.invalid_keys()
    assert good.section(DemoView).values["demo.token"] == "secret://env/API_TOKEN"


def test_only_a_nullable_absence_reaches_a_validator_as_none(tmp_path: Path) -> None:
    seen: list[dict[str, JsonValue]] = []

    def pair(values: Mapping[str, JsonValue]) -> str | None:
        seen.append(dict(values))
        too_small = cast("int", values["demo.size"]) < 2
        return "note needs size >= 2" if values["demo.note"] is not None and too_small else None

    registry = build_registry(tmp_path, rules={"demo.pair": (("demo.note", "demo.size"), pair)})
    assert registry.spec("demo.note").nullable
    assert not registry.spec("demo.size").nullable

    assert run_section_validators(registry, {"demo.size": 1}, ["demo"]) == ()  # absent nullable → None
    assert seen[-1] == {"demo.note": None, "demo.size": 1}
    assert run_section_validators(registry, {"demo.note": "n", "demo.size": 1}, ["demo"]) == (
        ("demo.pair", "note needs size >= 2"),
    )
    calls = len(seen)
    [(validator, message)] = run_section_validators(registry, {"demo.note": "n"}, ["demo"])
    assert validator == "demo.pair"
    assert "demo.size" in message
    [finding] = check_section_validators(registry, {"demo.note": MISSING, "demo.size": MISSING}, ["demo"])
    assert finding.blocked_by == ("demo.size",)  # explicit MISSING of a required key blocks too
    assert len(seen) == calls

    chain = work_chain()
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.note": "n"}})]
    )
    assert effective.invalid_keys()["demo.note"].validator == "demo.pair"
    assert effective.get("demo.tags") == []  # other keys of the section stay readable
    absent = run(registry, chain, [defaults(registry), *stored(chain, {})])
    assert not absent.invalid_keys()
    assert seen[-1] == {"demo.note": None, "demo.size": 1}


@pytest.mark.parametrize(
    "leaked", ["plain-text-SeCrEt", 4242, ["sk-SeCrEt"]], ids=["text", "number", "array"]
)
def test_a_plaintext_secret_is_invalid_and_quoted_nowhere(tmp_path: Path, leaked: JsonValue) -> None:
    # settings §A.5 R6: the text of an error never contains the rejected secret value
    registry = build_registry(tmp_path, SINGLE_CHAIN)
    chain = work_chain()
    needles = {"SeCrEt", "4242"}
    bad = run(registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.token": leaked}})])

    def clean(text: str) -> None:
        assert not any(item in text for item in needles), text

    problem = bad.invalid_keys()["demo.token"]
    assert problem.reason == "schema"
    assert problem.issues
    assert all("secret_ref_required" in str(issue["message"]) for issue in problem.issues)
    assert {str(issue["code"]) for issue in problem.issues} <= {"type", "pattern"}  # safe structure is kept
    clean(problem.message)
    clean(dumped(problem.to_json()))
    assert problem.provenance.winner == ref(Level.INSTANCE)  # layers are kept, values are not
    assert [item.contribution.layer for item in problem.provenance.trace] == [ref(Level.INSTANCE)]
    assert [item.code for item in bad.diagnostics] == ["CONFIG_INVALID"]
    for item in bad.diagnostics:
        clean(item.message)
        clean(dumped(item.details))
    for read in (
        lambda: bad.get("demo.token"),
        lambda: bad.present("demo.token"),
        lambda: bad.section(DemoView),
    ):
        with pytest.raises(ValidationFailed) as refused:
            read()
        assert refused.value.code is ErrorCode.CONFIG_INVALID
        clean(str(refused.value))
        clean(dumped(refused.value.details))
    assert bad.get("demo.size") == 1  # only the secret key is refused
    direct = validate_value(registry, "demo.token", leaked)
    assert direct
    for issue in direct:
        clean(issue.message)
        clean(dumped(issue.to_json()))
    # a public key keeps the schema message with its value
    assert "1 is not of type" in validate_value(registry, "demo.note", 1)[0].message


# ---------------------------------------------------------------------------------------------------------
# Immutability and digest


def test_resolved_values_do_not_alias_the_inputs_and_are_immutable(registry: SettingsRegistry) -> None:
    chain = work_chain()
    tags: list[JsonValue] = ["a"]
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.tags": tags}})]
    )
    tags.append("b")
    value = effective.get("demo.tags")
    assert value == ["a"]
    with pytest.raises(TypeError):
        cast("Any", value).append("c")


def test_digest_covers_valid_present_values_and_normalizes_numbers(registry: SettingsRegistry) -> None:
    chain = work_chain()
    as_float = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.ratio": 2.5}})]
    )
    as_text = values_digest({**_valid_values(as_float), "demo.ratio": "2.5"})
    assert as_float.digest == as_text  # float → repr string (§B.6 step 8), no TypeError from canonical JSON
    assert as_float.digest.startswith("sha256:")
    assert as_float.digest != run(registry, chain, [defaults(registry), *stored(chain, {})]).digest
    invalid = run(registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.size": 11}})])
    without = run(
        registry,
        chain,
        [defaults(registry), *stored(chain, {})],
        keys=[k for k in invalid.resolved_keys() if k != "demo.size"],
    )
    assert invalid.digest == without.digest  # an invalid key does not contribute
    same = run(registry, chain, [defaults(registry), *stored(chain, {})], generation=9)
    assert same.digest == run(registry, chain, [defaults(registry), *stored(chain, {})]).digest


def test_number_normalization_follows_the_canonical_contract() -> None:
    with pytest.raises(TypeError):
        digest({"k": 0.5})  # public canonical JSON refuses floats
    assert normalize_numbers({"a": [1.0, 0.5, -0.0, True, 3, None], "b": 1e300, "c": "secret://env/X"}) == {
        "a": ["1.0", "0.5", "-0.0", True, 3, None],
        "b": "1e+300",
        "c": "secret://env/X",
    }
    assert values_digest({"k": 0.5}) == digest({"k": "0.5"})
    assert values_digest({"k": 20.0}) == digest({"k": "20.0"})
    assert values_digest({"k": True}) != values_digest({"k": 1})
    with pytest.raises(TypeError):
        normalize_numbers(float("nan"))


def _valid_values(effective: EffectiveConfig) -> dict[str, JsonValue]:
    return {
        key: effective.get(key)
        for key in effective.resolved_keys()
        if key not in effective.invalid_keys() and effective.present(key)
    }


def test_strategy_metadata_is_the_registry_one(registry: SettingsRegistry) -> None:
    assert registry.spec("demo.members").merge is MergeStrategy.UNION
    chain = work_chain()
    effective = run(
        registry, chain, [defaults(registry), *stored(chain, {Level.INSTANCE: {"demo.members": ["b"]}})]
    )
    assert effective.get("demo.members") == ["a", "b"]
    assert "EffectiveConfig(chain=work" in repr(effective)
