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
| Last Updated | 2026-07-15 (P4.2 закрыт — фаза P4 терминальна) |
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
| P3.1–P3.2 | opus/high + perplexity-web/context7 | manual | routing-policy аудит = архитектурное решение; effort high+ MANDATORY; RAG на model-capabilities в основной сессии |
| P5.1 | sonnet/medium | plan-exec | внутренний аудит инструментом `skiller budget` — детерминированный, дефолты §9 |
| P5.2 | fable/medium | manual | внешний RAG-развед — токен-дёшево (D1), fable вне пина plan-exec |
| P4.1–P4.2 | sonnet/medium | plan-exec | repo-grounded пере-агрегация DENY + дисциплина-правка скилла (зеркало P2); детерминированная Validation; внешнего RAG нет. Protection-surface (permissions/auto-approve/safe-dirs) — Owner-gated, вынесено в OQ-5, командой НЕ применяется |
| P5.3 | opus/high | manual | синтез ROI + рекомендация приоритизации = архитектурное решение |
<P5.1 ∥ P5.2 независимы → орк-кандидат: parallel(P5.1, P5.2) → P5.3 (при исполнении фазы).>

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Workflow completion-signal (анти-релонч) | 2/3 | 🟠 Done with deviations |
| P2 | Churn-гейт файл-операций | 2/2 | 🟢 Done |
| P3 | Model-routing аудит | 2/2 | 🟢 Done |
| P4 | Permission-friction | 2/2 | 🟢 Done |
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
| D8 | 2026-07-15 | OQ-1 разрешён → **Вариант A** (аудит по task-командам, не по phase-токенам). Гранулярность P3 = пины `commands/*.md` + телеметрия `analyst token-report --by model` (реализован); Вариант B (phase-токены) отклонён — `--by phase` не реализован (`token_report.py:38-41`, ESCALATION-REQUIRED), схема run-report не несёт токены на workflow-уровне, доработка формата хука вне скоупа. Downgrade correctness-critical пинов — ТОЛЬКО с Owner-одобрением (P3.2), не blanket по цене. **Pre-mortem:** тихий downgrade design/plan-audit/review → деградация качества планов/ревью во ВСЕХ проектах, никем не замечаемая без quality-телеметрии → mitigation: не трогать correctness-critical без Owner + аудит-док как провенанс | Вариант A не блокируется telemetry-gap (данные сразу); точная phase-атрибуция (B) требует доработки run-report вне плана. RAG:— (repo-grounded: `token_report.py:30-41` + `docs/routing.md` + `findings/telemetry-baseline.md`) |
| D9 | 2026-07-15 | P3.2: вердикт P3.1 применён. **Downgrade применён (Owner-делегировано):** `dev` opus/high→**sonnet/high**, `make-workflow` opus/high→**sonnet/high** (frontmatter+description+body+`skiller registry`+`validate.sh` зелёный). **Keep-Opus подтверждены:** design/plan-design (opus/high), plan-audit/review (opus/xhigh) — правок пинов нет. **research** (needs-Owner) → OQ-4 «Decision pending». Политик-док — секция «Model-routing пинов task-команд» в `docs/routing.md`. Owner-гейт: `AskUserQuestion` по 2 кандидатам → владелец делегировал выбор исполнителю → оба применены по вердикту P3.1 (downgrade-candidate, safety-nets review-gate/статич.ревьюер, Sonnet 5 par/выше на coding-agentic). Fable не рассматривался (дороже Opus). Ось токен-экономии P3 (Opus 8.1M vs Sonnet 5.4M out) | Аудит без применения — потраченная фаза; downgrade correctness-critical = ставка на качество → только Owner-гейт (D8 pre-mortem). RAG:— (repo-grounded: `findings/P3-routing-audit.md` вердикты + Owner-делегирование в сессии P3.2) |
| D10 | 2026-07-15 | **P4 probe-реframe.** Baseline-гипотеза кластера 4 («118 DENY(policy) = rm в защищённых → рычаг `harness safe-dirs`») **частична**: design-time probe над `*/.claude/runs/*.json` (166 run-reports, паттерн `Permission to use * has been denied` в `tool_failures`) → 124 денаев, **Bash 96** — подавляюще **компаунд/пайп read-only цепочки** (`cd;ls;grep;cat`), денайнутые atomic allow-matcher'ом; деструктивный `rm` — меньшинство; Read-«денаи» probe'ом как policy НЕ подтверждены. Рычаг смещается с safe-dirs(rm) на allow-matchability read-only Bash. **Форма ремедиации = дисциплина-first (зеркало D6), защиту НЕ ослабляем:** дисциплина-правило «DENY терминален для формы — не retry verbatim, адаптировать/штатный тул» (устраняет ПОВТОРНЫЕ тычки — цель кластера); protection-surface (permissions/auto-approve компаунд-парсинг/safe-dirs) — только Owner-gated (OQ-5), plan-exec не применяет. P4.1 пере-деривит точные цифры на полном окне и классифицирует бакеты (a компаунд-фрикция / b корректный-deny-агент-ошибка / c легит-блок-Owner). Pre-mortem: слепое ослабление allow-правил ради числа 118 → дыра в защите → mitigation: бакет-(c) не применять без Owner, классификация по РЕАЛЬНЫМ allow/deny-правилам, не «на глаз» | Планировать на falsified-гипотезе нельзя (CLAUDE.md методология: до-проверять аудит на свежих данных); зеркалит D6 (native-гейт корректен, чинит дисциплина, не второй гейт — здесь гейт напротив слишком строг для read-only, но ослабление = protection-surface → Owner). RAG:— (repo-grounded: probe над run-reports + `_lib.py:450-452` tool_failures shape + `settings.base.json` allow/deny + `auto-approve/` deny-порядок) |
| D11 | 2026-07-15 | P4.2: вердикт P4.1 применён. Дисциплина-правило «DENY(policy) терминален для точной формы команды в сессии — не retry verbatim» добавлено в CORE-скилл `anti-drift` (секция «DENY circuit-breaker», v0.3.0→0.4.0, RU→EN регенерация). Protection-surface (auto-approve компаунд-парсинг ось B, dedicated-сигнал ось C, бакет-(c) needs-Owner формы) — НЕ применяется, вынесено/уточнено в OQ-5 (Decision pending) | Ослабление allow-правил = ставка на защиту → только Owner; дисциплина бьёт в цель кластера (повторные тычки) без protection-surface риска (зеркало D6). RAG:— (repo-grounded: `findings/P4-deny-inventory.md` рекомендация + D6/D10) |
| D7 | 2026-07-15 | OQ-2 разрешён: `async_launched` + отдельный `<task-notification>` на завершение, и `resumeFromRunId` (resume после правки скрипта с кэшем нетронутого префикса) — ДОКУМЕНТИРОВАННЫЙ, санкционированный контракт тула `Workflow`, не баг ядра. Реальный драйвер 15× в dterema (657a7deb) — 11 из 15 вызовов были `resume` ПОСЛЕ правки скрипта воркфлоу (co-разработка воркфлоу внутри основной сессии: relative-path баг, top-level `return`, gate-промпт без scope, docblock/pint-форматирование, дважды правился review-промпт) — токен-жор от нестабильности только что написанного скрипта + отладки в основной сессии, не от «недоставленного» completion-сигнала (сигнал дошёл — session дождалась `<task-notification>` и корректно среагировала TaskStop'ом). D3 сужен: профилактика остаётся детекция+guidance (ядро не патчим), но детектор P1.2 обязан различать «resume-цикл отладки» (штатно) от «висящего async без notification к концу сессии» (реальная аномалия) | RAG:✅ (первичный источник — JSONSchema-описание тула `Workflow` в системном промпте, дословные цитаты; вторичная сверка `claude-code-guide` по публичным докам — COULD NOT VERIFY на этом уровне детализации, не противоречит) + repo-grounded (транскрипт `657a7deb-0784-4368-8f18-b49db286f595.jsonl` построчно, см. `findings/P1-workflow-rootcause.md`) |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-15 | plan-design/opus | План создан из телеметрии (findings/telemetry-baseline.md); P1 детализирован, P2–P4 скелеты. ACTIVE → 2026.07.15-TELEMETRY-OPT |
| 2026-07-15 | plan-design/opus | Добавлена discovery-фаза P5 (RAG-развед рычагов токен-экономии, скелет); D5 |
| 2026-07-15 | plan-design/opus | P5 детализирован (3 items: внутр. аудит ∥ внешний RAG → синтез ROI-backlog), DoR пройден; Routing §3 покрывает P5. P2–P4 намеренно скелеты до discovery |
| 2026-07-15 | plan-design/opus | P2 детализирован (2 items: инвентаризация churn → file-op-гигиена в anti-drift), DoR пройден; D6 (дисциплина-first, гейт отклонён); Routing §3 покрывает P2.1–P2.2; OQ-3 → P2.1. Детализирован ранее общей дизайн-паузы — churn-кластер самодостаточен по baseline, не зависит от P1.1/P5 discovery |
| 2026-07-15 | plan-design/opus | P3 детализирован (2 items: аудит 7 Opus-пинов task-команд → применение вердикта + политик-док), DoR пройден; D8 (OQ-1 → Вариант A, phase-токены отклонены); Routing §3 покрывает P3.1–P3.2 (opus/high manual). Оба item'а manual — архитектурное решение + RAG на model-capabilities |
| 2026-07-15 | plan-exec/sonnet | P1.1 закрыт: корневая причина 15× dterema-релонча — 11/15 вызовов `resumeFromRunId` ПОСЛЕ правки скрипта (co-разработка воркфлоу в основной сессии), не отсутствие completion-сигнала; OQ-2 → D7 (Resolved) — детали см. phases/P1.md P1.1 Completion Notes |
| 2026-07-15 | plan-exec/sonnet | P1.2 закрыт: срез `workflow_relaunch` добавлен в run-report hook, группировка по `runId` (fallback `workflowName`) — детали см. phases/P1.md P1.2 Completion Notes |
| 2026-07-15 | plan-exec/sonnet | P1.3 закрыт (🟠, tests вне буквального Files): сигнал `workflow_relaunch` поднят в analyst digest (сигнал D) + анти-релонч-дисциплина в скилле workflow-craft (§4.1, RU+EN) — фаза P1 терминальна (🟠) — детали см. phases/P1.md P1.3 Completion Notes |
| 2026-07-15 | plan-exec/sonnet | P2.1 закрыт: пере-агрегация 114 run-reports — reread(342) доминирует над Edit/Write edit-fail(55); нативный read-гейт подтверждён по факту; вердикт «дисциплина, не хук-сигнал» (OQ-3 → Resolved, совпал с D6) — детали см. phases/P2.md P2.1 Completion Notes |
| 2026-07-15 | plan-exec/sonnet | P2.2 закрыт, фаза P2 терминальна: file-op-гигиена (read-before-edit/якорь/анти-reread) в CORE-скилле `anti-drift` (RU→EN, version 0.3.0) — детали см. phases/P2.md P2.2 Completion Notes |
| 2026-07-15 | manual/opus/high | P3.1 закрыт: аудит 7 Opus-пинов (keep×4 correctness-critical / downgrade-cand×2 dev·make-workflow / needs-Owner×1 research); Fable исключён (дороже Opus); RAG:✅ 2026-07 — детали см. phases/P3.md P3.1 Completion Notes |
| 2026-07-15 | manual/opus/high | P3.2 закрыт, фаза P3 терминальна: вердикт применён — dev/make-workflow → sonnet/high (Owner-делегировано), keep-Opus×4 подтверждены, research → OQ-4; политик-док «Model-routing пинов task-команд» в docs/routing.md; D9 — детали см. phases/P3.md P3.2 Completion Notes |
| 2026-07-15 | plan-design/opus | P4 детализирован (2 items), DoR пройден; D10 (probe-реframe: доминанта — компаунд read-only Bash, не rm; дисциплина-first, protection-surface Owner-gated); Routing §3 (P4.1–P4.2 sonnet/medium plan-exec); OQ-5 + Discussion №3 — детали см. phases/P4.md |
| 2026-07-15 | plan-exec/sonnet | P4.1 закрыт: полное окно 169 run-reports, 98 policy-shaped DENY (Bash 75/Read 23), бакеты a=16(16%)/b=46(47%)/c=36(37%) — на полном окне (a) компаунд-Bash МЕНЬШИНСТВО (уточнение к D10), rm-гипотеза не подтвердилась (D10 if-then не сработал) — детали см. phases/P4.md P4.1 Completion Notes |
| 2026-07-15 | plan-exec/sonnet | P4.2 закрыт, фаза P4 терминальна: дисциплина-правило «DENY терминален для формы» в CORE-скилле `anti-drift` (v0.4.0, RU→EN); protection-surface (ось B/C, бакет-c) уточнён и остаётся в OQ-5 (Decision pending); D11 — детали см. phases/P4.md P4.2 Completion Notes |

## Обсуждение

### 1 — Гранулярность model-routing аудита (P3): по task-командам vs по phase-токенам

- **(рекоменд.) Вариант A — по task-командам.** Аудитить пины `commands/*.md` (кто пинит Opus/xhigh
  и оправдан ли). Плюсы: данные есть сразу (frontmatter), не блокируется telemetry-gap. Минусы:
  не видит реальную токен-цену конкретной фазы.
- **Вариант B — по phase-токенам.** Требует `--by phase` в analyst (workflows[] без токенов —
  ESCALATION-REQUIRED, `token_report.py:38`). Плюсы: точная атрибуция. Минусы: блокируется
  telemetry-gap, дороже.

**Статус:** Resolved → D8 (Вариант A — по task-командам; Вариант B отклонён, `--by phase` не реализован)

### 2 — Порог `workflow_relaunch` (D4): фиксированный vs адаптивный

- **(рекоменд.) Вариант A — фиксированный порог ≥3.** Простота, детерминизм. Уточняется данными в P1.2.
- **Вариант B — адаптивный** (доля async без парного завершения). Точнее, но сложнее и хрупче на малых N.

**Статус:** Resolved → D4 (фиксированный, refinable)

### 3 — Форма ремедиации permission-friction (P4): дисциплина vs preset-tuning vs dedicated-сигнал

- **(рекоменд.) Ось A — дисциплина.** Правило «DENY терминален для формы — не retry verbatim,
  адаптировать/штатный тул» в CORE-скилле (зеркало P2.2). Плюсы: бьёт прямо в цель («убрать
  ПОВТОРНЫЕ тычки»), защиту не трогает, plan-exec-able. Минусы: не расширяет auto-approve —
  легитимный компаунд read-only всё равно требует адаптации агентом.
- **Ось B — тюнинг permissions/auto-approve.** Научить auto-approve пропускать компаунд READ-ONLY
  (сплит по `;`/`&&`/`|`, все под-команды в allow-set → approve). Плюсы: выше рычаг, снимает
  фрикцию у источника. Минусы: **protection-surface** (баг парсинга = пропуск скрытой деструктивной
  под-команды), нетривиальный код → Owner + возможный ре-дизайн, не plan-exec.
- **Ось C — dedicated `permission_friction`-сигнал в run-report.** Плюсы: явная телеметрия.
  Минусы: DENY уже видим в `tool_failures` (зеркало OQ-3 — сигнал невостребован), ценность недоказана.

**Статус:** Decision pending (нужен владелец) → OQ-5. Ось A применяется в P4.2 (дефолт D10);
оси B/C — под Owner (protection-surface / недоказанная ценность), конкретные кандидаты из данных P4.1.
