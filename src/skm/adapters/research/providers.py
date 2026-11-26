"""Bounded HTTPS research adapters. Provider replies are data and are never executed."""

from __future__ import annotations

import json
from hashlib import sha256
from time import monotonic
from typing import TYPE_CHECKING, Any, Protocol, override
from urllib.parse import urlsplit

from skm.adapters.research.command import admit_reply, array_value, object_value
from skm.adapters.research.retry import SourceBusy, SourceFailed
from skm.modules.context.domain.research import RawDocument, RawSourceReply, ResearchTier, SourceCapability
from skm.modules.context.domain.research_rules import DEFAULT_DENY, url_problem

if TYPE_CHECKING:
    from collections.abc import Callable

    from skm.kernel.cancel import CancelToken
    from skm.modules.context.domain.research import ResearchSourceConfig, SourceQuery

__all__ = [
    "Context7ResearchSource",
    "PerplexityApiResearchSource",
    "PerplexityWebResearchSource",
    "WebSearchResearchSource",
]


def _string(value: Any) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise SourceFailed()
    return value


def _document(row: dict[str, Any], origin: str, title: str, excerpt: str) -> RawDocument:
    url = _string(row[origin])
    heading = _string(row[title]) if row.get(title) else url
    text = _string(row[excerpt]) if row.get(excerpt) else None
    return RawDocument(url, heading, text, {})


class _Transport(Protocol):
    def request(
        self,
        request: tuple[str, str, dict[str, Any]],
        *,
        cancel: CancelToken,
        timeout: float,
        allow_not_found: bool = False,
    ) -> bytes | None: ...


class _Provider:
    tiers = (ResearchTier.EXTERNAL_SEARCH,)
    kind: str

    def __init__(
        self,
        transport: _Transport,
        *,
        credential: Callable[[str], str | None] = lambda _name: None,
    ) -> None:
        self._transport = transport
        self._credential = credential

    def _headers(
        self, variable: str, header: str = "Authorization", *, prefix: str = "Bearer "
    ) -> dict[str, str]:
        key = self._credential(variable)
        if not key or any(not 33 <= ord(char) <= 126 for char in key):
            raise SourceFailed()
        return {header: prefix + key}

    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        if (
            config.kind != self.kind
            or config.tier not in self.tiers
            or config.capabilities != frozenset({SourceCapability.SEARCH})
            or config.argv
            or config.env_allow
            or config.roots
            or config.reads_checkout
            or (config.endpoint is not None and self.kind != "perplexity_web")
            or not 0 < config.timeout_seconds <= 3600
        ):
            return ("provider_config",)
        return ()

    def request(self, config: ResearchSourceConfig, query: SourceQuery) -> tuple[str, str, dict[str, Any]]:
        raise NotImplementedError

    def documents(self, payload: dict[str, Any]) -> list[RawDocument]:
        raise NotImplementedError

    def search(
        self, config: ResearchSourceConfig, query: SourceQuery, *, cancel: CancelToken
    ) -> RawSourceReply:
        cancel.raise_if_cancelled()
        if self.validate_config(config):
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        deadline = monotonic() + config.timeout_seconds
        try:
            raw = self._transport.request(
                self.request(config, query),
                cancel=cancel,
                timeout=config.timeout_seconds,
                allow_not_found=self.kind == "context7",
            )
            if raw is None:
                return RawSourceReply((), None, (), {"requests": 1}, "sha256:" + sha256(b"").hexdigest())
            cancel.raise_if_cancelled()
            # Provider output cannot invent repository provenance or trigger URL fetches.
            documents = [
                doc
                for doc in self.documents(object_value(json.loads(raw)))
                if doc.origin.startswith(("http://", "https://"))
                and len(doc.origin) <= 2000
                and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in doc.origin)
            ]
        except TimeoutError:
            raise SourceBusy("Research provider timed out or is temporarily unavailable") from None
        except SourceFailed:
            raise
        except (ValueError, KeyError, TypeError, RecursionError):
            raise SourceFailed() from None
        return admit_reply(
            RawSourceReply(tuple(documents), None, (), {"requests": 1}, "sha256:" + sha256(raw).hexdigest()),
            config,
            query,
            cancel=cancel,
            timeout=max(0.001, deadline - monotonic()),
        )


class Context7ResearchSource(_Provider):
    kind = "context7"
    tiers = (ResearchTier.LOCAL_DOCS, ResearchTier.EXTERNAL_SEARCH)

    @override
    def request(self, config: ResearchSourceConfig, query: SourceQuery) -> tuple[str, str, dict[str, Any]]:
        return (
            "GET",
            "https://context7.com/api/v3/search",
            {
                "params": {"query": query.text, "type": "json"},
                "headers": self._headers("CONTEXT7_API_KEY"),
            },
        )

    @override
    def documents(self, payload: dict[str, Any]) -> list[RawDocument]:
        ranked: list[tuple[int, RawDocument]] = []
        for item in array_value(payload["codeSnippets"]):
            row = object_value(item)
            examples = [_string(object_value(code)["code"]) for code in array_value(row["codeList"])]
            body = "\n\n".join((str(row.get("codeDescription") or ""), *examples))
            ranked.append(
                (int(row["rank"]), RawDocument(_string(row["codeId"]), _string(row["codeTitle"]), body, {}))
            )
        for item in array_value(payload["infoSnippets"]):
            row = object_value(item)
            ranked.append((int(row["rank"]), _document(row, "pageId", "breadcrumb", "content")))
        return [doc for _, doc in sorted(ranked, key=lambda entry: entry[0])]


class PerplexityApiResearchSource(_Provider):
    kind = "perplexity_api"

    @override
    def request(self, config: ResearchSourceConfig, query: SourceQuery) -> tuple[str, str, dict[str, Any]]:
        return (
            "POST",
            "https://api.perplexity.ai/search",
            {
                "json": {"query": query.text, "max_results": min(query.max_documents, 20)},
                "headers": self._headers("PERPLEXITY_API_KEY"),
            },
        )

    @override
    def documents(self, payload: dict[str, Any]) -> list[RawDocument]:
        return [
            _document(object_value(row), "url", "title", "snippet") for row in array_value(payload["results"])
        ]


class PerplexityWebResearchSource(_Provider):
    """Send a query to an operator-managed, separately isolated browser broker."""

    kind = "perplexity_web"
    tiers = (ResearchTier.EXTERNAL_SEARCH, ResearchTier.DEEP_RESEARCH)

    @override
    def validate_config(self, config: ResearchSourceConfig) -> tuple[str, ...]:
        problems = super().validate_config(config)
        endpoint = config.endpoint
        if not endpoint or not endpoint.startswith("https://") or url_problem(endpoint, (), DEFAULT_DENY):
            return (*problems, "endpoint")
        url = urlsplit(endpoint)
        if url.query or url.fragment or url.username is not None or url.password is not None:
            return (*problems, "endpoint")
        return problems

    @override
    def request(self, config: ResearchSourceConfig, query: SourceQuery) -> tuple[str, str, dict[str, Any]]:
        return (
            "POST",
            config.endpoint or "",
            {
                "json": {"query": query.text, "max_documents": query.max_documents, "depth": query.depth},
            },
        )

    @override
    def documents(self, payload: dict[str, Any]) -> list[RawDocument]:
        return [
            _document(object_value(row), "url", "title", "text") for row in array_value(payload["documents"])
        ]


class WebSearchResearchSource(_Provider):
    kind = "web_search"

    @override
    def request(self, config: ResearchSourceConfig, query: SourceQuery) -> tuple[str, str, dict[str, Any]]:
        if len(query.text) > 600 or len(query.text.split()) > 75:
            raise SourceFailed("RESEARCH_SOURCE_INVALID")
        return (
            "GET",
            "https://api.search.brave.com/res/v1/web/search",
            {
                "params": {
                    "q": query.text,
                    "count": min(query.max_documents, 20),
                    "text_decorations": "false",
                },
                "headers": self._headers("BRAVE_SEARCH_API_KEY", "X-Subscription-Token", prefix=""),
            },
        )

    @override
    def documents(self, payload: dict[str, Any]) -> list[RawDocument]:
        web = object_value(payload.get("web", {}))
        return [
            _document(object_value(row), "url", "title", "description")
            for row in array_value(web.get("results", []))
        ]
