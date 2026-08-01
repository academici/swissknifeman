# Референсы: внешние фреймворки и каталоги агентов Claude Code

Карта внешних источников, изученных при проектировании swissknifeman (слой субагентов/шаблонов —
research-аудит июнь 2026; skill-реестр и eval — рецензия skill-фреймворков июнь 2026). Для каждого —
что это, зрелость, **плюсы/минусы**, вердикт и что именно взято в swissknifeman. Цель — чтобы дальше
можно было возвращаться к ним адресно.

> **Правило:** использовал внешний ресурс при проектировании (репо, фреймворк, чужой скилл, статью,
> спецификацию) — **отметь его здесь** (строка в таблице + при значимости карточка: что, зрелость,
> вердикт, что взято). Это единый каталог провенанса; per-skill паспорта живут в `upstream.json`.

> Вердикты: **adopt** — взято; **reference** — паттерн/ориентир (не зависимость); **skip** — не
> подходит. Конвенция репо — stdlib-only Python, без JS/pip-рантайма: любой код извне берём как
> **паттерн** и переписываем, а не тащим зависимостью.

## Сводная таблица

| Источник | Что | Зрелость | Вердикт | Взято в swissknifeman |
|:--|:--|:--|:--|:--|
| Официальный спек Claude Code | subagents/skills/hooks/plugins, «steering» | first-party, активный | **adopt** | канон frontmatter субагента (`name/description+<example>/tools/model/color`), контракты хуков, прогрессивное раскрытие |
| [OpenAI Codex manual](https://developers.openai.com/codex/codex-manual.md) + [OpenAI model catalog](https://developers.openai.com/api/docs/models) + [Anthropic Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/) | current provider surfaces и model roles: instructions/config/trust, skills/plugins, hooks, MCP, approvals/sandbox; GPT-5.6 Sol/Terra/Luna | first-party, повторно проверено 2026-07-24 | **adopt (contract facts)** | provider contracts для `2026.07.19-DUAL-PROVIDER`; Goal/Constraints/Done, context/subagent budget, skill discovery и multi-source hooks для `2026.07.24-AGENT-RELIABILITY` |
| [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | task/trial/grader/transcript/outcome/harness; capability и regression evals; fixed task bank | first-party, 2026-01-09; проверено 2026-07-24 | **adopt (метод)** | основа failure-corpus и transcript-aware eval дизайна плана `2026.07.24-AGENT-RELIABILITY`; 20–50 реальных задач как старт, regression floor близок к 100% |
| [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) | vocabulary для conversation/agent/tool IDs, token usage, latency и evaluation attributes | открытый стандарт, development status; проверено 2026-07-24 | **reference** | shape reference для stdlib-only unified trace; OTel runtime dependency не добавляется |
| [Google SRE — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/) | blameless incident anatomy: impact, causes, action items, prevention и follow-up | first-party SRE book; проверено 2026-07-24 | **adopt (метод)** | same-finding loop переводится в incident/root-cause с owner/action/verification, а не в бесконечный retry |
| [Anthropic — Equipping agents with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) + [CSA/Trail of Bits — Skill Scanner Bypass](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-skill-scanner-bypass-20260610-csa/) + [cisco-ai-defense/skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) + [Heeler — Agent Skills security](https://www.heeler.com/resource/introducing-agent-skills-security-identify-and-prevent-risk-in-the-ai-agent-supply-chain) | supply-chain внешних скиллов: четыре класса угрозы (prompt injection · data exfiltration · malicious code execution · over-permissive tool use), позиция «первопартийного сканера нет, аудируй бандл руками», доказанная обходимость сканеров, «no findings ≠ safe» | first-party + CSA research note 2026-06 + OSS; проверено 2026-07-31 | **adopt (метод)** · **reference (паттерны)** | человеческий аудит 56 бандлов как ГРАНИЦА доверия + подчинённая ему триаж-ступень `update-upstreams.sh --check` (`2026.07.31-SKM-LEAN` P5.1). Паттерны cisco-ai-defense **переписаны своими стдлиб-правилами** — взято как ПАТТЕРН, не как зависимость (`root.engineering-invariants`); YARA/LLM-ступень апстрима не переносятся (внешняя зависимость / названа CSA обходимой) |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | курируемый каталог | 47k★, активный, NOASSERTION-лиц. | reference | подтверждает реальную схему субагента; Design-Review ≈ agent-pack 1:1 |
| [vijaythecoder/awesome-claude-agents](https://github.com/vijaythecoder/awesome-claude-agents) | оркестратор + специалисты | 4.3k★, MIT, ~stale | reference | блюпринт `orchestrator → stack-detect → специалисты` (= наши профили + `_common`) |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | 150+ субагентов | 22k★, MIT, активный | reference | seed-материал ролей; нативный frontmatter |
| [claude-rio](https://github.com/alex-popov-tech/claude-rio) | hooks-matcher (роутинг) | ~20★, MIT, ранний | adopt → `harness router` | контракт `UserPromptSubmit.additionalContext` лёг в хуки `agent-router` |
| Self-Improving session-hooks | паттерны session-хуков | talk-level, без репо | adopt → пакет `analyst` | подтверждает `additionalContext`-путь (memory-digest-hook в maind) |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | multi-agent runtime | 35k★, MIT | **skip** (reference) | только словарь оркестрации (supervisor/swarm) для прозы — иной слой |
| [itgoyo/awesome-agent-skills](https://github.com/itgoyo/awesome-agent-skills) | каталог скиллов | 138★, CC-BY | reference → [roadmap](../roadmap/skill-rules-sidecar.md) | паттерн `skill-rules.json` сайдкар (отложен) |
| [wshobson/agents](https://github.com/wshobson/agents) | стек-бандлы + model-tiers + мульти-харнес генератор (Claude Code · Codex CLI · Cursor · OpenCode · Copilot · Gemini CLI) | 38 346★, MIT, активный (`pushed_at` 2026-07-22); верифиц. GitHub API + прямое чтение `ARCHITECTURE.md` 2026-07-29 | reference | блюпринт профилей: стек→бандл, per-agent model-tiers; инвариант «generated gitignored и не правится руками» + `make garden` как референс единого гейта дрейфа (`2026.07.29-HARNESS-AGNOSTIC` P0.2, D6) |
| [anthropics/skills](https://github.com/anthropics/skills) | официальные skills (skill-creator, mcp-builder, doc/creative) | first-party, Apache-2.0 (docx/pdf/pptx — Proprietary) | **adopt** (метод) | eval-харнес скиллов из `skill-creator` (evals/benchmark, оптимизация описания); docx/pdf/pptx — **skip** (Proprietary); `mcp-builder` — reference (отложено) |
| [obra/superpowers](https://github.com/obra/superpowers) | process/discipline-скиллы + каркас (hooks-bootstrap) | MIT, активный, мульти-harness | **adopt** (метод) | pressure-тесты (`writing-skills` — TDD для документации) в eval-формат; iron-law/red-flag/SessionStart-bootstrap — reference (отложено) |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | кросс-harness фреймворк (skills/agents/hooks/security) | ~221k★, MIT, активный | reference | supply-chain-скан вендоринга, hook-профили, PreCompact, fact-force gate — **отложено**; инфраструктура (память/граф) уже у `maind` |
| [ai-agent-rules](https://github.com/wpfleger96/ai-agent-rules) · [anywhere-agents](https://github.com/yzhao062/anywhere-agents) · [agent-config](https://github.com/brianlovin/agent-config) · [ai-cli-mcp](https://github.com/mkXultra/ai-cli-mcp) · [agent-bridge](https://github.com/raysonmeng/agent-bridge) | multi-provider target classes, manifest/lock/hash/drift, lightweight sync и agent bridges | shallow commit-pinned audit 2026-07-19 | **reference** | P0/P1/P2 patterns; deterministic adapters/packaging controls приняты, external deps/symlink-first/runner bridge не входят в migration core |
| [Anthropic — Founder's Playbook](https://www.anthropic.com/) | методология AI-native стартапа (Idea/MVP/Launch/Scale, Claude как structured devil's advocate) | first-party, май 2026 | **reference** | каркас founder-трека + `idea-audit` (4 модуля, stage-context, premature scaling); эпиграф = парафраз, не verbatim |
| [CB Insights — Why Startups Fail](https://www.cbinsights.com/research/report/startup-failure-reasons-top/) | пост-мортемы стартапов, «no market need» | классика ~2014, апдейт 2026 | **reference** | аргумент зоны idea-validation в `idea-audit`; цитировать как классику (~42%), 2026 реформулирует ~43% poor PMF |
| [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | context engineering для агентов | first-party, сен 2025 | **reference** | основа Perplexity-навыка `idea-architect` (роль/режимы/правила веб-поиска/антипаттерны) |
| [Perplexity — Prompt Guide](https://docs.perplexity.ai/guides/prompt-guide) + Help Center | официальные правила формулировки запросов (specificity, version+context, cap result counts, separate concerns, grounding-rules) | first-party, верифиц. 2026-06-29 | **reference** | факт-основа CORE-скилла `research/query-craft` (5 слотов запроса, анти-паттерны, режимы search/advanced/deep); верифицировано RAG (WebSearch+WebFetch), не по памяти |
| `perplexity-web-mcp` — integration note (контракт MCP) | демон+пулы (`--pool`, до `maxConcurrency` вкладок, `idleShutdownMs`, авто-фолбэк в legacy); коды ошибок (`BROWSER_BUSY`/`TIMEOUT`/`LOGIN_REQUIRED`/`PROTOCOL_MISMATCH`/`INTERNAL`); client-side resilience (retry-with-backoff 3×, `notify-send`, JSONL error-log `$XDG_STATE_HOME/…/errors.jsonl`); login grace-window (~3 мин + cooldown, fail-fast) | sibling-пакет (вне репо), сверено по коду `src/{config,resilience,dispatcher}.ts` 2026-07-03 | **adopt** | обновил `research/query-craft` (раздел «Конкурентность и устойчивость» — resilience/grace-window) и `general/mcp-advisor` (пул-нота); прежний обход «не параллелить» снят как legacy; `.mcp.json` зонтика → `--pool=swissknifeman` |
| Industry-паттерны workflow-resilience 2025–2026 (rate-limit backpressure/circuit-breaker, job/worker/supervisor liveness, progress+deadline watchdog, `Promise.race`/cancellation, structured-output retry, infra-vs-task failure taxonomy) — Portkey/TrueFoundry/respan.ai/Vercel Workflow/claude-code issues | как проектировать устойчивый agent-workflow под rate-limit/hang | web/vendor-блоги + офиц. SDK-доки, верифиц. `perplexity-web` 2026-07-01 | **reference** | факт-основа раздела «Устойчивость» (`background-agents.md`) и dev-loop-правок (audit `2026-07-01-workflow-resilience-ratelimit`): fail-fast, `infra-failed`, supervisor+`PushNotification`; отклонён in-script `withDeadline` (V8-sandbox: нет `Date.now()`/`setTimeout`/cancel) |
| LangSmith / AgentOps / Helicone (LLM-agent observability платформы) | категории паттернов отказа агентов, которые эти платформы трейсят: клиенты tool-error, no-op/избыточные retry, застрявшие циклы рассуждений, раздутие context/token, latency/cost-аномалии | first-party доки/дашборды платформов, верифиц. `perplexity-web` 2026-07-02 | **reference** | ориентир КАТЕГОРИЙ для эвристик `core/pathology.py` (`file-reread`/`tool-error-loop`/`no-op-run`/`cache-miss`/`retrieval-stuffing`/`static-context`) — пороги НЕ откалиброваны по этим платформам, только форма сигналов; см. [Каталог патологий](/analyst/guide/pathologies) |
| [Kulaxyz/self-learning-skills](https://github.com/Kulaxyz/self-learning-skills) | промпт-скилл самообучения (0 кода/хуков, авто-запись скиллов) | 621★, MIT, ~3 дня, viral/no-track-record | **reference** | эпистемическая дисциплина записи знания в `analyst` (promotion-rule: passing-check+named-failure+ruled-out dead-end; capture-failures; секрет-по-ссылке; триаж skill/memory/skip). Авто-запись **инвертирована** в human-gate (синтез — во внутреннем дизайне пакета `analyst`). |
| [affaan-m ECC — continuous-learning-v2](https://github.com/affaan-m/everything-claude-code) | observations→instincts→evolved-skills, confidence-тиры, демон Haiku | MIT, активный | **adopt (паттерн)** | 3-ярусная лестница + privacy-by-directory-layout + confidence 0.3/0.5/0.7/0.9 + human-gated evolve/promote в `analyst`. **Отказ от демона** — cadence on-demand (v1). Верифиц. GitHub API+DeepWiki+Mintlify |
| [Diátaxis](https://diataxis.fr/) | фреймворк структуры документации (tutorial/how-to/reference/explanation по интенту читателя) | de-facto стандарт (Read the Docs и др.), верифиц. `perplexity-web` 2026-07-02 | **reference (метод)** | каркас зонтичного сайта: landing = карта-каталог пакетов; per-package `index.md` = «что это + когда брать», usage — в `guide/`; отдельные `getting-started` (tutorial) и `tasks` (how-to). Полная 1:1-миграция всех страниц НЕ проводилась — введён каркас навигации, не переписан весь контент |
| [mem0](https://github.com/mem0ai/mem0) ([arxiv 2504.19413](https://arxiv.org/abs/2504.19413)) | память агентов: extraction→consolidation | Apache-2.0 | **adopt (паттерн)** | консолидация-таксономия mem0 = **ADD/UPDATE/DELETE/NOOP** (канон `prompts.py`) → адаптирована как **ADD/UPDATE/NOOP/CONFLICT** (`analyst.lessons.classify_consolidation`): **CONFLICT вместо DELETE** — авто-удаление нарушило бы инвариант «человек в гейте» (F-RAG-2, verified perplexity 2026-07). Плюс retrieve-similar-before-write (BM25/Jaccard stdlib); soft-invalidate вместо delete; timestamp-ranking вместо decay. Extraction фактов — LLM-inherent (флаг) |
| Self-improving/anti-poisoning канон: [SICA](https://arxiv.org/abs/2504.15228)·[Voyager](https://voyager.minedojo.org/)·[Reflexion](https://arxiv.org/abs/2303.11366)·Generative Agents·A-MEM · [OWASP ASI06](https://genai.owasp.org/)·[MITRE AML.T0080](https://ttps.ai/technique/memory_poisoning.html)·MINJA | guardrails против model-collapse/memory-poisoning | академ.+security-фреймворки, верифиц. 2026-07 | **reference (комплаенс)** | safety-ядро `analyst`: self-verification доказанно достаточен против collapse → validate-before-promote; human-gate+провенанс+namespace = Tier-1; segment-per-tenant/expire-unverified (OWASP). Синтез — во внутреннем дизайне пакета `analyst`. |
| Industry prompt-engineering для RAG-forcing / verification-footer / self-critique (2025–2026) — plan→retrieve→verify loop, tool-forcing, структурные секции `unverified_assumptions`/`tool_failures`/`verification_report`, «cited but not verified» (dev.to · sey.pro) | как заставить план-агента 100% опираться на свежий RAG и честно выносить непроверенное | web-блоги, верифиц. `perplexity-web` 2026-07-01 | **reference** | факт-основа footer'а «Проверка» в `verify-claims`/`decision-verification`/CLAUDE.md + блока `VERIFICATION` оркестратора + `tool_failures[]` в `dev-loop.js`; решение токен-экономии — агрессивный flat-rate `perplexity-web` |
| [Roave/BackwardCompatibilityCheck](https://github.com/Roave/BackwardCompatibilityCheck) | статический BC-чекер публичного API PHP-пакетов (git diff текущей ветки vs baseline-тега) | стабильный, MIT, `^8.13`, верифиц. RAG 2026-07-02 | **adopt** | BC-ось reviewer'а `agent-packs/laravel-package`: интервью-проба `BC_CHECK_CMD` (`test -x vendor/bin/roave-backward-compatibility-check`) — при отсутствии бинаря ось остаётся прозой, а не блокирует пак |
| [github/spec-kit](https://github.com/github/spec-kit) | spec-driven development: `constitution → spec → plan → tasks → implement`, MD-артефакты как SSOT проекта | first-party GitHub, MIT, активный, верифиц. `perplexity-web` 2026-07-02 | reference | изучен при дизайне plan-протокола (`SKM-MASTER-002` фаза A/P1): machine-markers/фазовая заморозка/anti-staleness |
| [steveyegge/beads](https://github.com/steveyegge/beads) | git-backed граф-issue-tracker как персистентная память для AI-агентов (DAG задач, `bd ready` — только разблокированное) | 13.7k★, активный, верифиц. `perplexity-web` 2026-07-02 | reference | изучен при дизайне plan-протокола: machine-markers/фазовая заморозка/anti-staleness |
| [planning-with-files](https://github.com/othmanadi/planning-with-files) (паттерн Manus «Context Engineering for AI Agents») | Claude Code skill, воспроизводящий Manus todo.md-recitation: `task_plan/findings/progress.md` + PreToolUse/Stop-хуки против goal drift | сторонний skill-репо, верифиц. `perplexity-web` 2026-07-02 | reference | изучен при дизайне plan-протокола: machine-markers/фазовая заморозка/anti-staleness |
| `perplexity-web` синтез — voice-agent паттерны 2025–2026 (LiveKit Agents · Pipecat smart-turn-v2 · OpenAI Realtime VAD · WebRTC RFC 8825) | архитектура voice-агентов: WebRTC media + WebSocket control, 3-слойный turn-detection (VAD+семантический EOU+LLM-side), barge-in <500ms, латентность <800ms (1200ms — LEGACY/IVR), session state-machine | web/vendor-доки+спеки, верифиц. `perplexity-web` 2026-07-03 | **reference** | скилл `voice-ai` (`skills/voice-ai/voice-ai/`): пороги латентности/barge-in, session-machine idle→listening→thinking→speaking, backchannel-детекция |
| `perplexity-web` синтез — RU voice-стек (Yandex SpeechKit gRPC v3 streaming · SaluteSpeech · YandexGPT/GigaChat) + офлайн-альтернативы (Whisper/pyannote/Piper-VITS/Llama) | какие STT/TTS/LLM-сервисы актуальны для голосовых агентов в РФ, комплаенс 152-ФЗ | vendor-доки, верифиц. `perplexity-web` 2026-07-03 | **reference** | скилл `voice-ai`: RU-стек-секция + явная ремарка 152-ФЗ (region=RU, без cross-region fallback) |
| `perplexity-web` синтез — monorepo.tools · contracts-as-SSOT+codegen паттерны для полиглот-монорепо | как организовать `services/+packages/js|php|flutter/+apps/+infra/`, dependency direction, per-package vs unified semver, отдельные lockfiles, CI multi-lang | web/vendor-доки, верифиц. `perplexity-web` 2026-07-03 | **reference** | `docs/guide/polyglot-monorepo.md` (skiller) + профиль `platform-service` (`packages/skiller/profiles/`) |
| `code.claude.com/docs/en/skills` (frontmatter `model`/`effort`) · `…/model-config` (нет API смены модели сессии) · `…/sub-agents` (нет per-subagent effort) | официальный спек: где живут `model`/`effort`, какие ручки смены модели существуют | first-party, верифиц. `perplexity-web` 2026-07-15 (`2026.07.13-PLAN-PROTOCOL-GAP` D1/D3) | **reference** | подтверждён факт «нет API переключения модели/effort сессии изнутри команды» → `plan-exec` реализован как routing-**гейт-отказ** (эскалация `manual`), а не авто-переключение модели/effort |
| `perplexity-web` синтез — токен-экономия агентных систем 2026 (Anthropic prompt-caching docs · /compact-vs-/clear практика · sub-agent isolation · tool-result trimming/PARTIAL-receipts · MCP tool-def deferred loading (paddo.dev/reddit-кейс 92%) · tiered model-routing «не даунгрейдить ревьюеров») | актуальные (2026) внешние рычаги токен-экономии, сверенные с архитектурой репо | web/vendor-доки + first-party Anthropic, верифиц. `perplexity-web` 2026-07-15 (6 запросов; context7 — quota-промах) | **reference** (C4/C5 — adopt-кандидаты backlog) | `findings/P5-external-bestpractices.md` плана `2026.07.15-TELEMETRY-OPT`: C1–C3/C6 подтверждают уже принятое (`context-economy`, workflow-craft, D8/D9-routing); adopt-кандидаты — потолок+truncation-receipt в ответах maind MCP-тулов (C4) и прополка MCP-серверов / deferred tool-loading (C5, `ENABLE_TOOL_SEARCH` — `[UNVERIFIED]`, пред-проверка по first-party доке); C7/C8 → rejected-optimizations |
| [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) | local-first код-граф (Tree-sitter AST → SQLite) + MCP (30 тулов)/CLI; 40+ языков; заявка ~82× токен-экономии на вопрос (самозамер) | 26k★, MIT, активный; верифиц. GitHub API + README 2026-07-25; пилот-замер 2026-07-27 (v2.3.7) | **skip** (измерено, вердикт владельца `2026.07.25-ECO-OPT` D113) | Пилот против Serena исполнен: `Ops` отличные (build 1.66 с / 405 файлов, инкремент 0.24 с), но precision blast-radius против co-change ground truth `P_impact` = **0.039** при объявленном ДО замера пороге `≥ 0.40` (24 fold'а на 3 коммитах Laravel-проекта; порог перешёл 1 fold). Отказ по ШУМУ, не по слепоте: recall 0.40–0.43, но 110 файлов на seed, истинные — на позициях 77 и 102. Не подключаем **по нашим числам на нашей кодовой базе**; канон графа кода остаётся **Serena** (LSP). Взято: правило «graph-retrieval MCP не подключается по README — только после своего co-change-замера» + триггеры переоткрытия → тело скилла `general/mcp-advisor`; числа — `plans/archive/2026.07.25-ECO-OPT/findings/P5.1-stage0-killgate.md`, пакет решения — `findings/P5.2-codegraph-verdict-packet.md` |
| [breferrari/obsidian-mind](https://github.com/breferrari/obsidian-mind) | Obsidian-vault как персистентная память агентов (CC/Codex/Gemini), git-синк, хуки+MCP semantic search | 3.9k★, MIT, TS/Node; верифиц. GitHub API + README 2026-07-25 | **skip** (паттерн-reference) | как механизм памяти дублирует maind/agentmemory + Brain vault; полезный паттерн MEMORY.md-указателей уже канон; cross-machine решается демоном-хостом (`2026.07.25-ECO-OPT` P4, D4) |
| [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) | скилл ADHD-friendly вывода: 10 правил (action-first, нумерация, no preamble/closers) | 9.6k★, MIT, Python; верифиц. GitHub API + README 2026-07-25 | **skip** (reference) | дублирует lean output style + `core:compact-responses`; 1–2 правила (answer-first, no closers) — кандидаты в правку compact-responses (`2026.07.25-ECO-OPT` P6.2, D8) |
| [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | официальный OpenAI плагин CC: `/codex:review\|adversarial-review\|rescue\|transfer`, subprocess над локальным `codex` CLI | 29.9k★, Apache-2.0, first-party OpenAI; верифиц. GitHub API + README 2026-07-25 | **adopt (Codex CLI как второй водитель) · reference (плагин, opt-in per-plan)** | план `2026.07.25-ECO-OPT` P7 (D84/P7.1/P7.2/P7.3): Codex CLI напрямую водит тот же plan-протокол при недоступности Claude (dogfood — «дошёл с 4 вмешательствами», 2 из 4 устранены починкой корневого `AGENTS.md`); плагин `codex-plugin-cc` установлен, но задействуется ТОЛЬКО при явном указании в плане (правило текстовое, машинного гейта нет) |
| [Anthropic — Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5) | first-party гайд: анти-паттерн явных verify/double-check инструкций (овер-верификация), effort-sweep (low/medium дешевле при качестве), subagent-капы, verbosity/scope-стиринг, 1M контекст | first-party, 2026; прочитан 2026-07-25 | **adopt (метод)** | план `2026.07.25-ECO-OPT` P2: Brain model-notes выжимка + точечная ревизия task-команд/agent-packs (убрать double-check из Opus-pinned, пересмотреть effort-пины) — D5: модель-специфика в model-notes, не в evergreen-скиллах |
| [Anthropic — Prompting Claude Sonnet 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5) | first-party гайд implementation-тира: тот же анти-паттерн явной верификации/лесов статус-апдейтов применим и к Sonnet-пиненным поверхностям (5 из 10 запиненных команд); буквальность инструкций (не обобщает правило с одного объекта на другие); effort-мэппинг при миграции (medium≈S4.6 high, high≈S4.6 max); +30% токенайзер; confidence-level на находку в code review | first-party, 2026; прочитан 2026-07-25 | **adopt (метод)** | план `2026.07.25-ECO-OPT` P2: Brain model-notes `sonnet-5-prompting.md` + вход в ревизию P2.2/P2.3 (D19) |
| [Anthropic — Effort](https://platform.claude.com/docs/en/build-with-claude/effort) | first-party спек параметра `effort`: 5 уровней (low/medium/high/xhigh/max) + typical use case, поведенческий сигнал (не токен-бюджет), `xhigh`/`max` — thinking нельзя отключить, кэш-инвалидация при смене effort между запросами | first-party, 2026; прочитан 2026-07-25 | **adopt (метод)** | план `2026.07.25-ECO-OPT` P2.1: несущий источник обеих Brain-нот (Opus 5 + Sonnet 5); effort-таблицы обеих нот — прямая выжимка |
| [romarayt/raytsystem-public-os](https://github.com/romarayt/raytsystem-public-os) | local-first агентный воркспейс; для нас — **механика гейтов**: политика как данные, preflight-хеш-запись, один guard для CLI и pre-commit, симулятор ≡ рантайм, версионированный реестр контрактов, docs-DoD + coverage по живым контрактам, отчёт квалификации с классом свидетельства | Apache-2.0; публичное дерево — **сквошенный снимок** (1 коммит, 0 тегов), поэтому ★/возраст не индикатор; зрелость снята артефактами: 35 ADR, 73 теста (809 КБ), датированный отчёт прогона, полевые issue с числами. Верифиц. GitHub API + `raw.githubusercontent.com` + `perplexity-web` 2026-07-25 | **adopt (механика, 17 item'ов)** · **skip** (uv/pyproject/React, каталог-снимок схем на версию, обязательность на pre-commit) · **reference** (симулятор политики как код, `reason` в каталогах адаптеров) | `plans/archive/2026.07.25-ECO-OPT/findings/rayt-deep-2026-07-25.md` (слой 1) + `research/09-rayt-adoption-map.md` (вердикты по каждому приёму, карта по пакетам). Адресат — **фаза P8** плана `2026.07.25-ECO-OPT` (9 приёмов), остальные 10 — в его `roadmap.md` (D41: отдельный план отменён) |
| Внешний архитектурный аудит `core`/provider (Perplexity, запинен хешами в `plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/perplexity-audit.md`) | сторонний разбор монорепо: предлагает перестроить `core`/провайдерный слой, ввести обязательные контрактные тесты, вынести политику владения из хуков, программу внедрения на 12 PR / 90 дней | одноразовый разбор, снапшот запинен и неизменяем (D25); проверен **по коду**, а не по описанию, 2026-07-26 | **частично adopt (3 из 16), в основном reject** | `2026.07.24-AGENT-RELIABILITY` P4.1: 16 несущих гипотез адъюдицированы против функций/вызывающих/тестов — **3 accept** (провенанс резолва конфига не рендерится никому; `run-report` деградирует молча; предикат владения `managed AND NOT user_owned` реализован трижды без parity-гейта) → оформлены как БУДУЩИЕ предложения FP-1/FP-2/FP-3 с владельцами, **11 reject**, **2 unknown** (H15/H16 — доказательства не существует). Ни одна гипотеза не реализована этим планом; вердикты — `findings/P4.1-code-grounded-audit.md`, `root/provider-core-hypotheses.md`; отклонённое — [rejected-optimizations](./rejected-optimizations.md) |
| [opencode.ai/docs/skills](https://opencode.ai/docs/skills/) | какие каталоги скиллов читает OpenCode: `.opencode/skills/`, `~/.config/opencode/skills/`, `.claude/skills/`, `~/.claude/skills/`, **`.agents/skills/`**, `~/.agents/skills/`; обязательный frontmatter `name` (1–64, lowercase-kebab, = имя каталога) + `description` (1–1024) | first-party, WebFetch 2026-07-29 | **reference** (провенанс) | `2026.07.29-HARNESS-AGNOSTIC` P0.2: канал `.agents/skills`, который skiller уже пишет как Codex-выход, читается ШИРЕ одного Codex — правило «не ломать `.agents/skills`». Cursor/OpenCode как цели вне скоупа (решение владельца 2026-07-29), факт зафиксирован как провенанс, а не как задача. Замер — `plans/archive/2026.07.29-HARNESS-AGNOSTIC/findings/01-rag-cross-harness-2026-07-29.md` Ф1 |
| [cursor.com/docs/skills](https://cursor.com/docs/skills) | Cursor ищет `.agents/skills/`, `.cursor/skills/`, `~/.agents/skills/`, `~/.cursor/skills/`; для back-compat дополнительно `.claude/skills/` и `.codex/skills/`; рекурсивный обход (монорепо-дружественно); опциональные `paths`/`disable-model-invocation`/`metadata` | first-party, WebFetch 2026-07-29 | **reference** (провенанс) | То же правило «не ломать `.agents/skills`» — второе first-party подтверждение того же адреса (Ф1). Рекурсивный обход и `paths` — ориентир на будущее, если скоуп харнесов расширится; сейчас не задача |
| [learn.chatgpt.com/docs/build-skills](https://learn.chatgpt.com/docs/build-skills) | бюджет **обнаружения** скиллов у Codex: в контекст сначала грузятся только `name`/`description`/`path`, и ЭТОТ листинг ограничен «максимум 2 % контекстного окна модели либо 8 000 символов при неизвестном окне»; после выбора «Codex still reads the full SKILL.md» | first-party (через цитирующий поиск `perplexity-web`), 2026-07-29 | **reference** | `2026.07.29-HARNESS-AGNOSTIC` D6: тезис «8 KB — жёсткий лимит ТЕЛА `SKILL.md` у Codex» (в т.ч. у wshobson, где под него режут тела) **опровергнут** — 8 000 ограничивают ЛИСТИНГ обнаружения, а не тело выбранного скилла. 37 скиллов реестра > 8 KB по этому факту не сломаны (максимум — `general/plan-protocol` 89 988 байт). Реальный дефицит — качество `description` и число одновременно установленных скиллов. **`[UNVERIFIED]`:** собственного замера на живом Codex CLI не проводилось; кап тела как правило принимать нельзя без него. Разбор — `findings/01-rag-cross-harness-2026-07-29.md` Ф4 |
| [openai.com/index/harness-engineering](https://openai.com/index/harness-engineering/) | first-party OpenAI об инженерии харнеса — источник практик, на который ссылается `ARCHITECTURE.md` wshobson (вместе с конвенцией `agents.md`) | first-party; **`[UNVERIFIED]`** — известен по ссылке из `ARCHITECTURE.md` (прочитан 2026-07-29), сам текст first-party не читался | **reference** | Пока только провенанс: назван как корень практик мульти-харнес генератора wshobson (`findings/01-rag-cross-harness-2026-07-29.md` Ф3). Читать первоисточником — до того, как хоть один его тезис попадёт в несущую позицию |
| Входящий аудит владельца (Perplexity, 2026-07-29) — запинен в `plans/archive/2026.07.29-HARNESS-AGNOSTIC/findings/00-owner-audit-perplexity-2026-07-29.md` | сводный внешний разбор монорепо: скиллы/токен-бюджет, матрица роль × стек, перенос из `wshobson/agents` и Anthropic multi-agent research, целевая структура репозитория, что дописать в документы | одноразовый разбор, снапшот запинен и неизменяем; адъюдицирован по коду 2026-07-29 | **reference** (частично **adopt**: §11-правила 1 и 4, §7 policy-слой, §12) | **Оговорка: аудит собран по публичным README, а не по дереву** — шесть из восьми его несущих рекомендаций уже реализованы (agent-packs, дробление бакетов, роль × стек, model-тиры, provider-контракт), и он предлагал уже отклонённое, потому что каталоги провенанса отставали от решённого. Принято: корневой always-on контекст = короткий индекс; спавн по бюджету контекста; delegation contract как обязательная форма; актуализация канона каркаса (сам вход `framework-overview.md` протух и породил ложные разделы аудита). Отклонённое — [rejected-optimizations](./rejected-optimizations.md) (§10.1/§10.2/§10.3/§10.5). Посекционный вердикт — `plans/archive/2026.07.29-HARNESS-AGNOSTIC/research/01-audit-adjudication.md` |

## Карточки

### Официальный спек Claude Code — adopt
Канон, на котором стоит всё. Субагент = `.claude/agents/*.md` с frontmatter
`name/description(+ <example>)/tools/model/color`; **автоделегирование идёт по `description`**, а
не по выдуманному полю `triggers`. SKILL.md — минимум `name/description`, автоактивация
прогрессивным раскрытием. Хуки — фикс. список событий + JSON-контракты
(`hookSpecificOutput.additionalContext` и т.п.).
**Плюсы:** авторитетно, бесплатно, схема берётся дословно. **Минусы:** доки переехали на
`code.claude.com` (сетево недоступны из части окружений); новые поля субагента
(`disallowedTools/skills/memory`) ещё не зафиксированы как first-party — строить на них рано.
**Взято:** канонические `description`+`<example>` во всех пак-агентах, поле `color`, `model`-тиры.

### Официальные Codex + Claude Code docs — adopt (contract facts)

Fresh Codex manual и official Anthropic docs повторно проверены 2026-07-19 для плана
`2026.07.19-DUAL-PROVIDER`. **Плюсы:** first-party contracts для instruction/config layers,
skills/plugins, hooks, MCP и security knobs. **Минусы:** одинаковые названия скрывают разные
trust/precedence/permission semantics; 1:1 field mapping недопустим. **Взято:** общий capability
язык + нативные adapters; `approval`, `sandbox/access` и `project trust` остаются разными осями.

### Multi-provider upstream audit — reference

Пять небольших репо из сводной строки проверены на pinned commits 2026-07-19. **Плюсы:**
практические target classes, manifest/lock/hash/drift и лёгкий sync. **Минусы:** ни один не
покрывает contract swissknifeman; встречаются symlink-first, внешние dependencies и runner/bridge
scope. **Взято:** только deterministic adapter и packaging-control patterns; runtime dependency,
fleet rollout и unattended runner в эту migration не перенесены.

### hesreallyhim/awesome-claude-code — reference
Огромный курируемый каталог. **Плюсы:** сигнал «что реально шипят»; Design-Review-Workflow ≈
наш agent-pack; подтверждает реальную схему и опровергает skm2-выдумки `triggers/agents`.
**Минусы:** это список, не фреймворк; кастомная лицензия (копировать прозу — с проверкой);
дочерний `*-agents` слабый. **Взято:** ориентир по структуре пака.

### vijaythecoder/awesome-claude-agents — reference (ключевой блюпринт)
Доказывает целевую архитектуру пользователя «на практике»: `tech-lead-orchestrator` →
`team-configurator` (детект стека) → специалисты, всё как обычные `.md` без рантайма.
**Плюсы:** прямой прообраз «шаблона по типу проекта» (= наши `profiles/` + `_common`-оркестратор);
нативный минимальный frontmatter. **Минусы:** ~stale (окт-2025); набор неровный; конфиг пишется
в CLAUDE.md (риск коллизий — у нас доставка детерминированная). **Взято:** идея оркестратора +
per-type селекции.

### VoltAgent/awesome-claude-code-subagents — reference
150+ персон, MIT, активно. **Плюсы:** безопасно копировать с атрибуцией; 100% нативный
frontmatter — падает прямо в `.claude/agents/`. **Минусы:** только статический список (ни движка,
ни хуков — наши `dev-loop.js`+`review-gate` мощнее по исполнению); агенты общие/многословные, без
`PLACEHOLDER`-шаблонизации/`skills:`. **Взято:** seed-идеи ролей для будущих паков.

### claude-rio — reference → roadmap
Hooks-matcher: `UserPromptSubmit` подсказывает скилл/агент по ключевым словам. **Плюсы:** закрывает
реальный пробел — агенты/команды НЕ автоактивируются; чистый контракт I/O; ненавязчив. **Минусы:**
для скиллов избыточен (они и так автозагружаются); JS/npx — против stdlib-only; матчер наивный.
**Решение:** контракт взяли, реализация — на Python: хуки
`packages/harness/configs/claude-code/hooks/agent-router/` + `harness router` (спека-роадмап закрыта и удалена).

### Self-Improving session-hooks — reference → roadmap
Паттерны: direnv-промпты, strike/praise CSV, skill-activation, SessionStart-инжект контекста.
**Плюсы:** всё ложится на уже используемый в maind `additionalContext`-путь. **Минусы:** «CSV-скоринг»
без канона (talk-level); `UserPromptSubmit.additionalContext` протухает на resume. **Решение:**
безопасную форму самообучения — пакетом `analyst` (через память maind, ручное промо);
остаток потокового capture — `packages/analyst/docs/roadmap.md`.

### langchain-ai/langgraph — skip (reference)
Production-grade multi-agent **рантайм**. **Плюсы:** зрелый словарь топологий (supervisor/swarm/
checkpointing). **Минусы:** иной слой целиком — это рантайм, который исполняешь, а swissknifeman
лишь **конфигурирует** Claude Code; тяжёлый не-stdlib стек. **Взято:** только словарь для прозы
доков об оркестрации.

### itgoyo/awesome-agent-skills — reference → roadmap
Каталог-директория (ценность — в 4-5 downstream-репо). **Плюсы:** указывает на качественные MIT-
реализации (skill-rules.json scoring, role-hierarchy паки, model-tier rules). **Минусы:** сам список
структурно ничего не даёт; звёзды ненадёжны; референс-репо доменные. **Взято:** паттерн
`skill-rules.json` — отложен в [roadmap](../roadmap/skill-rules-sidecar.md).

### wshobson/agents — reference (блюпринт профилей)
38 346★, MIT, активный (`pushed_at` 2026-07-22) — стек-именованные бандлы + единый источник→много
харнесов (Claude Code, Codex CLI, Cursor, OpenCode, GitHub Copilot, Gemini CLI) + per-agent
model-tiers. Верифицировано GitHub API и прямым чтением `ARCHITECTURE.md` (2026-07-29,
`plans/archive/2026.07.29-HARNESS-AGNOSTIC/findings/01-rag-cross-harness-2026-07-29.md` Ф3), а не по
памяти модели. **Пять инвариантов `ARCHITECTURE.md`:** (1) single source of truth — авторинг
только в `plugins/<name>/`, харнес-специфичное **генерируется и gitignored**, «never hand-edit
generated files» (исключение — маленькие native-install реестры, они лишь указывают на источник);
(2) один канонический контекст-файл (`AGENTS.md`, `CLAUDE.md` — симлинк); (3) адаптеры владеют
харнес-механикой, исходники не несут условной логики; (4) механическое принуждение с
remediation-хинтом на каждую находку; (5) progressive disclosure до конца (контекст-файлы ≤ ~150
строк, тела скиллов ≤ ~8 KB). **Три гейта:** `make validate` (структура сгенерированного),
`make garden` (дрейф: мёртвые ссылки, устаревшие артефакты, oversize-компоненты, orphan'ы
marketplace), `make test` (386 тестов, включая round-trip и real-CLI smoke). **Плюсы:** почти
готовый блюпринт для `maind`/skiller-профилей: `specialized/<framework>` + `universal` + `core`,
версионируемо, без движка. **Минусы:** мульти-харнес генератор тяжёлый — берём **форму, не
масштаб** (наш живой скоуп — Claude основной + Codex запасной; Cursor/OpenCode вне скоупа,
решение владельца 2026-07-29); их кап тела скилла ≤ 8 KB — перестраховка, а не требование
платформы (см. строку про бюджет обнаружения скиллов Codex в сводной таблице выше). **Взято:**
идея per-agent model-tiers (реализована как `profile.model_tiers` → `MODEL_*`-плейсхолдеры);
инвариант 1 «generated не правится руками» — как усиление нашего provider-контракта
(у нас часть производного закоммичена и разъезжается вручную) и `make garden` — как референс
одного гейта дрейфа поверх генерируемых поверхностей, которого у нас нет (есть `validate.sh` по
пакетам и `provider-docs.py --check`). Оба — `2026.07.29-HARNESS-AGNOSTIC` D6, разбор —
`research/01-audit-adjudication.md` §6.

### anthropics/skills — adopt (методология)
Официальные демонстрационные skills. **Плюсы:** `skill-creator` даёт ровно то, чего у нас не было —
**eval/benchmark** скиллов и оптимизацию триггера описания; его 3-ярусная модель раскрытия совпадает
с нашим `budget.py` (у нас даже строже — ≤150 строк тела). `mcp-builder` — эталон дизайна MCP-серверов
(релевантно `maind`/бакету `ai`). **Минусы:** `docx/pdf/pptx` под **Proprietary**-лицензией (вендорить
нельзя); прочие — Apache-2.0 «for demonstration only»; код тащить не надо (stdlib-only) — берём метод.
**Взято:** eval-харнес скиллов (`lib/skiller/eval.py`, `skiller eval`, формат `evals/`); `mcp-builder`
и doc/creative — reference/skip.

### obra/superpowers — adopt (методология)
Каркас process-скиллов (TDD/debugging/brainstorming) + SessionStart-bootstrap, инжектящий «скиллы
существуют». **Плюсы:** `writing-skills` = **TDD для документации** (pressure-тесты: сценарии-соблазны,
прогон субагентами до соблюдения) — прямой донор нашего `pressure.json`; iron-law и red-flag-таблицы
рационализаций — сильные приёмы принуждения. **Минусы:** список process-скиллов у нас уже покрыт
(`general`/`quality`); bootstrap/хуки — отдельный слой `harness`. **Взято:** pressure-тесты в
eval-формат; bootstrap/iron-law/hook-механизмы — reference (отложено, см. план).

### affaan-m/ECC — reference
Крупный кросс-harness фреймворк (~221k★): 271 скилл, 67 агентов, 20+ хуков, безопасность, memory.
**Плюсы:** боевые паттерны supply-chain-гигиены вендоринга (IOC-скан, санитизация prompt-injection),
hook-профили (minimal/standard/strict), PreCompact memory-save, fact-force gate. **Минусы:** инфраструктура
(память/граф/install-профили/кросс-harness) у нас уже закрыта `maind`/`harness`/`skiller`; массовый
импорт скиллов не нужен (домен у́же, курируется). **Взято:** ничего сразу — supply-chain-скан и
hook-механизмы **отложены** (реальный пробел: вендорим 54 внешних скилла лишь с sha256).

### Founder/idea-audit — методология (Founder's Playbook · CB Insights · context-engineering) — reference
Внешний каркас для founder-трека и нового скилла `idea-audit` (из Perplexity-аудита, факты выверены через
RAG перед фиксацией). **Anthropic Founder's Playbook** (май 2026) — реальный first-party гайд по AI-native
стартапу (стадии Idea/MVP/Launch/Scale; «structured devil's advocate» — ядро стадии Idea); уже цитируется
в `adversarial-check`/`startup-lifecycle`. **CB Insights «42% no market need»** — реальная, но классическая
(~2014) цифра; апдейт 2026 переформулирует как «poor PMF ~43%» → цитировать как классику, не как свежак.
**Anthropic «Effective context engineering for AI agents»** (сен 2025) — реальная статья, основа
Perplexity-навыка `idea-architect`. **Плюсы:** авторитетная рамка скептической работы с AI на стадии идеи;
**минусы:** эпиграф аудита — парафраз (не verbatim), цифру CB Insights легко подать устаревшей. **Взято:**
4 модуля `idea-audit` (first-principles → рынок → арх-pre-mortem → kill/build), stage-context в
`adversarial-check`, AI/Agentic-категория в `risk-assessment`, business_rationale в `architecture`,
falsification-signals в `idea-discovery`, external-signal-гейт в `startup-lifecycle`.

### mem0 — adopt (паттерн, таксономия консолидации)
Источник таксономии консолидации памяти для `analyst.lessons.classify_consolidation`. Канон mem0
(`prompts.py`) — четыре операции: **ADD / UPDATE / DELETE / NOOP** (F-RAG-2, verified perplexity
2026-07). `analyst` берёт таксономию, но **осознанно адаптирует**: **ADD / UPDATE / NOOP / CONFLICT** —
`CONFLICT` заменяет `DELETE`, потому что авто-удаление противоречащего урока нарушило бы инвариант
пакета «человек в гейте» (авто-запись/авто-удаление в знание запрещены). На противоречии analyst не
стирает, а **flag-and-ask**: помечает конфликт и отдаёт решение человеку (`--supersedes`/`--force`).
**Плюсы:** зрелая, проверенная в проде схема extraction→consolidation; retrieve-similar-before-write
ложится на stdlib-Jaccard без зависимостей. **Минусы:** сам mem0 — рантайм-зависимость (LLM-extraction),
её не тащим — берём только паттерн. **Взято:** таксономия (с заменой DELETE→CONFLICT), retrieve-before-write,
soft-invalidate вместо hard-delete, timestamp-ranking как альтернатива decay (у нас — обе: decay + ts).

### garrytan/gstack — reference (watch, пока не используется)
https://github.com/garrytan/gstack — сетап Claude Code Гарри Тана (YC): 23 «opinionated tools»
в ролях CEO/Designer/Eng Manager, 50+ скиллов (`/ship`, `/spec`, `/qa`, `/retro`, `/pair-agent`,
`/context-save`), `gbrain` — семантическая память на PGLite между сессиями. 122.5k★, MIT,
активный (июль 2026, 2264+ PR). Проверено по GitHub API 2026-07-18 (Perplexity ложно счёл часть
этой партии несуществующей — вердикты только по API/README). **Плюсы:** реальная операционная
документация (ARCHITECTURE 32KB, CLAUDE.md 59KB), боевой соло-масштаб; роль-ориентированная
модель близка нашим `roles/`. **Минусы:** свой самодостаточный мир — целиком тащить = дублировать
skiller/harness/maind; часть ценности (память) у нас закрыта mAInd. **Потенциал:** идейный донор
роль-структуры для супервизоров Foreman (мандаты/зоны), паттерны `/spec`, `/context-save`;
внедрять по факту измеренной потребности, через вендоринг отдельных скиллов с провенансом.

### mvanhorn/last30days-skill — reference (watch, пока не используется)
https://github.com/mvanhorn/last30days-skill — агентный «поисковик по людям, не редакторам»:
свежак за 30 дней из Reddit/X/YouTube/HN/Polymarket/TikTok/arXiv, скоринг апвоутами/лайками/
живыми деньгами. 52.6k★, MIT, активный (июль 2026), ставится как CC-плагин или `npx skills add`.
**Плюсы:** zero-config, дополняет наш RAG-стек (perplexity/context7) измерением «что сообщество
реально обсуждает» — полезно founder-треку (competitive-analysis, idea-audit) и research-fanout.
**Минусы:** внешние источники/ключи, к супервизорам отношения не имеет. **Потенциал:** research-
инструмент экосистемы; кандидат на вендоринг в research-бакет по факту потребности.

### aiwithremy/claude-skills-llm-council — reference (только идея; ⚠ НЕТ ЛИЦЕНЗИИ)
https://github.com/aiwithremy/claude-skills-llm-council — скилл «LLM Council» по методологии
Karpathy (karpathy/llm-council): 5 независимых советников → peer-review → синтез председателя.
1.1k★, апрель 2026, **лицензия отсутствует** → код не вендорить, только идея. **Плюсы:** зрелая
методология мульти-перспективной оценки решений. **Минусы:** у нас паттерн уже реализован
своими Workflow-примитивами (judge panel, adversarial verify, perspective-diverse verify) —
дублирование. **Потенциал:** сверка нашей judge-panel-механики с канонической методологией;
возможное применение в прогресс-движке Foreman (совет по спорному вердикту continue/escalate).

### openai/codex-plugin-cc — adopt (Codex CLI, второй водитель) · reference (плагин, opt-in per-plan) — вердикт `2026.07.25-ECO-OPT` P7 (D84/P7.1–P7.3), roadmap закрыт
https://github.com/openai/codex-plugin-cc — **официальный плагин OpenAI** для Claude Code:
`/codex:review` и `/codex:adversarial-review` (второе мнение другой моделью), `/codex:rescue`/
`transfer`/`status`/`result`/`cancel` — делегация задач и фоновые job'ы на Codex, субагент
`codex:codex-rescue`. 29.2k★, Apache-2.0, активный (июль 2026). Требует подписку ChatGPT
(вкл. Free) или OpenAI API key; расходует лимиты Codex, НЕ Claude.

**Фактический вердикт (2026-07-29, `finish` D84 → dogfood P7.1 → инструкционный слой P7.2 →
плагин P7.3).** Роль Codex — **ВТОРОЙ ВОДИТЕЛЬ**, не канал делегирования мелочи: та же
экосистема, те же скиллы, те же команды, тот же план; при проблемах с подпиской Claude
владелец пересаживается на Codex CLI напрямую (`codex`/`codex exec`, канонические формы —
`AGENTS.md` § «Codex launch and hook integrity») и продолжает работу тем же plan-протоколом.
Догфуд на живом item'е плана (`P6.4`) дал вердикт **«дошёл с 4 вмешательствами»**
(`findings/P7.1-switch-test.md` §5) — два из четырёх устранены починкой корневого `AGENTS.md`
этим же заходом (`research/21-P7.2-instruction-slice-spec.md`), два остаются известным риском
канона `plan-protocol` (`roadmap/` § «Добавлено прогоном P7.1»). Плагин `codex-plugin-cc`
**установлен и настроен** (P7.3): always-on цена измерена ДВУМЯ инструментами врозь (нативный
`claude plugin details codex@openai-codex` ≈449 ток апстримной поверхности; репо-проекция
`skiller budget --first-turn` — дельта 0, инструмент структурно слеп к marketplace-плагинам,
граница названа `CLAUDE.md` § «Философия и рамки»), правило отката — по ДЕЛЬТЕ и переводу
через порог 10 000 (`findings/P7.3-plugin-cost-and-procedure.md`). **Правило активации
(текстовое, машинного гейта нет, D84):** плагин задействуется ТОЛЬКО при явном указании в
плане, что данную работу ведут субагенты Codex; по умолчанию не используется — второй водитель
работает Codex CLI НАПРЯМУЮ, не через плагин. **Плюсы:** first-party качество; кросс-модельное
adversarial-ревью (опционально, дорожка B); разгрузка **лимита Claude** (расход Codex — общий
agentic-пул подписки OpenAI, не бесплатная работа). **Минусы:** вторая подписка/биллинг;
координация двух CLI; качество Codex на Laravel/Dart-стеках не замерено; численная экономика
делегирования (пилот дорожки A, `A`/`R`) сознательно НЕ измерялась (D84) — готовый протокол
лежит в `research/16-P7-target-design.md` §2, вытягивается по факту потребности.
**Взято:** Codex CLI как второй водитель (прямой запуск, тот же plan-протокол); правило
активации плагина (текстом); двухинструментный always-on гейт. **Roadmap-стаб закрыт** —
`roadmap/codex-subagent-offload.md` несёт датированный вердикт со ссылкой на
`findings/P7.1-switch-test.md`.

### romarayt/raytsystem-public-os — adopt (механика гейтов), skip (стек)
https://github.com/romarayt/raytsystem-public-os — local-first агентный воркспейс (знания,
документы, задачи, verifiable workflows), Apache-2.0, Python + React. Назначение у нас разное
(мы — менеджер инструментов), поэтому сравнивалась **механика инструкционного слоя и гейтов**,
а не продукт.

**Оценка зрелости — отдельно, потому что обычные индикаторы здесь не работают.** Публичное
дерево — сквошенный снимок: ровно **один коммит** (`b5ac7056`, 2026-07-13), **ноль тегов и
релизов**; ★ и возраст публичной истории не несут информации ни в плюс, ни в минус. Что реально
доказывает эксплуатацию: датированный машиночитаемый отчёт квалификации
(`evals/m5a/results/synthetic-20260711T105905Z.json` — ветка `codex/raytsystem-bootstrap`,
«252 passed», покрытие 81.77 %, гейты G0–G10 с классом свидетельства), 35 ADR с `Consequences`
и `Alternatives considered`, 73 тест-файла (809 КБ) с тестами на политику/guard/crash-recovery,
цепочка версий схем 27→151. Что картину ослабляет: все 35 ADR датированы тремя сутками
(07-10…07-12), бенчмарк опубликован **без результатов**, а автор на своём сайте пишет о себе
«Я не программист» — код агентно-сгенерирован под его контролем. Поэтому вес свидетельства
переносится на «есть тест/артефакт», а не «автор годами это эксплуатировал».

**Полевые свидетельства (issues 07-17…07-24, независимые операторы) — самое ценное:** ingest
квадратичен («~4 s на пустом леджере → ~344 s при ~590 источниках», 1 045 358 чтений на одну
операцию); код-граф падает целиком на пустом `__init__.py` и **не называет файл**; Windows
ломается на безусловном `import resource`. Ответов мейнтейнера нет, PR'ы висят → как **апстрим**
проект не сопровождается, вендорить нечего; берём механику.

**Плюсы:** политика как данные с валидатором формы рядом; preflight — редактированная хеш-запись
(`operation_key`, абсолютный путь не сохраняется) и `CHECKPOINTED_FOR_RESUME` + точная команда
вместо ложного «успеха»; **один** `CheckpointGuard` для CLI и pre-commit, а тест ассертит, что
хук зовёт ту же команду; симулятор политики вызывает **ту же чистую функцию**, что рантайм-гейт;
docs-in-the-same-change-set как DoD + coverage-гейт по **живым** контрактам («cannot pass by
editing the coverage page alone»); матрица возможностей с границей доказательства («A visible UI
section or CLI group is not proof that its external runtime is enabled»); тест, ассертящий
**форму инструкционного слоя** (`AGENTS.md ≤65` строк, `SKILL.md ≤150`, обязательные секции,
запрет дублирования канона в bootstrap, пара golden+adversarial на каждый скилл).
**Минусы:** стек не переносим (uv/pyproject/pydantic/React); каталог-снимок схем на каждую
версию накапливает мёртвые контракты (15 схем удалённого домена живут в v1.2.0–v1.4.0);
docs-гейт коарсовый (зачёт даёт любой файл под `website/docs/`); строгая ревалидация имеет
измеренную цену O(N²); fail-closed без имени виновника — реальный дефект UX.

**Взято:** пока ничего не внедрено — вердикты по 19 приёмам и карта заимствований лежат в
`plans/archive/2026.07.25-ECO-OPT/research/09-rayt-adoption-map.md`; сырьё — `findings/rayt-deep-2026-07-25.md`.
Из них **9 заведены фазой P8** плана `2026.07.25-ECO-OPT` (D41 — отдельный план отменён, чтобы не
плодить межплановую синхронизацию): отчёт закрытия фазы с классом свидетельства
(synthetic/real/`baseline_pending`), `Consequences` в D-записи, `CHECKPOINTED`-отказ с командой,
docs-impact гейт, матрица возможностей, CI-гигиена + verify-tag, `assert_safe_replace_target` в
`core/io.py`, дельта к `validate.sh` и `skiller eval`. Остальные 10 (реестр ролей ревью как
данные, preflight делегирования, провенанс-записи, реестр контрактов, coverage по живым
контрактам, инвариант устаревания графа) — в `roadmap.md` того же плана, тянутся по факту.

## Как это легло в архитектуру

- Канон субагентов (спек, Volt, vijay) → **agent-packs** с каноническими `description`+`<example>`.
- Per-type templating (vijay `team-configurator`, wshobson) → **skiller `profiles/` + детектор в
  `core/` + детерминированная доставка пака** (`harness agent-packs`, `maind sync` провиженер).
- Model-tiers (wshobson) → `profile.model_tiers` → `MODEL_*`-плейсхолдеры.
- Router/self-learning/skill-rules (Rio, session-hooks, itgoyo) → **отложены в `roadmap/`** —
  внедрять по факту измеренной проблемы, не спекулятивно.
- Eval скиллов (anthropics `skill-creator` + superpowers `writing-skills`) → **`skiller eval` +
  формат `evals/`** (поведенческое тестирование: evals/pressure/triggers, with-skill vs baseline).
  Composite-провенанс (несколько источников в одном скилле) → **`upstream.json strategy=merge`**
  (`origins[]` base+supplement, ручной agent-merge). Supply-chain-скан/bootstrap/hook-профили (ECC,
  superpowers) → **отложены** — см. план.
