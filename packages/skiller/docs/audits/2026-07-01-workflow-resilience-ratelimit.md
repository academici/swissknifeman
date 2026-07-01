# Инцидент + рекомендации: устойчивость agent-workflow к rate-limit (2026-07-01)

- **Тип:** операционный пост-мортем (не Perplexity framework-audit — нет `.raw.md`).
- **Где:** проект `chatom`, сборка форум-пакета через `chatom-dev-loop` (Workflow-оркестрация: per-slice `impl → tests-to-green → review-gate`), ночной автономный прогон.
- **Симптом (репортил владелец):** «10 часов выполняется, это не нормально».

## Что случилось

Три прогона Workflow-оркестрации дали **три разных режима отказа** — все медленные и молчаливые:

1. **Perplexity single-browser коллизия** (research fan-out). 13 параллельных агентов подрались за ЕДИНСТВЕННЫЙ Chromium-профиль `perplexity-web` (`SingletonLock: File exists`) → один завис на `about:blank`, остальные падали. Урок: **single-instance MCP-инструмент нельзя параллелить**.
2. **StructuredOutput retry-cap** (batch 2). Строгая JSON-схема на ВОЗВРАТЕ `test`-агента не прошла валидацию 5× → `agent({schema})` бросил `StructuredOutput retry cap (5) exceeded` → весь workflow оборвался на 3-м срезе (хотя impl+tests 1-2 уже закоммичены). Урок: **строгая схема на длинном/сложном возврате агента хрупкая**.
3. **API server-side rate-limit** (ГЛАВНЫЙ). `API Error: Server is temporarily limiting requests (not your usage limit) · Rate limited` — инфраструктурный throttling Anthropic (НЕ квота пользователя). Один `test`-агент шёл ~6 ч; batch-3 шёл ~10 ч и закоммитил **НОЛЬ**. Все срезы вернулись `deferred`, но по факту impl-агент был **rate-limited** и кода не создал.

## Корневая причина (кейс 3)

- Runtime **ретраит `agent()`-вызовы на транзиентных API-ошибках** (вкл. rate-limit) с бэкоффом до высокого капа. При УСТОЙЧИВОМ server-side throttling это превращается в **часы wall-clock с нулём durable-прогресса**.
- **Нет wall-clock-дедлайна**, **нет no-progress watchdog**, **нет проактивной проверки живости** оркестратором. Отказ медленный и невидимый — владельцу пришлось заметить «10 часов» вручную.
- **Усугубление:** батч = **9+ агентов** (3 среза × impl/test/review) → умножает retry-поверхность под throttling. Плюс отчёт пометил срезы `deferred` (=реальный дефект), хотя причина — инфра-отказ → **вводящая в заблуждение телеметрия**.

## Рекомендации (absorb в swissknifeman)

### P0 — Ограничивать WALL-CLOCK, а не только число ретраев
- **Per-workflow дедлайн + no-progress watchdog:** абортить прогон, если (а) нет нового коммита/durable-чекпоинта за `N` мин, или (б) суммарный runtime > `Y` мин. dev-loop уже circuit-breaks на 2 подряд не-green — добавить временны́е инварианты.
- **Кап на СУММАРНОЕ время ретраев на agent** (≤3 попытки, ≤~2 мин бэкоффа), **fail-fast на rate-limit** вместо многочасового грайндинга. Различать transient (rate-limit/5xx) vs terminal; на повторный rate-limit — статус «API throttled → пауза» и **стоп всего прогона**, не следующий агент.

### P1 — Живость оркестратора (не fire-and-forget)
- После запуска фонового workflow оркестратор **планирует проверку живости** (`ScheduleWakeup`/`Monitor` на `git log`): нет нового коммита за `N` мин → вмешаться/остановить. **Никогда не ждать completion-нотификацию вслепую часами.**
- Workflow эмитит **heartbeat/progress** (коммиты; срез X из Y), чтобы живость была видна человеку.

### P2 — Адаптивный режим под нагрузкой / мелкие юниты
- **Малые батчи (1–2 среза)**, не 3+ — меньше агентов = меньше retry-поверхность.
- **Solo-fallback:** при обнаружении throttling оркестратор делает работу САМ в main-loop (в разы меньше API-вызовов, чем 9-агентный батч) либо запускает агентов **по одному** с немедленным контролем.
- **Коммит РАНО/ЧАСТО** (impl-коммит до тестов) — mid-run отказ не теряет часы.

### P3 — Хрупкость инструментов (задокументировать явно)
- **Реестр single-instance MCP-инструментов** (`perplexity-web` = один Chromium/профиль) → ТОЛЬКО последовательно, НИКОГДА параллельный fan-out. При зависании: `pkill -f "perplexity-web-mcp/.playwright/profile"`.
- **Не строгая StructuredOutput-схема** на длинных/сложных возвратах — **текст-маркер** (`===SLICE-RESULT=== status=green`) или мягкая схема (минимум required-полей).

### P4 — Честная телеметрия отказов
- Различать `deferred` (реальный дефект, тест честно не зелёный) vs `failed:infra` (rate-limit/timeout/оборвался). **НЕ** маскировать инфра-отказ под дефер-срез. Выводить блок `<failures>` заметно в итог.

## Куда absorb (адресно)
- `docs/skiller/workflows/background-agents.md` — раздел **«Устойчивость»**: wall-clock-дедлайн, no-progress watchdog, fail-fast на rate-limit, реестр single-instance инструментов, liveness-проверка оркестратором.
- **agent-packs** (шаблоны dev-loop / review-gate, `packages/harness/configs/claude-code/agent-packs/*`): встроить wall-clock-cap + no-progress circuit-breaker + solo-fallback + честные статусы (`green`/`deferred`/`infra-failed`) + heartbeat.
- `decisions-ledger` — строка (accept P0/P1/P3/P4; P2 — дисциплина оркестратора).
- Связь: `chatom/planning/build-retrospective.md` §4 (оркестрация) / §6 (идеальная система) — это **resilience-измерение** того же аудита; свести вместе.

## Немедленно применено в текущем прогоне (chatom)
- Большие авто-ретраящиеся батчи заменены на **запуск агентов по одному** с немедленным контролем rate-limit (видим throttle сразу, не грайндим 10 ч).
- Батч-скоуп ужат; для схем-возвратов уже перешли на текст-маркер (кейс 2).

## Обновление: что реально absorb-нуто в swissknifeman (2026-07-01)

Верифицировано RAG (`perplexity-web`, 6 запросов: rate-limit/liveness/batching/
single-profile-Chromium/schema-retry/telemetry) + независимый разбор
`research/Надёжное управление агент-воркфлоу…md` (ограничения V8-sandbox подтверждены
source'ами: нет `AbortController`, `setTimeout` ненадёжен, `agent()` ретраит «сиротой»).

**Скорректировано против исходной рекомендации:** P0-«wall-clock-дедлайн / agent-timeout»
в самом скрипте **НЕ реализуем** — песочница Workflow не даёт `Date.now()`/надёжного
`setTimeout`, а `agent()` не отменяем → любой `withDeadline` был бы костылём без гарантии.
Вместо этого:
- **В скрипте (надёжно):** статус `infra-failed` (не маскировать под `deferred`),
  fail-fast на терминальный `agent()===null`, батч-дефолт 2, heartbeat `log()`,
  текст-маркер возврата. Затронуты `dev-loop.js` ×4 пака.
- **Вне скрипта (главный слой P1):** внешний supervisor — оркестратор докладывает
  статус каждые ~30 мин (`Monitor`/`ScheduleWakeup` на `git log`) и шлёт
  `PushNotification` на застой/`<failures>`; опц. автономный GHA cron-watchdog.
  Затронуты `_common/orchestrator.md` + `background-agents.md` → «Устойчивость».
- **P3 уточнён:** `perplexity-web` — не «sequential only», а **bounded concurrency**
  (pools/`maxConcurrency`, daemon v1.3.0); 13-way fan-out просто превысил лимит.
