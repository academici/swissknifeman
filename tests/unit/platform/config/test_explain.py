"""Schema, canonical example and diagnostic-only history for explain (§B.8)."""

import copy
import json
from functools import lru_cache
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.errors import ValidationFailed
from skm.platform.config.effective import FrozenConfig
from skm.platform.config.explain import build_explain as _build_explain
from skm.platform.config.explain import render_explain_text
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.schema.registry import SchemaRegistry

h = run_path(str(Path(__file__).with_name("test_frozen.py")))
# JSON field assertions below are paired with full schema validation.
build_explain = cast("Any", _build_explain)


@lru_cache(maxsize=1)
def validator():
    return SchemaRegistry.load_default().validator("urn:skm:config:explain:v1")


def test_json_matches_real_example_and_text_golden():
    # The example intentionally contains partial layer metadata, so render it directly; the resolver
    # regression below checks its semantic statuses using complete, validated LayerRefs.
    example = json.loads(
        Path("tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json").read_text()
    )
    assert validator().issues(example) == ()
    report = copy.deepcopy(example)
    report["keys"] = report["keys"][:2]
    golden = Path("tests/fixtures/corpus/examples/config/explain.txt").read_text().splitlines()[1:-2]
    actual = render_explain_text(report).splitlines()
    assert actual == golden


def test_resolved_narrow_explain_has_all_contributions_reasons_and_base(tmp_path):
    properties = copy.deepcopy(h["PROPERTIES"])
    properties["rounds"]["x-skm"].update(merge="narrow", narrow={"direction": "min"})
    registry = h["build_registry"](tmp_path, properties)
    workspace = h["ref"](Level.WORKSPACE)
    entries = {
        Level.INSTANCE: {"demo.rounds": 4},
        Level.WORKSPACE: {"demo.rounds": Contribution(workspace, "set", 3, locked=True)},
        Level.PROJECT: {"demo.rounds": 5},
        Level.PLAN: {"demo.rounds": 1},
    }
    pack = h["layer"](h["ref"](Level.PACK, name="example-overlay", priority=10), {"demo.rounds": 3})
    effective = h["config"](registry, generation=42, pack_generation=3, entries=entries, packs=(pack,))
    report = build_explain(effective, keys=["demo.rounds"])
    assert validator().issues(report) == ()
    key = report["keys"][0]
    assert key["value"] == 3
    assert key["base"]["level"] == "instance"
    assert key["locked_by"]["level"] == "workspace"
    assert [c["status"] for c in key["contributions"]] == [
        "shadowed",
        "shadowed",
        "used",
        "winner",
        "ignored",
        "ignored",
    ]
    assert [c.get("reason") for c in key["contributions"]][-2:] == ["locked_above", "locked_above"]
    assert key["diagnostics"][0]["code"] == "CONFIG_LOCKED"
    assert [r["level"] for r in report["chain"]] == [
        "default",
        "pack",
        "instance",
        "workspace",
        "project",
        "plan",
        "run",
    ]
    assert "starts the narrowing chain" in render_explain_text(report)
    assert "locked above (workspace)" in render_explain_text(report)
    assert build_explain(effective, keys=["demo.restart"], include_defaults_only=False)["keys"] == []
    with pytest.raises(ValidationFailed):
        build_explain(effective, keys=["demo.host_restart"])


def test_historical_unknown_descriptor_redacts_values_and_provenance_and_blocks_execution(tmp_path):
    registry = h["build_registry"](tmp_path, h["PROPERTIES"])
    effective = h["config"](
        registry,
        entries={Level.RUN: {"demo.refs": {"hook": {"secret": "secret://env/HOOK", "enabled": True}}}},
    )
    frozen = effective.freeze(registry)
    known = build_explain(frozen, registry=registry)
    assert known["interpretation"] == "known"
    assert next(k for k in known["keys"] if k["key"] == "demo.note")["present"] is False
    document = frozen.to_document()
    document["registry_digest"] = "sha256:" + "0" * 64
    unknown = FrozenConfig.from_document(h["rehash"](document))
    original = unknown.to_document()
    for descriptor in (None, registry):
        report = build_explain(unknown, registry=descriptor)
        assert validator().issues(report) == ()
        assert report["interpretation"] == "unknown"
        assert report["digest"] == original["digest"]
        assert report["registry_digest"] == original["registry_digest"]
        assert report["snapshot_schema"] == original["schema"]
        for key in report["keys"]:
            assert "value" not in key
            assert "provenance" not in key
            assert key["contributions"] == []
            assert key["merge"] is key["reload"] is key["sensitivity"] is None
        assert "secret://env/HOOK" not in json.dumps(report)
        assert "interpretation unknown" in render_explain_text(report)
        assert f"registry {original['registry_digest']}" in render_explain_text(report)
        assert f"snapshot {original['schema']}" in render_explain_text(report)
        assert "provenance run" not in render_explain_text(report)
        assert report["keys"] == []
    assert unknown.to_document() == original
    with pytest.raises(ValidationFailed):
        effective.with_overrides(unknown)


def test_new_default_live_ceiling_and_work_policy_are_separate_from_saved_explain(tmp_path):
    registry = h["build_registry"](tmp_path / "old", h["PROPERTIES"])
    frozen = h["config"](registry).freeze(registry)
    before = frozen.to_document()
    properties = copy.deepcopy(h["PROPERTIES"])
    properties["rounds"]["default"] = 99
    new = h["build_registry"](tmp_path / "new", properties)
    current = h["config"](new, generation=2, entries={Level.INSTANCE: {"demo.ceiling": 0}})
    history = build_explain(frozen, registry=new)
    assert history["interpretation"] == "unknown"
    assert history["keys"] == []
    live = build_explain(current, keys=["demo.ceiling"])["keys"][0]
    assert live["value"] == 0
    assert live["reload"] == "live"
    assert frozen.to_document() == before
    with pytest.raises(ValidationFailed):
        current.with_overrides(frozen)


def test_secret_metadata_is_safe_in_values_and_invalid_contributions(tmp_path):
    properties = copy.deepcopy(h["PROPERTIES"])
    properties["token"] = h["leaf"](
        {"$ref": "urn:skm:config:secret-ref:v1"}, reload="run_frozen", sensitivity="secret"
    )
    registry = h["build_registry"](tmp_path, properties)
    effective = h["config"](
        registry,
        entries={
            Level.INSTANCE: {
                "demo.token": "secret://file/private/token",
                "demo.refs": {"hook": {"secret": "secret://env/HOOK", "enabled": True}},
            }
        },
    )
    report = build_explain(effective, keys=["demo.token", "demo.refs"])
    assert validator().issues(report) == ()
    assert report["keys"][0]["value"] == "secret://file/private/token"
    assert "secret://env/HOOK" in json.dumps(report)
    bad = h["config"](
        registry,
        entries={
            Level.INSTANCE: {
                "demo.token": "never-show-literal",
                "demo.refs": {"hook": {"secret": "never-show-nested", "enabled": True}},
            }
        },
    )
    report = build_explain(bad, keys=["demo.token", "demo.refs"])
    assert validator().issues(report) == ()
    assert "never-show" not in json.dumps(report)
    assert "<redacted>" in render_explain_text(report)
    assert all(k["valid"] is False for k in report["keys"])


def test_work_policy_explain_field_merge_lock_provenance_and_unset():
    registry = run_path(str(Path(__file__).with_name("test_registry_all_sections.py")))["real_registry"]()
    key = "execution.work_policy.role_intensity"
    at = h["ref"](Level.WORKSPACE)
    pack = h["layer"](h["ref"](Level.PACK, name="intensity"), {key: {"reviewer": "heavy"}})
    effective = h["config"](
        registry,
        packs=(pack,),
        entries={
            Level.WORKSPACE: {key: Contribution(at, "set", {"executor": "light"}, locked=True)},
            Level.PROJECT: {key: {"executor": "heavy"}},
        },
    )
    entry = build_explain(effective, keys=[key])["keys"][0]
    assert entry["value"]["reviewer"] == "heavy"
    assert entry["value"]["executor"] == "light"
    assert entry["locked_by"]["level"] == "workspace"
    assert entry["contributions"][-1]["reason"] == "locked_above"
    frozen = effective.freeze(registry)
    selected = h["config"](registry, generation=2).with_overrides(frozen)
    entry = build_explain(selected, keys=[key])["keys"][0]
    assert entry["winner"]["level"] == "run_bundle"
    assert entry["value"] == frozen.values[key]
    reset_entries = {Level.WORKSPACE: {key: {"executor": "light"}}}
    assigned = build_explain(h["config"](registry, entries=reset_entries, packs=(pack,)), keys=[key])
    assert assigned["keys"][0]["value"]["executor"] == "light"
    del reset_entries[Level.WORKSPACE][key]
    restored = build_explain(h["config"](registry, entries=reset_entries, packs=(pack,)), keys=[key])["keys"][
        0
    ]
    assert "locked_by" not in restored
    assert restored["value"]["executor"] == "medium"


def test_explain_chain_contains_empty_stored_scopes_and_invalid_is_diagnostic(tmp_path):
    registry = h["build_registry"](tmp_path, h["PROPERTIES"])
    effective = h["config"](registry, entries={Level.RUN: {"demo.rounds": 0}})
    report = build_explain(effective)
    assert validator().issues(report) == ()
    assert len(report["chain"]) == 6
    assert next(k for k in report["keys"] if k["key"] == "demo.rounds")["valid"] is False


def test_schema_requires_registry_digest_for_frozen_and_complete_explain_envelope(tmp_path):
    registry = h["build_registry"](tmp_path, h["PROPERTIES"])
    frozen = h["config"](registry).freeze(registry).to_document()
    del frozen["registry_digest"]
    schemas = SchemaRegistry.load_default()
    assert schemas.validator("urn:skm:config:frozen:v1").issues(frozen)
    report = build_explain(h["config"](registry))
    for field in ("chain_kind", "pack_generation", "diagnostics"):
        incomplete = dict(report)
        del incomplete[field]
        assert validator().issues(incomplete) == ()
    invalid = copy.deepcopy(report)
    legacy = {
        key: value
        for key, value in report.items()
        if key not in {"chain_kind", "pack_generation", "diagnostics"}
    }
    assert validator().issues(legacy) == ()
    assert {"chain_kind", "pack_generation", "diagnostics"} <= report.keys()
    assert all(key["merge"] is not None for key in invalid["keys"])


def test_resolver_json_matches_example_fields():
    example = json.loads(
        Path("tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json").read_text()
    )
    registry = run_path(str(Path(__file__).with_name("test_registry_all_sections.py")))["real_registry"]()
    chain = ScopeChain(
        Chain.WORK,
        tuple(
            ScopeRef(Level(item["level"]), UUID(item["scope_id"]), item.get("label", ""))
            for item in example["chain"]
            if "scope_id" in item
        ),
    )
    layers = []
    for item in example["chain"]:
        at = LayerRef(
            Level(item["level"]),
            UUID(item["scope_id"]) if "scope_id" in item else None,
            item.get("label", ""),
            pack_id=item.get("pack_id"),
            pack_priority=item.get("pack_priority"),
        )
        contributions = {}
        for entry in example["keys"]:
            for trace in entry["contributions"]:
                if trace["layer"]["level"] != item["level"]:
                    continue
                raw = trace["layer"]
                source = LayerRef(
                    at.level,
                    at.scope_id,
                    raw.get("label", at.label),
                    pack_id=at.pack_id,
                    pack_priority=at.pack_priority,
                    entry_id=UUID(raw["entry_id"]) if "entry_id" in raw else None,
                    row_version=raw.get("row_version"),
                )
                contributions[entry["key"]] = Contribution(
                    source, trace["op"], trace.get("value"), trace.get("locked", False)
                )
        layers.append(Layer(at, contributions))
    effective = resolve(
        registry, chain, layers, keys=[k["key"] for k in example["keys"]], generation=42, pack_generation=3
    )
    report = build_explain(effective, keys=[k["key"] for k in example["keys"]])
    assert validator().issues(report) == ()
    # The example's illustrative digest is not derived from these values. Additional scope IDs and
    # base metadata in the implementation preserve the full provenance omitted in the illustration.
    expected = copy.deepcopy(example)
    expected.pop("digest")

    def project(actual, template):
        if isinstance(template, dict):
            return {key: project(actual[key], value) for key, value in template.items()}
        if isinstance(template, list):
            assert len(actual) == len(template)
            return [project(a, t) for a, t in zip(actual, template, strict=True)]
        return actual

    assert project(report, expected) == expected


@pytest.mark.parametrize(
    ("reason", "wording"),
    [
        ("scope_not_allowed", "level not allowed"),
        ("pack_not_allowed", "packs may not set this key"),
        ("override_not_allowed", "override not allowed"),
        ("op_not_allowed", "operation not allowed"),
        ("narrowing_violation", "would widen 2 from default"),
    ],
)
def test_all_ignored_reasons_have_schema_valid_json_and_explanatory_text(tmp_path, reason, wording):
    properties = copy.deepcopy(h["PROPERTIES"])
    at = h["ref"](Level.PROJECT)
    op = "set"
    if reason == "scope_not_allowed":
        properties["rounds"]["x-skm"]["levels"] = ["instance"]
    elif reason == "pack_not_allowed":
        properties["rounds"]["x-skm"]["pack"] = False
        at = h["ref"](Level.PACK)
    elif reason == "override_not_allowed":
        at = h["ref"](Level.INVOCATION)
    elif reason == "op_not_allowed":
        op = "append"
    else:
        properties["rounds"]["x-skm"].update(merge="narrow", narrow={"direction": "min"})
    registry = h["build_registry"](tmp_path, properties)
    chain = h["work_chain"](5)
    contribution = Contribution(at, op, 8)
    stored = (
        h["stored"](chain, {Level.PROJECT: {"demo.rounds": contribution}})
        if at.level is Level.PROJECT
        else h["stored"](chain, {})
    )
    layers = [h["defaults"](registry)]
    if at.level is Level.PACK:
        layers.append(Layer(at, {"demo.rounds": contribution}))
    layers.extend(stored)
    if at.level is Level.INVOCATION:
        layers.append(Layer(at, {"demo.rounds": contribution}))
    effective = resolve(registry, chain, layers, generation=1, pack_generation=1)
    report = build_explain(effective, keys=["demo.rounds"])
    assert validator().issues(report) == ()
    assert report["keys"][0]["contributions"][-1]["reason"] == reason
    assert wording in render_explain_text(report)


def test_external_schema_refs_mask_invalid_secrets_without_revealing_values():
    example = json.loads(
        Path("tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json").read_text()
    )
    value = copy.deepcopy(example["keys"][2]["value"])
    registry = run_path(str(Path(__file__).with_name("test_registry_all_sections.py")))["real_registry"]()
    value["notify-chat"]["target"]["previous_secret"] = None
    current = h["config"](registry, entries={Level.WORKSPACE: {"hooks.subscriptions": value}})
    report = build_explain(current, keys=["hooks.subscriptions"])
    assert "secret://env/SKM_HOOK_SECRET" in json.dumps(report)
    assert report["keys"][0]["value"]["notify-chat"]["target"]["previous_secret"] is None
    value["notify-chat"]["target"]["secret"] = "literal-private-token"
    invalid = h["config"](registry, entries={Level.WORKSPACE: {"hooks.subscriptions": value}})
    report = build_explain(invalid, keys=["hooks.subscriptions"])
    assert validator().issues(report) == ()
    assert "literal-private-token" not in json.dumps(report)
    assert "<redacted>" in render_explain_text(report)


def test_repeated_invocation_refs_keep_each_narrowing_ceiling(tmp_path):
    properties = copy.deepcopy(h["PROPERTIES"])
    properties["rounds"]["x-skm"].update(merge="narrow", narrow={"direction": "min"}, override=True)
    registry = h["build_registry"](tmp_path, properties)
    chain = h["work_chain"](5)
    at = h["ref"](Level.INVOCATION)
    effective = resolve(
        registry,
        chain,
        [
            h["defaults"](registry),
            *h["stored"](chain, {Level.INSTANCE: {"demo.rounds": 5}}),
            *(Layer(at, {"demo.rounds": Contribution(at, "set", value)}) for value in (9, 3, 9)),
        ],
        generation=1,
        pack_generation=1,
    )
    report = build_explain(effective, keys=["demo.rounds"])
    assert validator().issues(report) == ()
    ignored = [c for c in report["keys"][0]["contributions"] if c["status"] == "ignored"]
    assert [c["ceiling"] for c in ignored] == [5, 3]
    text = render_explain_text(report)
    assert "would widen 5 from instance" in text
    assert "would widen 3 from cli" in text


def test_generated_explain_consumer_round_trips_current_and_unknown_history(tmp_path):
    from skm.modules.settings.generated.views import explain_report_from_json, explain_report_to_json

    registry = h["build_registry"](tmp_path, h["PROPERTIES"])
    current = h["config"](registry)
    frozen = current.freeze(registry)
    for report in (build_explain(current), build_explain(frozen)):
        assert validator().issues(report) == ()
        assert explain_report_to_json(explain_report_from_json(report)) == report


def test_unknown_stored_key_is_preserved_as_a_global_diagnostic(tmp_path):
    registry = h["build_registry"](tmp_path, h["PROPERTIES"])
    current = h["config"](registry, entries={Level.INSTANCE: {"demo.typo": 8}})
    report = build_explain(current)
    assert validator().issues(report) == ()
    assert any(d["code"] == "CONFIG_UNKNOWN_KEY" and d["key"] == "demo.typo" for d in report["diagnostics"])
    assert "CONFIG_UNKNOWN_KEY" in render_explain_text(report)


def test_unknown_historical_values_and_provenance_do_not_leak(tmp_path):
    registry = h["build_registry"](tmp_path, h["PROPERTIES"])
    document = h["config"](registry).freeze(registry).to_document()
    document["values"]["unknown.key"] = {"nested": ["CANARY_VALUE", {"ref": "secret://env/CANARY"}]}
    document["provenance"]["unknown.key"] = "CANARY_PROVENANCE"
    document["values"]["canary.secret.key"] = "key-name-canary"
    document["provenance"]["canary.provenance.key"] = "anything"
    document["provenance"]["demo.rounds"] = "CANARY_KNOWN_PROVENANCE"
    document["values"]["demo.note"] = "CANARY_PUBLIC_VALUE"
    document["values"]["demo.refs"] = {
        "hook": {"secret": "secret://env/CANARY_KNOWN_SECRET", "enabled": True}
    }
    document = h["rehash"](document)
    frozen = FrozenConfig.from_document(document)
    for descriptor in (None, registry):
        report = build_explain(frozen, registry=descriptor)
        assert all(entry["key"] != "unknown.key" for entry in report["keys"])
        assert validator().issues(report) == ()
        output = json.dumps(report) + render_explain_text(report)
        for canary in (
            "CANARY_VALUE",
            "secret://env/CANARY",
            "CANARY_PROVENANCE",
            "CANARY_KNOWN_PROVENANCE",
            "CANARY_PUBLIC_VALUE",
            "secret://env/CANARY_KNOWN_SECRET",
            "canary.secret.key",
            "canary.provenance.key",
        ):
            assert canary not in output
    known = build_explain(frozen, registry=registry)
    known_rounds = next(entry for entry in known["keys"] if entry["key"] == "demo.rounds")
    assert known_rounds["present"] is True
    assert known_rounds["interpretation"] == "known"
    assert "value" not in known_rounds
    assert "<redacted>" in render_explain_text(known)
    assert frozen.to_document() == document

    document["registry_digest"] = "sha256:" + "0" * 64
    document["values"]["demo.rounds"] = {"nested": "CANARY_KNOWN_KEY_VALUE"}
    document["provenance"]["demo.rounds"] = "CANARY_KNOWN_KEY_PROVENANCE"
    incompatible = FrozenConfig.from_document(h["rehash"](document))
    for descriptor in (None, registry):
        report = build_explain(incompatible, registry=descriptor)
        output = json.dumps(report) + render_explain_text(report)
        assert "CANARY_KNOWN_KEY_VALUE" not in output
        assert "CANARY_KNOWN_KEY_PROVENANCE" not in output
