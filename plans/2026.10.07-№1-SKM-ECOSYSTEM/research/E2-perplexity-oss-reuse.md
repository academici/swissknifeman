Да — значительную часть экосистемы **не нужно писать самостоятельно**. Оптимальная стратегия: собственными оставить только контракты SKM, модель исполнения, capability negotiation, policy/effect semantics и composition layer; провайдерский gateway, durable execution, MCP/A2A, plugins, telemetry, policy engine, registry и supply-chain собрать из существующих проектов либо заимствовать из них проверенные конструкции.

## Архитектурная позиция

Я бы не строил систему вокруг одного «agent framework». LangGraph, PydanticAI, AutoGen, CrewAI, Semantic Kernel и аналоги полезны как источники реализаций и optional adapters, но ни один из них не должен стать фундаментальным доменным контрактом SKM.

Целевая схема:

```text
                         ┌──────────────────────┐
                         │   Presets / Profiles │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  Orchestration Core  │
                         │  compile / explain   │
                         │  policy / routing    │
                         └──────────┬───────────┘
                                    │ immutable ExecutionPlan
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
        ┌─────────▼────────┐ ┌──────▼───────┐ ┌──────▼─────────┐
        │ Local Engine     │ │ Durable      │ │ Remote Agent   │
        │ subprocess       │ │ Runtime      │ │ A2A            │
        │ container        │ │ Temporal/etc │ │                │
        └─────────┬────────┘ └──────┬───────┘ └──────┬─────────┘
                  │                 │                 │
        ┌─────────▼─────────────────▼─────────────────▼─────────┐
        │                Execution Adapter Layer                │
        │ model APIs | coding agents | MCP tools | shell | git │
        └─────────┬─────────────────────────────────────────────┘
                  │
        ┌─────────▼─────────────────────────────────────────────┐
        │ LiteLLM / direct SDK / MCP / CLI / container / HTTP │
        └───────────────────────────────────────────────────────┘
```

Ключевой принцип: **провайдер, агент и execution backend — разные сущности**.

| Сущность | Примеры | Контракт |
|---|---|---|
| Model provider | Anthropic API, OpenAI API, Gemini API, Bedrock | `ModelProviderPort` |
| Agent runtime | Claude Code, Codex CLI, Gemini CLI, OpenHands | `AgentExecutorPort` |
| Tool provider | MCP server, GitHub, filesystem, browser | `ToolProviderPort` |
| Execution substrate | subprocess, Docker, Kubernetes, remote worker | `ExecutionBackendPort` |
| Durable runtime | Temporal, Restate, DBOS, Hatchet | `WorkflowRuntimePort` |
| Remote agent | A2A-compatible agent | `RemoteAgentPort` |

Если свести всё к одному `Provider`, вскоре в нём окажутся модели, subprocess, sessions, tools, credentials, retries, terminals и durable state. Это будет универсальный интерфейс, который фактически ничего не абстрагирует.

## Что брать готовым

| Область | Основной выбор | Альтернативы | Решение |
|---|---|---|---|
| Multi-provider LLM gateway | [LiteLLM](https://github.com/BerriAI/litellm) | [Portkey Gateway](https://github.com/Portkey-AI/gateway) | Использовать как внешний gateway |
| Typed agent helpers | [PydanticAI](https://github.com/pydantic/pydantic-ai) | [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Подключать внутри adapters |
| Graph orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) | AutoGen, Semantic Kernel | Заимствовать graph/checkpoint patterns |
| Durable workflows | [Temporal](https://github.com/temporalio/temporal) | Restate, DBOS, Hatchet | Temporal — основной production-кандидат |
| MCP | [FastMCP](https://github.com/PrefectHQ/fastmcp) | Official MCP SDK | Использовать |
| Remote agents | [A2A](https://github.com/a2aproject/A2A) | Собственный HTTP protocol | Использовать как внешний bridge |
| Python plugins | [Pluggy](https://github.com/pytest-dev/pluggy) | entry points напрямую | Использовать для trusted plugins |
| Process plugins | [go-plugin](https://github.com/hashicorp/go-plugin) | JSON-RPC subprocess | Заимствовать handshake/lifecycle |
| Sandboxed plugins | [Extism](https://github.com/extism/extism) | [Wasmtime](https://github.com/bytecodealliance/wasmtime) | Вводить позднее |
| Schema generation | [datamodel-code-generator](https://github.com/datamodel-code-generator/datamodel-code-generator) | ручные Pydantic models | Использовать |
| Binary/RPC contracts | [Buf](https://github.com/bufbuild/buf) | OpenAPI/JSON-RPC | Использовать при появлении gRPC |
| Event envelope | [CloudEvents](https://github.com/cloudevents/sdk-python) | собственный envelope | Заимствовать модель |
| Policy engine | [OPA](https://github.com/open-policy-agent/opa) | [Cerbos](https://github.com/cerbos/cerbos) | OPA для общих policies |
| Telemetry conventions | [OpenInference](https://github.com/Arize-ai/openinference) | native OTel GenAI conventions | Использовать поверх OpenTelemetry |
| LLM observability | [Langfuse](https://github.com/langfuse/langfuse) | [Phoenix](https://github.com/Arize-ai/phoenix) | Выбрать один backend |
| Artifact distribution | [ORAS](https://github.com/oras-project/oras) | обычный object storage | OCI для публикуемых artifacts |
| Artifact specification | [OCI Image Spec](https://github.com/opencontainers/image-spec) | собственный формат | Заимствовать descriptor/digest model |
| Signing | [Cosign](https://github.com/sigstore/cosign) | GPG/minisign | Использовать |
| SBOM | [Syft](https://github.com/anchore/syft) | CycloneDX CLI | Использовать |
| Provenance | [in-toto](https://github.com/in-toto/in-toto) | собственные attestations | Использовать формат attestations |
| Dynamic flags | [OpenFeature](https://github.com/open-feature/spec) | собственный feature-flag API | Заимствовать provider abstraction |

## Провайдерский слой

### LiteLLM

[LiteLLM](https://github.com/BerriAI/litellm) уже реализует унифицированный доступ к множеству model APIs, gateway/proxy, маршрутизацию, cost tracking, logging, guardrails и load balancing. Поэтому писать ещё один универсальный OpenAI-compatible proxy внутри SKM экономически бессмысленно.

Но я бы **не использовал LiteLLM как внутренний доменный API**. Лучше:

```text
SKM ModelProviderPort
        │
        ├── LiteLLMProviderAdapter
        ├── AnthropicNativeAdapter
        ├── OpenAINativeAdapter
        ├── GeminiNativeAdapter
        └── LocalOpenAICompatibleAdapter
```

LiteLLM должен быть инфраструктурным компонентом:

```text
SKM -> stable internal port -> LiteLLM adapter -> LiteLLM gateway -> provider
```

Преимущества:

- SKM не зависит от конкретных LiteLLM classes.
- Можно заменить gateway.
- Можно обходить gateway для provider-native функций.
- Можно тестировать adapter через fake implementation.
- Изменения LiteLLM не затрагивают `ExecutionPlan`.
- Provider fallback не смешивается с workflow retry.

### Portkey

[Portkey Gateway](https://github.com/Portkey-AI/gateway) — второй серьёзный референс для gateway-layer: маршрутизация, model abstraction, guardrails и MCP-related возможности входят в область проекта. Его полезно изучать как альтернативную архитектуру, даже если основным runtime будет LiteLLM.

Практическое решение:

- LiteLLM — основной self-hosted gateway candidate.
- Portkey — архитектурный референс и compatibility target.
- Direct SDK adapters — для функций, которые gateway искажает или не поддерживает.
- Gateway никогда не становится владельцем workflow state.
- Gateway retries ограничиваются transport/provider retry.
- Business retry и смена стратегии остаются в orchestration/workflow layer.

### Не нормализовать всё

Плохой интерфейс:

```python
class Provider:
    async def complete(
        self,
        prompt: str,
        model: str,
        tools: list,
        json_schema: dict | None,
    ) -> str: ...
```

Он теряет:

- reasoning configuration;
- cached prompts;
- provider-specific tool semantics;
- computer use;
- multimodal content;
- citations;
- background jobs;
- asynchronous responses;
- batch API;
- native session IDs;
- safety metadata;
- provider usage fields;
- partial streaming events.

Лучше двухуровневая модель:

```python
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping, Protocol


@dataclass(frozen=True)
class Capability:
    id: str
    version: int = 1
    constraints: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple["Message", ...]
    tools: tuple["ToolDefinition", ...] = ()
    response_schema: Mapping[str, Any] | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderBinding:
    provider: str
    model: str
    account: str | None = None
    endpoint: str | None = None


class ModelProviderPort(Protocol):
    async def capabilities(
        self,
        binding: ProviderBinding,
    ) -> frozenset[Capability]: ...

    async def stream(
        self,
        request: ModelRequest,
        binding: ProviderBinding,
        context: "InvocationContext",
    ) -> AsyncIterator["ModelEvent"]: ...
```

`extensions` должен быть namespace-qualified:

```json
{
  "anthropic.cache_control": {
    "mode": "ephemeral"
  },
  "openai.reasoning": {
    "effort": "high"
  }
}
```

Core игнорирует неизвестные extensions, а конкретный adapter валидирует собственное пространство имён.

## Provider middleware

Не следует реализовывать auth, telemetry, retry, quota и caching отдельно в каждом provider adapter. Нужен стандартный middleware pipeline:

```text
Request
  -> request validation
  -> policy check
  -> credential resolution
  -> budget reservation
  -> concurrency limit
  -> rate limiter
  -> circuit breaker
  -> retry policy
  -> provider invocation
  -> response normalization
  -> usage reconciliation
  -> telemetry
  -> audit receipt
```

Интерфейс:

```python
class ProviderMiddleware(Protocol):
    async def invoke(
        self,
        request: ModelRequest,
        context: InvocationContext,
        call_next: "ProviderCall",
    ) -> "ModelResponse": ...
```

Не все middleware должны быть одинаково упорядочены:

- Policy — до выдачи credentials.
- Budget reservation — до invocation.
- Retry — внутри telemetry span либо с отдельным child span на attempt.
- Rate limiter — для каждого физического attempt.
- Idempotency — снаружи retry.
- Cache — после policy, но до provider quota.
- Secret redaction — до exporter.
- Usage reconciliation — после ответа, включая streaming completion.

### Готовые helpers

Для direct adapters разумно использовать:

- [HTTPX](https://github.com/encode/httpx) — async HTTP transport.
- [Tenacity](https://github.com/jd/tenacity) — composable retry.
- [aiolimiter](https://github.com/mjpieters/aiolimiter) — async rate limiting.
- [PyBreaker](https://github.com/danielfm/pybreaker) — circuit breaker.
- [Pydantic](https://github.com/pydantic/pydantic) — boundary validation.
- [Instructor](https://github.com/instructor-ai/instructor) — structured outputs поверх provider SDK.
- [Outlines](https://github.com/dottxt-ai/outlines) — constrained generation.
- [Guardrails](https://github.com/guardrails-ai/guardrails) — validation/guard patterns.

Однако retries нельзя слепо отдавать Tenacity. Retry policy должна учитывать нормализованный error class, idempotency запроса, наличие partial output и provider request ID.

## Ошибки провайдеров

Сделайте отдельную taxonomy, не зависящую от SDK:

```python
from enum import StrEnum


class ProviderErrorClass(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INVALID_REQUEST = "invalid_request"
    CONTENT_POLICY = "content_policy"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    MODEL_UNAVAILABLE = "model_unavailable"
    CONTEXT_LIMIT = "context_limit"
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    PROVIDER_INTERNAL = "provider_internal"
    CANCELLED = "cancelled"
    UNKNOWN_OUTCOME = "unknown_outcome"
```

Структура ошибки:

```python
@dataclass(frozen=True)
class ProviderFailure:
    classification: ProviderErrorClass
    provider: str
    provider_code: str | None
    retryable: bool
    retry_after_ms: int | None
    request_id: str | None
    attempt_consumed_quota: bool | None
    output_may_have_been_produced: bool
    safe_message: str
    diagnostic_artifact: str | None
```

Особенно важен `UNKNOWN_OUTCOME`: transport timeout после отправки запроса не означает, что provider его не выполнил. Автоматический retry может создать второй дорогой вызов или дублировать side effect.

## Coding-agent adapters

Claude Code, Codex CLI и Gemini CLI нельзя моделировать как обычные LLM providers. Это stateful agent runtimes, которые могут:

- читать и изменять workspace;
- запускать команды;
- вызывать MCP tools;
- создавать subprocess;
- поддерживать session/resume;
- возвращать tool and reasoning events;
- требовать interactive approval;
- завершаться с частично применёнными изменениями.

Полезные референсы:

- [OpenAI Codex](https://github.com/openai/codex).
- [Claude Code](https://github.com/anthropics/claude-code).
- [Gemini CLI](https://github.com/google-gemini/gemini-cli).
- [OpenHands](https://github.com/All-Hands-AI/OpenHands).
- [SWE-agent](https://github.com/SWE-agent/SWE-agent).
- [Aider](https://github.com/Aider-AI/aider).
- [Goose](https://github.com/block/goose).
- [Continue](https://github.com/continuedev/continue).

### Правильный контракт

```python
class AgentExecutorPort(Protocol):
    async def inspect(
        self,
        binding: "AgentBinding",
    ) -> "AgentDescriptor": ...

    async def prepare(
        self,
        request: "AgentRunRequest",
    ) -> "PreparedAgentRun": ...

    async def start(
        self,
        prepared: "PreparedAgentRun",
        context: "ExecutionContext",
    ) -> "AgentRunHandle": ...

    async def events(
        self,
        handle: "AgentRunHandle",
        cursor: str | None = None,
    ) -> AsyncIterator["AgentEvent"]: ...

    async def cancel(
        self,
        handle: "AgentRunHandle",
    ) -> "CancellationReceipt": ...

    async def resume(
        self,
        checkpoint: "AgentCheckpoint",
    ) -> "AgentRunHandle": ...
```

Не обещайте `resume`, пока конкретный adapter не доказал capability. У CLI может быть логическая session persistence, но отсутствовать безопасное восстановление процесса после crash.

### Adapter modes

Каждый coding-agent adapter должен объявлять поддерживаемые режимы:

```yaml
execution:
  modes:
    - subprocess
    - container
  interactive_approval: true
  resumable_session: true
  reconnectable_stream: false
  deterministic_replay: false
workspace:
  read: true
  write: true
  git_required: false
tools:
  mcp: true
  shell: true
```

Таким образом orchestrator выбирает agent не по имени, а по требованиям stage.

## Оркестрация агентов

### PydanticAI

[PydanticAI](https://github.com/pydantic/pydantic-ai) стоит использовать как helper для typed dependencies, tool schemas, result validation и model adapters. Но SKM не должен хранить `PydanticAI Agent` внутри `ExecutionPlan`: это implementation detail конкретного adapter.

Подход:

```text
SKM RoleSpec
    -> PydanticAIAdapter
        -> PydanticAI Agent
            -> model provider
```

Хорошо заимствовать:

- typed dependency injection;
- structured result types;
- event streaming;
- model abstraction;
- test/fake model patterns;
- instrumentation hooks.

Не отдавать ему:

- durable workflow ownership;
- cross-agent scheduling;
- repository lifecycle;
- global policy;
- ecosystem compatibility.

### LangGraph

[LangGraph](https://github.com/langchain-ai/langgraph) полезен как референс для state graphs, nodes, conditional edges, checkpointing и human-in-the-loop. Он может быть optional graph runtime, но не должен определять универсальный SKM workflow contract.

Лучшее применение:

```text
ExecutionPlan
    -> LangGraphExecutionAdapter
        -> compiled graph
```

Не стоит:

```text
SKM contracts == LangGraph state and messages
```

Иначе смена graph runtime потребует миграции всей экосистемы.

### AutoGen

[AutoGen](https://github.com/microsoft/autogen) нужно изучить ради patterns многоагентных conversations, agent runtime и event-driven messaging. Но conversation-oriented orchestration не следует принимать за универсальную модель execution: производственный pipeline должен иметь явные стадии, effect boundaries, deadlines и terminal semantics.

### Semantic Kernel

[Semantic Kernel](https://github.com/microsoft/semantic-kernel) полезен как референс для plugins, kernel functions, planners и enterprise integration. Особенно интересен, если позже понадобятся .NET/Java consumers.

### DSPy

[DSPy](https://github.com/stanfordnlp/dspy) стоит рассматривать как слой оптимизации prompts/programs, а не как execution runtime. Его место:

```text
skill/prompt development -> optimizer -> versioned prompt artifact
```

а не:

```text
production workflow state -> DSPy
```

### Другие references

- [OpenAI Agents Python](https://github.com/openai/openai-agents-python) — handoffs, sessions, tracing и guardrails.
- [Google ADK Python](https://github.com/google/adk-python) — agent composition и Google-oriented integrations.
- [smolagents](https://github.com/huggingface/smolagents) — компактная agent loop implementation.
- [Agno](https://github.com/agno-agi/agno) — agent/team/workflow composition.
- [CrewAI](https://github.com/crewAIInc/crewAI) — role/task/crew abstractions.

Их следует включить в conformance matrix, но не пытаться поддержать все на первом этапе.

## Durable execution

### Temporal

Для вашей модели наиболее сильный baseline — [Temporal](https://github.com/temporalio/temporal):

- workflow/activity separation;
- durable timers;
- retries;
- signals;
- queries;
- cancellation;
- long-running workflows;
- worker failover;
- replay-based recovery.

Но Temporal workflow code требует детерминизма. В workflow нельзя напрямую выполнять:

- network I/O;
- provider SDK calls;
- filesystem discovery;
- чтение environment;
- случайный routing;
- `datetime.now()` вне runtime API;
- mutable global config.

Правильная граница:

```text
Temporal workflow
  -> schedule activity
      -> SKM activity adapter
          -> engine/provider/agent
```

Provider adapter должен находиться внутри activity, а не внутри replayable workflow function.

### Restate

[Restate](https://github.com/restatedev/restate) стоит изучить, если вам ближе модель durable services/RPC, virtual objects и keyed state. Для remote-agent services эта модель иногда естественнее Temporal workflow definitions.

### DBOS

[DBOS](https://github.com/dbos-inc/dbos-transact-py) интересен, если нужен Python-first durable execution поверх PostgreSQL и вы хотите сократить число инфраструктурных компонентов. Это потенциально хороший вариант для локальной и небольшой deployment-конфигурации.

### Hatchet

[Hatchet](https://github.com/hatchet-dev/hatchet) стоит оценить для task orchestration, worker execution, concurrency controls и operational UI. Он может оказаться проще Temporal для pipeline-oriented workloads.

### Prefect и Dagster

[Prefect](https://github.com/PrefectHQ/prefect) и [Dagster](https://github.com/dagster-io/dagster) полезны для batch/data orchestration, scheduling и assets. Для интерактивных coding-agent sessions, bidirectional control и fine-grained event streams они менее естественны, но их deployment, retries и task-run models стоит изучить.

### Практический выбор

| Сценарий | Рекомендация |
|---|---|
| Локальный запуск до нескольких часов | Собственный local engine |
| Production, длительные runs, approvals, timers | Temporal |
| Durable service/RPC-oriented agents | Restate |
| PostgreSQL-first компактная установка | DBOS |
| Task queue + orchestration UI | Hatchet |
| Data pipelines | Dagster или Prefect |

Не пытайтесь сделать local engine «маленьким Temporal». Он должен поддерживать ограниченный профиль:

```text
start
stream events
cancel
timeout
artifact capture
idempotent submission
best-effort recovery
```

Durable timers, signals, replay, compensation и multi-day execution передаются специализированному runtime.

## MCP

[FastMCP](https://github.com/PrefectHQ/fastmcp) — сильный кандидат для Python MCP servers и clients; его имеет смысл использовать вместо собственной JSON-RPC/MCP реализации. Официальные SDK всё равно нужно оставить compatibility authority, но FastMCP может стать productivity layer.

### Где применять

```text
Agent
  -> MCP client
      -> MCP server
          -> SKM tool adapter
              -> GitHub/filesystem/browser/service
```

MCP подходит для:

- tool discovery;
- tool schemas;
- resources;
- prompts;
- request/response transport;
- интеграции с внешними agent clients.

MCP не должен быть:

- внутренним event bus;
- durable workflow engine;
- источником истины для run state;
- системой доставки execution events;
- заменой capability contracts всей экосистемы.

### Tool snapshot

Во время plan compilation нужно фиксировать snapshot tools:

```json
{
  "server_id": "github.production",
  "server_version": "1.8.0",
  "protocol_version": "2026-...",
  "tools_digest": "sha256:...",
  "tools": [
    {
      "name": "create_pull_request",
      "input_schema_digest": "sha256:...",
      "effect": "write",
      "approval": "required"
    }
  ]
}
```

Если MCP server изменил schema между `prepare` и `run`, запуск должен:

- отказаться;
- пересобрать plan;
- либо использовать совместимый pinned server.

Не надо молча продолжать по новым tool definitions.

## A2A

[A2A](https://github.com/a2aproject/A2A) предназначен для interoperability между самостоятельными agent applications, а официальный [Python SDK](https://github.com/a2aproject/a2a-python) позволяет не реализовывать протокол вручную. Его разумно добавить как внешний transport adapter.

```text
SKM RemoteAgentPort
    -> A2AAdapter
        -> external agent
```

A2A полезен, когда внешний агент:

- сам управляет tools;
- скрывает внутреннюю реализацию;
- имеет собственный lifecycle;
- публикует capabilities;
- выполняется за отдельной trust boundary.

Для вызова обычной функции или provider API A2A избыточен. Внутренние Python-компоненты SKM также не стоит связывать через A2A без реальной process/network boundary.

## Plugin architecture

Нужны три разных механизма, потому что у них разные threat model и цена.

### Trusted Python plugins

Для trusted in-process extensions использовать:

- `importlib.metadata.entry_points`;
- [Pluggy](https://github.com/pytest-dev/pluggy);
- Pydantic manifest validation;
- explicit lifecycle hooks.

Pluggy уже является production-oriented hook/plugin system и используется pytest-экосистемой, поэтому собственный hook dispatcher писать не нужно.

Пример групп:

```toml
[project.entry-points."skm.model_providers"]
anthropic = "skm_anthropic.plugin:create_plugin"

[project.entry-points."skm.agent_executors"]
claude_code = "skm_claude_code.plugin:create_plugin"

[project.entry-points."skm.execution_backends"]
docker = "skm_docker.plugin:create_plugin"

[project.entry-points."skm.skill_sources"]
git = "skm_skills_git.plugin:create_plugin"

[project.entry-points."skm.health_checks"]
anthropic = "skm_anthropic.doctor:checks"

[project.entry-points."skm.cli"]
providers = "skm_providers.cli:plugin"
```

### Isolated subprocess plugins

[HashiCorp go-plugin](https://github.com/hashicorp/go-plugin) — правильный референс для:

- handshake;
- protocol negotiation;
- launching child process;
- RPC transport;
- health checking;
- crash detection;
- process cleanup;
- protocol versioning.

В Python не обязательно копировать gRPC-based реализацию. Можно сделать:

```text
stdin/stdout JSON-RPC
stderr logs
one JSON handshake line
length-prefixed messages
heartbeat
graceful shutdown
hard kill deadline
```

Handshake:

```json
{
  "magic_cookie": "SKM_PLUGIN",
  "manifest_version": 1,
  "plugin_id": "provider.example",
  "plugin_version": "2.4.0",
  "protocols": {
    "skm.provider": {
      "min": 1,
      "max": 2
    }
  },
  "capabilities_digest": "sha256:...",
  "transport": "stdio-jsonrpc"
}
```

### WebAssembly plugins

[Extism](https://github.com/extism/extism) предоставляет cross-language WebAssembly plugin framework, а [Wasmtime](https://github.com/bytecodealliance/wasmtime) — полноценный WASM/WASI runtime. Это хороший путь для portable policy transforms, validators, parsers и stateless extensions.

Не надо начинать с WASM для provider SDK или coding agents: network streaming, async callbacks, credentials и subprocess management там значительно усложнят host ABI.

Лучшие первые WASM-кандидаты:

- config validation;
- output normalization;
- policy predicates;
- prompt transforms;
- event filters;
- artifact metadata extraction;
- static skill validation.

## Контракты

### JSON Schema

Для human-readable manifests, config, plans и event payloads используйте JSON Schema как canonical source. Python-модели можно генерировать через [datamodel-code-generator](https://github.com/datamodel-code-generator/datamodel-code-generator), который поддерживает генерацию Pydantic, dataclasses, TypedDict и других моделей из JSON Schema/OpenAPI/Protobuf-подобных источников.

Pipeline:

```text
schemas/*.json
  -> schema lint
  -> compatibility check
  -> generate Python models
  -> generate TypeScript types
  -> verify generated tree clean
  -> build contract package
```

Не редактировать generated models вручную.

### Protobuf и Buf

Когда появятся стабильные cross-process RPC contracts, используйте Protobuf и [Buf](https://github.com/bufbuild/buf). Buf предоставляет linting, generation workflow и breaking-change checks, поэтому особенно полезен для provider-plugin RPC и worker protocols.

Моя рекомендация:

- JSON Schema — manifests, persisted plans, config, audit records.
- Protobuf — высокочастотный RPC и streaming.
- CloudEvents-like JSON — interoperable event export.
- Внутренние Python objects — generated/validated representation.

Не пытайтесь описать одним IDL абсолютно всё.

### Compatibility rules

Для каждого schema:

```yaml
id: skm.run-event
major: 1
status: stable
readers:
  min_major: 1
  max_major: 1
writers:
  major: 1
unknown_fields: preserve
```

CI должен проверять:

- удаление property;
- перевод optional в required;
- сужение enum;
- изменение type;
- изменение discriminator;
- изменение default semantics;
- несовместимое изменение regex/range;
- повторное использование удалённого field number в Protobuf.

## События

[CloudEvents Python SDK](https://github.com/cloudevents/sdk-python) можно использовать для внешнего event export либо взять CloudEvents envelope как основу. Внутренний event SKM должен дополнительно содержать execution-specific поля.

```python
@dataclass(frozen=True)
class RunEvent:
    spec_version: str
    event_id: str
    event_type: str
    source: str
    emitted_at: datetime

    run_id: str
    stage_id: str | None
    attempt: int | None

    owner_id: str
    owner_epoch: int
    sequence: int

    correlation_id: str
    causation_id: str | None

    data_schema: str
    data: Mapping[str, Any]
```

### Reducer invariants

Reducer должен быть отдельной чистой функцией:

```python
def reduce_run(
    state: RunState,
    event: RunEvent,
) -> RunState:
    ...
```

Инварианты:

- `event_id` deduplicated.
- `sequence` не уменьшается в пределах owner epoch.
- События старого `owner_epoch` не изменяют state.
- Terminal state необратим.
- Completed stage не становится running.
- Attempt \(n-1\) не может завершить attempt \(n\).
- `cancel_requested` не равно `cancelled`.
- Конец stream не означает success.
- Unknown event version сохраняется, но не применяется.
- Reducer не выполняет I/O.
- Replay одного журнала всегда даёт одинаковое состояние.

Это место стоит покрыть property-based tests через [Hypothesis](https://github.com/HypothesisWorks/hypothesis), включая перестановки, дубли, пропуски и delayed delivery.

## Idempotency и outbox

Нужно использовать PostgreSQL transactional outbox вместо схемы «обновили run, затем отправили событие»:

```sql
begin;

update runs
set state = 'running',
    version = version + 1
where id = :run_id
  and version = :expected_version;

insert into outbox_events (
    id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    payload
) values (...);

commit;
```

Publisher читает outbox через `FOR UPDATE SKIP LOCKED`, публикует event и отмечает запись. Получатели всё равно должны быть idempotent, потому что после publish и до отметки возможен crash.

Idempotency hierarchy:

```text
submission_id
  └── run_id
      └── stage_execution_id
          ├── provider_invocation_id
          ├── tool_invocation_id
          └── effect_id
```

Нельзя использовать один `idempotency_key` для всех уровней.

## Policies

### OPA

[Open Policy Agent](https://github.com/open-policy-agent/opa) — лучший общий референс для policy-as-code и отделения policy decision от enforcement. [Conftest](https://github.com/open-policy-agent/conftest) можно применять для тестирования структурированных manifests/configuration в CI.

Policy input:

```json
{
  "subject": {
    "tenant": "acme",
    "actor": "user:123",
    "roles": ["developer"]
  },
  "action": {
    "kind": "tool.invoke",
    "tool": "github.create_pull_request",
    "effect": "external_write"
  },
  "resource": {
    "repository": "org/repo",
    "visibility": "private"
  },
  "context": {
    "environment": "production",
    "data_classification": "confidential",
    "approval_present": false
  }
}
```

Policy output не должен быть одним boolean:

```json
{
  "decision": "require_approval",
  "reason_codes": ["EXTERNAL_WRITE", "PRODUCTION_TARGET"],
  "obligations": [
    {
      "kind": "redact",
      "paths": ["request.secrets"]
    },
    {
      "kind": "audit",
      "level": "full"
    }
  ],
  "policy_digest": "sha256:..."
}
```

### Cerbos

[Cerbos](https://github.com/cerbos/cerbos) может быть проще, если основная задача — application authorization, RBAC/ABAC и resource/action decisions. OPA гибче для произвольных execution policies, но требует дисциплины Rego, policy packaging и testing.

### Enforcement points

Policy enforcement должно происходить минимум в четырёх точках:

1. Plan compilation.
2. Перед выдачей credentials.
3. Непосредственно перед side effect.
4. При export/logging/storage артефактов.

Policy на этапе plan compilation не заменяет runtime check: resource, actor, target branch или approval могут измениться между подготовкой и применением эффекта.

## Effects

Tool call и effect — не одно и то же. `read_file` и `merge_pull_request` могут оба выглядеть как tool invocation, но имеют разные guarantees.

```python
class EffectKind(StrEnum):
    READ = "read"
    LOCAL_WRITE = "local_write"
    EXTERNAL_WRITE = "external_write"
    IRREVERSIBLE = "irreversible"
    FINANCIAL = "financial"
    PRIVILEGED = "privileged"
```

Effect request:

```json
{
  "effect_id": "eff_01...",
  "kind": "external_write",
  "operation": "github.pull_request.create",
  "target": "github://academici/example",
  "input_digest": "sha256:...",
  "idempotency_key": "run/stage/effect",
  "requires_approval": true,
  "policy_decision": "poldec_01..."
}
```

Effect receipt:

```json
{
  "effect_id": "eff_01...",
  "status": "applied",
  "provider_resource_id": "pull-request:482",
  "provider_request_id": "...",
  "applied_at": "...",
  "output_digest": "sha256:...",
  "compensation": {
    "supported": true,
    "operation": "github.pull_request.close"
  }
}
```

Такая модель позволяет не выполнять один и тот же эффект повторно при retry workflow activity.

## Наблюдаемость

### OpenTelemetry и OpenInference

[OpenInference](https://github.com/Arize-ai/openinference) предоставляет OpenTelemetry-oriented instrumentation и semantic conventions для AI workloads. Его стоит использовать как совместимую основу, добавив собственное namespace `skm.*`.

Span hierarchy:

```text
skm.run
  skm.plan.compile
    skm.role.resolve
    skm.skill.resolve
    skm.policy.evaluate
    skm.route.select
  skm.stage
    skm.agent.execute
      skm.model.invoke
      skm.tool.invoke
      skm.effect.apply
```

Stable low-cardinality attributes:

```text
skm.component.name
skm.component.version
skm.runtime.kind
skm.provider.name
skm.model.family
skm.stage.kind
skm.effect.kind
skm.outcome
```

High-cardinality values оставлять в spans/logs, а не metric labels:

```text
skm.run.id
skm.stage.id
provider.request_id
prompt.digest
artifact.digest
session.id
```

### Langfuse

[Langfuse](https://github.com/langfuse/langfuse) объединяет LLM/agent tracing, evaluation, prompt management и self-hosted deployment. Для SKM это хороший основной observability backend, особенно если нужны experiments, datasets и prompt versioning.

Есть полезная reference-сборка [Langfuse OSS LLMOps Stack](https://github.com/langfuse/oss-llmops-stack), которая разделяет обязанности: LiteLLM отвечает за gateway/routing/cost controls, а Langfuse — за observability, prompts и evaluation. Именно такое разделение стоит повторить.

### Phoenix

[Arize Phoenix](https://github.com/Arize-ai/phoenix) — сильная альтернатива для AI observability, traces, datasets и evaluations. Phoenix особенно логично рассматривать вместе с OpenInference.

Не отправляйте telemetry одновременно в несколько vendor-specific SDK из core. Core должен экспортировать OpenTelemetry, а backend выбирается deployment profile.

## Evaluations

Production agent system без eval layer постепенно деградирует незаметно. Нужны четыре класса evaluations:

| Класс | Что измеряет |
|---|---|
| Contract eval | Соблюдение схем и terminal semantics |
| Behavioral eval | Решена ли пользовательская задача |
| Safety eval | Не выполнены ли запрещённые effects |
| Operational eval | Стоимость, latency, retries, tool failures |

Dataset item:

```yaml
id: laravel-review-001
input:
  repository_fixture: fixtures/repo-001.tar.zst
  task: "Find transaction consistency defects"
expectations:
  required_findings:
    - code: LOST_UPDATE
  forbidden_effects:
    - github.pull_request.merge
limits:
  max_cost_usd: 2.00
  max_duration_seconds: 900
```

Evaluation result должен ссылаться на:

- ecosystem lock;
- plan digest;
- provider/model;
- skill digest;
- policy digest;
- repository fixture digest;
- evaluator version.

Иначе результаты разных запусков нельзя корректно сравнить.

## Артефакты и registry

### OCI и ORAS

[OCI Image Spec](https://github.com/opencontainers/image-spec) даёт проверенную модель manifests, descriptors, media types и content digests. [ORAS](https://github.com/oras-project/oras) позволяет хранить произвольные artifacts в OCI-compatible registry.

Это можно использовать для:

- skills;
- policy bundles;
- presets;
- schema bundles;
- evaluation datasets;
- plugin manifests;
- ecosystem lock bundles;
- SBOM;
- attestations.

Пример media types:

```text
application/vnd.skm.skill.v1+tar
application/vnd.skm.policy.v1+tar
application/vnd.skm.preset.v1+yaml
application/vnd.skm.schema-bundle.v1+tar
application/vnd.skm.ecosystem-lock.v1+yaml
```

Reference:

```text
ghcr.io/academici/skm-skills/security-review:3.2.0
ghcr.io/academici/skm-skills/security-review@sha256:...
```

Mutable tag удобен людям, digest обязателен в lock и execution plan.

### Artifact storage

Runtime outputs необязательно хранить в OCI registry. Для них проще `ArtifactStorePort`:

```python
class ArtifactStorePort(Protocol):
    async def put(
        self,
        stream: AsyncIterator[bytes],
        metadata: ArtifactMetadata,
    ) -> ArtifactRef: ...

    async def open(
        self,
        ref: ArtifactRef,
    ) -> AsyncIterator[bytes]: ...
```

Backends:

- filesystem;
- PostgreSQL large objects — только для небольших deployments;
- S3/MinIO;
- OCI registry — для распространяемых immutable bundles.

## Supply-chain

[Cosign](https://github.com/sigstore/cosign) предназначен для signing и verification контейнеров и бинарных artifacts. [Syft](https://github.com/anchore/syft) генерирует SBOM для images и filesystems, а [in-toto](https://github.com/in-toto/in-toto) предоставляет framework для integrity/provenance software supply chain.

Release pipeline:

```text
source tag
  -> reproducible build
  -> unit/contract/integration tests
  -> build wheel + OCI artifacts
  -> generate SBOM
  -> generate provenance attestation
  -> sign digest
  -> publish
  -> verify from clean environment
```

Plugin installation:

```text
resolve reference
  -> pull manifest
  -> verify digest
  -> verify signature
  -> verify publisher policy
  -> inspect SBOM/provenance
  -> validate compatibility
  -> install to isolated environment
  -> run conformance tests
  -> activate
```

Нельзя сначала импортировать plugin, а потом проверять его manifest.

## Feature flags

[OpenFeature specification](https://github.com/open-feature/spec) и [Python SDK](https://github.com/open-feature/python-sdk) полезны как референс provider-neutral feature flags. Используйте flags для rollout и operational control, но не для незаметного изменения семантики persisted workflows.

Допустимо:

```text
enable_anthropic_batch_adapter
route_5_percent_to_new_router
disable_provider_x_due_to_incident
```

Опасно:

```text
change_terminal_state_rules
reinterpret_old_events
replace_plan_digest_algorithm
```

Для уже начавшегося run resolved flag values должны фиксироваться в plan или run snapshot.

## Sandboxing

Для coding agents нужен отдельный sandbox abstraction:

```python
class SandboxPort(Protocol):
    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...
    async def exec(self, handle: SandboxHandle, command: Command) -> ExecHandle: ...
    async def snapshot(self, handle: SandboxHandle) -> ArtifactRef: ...
    async def destroy(self, handle: SandboxHandle) -> None: ...
```

Референсы:

- [Docker Engine](https://github.com/moby/moby) — базовая изоляция.
- [gVisor](https://github.com/google/gvisor) — усиленная container sandbox.
- [Firecracker](https://github.com/firecracker-microvm/firecracker) — microVM isolation.
- [Bubblewrap](https://github.com/containers/bubblewrap) — lightweight Linux sandbox.
- [nsjail](https://github.com/google/nsjail) — namespaces/seccomp-based process isolation.
- [E2B](https://github.com/e2b-dev/E2B) — sandbox infrastructure для AI agents.
- [Daytona](https://github.com/daytonaio/daytona) — development environment/sandbox platform.
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) — референс agent runtime и sandbox integration.

Рекомендуемые profiles:

| Profile | Изоляция |
|---|---|
| `trusted-local` | subprocess под текущим пользователем |
| `local-sandbox` | container + read-only base + explicit mounts |
| `hardened` | gVisor |
| `strong-isolation` | Firecracker microVM |
| `remote-managed` | E2B/Daytona-compatible adapter |

Filesystem, network, environment и secrets должны задаваться отдельно:

```yaml
sandbox:
  filesystem:
    workspace: read-write
    home: none
    system: read-only
  network:
    default: deny
    allow:
      - api.anthropic.com:443
      - github.com:443
  secrets:
    inject:
      - ref: secret://github/token
        as: env
        name: GITHUB_TOKEN
  process:
    max_children: 32
    timeout_seconds: 3600
```

## Secrets

Не пишите свой secret manager. Сделайте `SecretResolverPort` и adapters:

```python
class SecretResolverPort(Protocol):
    async def resolve(
        self,
        reference: SecretRef,
        purpose: SecretPurpose,
        context: SecurityContext,
    ) -> SecretLease: ...
```

Backends:

- environment — development;
- OS keyring;
- Docker/Kubernetes secrets;
- HashiCorp Vault;
- AWS Secrets Manager;
- GCP Secret Manager;
- Azure Key Vault.

`SecretLease` должен иметь expiry и audit identity. Raw value не должен сериализоваться в plan, event, trace или exception.

## Routing

Routing нужно строить как чистую, объяснимую функцию:

```python
@dataclass(frozen=True)
class RouteCandidate:
    binding: ProviderBinding
    capabilities: frozenset[Capability]
    health: HealthSnapshot
    cost: CostEstimate | None
    policy: PolicyDecision


@dataclass(frozen=True)
class RoutingDecision:
    selected: ProviderBinding
    considered: tuple[CandidateDecision, ...]
    reason_codes: tuple[str, ...]
    ruleset_digest: str
```

Pipeline:

```text
all bindings
  -> capability filter
  -> policy filter
  -> health filter
  -> residency/privacy filter
  -> budget filter
  -> preference scoring
  -> deterministic tie-break
```

Fallback не должен происходить при каждой ошибке:

| Ошибка | Fallback |
|---|---|
| Authentication | Нет |
| Invalid request | Нет |
| Content policy | Обычно нет |
| Rate limit | Возможно |
| Model unavailable | Да |
| Provider internal | Да |
| Unknown outcome | Только после idempotency analysis |
| Context limit | Нужен re-plan, не простой fallback |

Каждая смена provider/model должна создавать событие с объяснением.

## Budget control

Budget — отдельный port, а не callback LiteLLM:

```python
class BudgetPort(Protocol):
    async def reserve(
        self,
        estimate: CostEstimate,
        scope: BudgetScope,
        idempotency_key: str,
    ) -> BudgetReservation: ...

    async def reconcile(
        self,
        reservation: BudgetReservation,
        actual: Usage,
    ) -> BudgetReceipt: ...
```

Нужны budgets:

- per invocation;
- per stage;
- per run;
- per user;
- per tenant;
- daily/monthly;
- provider-specific.

Если точную стоимость заранее определить нельзя, reserve использует upper-bound estimate, а затем reconciliation возвращает остаток.

## Configuration

Конфигурацию лучше валидировать Pydantic-моделями, но хранить contract в JSON Schema. Для secrets использовать только references.

Пример:

```yaml
api_version: skm.config/v1

profile: development

providers:
  anthropic-default:
    adapter: anthropic
    model: claude-...
    credentials:
      api_key: secret://anthropic/default

agents:
  reviewer:
    executor: claude-code
    provider: anthropic-default
    sandbox: local-sandbox

routing:
  rules:
    - when:
        role: reviewer
      select:
        agent: reviewer
```

`skm config explain` должен возвращать machine-readable результат:

```json
{
  "path": "agents.reviewer.sandbox",
  "value": "local-sandbox",
  "source": {
    "kind": "workspace",
    "file": ".skm/config.yaml",
    "line": 16
  },
  "overrides": [
    {
      "kind": "profile",
      "value": "trusted-local"
    }
  ]
}
```

## Что не писать

Не рекомендую самостоятельно писать:

- универсальный LLM proxy;
- MCP wire protocol;
- agent-to-agent network protocol;
- durable timers и workflow replay;
- OpenTelemetry exporter;
- authorization language;
- secret store;
- OCI registry;
- plugin hook dispatcher;
- generic retry library;
- SBOM generator;
- artifact signing;
- JSON Schema model generator;
- Protobuf breaking-change checker;
- полноценную sandbox platform;
- UI для LLM tracing и evaluations.

Это инфраструктурные направления с огромным числом edge cases.

## Что писать самим

Собственная ценность SKM должна находиться здесь:

1. `ExecutionPlan` и его compiler.
2. Capability vocabulary.
3. Role/skill resolution.
4. Provider/agent/tool/execution ports.
5. Нормализованная taxonomy событий и ошибок.
6. Single-owner и fencing semantics.
7. Effect request/receipt protocol.
8. Policy inputs, obligations и enforcement points.
9. Artifact references и data classification.
10. Ecosystem lock.
11. Config precedence и provenance.
12. Explainability.
13. Conformance test kit.
14. Compatibility catalog.
15. Presets для реальных coding workflows.
16. Адаптеры к Claude Code, Codex, Gemini CLI и другим agent runtimes.
17. Сквозная сборка из уже существующих infrastructure projects.

## Базовый стек

Если выбирать практический production stack сейчас, я бы взял:

```text
Contracts:
  JSON Schema + Pydantic v2
  datamodel-code-generator
  Protobuf + Buf для process/remote RPC

Provider access:
  LiteLLM gateway
  direct Anthropic/OpenAI/Gemini adapters
  HTTPX + Tenacity только внутри direct adapters

Agent helpers:
  PydanticAI optional adapter
  LangGraph optional graph adapter

Coding agents:
  Claude Code adapter
  Codex adapter
  Gemini CLI adapter
  OpenHands adapter позднее

Local execution:
  asyncio
  subprocess/container backends
  PostgreSQL state + outbox
  content-addressed artifact storage

Durable execution:
  Temporal
  DBOS profile как потенциальная compact alternative

Tools:
  FastMCP
  official MCP SDK compatibility tests

Remote agents:
  A2A adapter

Plugins:
  Python entry points + Pluggy
  JSON-RPC subprocess plugins
  Extism только для stateless sandboxed extensions

Policy:
  OPA
  Conftest in CI

Observability:
  OpenTelemetry
  OpenInference conventions
  Langfuse или Phoenix

Artifacts:
  S3/MinIO для runtime outputs
  OCI/ORAS для skills/policies/presets/schema bundles

Security:
  Cosign
  in-toto attestations
  Syft SBOM
  gVisor/Firecracker для недоверенного execution
```

## Composition root

Ни один компонент не должен самостоятельно искать все остальные компоненты и принимать глобальные решения. Wiring выполняет ecosystem/composition package:

```python
def build_runtime(config: ResolvedConfig) -> Runtime:
    contracts = ContractRegistry.load(config.contracts)

    plugins = PluginRegistry.discover(
        allowed_publishers=config.security.allowed_publishers,
    )

    secrets = build_secret_resolver(config.secrets)
    policies = build_policy_engine(config.policies)
    artifacts = build_artifact_store(config.artifacts)
    telemetry = build_telemetry(config.telemetry)

    providers = build_provider_registry(
        plugins=plugins,
        secrets=secrets,
        telemetry=telemetry,
    )

    agents = build_agent_registry(
        plugins=plugins,
        providers=providers,
    )

    engine = build_execution_engine(
        agents=agents,
        artifacts=artifacts,
        policies=policies,
        telemetry=telemetry,
    )

    return Runtime(
        contracts=contracts,
        providers=providers,
        agents=agents,
        engine=engine,
    )
```

Dependency injection framework здесь необязателен. Явный composition root обычно проще анализировать, тестировать и передавать coding agents.

## Conformance kit

Каждый extension type должен иметь black-box suite:

```bash
skm-conformance provider anthropic
skm-conformance agent claude-code
skm-conformance runtime temporal
skm-conformance tool-server github
skm-conformance artifact-store s3
skm-conformance plugin ./dist/example.whl
```

Provider suite:

- capabilities стабильны;
- streaming events корректно завершаются;
- cancellation не объявляется до подтверждения;
- secrets не попадают в events;
- retry metadata нормализуется;
- unknown provider fields сохраняются;
- invalid structured output классифицируется;
- usage reconciliation выполняется.

Agent suite:

- workspace permissions;
- stdout/stderr framing;
- timeout;
- cancellation;
- child-process cleanup;
- session handling;
- artifact capture;
- duplicate submission;
- crash during side effect;
- non-zero exit after partial changes.

Runtime suite:

- worker crash;
- delayed event;
- duplicate event;
- stale owner;
- lease expiration;
- retry после partial output;
- cancellation race;
- restart during approval;
- replay from complete history.

## Репозитории для code mining

### Provider abstractions

- [LiteLLM](https://github.com/BerriAI/litellm): adapters, routing, proxy, cost accounting.
- [Portkey Gateway](https://github.com/Portkey-AI/gateway): gateway, guardrails, routing.
- [Vercel AI SDK](https://github.com/vercel/ai): provider abstraction, streaming, tools и structured generation.
- [PydanticAI](https://github.com/pydantic/pydantic-ai): typed agents, dependencies, testing.
- [Instructor](https://github.com/instructor-ai/instructor): structured outputs.
- [Outlines](https://github.com/dottxt-ai/outlines): constrained output.

### Agent runtimes

- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python).
- [LangGraph](https://github.com/langchain-ai/langgraph).
- [AutoGen](https://github.com/microsoft/autogen).
- [Semantic Kernel](https://github.com/microsoft/semantic-kernel).
- [Google ADK](https://github.com/google/adk-python).
- [smolagents](https://github.com/huggingface/smolagents).
- [DSPy](https://github.com/stanfordnlp/dspy).
- [OpenHands](https://github.com/All-Hands-AI/OpenHands).
- [SWE-agent](https://github.com/SWE-agent/SWE-agent).

### Protocols

- [FastMCP](https://github.com/PrefectHQ/fastmcp).
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- [MCP reference servers](https://github.com/modelcontextprotocol/servers).
- [A2A specification](https://github.com/a2aproject/A2A).
- [A2A Python SDK](https://github.com/a2aproject/a2a-python).
- [CloudEvents Python SDK](https://github.com/cloudevents/sdk-python).

### Durability

- [Temporal](https://github.com/temporalio/temporal).
- [Temporal Python SDK](https://github.com/temporalio/sdk-python).
- [Restate](https://github.com/restatedev/restate).
- [DBOS Python](https://github.com/dbos-inc/dbos-transact-py).
- [Hatchet](https://github.com/hatchet-dev/hatchet).
- [Prefect](https://github.com/PrefectHQ/prefect).
- [Dagster](https://github.com/dagster-io/dagster).

### Extensions

- [Pluggy](https://github.com/pytest-dev/pluggy).
- [HashiCorp go-plugin](https://github.com/hashicorp/go-plugin).
- [Extism](https://github.com/extism/extism).
- [Extism Python SDK](https://github.com/extism/python-sdk).
- [Wasmtime](https://github.com/bytecodealliance/wasmtime).
- [Wasmtime Python](https://github.com/bytecodealliance/wasmtime-py).

### Contracts

- [datamodel-code-generator](https://github.com/datamodel-code-generator/datamodel-code-generator).
- [Buf](https://github.com/bufbuild/buf).
- [Buf GitHub Action](https://github.com/bufbuild/buf-action).
- [Pydantic](https://github.com/pydantic/pydantic).
- [jsonschema](https://github.com/python-jsonschema/jsonschema).

### Policy

- [OPA](https://github.com/open-policy-agent/opa).
- [Conftest](https://github.com/open-policy-agent/conftest).
- [OPA Control Plane](https://github.com/open-policy-agent/opa-control-plane).
- [Cerbos](https://github.com/cerbos/cerbos).
- [Cerbos Python SDK](https://github.com/cerbos/cerbos-sdk-python).

### Observability

- [OpenInference](https://github.com/Arize-ai/openinference).
- [Langfuse](https://github.com/langfuse/langfuse).
- [Langfuse Python SDK](https://github.com/langfuse/langfuse-python).
- [Phoenix](https://github.com/Arize-ai/phoenix).
- [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python).
- [OpenTelemetry Collector](https://github.com/open-telemetry/opentelemetry-collector).

### Artifacts

- [OCI Image Spec](https://github.com/opencontainers/image-spec).
- [OCI Distribution Spec](https://github.com/opencontainers/distribution-spec).
- [ORAS](https://github.com/oras-project/oras).
- [ORAS Python](https://github.com/oras-project/oras-py).
- [Cosign](https://github.com/sigstore/cosign).
- [Syft](https://github.com/anchore/syft).
- [in-toto](https://github.com/in-toto/in-toto).
- [in-toto Attestation](https://github.com/in-toto/attestation).

## Очерёдность прототипов

### Первый прототип

Собрать минимальную вертикаль:

```text
ExecutionPlan
  -> LocalEngine
  -> ClaudeCodeAdapter or CodexAdapter
  -> event reducer
  -> filesystem artifact store
  -> OpenTelemetry
```

Никакого Temporal, OPA и OCI registry на этом этапе, но все точки подключения уже выражены port-интерфейсами.

### Второй прототип

Добавить provider path:

```text
ModelProviderPort
  -> LiteLLMAdapter
  -> LiteLLM gateway
  -> Anthropic/OpenAI/Gemini
```

Одновременно реализовать capability probing, normalized errors и usage reconciliation.

### Третий прототип

Добавить:

- FastMCP client;
- effect classification;
- approval gate;
- policy interface;
- transactional outbox;
- conformance tests.

### Четвёртый прототип

Подключить Temporal:

```text
ExecutionPlan
  -> Temporal workflow
  -> SKM activities
  -> existing local engine/provider adapters
```

Не писать новые provider adapters специально для Temporal.

### Пятый прототип

Добавить ecosystem packaging:

- OCI/ORAS skill bundle;
- signed plugin manifest;
- ecosystem lock;
- schema compatibility CI;
- SBOM/provenance;
- Langfuse или Phoenix backend.

## Жёсткие запреты

Я бы зафиксировал архитектурными тестами:

```text
orchestrator-core MUST NOT import provider SDKs
orchestrator-core MUST NOT import Temporal
workflow definitions MUST NOT perform network/filesystem I/O
contracts MUST NOT import runtime implementations
provider adapters MUST NOT decide business workflow retries
gateway MUST NOT own run state
MCP MUST NOT be the internal event bus
agent adapters MUST NOT write global configuration
plugins MUST NOT load before manifest verification
secrets MUST NOT serialize into plans/events/traces
terminal state MUST NOT be reversible
stale owner epochs MUST NOT mutate state
effects MUST NOT execute without an idempotency key
runtime artifacts MUST NOT be embedded in event payloads
feature flags MUST NOT reinterpret persisted histories
```

Основная инженерная экономия здесь получится не от поиска одного идеального фреймворка, а от правильной сборки существующих специализированных проектов: **LiteLLM для gateway, FastMCP для tools, Temporal для durability, Pluggy/go-plugin/Extism для extensions, OPA для policy, OpenTelemetry/OpenInference и Langfuse/Phoenix для observability, OCI/ORAS/Cosign/in-toto для artifact lifecycle**. Собственным должен остаться тонкий, хорошо специфицированный SKM-kernel, который связывает эти системы, но не дублирует их.