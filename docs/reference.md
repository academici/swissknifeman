# Референсы: внешние фреймворки и каталоги агентов Claude Code

Карта внешних источников, изученных при проектировании слоя субагентов/шаблонов swissknifeman
(глубокий research-аудит, июнь 2026). Для каждого — что это, зрелость, **плюсы/минусы**, вердикт
и что именно взято в swissknifeman. Цель — чтобы дальше можно было возвращаться к ним адресно.

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

## Как это легло в архитектуру

- Канон субагентов (спек, Volt, vijay) → **agent-packs** с каноническими `description`+`<example>`.
- Per-type templating (vijay `team-configurator`, wshobson) → **skiller `profiles/` + детектор в
  `core/` + детерминированная доставка пака** (`harness agent-packs`, `maind sync` провиженер).
- Model-tiers (wshobson) → `profile.model_tiers` → `MODEL_*`-плейсхолдеры.
- Router/self-learning/skill-rules (Rio, session-hooks, itgoyo) → **отложены в `roadmap/`** —
  внедрять по факту измеренной проблемы, не спекулятивно.
