# P1↔P0 reconcile — журнал P1.1 против запечатанных контрактов P0.2/P0.6

**Слой 2 (синтез).** Дата: 2026-07-18. Автор: opus (design pass P1 reconcile).
**Повод:** P0 закрыта 6/6 🟢; контракты P0.2 (`driver-plan-protocol.md`) и P0.6
(`artifex-run-folder.md`) перешли draft→**sealed**. Контракт-блок фазы P1 их потреблял как
`draft`; §5 plan-protocol требует сверить `Потребляет` P1 с фактическим `Производит` P0 и при
расхождении — правка + D#. Reconcile-долг был явно назван (handoff after P0.3, Open risks;
P0.2 §6; P0.6 §6).

**Источники (слой 1/контракты):**
- `root/contracts/driver-plan-protocol.md` (P0.2, sealed, пин plan-protocol **v2.8.0 @ 2cf26e8**) — §2 JSON-конверт, §6 «совместимость с журналом P1.1».
- `root/contracts/artifex-run-folder.md` (P0.6, sealed, **v1**) — §3 событийная схема journal.jsonl, §6 reconcile-контракт с P1.1.
- `phases/P1.md` P1.1 (схема пер-планового `journal.jsonl`), plan.md D8/D20/D24/D26.

---

## 1. Сверка полей: пер-плановый журнал P1.1 ↔ run-folder journal P0.6 §3

P0.6 §6 объявил общие поля (контракт-ожидание к P1.1): `ts`, `plan_id`, `item_id`, `command`,
`result`, `session_id`, `run_id`. Фактическая сверка:

| Поле | P1.1 (пер-плановый) | P0.6 §3 (run-folder) | Вердикт |
|:--|:--|:--|:--|
| `ts` | str ISO-8601 UTC | ⚑ str ISO-8601 UTC | **байт-идентичен** (ключ) |
| `plan_id` | str | ⚑ str | **байт-идентичен** (ключ) |
| `run_id` | str\|null (ручной→null) | ⚑ str (== state.run_id) | **линковка**: P1.1 nullable (ручной запуск вне Artifex → null; Artifex → set = run_id прогона P0.6) |
| `session_id` | str\|null | ⚑ str\|null (null для событий драйвера) | **байт-идентичен** (ключ; null при backstop-записи драйвером) |
| `item_id` | str (Pn.m/Pn — запись ВСЕГДА про исполнение item) | ⚑ str\|null (null для событий уровня прогона/фазы) | **совместим (сужение)**: P1.1 никогда не эмитит null; P0.6 шире (несёт run-level события) |
| `command` | enum `/task:plan-{exec,run,close,audit,design}` | ⚑ str (в `item_launch`, «что запущено») | **совместим**: P1.1 конкретизирует enum'ом |
| `result` | **enum** {closed-green, closed-deviations, blocked, escalated, no-op, audit-red, audit-green, in-progress} | ⚑ в `item_result`: `result` («исход прогона», JSON-конверт P0.2 §2) **+ отдельно** `terminal_status` (∈6 канон-статусов) | **РАСХОЖДЕНИЕ** — см. §2 |

Прочие поля P1.1 (`attempt`, `actor`, `friction[]`, `cost_usd`, `num_turns`, `duration_ms`,
`note`) — НЕ помечены ⚑ в P0.6; агрегатные/производные, конфликта нет:
- `attempt` (P1.1, int на запись) ↔ `state.counters.attempts{"<Pn.m>": n}` (P0.6, снимок) — консистентно (журнал = per-attempt, state = агрегат).
- `cost_usd` (P1.1, запекается на запись из `_usage.py`) ↔ `item_result.total_cost_usd` → `state.cost_usd` (P0.6, per-run) — разные единицы агрегации, имя различается осознанно.

---

## 2. Единственное расхождение — поле `result`

**Факт.** P0.6 §3 в событии `item_result` несёт ДВА раздельных поля: `result`⚑ (исход ПРОГОНА —
процесс воркера завершился успешно/с ошибкой, производно от `is_error` JSON-конверта P0.2 §2) и
`terminal_status` (статус ITEM'а в ПЛАНЕ — один из 6 канонических 🟢/🟠/🔴/…). P1.1 несёт ОДНО
поле `result` — enum, СЛИВАЮЩИЙ исход-прогона + терминальный-статус-плана + вердикт-аудита
(`audit-red`/`audit-green`). Плюс есть тёзка-коллизия: в JSON-конверте P0.2 §2 поле `result` —
это СЫРОЙ финальный ТЕКСТ воркера (str), не enum.

**Вердикт (D46).** Байт-идентичны только 6 ЛИНКОВОЧНЫХ ключей: `ts, plan_id, item_id, command,
session_id, run_id`. Поле `result` — общее **по маппингу, не по идентичности**:

- P1.1.`result` (enum) — КОНСОЛИДИРОВАННЫЙ исход одного исполнения item, **ПРОИЗВОДНЫЙ**:
  для Artifex-порождённого item — из события `item_result` P0.6 (`result`+`terminal_status`+`is_error`);
  для ручного/backstop — из close-исхода воркера. НЕ копия сырого `result`-текста JSON-конверта.
- P0.6 сохраняет своё расщепление `result`+`terminal_status` (событийный лог; разделять
  успех-процесса и статус-плана там осмысленно). **P0.6 НЕ правится** (sealed; §6 P0.6 прямо
  делегирует расхождение reconcile-D#, а не тихой подгонке/правке схемы).
- Маппинг (документируется в P1.1, живёт на стороне P1.1):

  | P0.6 `item_result` (is_error / terminal_status) | P1.1 `result` |
  |:--|:--|
  | is_error=false, terminal_status=🟢 | `closed-green` |
  | is_error=false, terminal_status=🟠 | `closed-deviations` |
  | terminal_status=🔴 / Escalation Needed / ESCALATION-REQUIRED | `blocked` / `escalated` |
  | Вердикт `## Audit Pn` = RED / GREEN | `audit-red` / `audit-green` |
  | прогон без изменения статуса (no-op) | `no-op` |
  | запись СТАРТА (in-progress, до закрытия) | `in-progress` |

**Что исправляется в P1.1** (прежнее утверждение Implementation Rules: «общие … поля (ts,
plan_id, item_id, command, **result**, session_id, run_id) — байт-в-байт совпадают по имени/типу»
— теперь неверно для `result`): линковочные ключи (6) — байт-в-байт; `result` — по маппингу +
явно помечен ПРОИЗВОДНЫМ (не тёзка сырого `result`-текста конверта P0.2 §2).

---

## 3. Побочный reconcile: версия канона (P1.4 ↔ P0.2 пин)

P0.2 запечатан с пином plan-protocol **v2.8.0 @ 2cf26e8**. P1.4 вносит journal/index в §2
Раскладку скилла plan-protocol — это правка КАНОНА. Разбор влияния на parse-контракт драйвера
(P0.2 §4 breaking-детект — закрытый перечень якорей §1–§4: статусы, заголовок handoff, enum Next,
шапка Status Board, поля JSON-конверта):

- Добавление `journal.jsonl`/`index.md` в §2 Раскладку **НЕ трогает** ни один якорь P0.2 §1–§4 →
  **НЕ breaking** для драйвера.
- ⇒ P1.4 бампает канон **v2.8.0 → v2.9.0** (minor: расширение раскладки, обратно-совместимо) и
  **re-пинит** P0.2 контракт на v2.9.0 БЕЗ breaking-стопа (D47). Это снимает If-then P1.4 «если
  P0.2 не исполнен — не выдумывать версию»: P0.2 исполнен, пин конкретен.

---

## 4. Итог reconcile

- Контракт-блок P1: P0.2/P0.6 `draft` → `sealed` (пины v2.8.0@2cf26e8 / run-folder v1).
- P1.1: линковочные ключи байт-идентичны (6); `result` — по маппингу, производный (D46).
- P1.4: канон-бамп конкретизирован v2.8.0→v2.9.0, non-breaking для P0.2 (D47).
- P0.2/P0.6 **не правятся** (sealed; расхождение разрешено документацией, как предписано их §6).
- Структурный `Производит`/`Потребляет` P1 **не изменился** → нового `finish` не требуется
  (только draft→sealed + уточнение поля + версия).
