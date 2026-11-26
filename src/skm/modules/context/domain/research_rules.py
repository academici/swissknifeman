"""Pure research planning, admission and cache identities (context §5.14)."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from ipaddress import ip_address
from typing import Any, cast
from urllib.parse import urlsplit

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.context.domain.research import (
    RESEARCH_LADDER,
    Citation,
    Claim,
    DocumentTrust,
    RawDocument,
    RawSourceReply,
    ResearchDocument,
    ResearchQuerySpec,
    ResearchResult,
    ResearchSourceConfig,
    ResearchTier,
    ResearchUsage,
    SourceCapability,
    SourceQuery,
)

HTTPS_RESEARCH_KINDS = frozenset({"context7", "perplexity_api", "perplexity_web", "web_search"})

CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
TRUST = (DocumentTrust.THIRD_PARTY, DocumentTrust.EXTERNAL, DocumentTrust.REPOSITORY)
LIMITATIONS = frozenset(
    (
        "source_unavailable",
        "source_timeout",
        "ladder_stopped_at",
        "deep_research_disabled",
        "query_redacted",
        "url_denied",
        "url_not_allowed",
        "truncated_to_max_documents",
        "content_not_retrieved",
        "claim_without_document",
        "answer_without_citations",
        "classification_capped",
        "cache_bypassed_classification",
    )
)
DEFAULT_DENY = ("localhost", "127.*", "10.*", "172.16.*", "192.168.*", "169.254.*", "*.internal", "*.local")


def invalid(reason: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.SCHEMA_INVALID, reason, details={"reason": reason})


def normalize_query(text: str, *, query_max_chars: int = 4000) -> str:
    text = unicodedata.normalize("NFC", " ".join(text.split()))
    if not text:
        raise invalid("query_empty")
    if len(text) > query_max_chars:
        raise invalid("query_too_long")
    return text


def digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def query_digest(text: str) -> str:
    return digest_text(normalize_query(text, query_max_chars=20000).casefold())


def cache_key(inputs: JsonObject) -> str:
    return digest_text(json.dumps(inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def source_config_digest(config: ResearchSourceConfig, adapter_version: str) -> str:
    raw = asdict(config)
    raw.pop("config_digest")
    if config.endpoint is None:
        raw.pop("endpoint")
    raw["capabilities"] = sorted(config.capabilities)
    raw["adapter_version"] = adapter_version
    return cache_key(cast("JsonObject", raw))


def checkout_digest(states: Mapping[str, tuple[str, str] | None]) -> str | None:
    if not states or any(not state or not all(state) for state in states.values()):
        return None
    return cache_key({mount: list(state) for mount, state in states.items() if state is not None})


def source_config(
    source_id: str, raw: Mapping[str, Any], settings: Mapping[str, Any]
) -> ResearchSourceConfig:
    cache = settings.get("cache", {})
    config = ResearchSourceConfig(
        source_id=source_id,
        kind=raw["kind"],
        tier=ResearchTier(raw["tier"]),
        capabilities=frozenset(SourceCapability(c) for c in raw.get("capabilities", ("search",))),
        protocol=raw.get("protocol") or "json-v1",
        argv=tuple(raw.get("argv") or ()),
        tool=raw.get("tool") or "search",
        roots=tuple(raw.get("roots") or ()),
        url_allow=tuple(raw.get("url_allow") or ()),
        timeout_seconds=raw.get("timeout_seconds") or 120,
        concurrency=raw.get("concurrency") or 1,
        order=raw["order"] if raw.get("order") is not None else 100,
        ttl_seconds=raw.get("ttl_seconds") or cache.get("default_ttl_seconds", 86400),
        trust_cap=(
            DocumentTrust.THIRD_PARTY
            if raw["kind"] == "perplexity_web"
            else DocumentTrust(raw.get("trust_cap") or "external")
        ),
        classification=raw.get("classification") or "internal",
        env_allow=tuple(raw.get("env_allow") or ()),
        config_digest="",
        reads_checkout=raw["kind"] == "codegraph" or bool(raw.get("reads_checkout", False)),
        endpoint=raw.get("endpoint"),
    )
    return replace(config, config_digest=source_config_digest(config, raw.get("adapter_version", "unknown")))


PROFILE_FIELDS = ("sources", "max_documents", "query_max_chars", "excerpt_max_chars", "allow_deep")


def profile_allows(profile: Mapping[str, Any], source_id: str) -> bool:
    sources = profile.get("sources")
    return sources is None or source_id in sources


def profile_limits(settings: JsonObject, profile: Mapping[str, Any]) -> JsonObject:
    """A project profile can only reduce the effective work policy limits."""
    effective = dict(settings)
    for key in ("max_documents", "query_max_chars", "excerpt_max_chars"):
        if profile.get(key) is not None:
            effective[key] = min(cast("int", settings[key]), profile[key])
    if profile.get("allow_deep") is False:
        effective["allow_deep"] = False
    return effective


def plan_sources(settings: JsonObject, spec: ResearchQuerySpec) -> tuple[ResearchSourceConfig, ...]:
    values = cast("dict[str, Any]", settings)
    available = values.get("sources", {})
    disabled = set(values.get("disabled_sources", ()))
    candidates = {
        key: raw
        for key, raw in available.items()
        if key not in disabled and profile_allows(values.get("profile") or {}, key)
    }
    if spec.sources:
        missing = next((key for key in spec.sources if key not in candidates), None)
        if missing is not None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "unknown research source",
                details={"kind": "research_source", "source_id": missing},
            )
        selected = tuple(source_config(key, candidates[key], values) for key in spec.sources)
        return tuple(
            c
            for c in selected
            if c.tier is not ResearchTier.DEEP_RESEARCH
            or (spec.depth == "deep" and values.get("allow_deep", False))
        )
    configs = [source_config(key, raw, values) for key, raw in candidates.items()]
    return tuple(
        sorted(
            (
                c
                for c in configs
                if c.tier is not ResearchTier.DEEP_RESEARCH
                or (spec.depth == "deep" and values.get("allow_deep", False))
            ),
            key=lambda c: (RESEARCH_LADDER.index(c.tier), c.order, c.source_id),
        )
    )


def plan_limitations(settings: JsonObject, spec: ResearchQuerySpec) -> tuple[str, ...]:
    values = cast("dict[str, Any]", settings)
    blocked = spec.depth != "deep" or not values.get("allow_deep", False)
    sources = values.get("sources", {})
    ids = spec.sources or tuple(sources)
    return (
        ("deep_research_disabled",)
        if blocked
        and any(
            key not in values.get("disabled_sources", ())
            and profile_allows(values.get("profile") or {}, key)
            and sources.get(key, {}).get("tier") == "deep_research"
            for key in ids
        )
        else ()
    )


def ladder_stop(results: Sequence[ResearchResult], tier: ResearchTier, *, min_documents: int) -> str | None:
    if sum(len(r.documents) for r in results if r.status == "ok") >= min_documents:
        return "ladder_stopped_at:" + tier.value
    return None


def url_problem(url: str, allow: Sequence[str], deny: Sequence[str]) -> str | None:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".").lower().encode("idna").decode("ascii")
        port = parsed.port
    except (ValueError, UnicodeError):
        return "url_denied:invalid"
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
    ):
        return "url_denied:" + (host or "invalid")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if (address is not None and not address.is_global) or any(fnmatchcase(host, p.lower()) for p in deny):
        return "url_denied:" + host
    if allow and not any(fnmatchcase(host, p.lower()) for p in allow):
        return "url_not_allowed:" + host
    return None


def url_allowed(url: str, allow: Sequence[str], deny: Sequence[str]) -> bool:
    return url_problem(url, allow, deny) is None


def document_urls_allowed(doc: ResearchDocument, allow: Sequence[str], deny: Sequence[str]) -> bool:
    """Check both explicit URL and network origin, including when the optional URL is absent."""
    urls = [doc.url] if doc.url is not None else []
    if not doc.origin.startswith(("repo:", "file:", "mcp:", "answer:")):
        urls.append(doc.origin)
    return all(url_allowed(url, allow, deny) for url in urls)


def origin_trust(origin: str) -> DocumentTrust:
    return DocumentTrust.REPOSITORY if origin.startswith(("repo:", "file:")) else DocumentTrust.EXTERNAL


def _usage(raw: Mapping[str, int | str] | None) -> tuple[ResearchUsage | None, bool]:
    if raw is None:
        return None, False

    def counter(key: str) -> int | None:
        value = raw.get(key)
        return value if type(value) is int and value >= 0 else None

    requests = counter("requests")
    usage = ResearchUsage(
        requests if requests is not None else 1,
        counter("input_tokens"),
        counter("output_tokens"),
        counter("cost_usd_micros"),
    )
    return usage, all(
        raw.get(k) is not None and counter(k) is not None
        for k in ("requests", "input_tokens", "output_tokens", "cost_usd_micros")
    )


def normalize_reply(  # noqa: PLR0912, PLR0913 -- explicit host facts keep normalization free of IO/time/entropy
    reply: RawSourceReply,
    config: ResearchSourceConfig,
    query: SourceQuery,
    *,
    query_id: str,
    now: datetime,
    document_ids: Sequence[str],
    settings: JsonObject,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    checkout_state: str | None = None,
    adapter_version: str = "unknown",
    redact: Callable[[str], str],
) -> ResearchResult:
    values = cast("dict[str, Any]", settings)
    limit = min(query.max_documents, values.get("max_documents", 50), 50)
    if limit < 1 or now.utcoffset() is None:
        raise invalid("invalid_research_bounds")
    raw_docs = list(reply.documents)
    limitations: list[str] = []
    if reply.answer_text is not None and SourceCapability.SYNTHESIS in config.capabilities:
        raw_docs.append(
            RawDocument("answer:" + config.source_id, "Answer: " + config.source_id, reply.answer_text, {})
        )
        if SourceCapability.CITATIONS not in config.capabilities:
            limitations.append("answer_without_citations")
    documents: list[ResearchDocument] = []
    origins: dict[str, str] = {}
    seen: set[str] = set()
    for raw in raw_docs:
        if raw.origin in seen:
            continue
        seen.add(raw.origin)
        origin = redact(raw.origin)
        url = origin if origin.lower().startswith(("http:", "https:")) else None
        if url:
            problem = url_problem(url, config.url_allow, values.get("url_deny", DEFAULT_DENY))
            if problem:
                limitations.append(problem)
                continue
        elif not re.match(r"^(repo:|file:|mcp:|answer:).+", raw.origin):
            limitations.append("source_unavailable:invalid_origin")
            continue
        if len(documents) >= limit:
            limitations.append("truncated_to_max_documents")
            break
        if len(document_ids) <= len(documents):
            raise invalid("document_ids_missing")
        text = redact(raw.text) if raw.text is not None else None
        if text is None:
            limitations.append("content_not_retrieved")
        trust = min((config.trust_cap, origin_trust(raw.origin)), key=TRUST.index)
        documents.append(
            ResearchDocument(
                document_ids[len(documents)],
                origin,
                url,
                redact(raw.title)[:500] or origin[:500],
                now,
                digest_text(text) if text is not None else None,
                {k: redact(v) if isinstance(v, str) else v for k, v in raw.locator.items()},
                (text or "")[: values.get("excerpt_max_chars", 2000)],
                trust,
                config.classification,
                None,
            )
        )
        origins[raw.origin] = documents[-1].document_id
    claims: list[Claim] = []
    citations: list[Citation] = []
    if SourceCapability.CITATIONS in config.capabilities:
        for text, refs in reply.claims:
            if not refs or any(ref not in origins for ref in refs):
                limitations.append("claim_without_document")
                continue
            ids = tuple(dict.fromkeys(origins[ref] for ref in refs))
            citations.extend(Citation(len(claims), did, None) for did in ids)
            claims.append(Claim(redact(text), ids))
    elif reply.claims:
        limitations.append("answer_without_citations")
    config_digest = source_config_digest(config, adapter_version)
    qdigest = query_digest(query.text)
    key = cache_key(
        {
            "workspace_id": str(workspace_id),
            "project_id": str(project_id),
            "source_id": config.source_id,
            "source_config_digest": config_digest,
            "query_digest": qdigest,
            "depth": query.depth,
            "max_documents": limit,
            "excerpt_max_chars": values.get("excerpt_max_chars", 2000),
            "checkout_state": checkout_state
            if config.kind == "filesystem" or config.reads_checkout
            else None,
        }
    )
    cache = values.get("cache", {})
    cacheable = cache.get("enabled", True) and (
        not (config.kind == "filesystem" or config.reads_checkout) or checkout_state is not None
    )
    ttl = min(config.ttl_seconds, cache.get("max_ttl_seconds", 604800))
    usage, complete = _usage(reply.usage)
    result = ResearchResult(
        query_id,
        config.source_id,
        config.kind,
        config.tier,
        now,
        "ok" if documents else "empty",
        None,
        tuple(documents),
        tuple(citations),
        tuple(claims),
        tuple(dict.fromkeys(limitations)),
        usage,
        complete,
        "miss" if cacheable else "bypass",
        key,
        qdigest,
        config_digest,
        now + timedelta(seconds=ttl) if cacheable and ttl > 0 else None,
    )
    problems = validate_result(
        result,
        config=config,
        max_documents=limit,
        excerpt_max_chars=values.get("excerpt_max_chars", 2000),
        url_deny=values.get("url_deny", DEFAULT_DENY),
    )
    if problems:
        raise invalid(problems[0])
    return result


def validate_result(  # noqa: PLR0912 -- independent admission problems are accumulated
    result: ResearchResult,
    *,
    config: ResearchSourceConfig | None = None,
    max_documents: int = 50,
    excerpt_max_chars: int = 2000,
    url_deny: Sequence[str] = DEFAULT_DENY,
) -> tuple[str, ...]:
    problems: list[str] = []
    dates = (result.retrieved_at, *(d.retrieved_at for d in result.documents))
    if result.expires_at is not None:
        dates = (*dates, result.expires_at)
    if any(date.utcoffset() is None for date in dates):
        return ("invalid_timestamp",)
    ids = {d.document_id for d in result.documents}
    if len(ids) != len(result.documents):
        problems.append("document_id_duplicate")
    if len(result.documents) > min(max_documents, 50):
        problems.append("too_many_documents")
    if (result.status == "ok") != bool(result.documents) or (result.status == "error") != (
        result.error is not None
    ):
        problems.append("invalid_status")
    if result.status == "error" and (result.expires_at is not None or result.claims or result.citations):
        problems.append("error_cached")
    if config and (result.kind != config.kind or result.tier != config.tier):
        problems.append("source_provenance_mismatch")
    if result.expires_at is not None and result.expires_at <= result.retrieved_at:
        problems.append("invalid_expiry")
    for doc in result.documents:
        if config and config.kind in HTTPS_RESEARCH_KINDS and doc.url != doc.origin:
            problems.append("source_provenance_mismatch")
        cap = config.trust_cap if config else DocumentTrust.REPOSITORY
        if TRUST.index(doc.trust_class) > min(TRUST.index(cap), TRUST.index(origin_trust(doc.origin))):
            problems.append("trust_raised")
        if doc.classification not in CLASSIFICATIONS or (
            config
            and CLASSIFICATIONS.index(doc.classification) < CLASSIFICATIONS.index(config.classification)
        ):
            problems.append("classification_lowered")
        if len(doc.excerpt) > excerpt_max_chars:
            problems.append("excerpt_too_long")
        if not document_urls_allowed(doc, config.url_allow if config else (), (*DEFAULT_DENY, *url_deny)):
            problems.append("url_denied")
    for claim in result.claims:
        if not claim.document_ids or not set(claim.document_ids) <= ids:
            problems.append("claim_without_document")  # noqa: PERF401 -- accumulate heterogeneous problems
    for citation in result.citations:
        if (
            citation.document_id not in ids
            or not 0 <= citation.claim_index < len(result.claims)
            or citation.document_id not in result.claims[citation.claim_index].document_ids
        ):
            problems.append("claim_without_document")  # noqa: PERF401 -- accumulate heterogeneous problems
    if (
        (result.claims or result.citations)
        and config
        and SourceCapability.CITATIONS not in config.capabilities
    ):
        problems.append("answer_without_citations")
    if any(lim.split(":", 1)[0] not in LIMITATIONS for lim in result.limitations):
        problems.append("invalid_limitation")
    return tuple(dict.fromkeys(problems))
