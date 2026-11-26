# Первичные источники и границы проверки

Срез на **2026-10-05**. Для решений используются официальные документы и code evidence. Perplexity — discovery/counterargument канал; исходные ответы сохранены отдельно.

## Локальные источники и проверки

Repo HEAD: `34a6c0f3342290cb5e5a3c2d0be106838a4ae455`. [Source index](source-index.json) содержит пути, SHA-256 и ссылки на исходный commit для 43 локальных source/doc records и 19 CAO records. У Task исследованы commands/code/schemas и workflow templates; несуществующий root README пакета не используется как источник. Хеш пользовательского диалога зафиксирован отдельно.

Параллельные изменения Task появились во время исследования. Для каждого local record указаны inspected hash, HEAD hash и их совпадение; ссылка на GitHub указывает baseline commit и не притворяется ссылкой на незакоммиченный WIP. [Concurrent-source ledger](concurrent-source-changes.json) показывает отличия и пути. 56 прошедших тестов — исторический результат на момент запуска, не attestation поздних чужих правок; тесты не перезапускались поверх движущейся рабочей копии ради формального «зелёного» отчёта.

Внимательно просмотрены Task `context/scout/units/cli/lifecycle`, canonical command catalog/render, Harness worker/queue/gates/instructions, Artifex compiler/activity/dispatch/authority/scheduler/worktree. Это предметный аудит затронутых путей, не полный security/code review всех пакетов.

Для proposed stage semantics также прочитаны canonical `general/workflow-craft`, `repository-bootstrap/task-development-philosophy` и `packages/task/workflows/README.md`. Они обосновывают optional review, design/dev distinction, reuse templates и ограниченные повторы; новый runtime не должен вводить дополнительный mandatory audit процесс.

Два генераторных check прошли; существующие engine suites дали **13 context + 23 scout + 20 units = 56 тестов**, все зелёные. [Полные argv, exit code, время, stdout/stderr](local-checks.json). External model calls, CAO e2e, остальные test suites и installation doctor в этой работе не запускались: окружение не менялось.

## CAO: документация отдельно от релизов

Main pin: `c31dc281ec1f215cef898c2ed919a0ce507afd08`. Tag `v2.5.1`: `d98243e7149912bf66cb7572e77629ffa0c650af`. [Release/PyPI snapshot](cao-versions.json), [наличие компонентов tag/main](cao-release-surface.json), [diff numstat](cao-tag-main-diff.txt).

| Источник на изученном commit | Проверенные вопросы |
| --- | --- |
| [README](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/README.md) | Назначение, запуск, local runtime, лицензия |
| [Workflows](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/workflows.md) | Python/YAML tier, inputs, status/cancel/resume, reserved execution types |
| [Script authoring](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/workflow-scripts-authoring-guide.md) | Explicit recovery, replay, step identity, profile name/content, terminal reuse |
| [Profiles](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/agent-profile.md) | Model/effort binding, native agents, capabilities |
| [Claude](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/claude-code.md) | Native config, permissions, launch semantics |
| [Codex](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/codex-cli.md) | Auth, profile/sandbox, TUI version parsing |
| [Grok](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/grok-cli.md) | Official CLI, model, native workflows opt-in |
| [Restrictions](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/tool-restrictions.md) | Provider-specific enforcement, role shells, MCP |
| [Skills](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/skills.md) | Catalog/load_skill, advertised filtering, delivery differences |
| [Configuration](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/docs/configuration.md) | tmux и experimental herdr |
| [Shim](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cao_workflow/__init__.py) | Actual HTTP step interface и identity |
| [Script runner](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/services/script_runner.py) | SIGTERM/SIGKILL, registry, orphan sweep, best-effort journal |
| [Journal](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/services/workflow_journal.py) | Durable records, terminal ID column и begin-step signature |
| [Workflow service](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/services/workflow_service.py) | Step statuses, replay и settlement |
| [Claude provider](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/providers/claude_code.py) | `claudeConfig.effort` actual argv |
| [Codex provider](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/providers/codex.py) | Codex config passthrough, TUI patterns |
| [Grok provider](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/providers/grok_cli.py) | Model mapping, restrictions; no explicit effort mapping found |
| [Plugin gate](https://github.com/awslabs/cli-agent-orchestrator/blob/c31dc281ec1f215cef898c2ed919a0ce507afd08/src/cli_agent_orchestrator/agent_plugins/gate.py) | Experimental plugin activation, отсутствие в изученном tag |

Есть внутренние расхождения документации: workflows.md отдаёт предпочтение Python, authoring guide советует начинать с YAML и упоминает branch/loop, тогда как executable YAML types ограничены. Есть устаревшие comments orphan sweep про отсутствие terminal ID column. Такие несоответствия — повод проверить нужный путь в коде/пилоте, не повод объявлять все возможности неработающими.

## Native CLI и SDK

| Первичная страница | Зачем проверялась |
| --- | --- |
| [Claude headless](https://code.claude.com/docs/en/headless) | Stream JSON, resume, partial messages, bare/discovery/auth boundary |
| [Claude subagents](https://code.claude.com/docs/en/sub-agents) | Native delegation и permissions |
| [Claude skills](https://code.claude.com/docs/en/skills) | Delivery и instruction semantics |
| [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) | Native TS/Python runtime integration, threads/resume |
| [Codex non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode) | JSONL events, native execution |
| [Codex app-server](https://learn.chatgpt.com/docs/app-server) | JSON-RPC, schemas, experimental status |
| [Codex auth](https://learn.chatgpt.com/docs/auth) | Native subscription/API distinction |
| [Grok scripting](https://docs.x.ai/build/cli/headless-scripting) | Headless streaming-json, named sessions, ACP и native cached auth |
| [Grok CLI reference](https://docs.x.ai/build/cli/reference) | Effort и launch options |
| [Grok skills/plugins](https://docs.x.ai/build/features/skills-plugins-marketplaces) | Native delivery; skill fields не равны applied model/effort |

OpenAI страницы открыты только на официальных доменах, включая текущие redirect targets. Documented support не заменяет проверку local version и active account.

## SDK/runtime альтернативы

| Источник | Область проверки |
| --- | --- |
| [Vercel introduction](https://ai-sdk.dev/docs/introduction) | Model abstraction и новый harness слой |
| [Harness overview](https://ai-sdk.dev/docs/ai-sdk-harnesses/overview) | Experimental API, session ownership |
| [Adapter matrix](https://ai-sdk.dev/docs/ai-sdk-harnesses/harness-adapters) | Реальный список adapters и runtime locations |
| [Claude adapter](https://ai-sdk.dev/providers/ai-sdk-harnesses/claude-code) | Agent SDK bridge, sandbox, auth selection |
| [Codex adapter](https://ai-sdk.dev/providers/ai-sdk-harnesses/codex) | App-server bridge, permissions/approvals и cold-resume limitations |
| [Grok adapter](https://ai-sdk.dev/providers/ai-sdk-harnesses/grok-build) | ACP, pinned CLI, sandbox, auth и capability gaps |
| [Workflow utilities](https://ai-sdk.dev/docs/ai-sdk-harnesses/workflow-utilities) | Durable Workflow SDK boundary и resume persistence |
| [Terminal UI](https://ai-sdk.dev/docs/ai-sdk-harnesses/terminal-ui) | Console UI pathway |
| [Pydantic harness](https://pydantic.dev/docs/ai/harness/) | Coding/workspace/subagents/durable runtime |
| [Pydantic Codex provider](https://pydantic.dev/docs/ai/models/openai-codex/) | Отдельный OAuth provider, собственный credential store, ограничения |

Vercel GitHub source pin: `5440b3a04089fe084b9236f636b316132e890373`. Проверены tree и опубликованные npm metadata, просмотрены Grok harness/subscription code и exports. Это подтверждает существование implementation, не end-to-end совместимость всех adapters. [Packages metadata](vercel-harness-surface.json), [source files/hashes](vercel-source-snapshot.json). Остальные source files, присутствующие в download inventory, не автоматически считаются полноценно audited.

Исходная `vercel/ai` root README оказалась коротким pointer; classification уточнена по официальным docs и package source, а не по этому pointer. Для остальных проектов см. [alternatives](../alternatives.md) и [15 repo metadata/README records](repository-metadata.json). Дополнительно открыты [AI-DLC](https://github.com/awslabs/aidlc-workflows), [Agent Orchestrator project config](https://docs.orchestrator.inc/configuration/projects/) и основные первичные README из исходного списка.

## Экономика и контекст

[Anthropic effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching). Использованы общие механизмы и границы измерения; конкретные rates/TTL/models не служат основанием рекомендации и должны перепроверяться при реальном benchmark.

## Правила интерпретации

**Документированный факт** — что утверждает актуальный primary source. **Code evidence** — что видно в конкретном просмотренном пути. **Локально проверено** — что реально исполнялось с argv/результатом в local-checks. **Предложение** — архитектура будущей интеграции. **Неизвестно** — actual auth/entitlement, economy и recovery behavior в целевой среде.

Не делается вывод о security isolation по имени role, о стабильности по бренду или об экономии по маркетинговым token savings. Raw research и неизменённый пользовательский диалог сохранены для последующего независимого review.
