"""Stable interpretation, nullable absence and live authority around immutable run snapshots (§B.7).

Donor scenarios: aicore test_model (schema defaults, absence, immutable data), test_maps (field-wise
merge), orch test_authority_monotonic (current authority cannot be weakened by old configuration).
"""

import copy
import json
from dataclasses import replace
from pathlib import Path
from runpy import run_path
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.config.effective import (
    FrozenConfig,
    ProcessConfig,
    normalize_numbers,
    registry_descriptor_digest,
)
from skm.platform.config.keys import Level, copy_json
from skm.platform.config.layers import Contribution
from skm.platform.config.resolver import resolve
from skm.platform.jsonc.canonical import canonical_bytes
from skm.platform.jsonc.digest import digest
from skm.platform.schema.registry import SchemaRegistry

helpers = run_path(str(Path(__file__).with_name("test_resolver.py")))
leaf = helpers["leaf"]
build_registry = helpers["build_registry"]
work_chain = helpers["work_chain"]
host_chain = helpers["host_chain"]
defaults = helpers["defaults"]
stored = helpers["stored"]
ref = helpers["ref"]
layer = helpers["layer"]

PROPERTIES = {
    "rounds": leaf({"type": "integer", "minimum": 1}, default=2, reload="run_frozen"),
    "note": leaf({"type": "string"}, reload="run_frozen"),
    "null_value": leaf({"type": ["string", "null"]}, default=None, reload="run_frozen"),
    "ceiling": leaf(
        {"type": "integer", "minimum": 0}, default=10, merge="narrow", narrow={"direction": "min"}
    ),
    "restart": leaf({"type": "string"}, default="original", reload="restart"),
    "host_restart": leaf(
        {"type": "string"},
        default="host-original",
        reload="restart",
        chain="host",
        levels=["instance", "host"],
    ),
    "refs": leaf(
        {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "secret": {"$ref": "urn:skm:config:secret-ref:v1"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["secret", "enabled"],
            },
        },
        default={},
        merge="deep_merge",
        reload="run_frozen",
    ),
}


def config(registry, *, generation=1, pack_generation=1, entries=None, packs=(), chain=None):
    chain = chain or work_chain(5)
    return resolve(
        registry,
        chain,
        [defaults(registry, chain.kind), *packs, *stored(chain, entries or {})],
        generation=generation,
        pack_generation=pack_generation,
    )


def rehash(document):
    document["digest"] = digest(
        {
            "schema": document["schema"],
            "registry_digest": document["registry_digest"],
            "values": normalize_numbers(document["values"]),
        }
    )
    return document


@pytest.fixture
def registry(tmp_path):
    return build_registry(tmp_path, PROPERTIES)


def test_freeze_only_run_frozen_and_round_trip(registry):
    original = config(
        registry,
        entries={Level.RUN: {"demo.refs": {"hook": {"secret": "secret://env/HOOK", "enabled": True}}}},
    )
    frozen = original.freeze(registry)
    assert set(frozen.values) == {"demo.rounds", "demo.null_value", "demo.refs"}
    assert "demo.note" not in frozen.values
    assert frozen.values["demo.null_value"] is None
    document = frozen.to_document()
    schemas = SchemaRegistry.load_default()
    assert schemas.validator("urn:skm:config:frozen:v1").issues(document) == ()
    loaded = cast("Any", FrozenConfig.from_document(json.loads(json.dumps(document))))
    assert loaded.to_document() == document
    assert loaded.digest == digest(
        {
            "schema": document["schema"],
            "registry_digest": document["registry_digest"],
            "values": normalize_numbers(document["values"]),
        }
    )
    assert "HOOK" not in repr(loaded)
    assert loaded.values["demo.refs"]["hook"]["secret"] == "secret://env/HOOK"
    with pytest.raises(TypeError):
        loaded.values["demo.refs"]["hook"]["secret"] = "literal-secret"
    document["values"]["demo.refs"]["hook"]["secret"] = "changed"
    document["provenance"]["demo.rounds"] = "changed"
    assert loaded.values["demo.refs"]["hook"]["secret"] == "secret://env/HOOK"
    assert loaded.provenance["demo.rounds"] == "default"


def test_new_generation_keeps_frozen_and_current_live_ceiling(registry):
    frozen = config(registry).freeze(registry)
    before = canonical_bytes(normalize_numbers(copy_json(frozen.to_document(), "snapshot")))
    current = config(
        registry,
        generation=2,
        pack_generation=2,
        entries={
            Level.WORKSPACE: {"demo.rounds": 9, "demo.ceiling": 0, "demo.note": "new"},
        },
    )
    overlaid = current.with_overrides(frozen)
    assert overlaid.generation == 2
    assert overlaid.pack_generation == 2
    assert overlaid.get("demo.rounds") == 2
    assert overlaid.get("demo.ceiling") == 0
    assert overlaid.present("demo.note") is False
    frozen_winner = overlaid.provenance("demo.rounds").winner
    live_winner = overlaid.provenance("demo.ceiling").winner
    assert frozen_winner is not None
    assert live_winner is not None
    assert frozen_winner.level is Level.RUN_BUNDLE
    assert live_winner.level is Level.WORKSPACE
    assert canonical_bytes(normalize_numbers(copy_json(frozen.to_document(), "snapshot"))) == before


@pytest.mark.parametrize("change", ["default", "merge", "reload", "schema"])
def test_equal_values_with_different_descriptors_have_different_snapshot_digest(tmp_path, change):
    first = build_registry(tmp_path / "first", PROPERTIES)
    changed = copy.deepcopy(PROPERTIES)
    if change == "default":
        changed["rounds"]["default"] = 3
    elif change == "merge":
        changed["rounds"]["x-skm"].update(merge="narrow", narrow={"direction": "min"})
    elif change == "reload":
        changed["restart"]["x-skm"]["reload"] = "live"
    else:
        changed["rounds"]["maximum"] = 20
    second = build_registry(tmp_path / "second", changed)
    entries = {Level.INSTANCE: {"demo.rounds": 5}}
    old, new = config(first, entries=entries).freeze(first), config(second, entries=entries).freeze(second)
    assert old.values == new.values
    assert old.registry_digest != new.registry_digest
    assert old.digest != new.digest
    with pytest.raises(ValidationFailed) as error:
        config(second).with_overrides(old)
    assert error.value.code is ErrorCode.CONFIG_INVALID
    assert error.value.details["reason"] == "frozen_registry_incompatible"


def test_changed_defaults_and_live_restriction_do_not_rewrite_old_bundle(tmp_path):
    first = build_registry(tmp_path / "first", PROPERTIES)
    frozen = config(first).freeze(first)
    before = json.dumps(frozen.to_document(), sort_keys=True)
    changed = copy.deepcopy(PROPERTIES)
    changed["rounds"]["default"] = 99
    changed["note"]["default"] = "new nullable default"
    second = build_registry(tmp_path / "second", changed)
    current = config(second, generation=3, entries={Level.INSTANCE: {"demo.ceiling": 0}})
    assert current.get("demo.ceiling") == 0
    with pytest.raises(ValidationFailed, match="snapshot"):
        current.with_overrides(frozen)
    assert frozen.values["demo.rounds"] == 2
    assert "demo.note" not in frozen.values
    assert json.dumps(frozen.to_document(), sort_keys=True) == before
    new_bundle = current.freeze(second)
    assert new_bundle.values["demo.rounds"] == 99
    assert new_bundle.digest != frozen.digest


def test_new_required_frozen_key_is_incompatible(tmp_path):
    old = build_registry(tmp_path / "old", PROPERTIES)
    frozen = config(old).freeze(old)
    properties = copy.deepcopy(PROPERTIES)
    properties["added"] = leaf({"type": "integer"}, default=1, reload="run_frozen")
    new = build_registry(tmp_path / "new", properties)
    with pytest.raises(ValidationFailed):
        config(new).with_overrides(frozen)
    # Even a claimed current descriptor cannot hide a missing required key.
    forged = FrozenConfig.from_document(
        rehash(dict(frozen.to_document(), registry_digest=registry_descriptor_digest(new)))
    )
    with pytest.raises(ValidationFailed):
        config(new).with_overrides(forged)


@pytest.mark.parametrize(
    "bad",
    [
        "missing_registry",
        "bad_uuid",
        "negative_generation",
        "bool_generation",
        "unknown_schema",
        "extra",
        "digest",
        "literal_secret",
        "foreign_key",
    ],
)
def test_malformed_or_semantically_incompatible_snapshots_fail_closed(registry, bad):
    document: dict[str, Any] = dict(config(registry).freeze(registry).to_document())
    if bad == "missing_registry":
        del document["registry_digest"]
    elif bad == "bad_uuid":
        document["run_scope_id"] = "not-uuid"
    elif bad == "negative_generation":
        document["generation"] = -1
    elif bad == "bool_generation":
        document["generation"] = True
    elif bad == "unknown_schema":
        document["schema"] = "urn:unknown"
    elif bad == "extra":
        document["unexpected"] = True
    elif bad == "digest":
        document["values"]["demo.rounds"] = 8
    elif bad == "literal_secret":
        document["values"]["demo.refs"] = {"hook": {"secret": "plaintext", "enabled": True}}
        rehash(document)
    else:
        document["values"]["demo.ceiling"] = 100
        rehash(document)
    with pytest.raises(ValidationFailed) as error:
        config(registry).with_overrides(FrozenConfig.from_document(document))
    assert error.value.code is ErrorCode.CONFIG_INVALID
    assert "plaintext" not in str(error.value.details)


def test_unknown_descriptor_is_readable_but_not_executable(registry):
    doc = config(registry).freeze(registry).to_document()
    doc["registry_digest"] = "sha256:" + "0" * 64
    unknown = FrozenConfig.from_document(rehash(doc))
    assert unknown.values["demo.rounds"] == 2
    with pytest.raises(ValidationFailed):
        config(registry).with_overrides(unknown)


def test_freeze_rejects_invalid_partial_foreign_or_wrong_run(registry):
    with pytest.raises(ValidationFailed):
        config(registry, chain=work_chain()).freeze(registry)
    invalid = config(registry, entries={Level.RUN: {"demo.rounds": 0}})
    with pytest.raises(ValidationFailed):
        invalid.freeze(registry)
    partial = resolve(
        registry,
        work_chain(5),
        [defaults(registry), *stored(work_chain(5), {})],
        keys=["demo.rounds"],
        generation=1,
        pack_generation=1,
    )
    with pytest.raises(ValidationFailed):
        partial.freeze(registry)
    frozen = config(registry).freeze(registry)
    with pytest.raises(ValidationFailed):
        config(registry, chain=host_chain()).with_overrides(frozen)
    with pytest.raises(ValidationFailed):
        config(registry).with_overrides(replace(frozen, run_scope_id=helpers["IDS"][Level.PROJECT]))


def test_work_policy_field_merge_lock_unset_and_all_four_frozen_keys():
    real = run_path(str(Path(__file__).with_name("test_registry_all_sections.py")))["real_registry"]()
    prefix = "execution.work_policy."
    role = prefix + "role_intensity"
    verify = prefix + "verification_intensity"
    warn = prefix + "role_warn_seconds"
    repro = prefix + "repro_warn_seconds"
    at = ref(Level.WORKSPACE)
    packs = (layer(ref(Level.PACK, name="policy", priority=1), {role: {"reviewer": "heavy"}}),)
    entries = {
        Level.WORKSPACE: {
            role: Contribution(at, "set", {"executor": "heavy"}, locked=True),
            verify: "heavy",
            warn: {"executor": {"heavy": 4000}},
            repro: {"heavy": 120},
        },
        Level.PROJECT: {role: {"executor": "light", "scout": "light"}},
    }
    effective = config(real, entries=entries, packs=packs)
    roles = cast("dict[str, Any]", effective.get(role))
    assert roles["reviewer"] == "heavy"
    assert roles["executor"] == "heavy"
    assert roles["scout"] == "medium"
    assert effective.provenance(role).locked_by == at
    frozen = effective.freeze(real)
    before = frozen.to_document()
    assert {role, verify, warn, repro} <= frozen.values.keys()
    assert frozen.provenance[role] == "workspace"
    new = config(
        real,
        generation=2,
        pack_generation=2,
        packs=(layer(ref(Level.PACK, name="policy", priority=2), {role: {"reviewer": "light"}}),),
        entries={
            Level.INSTANCE: {
                role: {"executor": "light"},
                verify: "light",
                warn: {"executor": {"heavy": 5000}},
                repro: {"heavy": 150},
            }
        },
    )
    selected = new.with_overrides(frozen)
    for key in (role, verify, warn, repro):
        assert selected.get(key) == frozen.values[key]
    assert frozen.to_document() == before
    # An unset command removes exactly the selected stored contribution, without a merge tombstone.
    reset_entries = {Level.WORKSPACE: {role: {"executor": "heavy"}}}
    assert (
        cast("dict[str, Any]", config(real, entries=reset_entries, packs=packs).get(role))["executor"]
        == "heavy"
    )
    del reset_entries[Level.WORKSPACE][role]
    restored = config(real, entries=reset_entries, packs=packs)
    restored_roles = cast("dict[str, Any]", restored.get(role))
    assert restored_roles["executor"] == "medium"
    assert restored_roles["reviewer"] == "heavy"
    assert restored.provenance(role).locked_by is None
    assert restored.with_overrides(frozen).get(role) == frozen.values[role]


def test_snapshot_float_digest_normalization(tmp_path):
    properties = copy.deepcopy(PROPERTIES)
    properties["ratio"] = leaf({"type": "number"}, default=0.5, reload="run_frozen")
    registry = build_registry(tmp_path, properties)
    frozen = config(registry).freeze(registry)
    assert frozen.values["demo.ratio"] == 0.5
    assert FrozenConfig.from_document(frozen.to_document()).digest == frozen.digest


def test_cross_key_validation_uses_the_selected_frozen_live_slice(tmp_path):
    properties = copy.deepcopy(PROPERTIES)
    properties["rounds"]["default"] = 2
    registry = build_registry(
        tmp_path,
        properties,
        {
            "demo.bounds": (
                ("demo.rounds", "demo.ceiling"),
                lambda values: (
                    "rounds exceeds live ceiling" if values["demo.rounds"] > values["demo.ceiling"] else None
                ),
            )
        },
    )
    frozen = config(registry).freeze(registry)
    current = config(registry, entries={Level.INSTANCE: {"demo.rounds": 5, "demo.ceiling": 3}})
    assert current.invalid_keys()
    restored = current.with_overrides(frozen)
    assert restored.get("demo.rounds") == 2
    assert restored.get("demo.ceiling") == 3
    assert not restored.invalid_keys()
    assert not any(d.code == "CONFIG_INVALID" for d in restored.diagnostics)
    too_strict = config(registry, entries={Level.INSTANCE: {"demo.rounds": 1, "demo.ceiling": 1}})
    assert not too_strict.invalid_keys()
    restricted = too_strict.with_overrides(frozen)
    with pytest.raises(ValidationFailed):
        restricted.get("demo.ceiling")
    expected = {"reason": "validator", "validator": "demo.bounds"}
    control = config(registry, entries={Level.INSTANCE: {"demo.rounds": 2, "demo.ceiling": 1}})
    for key in ("demo.rounds", "demo.ceiling"):
        diagnostic = next(d for d in restricted.diagnostics if d.code == "CONFIG_INVALID" and d.target == key)
        original = next(d for d in control.diagnostics if d.code == "CONFIG_INVALID" and d.target == key)
        assert dict(diagnostic.details) == dict(original.details) == expected
        problem = restricted.invalid_keys()[key]
        assert problem.reason == expected["reason"]
        assert problem.validator == expected["validator"]
        assert problem.blocked_by == ()


def test_algorithm_version_is_part_of_the_registry_descriptor(registry, monkeypatch):
    import importlib

    effective = importlib.import_module("skm.platform.config.effective")
    frozen = config(registry).freeze(registry)
    monkeypatch.setattr(effective, "_ALGORITHMS", {"merge": "unknown-next-version"})
    newer = config(registry).freeze(registry)
    assert frozen.values == newer.values
    assert frozen.registry_digest != newer.registry_digest
    assert frozen.digest != newer.digest
    with pytest.raises(ValidationFailed):
        config(registry).with_overrides(frozen)


@pytest.mark.parametrize("access", ["get", "section", "freeze", "process"])
def test_invalid_nested_secret_is_masked_on_every_snapshot_read_path(tmp_path, access):
    properties = copy.deepcopy(PROPERTIES)
    properties.pop("host_restart")
    if access == "process":
        properties["refs"]["x-skm"]["reload"] = "restart"
    registry = build_registry(tmp_path, properties)
    current = config(
        registry,
        chain=work_chain() if access == "process" else work_chain(5),
        entries={
            Level.INSTANCE: {"demo.refs": {"hook": {"secret": "never-disclose-literal", "enabled": True}}}
        },
    )
    original = copy_json(current.invalid_keys()["demo.refs"].to_json(), "invalid")
    action = {
        "get": lambda: current.get("demo.refs"),
        "section": lambda: current.section(helpers["DemoView"]),
        "freeze": lambda: current.freeze(registry),
        "process": lambda: ProcessConfig.capture(current),
    }[access]
    with pytest.raises(ValidationFailed) as error:
        action()
    assert error.value.code is ErrorCode.CONFIG_INVALID
    assert "never-disclose-literal" not in str(error.value)
    assert "never-disclose-literal" not in json.dumps(copy_json(error.value.details, "details"))
    assert current.invalid_keys()["demo.refs"].to_json() == original
