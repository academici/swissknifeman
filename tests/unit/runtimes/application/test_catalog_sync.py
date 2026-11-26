"""Offline catalog sync: four sources, null tariffs and the staging trust policy."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.modules.runtimes import public as runtimes

TODAY = date(2026, 11, 23)
PROVIDERS = {
    "anthropic": "claude_code",
    "openai": "codex",
    "x-ai": "grok",
    "xai": "grok",
    "grok": "grok",
    "cursor": "cursor",
}


class MapTransport:
    """In-memory documents. A missing URL fails closed without a socket."""

    def __init__(self, documents: dict[str, str]) -> None:
        self.documents = documents
        self.calls: list[str] = []

    def get_text(self, url: str) -> str:
        self.calls.append(url)
        try:
            return self.documents[url]
        except KeyError as exc:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE, "document not staged", details={"url": url}
            ) from exc


def _models_dev() -> str:
    return json.dumps(
        {
            "anthropic": {
                "models": {
                    "claude-haiku": {
                        "name": "Claude Haiku",
                        "cost": {"input": "0.25", "output": "1.25"},
                        "limit": {"context": 200000, "output": 8192},
                    },
                    "claude-unpriced": {
                        "name": "Claude Unpriced",
                        "cost": {},
                        "limit": {"context": 200000},
                    },
                }
            },
            "ignored-provider": {"models": {"nope": {"name": "Nope"}}},
        }
    )


def _openrouter_models() -> str:
    return json.dumps(
        {
            "data": [
                {
                    "id": "x-ai/grok-4",
                    "name": "Grok 4",
                    "context_length": 131072,
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                    "top_provider": {"max_completion_tokens": 4096},
                },
                {
                    "id": "openai/gpt-missing-tariff",
                    "name": "GPT missing tariff",
                    "context_length": 128000,
                    "pricing": {"prompt": None, "completion": None},
                },
            ]
        }
    )


def _openrouter_endpoints() -> str:
    return json.dumps(
        {
            "data": {
                "endpoints": [
                    {"pricing": {"prompt": "0.000002", "completion": "0.000010"}},
                ]
            }
        }
    )


def _v1_models() -> str:
    return json.dumps({"data": [{"id": "gpt-luna"}, {"id": "gpt-zero-tariff"}]})


def _documents() -> dict[str, str]:
    return {
        "https://models.dev/api.json": _models_dev(),
        "https://openrouter.ai/api/v1/models": _openrouter_models(),
        "https://openrouter.ai/api/v1/models/x-ai/grok-4/endpoints": _openrouter_endpoints(),
        "https://openrouter.ai/api/v1/models/openai/gpt-missing-tariff/endpoints": json.dumps(
            {"data": {"endpoints": []}}
        ),
        "https://api.openai.com/v1/models": _v1_models(),
    }


def test_four_sources_stage_offline_and_keep_missing_tariffs_null() -> None:
    transport = MapTransport(_documents())
    providers = {**PROVIDERS, "openai": "openai_cli"}
    report = runtimes.ModelCatalogSyncJob(
        transport=transport,
        today=TODAY,
        provider_runtimes=providers,
    ).run()

    by_source = {
        source: [row.candidate for row in report.staged if row.candidate.source_id is source]
        for source in runtimes.CatalogSourceId
    }
    assert set(by_source) == set(runtimes.CatalogSourceId)
    assert [row.model_id for row in by_source[runtimes.CatalogSourceId.MODELS_DEV]] == [
        "claude-haiku",
        "claude-unpriced",
    ]
    haiku = by_source[runtimes.CatalogSourceId.MODELS_DEV][0]
    assert haiku.pricing == runtimes.PriceQuote(
        Decimal("0.25"), Decimal("1.25"), verified_at=TODAY, source="https://models.dev/api.json"
    )
    assert by_source[runtimes.CatalogSourceId.MODELS_DEV][1].pricing is None

    grok = by_source[runtimes.CatalogSourceId.OPENROUTER][0]
    assert grok.runtime_id == "grok"
    assert grok.pricing is not None
    assert grok.pricing.input_per_mtok_usd == Decimal("2.000000")
    assert grok.pricing.output_per_mtok_usd == Decimal("10.000000")
    missing = by_source[runtimes.CatalogSourceId.OPENROUTER][1]
    assert missing.pricing is None
    assert missing.pricing != runtimes.PriceQuote(Decimal(0), Decimal(0), verified_at=TODAY, source="x")

    listed = by_source[runtimes.CatalogSourceId.V1_MODELS]
    assert [row.model_id for row in listed] == ["gpt-luna", "gpt-zero-tariff"]
    assert {row.runtime_id for row in listed} == {providers["openai"]}
    assert all(row.pricing is None for row in listed)

    fallback = by_source[runtimes.CatalogSourceId.FALLBACK_GENERALIZATIONS]
    assert {row.runtime_id for row in fallback} == set(providers.values())
    assert all(row.pricing is None and row.trust is runtimes.CandidateTrust.EXTERNAL for row in fallback)
    assert "https://api.openai.com/v1/models" in transport.calls
    assert all(not url.startswith("http://") for url in transport.calls)


def test_a_failing_source_is_recorded_and_the_other_sources_still_stage() -> None:
    documents = _documents()
    del documents["https://models.dev/api.json"]
    adapters = (
        runtimes.default_adapters()[0],
        runtimes.default_adapters()[1],
        runtimes.V1ModelsSource(runtime_id="codex"),
        runtimes.default_adapters()[3],
    )
    report = runtimes.ModelCatalogSyncJob(
        transport=MapTransport(documents), today=TODAY, adapters=adapters, provider_runtimes=PROVIDERS
    ).run()
    assert report.source_errors == ((runtimes.CatalogSourceId.MODELS_DEV, "document not staged"),)
    assert runtimes.CatalogSourceId.V1_MODELS in {row.candidate.source_id for row in report.staged}


def test_external_candidates_stay_staged_and_only_operator_rows_are_active() -> None:
    external = runtimes.FallbackGeneralizationsSource().fetch(
        MapTransport({}), today=TODAY, provider_runtimes=PROVIDERS
    )[0]
    trusted = runtimes.CatalogCandidate(
        source_id=runtimes.CatalogSourceId.MODELS_DEV,
        runtime_id="codex",
        model_id="operator-model",
        provider_model_id="operator-model",
        display_name="Operator model",
        context_window_tokens=128000,
        classes=frozenset({runtimes.ModelClass.IMPLEMENTATION}),
        verified_at=TODAY,
        source="operator",
        trust=runtimes.CandidateTrust.OPERATOR,
        pricing=None,
    )
    staged = runtimes.stage_candidates((external, trusted))
    assert [(row.candidate.model_id, row.active) for row in staged] == [
        (external.model_id, False),
        ("operator-model", True),
    ]
    with pytest.raises(ValidationFailed) as err:
        runtimes.StagedCandidate(external, active=True)
    assert err.value.code is ErrorCode.SCHEMA_INVALID


def test_zero_is_a_real_tariff_and_a_blank_tariff_stays_absent() -> None:
    body = json.dumps(
        {
            "data": [
                {
                    "id": "openai/gpt-free",
                    "name": "GPT free",
                    "context_length": 8000,
                    "pricing": {"prompt": "0", "completion": "0"},
                }
            ]
        }
    )
    source = runtimes.OpenRouterSource()
    rows = source.fetch(
        MapTransport(
            {
                source.models_url: body,
                source.endpoints_template.format(id="openai/gpt-free"): json.dumps(
                    {"data": {"endpoints": []}}
                ),
            }
        ),
        today=TODAY,
        provider_runtimes=PROVIDERS,
    )
    assert rows[0].pricing is not None
    assert rows[0].pricing.input_per_mtok_usd == Decimal(0)
    assert rows[0].pricing.output_per_mtok_usd == Decimal(0)
