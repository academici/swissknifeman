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
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | курируемый каталог | 47k★, активный, NOASSERTION-лиц. | reference | подтверждает реальную схему субагента; Design-Review ≈ agent-pack 1:1 |
| [vijaythecoder/awesome-claude-agents](https://github.com/vijaythecoder/awesome-claude-agents) | оркестратор + специалисты | 4.3k★, MIT, ~stale | reference | блюпринт `orchestrator → stack-detect → специалисты` (= наши профили + `_common`) |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | 150+ субагентов | 22k★, MIT, активный | reference | seed-материал ролей; нативный frontmatter |
| [claude-rio](https://github.com/alex-popov-tech/claude-rio) | hooks-matcher (роутинг) | ~20★, MIT, ранний | reference → [roadmap](../roadmap/agent-command-router-hook.md) | контракт `UserPromptSubmit.additionalContext` для будущего router-хука |
| Self-Improving session-hooks | паттерны session-хуков | talk-level, без репо | reference → [roadmap](../roadmap/self-learning-memory.md) | подтверждает `additionalContext`-путь (уже есть в maind) |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | multi-agent runtime | 35k★, MIT | **skip** (reference) | только словарь оркестрации (supervisor/swarm) для прозы — иной слой |
| [itgoyo/awesome-agent-skills](https://github.com/itgoyo/awesome-agent-skills) | каталог скиллов | 138★, CC-BY | reference → [roadmap](../roadmap/skill-rules-sidecar.md) | паттерн `skill-rules.json` сайдкар (отложен) |
| [wshobson/agents](https://github.com/wshobson/agents) | стек-бандлы + model-tiers | 37k★, MIT, активный | reference | блюпринт профилей: стек→бандл, per-agent model-tiers |
| [anthropics/skills](https://github.com/anthropics/skills) | официальные skills (skill-creator, mcp-builder, doc/creative) | first-party, Apache-2.0 (docx/pdf/pptx — Proprietary) | **adopt** (метод) | eval-харнес скиллов из `skill-creator` (evals/benchmark, оптимизация описания); docx/pdf/pptx — **skip** (Proprietary); `mcp-builder` — reference (отложено) |
| [obra/superpowers](https://github.com/obra/superpowers) | process/discipline-скиллы + каркас (hooks-bootstrap) | MIT, активный, мульти-harness | **adopt** (метод) | pressure-тесты (`writing-skills` — TDD для документации) в eval-формат; iron-law/red-flag/SessionStart-bootstrap — reference (отложено) |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | кросс-harness фреймворк (skills/agents/hooks/security) | ~221k★, MIT, активный | reference | supply-chain-скан вендоринга, hook-профили, PreCompact, fact-force gate — **отложено**; инфраструктура (память/граф) уже у `maind` |
| [Anthropic — Founder's Playbook](https://www.anthropic.com/) | методология AI-native стартапа (Idea/MVP/Launch/Scale, Claude как structured devil's advocate) | first-party, май 2026 | **reference** | каркас founder-трека + `idea-audit` (4 модуля, stage-context, premature scaling); эпиграф = парафраз, не verbatim |
| [CB Insights — Why Startups Fail](https://www.cbinsights.com/research/report/startup-failure-reasons-top/) | пост-мортемы стартапов, «no market need» | классика ~2014, апдейт 2026 | **reference** | аргумент зоны idea-validation в `idea-audit`; цитировать как классику (~42%), 2026 реформулирует ~43% poor PMF |
| [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | context engineering для агентов | first-party, сен 2025 | **reference** | основа Perplexity-навыка `idea-architect` (роль/режимы/правила веб-поиска/антипаттерны) |
| [Perplexity — Prompt Guide](https://docs.perplexity.ai/guides/prompt-guide) + Help Center | официальные правила формулировки запросов (specificity, version+context, cap result counts, separate concerns, grounding-rules) | first-party, верифиц. 2026-06-29 | **reference** | факт-основа CORE-скилла `research/query-craft` (5 слотов запроса, анти-паттерны, режимы search/advanced/deep); верифицировано RAG (WebSearch+WebFetch), не по памяти |
| `perplexity-web-mcp` v1.3.0 — integration note (контракт MCP) | конкурентность через демон: общий браузер-демон, до `maxConcurrency` вкладок, пулы (`--pool`), коды ошибок (`BROWSER_BUSY`/`TIMEOUT`/`LOGIN_REQUIRED`/`PROTOCOL_MISMATCH`) | sibling-пакет (вне репо), сверено 2026-06-30 | **adopt** | обновил `research/query-craft` (раздел «Конкурентность и устойчивость») и `general/mcp-advisor` (пул-нота); прежний обход «не параллелить» снят как legacy; `.mcp.json` зонтика → `--pool=swissknifeman` |
| Industry-паттерны workflow-resilience 2025–2026 (rate-limit backpressure/circuit-breaker, job/worker/supervisor liveness, progress+deadline watchdog, `Promise.race`/cancellation, structured-output retry, infra-vs-task failure taxonomy) — Portkey/TrueFoundry/respan.ai/Vercel Workflow/claude-code issues | как проектировать устойчивый agent-workflow под rate-limit/hang | web/vendor-блоги + офиц. SDK-доки, верифиц. `perplexity-web` 2026-07-01 | **reference** | факт-основа раздела «Устойчивость» (`background-agents.md`) и dev-loop-правок (audit `2026-07-01-workflow-resilience-ratelimit`): fail-fast, `infra-failed`, supervisor+`PushNotification`; отклонён in-script `withDeadline` (V8-sandbox: нет `Date.now()`/`setTimeout`/cancel) |
| Industry prompt-engineering для RAG-forcing / verification-footer / self-critique (2025–2026) — plan→retrieve→verify loop, tool-forcing, структурные секции `unverified_assumptions`/`tool_failures`/`verification_report`, «cited but not verified» (dev.to · sey.pro) | как заставить план-агента 100% опираться на свежий RAG и честно выносить непроверенное | web-блоги, верифиц. `perplexity-web` 2026-07-01 | **reference** | факт-основа footer'а «Проверка» в `verify-claims`/`decision-verification`/CLAUDE.md + блока `VERIFICATION` оркестратора + `tool_failures[]` в `dev-loop.js`; решение токен-экономии — агрессивный flat-rate `perplexity-web` |

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
**Решение:** контракт берём, реализацию откладываем в [roadmap](../roadmap/agent-command-router-hook.md)
(внедрять по факту мисроутов), на Python.

### Self-Improving session-hooks — reference → roadmap
Паттерны: direnv-промпты, strike/praise CSV, skill-activation, SessionStart-инжект контекста.
**Плюсы:** всё ложится на уже используемый в maind `additionalContext`-путь. **Минусы:** «CSV-скоринг»
без канона (talk-level); `UserPromptSubmit.additionalContext` протухает на resume. **Решение:**
безопасную форму самообучения — в [roadmap](../roadmap/self-learning-memory.md) (через память maind,
ручное промо).

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
37k★, MIT, активный — стек-именованные бандлы + единый источник→много харнесов + per-agent
model-tiers. **Плюсы:** почти готовый блюпринт для `maind`/skiller-профилей: `specialized/<framework>`
+ `universal` + `core`, версионируемо, без движка. **Минусы:** мульти-харнес генератор тяжёлый —
берём **форму, не масштаб** (нам нужны только claude+cursor). **Взято:** идея per-agent model-tiers
(реализована как `profile.model_tiers` → `MODEL_*`-плейсхолдеры).

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
