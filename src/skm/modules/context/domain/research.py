"""Research contracts and deterministic ledger codecs (context §§4.6, 11)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from skm.kernel.json_types import JsonObject

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Literal

    from skm.kernel.json_types import JsonScalar
    from skm.modules.artifacts.public import StagedBlobRef
    from skm.modules.context.domain.contracts import Digest


class ResearchTier(StrEnum):
    LOCAL_DOCS = "local_docs"
    CODEGRAPH = "codegraph"
    EXTERNAL_SEARCH = "external_search"
    DEEP_RESEARCH = "deep_research"


class SourceCapability(StrEnum):
    SEARCH = "search"
    CITATIONS = "citations"
    SYNTHESIS = "synthesis"
    DEEP = "deep"


class DocumentTrust(StrEnum):
    REPOSITORY = "repository"
    EXTERNAL = "external"
    THIRD_PARTY = "third_party"


@dataclass(frozen=True, slots=True)
class ResearchError:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ResearchSourceConfig:
    source_id: str
    kind: str
    tier: ResearchTier
    capabilities: frozenset[SourceCapability]
    protocol: Literal["text-v0", "json-v1"]
    argv: tuple[str, ...]
    tool: str
    roots: tuple[str, ...]
    url_allow: tuple[str, ...]
    timeout_seconds: int
    concurrency: int
    order: int
    ttl_seconds: int
    trust_cap: DocumentTrust
    classification: str
    env_allow: tuple[str, ...]
    config_digest: Digest
    reads_checkout: bool = False
    endpoint: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchQuerySpec:
    text: str
    sources: tuple[str, ...]
    depth: Literal["standard", "deep"]
    max_documents: int
    use_cache: bool
    save_as_material: bool


@dataclass(frozen=True, slots=True)
class SourceQuery:
    text: str
    max_documents: int
    depth: str
    mounts: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class RawDocument:
    origin: str
    title: str
    text: str | None
    locator: Mapping[str, JsonScalar]


@dataclass(frozen=True, slots=True)
class RawSourceReply:
    documents: tuple[RawDocument, ...]
    answer_text: str | None
    claims: tuple[tuple[str, tuple[str, ...]], ...]
    usage: Mapping[str, int | str] | None
    raw_digest: Digest


@dataclass(frozen=True, slots=True)
class ResearchDocument:
    document_id: str
    origin: str
    url: str | None
    title: str
    retrieved_at: datetime
    content_digest: Digest | None
    locator: Mapping[str, JsonScalar]
    excerpt: str
    trust_class: DocumentTrust
    classification: str
    staged_blob: StagedBlobRef | None


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    document_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Citation:
    claim_index: int
    document_id: str
    quote: str | None


@dataclass(frozen=True, slots=True)
class ResearchUsage:
    requests: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd_micros: int | None


@dataclass(frozen=True, slots=True)
class ResearchResult:
    query_id: str
    source_id: str
    kind: str
    tier: ResearchTier
    retrieved_at: datetime
    status: Literal["ok", "empty", "error"]
    error: ResearchError | None
    documents: tuple[ResearchDocument, ...]
    citations: tuple[Citation, ...]
    claims: tuple[Claim, ...]
    limitations: tuple[str, ...]
    usage: ResearchUsage | None
    usage_complete: bool
    cache_status: Literal["miss", "hit", "bypass"]
    cache_key: Digest
    query_digest: Digest
    source_config_digest: Digest
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ResearchBatch:
    query_text: str
    query_digest: Digest
    results: tuple[ResearchResult, ...]


@dataclass(frozen=True, slots=True)
class ResearchItem:
    step_ref: str
    query: str
    claims: tuple[Claim, ...]
    unknowns: tuple[str, ...]
    contradictions: tuple[str, ...]
    documents: tuple[ResearchDocument, ...]


RESEARCH_LADDER = (
    ResearchTier.LOCAL_DOCS,
    ResearchTier.CODEGRAPH,
    ResearchTier.EXTERNAL_SEARCH,
    ResearchTier.DEEP_RESEARCH,
)


def document_from_json(raw: dict[str, Any]) -> ResearchDocument:
    return ResearchDocument(
        document_id=raw["document_id"],
        origin=raw["origin"],
        url=raw["url"],
        title=raw["title"],
        retrieved_at=datetime.fromisoformat(raw["retrieved_at"]),
        content_digest=raw["content_digest"],
        locator=raw["locator"],
        excerpt=raw["excerpt"],
        trust_class=DocumentTrust(raw["trust_class"]),
        classification=raw["classification"],
        staged_blob=raw.get("staged_blob"),
    )


def result_from_json(raw: dict[str, Any]) -> ResearchResult:
    return ResearchResult(
        query_id=raw["query_id"],
        source_id=raw["source_id"],
        kind=raw["kind"],
        tier=ResearchTier(raw["tier"]),
        retrieved_at=datetime.fromisoformat(raw["retrieved_at"]),
        status=raw["status"],
        error=ResearchError(**raw["error"]) if raw["error"] else None,
        documents=tuple(document_from_json(d) for d in raw["documents"]),
        citations=tuple(Citation(**c) for c in raw["citations"]),
        claims=tuple(Claim(c["text"], tuple(c["document_ids"])) for c in raw["claims"]),
        limitations=tuple(raw["limitations"]),
        usage=ResearchUsage(**raw["usage"]) if raw["usage"] is not None else None,
        usage_complete=raw["usage_complete"],
        cache_status=raw["cache_status"],
        cache_key=raw["cache_key"],
        query_digest=raw["query_digest"],
        source_config_digest=raw["source_config_digest"],
        expires_at=datetime.fromisoformat(raw["expires_at"]) if raw["expires_at"] else None,
    )


def result_to_json(result: ResearchResult) -> JsonObject:
    """The generated wire shape, without ledger-only scope/provenance fields."""

    def encode(value: Any) -> Any:
        if isinstance(value, StrEnum):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: encode(v) for k, v in cast("dict[str, Any]", value).items()}
        if isinstance(value, tuple | list):
            return [encode(v) for v in cast("list[Any]", value)]
        return value

    return cast("JsonObject", encode(asdict(result)))
