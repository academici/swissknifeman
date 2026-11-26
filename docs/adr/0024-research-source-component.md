# ADR 0024: Research sources are a separate plugin component kind

Status: accepted
Date: 2026-10-25

## Context
The researcher stage and `skm research query` (P09.09, audit gaps G3/G39) ask external sources (local files, a command
speaking the legacy `text-v0`/`json-v1` protocol, an MCP server over stdio, later HTTP search providers) and store
documents, citations and limitations with a trust class, URL policy and a TTL cache. ADR 0022 fixes the set of plugin
component kinds; adding a kind is a change of the core and needs an ADR. The nearest existing kind, `knowledge_source`,
feeds the code graph of the optional `knowledge` module and has a different contract.

## Decision
Add `ComponentKind.RESEARCH_SOURCE = "research_source"` to `skm.plugin_api` (API_VERSION stays 1: the plugin API is not
released yet, so adding a kind is compatible). Contract (`modules/context/ports.py`, marked `@host_gateway`):
`ResearchSource.kind`, `validate_config(config) -> tuple[str, ...]` (problems → `RESEARCH_SOURCE_INVALID`),
`search(config, query, *, cancel) -> RawSourceReply` (raises `SourceBusy` — retryable — or `SourceFailed(code, message)`).
Side: host only; registry `ResearchSourceRegistry` (`HostGateways.research_sources`). Built-in components live in
`adapters/research/` with keys `command`, `filesystem`, `mcp_stdio`; plugin components use the key `<plugin_id>:<name>`.
Only the host operation `context.host.research_query` calls sources; the control plane stores results through
`context.record_research_result` and serves cache lookups through `context.find_research_cache`.

## Alternatives considered
- Reuse `knowledge_source`: rejected — different request/response contract and consumer (mandatory `context` vs
  optional `knowledge`); the code graph can still be a research source of step `codegraph` via `command`/`mcp_stdio`.
- Configuration only (no plugin kind): rejected — HTTP providers need code, and the built-ins should use the same
  interface as plugins (ADR 0022).

## Consequences
The kind is [`ComponentKind.RESEARCH_SOURCE`](../../src/skm/plugin_api/manifest.py), registered from [`bootstrap/builtins.py`](../../src/skm/bootstrap/builtins.py). Error codes are `RESEARCH_SOURCE_UNAVAILABLE`, `RESEARCH_SOURCE_TIMEOUT` and `RESEARCH_SOURCE_INVALID`.

## Compatibility
Additive to plugin API v1 before its first release.

## Verification
`tests/contracts/context/research_source_suite.py` runs against every built-in source and the plugin fixture;
`tests/unit/context/host/test_research_query.py` covers cache hits, busy retries and failures.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

Use typed ctx.gateways.get(ResearchSourceRegistry), as defined by the composition contract, rather than treating the historical HostGateways.research_sources shorthand as an attribute API.

I-09.3 adds the native `codegraph` research source. Its index lifecycle belongs to the `context` host
surface and uses the registered project's checkout binding.

## Project design research

`skm plan research PLAN "question" --json` resolves the plan and checks project research
permission before calling a source. To require design evidence, add an item section with
`id = "design-research"` and title `Design research`. Put one `research-query:<uuid>` per
line in its text using the command's displayed references or the JSON `design_query_ids`.
R15 requires at least one reference and validates every result against current project
and plan policy. Admitted evidence participates in readiness freshness. The existing
`research.need` field controls research during execution.

Use `context.research.profile` at project scope to select host-defined source IDs with
`sources`, limit documents or characters with `max_documents`, `query_max_chars` and
`excerpt_max_chars`, or disable deep research with `allow_deep = false`. An empty
`sources` list disables retrieval. Omitted fields inherit the effective research settings.

Register sources under `context.research.sources` at instance or host scope. Each of the
HTTPS providers supports the `search` capability.

| Kind | Interface | Host credential |
| --- | --- | --- |
| `context7` | [Context7 Search API](https://context7.com/docs/search-api) | `CONTEXT7_API_KEY` |
| `perplexity_api` | [Perplexity Search API](https://docs.perplexity.ai/api-reference/search-post) | `PERPLEXITY_API_KEY` |
| `web_search` | [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get) | `BRAVE_SEARCH_API_KEY` |
| `perplexity_web` | Operator-managed browser broker at the source's HTTPS `endpoint` | Browser credentials stay in the broker |
| `codegraph` | Indexed local checkout through the native CodeGraph CLI | None |

Deploy the browser broker separately with an isolated browser profile and no SKM checkout,
control-plane credential, or host mounts. The broker accepts a JSON POST with `query`,
`depth` and `max_documents` and returns `{"documents":[{"url":"https://…","title":"…","text":"…"}]}`.
The SKM adapter uses a fresh HTTPS client for each call, rejects redirects, and sends no
browser credentials or checkout metadata. It treats every broker document as third-party
content. D4 labels third-party documents `THIRD_PARTY` and labels external and repository
retrievals `EXTERNAL` in prompts. Titles, URLs, queries, excerpts, and claims render inside fences.
