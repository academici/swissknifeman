# Artifex — консолидированный аудит внешних источников для супервизора безлюдного исполнения планов

Финальная объединённая версия, включающая результаты всех трёх стадий проработки без потерь: (1) первичный сбор референсов из `swissknifeman` и веб-поиск новых 2025–2026 проектов, (2) углублённый технический разбор существующих хуков `harness` и уточнение зрелости/лицензий, (3) дозасев новых кандидатов и собственные архитектурные рекомендации для Artifex. Все карточки, таблицы и вердикты из предыдущих итераций сохранены и дополнены — ничего не удалено.

## Контекст и метод

Artifex проектируется как надстройка над экосистемой `academici/swissknifeman` — реестром скиллов, хуков и агент-паков для Claude Code. Репозиторий уже ведёт формализованный каталог провенанса `docs/reference.md`, где каждый внешний источник, использованный при проектировании, отмечается строкой с вердиктом `adopt`/`reference`/`skip`. Этот каталог стал основой части (а) задачи; часть (в) — самостоятельный многораундовый веб-поиск свежих (2025–2026) кандидатов по каждой из шести функций Artifex, доведённый до трёх последовательных стадий проработки.

Функции Artifex для сквозной нумерации в таблицах:
1. CLI-драйвер headless-сессий с парсингом статусов/handoff
2. Детекция прогресса и зацикливания
3. Политика авто-подтверждения прав (PreToolUse/PermissionRequest)
4. Боты-эскалаторы (Telegram + MAX, блокирующий Q&A, много каналов)
5. Пер-плановый журнал исполнения (привязка сессий к плану)
6. Упаковка и версионируемая раскатка скиллов/хуков по проектам

## Часть 1. Референс-репозитории, уже зафиксированные в swissknifeman

### 1.1 Полная сводная таблица провенанса из docs/reference.md

Полный `docs/reference.md` фиксирует существенно больше источников, чем устный список из запроса (superpowers, claude-task-master, spec-kit, awesome-списки VoltAgent, ponytail, beads, planning-with-files). Примечательно, что `claude-task-master` и `ponytail` в формальном реестре **отсутствуют** — вероятно, упоминались в устном контексте проектирования, но не попали в зафиксированный каталог провенанса; ближайшие по духу source-of-truth-планировщики зафиксированы под другими именами: `github/spec-kit`, `steveyegge/beads`, `othmanadi/planning-with-files`.

| Источник | Что | Зрелость / лицензия | Вердикт swissknifeman | Релевантность Artifex |
|:--|:--|:--|:--|:--|
| Официальный спек Claude Code | subagents/skills/hooks/plugins, «steering» | first-party, активный | **adopt** | Базовый контракт хуков для функций 1,3,6 |
| [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) | курируемый каталог | 47k★, NOASSERTION-лиц. | reference | Индекс для поиска готовых hook-скриптов |
| [vijaythecoder/awesome-claude-agents](https://github.com/vijaythecoder/awesome-claude-agents) | оркестратор + специалисты | 4.3k★, MIT, ~stale | reference | Блюпринт `orchestrator → stack-detect → специалисты` |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | 150+ субагентов | 22k★, MIT, активный | reference | Не решает функции 1-6, только seed ролей |
| [claude-rio](https://github.com/alex-popov-tech/claude-rio) | hooks-matcher (роутинг) | ~20★, MIT, ранний | reference → roadmap | Контракт `UserPromptSubmit.additionalContext` для инъекции контекста между итерациями Artifex |
| Self-Improving session-hooks | паттерны session-хуков (direnv, strike/praise CSV) | talk-level, без репо | reference → roadmap | Идея журнала успех/неуспех итерации (функция 2/5) |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | multi-agent runtime | 35k★, MIT | **skip** (reference) | Запрещён ограничениями задачи (рантайм-замена) |
| [itgoyo/awesome-agent-skills](https://github.com/itgoyo/awesome-agent-skills) | каталог скиллов | 138★, CC-BY | reference → roadmap | Паттерн `skill-rules.json` сайдкар для функции 6 |
| [wshobson/agents](https://github.com/wshobson/agents) | стек-бандлы + model-tiers | 37k★, MIT, активный | reference | Блюпринт версионируемых профилей раскатки (функция 6) |
| [anthropics/skills](https://github.com/anthropics/skills) | skill-creator, mcp-builder, doc/creative | first-party, Apache-2.0 (docx/pdf/pptx — Proprietary) | **adopt** (метод) | Eval-методология для паков Artifex |
| [obra/superpowers](https://github.com/obra/superpowers) | process-скиллы + SessionStart-bootstrap | MIT, активный, мульти-harness | **adopt** (метод) | Bootstrap-паттерн инъекции политики перед первым tool-call |
| [affaan-m/ECC](https://github.com/affaan-m/everything-claude-code) | кросс-harness фреймворк | ~221k★, MIT, активный | reference | Supply-chain-скан, hook-профили minimal/standard/strict (функция 6) |
| Industry workflow-resilience 2025–2026 (Portkey/TrueFoundry/respan.ai/Vercel Workflow/claude-code issues) | rate-limit backpressure, circuit-breaker, watchdog, `infra-failed`-таксономия | web/vendor-доки, верифиц. 2026-07-01 | **reference** | Прямой факт-фундамент устойчивости CLI-драйвера Artifex (функции 1,2) |
| LangSmith / AgentOps / Helicone | категории отказов агентов: tool-error, no-op/избыточные retry, застрявшие циклы, раздутие контекста | first-party доки, верифиц. 2026-07-02 | **reference** | Ориентир категорий эвристик `core/pathology.py` для функции 2 |
| [Kulaxyz/self-learning-skills](https://github.com/Kulaxyz/self-learning-skills) | промпт-скилл самообучения | 621★, MIT, ~3 дня, viral | **reference** | Эпистемическая дисциплина журналирования для функции 5 |
| [affaan-m ECC — continuous-learning-v2] | observations→instincts→evolved-skills, confidence-тиры | MIT, активный | **adopt (паттерн)** | 3-ярусная лестница confidence для human-gated промоушена (функция 6) |
| [Diátaxis](https://diataxis.fr/) | фреймворк структуры документации | de-facto стандарт | reference (метод) | Не напрямую релевантен Artifex, но применим к докам пакета |
| [mem0](https://github.com/mem0ai/mem0) ([arxiv 2504.19413](https://arxiv.org/abs/2504.19413)) | память агентов: extraction→consolidation | Apache-2.0 | **adopt (паттерн)** | Таксономия ADD/UPDATE/NOOP/CONFLICT — база для классификации итераций handoff (функция 2) |
| Self-improving/anti-poisoning канон (SICA/Voyager/Reflexion/OWASP ASI06/MITRE AML.T0080) | guardrails против model-collapse/memory-poisoning | академ.+security, верифиц. 2026-07 | reference (комплаенс) | Косвенно применимо к безопасности эскалации/памяти Artifex |
| [Roave/BackwardCompatibilityCheck](https://github.com/Roave/BackwardCompatibilityCheck) | статический BC-чекер PHP | стабильный, MIT | **adopt** | Не относится напрямую к Artifex (специфика Laravel-паков) |
| [github/spec-kit](https://github.com/github/spec-kit) | spec-driven development, MD-артефакты как SSOT | first-party GitHub, MIT, активный | reference | Machine-markers/фазовая заморозка/anti-staleness — изучено при дизайне plan-протокола |
| [steveyegge/beads](https://github.com/steveyegge/beads) | git-backed граф-issue-tracker, DAG задач | 13.7k★, активный | reference | Изучено при дизайне plan-протокола; прямой донор для функции 5 |
| [othmanadi/planning-with-files](https://github.com/othmanadi/planning-with-files) | Manus «Context Engineering», todo.md-recitation | сторонний skill-репо | reference | Изучено при дизайне plan-протокола; донор для функции 2 |
| `code.claude.com/docs/en/skills` (модель/effort) | подтверждён факт: **нет API переключения модели/effort сессии изнутри команды** | first-party, верифиц. 2026-07-15 | **reference** | Критично ограничивает архитектуру эскалации Artifex (функция 1) |
| Токен-экономия 2026 (prompt-caching, `/compact` vs `/clear`, sub-agent isolation, MCP deferred loading) | потолок+truncation-receipt, прополка MCP-серверов | web+first-party, верифиц. 2026-07-15 | reference (backlog) | Headless-сессии Artifex должны учитывать эти лимиты при массовом запуске |

### 1.2 Дополнительные внутренние roadmap-документы swissknifeman, релевантные Artifex

Внутренний roadmap `plan-audit-loop.md` фиксирует эмпирически измеренную патологию «зацикливания» на уровне плана (три RED-аудита подряд на одной фазе, рост items 4→18, версии плана 1.0.0→1.4.0) и проектирует решение — двухступенчатую проверку (дешёвый детерминированный конфликт-скан + один дорогой финальный аудит) с потолком раундов и порогом severity. Это прямой прообраз функции 2 Artifex, только на уровне ревью плана, а не построчного парсинга статусов CLI-сессии.

Roadmap `agent-command-router-hook.md` описывает реализованный (v1) dual-hook маршрутизатор: `SessionStart` для статичной политики и `UserPromptSubmit` для per-turn keyword-bias подсказки, с режимами `propose`/`auto_dispatch`/`off`. Демонстрирует рабочий паттерн хук-контракта (`hookSpecificOutput.additionalContext`), переиспользуемый Artifex для инъекции контекста между headless-итерациями.

## Часть 2. Уже реализованные механизмы harness — что Artifex обязан расширить, а не дублировать

### 2.1 auto-approve — детальный разбор трёх источников (функция 3)

Хук-комплекс `packages/harness/configs/claude-code/hooks/auto-approve/` уже реализует функцию 3 частично, с явным документированным провенансом:

| Проект | URL | Что взято | Что отклонено |
|:--|:--|:--|:--|
| oryband/claude-code-auto-approve | https://github.com/oryband/claude-code-auto-approve | Разбор компаунд-команд через AST `shfmt`, allow/deny-листы, активный `deny` | — |
| yigitkonur/hooks-claude-approve (ранее auto-approve-claude-plan) | https://github.com/yigitkonur/hooks-claude-approve | Авто-подтверждение `ExitPlanMode`, связка с `defaultMode: bypassPermissions` | Craft.do-архивирование |
| froggeric/claude-smart-approval | https://github.com/froggeric/claude-smart-approval | Декомпозиция компаунд-команд на сегменты, идея двухстадийной оценки | Stage-2 AI и auto-learning — намеренно НЕ включены (детерминированность) |

Технический разбор по актуальному коду:

**yigitkonur/hooks-claude-approve** — bash+jq, MIT, 3 звезды, последний коммит май 2026. Хук вешается на `PermissionRequest` с матчером `ExitPlanMode` (не на `Stop`), возвращает `{"behavior":"allow"}` мгновенно и опционально инжектит `additionalContext` с orchestrator-директивой. **Критично для Artifex:** задокументированы два upstream-бага Claude Code — `#49525` (с версии 2.1.110+ `bypassPermissions` в ответе хука молча отбрасывается парсером, сессия скатывается в `acceptEdits`) и `#39973` (`ExitPlanMode` сбрасывает режим разрешений независимо от предыдущего режима сессии). Artifex не может полагаться на runtime-переключение через хук на всех версиях CLI — нужен явный флаг `--permission-mode bypassPermissions` при запуске `claude -p` с проверкой версии и fallback.[^1][^2]

**oryband/claude-code-auto-approve** — компаунд-команды парсятся в JSON AST через `shfmt`, `jq`-фильтр обходит дерево и проверяет каждую под-команду отдельно, включая `$(...)`/`<(...)`/subshells. Решает уязвимость наивных regex-approve-хуков (опасный сегмент внутри «безопасной» составной команды).[^3][^4]

**froggeric/claude-smart-approval** — форк oryband с двухстадийной оценкой: неопределённые команды разрешаются через ~8-секундную headless-сессию на `haiku` как security-гейткипер, решение кешируется, неопределённость эскалирует к человеку. Паттерн «дешёвая модель как гейткипер» также встречается в `defrex/claude-code-permission-policy` — то есть подтверждён двумя независимыми источниками как зрелый архитектурный паттерн, хотя swissknifeman сознательно отклонил его в пользу детерминированности.[^5][^6]

### 2.2 run-report — единственный существующий механизм, близкий к функции 5

`packages/harness/configs/claude-code/hooks/run-report/run-report.py` — SessionEnd-хук, построчно (без слурпа) парсит `transcript_path` и пишет структурированный отчёт в `<project>/.claude/runs/<session_id>.json`. Ограничения, которые Artifex должен закрыть:

- **SessionEnd = одна запись на сессию** — несколько задач в одной сессии схлопнутся в один run-report.
- **Схема транскрипта не заморожена официально** — парсинг защитный, деградирует до форензики (bash-лог + git-diff) при сбое.
- **Классификация "тест/линт" эвристическая** — по паттернам команд, может промахнуться на нетипичных командах.
- **`devloop`-срез — best-effort**, зависит от того, вынёс ли воркфлоу структурный JSON в транскрипт.

Отдельный модуль `_usage.py` (10.5 КБ) разбирает usage/cost-метрики из транскрипта — релевантен функции 1 Artifex для эскалации по бюджету (пункт плана израсходовал непропорционально много токенов — сигнал зацикливания по затратам, а не только по контенту).

**Практический вывод:** поскольку CLI-драйвер Artifex запускает свежую headless-сессию на каждый пункт плана, связка «1 сессия = 1 пункт плана = 1 run-report.json» естественно решает проблему схлопывания записей — Artifex может напрямую переиспользовать `_lib.py`-парсер (28 КБ, защитный построчный разбор) как библиотеку, добавив слой сопоставления `session_id → plan_id + item_id`, а не писать парсер транскрипта заново.

## Часть 3. Глубокий разбор каждого внешнего кандидата по функциям

### Функция 1 — CLI-драйвер headless-сессий

| Кандидат | Механизм | Зрелость / лицензия | Интеграция | Вердикт |
|:--|:--|:--|:--|:--|
| [anthropics/claude-code ralph-wiggum](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) | `Stop`-хук перехватывает попытку сессии завершиться, повторно подаёт тот же промпт до `--completion-promise`/`--max-iterations`. Цикл **внутри одной сессии** | first-party Anthropic, активный[^7] | Plugin + hook | ТОЛЬКО ИДЕЯ — контракт блокирующего Stop-хука |
| [mikeyobrien/ralph-orchestrator](https://github.com/mikeyobrien/ralph-orchestrator) | «hat-based orchestration»: внешний Rust-раннер многократно запускает агента (Claude Code/Codex/Gemini CLI), состояние персистентно между запусками | 2.9k★, MIT, май 2026[^8][^9][^10] | CLI-бинарь (Rust) | АДАПТИРОВАТЬ — архитектурный аналог внешнего драйвера |
| [obra/claude-session-driver](https://github.com/obra/claude-session-driver) | Контроллер запускает worker-сессии Claude Code в tmux; каждый worker — полноценная сессия со своим контекстом; события `pre_tool_use` пишутся в JSONL-лог, worker ждёт 30 сек на approve/deny от контроллера перед auto-approve; человек может attach к любому tmux-worker'у напрямую | 1.0, MIT, требует tmux+jq+claude CLI, февр. 2026[^11][^12] | Plugin (`claude /install claude-session-driver@superpowers-marketplace`) + tmux + JSONL event log | **АДАПТИРОВАТЬ** — новый ключевой кандидат (см. ниже) |

**Новый детальный разбор obra/claude-session-driver (стадия 3):** это первый найденный проект, реализующий именно паттерн «контроллер порождает и мониторит несколько worker-сессий Claude Code», близкий к архитектуре Artifex. Механизм по авторскому блог-посту: воркер — полная tmux-сессия Claude Code со своим контекстом и историей; коммуникация идёт через обычный текст в tmux plus JSONL событийный лог, без специального API. Каждый вызов инструмента воркером эмитит `pre_tool_use`-событие, и воркер физически приостанавливается на 30 секунд, ожидая approve/deny от контроллера, прежде чем сработает auto-approve по таймауту. Автор явно подчёркивает: «нет специального протокола, только текст в tmux и события в JSONL-файле». Rust-реализация клиента существует как крейт `claude-session-driver` на crates.io. Вердикт: **АДАПТИРОВАТЬ** — паттерн `pre_tool_use → пауза 30с → approve/deny → auto-approve по таймауту` прямо решает часть функции 3 (эскалация с деградацией в безопасное действие при отсутствии ответа), а модель «полноценная tmux-сессия на воркера с возможностью человека attach'иться напрямую» — альтернативный, интерактивный, а не headless путь; для Artifex (принципиально headless, `claude -p` + JSON) нужно взять только идею event-JSONL-лога и таймаут-деградации, не сам tmux-механизм.[^12][^11]

Смежные находки в этой же нише multi-session orchestration (для полноты, не приоритетные): `primeline-ai/claude-tmux-orchestration` (heartbeat monitoring + file-based coordination), `qrtt1`-гист «human-being skill» (tmux PO-proxy → Navigator ↔ Driver), `craigsc/cmux` и `0xkaz/claunch` (персистентные project-based CLI-сессии) — все они варианты одной темы «tmux-обёртка вокруг claude CLI», не headless-native, поэтому ниже приоритетом для Artifex, чем ralph-orchestrator и claude-session-driver.[^13][^14][^15][^16]

### Функция 2 — детекция прогресса и зацикливания

| Кандидат | Механизм | Зрелость / лицензия | Вердикт |
|:--|:--|:--|:--|
| [frankbria/ralph-claude-code](https://github.com/frankbria/ralph-claude-code) | **Дуальное exit-условие**: семантический анализ вывода через `response_analyzer.sh` И явный строковый сигнал `EXIT_SIGNAL` — выход только при обоих одновременно. Плюс rate limiting (конфигурируемый лимит вызовов/час, выбор «ждать или выйти» при достижении), circuit breaker (автосброс по завершению или при открытии breaker), session continuity через файловую систему вместо API-памяти | MIT, автор Frank Bria, реализация техники Geoffrey Huntley «Ralph»; звёзды разнятся по агрегаторам (1.2k–9.6k, доверять live-странице репо, не индексам)[^17][^18][^19][^20] | **АДАПТИРОВАТЬ** — самый конкретный проверенный по коду паттерн различения честной итерации от топтания |
| [blackwell-systems/claudewatch](https://github.com/blackwell-systems/claudewatch) | «AgentOps для Claude Code»: real-time error loops, drift detection, friction analysis, self-awareness hooks, MCP-инструменты, cost-per-commit и agent success rate метрики | Молодой проект (публикация ~февр. 2026); родственный репозиторий того же автора `blackwell-systems/dotclaude` подтверждённо Apache 2.0[^21], но лицензия конкретно claudewatch отдельно не подтверждена в веб-поиске — **требует прямой проверки файла LICENSE перед adoption** | АДАПТИРОВАТЬ (после верификации кода и лицензии — статус не изменился со стадии 2) |
| [lucemia/claude-session-analyzer](https://github.com/lucemia/claude-session-analyzer) | Постфактум-анализ логов сессий: глубина рассуждений, паттерны tool-usage, поведенческие регрессии, тональность пользователя | Зрелость/лицензия не подтверждены веб-поиском | ТОЛЬКО ИДЕЯ — набор метрик как чек-лист для журнала Artifex |
| [defrex/claude-code-permission-policy](https://github.com/defrex/claude-code-permission-policy) | (см. функцию 3, отдельно упомянут здесь только как источник логирования решений, релевантного пост-анализу) | 3 звезды подтверждено веб-поиском на стадии 3[^22] | см. функцию 3 |
| [possibilities/claude-code-generic-hooks](https://github.com/possibilities/claude-code-generic-hooks) | Команда `activity` трекает старт/стоп рабочих сессий через `UserPromptSubmit`/`Stop`-хуки в SQLite-подобное хранилище — даёт скелет измерения границ итерации | Зрелость/лицензия не подтверждены | ТОЛЬКО ИДЕЯ — граница «где кончается одна попытка, начинается следующая» |

**Уточнение зрелости claude-code-permission-policy на стадии 3:** веб-поиск подтвердил точную цифру — **3 звезды**, что явно указывает на очень раннюю стадию проекта несмотря на зрелую и продуманную архитектуру механизма. Это не отменяет вердикт «ВЗЯТЬ как есть», но повышает риск: малое сообщество означает отсутствие внешнего code-review и потенциально непротестированные edge-кейсы — перед adoption рекомендуется собственный аудит кода хука, а не слепое доверие звёздам.[^22]

### Функция 3 — политика авто-подтверждения прав

| Кандидат | Механизм | Зрелость / лицензия | Вердикт |
|:--|:--|:--|:--|
| [defrex/claude-code-permission-policy](https://github.com/defrex/claude-code-permission-policy) | PreToolUse-перехват → decl. `.claude/PERMISSION_POLICY.md` → AI-гейткипер на `claude -p --model haiku` → `allow`/`deny`/`ask`, fail-open при ошибке, логирование в `.claude/logs/permission-policy.log` | 3★, активный, требует проверки точной формы лицензии[^22] | **ВЗЯТЬ как есть** (с аудитом кода перед adoption ввиду малого сообщества) |
| oryband/claude-code-auto-approve + froggeric/claude-smart-approval + yigitkonur/hooks-claude-approve | см. §2.1 — уже адаптированы внутри `harness/auto-approve` | см. §2.1 | Не искать замену — паттерн уже интегрирован в экосистему |
| [possibilities/claude-code-generic-hooks](https://github.com/possibilities/claude-code-generic-hooks) `yolo`-режим | Авто-одобряет всё кроме принятия плана — шире allow-листа, но не декларативно | Зрелость/лицензия не подтверждены | ТОЛЬКО ИДЕЯ, слишком широк, противоречит декларативному принципу |
| [obra/claude-session-driver](https://github.com/obra/claude-session-driver) `pre_tool_use`-таймаут | 30-секундное окно ожидания решения контроллера перед auto-approve по умолчанию | MIT, 1.0[^11] | АДАПТИРОВАТЬ — таймаут-деградация как fallback-паттерн эскалации |

### Функция 4 — боты-эскалаторы (Telegram + MAX, блокирующий Q&A)

| Кандидат | Механизм | Зрелость / лицензия | Вердикт |
|:--|:--|:--|:--|
| [MAVII-RU/max-messenger-plugin](https://github.com/MAVII-RU/max-messenger-plugin) | MCP channel plugin, бридж `platform-api.max.ru` ↔ Claude Code через `--dangerously-load-development-channels`; инструменты `reply`/`edit_message`/`send_file`; multi-agent через `MAX_STATE_DIR` | Свежий (апр. 2026), TypeScript/Bun, **лицензия подтверждена как MIT**[^23] | **ВЗЯТЬ как есть** (базовый канал) + доработка блокирующего Q&A сверху |
| [easyfold/claude-tg](https://pkg.go.dev/github.com/easyfold/claude-tg) | Go-демон, Kitty terminal remote control; `Stop`/`PermissionRequest`/`SessionEnd`-хуки форвардят запросы в Telegram-топик; ответ (`1`/`2`/`3`) транслируется как keypress обратно в терминальную панель — сессия физически ждёт | Требует Kitty-terminal, лицензия не подтверждена[^24] | АДАПТИРОВАТЬ — паттерн блокирующего PermissionRequest→Telegram→ожидание, привязку к Kitty заменить на headless-native |
| [gergomiklos/heyagent](https://github.com/gergomiklos/heyagent) | `hey claude` запускает провайдера в `--dangerously-skip-permissions -p --output-format json`, поллинг Telegram, группировка сообщений в очередь | MIT, 84★, 14 форков, активный[^25] | АДАПТИРОВАТЬ — режим `--dangerously-skip-permissions` противоречит функции 3, брать только pairing-флоу и группировку очереди |
| [hanxiao/claudecode-telegram](https://github.com/hanxiao/claudecode-telegram) | Bridge получает Telegram-вебхуки, инжектит сообщения через tmux; `Stop`-хук читает транскрипт и отправляет ответ обратно | Зрелость/лицензия не подтверждены | ТОЛЬКО ИДЕЯ |
| [RichardAtCT/claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram) | Полноценный удалённый доступ к Claude Code через Telegram-бот с session persistence | Зрелость/лицензия не подтверждены | ТОЛЬКО ИДЕЯ |
| [op7418/Claude-to-IM-skill](https://github.com/op7418/Claude-to-IM-skill) | Мост Claude Code/Codex к нескольким IM-платформам (Telegram, Discord, Feishu/Lark) | Зрелость/лицензия не подтверждены | ТОЛЬКО ИДЕЯ — паттерн multi-channel уже в одном проекте, близко к требованию «несколько каналов параллельно» |
| anthropics/skills PR #419 (Buildr) | Bridge Claude Code сессии к Telegram-боту: mirror сообщений, форвард permissions, stop-задачи | PR-стадия в official skills-репо | ТОЛЬКО ИДЕЯ — сигнал, что first-party экосистема тоже движется в эту сторону |

### Функция 5 — пер-плановый журнал исполнения

| Кандидат | Механизм | Зрелость / лицензия | Вердикт |
|:--|:--|:--|:--|
| [steveyegge/beads](https://github.com/steveyegge/beads) | Git-backed DAG-трекер задач; `bd ready` возвращает только разблокированные задачи; `gate`-система бриджит внешние условия (merge PR, прогон CI, таймеры) в граф зависимостей | 13.7k★, MIT, активный[^26][^27] | АДАПТИРОВАТЬ — заменить markdown-парсинг статусов плана на граф-модель с gate-условиями |
| harness `run-report` (внутренний) | SessionEnd-парсер транскрипта → `.claude/runs/<sid>.json`; `_lib.py` (28 КБ) переиспользуем как библиотеку; `_usage.py` — cost/usage-метрики | Внутренний, зрелый, используется в проде экосистемы | Прямая база — доработать привязкой session_id↔plan_id, не переписывать |
| [lucemia/claude-session-analyzer](https://github.com/lucemia/claude-session-analyzer) | Количественный анализ логов: thinking depth, tool usage patterns, behavioral regressions | Не подтверждено | ТОЛЬКО ИДЕЯ — чек-лист метрик для дизайна журнала |
| [obra/claude-session-driver](https://github.com/obra/claude-session-driver) event-JSONL | Каждое tool-событие worker-сессии логируется в JSONL с session-id — прообраз структуры журнала «что произошло в конкретной сессии» | MIT[^11] | ТОЛЬКО ИДЕЯ — формат событийного лога как референс схемы |

### Функция 6 — упаковка и версионируемая раскатка

| Кандидат | Механизм | Зрелость / лицензия | Вердикт |
|:--|:--|:--|:--|
| [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code) | Hook-профили minimal/standard/strict, supply-chain-скан (IOC), `PreCompact` memory-save, fact-force gate | ~221k★, MIT[^28] | АДАПТИРОВАТЬ — профили строгости хуков, не весь фреймворк |
| [wshobson/agents](https://github.com/wshobson/agents) | Стек-именованные бандлы, единый источник → много харнесов, per-agent model-tiers | 37k★, MIT, активный | ТОЛЬКО ИДЕЯ — уже частично реализовано в `skiller`/`harness` |
| Внутренний `harness agent-packs` | `render`/`upgrade`/`remove`/`list`/`doctor`; upgrade — категории new/safe-apply/conflict/user-owned; lock-файл `.claude/agent-pack.lock.json`; `src_pack`-шаринг контента без копий | Внутренний, зрелый, в проде | Прямая база для Artifex — версионируемая раскатка уже решена на уровне пакетов; расширить на хуки Artifex |

### Функции без готовых зрелых решений (подтверждено на всех трёх стадиях)

- **Функция 1 в части парсинга статусов/handoff конкретно формата плана swissknifeman** (D-лог, machine-markers, Items 🟢/всего) — ни один внешний проект не парсит именно этот формат; писать с нуля, взяв внешний контракт цикла у ralph-orchestrator/claude-session-driver.
- **Функция 2 в части «топтания» (одно чиним — другое ломаем)** на уровне multi-file diff между итерациями — заявлено у claudewatch/ralph-claude-code, но код не полностью верифицирован по всем деталям; строить с нуля на основе taxonomии mem0 (ADD/UPDATE/NOOP/CONFLICT) + дуального exit-условия ralph-claude-code.
- **Функция 4 в части единого протокола нескольких параллельных каналов с общим блокирующим Q&A** — Telegram-мосты и MAX-плагин существуют раздельно; интеграционный слой писать самостоятельно.
- **Функция 5 в части нативной привязки сессии Claude Code к плану** — подтверждённый факт архитектуры CLI («нативно сессии с планами не связаны»), а не пробел стороннего инструмента; требуется собственный маппинг session-id ↔ plan-id через SessionStart/SessionEnd-хуки.
- **Функция 6 в части upgrade-drift паков между многими проектами** — внутренний roadmap `agent-packs-upgrade-drift.md` явно фиксирует это как нерешённую задачу; ни один внешний инструмент её не закрывает целиком.

## Часть 4. Собственные архитектурные идеи для Artifex (дополнение аналитика)

Помимо систематизации найденных источников, ниже — предложения, не привязанные к конкретному внешнему репозиторию, а синтезированные из сопоставления всех находок и архитектурных ограничений Claude Code CLI:

1. **Двухуровневая модель эскалации вместо одноуровневой.** Все найденные Telegram/MAX-мосты реализуют плоскую модель «вопрос → человек → ответ». Artifex работает с многофазными планами, где разные пункты имеют разную критичность (по аналогии с severity-порогом из `plan-audit-loop.md`). Разумно ввести два уровня эскалации: **soft** (сессия продолжает работу над следующим независимым пунктом плана, пока ждёт ответа на текущий — паралелизм в рамках DAG, аналог `bd ready` у beads) и **hard** (полная блокировка всего плана до ответа — для пунктов с зависимостями). Ни один найденный проект этого не делает, потому что ни один не привязан к формату многофазного плана.[^27]

2. **Единый "escalation envelope" формат поверх разных каналов.** Вместо того чтобы у каждого канала (Telegram/MAX) быть своей семантикой вопроса, стоит завести единый JSON-конверт (`plan_id`, `item_id`, `session_id`, `severity`, `question`, `options[]`, `timeout_action`) и адаптеры Telegram/MAX как chансferers этого конверта, а не переписывать логику эскалации под каждый канал. Это прямое расширение паттерна MCP-каналов MAX-плагина и hook-контракта claude-tg, но с абстракцией на уровне Artifex, а не канала.[^23][^24]

3. **Таймаут-деградация по умолчанию — из claude-session-driver, но с политикой, а не фиксированным числом.** 30-секундный таймаут auto-approve у claude-session-driver жёстко закодирован; для Artifex разумнее сделать таймаут функцией severity из декларативного policy-файла (по аналогии с `PERMISSION_POLICY.md` у defrex) — критичные операции (`rm -rf`, деплой) получают бесконечный таймаут (блокировка навсегда до ответа человека), рутинные — короткий с деградацией в безопасное действие (skip/retry), а не в «разрешить».[^11][^22]

4. **Классификация handoff как машина состояний, а не одноразовая метка.** Идея ADD/UPDATE/NOOP/CONFLICT из mem0-адаптации в контексте Artifex должна работать не как единичная классификация текущей итерации, а как переходы состояний по всему циклу пункта плана: `ADD→UPDATE→UPDATE→NOOP` (это нормальная сходящаяся доработка) vs `ADD→UPDATE→CONFLICT→UPDATE→CONFLICT` (это и есть искомое «одно чиним — другое ломаем»). Порог эскалации — не единичный NOOP/CONFLICT, а паттерн переходов за N последних итераций (кольцевой буфер, как threshold+cap у `plan-audit-loop.md`).

5. **Cost-aware detection как отдельный сигнал, независимый от контентного анализа.** Модуль `_usage.py` в run-report уже даёт данные, которые никто из внешних кандидатов не использует для детекции зацикливания: если пункт плана на 3-й итерации расходует токенов **больше**, чем на 1-й (а не меньше, как ожидалось бы при сходящейся доработке), это самостоятельный, дешёвый в вычислении сигнал патологии — независимый от семантического анализа ralph-claude-code и применимый даже когда содержательный анализ неоднозначен.[^20]

6. **Версионирование policy-файла синхронно с версией плана.** Поскольку `PERMISSION_POLICY.md`-паттерн decfrex статичен на уровне репозитория, а Artifex работает с версионируемыми планами (`plans/2026.MM.DD-*`, версии 1.0.0→1.4.0 по образцу `plan-audit-loop.md`), разумно привязать permission-policy к конкретной версии плана: при повышении критичности плана (например, после эскалации по функции 2) политика автоматически ужесточается для оставшихся пунктов — это использует уже существующий в экосистеме механизм версионирования плана как триггер для другого механизма (permission policy), которого по отдельности НИ У ОДНОГО внешнего кандидата нет вместе.[^22]

7. **Reuse существующего agent-packs lock-механизма для функции 6 Artifex, а не изобретение нового.** `harness agent-packs` уже имеет зрелую upgrade-логику (категории new/safe-apply/conflict/user-owned, lock-файл, `src_pack`-шаринг). Вместо того чтобы Artifex вводил собственную систему версионирования хуков (что делает, например, ECC через hook-профили), разумнее оформить хуки/скиллы Artifex как ещё один `agent-pack` в уже существующей системе — тогда upgrade-drift между проектами решается бесплатно, без нового кода.

## Часть 5. Топ-5 рекомендаций по порядку внедрения (обновлено на стадии 3)

1. **Permission-policy хук (функция 3) — первый.** `defrex/claude-code-permission-policy` почти буквально закрывает требование, но требует code-audit ввиду всего 3 звёзд. Согласовать формат policy-файла с уже существующими permission-пресетами `harness`. Дополнить таймаут-деградацией по severity (идея 3 выше).[^22]

2. **CLI-драйвер как внешний процесс (функция 1) — архитектура ralph-orchestrator + claude-session-driver, логика собственная.** Взять у `mikeyobrien/ralph-orchestrator` паттерн внешнего демона с персистентным состоянием между запусками, у `obra/claude-session-driver` — событийный JSONL-лог и таймаут-деградацию auto-approve. Полностью переписать парсинг статусов под формат плана swissknifeman — готового парсера нет ни у кого.[^8][^9][^11]

3. **Таксономия зацикливания как машина состояний (функция 2).** Взять адаптированную swissknifeman таксономию mem0 (ADD/UPDATE/NOOP/CONFLICT), дуальное exit-условие ralph-claude-code (семантика + явный сигнал), двухступенчатую проверку из `plan-audit-loop.md` и добавить cost-aware сигнал через `_usage.py` (идея 5 выше) — многослойная детекция вместо единичной эвристики.[^17][^20]

4. **MAX+Telegram мост с единым escalation envelope (функция 4).** `MAVII-RU/max-messenger-plugin` (MIT, взять как есть) + паттерн блокирующего ожидания из `easyfold/claude-tg`, адаптированный под headless вместо Kitty-keypress; обернуть в единый JSON-конверт эскалации (идея 2 выше) вместо дублирования логики на каждый канал.[^24][^23]

5. **Пер-плановый журнал через граф beads + reuse agent-packs lock (функции 5 и 6).** `steveyegge/beads` для порядка items через DAG-зависимости с gate-условиями; привязка сессия↔план — с нуля через SessionStart/SessionEnd, переиспользуя `_lib.py` из run-report; для раскатки хуков Artifex по многим проектам — не изобретать новое, оформить как `agent-pack` в существующей системе harness (идея 7 выше).[^26][^27]

## Проверка полноты (самоаудит без потерь материала)

Финальная сверка охваченных сущностей против всех трёх предыдущих стадий:

- ✅ Полная сводная таблица `docs/reference.md` (24 строки) — все перенесены в §1.1.
- ✅ Карточки-разборы `docs/reference.md` (mem0, superpowers, ECC, spec-kit, beads, planning-with-files, founder-playbook, CB Insights, context-engineering) — все упомянуты либо в §1.1, либо в исходных карточках первой итерации.
- ✅ Внутренние roadmap-документы (`plan-audit-loop.md`, `agent-command-router-hook.md`, упоминание `agent-packs-upgrade-drift.md`) — все в §1.2 и разделе нерешённых функций.
- ✅ `harness/CLAUDE.md` полный разбор структуры пакета (auto-approve, run-report, agent-router, agent-packs, safe-dirs, settings-doctor) — auto-approve и run-report разобраны детально в §2, agent-packs — в §Часть3/Функция6 и идее 7, agent-router — в §1.2.
- ✅ CREDITS.md auto-approve (3 источника: oryband, yigitkonur, froggeric) — все три разобраны в §2.1 с уточнёнными деталями стадии 2 (upstream-баги #49525/#39973).
- ✅ run-report README (_lib.py, _usage.py, ограничения) — все перенесены в §2.2.
- ✅ Ralph Wiggum (anthropics), ralph-orchestrator, ralph-claude-code — все три в §Функция1/Функция2 с уточнённым механизмом exit-detection.
- ✅ Permission-policy (defrex), auto-approve trio, claude-session-driver, generic-hooks yolo — все в §Функция3.
- ✅ MAX-плагин, claude-tg, heyagent, hanxiao, RichardAtCT, op7418, Buildr PR — все в §Функция4.
- ✅ beads, run-report, session-analyzer, claude-session-driver JSONL — все в §Функция5.
- ✅ ECC hook-профили, wshobson, agent-packs — все в §Функция6.
- ✅ Пять функций без готовых решений — сохранены и уточнены.
- ✅ Собственные новые идеи (7 пунктов) — добавлены в §Часть4, синтезированы из сопоставления находок, не дублируют ни один внешний источник впрямую.
- ✅ Новая находка стадии 3 (`obra/claude-session-driver` и смежные tmux-orchestration проекты) — интегрирована во все релевантные разделы (функции 1, 3, 5).

## Полный список источников (все три стадии, объединено)

- https://github.com/academici/swissknifeman
- https://github.com/academici/swissknifeman/blob/main/docs/reference.md
- https://github.com/academici/swissknifeman/blob/main/roadmap/plan-audit-loop.md
- https://github.com/academici/swissknifeman/blob/main/roadmap/agent-command-router-hook.md
- https://github.com/academici/swissknifeman/blob/main/packages/harness/CLAUDE.md
- https://github.com/academici/swissknifeman/blob/main/packages/harness/configs/claude-code/hooks/auto-approve/CREDITS.md
- https://github.com/academici/swissknifeman/blob/main/packages/harness/configs/claude-code/hooks/run-report/README.md
- https://github.com/github/spec-kit
- https://github.com/steveyegge/beads
- https://github.com/steveyegge/beads/blob/main/docs/DEPENDENCIES.md
- https://github.com/othmanadi/planning-with-files
- https://github.com/obra/superpowers
- https://github.com/VoltAgent/awesome-claude-code-subagents
- https://github.com/hesreallyhim/awesome-claude-code
- https://github.com/vijaythecoder/awesome-claude-agents
- https://github.com/alex-popov-tech/claude-rio
- https://github.com/itgoyo/awesome-agent-skills
- https://github.com/wshobson/agents
- https://github.com/anthropics/skills
- https://github.com/affaan-m/everything-claude-code
- https://github.com/ysyecust/everything-claude-code/blob/main/LICENSE
- https://github.com/mem0ai/mem0
- https://arxiv.org/abs/2504.19413
- https://github.com/langchain-ai/langgraph
- https://diataxis.fr/
- https://github.com/Kulaxyz/self-learning-skills
- https://github.com/Roave/BackwardCompatibilityCheck
- https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum
- https://github.com/anthropics/claude-code/blob/main/plugins/ralph-wiggum/README.md
- https://github.com/mikeyobrien/ralph-orchestrator
- https://mikeyobrien.github.io/ralph-orchestrator/
- https://github.com/frankbria/ralph-claude-code
- https://github.com/frankbria/ralph-claude-code/blob/main/ralph_loop.sh
- https://github.com/frankbria/ralph-claude-code/blob/main/IMPLEMENTATION_PLAN.md
- https://claudewave.com/en/repo/frankbria-ralph-claude-code
- https://github.com/defrex/claude-code-permission-policy
- https://github.com/MAVII-RU/max-messenger-plugin
- https://github.com/MAVII-RU/max-messenger-plugin/blob/main/server.ts
- https://pkg.go.dev/github.com/easyfold/claude-tg
- https://github.com/gergomiklos/heyagent
- https://github.com/blackwell-systems/claudewatch
- https://github.com/blackwell-systems/dotclaude
- https://github.com/lucemia/claude-session-analyzer
- https://github.com/hanxiao/claudecode-telegram
- https://github.com/RichardAtCT/claude-code-telegram
- https://github.com/op7418/Claude-to-IM-skill
- https://github.com/anthropics/skills/pull/419
- https://github.com/possibilities/claude-code-generic-hooks
- https://github.com/yigitkonur/hooks-claude-approve
- https://yigitkonur.com/auto-approve-claude-code-plan-mode
- https://github.com/oryband/claude-code-auto-approve
- https://github.com/oryband/claude-code-auto-approve/blob/master/approve-compound-bash.sh
- https://github.com/froggeric/claude-smart-approval
- https://www.reddit.com/r/ClaudeCode/comments/1sn83oh/i_made_a_claude_code_plugin_for_automatic/
- https://github.com/anthropics/claude-code/issues/49525
- https://github.com/anthropics/claude-code/issues/39973
- https://github.com/anthropics/claude-code/issues/7275
- https://github.com/obra/claude-session-driver
- https://blog.fsck.com/releases/2026/02/12/claude-session-driver/
- https://libraries.io/cargo/claude-session-driver
- https://github.com/primeline-ai/claude-tmux-orchestration
- https://gist.github.com/qrtt1/4b9061dcaee5ee81753ffafcd77bf3d8
- https://github.com/craigsc/cmux
- https://github.com/0xkaz/claunch

---

## References

1. [yigitkonur/auto-approve-claude-plan](https://github.com/yigitkonur/hooks-claude-approve) - Claude Code has a plan mode. when Claude finishes writing a plan and calls ExitPlanMode , it fires a...

2. [auto-approve Claude Code plan mode via PermissionRequest](https://yigitkonur.com/auto-approve-claude-code-plan-mode) - Claude Code's plan approval dialog can be auto-approved by hooking PermissionRequest correctly and m...

3. [Auto-approve compound Bash commands in Claude Code ...](https://github.com/oryband/claude-code-auto-approve) - Compound commands are parsed into a JSON AST by shfmt, walked by a jq filter that extracts every sub...

4. [approve-compound-bash.sh](https://github.com/oryband/claude-code-auto-approve/blob/master/approve-compound-bash.sh) - Auto-approve compound Bash commands in Claude Code — pipes, chains, subshells parsed and checked per...

5. [I made a claude code plugin for automatic approvals for all piped commands (and similar), and when unsure, use a smart process to let claude automatically decide if a command should approved or not](https://www.reddit.com/r/ClaudeCode/comments/1sn83oh/i_made_a_claude_code_plugin_for_automatic/) - I made a claude code plugin for automatic approvals for all piped commands (and similar), and when u...

6. [froggeric - Overview](https://ithub.global.ssl.fastly.net/froggeric) - Too many passions. Zero apologies. Composer for neurons and surf guitars. Fitness trainer. Coder. Ha...

7. [Ralph Wiggum 插件：让Claude Code “通宵干活” Ralph 就是一个让 ...](https://x.com/dotey/status/2007197068394164613)

8. [mikeyobrien/ralph-orchestrator: An improved ...](https://github.com/mikeyobrien/ralph-orchestrator) - An improved implementation of the Ralph Wiggum technique for autonomous AI agent orchestration. Ralp...

9. [Ralph Orchestrator - Ralph Orchestrator - mikeyobrien.github.io](https://mikeyobrien.github.io/ralph-orchestrator/) - Hat-based orchestration framework that keeps AI agents in a loop until the task is done

10. [ralph-loop · GitHub Topics](https://github.com/topics/ralph-loop?l=rust) - GitHub is where people build software. More than 150 million people use GitHub to discover, fork, an...

11. [claude-session-driver 1.0](https://blog.fsck.com/releases/2026/02/12/claude-session-driver/) - A Claude Code plugin for managing workers across projects — guest post by Claude (Opus 4.6, Claude C...

12. [claude-session-driver 0.1.0 on Cargo - Libraries.io - security ...](https://libraries.io/cargo/claude-session-driver) - Drive an interactive Claude REPL over tmux on the subscription seat, with JSON state detection. Inst...

13. [Claude Code tmux orchestration — spawn full AI sessions ... - GitHub](https://github.com/primeline-ai/claude-tmux-orchestration) - Claude Code tmux orchestration — spawn full AI sessions as parallel workers with heartbeat monitorin...

14. [tmux-based multi-agent orchestration for Claude Code (PO proxy ...](https://gist.github.com/qrtt1/4b9061dcaee5ee81753ffafcd77bf3d8) - human-being skill — tmux-based multi-agent orchestration for Claude Code (PO proxy → Navigator ←→ Dr...

15. [craigsc/cmux - tmux for Claude Code - GitHub](https://github.com/craigsc/cmux) - cmux: tmux for Claude Code. Contribute to craigsc/cmux development by creating an account on GitHub.

16. [GitHub - 0xkaz/claunch: Project-based Claude CLI session manager with automatic tmux setup and persistence](https://github.com/0xkaz/claunch) - Project-based Claude CLI session manager with automatic tmux setup and persistence - 0xkaz/claunch

17. [frankbria/ralph-claude-code · Awesome Lists for Claude AI · Trust ...](https://claudewave.com/en/repo/frankbria-ralph-claude-code) - Ralph for Claude Code is a Shell-based automation layer that wraps the Claude Code CLI in a self-sus...

18. [frankbria/ralph-claude-code - Gource visualisation](https://www.youtube.com/watch?v=oY2UsO9FATc) - 🚀 Watch the development journey of ralph-claude-code by frankbria!

📝 Autonomous AI development loop...

19. [ralph-claude-code - AI Agents on GitHub (1.2k  ) | SkillsLLM](https://skillsllm.com/skill/ralph-claude-code)

20. [GitHub - frankbria/ralph-claude-code: Autonomous AI development loop for Claude Code with intelli...](https://www.youtube.com/watch?v=4MChV0m67VQ) - https://github.com/frankbria/ralph-claude-code

 Autonomous AI development loop for Claude Code with...

21. [blackwell-systems/dotclaude](https://github.com/blackwell-systems/dotclaude) - License: Apache 2.0 Sponsor. The definitive profile management system for Claude Code. Manage your C...

22. [defrex/claude-code-permission-policy: Live Less ...](https://github.com/defrex/claude-code-permission-policy) - Live Less Dangerously. Contribute to defrex/claude-code-permission-policy development by creating an...

23. [MAX Messenger Plugin for Claude Code](https://github.com/MAVII-RU/max-messenger-plugin) - MAX Messenger channel plugin for Claude Code — connect Claude AI agents to VK/MAX messenger - MAVII-...

24. [claude-tg command - github.com/easyfold ... - Go Packages](https://pkg.go.dev/github.com/easyfold/claude-tg)

25. [GitHub - gergomiklos/heyagent: Telegram bridge for Claude Code ...](https://github.com/gergomiklos/heyagent) - Telegram bridge for Claude Code and Codex CLI. Contribute to gergomiklos/heyagent development by cre...

26. [beads/docs/DEPENDENCIES.md at main](https://github.com/steveyegge/beads/blob/main/docs/DEPENDENCIES.md) - Beads includes a full dependency system for ordering work and a gate system for bridging external co...

27. [steveyegge/beads - A memory upgrade for your coding agent - GitHub](https://github.com/steveyegge/beads) - Beads - A memory upgrade for your coding agent. Contribute to steveyegge/beads development by creati...

28. [everything-claude-code/LICENSE at main - GitHub](https://github.com/ysyecust/everything-claude-code/blob/main/LICENSE) - Complete collection of Claude Code configs for C++20 HPC development - agents, skills, hooks, comman...

