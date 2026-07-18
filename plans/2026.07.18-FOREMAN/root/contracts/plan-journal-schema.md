---
type: contract
plan: 2026.07.18-FOREMAN
contract: plan-execution-journal (per plan, append-only)
status: sealed (P1.1)
exports: "пер-плановый журнал исполнения plans/<ID>/journal.jsonl (append-only NDJSON)"
version: v1
consumers: "драйвер P2.3 (next/retry по result), скилл supervisor-protocol P3.3, эскалация P4, прогресс-движок P5 (петли/трение/cost), все планы экосистемы после P1.4 (канон+lint)"
reconcile: "run-folder journal P0.6 §3 (артефакт artifex-run-folder.md) — 6 линковочных ключей байт-идентичны, поле result по маппингу (D24/D46, research/03-p1-p0-reconcile.md); JSON-конверт P0.2 §2 (driver-plan-protocol.md) — источник cost/turns/session_id"
verdict: "RAG:— (repo-grounded: brief/01-refinements.md §1; harness run-report README I/O-контракт + _usage.py; D8/D20/D24/D46; P0.2 §2/§6 sealed; P0.6 §3/§6 sealed v1)"
---

# Контракт пер-планового журнала исполнения (`plans/<ID>/journal.jsonl`)

**Назначение.** Канон **истории исполнения ПЛАНА**: неизменяемый append-only лог «что реально
запускалось в рамках плана, с какими трениями, с каким результатом» — одна запись на исполнение
item ЛЮБЫМ запуском `/task:plan-*`, из ВСЕХ сессий (ручных владельца и Artifex-порождённых).
Сессии Claude Code не привязаны к плану — по логам сессий (`.claude/runs/`) невозможно
восстановить «какая команда шла в рамках какого плана» (brief §1); журнал закрывает этот разрыв
и является главным входом прогресс-движка супервизора P5 (петли одной команды, трение, cost-aware
сигнал зацикливания).

**Формат.** NDJSON (D20): файл `plans/<ID>/journal.jsonl`, одна строка = одна запись валидного
JSON. Человекочитаемый вид НЕ хранится отдельным файлом — генерируется по запросу
(`plan-lint`/хелпер), чтобы не плодить второй носитель факта (§3 plan-protocol; отвергнутые
варианты B/C — plan.md §Обсуждение).

**Дом записи (P1.3).** Пишет **воркер** в close-протоколе `/task:plan-*` (хелпер
`lib/task/journal.py`, P1.3) — рядом с bookkeeping-коммитом, где план-файлы уже пишутся.
Драйвер Artifex пишет пер-плановую запись ТОЛЬКО как backstop (воркер упал до close-протокола —
crash/timeout/quota-abort; D26/P0.6 §6). Реализация записи — P1.3, НЕ этот контракт (он — схема).

---

## 1. Правило append-only (иммутабельность истории)

- Запись **только добавляется** в конец файла. Существующие строки **НИКОГДА** не
  перезаписываются и не удаляются — в этом весь смысл журнала против `handoff.md`
  (перезаписываемый снапшот «куда дальше») и Status Board (текущий статус item).
- Правка «задним числом» запрещена: ошибочная запись НЕ редактируется, а **компенсируется**
  новой записью (напр. `friction:["deviation"]` + `note` с пояснением). История дефекта — часть
  истории плана.
- Append из параллельных сессий — построчный (NDJSON без merge-конфликтов: каждая сессия
  дописывает свою строку, git-merge разрешается конкатенацией, D20).
- Файл **git-tracked и durable** (в отличие от эфемерного `.claude/runs/` run-report, который
  gitignored и machine-local — §4).

---

## 2. Схема записи

Одна запись = один JSON-объект в одну строку. Поля:

| Поле | Тип | Обяз. | Дефолт | Назначение |
|:--|:--|:--:|:--|:--|
| `ts` | str | ✔ | — | ISO-8601 UTC момента записи (`2026-07-18T18:42:07Z`) ⚑ |
| `plan_id` | str | ✔ | — | ID плана (`2026.07.18-FOREMAN`) ⚑ |
| `item_id` | str | ✔ | — | `Pn.m` или `Pn` — запись ВСЕГДА про исполнение конкретного item ⚑ (сужение P0.6 `str\|null`) |
| `command` | enum | ✔ | — | что запущено: `plan-exec`\|`plan-run`\|`plan-close`\|`plan-audit`\|`plan-design` ⚑ |
| `session_id` | str\|null | ✔ | `null` | id сессии CC-воркера (best-effort указатель на run-report); `null` при backstop-записи драйвером ⚑ |
| `run_id` | str\|null | ✔ | `null` | прогон Artifex (`ГГГГ.ММ.ДД-КОД` = run-folder P0.6); `null` для ручного запуска вне Artifex ⚑ |
| `attempt` | int | ✔ | `1` | счётчик петель ОДНОГО item (1-based); связывает старт+финал одного исполнения и повторные попытки (вход P5) |
| `actor` | str | ✔ | — | кто исполнял: `<model>/<effort>` (напр. `opus/high`) или `owner` (ручная правка владельцем) |
| `friction` | array<enum> | ✔ | `[]` | маркеры трения (закрытый список, §2.1); пустой массив = гладкий прогон |
| `result` | enum | ✔ | — | консолидированный исход исполнения (закрытый список, §2.2); ПРОИЗВОДНОЕ поле (§2.3) |
| `cost_usd` | number\|null | ✔ | `null` | стоимость прогона, ЗАПЕКАЕТСЯ при закрытии (§4); `null` в старт-записи и когда недоступно |
| `num_turns` | int\|null | ✔ | `null` | число ходов сессии, запекается при закрытии; `null` в старт-записи/недоступно |
| `duration_ms` | number\|null | ✔ | `null` | длительность прогона, запекается при закрытии; `null` в старт-записи/недоступно |
| `note` | str\|null | ✔ | `null` | 1 строка сути (что сделано / причина трения); `null` если нечего добавить |

⚑ = поле общее с run-folder journal P0.6 §3 (реконсиль-контракт, §5). `attempt`/`actor`/
`friction`/`cost_usd`/`num_turns`/`duration_ms`/`note` — агрегатные/производные, в P0.6 не помечены
⚑, конфликта нет (research/03 §1).

**Пара записей на исполнение (P1.3).** Одно исполнение item эмитит ДВЕ записи: **старт**
(`result:"in-progress"`, cost/turns/duration = `null` — ещё неизвестны) в начале и **финал**
(терминальный `result` + запечённые cost/turns/duration) при закрытии. Обе несут один `attempt`;
повторная попытка того же item — новый `attempt` со своей парой. Backstop-запись драйвера (воркер
упал) — одна финальная запись с `result:"blocked"`/`"escalated"`.

### 2.1 Enum `friction` (закрытый список)

Маркеры трения в процессе исполнения (массив, могут сочетаться):

| Значение | Когда |
|:--|:--|
| `escalation` | воркер поднял эскалацию (`🔴 Blocked`/`Escalation Needed: yes`/`ESCALATION-REQUIRED`) |
| `routing-blocked` | routing-гейт остановил исполнение (`ROUTING-BLOCKED`/`ROUTING-INCONSISTENT`) |
| `red-audit` | аудит вернул RED/ATTENTION по этому item |
| `deviation` | зафиксировано отклонение (Known Deviations непусто — material или process) |
| `retry` | исполнение — повторная попытка (attempt > 1) или tier-ретрай драйвера |
| `no-op` | прогон не изменил статус item (движение на месте — сигнал зацикливания P5) |

### 2.2 Enum `result` (закрытый список)

Консолидированный исход ОДНОГО исполнения item:

| Значение | Смысл |
|:--|:--|
| `in-progress` | старт-запись (item взят в работу, ещё не закрыт) |
| `closed-green` | item закрыт `🟢 Done` |
| `closed-deviations` | item закрыт `🟠 Done with deviations` |
| `blocked` | item `🔴 Blocked` (нужна правка плана/владелец) |
| `escalated` | исполнение подняло эскалацию владельцу (`ESCALATION-REQUIRED`) |
| `no-op` | прогон завершился без изменения статуса item (петля без прогресса) |
| `audit-green` | заход `/task:plan-audit` дал вердикт GREEN |
| `audit-red` | заход `/task:plan-audit` дал вердикт RED/ATTENTION |

### 2.3 `result` — ПРОИЗВОДНОЕ поле (анти-тёзка-коллизия)

`result` журнала P1.1 — **enum-исход**, СЛИВАЮЩИЙ (а) успех/провал прогона, (б) терминальный
статус item в плане, (в) вердикт аудита. Он **производный** и **НЕ тёзка** сырого `result`-ТЕКСТА
JSON-конверта `claude -p` (P0.2 §2: `result` там — финальный str-текст воркера, не enum).
Путать эти два `result` — источник тихой ошибки парсера (Code Guidance P1.1); при реализации
(P1.3) явно разделять.

**Источник значения:**
- Artifex-порождённый item → из события `item_result` run-folder P0.6 (`is_error` +
  `terminal_status` + `result`-текст конверта), по маппингу §2.4.
- Ручной / backstop → из close-исхода воркера (Status item'а после закрытия / текста отчёта).

### 2.4 Маппинг P0.6 `item_result` → P1.1 `result` (D46, research/03 §2)

| P0.6 `item_result` (is_error / terminal_status / вердикт) | P1.1 `result` |
|:--|:--|
| `is_error=false`, `terminal_status=🟢` | `closed-green` |
| `is_error=false`, `terminal_status=🟠` | `closed-deviations` |
| `terminal_status=🔴` | `blocked` |
| `Escalation Needed: yes` / `ESCALATION-REQUIRED` | `escalated` |
| прогон без изменения статуса (no-op) | `no-op` |
| вердикт `## Audit Pn` = GREEN / RED | `audit-green` / `audit-red` |
| старт-запись (in-progress, до закрытия) | `in-progress` |

---

## 3. Граница анти-второй-носитель (§3 plan-protocol)

Журнал — **append-only ИСТОРИЯ запусков**, НЕ текущее состояние. Не дублирует:

- **Status Board** (`plan.md §4` / `Phase Status`) — единственный носитель ТЕКУЩЕГО статуса item.
  Журнал фиксирует ход исполнения (`result` записи), но SSOT статуса — Status Board.
- **`handoff.md`** — единственный носитель «куда дальше» (перезаписываемый снапшот). Журнал не
  несёт «next».
- **run-folder `journal.jsonl` P0.6** — сырой событийный лог ОДНОГО прогона супервизора; журнал
  P1.1 — консолидированная история ПЛАНА (§5).

Соблазн внести в журнал статус/next → стоп: это источник дрейфа (два носителя одного факта, §3).

---

## 4. Durable-vs-ephemeral граница

- Журнал `journal.jsonl` — **git-tracked, durable** (переживает ребут, часть дерева плана).
- `.claude/runs/<session_id>.json` (run-report harness) — **эфемерный, gitignored, machine-local**
  (README run-report: `runs/` само-игнорируется `*`). Журнал НЕ ссылается на него как на живую
  зависимость.
- **`session_id`** — best-effort указатель на эфемерный run-report для отладки, НЕ жёсткая
  зависимость: если run-report подчищен ретеншеном, запись журнала остаётся полной.
- **`cost_usd`/`num_turns`/`duration_ms` ЗАПЕКАЮТСЯ** в запись при закрытии (не ссылка на
  эфемерный источник).

**Источник cost/turns/duration (reuse, разобрано до корня — Code Guidance P1.1).** `_usage.py`
(`finish()`) возвращает токены (`in`/`out`/`cache_*`), `msgs`, `wall_seconds` — но **НЕ**
`total_cost_usd`/`num_turns` напрямую. Каноничный источник этих трёх — **JSON-конверт
`claude -p --output-format json`** (P0.2 §2: `total_cost_usd`, `num_turns`, `duration_ms`):
- **Artifex/headless** (конверт есть): `cost_usd ← total_cost_usd`, `num_turns ← num_turns`,
  `duration_ms ← duration_ms` (через `item_result` P0.6 → запись).
- **Ручной запуск** (конверта нет, только транскрипт): best-effort через run-report
  `_lib.py`/`_usage.py` — `duration_ms ← wall_seconds·1000`, `num_turns ≈ msgs`, `cost_usd`
  требует прайсинг-слоя поверх токенов `_usage.py` (или остаётся `null`). Реализация (P1.3)
  обязана брать метрики этим общим путём, не изобретать свой парсер транскрипта; расхождение
  полей `_usage.py` со схемой (нет прямого USD) разрешено здесь документацией, не подгонкой.

---

## 5. Reconcile с run-folder journal P0.6 (D24/D46)

Два журнала делят общие поля и связываются ключами (D24, артефакт `artifex-run-folder.md` §6):

- **run-folder `journal.jsonl`** (P0.6) = сырой событийный лог ОДНОГО прогона супервизора (все
  его сессии, ретраи, `decision`-события).
- **пер-плановый `journal.jsonl`** (этот контракт, P1.1) = консолидированная история ПЛАНА (одна
  запись на исполнение item, из ВСЕХ сессий — ручных и Artifex).

**Байт-идентичны по имени/типу — ТОЛЬКО 6 линковочных ключей** (D46, research/03 §1):
`ts`, `plan_id`, `item_id`, `command`, `session_id`, `run_id`. Оговорки сужения:
- `item_id` — в P1.1 всегда set (`str`), в P0.6 шире (`str|null` — несёт run-level события).
- `session_id` / `run_id` — nullable в обоих.

**Поле `result` — общее ПО МАППИНГУ, не по идентичности** (§2.3–2.4): P1.1 сливает в один enum
то, что P0.6 держит раздельно (`result` конверта + `terminal_status`). P0.6 **sealed, НЕ
правится**; расхождение разрешено документацией на стороне P1.1 (как предписывает §6 P0.6 —
reconcile-D#, не reopen P0).

**Владение записью / линковка (D26).** Драйвер инъектит `run_id` в env воркера
(`ARTIFEX_RUN_ID`) → воркерская запись P1.1 несёт `run_id`. Драйвер бэкфиллит пер-плановую запись
ТОЛЬКО когда воркер упал до close-протокола (единственный случай прямой записи драйвером) — так
D24 «Artifex пишет в оба» соблюдается без двойной записи одной строки.

**If-then (анти-тихая-подгонка).** Если при реализации P1.3 обнаружится НОВАЯ несовместимость
общих полей сверх разрешённого D46 — **эскалация + D# (supersedes)**, P0.6 sealed НЕ править
(reopen P0), расхождение разрешать на стороне P1.1.

---

## 6. Трассировка полей → потребитель (анти-«поле на будущее»)

| Поле | Потребитель |
|:--|:--|
| `result` | драйвер P2.3 (next/retry/эскалация по исходу), прогресс-движок P5 |
| `friction`, `attempt` | прогресс-движок P5 (петли/трение — прогресс vs зацикливание), скилл P3.3 |
| `no-op` (result/friction) | P5 cost-aware + content-aware детект «движение на месте» |
| `cost_usd`, `num_turns`, `duration_ms` | P5 cost-aware сигнал зацикливания, mAInd-репорт P4.4 |
| `run_id` | связь с run-folder P0.6 (один прогон ↔ его записи в истории плана) |
| `session_id` | линковка с run-report (отладка), P0.2 §2 |
| `actor` | аудит владельца (кто/какой моделью исполнял), routing-adherence |

---

## 7. Примеры записи

**Минимальная (старт-запись, ручной запуск владельца):**

```json
{"ts":"2026-07-18T18:40:00Z","plan_id":"2026.07.18-FOREMAN","item_id":"P1.1","command":"plan-run","session_id":null,"run_id":null,"attempt":1,"actor":"opus/high","friction":[],"result":"in-progress","cost_usd":null,"num_turns":null,"duration_ms":null,"note":null}
```

**Полная (финал, Artifex-порождённый прогон с трением):**

```json
{"ts":"2026-07-18T19:12:33Z","plan_id":"2026.07.18-FLEX-2","item_id":"P3.2","command":"plan-exec","session_id":"eda9aad3-1f2b-4c7e-9a01-77b2c9d4e5f6","run_id":"2026.07.20-FLEX2-P3-DRIVE","attempt":2,"actor":"sonnet/high","friction":["retry","deviation"],"result":"closed-deviations","cost_usd":1.83,"num_turns":14,"duration_ms":268400,"note":"tenancy-reuse: workaround stancl/tenancy v4, Known Deviation D12"}
```

**Backstop (воркер упал до close, запись драйвера):**

```json
{"ts":"2026-07-18T20:03:11Z","plan_id":"2026.07.18-FLEX-2","item_id":"P3.3","command":"plan-exec","session_id":null,"run_id":"2026.07.20-FLEX2-P3-DRIVE","attempt":1,"actor":"sonnet/high","friction":["escalation"],"result":"blocked","cost_usd":0.42,"num_turns":3,"duration_ms":51200,"note":"timeout до close-протокола; backfill драйвером (D26)"}
```
