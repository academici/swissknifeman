"""Lazy invalid sections: an invalid section fails closed on read, every other section stays readable.

Cross-key validators run on the candidate slice of their section (settings §B.6 step 7, §B.8.3); an invalid
key keeps its provenance. Scenarios use the real platform sections and their ``plugins.subsets`` rule.
"""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.generated.settings import (
    EventsSettings,
    LoggingHostView,
    LoggingSettings,
    PluginsSettings,
    StorageSettings,
)
from skm.platform.config.keys import MISSING, Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SectionValidatorFn, SettingsRegistry
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.validation import (
    check_section_validators,
    run_section_validators,
    validate_value,
)
from skm.platform.config.validators import SECTION_URNS, VALIDATORS, VIEWS
from skm.platform.schema.registry import SchemaRegistry

INSTANCE = UUID(int=1)
HOST = UUID(int=2)
SUBSET_KEYS = ("plugins.allowed", "plugins.required", "plugins.control_plane_allowed")


@cache
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def build(validator: SectionValidatorFn | None = None) -> SettingsRegistry:
    validators = dict(VALIDATORS) if validator is None else {"plugins.subsets": validator}
    return SettingsRegistry.build(
        schemas(), SECTION_URNS, views=VIEWS, validators=validators, known_permissions=frozenset()
    )


@cache
def platform() -> SettingsRegistry:
    return build()


def details(error: pytest.ExceptionInfo[ValidationFailed]) -> Any:
    return error.value.details


def defaults(registry: SettingsRegistry, chain: Chain, *, skip: str = "") -> Layer:
    at = LayerRef(Level.DEFAULT)
    return Layer(
        at,
        {
            spec.key: Contribution(at, "default", cast("JsonValue", spec.default))
            for spec in registry.keys(chain=chain)
            if spec.default is not MISSING and not (skip and spec.section == skip)
        },
    )


def effective(
    entries: Mapping[str, JsonValue] | None = None,
    *,
    registry: SettingsRegistry | None = None,
    skip_defaults_of: str = "",
) -> EffectiveConfig:
    registry = registry or platform()
    chain = ScopeChain(Chain.WORK, (ScopeRef(Level.INSTANCE, INSTANCE, "instance"),))
    instance = LayerRef(Level.INSTANCE, INSTANCE, label="instance")
    layers = [
        defaults(registry, Chain.WORK, skip=skip_defaults_of),
        Layer(
            instance, {key: Contribution(instance, "set", value) for key, value in (entries or {}).items()}
        ),
    ]
    return resolve(registry, chain, layers, generation=3, pack_generation=1)


def test_an_invalid_section_fails_closed_and_other_sections_stay_readable() -> None:
    config = effective({"plugins.required": ["x"]})  # required ⊄ allowed (default [])
    with pytest.raises(ValidationFailed) as refused:
        config.section(PluginsSettings)
    assert refused.value.code is ErrorCode.CONFIG_INVALID
    listed = [item["key"] for item in details(refused)["keys"]]
    assert listed == list(SUBSET_KEYS)
    for key in SUBSET_KEYS:
        with pytest.raises(ValidationFailed):
            config.get(key)
    assert config.get("plugins.override_builtin") == []  # same section, not part of the failed rule
    storage = config.section(StorageSettings)
    assert storage.statement_timeout_ms == 30000
    assert config.get("events.delivery.max_attempts") == config.section(EventsSettings).delivery.max_attempts


def test_an_invalid_key_keeps_its_provenance() -> None:
    config = effective({"plugins.required": ["x"]})
    problem = config.invalid_keys()["plugins.required"]
    assert (problem.reason, problem.validator) == ("validator", "plugins.subsets")
    assert "subset" in problem.message
    assert problem.provenance.winner == LayerRef(Level.INSTANCE, INSTANCE, label="instance")
    allowed = config.invalid_keys()["plugins.allowed"]
    assert allowed.provenance.winner == LayerRef(Level.DEFAULT)
    with pytest.raises(ValidationFailed) as refused:
        config.get("plugins.required")
    document = details(refused)
    assert document["validator"] == "plugins.subsets"
    assert document["provenance"]["winner"]["level"] == "instance"
    assert config.resolution("plugins.required").value == ["x"]  # explain still sees the rejected value
    invalid = [item for item in config.diagnostics if item.code == "CONFIG_INVALID"]
    assert {item.target for item in invalid} == set(SUBSET_KEYS)
    assert all(item.severity == "error" for item in invalid)


def test_a_valid_combination_passes_the_validator() -> None:
    config = effective({"plugins.allowed": ["x", "y"], "plugins.required": ["x"]})
    assert not config.invalid_keys()
    plugins = config.section(PluginsSettings)
    assert plugins.required == ("x",)


def test_validators_receive_exactly_their_read_only_candidate_slice() -> None:
    seen: list[Mapping[str, JsonValue]] = []

    def record(values: Mapping[str, JsonValue]) -> str | None:
        seen.append(values)
        with pytest.raises(TypeError):
            cast("Any", values)["plugins.allowed"] = []
        return VALIDATORS["plugins.subsets"](values)

    config = effective({"plugins.allowed": ["x"]}, registry=build(record))
    assert len(seen) == 1
    assert dict(seen[0]) == {
        "plugins.allowed": ["x"],
        "plugins.required": [],
        "plugins.control_plane_allowed": [],
    }
    assert not config.invalid_keys()


def test_a_validator_with_an_invalid_input_does_not_run_and_blocks_its_other_keys() -> None:
    calls: list[object] = []

    def record(values: Mapping[str, JsonValue]) -> str | None:
        calls.append(values)
        return None

    config = effective({"plugins.allowed": ["Not Valid!"]}, registry=build(record))
    assert calls == []
    invalid = config.invalid_keys()
    assert invalid["plugins.allowed"].reason == "schema"
    for key in ("plugins.required", "plugins.control_plane_allowed"):
        assert invalid[key].reason == "validator"
        assert invalid[key].blocked_by == ("plugins.allowed",)
    assert config.get("plugins.override_builtin") == []


@pytest.mark.parametrize("result", ["raise", 42, ""])
def test_a_broken_validator_fails_its_keys_closed_without_breaking_resolution(result: Any) -> None:
    def broken(values: Mapping[str, JsonValue]) -> str | None:
        if result == "raise":
            raise RuntimeError("boom")
        return result

    config = effective(registry=build(broken))
    assert set(config.invalid_keys()) == set(SUBSET_KEYS)
    message = config.invalid_keys()["plugins.allowed"].message
    assert {"raise": "RuntimeError", 42: "int", "": "violated"}[result] in message
    assert config.section(StorageSettings).retry.max_attempts == 3


def test_a_required_key_without_value_fails_its_section_only() -> None:
    config = effective(skip_defaults_of="storage")
    with pytest.raises(ValidationFailed) as refused:
        config.section(StorageSettings)
    reasons = {item["reason"] for item in details(refused)["keys"]}
    assert reasons == {"missing"}
    assert config.section(EventsSettings).delivery.max_attempts >= 1
    assert config.section(PluginsSettings).allowed == ()


def test_sections_are_memoized_and_safe_to_read_concurrently() -> None:
    config = effective()
    with ThreadPoolExecutor(max_workers=8) as pool:
        views = list(pool.map(lambda _: config.section(EventsSettings), range(32)))
    assert all(view is views[0] for view in views)
    assert config.section(EventsSettings) is views[0]


def test_scoped_views_do_not_expose_the_other_chain() -> None:
    work = effective()
    work_view = work.section(LoggingSettings)
    assert work_view.redact_patterns == ()
    assert not hasattr(work_view, "level")
    with pytest.raises(ValidationFailed) as refused:
        work.section(LoggingHostView)
    assert refused.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert work.get("logging.redact_patterns") == []

    chain = ScopeChain(Chain.HOST, (ScopeRef(Level.INSTANCE, INSTANCE), ScopeRef(Level.HOST, HOST)))
    host_ref = LayerRef(Level.HOST, HOST)
    host = resolve(
        platform(),
        chain,
        [
            defaults(platform(), Chain.HOST),
            Layer(LayerRef(Level.INSTANCE, INSTANCE), {}),
            Layer(host_ref, {"logging.level": Contribution(host_ref, "set", "debug")}),
        ],
        generation=1,
        pack_generation=0,
    )
    assert host.get("logging.level") == "debug"
    host_view = host.section(LoggingHostView)
    assert host_view.level == "debug"
    assert not hasattr(host_view, "redact_patterns")
    with pytest.raises(ValidationFailed) as host_refused:
        host.section(LoggingSettings)
    assert host_refused.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED


def test_an_unknown_view_is_an_unknown_section() -> None:
    with pytest.raises(ValidationFailed) as refused:
        effective().section(dict)
    assert refused.value.code is ErrorCode.CONFIG_UNKNOWN_KEY


def test_run_section_validators_checks_the_full_slice() -> None:
    assert run_section_validators(
        platform(),
        {"plugins.allowed": [], "plugins.required": ["x"], "plugins.control_plane_allowed": []},
        ["plugins"],
    ) == (("plugins.subsets", "plugins.required must be a subset of plugins.allowed"),)
    full = {"plugins.allowed": ["x"], "plugins.required": ["x"], "plugins.control_plane_allowed": []}
    assert run_section_validators(platform(), full, iter(["plugins", "plugins"])) == ()
    assert run_section_validators(platform(), {}, ["storage"]) == ()


def test_an_absent_required_input_blocks_the_rule_instead_of_passing_it() -> None:
    calls: list[object] = []

    def record(values: Mapping[str, JsonValue]) -> str | None:
        calls.append(values)
        return None

    registry = build(record)
    assert not any(registry.spec(key).nullable for key in SUBSET_KEYS)
    [(validator, message)] = run_section_validators(registry, {"plugins.required": ["x"]}, ["plugins"])
    assert validator == "plugins.subsets"
    assert message.endswith("unavailable input plugins.allowed, plugins.control_plane_allowed")
    [finding] = check_section_validators(
        registry,
        {"plugins.allowed": MISSING, "plugins.required": ["x"], "plugins.control_plane_allowed": []},
        ["plugins"],
    )
    assert finding.blocked_by == ("plugins.allowed",)
    assert calls == []  # the callback never saw an incomplete slice
    assert (
        check_section_validators(
            registry,
            {"plugins.allowed": ["x"], "plugins.required": ["x"], "plugins.control_plane_allowed": []},
            ["plugins"],
        )
        == ()
    )
    assert len(calls) == 1


def test_validate_value_tells_missing_from_null() -> None:
    assert validate_value(platform(), "plugins.allowed", []) == ()
    assert validate_value(platform(), "plugins.allowed", None)  # null is a value and must fit the schema
    assert validate_value(platform(), "plugins.allowed", MISSING)[0].code == "missing"  # required key
    assert validate_value(platform(), "plugins.allowed", ["Not Valid!"])[0].pointer == "/0"
    assert validate_value(platform(), "logging.file", MISSING) == ()  # nullable key may be absent
    with pytest.raises(ValidationFailed) as unknown:
        validate_value(platform(), "plugins.nope", 1)
    assert unknown.value.code is ErrorCode.CONFIG_UNKNOWN_KEY
