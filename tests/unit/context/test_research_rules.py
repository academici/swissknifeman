"""Research baseline and ench2 cache identities/admission vectors."""

from dataclasses import replace
from datetime import timedelta

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.modules.context.domain.research import (
    Citation,
    Claim,
    DocumentTrust,
    RawDocument,
    RawSourceReply,
    ResearchError,
    ResearchQuerySpec,
    ResearchTier,
)
from skm.modules.context.domain.research_rules import (
    DEFAULT_DENY,
    cache_key,
    checkout_digest,
    digest_text,
    ladder_stop,
    normalize_query,
    plan_limitations,
    plan_sources,
    query_digest,
    source_config_digest,
    url_allowed,
    url_problem,
    validate_result,
)
from unit.context.research_support import IDS, NOW, config, normalized


def spec(**options):
    return ResearchQuerySpec(
        **{
            "text": "q",
            "sources": (),
            "depth": "standard",
            "max_documents": 10,
            "use_cache": True,
            "save_as_material": False,
            **options,
        }
    )


@pytest.mark.parametrize("text", [" Cafe\u0301\t research\n", "Café   research", "\nCafé research\u00a0"])
def test_normalize_nfc_whitespace_and_casefold_digest(text):
    assert normalize_query(text) == "Café research"
    assert query_digest(text) == query_digest("CAFÉ research")
    assert query_digest(text) == digest_text("café research")


@pytest.mark.parametrize(
    ("text", "reason"), [("", "query_empty"), (" \t\n", "query_empty"), ("x" * 101, "query_too_long")]
)
def test_normalization_rejects_empty_and_oversized(text, reason):
    with pytest.raises(ValidationFailed) as error:
        normalize_query(text, query_max_chars=100)
    assert error.value.code is ErrorCode.SCHEMA_INVALID
    assert error.value.details["reason"] == reason


def sources():
    return {
        "sources": {
            "web": {"kind": "command", "tier": "external_search", "order": 0},
            "local-b": {"kind": "filesystem", "tier": "local_docs", "order": 1},
            "local-a": {"kind": "filesystem", "tier": "local_docs", "order": 1},
            "graph": {"kind": "command", "tier": "codegraph"},
            "deep": {"kind": "command", "tier": "deep_research"},
        },
        "disabled_sources": ["local-b"],
    }


def test_ladder_filters_disabled_groups_tiers_and_sorts_deterministically():
    settings = sources()
    assert [c.source_id for c in plan_sources(settings, spec())] == ["local-a", "graph", "web"]
    assert plan_limitations(settings, spec()) == ("deep_research_disabled",)
    settings["allow_deep"] = True
    assert [c.source_id for c in plan_sources(settings, spec(depth="deep"))] == [
        "local-a",
        "graph",
        "web",
        "deep",
    ]
    assert plan_limitations(settings, spec(depth="deep")) == ()
    assert [c.source_id for c in plan_sources(settings, spec(sources=("web", "local-a")))] == [
        "web",
        "local-a",
    ]
    assert plan_sources({}, spec()) == ()
    for sid in ("missing", "local-b"):
        with pytest.raises(NotFound) as error:
            plan_sources(settings, spec(sources=(sid,)))
        assert error.value.details["kind"] == "research_source"


def test_ladder_stops_only_after_enough_ok_documents():
    result = normalized()
    error = replace(
        result,
        status="error",
        error=ResearchError("RESEARCH_SOURCE_UNAVAILABLE", "down"),
        documents=(),
        expires_at=None,
    )
    empty = replace(result, status="empty", documents=())
    assert ladder_stop((error, empty), ResearchTier.LOCAL_DOCS, min_documents=1) is None
    assert ladder_stop((result, error), ResearchTier.CODEGRAPH, min_documents=2) is None
    assert (
        ladder_stop((result, result), ResearchTier.CODEGRAPH, min_documents=2)
        == "ladder_stopped_at:codegraph"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/a",
        "http://127.0.0.1/a",
        "http://10.2.3.4",
        "http://172.31.2.3/a",
        "http://192.168.2.3",
        "http://169.254.169.254",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "https://thing.internal/a",
        "https://host.local/a",
        "file:///tmp/a",
        "ftp://example.com",
        "http://user:pass@example.com/a",
        "https://example.com:wrong/",
        "https:///missing",
    ],
)
def test_url_policy_refuses_private_internal_or_non_http(url):
    assert not url_allowed(url, (), DEFAULT_DENY)


def test_url_allow_is_narrowing_and_hosts_are_normalized():
    assert url_allowed("https://DOCS.Example.com./a", ("*.example.com",), DEFAULT_DENY)
    assert (
        url_problem("https://elsewhere.com/a", ("*.example.com",), DEFAULT_DENY)
        == "url_not_allowed:elsewhere.com"
    )
    assert not url_allowed("https://localhost/a", ("localhost",), DEFAULT_DENY)


def test_reply_deduplicates_filters_bounds_and_preserves_unknown_content_and_usage():
    reply = RawSourceReply(
        (
            RawDocument("http://127.0.0.1/a", "private", "secret", {}),
            RawDocument("https://example.com/a", "a", None, {}),
            RawDocument("https://example.com/a", "duplicate", "ignored", {}),
            RawDocument("https://example.com/b", "b", "b" * 5000, {}),
            RawDocument("https://example.com/c", "c", "tail", {}),
        ),
        None,
        (),
        None,
        "raw",
    )
    result = normalized(reply, settings={"max_documents": 2, "excerpt_max_chars": 200})
    assert [d.title for d in result.documents] == ["a", "b"]
    assert result.documents[0].content_digest is None
    assert len(result.documents[1].excerpt) == 200
    assert result.documents[1].content_digest == digest_text("b" * 5000)
    assert set(result.limitations) == {
        "url_denied:127.0.0.1",
        "content_not_retrieved",
        "truncated_to_max_documents",
    }
    assert result.usage is None
    assert not result.usage_complete


def test_synthesis_without_citations_is_data_and_has_zero_claims():
    reply = RawSourceReply((), "answer", (("invented", ("unknown",)),), None, "raw")
    result = normalized(reply, cfg=config(capabilities=["synthesis"]))
    assert not result.claims
    assert not result.citations
    assert result.documents[0].origin == "answer:docs"
    assert result.documents[0].trust_class is DocumentTrust.EXTERNAL
    assert "answer_without_citations" in result.limitations


def test_claims_use_only_retained_document_origins_and_create_real_citations():
    origin = "https://example.com/a"
    reply = RawSourceReply(
        (RawDocument(origin, "a", "text", {}),),
        None,
        (("valid", (origin,)), ("invented", ("https://foreign.example/b",))),
        None,
        "raw",
    )
    result = normalized(reply)
    assert result.claims == (Claim("valid", (IDS[0],)),)
    assert result.citations == (Citation(0, IDS[0], None),)
    assert result.limitations == ("claim_without_document",)
    assert validate_result(result, config=config()) == ()


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"claims": (Claim("bad", ("foreign",)),)}, "claim_without_document"),
        ({"claims": (Claim("bad", ()),)}, "claim_without_document"),
        ({"citations": (Citation(0, "foreign", None),)}, "claim_without_document"),
        ({"documents": ()}, "invalid_status"),
        ({"expires_at": NOW - timedelta(seconds=1)}, "invalid_expiry"),
        ({"limitations": ("made_up",)}, "invalid_limitation"),
    ],
)
def test_validation_rejects_foreign_references_and_invalid_state(change, reason):
    assert reason in validate_result(replace(normalized(), **change))


def test_validation_refuses_trust_escalation_and_source_classification_lowering():
    result = normalized()
    doc = result.documents[0]
    assert "trust_raised" in validate_result(result, config=config(trust_cap="external"))
    assert "classification_lowered" in validate_result(result, config=config(classification="restricted"))
    assert "excerpt_too_long" in validate_result(
        replace(result, documents=(replace(doc, excerpt="x" * 2001),))
    )
    external = replace(doc, origin="https://example.com", url="https://example.com")
    assert "trust_raised" in validate_result(replace(result, documents=(external,)))
    assert (
        normalized(cfg=config(trust_cap="third_party")).documents[0].trust_class is DocumentTrust.THIRD_PARTY
    )


def test_errors_never_validate_as_cacheable_success():
    result = replace(
        normalized(), status="error", error=ResearchError("RESEARCH_SOURCE_TIMEOUT", "down"), documents=()
    )
    assert "error_cached" in validate_result(result)
    assert validate_result(replace(result, expires_at=None)) == ()


@pytest.mark.parametrize("url", [None, "https://allowed.example/a"])
@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost/a",
        "http://127.0.0.1/a",
        "https://denied.example/a",
        " http://localhost/a",
        "ftp://example.com",
    ],
)
def test_validation_checks_network_origin_even_if_optional_url_is_absent_or_different(origin, url):
    result = normalized()
    doc = replace(result.documents[0], origin=origin, url=url, trust_class=DocumentTrust.EXTERNAL)
    assert "url_denied" in validate_result(
        replace(result, documents=(doc,)), config=config(), url_deny=["denied.example"]
    )


def test_validation_applies_source_url_allow_to_origin_without_optional_url():
    result = normalized()
    doc = replace(
        result.documents[0], origin="https://example.com/a", url=None, trust_class=DocumentTrust.EXTERNAL
    )
    result = replace(result, documents=(doc,))
    assert validate_result(result, config=config(url_allow=["example.com"])) == ()
    assert "url_denied" in validate_result(result, config=config(url_allow=["other.example"]))


def test_non_network_origin_can_contain_an_embedded_uri():
    result = normalized()
    doc = replace(
        result.documents[0], origin="mcp:docs/https://example.com/a", trust_class=DocumentTrust.EXTERNAL
    )
    assert validate_result(replace(result, documents=(doc,)), config=config()) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("roots", ("repo:docs",)),
        ("argv", ("search", "--flag")),
        ("env_allow", ("PUBLIC_TOKEN",)),
        ("url_allow", ("example.com",)),
        ("reads_checkout", True),
        ("timeout_seconds", 12),
    ],
)
def test_config_digest_covers_every_source_field(field, value):
    cfg = config()
    assert source_config_digest(cfg, "1") != source_config_digest(replace(cfg, **{field: value}), "1")
    assert source_config_digest(cfg, "1") != source_config_digest(cfg, "2")


def test_checkout_cache_changes_with_head_dirty_mount_and_scope():
    state = {"repo": ("head", "clean")}
    digest = checkout_digest(state)
    assert digest != checkout_digest({"repo": ("new-head", "clean")})
    assert digest != checkout_digest({"repo": ("head", "dirty")})
    assert digest != checkout_digest({"other": ("head", "clean")})
    assert checkout_digest({"repo": None}) is None
    assert checkout_digest({}) is None
    assert cache_key({"project_id": "a", "checkout_state": digest}) != cache_key(
        {"project_id": "b", "checkout_state": digest}
    )
    assert cache_key({"a": 1, "b": 2}) == cache_key({"b": 2, "a": 1})
    cfg = config(kind="filesystem")
    uncached = normalized(cfg=cfg)
    assert uncached.expires_at is None
    assert uncached.cache_status == "bypass"
    assert normalized(cfg=cfg, checkout_state=digest).expires_at is not None
    assert (
        normalized(cfg=cfg, checkout_state=digest).cache_key
        != normalized(cfg=cfg, checkout_state=checkout_digest({"repo": ("new", "clean")})).cache_key
    )
    assert normalized(cfg=config(reads_checkout=True)).expires_at is None


def test_ttl_is_bounded_and_usage_unknown_is_never_zero():
    result = normalized(cfg=config(ttl_seconds=10000), settings={"cache": {"max_ttl_seconds": 60}})
    assert result.expires_at == NOW + timedelta(seconds=60)
    result = normalized(RawSourceReply((), None, (), {"requests": 0, "input_tokens": 4}, "raw"))
    assert result.usage is not None
    assert result.usage.requests == 0
    assert result.usage.output_tokens is None
    assert not result.usage_complete
    assert normalized(settings={"cache": {"enabled": False}}).expires_at is None


def test_redaction_precedes_excerpt_digest_and_claim_storage():
    reply = RawSourceReply(
        (RawDocument("repo:repo/a", "a", "password=very-secret-value", {}),), None, (), None, "raw"
    )
    doc = normalized(reply).documents[0]
    assert "very-secret-value" not in doc.excerpt
    assert doc.content_digest == digest_text(doc.excerpt)


def test_project_rag_profile_only_narrows_policy_and_preserves_source_ladder():
    from skm.modules.context.domain.research_rules import profile_limits

    settings = {
        "sources": {
            "docs": {"kind": "context7", "tier": "local_docs"},
            "graph": {"kind": "codegraph", "tier": "codegraph"},
            "web": {"kind": "web_search", "tier": "external_search"},
            "deep": {"kind": "perplexity_web", "tier": "deep_research"},
        },
        "disabled_sources": ["graph"],
        "allow_deep": False,
        "max_documents": 8,
        "query_max_chars": 4000,
        "excerpt_max_chars": 2000,
        "profile": {
            "sources": ["web", "graph", "docs", "deep"],
            "allow_deep": True,
            "max_documents": 50,
            "query_max_chars": 80,
            "excerpt_max_chars": 100,
        },
    }
    effective = profile_limits(settings, settings["profile"])
    assert effective["max_documents"] == 8
    assert effective["query_max_chars"] == 80
    assert effective["excerpt_max_chars"] == 100
    assert effective["allow_deep"] is False
    assert [source.source_id for source in plan_sources(effective, spec(depth="deep"))] == ["docs", "web"]
    with pytest.raises(NotFound):
        plan_sources(effective, spec(sources=("graph",)))
    effective["profile"] = {"sources": []}
    assert plan_sources(effective, spec()) == ()


def test_https_source_cannot_record_repository_provenance():
    source = config(kind="perplexity_web", tier="external_search", trust_cap="repository")
    result = normalized()
    forged = replace(
        result,
        kind=source.kind,
        tier=source.tier,
        documents=(replace(result.documents[0], trust_class=DocumentTrust.THIRD_PARTY),),
    )
    assert "source_provenance_mismatch" in validate_result(forged, config=source)
