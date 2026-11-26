"""Usage accounting (runtimes §4.8): merge, cost in integer micros, fresh tokens, unknown != 0."""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest

from skm.modules.runtimes.domain.catalog import (
    ModelCatalog,
    ModelEntry,
    ModelStatus,
    Pricing,
    RuntimeCatalogEntry,
    parse_price,
    parse_pricing,
)
from skm.modules.runtimes.domain.classes import ModelClass
from skm.modules.runtimes.domain.usage import (
    SubagentUsage,
    UsageReport,
    UsageStatus,
    cache_hit_rate,
    cost,
    estimate_from_prompt,
    fresh_tokens,
    merge_usage,
    unknown_usage,
    usage_from_json,
    usage_to_json,
)
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
URN = "urn:skm:runtimes:usage-report:v1"
DISCLOSED = SubagentUsage(used=False, disclosed=True)


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def report(
    input_tokens: int | None = 100,
    output_tokens: int | None = 20,
    *,
    cache_read: int | None = None,
    cache_write: int | None = None,
    status: UsageStatus = UsageStatus.REPORTED,
    subagents: SubagentUsage = DISCLOSED,
    cost_micros: int | None = None,
    source: str = "stream:delta",
) -> UsageReport:
    return UsageReport(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=None,
        cost_usd_micros=cost_micros,
        status=status,
        source=source,
        subagents=subagents,
    )


PRICING = Pricing(
    input_per_mtok_usd=Decimal("3.00"),
    output_per_mtok_usd=Decimal("15.00"),
    cache_read_per_mtok_usd=Decimal("0.30"),
    cache_write_per_mtok_usd=Decimal("3.75"),
    currency="USD",
    verified_at=date(2026, 10, 1),
    source="test",
)


def test_cumulative_replaces_and_delta_adds() -> None:
    total = merge_usage(report(100, 20), report(50, 5), cumulative=False)
    assert (total.input_tokens, total.output_tokens) == (150, 25)
    replaced = merge_usage(total, report(400, 90, source="stream:result"), cumulative=True)
    assert (replaced.input_tokens, replaced.output_tokens, replaced.source) == (400, 90, "stream:result")


@pytest.mark.parametrize("cumulative", [True, False], ids=["cumulative", "delta"])
@pytest.mark.parametrize(
    "subagents",
    [DISCLOSED, SubagentUsage(used=True, disclosed=True), SubagentUsage(used=True, disclosed=False)],
    ids=["unused-disclosed", "used-disclosed", "used-undisclosed"],
)
def test_first_report_into_unknown_start_is_taken_whole(cumulative: bool, subagents: SubagentUsage) -> None:
    first = report(7, 3, subagents=subagents)
    merged = merge_usage(unknown_usage(), first, cumulative=cumulative)
    assert merged == first
    assert (merged.input_tokens, merged.output_tokens, merged.status) == (7, 3, UsageStatus.REPORTED)


@pytest.mark.parametrize("cumulative", [True, False], ids=["cumulative", "delta"])
def test_known_subagent_facts_of_an_empty_accumulator_survive(cumulative: bool) -> None:
    # Counters unknown, but subagents were already reported: not the neutral start.
    seen = dataclasses.replace(unknown_usage(), subagents=SubagentUsage(used=True, disclosed=False))
    merged = merge_usage(seen, report(7, 3, subagents=DISCLOSED), cumulative=cumulative)
    assert (merged.input_tokens, merged.output_tokens) == (7, 3)
    assert merged.subagents == SubagentUsage(used=True, disclosed=False)


def test_unknown_delta_after_measured_usage_is_not_a_zero() -> None:
    merged = merge_usage(report(7, 3), unknown_usage(), cumulative=False)
    assert (merged.input_tokens, merged.output_tokens) == (7, 3)
    assert merged.status is UsageStatus.ESTIMATED  # some spend is not counted


def test_worse_status_wins_and_partial_cost_is_unknown() -> None:
    merged = merge_usage(
        report(1, 1, cost_micros=10),
        report(1, 1, status=UsageStatus.ESTIMATED, cost_micros=None),
        cumulative=False,
    )
    assert merged.status is UsageStatus.ESTIMATED
    assert merged.cost_usd_micros is None
    both = merge_usage(report(1, 1, cost_micros=10), report(1, 1, cost_micros=5), cumulative=False)
    assert both.cost_usd_micros == 15


@pytest.mark.parametrize("cumulative", [True, False])
def test_subagents_survive_merge(cumulative: bool) -> None:
    seen = report(subagents=SubagentUsage(used=True, disclosed=False))
    later = report(subagents=SubagentUsage(used=False, disclosed=True))
    merged = merge_usage(seen, later, cumulative=cumulative)
    assert merged.subagents.used is True
    assert merged.subagents.disclosed is False  # earlier undisclosed subagents are not covered


def test_cumulative_total_that_includes_subagents_discloses_them() -> None:
    seen = report(subagents=SubagentUsage(used=True, disclosed=False))
    final = report(subagents=SubagentUsage(used=True, disclosed=True))
    assert merge_usage(seen, final, cumulative=True).subagents == SubagentUsage(used=True, disclosed=True)


def test_unknown_usage_carries_no_counters() -> None:
    usage = unknown_usage()
    assert usage.input_tokens is None
    assert usage.cost_usd_micros is None
    assert fresh_tokens(usage) is None
    assert cache_hit_rate(usage) is None
    assert cost(usage, PRICING) is None
    with pytest.raises(ValueError, match="unknown"):
        report(0, 0, status=UsageStatus.UNKNOWN)


def test_fresh_tokens_count_cache_writes_but_not_cache_reads() -> None:
    assert fresh_tokens(report(100, 20, cache_read=5000, cache_write=30)) == 150
    assert fresh_tokens(report(100, 20, cache_read=5000, cache_write=None)) == 120
    assert fresh_tokens(report(None, 20)) is None
    assert fresh_tokens(report(100, None)) is None


@pytest.mark.parametrize(
    ("reads", "writes", "expected"),
    [(None, 80, None), (240, None, None), (0, 0, None), (0, 80, 0.0), (240, 0, 1.0), (240, 80, 0.75)],
)
def test_cache_hit_rate_uses_only_available_cache_counters(
    reads: int | None, writes: int | None, expected: float | None
) -> None:
    assert cache_hit_rate(report(None, None, cache_read=reads, cache_write=writes)) == expected
    assert cache_hit_rate(report(9999, 777, cache_read=reads, cache_write=writes)) == expected


def test_cost_is_integer_micros_rounded_up() -> None:
    # 1 input token at 3.00 USD/Mtok is exactly 3 micros; 1 token at 0.30 is 0.3 micro -> rounds up.
    assert cost(report(1, 0), PRICING) == 3
    assert cost(report(0, 0, cache_read=1), PRICING) == 1
    value = cost(report(1000, 200, cache_read=10000, cache_write=500), PRICING)
    assert value == 3000 + 3000 + 3000 + 1875
    assert isinstance(value, int)


def test_cost_unknown_without_pricing_counters_or_cache_price() -> None:
    assert cost(report(), None) is None
    assert cost(report(None, 20), PRICING) is None
    assert cost(report(100, None), PRICING) is None
    no_cache_price = Pricing(Decimal(3), Decimal(15), None, None, "USD", date(2026, 10, 1), "test")
    assert cost(report(100, 20), no_cache_price) == 600
    assert cost(report(100, 20, cache_read=1), no_cache_price) is None


def test_estimate_from_prompt_is_estimated() -> None:
    estimate = estimate_from_prompt(1200, 800)
    assert estimate.status is UsageStatus.ESTIMATED
    assert (estimate.input_tokens, estimate.output_tokens) == (1200, 800)
    assert estimate.source == "estimate:prompt_chars"


@pytest.mark.parametrize("value", [-1, True, 1.5, 2**63])
def test_counters_are_bounded_non_negative_ints(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        report(input_tokens=value)  # pyright: ignore[reportArgumentType]


def test_usage_report_schema_with_subagents() -> None:
    sample = json.loads((ROOT / "tests/fixtures/corpus/examples/runtimes/usage-report.json").read_text())
    assert registry().validate(URN, sample) == ()
    decoded = usage_from_json(sample)
    assert usage_to_json(decoded) == sample
    for usage in (report(), unknown_usage(), estimate_from_prompt(1, 1)):
        assert registry().validate(URN, usage_to_json(usage)) == ()
    missing_subagents = {key: value for key, value in usage_to_json(report()).items() if key != "subagents"}
    assert registry().validate(URN, missing_subagents) != ()
    float_cost = usage_to_json(report()) | {"cost_usd_micros": 1.5}
    assert registry().validate(URN, float_cost) != ()


def test_catalog_prices_are_decimal_strings() -> None:
    pricing = parse_pricing(
        {
            "input_per_mtok_usd": "3.00",
            "output_per_mtok_usd": "15",
            "cache_read_per_mtok_usd": "0.30",
            "currency": "USD",
            "verified_at": "2026-10-01",
            "source": "docs",
        }
    )
    assert pricing is not None
    assert pricing.input_per_mtok_usd == Decimal("3.00")
    assert pricing.cache_write_per_mtok_usd is None
    assert parse_pricing(None) is None
    for bad in (3.0, 3, "-1", "1e3", "3.", ""):
        with pytest.raises(ValueError, match="decimal string"):
            parse_price(bad, "input_per_mtok_usd")
    with pytest.raises(TypeError):
        Pricing(3.0, Decimal(1), None, None, "USD", date(2026, 1, 1), "x")  # pyright: ignore[reportArgumentType]


def entry(
    model_id: str, status: ModelStatus, *, pricing: Pricing | None = PRICING, patterns: tuple[str, ...] = ()
) -> ModelEntry:
    return ModelEntry(
        id=model_id,
        runtime_id="claude_code",
        display_name=model_id,
        classes=frozenset({ModelClass.FRONTIER}),
        suited_roles=frozenset(),
        context_window_tokens=200000,
        max_output_tokens=None,
        pricing=pricing,
        patterns=patterns,
        status=status,
        verified_at=date(2026, 10, 1),
        source="test",
        notes="",
    )


def test_catalog_lookup_feeds_cost_and_skips_deprecated_on_pick() -> None:
    catalog = ModelCatalog(
        catalog_version="1.0.0",
        resource_version_ids=(),
        digest="sha256:" + "0" * 64,
        runtimes={
            "claude_code": RuntimeCatalogEntry(
                runtime_id="claude_code",
                class_selectors={ModelClass.FRONTIER: ("old", "opus")},
                effort_selectors={},
                models=(
                    entry("old", ModelStatus.DEPRECATED),
                    entry("opus", ModelStatus.CONFIRMED, patterns=(r"claude-opus-.*",)),
                ),
            )
        },
    )
    picked = catalog.pick("claude_code", ModelClass.FRONTIER)
    assert picked is not None
    assert picked.id == "opus"
    assert catalog.pick("claude_code", ModelClass.ECONOMY) is None
    variant = catalog.model("claude_code", "claude-opus-5-5")
    assert variant is not None
    assert variant.id == "opus"
    assert catalog.model("claude_code", "xclaude-opus") is None
    assert catalog.model("codex", "opus") is None
    assert cost(report(1000, 200), variant.pricing) == 6000
