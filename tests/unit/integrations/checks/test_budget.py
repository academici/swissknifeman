"""Estimator vectors, five sources, exact thresholds and incomplete observations."""

import math
from uuid import UUID

import pytest

from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.budget import (
    FirstTurnSourceKind,
    FirstTurnVerdict,
    estimate_tokens,
    first_turn_sources,
    first_turn_verdict,
    frontmatter_field,
    source_total,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.settings import SECTION_URNS, VIEWS, validators_for
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.resolver import resolve
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.sources.defaults import defaults_layer
from skm.platform.schema.registry import SchemaRegistry


@pytest.mark.parametrize("text", ["", "hello world", "Привет мир", "hello Привет", "\u0500\u052f", "🙂\n"])
def test_token_vectors(text):
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff" or "\u0500" <= c <= "\u052f")
    assert estimate_tokens(text) == math.ceil(cyr / 2.9 + (len(text) - cyr) / 3.4)


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (0, "ok"),
        (16000, "ok"),
        (16001, "elevated"),
        (23000, "elevated"),
        (23001, "warn"),
        (None, "incomplete"),
    ],
)
def test_exact_thresholds(total, expected):
    assert first_turn_verdict(total, target=16000, warn=23000) == expected


def sources(**override):
    args = {
        "target": TargetId.CLAUDE_CODE,
        "skills": {"SKILL.md": "---\nname: test\ndescription: Useful skill\n---\nlarge body"},
        "agents": {"agent.md": "---\ndescription: Useful agent\n---\nlarge body"},
        "instructions": {"CLAUDE.md": "managed\n" + "unmanaged\n" * 20},
        "session_start_template": "Welcome to project",
        "mcp_servers": {"docs": {"tool_count": 8, "instructions": "Read docs"}, "fallback": {}},
    }
    return first_turn_sources(**(args | override))


def test_five_sources_have_explicit_methods_counts_digests_and_are_estimates():
    report = sources()
    assert [source.kind for source in report] == list(FirstTurnSourceKind)
    assert report[0].tokens == estimate_tokens("test: Useful skill")
    assert report[1].tokens == estimate_tokens("Useful agent")
    assert report[2].tokens == estimate_tokens("managed\n" + "unmanaged\n" * 20)
    assert report[3].tokens == estimate_tokens("Welcome to project")
    assert report[4].tokens == 8 * 150 + estimate_tokens("Read docs") + 5 * 150 + 40
    tokens = [source.tokens for source in report]
    assert None not in tokens
    assert source_total(report) == sum(count for count in tokens if count is not None)
    digests = report[2].detail["digests"]
    assert isinstance(digests, dict)
    digest = digests["CLAUDE.md"]
    assert isinstance(digest, str)
    assert digest.startswith("sha256:")
    assert all(source.method and source.detail["estimated"] is True for source in report)
    assert report[3].detail["run_hooks"] is False


@pytest.mark.parametrize(
    "missing", ["skills", "agents", "instructions", "session_start_template", "mcp_servers"]
)
def test_partial_or_missing_native_source_forces_incomplete(missing):
    value = (
        None if missing in ("session_start_template", "mcp_servers") else {"missing": None, "other": "valid"}
    )
    report = sources(**{missing: value})
    assert any(source.tokens is None for source in report)
    assert source_total(report) is None
    assert first_turn_verdict(source_total(report), target=16000, warn=23000) is FirstTurnVerdict.INCOMPLETE


def test_listing_caps_deferred_mcp_and_disabled_server():
    long = "---\nname: test\ndescription: " + "x" * 10000 + "\n---\n"
    report = sources(
        skills={"SKILL.md": long},
        listing_fraction=0.001,
        context_window=8000,
        deferred_tool_search=True,
        mcp_servers={"docs": {"tool_count": 2}, "off": {"enabled": False}},
    )
    assert report[0].detail["listing_chars"] == 1536
    assert report[0].tokens == 8
    assert report[4].tokens == 2 * 24 + 40
    for target in (TargetId.CODEX, TargetId.CURSOR, TargetId.GROK):
        assert sources(target=target, skills={str(i): long for i in range(20)})[0].tokens == estimate_tokens(
            "\n".join(("test: " + "x" * 10000)[:1536] for _ in range(20))[:8000]
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('"hello: world"', "hello: world"),
        ("'it''s valid'", "it's valid"),
        (">-\n  one\n  two", "one two"),
        ("|-\n  one\n  two", "one\ntwo"),
    ],
)
def test_native_frontmatter_strings(value, expected):
    assert frontmatter_field("---\ndescription: " + value + "\n---\nbody", "description") == expected


@pytest.mark.parametrize("overlay", [False, True])
def test_invalid_effective_budget_uses_early_registered_validator(overlay):
    registry = SettingsRegistry.build(
        SchemaRegistry.load_default(),
        SECTION_URNS,
        views=VIEWS,
        known_permissions=frozenset({"hook.manage"}),
        validators=validators_for(hookable_types=(), sink_ids=()),
    )
    at = (
        LayerRef(Level.PACK, pack_id="budget-overlay", pack_priority=10)
        if overlay
        else (LayerRef(Level.INSTANCE, UUID(int=1)))
    )
    values = {"integrations.budget.first_turn.target": 24000, "integrations.budget.first_turn.warn": 23000}
    layer = Layer(at, {key: Contribution(at, "set", value) for key, value in values.items()})
    chain = ScopeChain(Chain.WORK, (ScopeRef(Level.INSTANCE, UUID(int=1)),))
    layers = (defaults_layer(registry, Chain.WORK), layer)
    if overlay:
        instance = LayerRef(Level.INSTANCE, UUID(int=1))
        layers += (Layer(instance, {}),)
    config = resolve(registry, chain, layers, generation=0, pack_generation=0)
    with pytest.raises(ValidationFailed) as caught:
        config.get("integrations.budget.first_turn.target")
    assert caught.value.details["validator"] == "integrations.budget_order"
    assert config.generation == 0


def test_native_toml_agent_description_and_malformed_metadata():
    report = sources(target=TargetId.CODEX, agents={"agent.toml": 'description = "Native role"\n'})
    assert report[1].tokens == estimate_tokens("Native role")
    report = sources(target=TargetId.CODEX, agents={"agent.toml": "description = [broken"})
    assert report[1].tokens is None
    assert report[1].detail["unmeasurable"] == ["agent.toml"]
