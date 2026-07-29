---
type: finding
plan: 2026.07.18-FOREMAN
item: P0.4
source: claude-code-guide agent (first-party docs code.claude.com) + локальный `claude` 2.1.214 exec + GitHub API (repos/issues) + Perplexity (MAX API, сверен с first-party dev.max.ru)
date: 2026-07-18
verdict: 9/9 пунктов сняты (7 RAG:✅ verified, 2 [UNVERIFIED]-как-механика → зависимые фазы строятся БЕЗ них)
supersedes: §Неопределённости факт-листа (headless-claude-code-factsheet); финализирует D7
---

# P0.4 — Снятие неопределённостей headless (9 пунктов)

RAG-лестница (D19): first-party дока / claude-code-guide → GitHub API (репы/issue —
только API) → Perplexity (последним, не финален). Каждый пункт: вердикт + источник + дата.
CLI на момент проверки — **2.1.214** (`claude --version`).

Сводка влияния на контракты/фазы:

| # | Пункт | Вердикт | Меняет |
|:--|:--|:--|:--|
| 1 | `defer` + resume | **[UNVERIFIED]** механика | P4.3/OQ-2 остаётся exploration — MVP без него |
| 2 | auto-compact в `-p` | RAG:✅ управляем env, НЕ отключаем | OQ-3: драйверу нужен свой контроль размера |
| 3 | AskUserQuestion в `auto` | RAG:✅ не auto-approve, требует ввода | эскалация через handoff (не вопрос) подтверждена |
| 4 | `--max-turns` | RAG:✅ **СУЩЕСТВУЕТ и работает** | **D7 переворачивается** |
| 5 | баги #49525/#39973 | RAG:✅ **НЕ пофикшены** (closed not_planned/stale) | D28/D15в подтверждены: mode ФЛАГОМ, не хуком |
| 6 | CC Tasks `~/.claude/tasks` | **[UNVERIFIED]** как first-party примитив | D17в отклонён: драйвер строит СВОЮ очередь |
| 7 | LICENSE claudewatch / Ralph | RAG:✅ Ralph MIT / claudewatch топ без лицензии | Ralph = шаблон ok; claudewatch reference-only |
| 8 | MAX Bot API | RAG:✅ endpoint/auth сняты | P4.1 notify-адаптер: контракт есть |
| 9 | quota-детект | RAG:✅ различим по тексту, reset-ts нет | D18 подтверждён + уточнён |

---

## 1. `defer` permission + Agent SDK resume — [UNVERIFIED] как рабочая механика

**Вердикт:** `defer` перечислен как значение `permissionDecision` в PreToolUse, НО его
поведение в headless `-p` first-party дока НЕ специфицирует (нет описания «выход с
сохранённым pending tool call», нет рабочего примера). `--resume <session-id>` резюмит
ВСЮ сессию-разговор, а не подвешенное разрешение конкретного tool-call. Родного
задокументированного remote-approve-flow нет.

**Следствие:** Layer 3 (P4.3, OQ-2) остаётся exploration; **MVP живёт без defer-resume**
(D6). Строить контракт на defer НЕЛЬЗЯ — механика не гарантирована. Если Layer 3 делаем —
только после отдельного прототипа-доказательства (Scope P4.3), не на доке.

**Источник:** hooks.md (значение `defer` перечислено без семантики), headless.md (о
suspend/resume approval молчит), permission-modes.md — claude-code-guide, 2026-07-18.

## 2. auto-compact в `-p` — RAG:✅ управляем, не отключаем

**Вердикт:** авто-компакт срабатывает при достижении % от контекст-окна модели (Sonnet 5 —
1M, стандартные — 200K); дефолтный % публично НЕ задокументирован. **Управляется env:**
`CLAUDE_CODE_AUTO_COMPACT_WINDOW=<tokens>` (переопределить эффективный размер окна для
порога) и `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=<1-100>` (процент срабатывания). Полностью
**отключить в `-p` штатно нельзя** — только сдвинуть порог.

**Следствие (OQ-3 → снят):** нативного жёсткого контроля недостаточно → драйверу нужен
СВОЙ контроль размера сессии (timeout + сплит item'а сверх нативного). «1 сессия = 1 item»
+ fresh-session-per-item (D1) уже ограничивает рост; env-tuning — дополнительный рычаг.

**Источник:** env-vars.md (Context Window & Compaction) — claude-code-guide, 2026-07-18.

## 3. AskUserQuestion в `auto`-mode — RAG:✅ не auto-approve

**Вердикт:** в `auto` (mode-классификатор) AskUserQuestion **НЕ авто-одобряется** — он
требует пользовательского ВВОДА, а не разрешения, и классификатором не покрывается; в
`dontAsk` — явно denied даже при матчащем allow-правиле; в `bypassPermissions` — всё равно
промптит (исключение). Во всех headless-режимах AskUserQuestion эффективно нерабочий.

**Следствие:** подтверждает §1 факт-листа и D3 — канал эскалации воркера = **handoff**
(ATTENTION/Escalation Needed), а не вопрос. Ни `auto`, ни любой другой режим этого не меняют.

**Источник:** permission-modes.md — claude-code-guide, 2026-07-18.

## 4. `--max-turns` — RAG:✅ СУЩЕСТВУЕТ и работает (D7 переворачивается)

**Вердикт:** флаг **есть и работает на 2.1.214**. Локальная проверка:
`claude -p --max-turns 1 "reply with the single word OK" --output-format json` →
exit 0, валидный `{"type":"result","is_error":false,"num_turns":1,"result":"OK",...}`.
В `claude --help` присутствует строка про лимит «of each user turn»; дополнительно
обнаружен **`--max-budget-usd <amount>`** (потолок трат API на прогон). Первоначальное
`grep` факт-листа промахнулось (флаг в свёрнутой секции help), а не отсутствовал.

**Следствие (D7 финализируется, вывод МЕНЯЕТСЯ):** драйвер ограничивает ходы штатным
`--max-turns` (а НЕ только `timeout`), а стоимость прогона — `--max-budget-usd`; оба —
дешёвые встроенные предохранители для unattended (P2 worker-запуск, P5 cost-aware). Прежнее
«считать несуществующим» отменено.

**Источник:** локальный exec `claude` 2.1.214 (2026-07-18, session_id eda9aad3) +
cli-reference.md (Resource & Turn Limits).

## 5. Баги #49525 / #39973 — RAG:✅ НЕ пофикшены на 2.1.214

**Вердикт (GitHub API, прямое чтение issue):**
- **#49525** («setMode:'bypassPermissions' silently dropped in 2.1.110+»): state=closed,
  **state_reason=`not_planned`**, label `stale`; закрыт ботом github-actions по неактивности
  2026-05-25. Последний человеческий датапоинт (edwluo, 2026-04-18): **«Still broken in
  2.1.113 and 2.1.114»** с чистым bisect (регрессия с 2.1.107→2.1.11x). Фикс-коммита/
  changelog-записи нет.
- **#39973** («ExitPlanMode resets permission mode to acceptEdits»): state=closed,
  **state_reason=`not_planned`**, `stale`; закрыт ботом 2026-05-10. Комментарий (epologee):
  hook `setMode` в PermissionRequest принимает ТОЛЬКО `default|acceptEdits|dontAsk|plan` —
  `bypassPermissions` не валиден; программно восстановить режим после ExitPlanMode нельзя.

Оба закрыты **административно (stale-бот), НЕ решены**. На 2.1.214 (> 2.1.114) доказательств
фикса нет → **баги в силе**.

**Следствие (вход P3, D28/D15в подтверждены):** permission-mode задаётся **ФЛАГОМ
`--permission-mode` при запуске** `claude -p`, НИКОГДА через hook-`setMode`; `bypassPermissions`
через hook недостижим (и не дефолт — D28). ExitPlanMode-сброс режима — реальный риск, но
worker-профиль стартует НЕ в plan-mode (baseline `acceptEdits`, D28), контур ExitPlanMode не
задействуется. Зафиксировать как явный вход детализации/exec P3.

**Источник:** GitHub API `repos/anthropics/claude-code/issues/{49525,39973}` (+comments) —
2026-07-18.

## 6. Claude Code Tasks (`~/.claude/tasks`) — [UNVERIFIED] как first-party примитив

**Вердикт:** first-party дока НЕ описывает `~/.claude/tasks` как durable DAG-примитив.
Задокументировано ТОЛЬКО session-scoped: `/loop` (интервальный цикл) + Cron-тулы
(`CronCreate/Delete/List`), истечение через 7 дней, восстановление через `--resume`.
`CLAUDE_CODE_TASK_LIST_ID` в first-party доке НЕ найден; `CLAUDE_CODE_ENABLE_TASKS`
упоминается лишь как отключение legacy `TodoWrite`, не как включение durable-очереди.
Локально: **`~/.claude/tasks` не существует** (`ls` → No such file). Perplexity-утверждение
(finding supervisor-runtimes §3: «DAG blocked-by, shared task list, переживает ребут»)
**первоисточником НЕ подтверждено** → по D19 отклоняется как несущий факт.

**Следствие (D17в отклонён):** драйвер НЕ опирается на CC Tasks — строит **СВОЮ durable
очередь items** (run-folder `state.json` + `journal.jsonl`, P0.6/P2.4). Это и был fallback-
план (D16/D17: «готового нет — строим свой»); CC Tasks как удешевление P2-очереди снимается
с рассмотрения.

**Источник:** scheduled-tasks.md (claude-code-guide, 2026-07-18) + локальный `ls ~/.claude/tasks`
+ отсутствие first-party подтверждения Perplexity-заявки (D19).

## 7. LICENSE claudewatch / Ralph orchestrator — RAG:✅

**Вердикт (GitHub API):**
- **ralph-orchestrator** (`mikeyobrien/ralph-orchestrator`): **MIT**, 3037★, активен
  (pushed 2026-07-10), archived=false. → легально пригоден как АРХИТЕКТУРНЫЙ шаблон
  run-folder layout (D17а: `events-*.jsonl`/`tasks.jsonl`/termination-контур) и эвристика
  similarity≥90% (P5.1). D17 «лицензия Ralph — перепроверить» → снято: MIT.
- **claudewatch**: единой канонической репы НЕТ (десятки одноимённых форков). Топовая по
  звёздам — `theangeloumali/ClaudeWatch` (79★) — **license=null (без лицензии = all rights
  reserved, НЕ пригодна для reuse)**; MIT-варианты существуют только у мелких форков
  (elliotykim 41★, gosparq 10★ и др.).

**Следствие:** Ralph — шаблон структуры (не донор кода, D17б), лицензия чистая. claudewatch —
**reference-only** (наблюдение за квотой/usage — идея), код НЕ вендорить (топ-репа
unlicensed); наш quota-детект build-new (D18/D45 Ф-набор). Юр-риск reuse снят.

**Источник:** GitHub API `repos/mikeyobrien/ralph-orchestrator`, `search/repositories?q=claudewatch`
— 2026-07-18.

## 8. MAX Bot API — RAG:✅ (Perplexity, сверено с first-party dev.max.ru)

**Вердикт:** отправка сообщения — `POST https://platform-api2.max.ru/messages`, заголовок
`Authorization: <bot_token>` (токен в query больше НЕ поддерживается — только header),
тело JSON `{ "chat_id": <int>, "text": "...", "format": "markdown"|"html" }`; апдейты —
long-poll `GET /updates` (dev/test) или webhook `POST /subscriptions` (prod, HTTPS с
доверенным сертификатом обязателен с 2026-05-25). **Внимание:** база в миграции
`platform-api.max.ru` → `platform-api2.max.ru`, дедлайн перехода **2026-07-19** (завтра) —
на момент реализации P4.1 перепроверить актуальную базу. Паттерн `api.max.im/bot<TOKEN>/…`
(Telegram-подобный) — из сторонних статей, НЕ официален.

**Следствие:** Layer 1 notify-адаптер MAX (P4.1, D31) реализуем на stdlib `urllib` (POST
JSON + header) — тривиально, без Bun/TS-плагина. Контракт `sendMessage` для envelope (D32)
есть. Base-URL — единственная плавающая деталь, снять на P4.1.

**Источник:** Perplexity search_advanced 2026-07-18, first-party цитата `https://dev.max.ru/docs-api`
(+ webappdev.ru/max/bot-api, github max-messenger/max-bot-api-client-go). D19: база
перепроверяется на P4.1 первоисточником перед кодом.

## 9. quota-детект в `claude -p --output-format json` — RAG:✅ (уточняет D18)

**Вердикт:**
- При исчерпании лимита: **`is_error: true`, exit code `1`** (общий failure).
- Тип лимита различается **ТОЛЬКО по тексту `result`**: «You've hit your **session** limit»
  (5-часовое скользящее окно) vs «You've hit your **weekly** limit» (недельный кап). ОТДЕЛЬНОГО
  структурного поля-типа НЕТ; в `stream-json` — `error_category: billing_error` в событиях
  `system/api_retry` (наравне с `rate_limit`/`authentication_failed`).
- **Reset-timestamp в JSON НЕ экспонируется** (CLI показывает «когда сбросится» в TTY, но
  структурного поля нет).
- **Смена учётки:** после `/login` (браузер-релогин) в другую учётку следующий вызов
  `claude -p` подхватывает новый credential из хранилища CLI (приоритет: `ANTHROPIC_API_KEY`
  → `apiKeyHelper` → сохранённый OAuth-токен). Явной «ротации по релогину» в доке нет —
  подхват на СЛЕДУЮЩЕМ запуске.

**Следствие (D18 подтверждён и уточнён):** драйвер классифицирует quota-сбой по
`is_error && exit 1 && result~/session|weekly limit/`; **5h vs weekly — по подстроке текста**
(«session»→ждать/таймер; «weekly»/неизвестно → URGENT-эскалация будить, D18); **reset-ts нет
→ драйвер сам ставит 5h-таймер** от момента детекта; после ручного релогина «продолжай
<папка>» свежей сессией — CLI подхватит учётку. Детект по ТЕКСТУ — хрупкость (сообщение
может смениться): дефенсивно (подстрока + `billing_error` в stream-json), падение матча →
консервативно URGENT-эскалация (fail-safe, D18/D10).

**Источник:** errors.md (Usage Limits), headless.md (stream-json api_retry категории),
costs.md (5h + weekly окна) — claude-code-guide, 2026-07-18.

---

## Остаточные [UNVERIFIED] (приняты осознанно, зависимые контракты их не используют)

- **#1 defer-resume** — механика не гарантирована дока → P4.3/Layer 3 остаётся опциональным
  прототипом (OQ-2), MVP без него. Риск принят: не блокирует P0.2/P0.6 (они defer не читают).
- **#6 CC Tasks формат** — first-party примитив не подтверждён → драйвер строит свою очередь
  (P0.6). Риск принят: путь «свой run-folder» и был основным (D16), CC Tasks был бы бонусом.

Оба не разблокируют/не блокируют несущие контракты — фазы построены на верифицированном
подмножестве (пп. 2,3,4,5,7,8,9). Дисциплина D19 соблюдена: не выдано ни одного «работает,
вроде» без грепаемого артефакта.
