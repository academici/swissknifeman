from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from skm.adapters.runtimes.pool import (
    FailoverCandidate,
    FailoverController,
    FailoverDecision,
    FailoverPolicy,
    ProviderSlot,
)
from skm.modules.execution.domain.session import Fresh
from skm.modules.runtimes.public import Pricing, estimate_from_prompt, unknown_usage

_OPTED_IN = FailoverPolicy(
    enabled=True,
    explicit_consent=True,
    tos_acknowledged=True,
    cost_ceiling_usd_micros=70,
    fresh_session=True,
)
_TARIFF = Pricing(Decimal("2"), Decimal("3"), None, None, "USD", date(2026, 1, 1), "test")
_FALLBACK = FailoverCandidate(
    ProviderSlot("secondary", "fallback"),
    "cloud_b",
    _TARIFF,
    estimate_from_prompt(20, 10),
)


def _route(
    controller: FailoverController,
    via_local_proxy: bool,
    candidate: FailoverCandidate = _FALLBACK,
    *,
    consumed_host_private: bool | None = False,
) -> FailoverDecision | None:
    if via_local_proxy:
        return controller.route_local_proxy(candidate, consumed_host_private=consumed_host_private)
    return controller.select_failover(
        (candidate,),
        source_provider_id="cloud_a",
        http_status=529,
        consumed_host_private=consumed_host_private,
    )


@pytest.mark.parametrize("via_local_proxy", [False, True], ids=["failover", "proxy"])
def test_disabled_by_default(via_local_proxy: bool) -> None:
    assert _route(FailoverController(), via_local_proxy) is None


@pytest.mark.parametrize("via_local_proxy", [False, True], ids=["failover", "proxy"])
@pytest.mark.parametrize(
    "policy",
    [
        pytest.param(replace(_OPTED_IN, enabled=False), id="disabled"),
        pytest.param(replace(_OPTED_IN, explicit_consent=False), id="missing-consent"),
        pytest.param(replace(_OPTED_IN, tos_acknowledged=False), id="missing-tos"),
        pytest.param(replace(_OPTED_IN, fresh_session=False), id="missing-fresh-session"),
        pytest.param(replace(_OPTED_IN, cost_ceiling_usd_micros=None), id="missing-ceiling"),
        pytest.param(replace(_OPTED_IN, cost_ceiling_usd_micros=-1), id="negative-ceiling"),
        pytest.param(replace(_OPTED_IN, cost_ceiling_usd_micros=69), id="over-ceiling"),
    ],
)
def test_each_policy_gate_is_required(via_local_proxy: bool, policy: FailoverPolicy) -> None:
    assert _route(FailoverController(policy), via_local_proxy) is None


@pytest.mark.parametrize("via_local_proxy", [False, True], ids=["failover", "proxy"])
@pytest.mark.parametrize("truthy", [1, "true"])
def test_truthy_values_do_not_count_as_consent_or_tos(via_local_proxy: bool, truthy: bool) -> None:
    assert _route(FailoverController(replace(_OPTED_IN, explicit_consent=truthy)), via_local_proxy) is None
    assert _route(FailoverController(replace(_OPTED_IN, tos_acknowledged=truthy)), via_local_proxy) is None


@pytest.mark.parametrize("via_local_proxy", [False, True], ids=["failover", "proxy"])
@pytest.mark.parametrize(
    "candidate",
    [
        pytest.param(replace(_FALLBACK, pricing=None), id="unknown-tariff"),
        pytest.param(replace(_FALLBACK, estimated_usage=unknown_usage()), id="unknown-usage"),
        pytest.param(
            replace(_FALLBACK, estimated_usage=replace(_FALLBACK.estimated_usage, cache_write_tokens=1)),
            id="partially-unpriced-usage",
        ),
    ],
)
def test_unknown_cost_fails_closed(via_local_proxy: bool, candidate: FailoverCandidate) -> None:
    assert _route(FailoverController(_OPTED_IN), via_local_proxy, candidate) is None


@pytest.mark.parametrize("via_local_proxy", [False, True], ids=["failover", "proxy"])
@pytest.mark.parametrize("consumed_host_private", [True, None], ids=["consumed", "unknown"])
def test_host_private_episodes_block_routing(
    via_local_proxy: bool, consumed_host_private: bool | None
) -> None:
    assert (
        _route(FailoverController(_OPTED_IN), via_local_proxy, consumed_host_private=consumed_host_private)
        is None
    )


@pytest.mark.parametrize("http_status", [None, 402, 429, 503, 529.0, "529"])
def test_only_an_integer_http_529_triggers_failover(http_status: int | None) -> None:
    assert (
        FailoverController(_OPTED_IN).select_failover(
            (_FALLBACK,), source_provider_id="cloud_a", http_status=http_status, consumed_host_private=False
        )
        is None
    )


def test_529_selects_first_affordable_different_cloud_and_forces_fresh_session() -> None:
    same_cloud = replace(_FALLBACK, slot=ProviderSlot("other_runtime", "same-cloud"), provider_id="cloud_a")
    unknown_tariff = replace(_FALLBACK, pricing=None)
    too_expensive = replace(_FALLBACK, estimated_usage=estimate_from_prompt(21, 10))
    cheaper = replace(
        _FALLBACK, slot=ProviderSlot("third", "cheaper"), estimated_usage=estimate_from_prompt(1, 1)
    )

    decision = FailoverController(_OPTED_IN).select_failover(
        (same_cloud, unknown_tariff, too_expensive, _FALLBACK, cheaper),
        source_provider_id="cloud_a",
        http_status=529,
        consumed_host_private=False,
    )

    assert decision is not None
    assert decision.slot == _FALLBACK.slot
    assert decision.provider_id == "cloud_b"
    assert decision.estimated_cost_usd_micros == 70
    assert decision.via_local_proxy is False
    assert decision.session == Fresh("ROUTE_CHANGED", handoff=False)


def test_local_proxy_returns_a_fresh_session_without_a_provider_error() -> None:
    free_tariff = replace(_TARIFF, input_per_mtok_usd=Decimal(0), output_per_mtok_usd=Decimal(0))
    proxy = replace(_FALLBACK, slot=ProviderSlot("proxy_runtime", "local"), pricing=free_tariff)
    controller = FailoverController(replace(_OPTED_IN, cost_ceiling_usd_micros=0))

    decision = controller.route_local_proxy(proxy, consumed_host_private=False)

    assert decision is not None
    assert decision.slot == proxy.slot
    assert decision.estimated_cost_usd_micros == 0
    assert decision.via_local_proxy is True
    assert decision.session == Fresh("ROUTE_CHANGED", handoff=False)
