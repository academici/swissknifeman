# 2026.07.15-TELEMETRY-OPT — Оптимизация токен-расхода и надёжности workflow (по кросс-проектной телеметрии)

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.15-TELEMETRY-OPT |
| Title | Оптимизация токен-расхода и надёжности workflow экосистемы |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-07-15 |
| Repository | swissknifeman |
| Related Packages | harness (run-report hook, permissions), analyst (token_report, digest), task (workflow-craft/routing-команды), skiller (workflow-craft/plan-protocol скиллы) |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) · fable (research/mechanical) |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| Paused By | — |

## 1. Context

За 4 дня (2026-07-11…07-15) кросс-проектная телеметрия (114 run-reports schema v2, 8 проектов,
`findings/telemetry-baseline.md`) вскрыла 4 кластера неэффективности. **Промах-кэша НЕТ**
(cache_hit ≈ 100%, low-cache 0/114) — «перерасход» не в промахах, а в: (1) **релончах
workflow** — сессия dterema звала один named-workflow `dterema-site-p3-api` 15× подряд, все
`async_launched`, завершение не записано (детектор `error_loops` их не видит — это не ошибки);
(2) **churn на файл-операциях** — 46 «not-read-first» + 16 edit-fail + reread(extra) 392;
(3) **доминировании Opus** — 8.1M out против Sonnet 5.4M (task:design/review/audit пинят
Opus/xhigh намеренно, но это самый дорогой рычаг, а `--by phase` в analyst не реализован —
токены на уровне workflow не видны); (4) **permission-friction** — 118 DENY(policy), агенты
повторно долбятся в защищённые операции. План бьёт по всем четырём фазами P1–P4, начиная с
самой жгущей токены (workflow-релончи).

## 2. Execution Rules

- Один item за раз; статус обновляется В ПЛАНЕ до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (plan-protocol §5).
- **stdlib-only** во всех python-правках (harness/analyst/task) — жёстко, без pip.
- Правки run-report hook — в SOURCE `packages/harness/configs/claude-code/hooks/run-report/`,
  НЕ в деплой-копии `~/.claude/hooks/` (её раскатывает harness).
- Скиллы: правишь `SKILL.ru.md` → регенеришь `SKILL.md` → `check-translations.sh --stamp`.
- План разошёлся с кодом → не импровизировать, эскалировать (plan-protocol §10).
- После закрытия item/фазы — перезаписать `handoff.md`; после правок скиллов — `skiller registry`.

## 3. Routing

<Отклонения от SSOT-матрицы §9 + явное покрытие детализированной фазы P1.>

| Items | Model/effort | Exec | Почему |
|:--|:--|:--|:--|
| P1.1–P1.3 | sonnet/medium | plan-exec | repo-grounded recon + правки hook/скилла — дефолты §9, детерминированная Validation |
| P2.1 | sonnet/medium | plan-exec | repo-grounded пере-агрегация run-reports + findings — дефолты §9, воспроизводимая Validation |
| P2.2 | sonnet/medium | plan-exec | правка CORE-скилла anti-drift (RU→EN регенерация) — детерминированные гейты (check-translations/registry/validate) |
| P3.x (routing-policy design) | opus/high | manual | выработка политики модель-роутинга = архитектурное решение, effort high+ MANDATORY (при детализации P3) |
| P5.1 | sonnet/medium | plan-exec | внутренний аудит инструментом `skiller budget` — детерминированный, дефолты §9 |
| P5.2 | fable/medium | manual | внешний RAG-развед — токен-дёшево (D1), fable вне пина plan-exec |
| P5.3 | opus/high | manual | синтез ROI + рекомендация приоритизации = архитектурное решение |

<P4 — скелет; routing проставится при детализации фазы (`/task:plan-design <ID> Pn`).>
<P5.1 ∥ P5.2 независимы → орк-кандидат: parallel(P5.1, P5.2) → P5.3 (при исполнении фазы).>

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Workflow completion-signal (анти-релонч) | 1/3 | 🟡 In progress |
| P2 | Churn-гейт файл-операций | 0/2 | ⬜ Not started |
| P3 | Model-routing аудит | 0/2 | ⬜ Not started |
| P4 | Permission-friction | 0/2 | ⬜ Not started |
| P5 | Discovery: дальнейшие рычаги токен-экономии (RAG) | 0/3 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-15 | Дом плана — репо swissknifeman (`plans/`); дизайн под Opus/high, research/exec — Fable/Sonnet | Проблемы в тулинге экосистемы (harness/analyst/task); синтез требует кросс-источникового reasoning, механика — дёшево. Подтверждено с Owner. RAG:— (repo-grounded: решение владельца + CLAUDE.md model-routing) |
| D2 | 2026-07-15 | Порядок фаз: P1 (workflow) → P2 (churn) → P3 (routing) → P4 (perms) | P1 — самый жгущий токены кластер (повторный fan-out); P3 частично упирается в telemetry-gap, закрываемый в P1. RAG:— (repo-grounded: `findings/telemetry-baseline.md`) |
| D3 | 2026-07-15 | Профилактика релончей — через ДЕТЕКЦИЮ (run-report/analyst) + ДИСЦИПЛИНУ (скилл workflow-craft), НЕ через патч ядра Workflow-тула | Ядро Workflow-тула Claude Code предположительно вне нашего контроля; в нашей власти — сигнал + guidance. `[UNVERIFIED]` — верифицируется в P1.1 (OQ-2) |
| D4 | 2026-07-15 | Порог сигнала `workflow_relaunch`: ≥2 записи одного `workflowName` со `status=async_launched` в одной сессии = suspicious, ≥3 = flag (дефолт, уточняем данными в P1.2) | 15× в dterema — явная аномалия; консервативный ≥3 избегает ложных на легитимном fan-out. RAG:— (repo-grounded: `findings/telemetry-baseline.md` + `_lib.py:476-491`) |
| D5 | 2026-07-15 | Добавлена discovery-фаза P5 (RAG-развед «на чём ещё сэкономить») поверх known-кластеров; её backlog может переупорядочить P2–P4 по ROI / породить P6+ | P1–P4 закрывают измеренные проблемы, но не исчерпывают рычаги; discovery ищет ЕЩЁ (always-on бюджет, MCP-поверхность, best-practices) до фиксации приоритетов. RAG:— (repo-grounded: запрос Owner + рамки CLAUDE.md «фичу — по факту измеренной проблемы») |
| D6 | 2026-07-15 | Форма вмешательства P2 (churn) = **дисциплина-first** (CORE-скилл anti-drift), НЕ новый блокирующий хук-гейт; хук-сигнал категоризации отложен до вердикта P2.1 | Edit/Write Claude Code уже нативно гейтят read-before-edit — 46 «not-read-first» это СРАБАТЫВАНИЯ гейта (фейлы в `tool_failures`), а не тихие перезаписи → второй гейт избыточен; churn «100% устраним дисциплиной» (baseline). Alternatives: (A) блокирующий хук-гейт — отклонён (редундантен, добавляет friction на Write); (B) хук-сигнал категоризации в analyst — отложен (churn уже видим в `tool_failures`, analyst его не читает — ценность недоказана, решает P2.1). RAG:— (repo-grounded: контракт тула Edit/Write + `findings/telemetry-baseline.md` 46 not-read-first в tool_failures + `_lib.py:445-447`) |
| D7 | 2026-07-15 | OQ-2 разрешён: `async_launched` + отдельный `<task-notification>` на завершение, и `resumeFromRunId` (resume после правки скрипта с кэшем нетронутого префикса) — ДОКУМЕНТИРОВАННЫЙ, санкционированный контракт тула `Workflow`, не баг ядра. Реальный драйвер 15× в dterema (657a7deb) — 11 из 15 вызовов были `resume` ПОСЛЕ правки скрипта воркфлоу (co-разработка воркфлоу внутри основной сессии: relative-path баг, top-level `return`, gate-промпт без scope, docblock/pint-форматирование, дважды правился review-промпт) — токен-жор от нестабильности только что написанного скрипта + отладки в основной сессии, не от «недоставленного» completion-сигнала (сигнал дошёл — session дождалась `<task-notification>` и корректно среагировала TaskStop'ом). D3 сужен: профилактика остаётся детекция+guidance (ядро не патчим), но детектор P1.2 обязан различать «resume-цикл отладки» (штатно) от «висящего async без notification к концу сессии» (реальная аномалия) | RAG:✅ (первичный источник — JSONSchema-описание тула `Workflow` в системном промпте, дословные цитаты; вторичная сверка `claude-code-guide` по публичным докам — COULD NOT VERIFY на этом уровне детализации, не противоречит) + repo-grounded (транскрипт `657a7deb-0784-4368-8f18-b49db286f595.jsonl` построчно, см. `findings/P1-workflow-rootcause.md`) |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-15 | plan-design/opus | План создан из телеметрии (findings/telemetry-baseline.md); P1 детализирован, P2–P4 скелеты. ACTIVE → 2026.07.15-TELEMETRY-OPT |
| 2026-07-15 | plan-design/opus | Добавлена discovery-фаза P5 (RAG-развед рычагов токен-экономии, скелет); D5 |
| 2026-07-15 | plan-design/opus | P5 детализирован (3 items: внутр. аудит ∥ внешний RAG → синтез ROI-backlog), DoR пройден; Routing §3 покрывает P5. P2–P4 намеренно скелеты до discovery |
| 2026-07-15 | plan-design/opus | P2 детализирован (2 items: инвентаризация churn → file-op-гигиена в anti-drift), DoR пройден; D6 (дисциплина-first, гейт отклонён); Routing §3 покрывает P2.1–P2.2; OQ-3 → P2.1. Детализирован ранее общей дизайн-паузы — churn-кластер самодостаточен по baseline, не зависит от P1.1/P5 discovery |
| 2026-07-15 | plan-exec/sonnet | P1.1 закрыт: корневая причина 15× dterema-релонча — 11/15 вызовов `resumeFromRunId` ПОСЛЕ правки скрипта (co-разработка воркфлоу в основной сессии), не отсутствие completion-сигнала; OQ-2 → D7 (Resolved) — детали см. phases/P1.md P1.1 Completion Notes |

## Обсуждение

### 1 — Гранулярность model-routing аудита (P3): по task-командам vs по phase-токенам

- **(рекоменд.) Вариант A — по task-командам.** Аудитить пины `commands/*.md` (кто пинит Opus/xhigh
  и оправдан ли). Плюсы: данные есть сразу (frontmatter), не блокируется telemetry-gap. Минусы:
  не видит реальную токен-цену конкретной фазы.
- **Вариант B — по phase-токенам.** Требует `--by phase` в analyst (workflows[] без токенов —
  ESCALATION-REQUIRED, `token_report.py:38`). Плюсы: точная атрибуция. Минусы: блокируется
  telemetry-gap, дороже.

**Статус:** Exploration (решится при детализации P3; трекинг — `open-questions.md`)

### 2 — Порог `workflow_relaunch` (D4): фиксированный vs адаптивный

- **(рекоменд.) Вариант A — фиксированный порог ≥3.** Простота, детерминизм. Уточняется данными в P1.2.
- **Вариант B — адаптивный** (доля async без парного завершения). Точнее, но сложнее и хрупче на малых N.

**Статус:** Resolved → D4 (фиксированный, refinable)
