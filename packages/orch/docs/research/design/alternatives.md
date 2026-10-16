# Кандидаты и инструменты из исходного диалога

Проверено 2026-10-05. Классификация относится к документированным возможностям и просмотренным источникам, а не к измеренной надёжности в наших проектах. [Metadata/README hashes](research/repository-metadata.json). Считать все эти продукты interchangeable harness было бы ошибкой.

## Все 14 первоначальных ссылок

| Продукт | Что это и что полезно | Вывод для нашей задачи |
| --- | --- | --- |
| [Harness.io CLI](https://www.harness.io/products/platform/cli) | CLI платформы CI/CD и инфраструктуры | Не кандидат на native coding-agent workflow engine |
| [Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/) | Python agent runtime с workspace/coding, subagents, compaction и durable integrations | Серьёзный программируемый runtime, но не готовый диспетчер именно наших трёх native CLI |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Собственный agent runtime, память, skills, tools и разные модели | Возможный worker; текущие материалы не доказывают нужный multi-CLI stage executor |
| [OpenHarness](https://github.com/autonomous-ai/openharness) | Терминальный command center, native processes, sessions/worktrees | Полезен для живой работы; tab collaboration experimental, Task workflow recovery требует отдельной проверки |
| [Vercel AI SDK](https://ai-sdk.dev/docs/ai-sdk-harnesses/overview) | Теперь и model SDK, и экспериментальный HarnessAgent | Нельзя исключать как API-only; подробнее ниже |
| [AWS Labs CAO](https://github.com/awslabs/cli-agent-orchestrator) | Multi-CLI orchestration, tmux, profiles, Python workflows | Основной внешний кандидат для пилота |
| [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) | Собственный RLM/REPL runtime, recursive agents, daemon/attach | Иная вычислительная модель; не начинать с него как оболочки над существующими CLI |
| [Superpowers](https://github.com/obra/superpowers) | Skills и методология coding workflow; native delivery для нескольких продуктов | Выборочные роли/skills, не engine. Не переносить обязательный процесс целиком поверх Task |
| [ECC](https://github.com/affaan-m/ECC) | Большой набор agent skills/hooks/configs; strongest Claude surface, другие adapters | Полезные части после проверки ownership; wholesale install способен дублировать наши hooks/планирование |
| [code-review-graph](https://github.com/tirth8205/code-review-graph) | Локальная code intelligence/MCP и помощь в reviewer context | В репозитории уже есть **измеренный owner verdict: skip** после пилота против Serena. Не рекомендовать повторное подключение без новых оснований; token savings рекламы не отменяют этот результат |
| [OpenCodex](https://github.com/lidge-jun/opencodex) | Provider/proxy совместимость для Codex и API routing | Не заменяет stage scheduler; proxy не означает перенос любых подписочных прав |
| [wshobson/agents](https://github.com/wshobson/agents) | Каталог ролей и skills с адаптацией под разные harness | Reference для content/render boundary, не собственник execution lifecycle |
| [Dify](https://github.com/langgenius/dify) | Платформа приложений и API-workflow | Не первый выбор для локальных native terminal processes; лицензию рассматривать отдельно от Apache/MIT |
| [i-have-adhd](https://github.com/ayghri/i-have-adhd) | Skill для формы ответов и когнитивной нагрузки | Не orchestration engine; в существующем provenance отмечен как skip из-за пересечения с нашим стилевым skill |

## Vercel: существенная поправка к первоначальному сравнению

Текущие [adapter docs](https://ai-sdk.dev/docs/ai-sdk-harnesses/harness-adapters) перечисляют Claude Code, Codex и Grok Build. Это не только roadmap: GitHub содержит соответствующие packages, а npm latest на момент проверки — harness `1.0.138`, Claude adapter `1.0.142`, Codex `1.0.140`, Grok `1.0.76`. Документация всё равно помечает harness API как experimental. [Проверенные metadata](research/vercel-harness-surface.json), [source snapshot](research/vercel-source-snapshot.json).

Claude adapter использует Agent SDK bridge, Codex — app-server bridge, Grok — ACP. Эти три пути рассчитаны на network sandbox; пример с Vercel Sandbox не является локальным процессом в нашем cwd. Документирован fallback к native subscription discovery, но auto auth сначала учитывает подходящие environment credentials. Нельзя обещать native billing при наличии API/Gateway vars. [Claude adapter](https://ai-sdk.dev/providers/ai-sdk-harnesses/claude-code), [Codex adapter](https://ai-sdk.dev/providers/ai-sdk-harnesses/codex), [Grok adapter](https://ai-sdk.dev/providers/ai-sdk-harnesses/grok-build).

У Grok adapter есть ограничения ACP built-in filtering и per-step usage. У Codex описаны ограничения native approvals и cold-resume events. Нужно проверить необходимый local/basic sandbox путь, version pins и auth до включения в сравнение локальных runners. [Workflow utilities](https://ai-sdk.dev/docs/ai-sdk-harnesses/workflow-utilities) дают durable-интеграцию с отдельным Workflow SDK; они не решают автоматически Git/Task effects. [Terminal UI](https://ai-sdk.dev/docs/ai-sdk-harnesses/terminal-ui) делает этот путь интересным при приоритете TypeScript UI.

**Вывод:** отдельный кандидат C для следующего расширения, если нужен Node-sidecar и приемлем sandbox. По исходным приоритетам локальных подписочных CLI и terminal attach CAO ближе; native JSONL runner проще контролировать локально.

## Pydantic: тоже нельзя оставлять прежнее API-only объяснение

Harness уже включает coding-agent machinery. Кроме того, официальный [OpenAI Codex provider](https://pydantic.dev/docs/ai/models/openai-codex/) поддерживает отдельный OAuth путь подписки Codex/ChatGPT. Это API/backend adapter с собственным credential store и ограничениями, а не запуск native Codex CLI и не общий способ запускать Claude/Grok подписки. Есть ограничения stored responses/resume/counting; конкретный путь нужно проверять отдельно.

**Вывод:** подходит, если мы хотим собственный Python agent loop. Для пользователя, который хочет использовать текущие CLI с их native skills/config, это более глубокая смена runtime.

## Дополнительные кандидаты

| Продукт | Почему рассмотрен | Какой вопрос остаётся |
| --- | --- | --- |
| [Agent Orchestrator](https://github.com/OrchestratorInc/agent-orchestrator), прежняя ссылка ComposioHQ перенаправляется сюда | Готовые native agent sessions, проекты/worktrees, CI/review/integration; Grok также предусмотрен | Насколько удобно выразить наши stage policies и Task lifecycle без перехода к issue-first модели; это реальная альтернатива, не проверенный проигравший |
| [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) | Native agent board, worktrees и review UX | Документированного Grok пути в просмотренном README не найдено; программный stage recovery не проверен |
| [AWS AI-DLC workflows](https://github.com/awslabs/aidlc-workflows) | Harness-neutral workflow core, native adapters, роли и выбор профиля | Методология и instructions поверх harness; просмотренные материалы не доказывают самостоятельный multi-CLI process supervisor |

Agent Orchestrator заслуживает резервного пилота, если приоритет сместится к параллельным задачам, CI и merge supervision. AI-DLC может дать отдельные шаблоны стадий, но установка всей methodology добавляет ещё один lifecycle поверх Task. OpenHarness/Vibe Kanban сильнее как пользовательские командные центры; оценка их programmable execution должна опираться на код конкретной версии.

## Как подключать готовые skills

Выбирать отдельные skills по конкретной пользе: reviewer, frontend/design, testing/debugging. Сохранить upstream provenance/license и адаптировать delivery через Skiller. Не устанавливать автоматически все hooks, memory и plan commands другого набора. Новый skill должен дополнять существующую stage responsibility и проверяться против запуска без него.

В этом исследовании ничего из перечисленного не установлено и не vendored. Утверждения о совместимости описывают источники, а не проверку effective loading в текущей сессии.

Существующие решения учитываются отдельно от новой классификации: [docs/reference.md](../docs/reference.md) уже фиксирует использование отдельных методов Superpowers, reference для ECC и измеренный отказ от code-review-graph. Данный аудит не отменяет эти решения и не назначает повторный пилот graph tool только потому, что он есть в исходном списке ссылок.
