"""Process restart values stay at startup, live/run values retain their own reload policy (§B.13)."""

import copy
import json
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.errors import ValidationFailed
from skm.platform.config.effective import ProcessConfig
from skm.platform.config.explain import build_explain as _build_explain
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Layer, LayerRef
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef

h = run_path(str(Path(__file__).with_name("test_frozen.py")))
build_explain = cast("Any", _build_explain)
config, work_chain, host_chain = h["config"], h["work_chain"], h["host_chain"]


@pytest.fixture
def registry(tmp_path):
    return h["build_registry"](tmp_path, h["PROPERTIES"])


def test_process_captures_only_restart_and_retains_work_host_partition(registry):
    process = ProcessConfig.capture(
        config(registry, chain=work_chain()), config(registry, chain=host_chain())
    )
    assert process.work == {"demo.restart": "original"}
    assert process.host == {"demo.host_restart": "host-original"}
    current = config(
        registry,
        generation=2,
        entries={Level.INSTANCE: {"demo.restart": "pending", "demo.rounds": 7, "demo.ceiling": 3}},
    )
    selected = current.with_overrides(process=process)
    assert selected.get("demo.restart") == "original"
    assert selected.get("demo.rounds") == 7
    assert selected.get("demo.ceiling") == 3
    assert selected.provenance("demo.restart").winner.level is Level.PROCESS
    pending = [d for d in selected.diagnostics if d.code == "CONFIG_RESTART_PENDING"]
    assert len(pending) == 1
    assert pending[0].target == "demo.restart"
    assert pending[0].severity.value == "info"
    assert pending[0].details["process_generation"] == 1
    report = build_explain(selected, keys=["demo.restart"])
    assert report["keys"][0]["winner"]["level"] == "process"
    assert report["keys"][0]["diagnostics"][0]["code"] == "CONFIG_RESTART_PENDING"
    current_host = config(
        registry,
        chain=host_chain(),
        generation=2,
        entries={Level.HOST: {"demo.host_restart": "host-pending"}},
    )
    assert current_host.with_overrides(process=process).get("demo.host_restart") == "host-original"


def test_unchanged_restart_does_not_emit_pending_and_new_process_applies_change(registry):
    process = ProcessConfig.capture(config(registry, chain=work_chain()))
    assert not config(registry).with_overrides(process=process).diagnostics
    new_work = config(
        registry, chain=work_chain(), generation=2, entries={Level.INSTANCE: {"demo.restart": "new"}}
    )
    new_process = ProcessConfig.capture(new_work)
    current = config(registry, generation=2, entries={Level.INSTANCE: {"demo.restart": "new"}})
    assert current.with_overrides(process=new_process).get("demo.restart") == "new"
    assert not current.with_overrides(process=new_process).diagnostics


def test_frozen_process_and_live_values_are_selected_independently(registry):
    old = config(registry)
    frozen = old.freeze(registry)
    process = ProcessConfig.capture(config(registry, chain=work_chain()))
    current = config(
        registry,
        generation=2,
        entries={Level.RUN: {"demo.rounds": 9, "demo.restart": "future", "demo.ceiling": 1}},
    )
    selected = current.with_overrides(frozen, process)
    assert selected.get("demo.rounds") == 2
    assert selected.get("demo.restart") == "original"
    assert selected.get("demo.ceiling") == 1
    assert current.get("demo.rounds") == 9
    assert selected.with_overrides(frozen, process).get("demo.restart") == "original"


def test_process_snapshot_is_immutable_and_rejects_wrong_startup_chain(registry):
    source = {"demo.restart": "original"}
    process = ProcessConfig(source, {}, 1)
    source["demo.restart"] = "mutated"
    assert process.work["demo.restart"] == "original"
    with pytest.raises(TypeError):
        cast("Any", process.work)["demo.restart"] = "mutated"
    with pytest.raises(ValueError, match="instance"):
        ProcessConfig.capture(config(registry))
    with pytest.raises(ValueError, match="same generation"):
        ProcessConfig.capture(
            config(registry, chain=work_chain()), config(registry, chain=host_chain(), generation=2)
        )
    with pytest.raises(ValidationFailed):
        config(registry).with_overrides(process=ProcessConfig({}, {}, 1))
    with pytest.raises(ValidationFailed):
        config(registry).with_overrides(process=ProcessConfig({"demo.restart": 7}, {}, 1))


def test_nullable_restart_absence_does_not_acquire_current_value(tmp_path):
    import copy

    properties = copy.deepcopy(h["PROPERTIES"])
    del properties["restart"]["default"]
    properties["restart"]["x-skm"]["nullable"] = True
    registry = h["build_registry"](tmp_path, properties)
    process = ProcessConfig.capture(config(registry, chain=work_chain()))
    current = config(registry, entries={Level.INSTANCE: {"demo.restart": "later"}})
    selected = current.with_overrides(process=process)
    assert selected.present("demo.restart") is False
    assert selected.diagnostics[0].code == "CONFIG_RESTART_PENDING"


@pytest.mark.parametrize("generation", [True, -1, 1.5, "1"])
def test_process_generation_must_be_a_non_negative_integer(generation):
    with pytest.raises(ValueError, match="generation"):
        ProcessConfig({}, {}, generation)


def bounded_registry(tmp_path):
    """``demo.rounds`` (restart, startup 2) must not exceed the live ``demo.ceiling`` (default 10)."""
    properties = copy.deepcopy(h["PROPERTIES"])
    properties["rounds"]["x-skm"]["reload"] = "restart"
    return h["build_registry"](
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


def json_registry(tmp_path):
    """Unconstrained restart objects (``shape``) and arrays (``list``) on the work and the host chain."""
    properties = copy.deepcopy(h["PROPERTIES"])
    for name, kind, default in (("shape", "object", {}), ("list", "array", [])):
        properties[name] = h["leaf"]({"type": kind}, default=default, reload="restart")
        properties[f"host_{name}"] = h["leaf"](
            {"type": kind}, default=default, reload="restart", chain="host", levels=["instance", "host"]
        )
    return h["build_registry"](tmp_path, properties)


def json_key(chain, value):
    return f"demo.{'host_' if chain is Chain.HOST else ''}{'shape' if isinstance(value, dict) else 'list'}"


def pending_keys(effective):
    return [d.target for d in effective.diagnostics if d.code == "CONFIG_RESTART_PENDING"]


KIND_CHANGES = [
    ({"x": True}, {"x": 1}),
    ({"x": False}, {"x": 0}),
    ([False], [0]),
    ([True], [1.0]),
    ({"x": 1}, {"x": 1.0}),
    ([1], [1.0]),
    ({"a": [{"b": True}]}, {"a": [{"b": 1}]}),
    ({"a": {"b": [2]}}, {"a": {"b": [2.0]}}),
    ([[0]], [[False]]),
]
ORDINARY_CHANGES = [
    ({"x": 1}, {"x": 2}),
    ([1, 2], [2, 1]),
    ([1], [1, 1]),
    ({"x": 1}, {"x": 1, "y": 1}),
    ({"x": None}, {}),
    ({"x": []}, {"x": {}}),
    ([[]], [{}]),
    ({"a": {"b": "c"}}, {"a": {"b": "d"}}),
]
EQUAL_VALUES = [{"x": True}, [False, 0, 0.0], {"a": [{"b": 1, "c": 1.0, "d": None}]}, [], {}]


def capture_shapes(registry, key, value):
    host = key.startswith("demo.host_")
    return ProcessConfig.capture(
        config(registry, chain=work_chain(), entries={} if host else {Level.INSTANCE: {key: value}}),
        config(registry, chain=host_chain(), entries={Level.HOST: {key: value}} if host else {}),
    )


def current_shapes(registry, key, value):
    host = key.startswith("demo.host_")
    level, chain = (Level.HOST, host_chain()) if host else (Level.INSTANCE, work_chain())
    return config(registry, chain=chain, generation=2, entries={level: {key: value}})


@pytest.mark.parametrize("chain", [Chain.WORK, Chain.HOST])
@pytest.mark.parametrize(("before", "after"), KIND_CHANGES + ORDINARY_CHANGES)
def test_restart_comparison_distinguishes_json_kinds_at_every_depth(tmp_path, chain, before, after):
    registry = json_registry(tmp_path)
    key = json_key(chain, before)
    assert not registry.value_issues(key, before)
    assert not registry.value_issues(key, after)
    process = capture_shapes(registry, key, before)
    selected = current_shapes(registry, key, after).with_overrides(process=process)
    assert pending_keys(selected) == [key]
    assert json.dumps(selected.get(key)) == json.dumps(before)  # the process keeps its own JSON kinds


@pytest.mark.parametrize("chain", [Chain.WORK, Chain.HOST])
@pytest.mark.parametrize("value", EQUAL_VALUES)
def test_restart_comparison_accepts_the_same_json_value(tmp_path, chain, value):
    registry = json_registry(tmp_path)
    key = json_key(chain, value)
    process = capture_shapes(registry, key, value)
    selected = current_shapes(registry, key, copy.deepcopy(value)).with_overrides(process=process)
    assert pending_keys(selected) == []
    assert not selected.diagnostics


def test_live_only_validator_failure_does_not_mark_unchanged_restart_pending(tmp_path):
    registry = bounded_registry(tmp_path)
    process = ProcessConfig.capture(config(registry, chain=work_chain()))
    assert process.work["demo.rounds"] == 2

    def select(generation, entries):
        current = config(registry, generation=generation, entries={Level.INSTANCE: entries})
        return current, current.with_overrides(process=process)

    # Live-only invalidation: the configured and captured restart values are both still 2.
    current, selected = select(2, {"demo.ceiling": 1})
    assert current.invalid_keys()["demo.rounds"].reason == "validator"
    assert pending_keys(selected) == []
    assert selected.invalid_keys()["demo.rounds"].reason == "validator"  # validity stays reported separately
    # A live input that is itself invalid blocks the validator; the restart value is still unchanged.
    current, selected = select(3, {"demo.ceiling": -1})
    assert current.invalid_keys()["demo.rounds"].blocked_by == ("demo.ceiling",)
    assert pending_keys(selected) == []
    # Restoration of the live input.
    _current, selected = select(4, {"demo.ceiling": 10})
    assert pending_keys(selected) == []
    assert not selected.diagnostics
    # A changed restart input that fails the cross-key validator still requires restart.
    current, selected = select(5, {"demo.rounds": 5, "demo.ceiling": 3})
    assert current.invalid_keys()["demo.rounds"].reason == "validator"
    assert pending_keys(selected) == ["demo.rounds"]
    # A changed valid restart input and a schema-invalid one.
    _current, selected = select(6, {"demo.rounds": 1, "demo.ceiling": 1})
    assert pending_keys(selected) == ["demo.rounds"]
    current, selected = select(7, {"demo.rounds": 0})
    assert current.invalid_keys()["demo.rounds"].reason == "schema"
    assert pending_keys(selected) == ["demo.rounds"]


@pytest.mark.parametrize("live_ceiling", [1, -1])
def test_process_override_preserves_validator_diagnostic_metadata(tmp_path, live_ceiling):
    registry = bounded_registry(tmp_path)
    process = ProcessConfig.capture(config(registry, chain=work_chain()))
    current = config(
        registry,
        generation=2,
        entries={Level.INSTANCE: {"demo.rounds": 1, "demo.ceiling": live_ceiling}},
    )
    if live_ceiling == 1:
        assert not current.invalid_keys()
    else:
        assert current.invalid_keys()["demo.ceiling"].reason == "schema"
    selected = current.with_overrides(process=process)
    expected: dict[str, dict[str, Any]] = {
        "demo.rounds": {"reason": "validator", "validator": "demo.bounds"},
        "demo.ceiling": {"reason": "validator", "validator": "demo.bounds"},
    }
    if live_ceiling == -1:
        expected["demo.rounds"]["blocked_by"] = ["demo.ceiling"]
        expected["demo.ceiling"] = {"reason": "schema"}
    control = config(registry, entries={Level.INSTANCE: {"demo.rounds": 2, "demo.ceiling": live_ceiling}})
    for key, details in expected.items():
        diagnostic = next(d for d in selected.diagnostics if d.code == "CONFIG_INVALID" and d.target == key)
        original = next(d for d in control.diagnostics if d.code == "CONFIG_INVALID" and d.target == key)
        assert dict(diagnostic.details) == dict(original.details) == details
        problem = selected.invalid_keys()[key]
        assert problem.reason == details["reason"]
        assert problem.validator == details.get("validator")
        assert list(problem.blocked_by) == details.get("blocked_by", [])
    # Restoring the live input and selecting the startup value removes both stale CONFIG_INVALID findings.
    repaired = config(registry, generation=3, entries={Level.INSTANCE: {"demo.rounds": 5, "demo.ceiling": 3}})
    assert set(repaired.invalid_keys()) == {"demo.rounds", "demo.ceiling"}
    restored = repaired.with_overrides(process=process)
    assert restored.get("demo.rounds") == 2
    assert restored.get("demo.ceiling") == 3
    assert not restored.invalid_keys()
    assert not any(d.code == "CONFIG_INVALID" for d in restored.diagnostics)


def test_process_scope_binding_rejects_other_hosts_and_instances(registry):
    instance1 = work_chain().target
    instance2 = ScopeRef(Level.INSTANCE, UUID(int=111))
    host1 = host_chain().target
    host2 = ScopeRef(Level.HOST, UUID(int=222))
    process = ProcessConfig.capture(
        config(registry, chain=work_chain()), config(registry, chain=host_chain())
    )
    assert process.instance_scope_id == instance1.scope_id
    assert process.host_target == host1
    assert (
        config(registry, chain=host_chain()).with_overrides(process=process).get("demo.host_restart")
        == "host-original"
    )
    other_host = ScopeChain(Chain.HOST, (instance1, host2))
    other_instance_work = ScopeChain(Chain.WORK, (instance2,))
    other_instance_host = ScopeChain(Chain.HOST, (instance2, host1))

    def resolve_chain(chain):
        layers = [h["defaults"](registry, chain.kind)]
        layers.extend(Layer(LayerRef(scope.level, scope.scope_id), {}) for scope in chain.scopes)
        return resolve(registry, chain, layers, generation=1, pack_generation=1)

    for chain in (other_host, other_instance_work, other_instance_host):
        with pytest.raises(ValidationFailed):
            resolve_chain(chain).with_overrides(process=process)
    with pytest.raises(ValueError, match="same generation"):
        ProcessConfig.capture(config(registry, chain=work_chain()), resolve_chain(other_instance_host))
    with pytest.raises(ValidationFailed):
        config(registry).with_overrides(process=ProcessConfig(process.work, process.host, 1))


def test_process_host_instance_target_requires_matching_capture(registry):
    instance = work_chain().target
    host_instance = ScopeChain(Chain.HOST, (instance,))
    work = config(registry, chain=work_chain())
    host = config(registry, chain=host_instance)
    process = ProcessConfig.capture(work, host)
    assert host.with_overrides(process=process).get("demo.host_restart") == "host-original"
    with pytest.raises(ValidationFailed):
        config(registry, chain=host_chain()).with_overrides(process=process)
    no_host = ProcessConfig.capture(work)
    with pytest.raises(ValidationFailed):
        host.with_overrides(process=no_host)
    with pytest.raises((AttributeError, TypeError)):
        cast("Any", process).instance_scope_id = UUID(int=77)
    with pytest.raises(TypeError):
        ProcessConfig({}, {}, 1, cast("Any", "not-a-uuid"))
