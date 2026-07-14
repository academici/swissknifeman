# HANDOFF — 2026-07-14 — after P3

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high» — item P3.1 (`Exec = manual`, D45)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — сведение восьми правил канона в один текст команды под потолком 180 строк (авторская правка контракта, не транскрипция) |
| Context | continue (/clear) — ручной item |
| Суть | `plan-exec.md`: routing-гейт (F7) + топология двух коммитов + честный lint с атрибуцией + status-rule |

Slash-команды у item'а нет: `/task:plan-exec` пинит sonnet/medium и по routing-гейту обязан
`Exec = manual` отклонить. Выстави `/model opus` + `/effort high`, затем голый промпт:

```
Исполни item P3.1 мастер-плана 2026.07.13-PLAN-PROTOCOL-GAP по plan-протоколу (скилл
general/plan-protocol — SSOT; команда packages/task/commands/plan-exec.md — протокол исполнения,
читай её как инструкцию, но НЕ запускай как slash-команду: item Exec = manual, D45).

Cold-start reads (в этом порядке):
1. plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md — §1 Context, §2 Execution Rules, §3 Routing,
   §4 Status Board, D-лог (несущие: D1/D2/D5/D6/D8/D9/D15/D16/D19/D22/D26/D27/D33/D36/D38/D45);
2. plans/2026.07.13-PLAN-PROTOCOL-GAP/handoff.md — где мы;
3. plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P3.md — Phase Context + item P3.1 целиком (16 полей);
4. Required Reads item'а P3.1 — в указанном порядке.

Исполняй СТРОГО в Scope Included P3.1; Implementation Rules и Code Guidance — жёсткие рамки.
Закрытие ОБЯЗАТЕЛЬНО по §8 (две коммит-топологии: item-коммит по путям Files → bookkeeping →
перезапись handoff → plan-lint --baseline HEAD ПОСЛЕ handoff → счёт с атрибуцией K → bookkeeping-
коммит). git add -A запрещён. Числа в отчёте — с якорем дерева (D36).
```

**Аудит №4 фазы P2 ОТМЕНЁН (D44, решение владельца).** Вместо него — детерминированный
конфликт-скан (на `b5ca096`): enum `Context` (3 значения) и enum форм `Next` (8) совпадают в
`SKILL.ru.md` / `SKILL.md` / снипетах; `fresh session` (значение вне enum'а) — 0; противоречий
топологии коммита нет; гейт литералов `i18n-keep` — **0 ❌**; тесты линтера — **124 OK**;
`validate.sh` обоих пакетов зелёные; `plan-lint` по 6 планам монорепо — **0 ERROR**.
Остаточный риск назван: скан покрывает МЕХАНИЧЕСКИЙ класс (он же дал все окупившиеся находки трёх
аудитов), семантику правил не проверяет — ловится первым живым применением (P3) и регрессом (P4.1).

**Done:** P1 терминальна (`4c03715`, `b45cd51`). **P2 закрыта: 18/18 items терминальны**
(17 🟢 + P2.4 🟠) → фаза **🟠 Done with deviations**; скилл `plan-protocol` **2.5.0**, EN-канон
свежий (`d92ace0`), гейт литералов 0 ❌, `plan-lint` плана → 0 ERROR / 0 WARN (на `b5ca096`).

**Фаза P3 спроектирована** (`/task:plan-design`, эта сессия):
- **6 items** (было 5): ТЗ пересобраны под канон **2.5.0** — прежний текст P3 писался ДО трёх
  реопенов P2 и ссылался на ОТМЕНЁННЫЕ формы (топология одного коммита; `Context = NEW SESSION`
  у manual-item'а — отменён D33). Исполнение по старому ТЗ внесло бы в команды правила,
  противоречащие SSOT.
- **+P3.6** — терминальный item фазы (D42, opus/high, `Exec = manual`): `/task:plan-run` в §13
  скилла, версия 2.5.0 → **2.6.0**, регенерация EN-канона, `skiller registry` + **сквозная
  сверка «правило канона → команда»**.
- **D42/D43** — новые решения; `findings/P3-command-layer.md` — RAG-верификация омиссии
  `model`/`effort` (RAG:✅ 2026-07-14) + матрица дыр исполнительного слоя + потолки объёма команд.
- **Замер (findings §2, на `b5ca096`):** команды `/task:plan-*` не несут **ни одного** правила
  фаз P1/P2, а три их строки прямо ПРОТИВОРЕЧАТ канону 2.5.0 (один коммит вместо двух;
  `Context: fresh session` вне enum'а; RAG-enum из двух маркеров вместо трёх).

**Remaining:**

1. **P3** ← Next (6 items, ТЗ готовы, DoR пройден): P3.1 `plan-exec` → P3.2 `plan-close` →
   **P3.3 `plan-audit` (несёт правила остановки, D44)** → P3.4 `plan-design` → P3.5 `plan-run` →
   **P3.6 терминальный**. Порядок обязателен: P3.2/P3.5 читают тело `plan-exec` ПОСЛЕ P3.1.
   P3.1–P3.5 — `/task:plan-exec` (sonnet/medium); P3.6 — ЗАПУСК ВРУЧНУЮ (opus/high).
2. P4 (3 items): регресс по флоту, закрытие эскалации REGHUB, доки + CHANGELOG.
3. Аудит фазы P3 — по НОВЫМ правилам остановки (после P3.3): один заход, RED только на сломанном
   продукте, бухгалтерия → ATTENTION + Pending Work, реопена по умолчанию нет.

**Sources of truth:** `plan.md` (Meta **1.4.0**, §2 Execution Rules + carve-out D34, §3 Routing,
§5 D-лог **D1–D43**, `## Обсуждение` — 9 развилок со статусами) · `phases/P2.md` (Completion Notes
P2.1–P2.18, три блока `## Audit P2`, финальный `## Phase Handoff`) · `phases/P3.md` (**6 items,
ТЗ по канону 2.5.0**) · `phases/P4.md` (скелет) · `findings/P0-protocol-gap-recon.md`,
`findings/P2-third-reopen-fleet-measurements.md`, **`findings/P3-command-layer.md`** ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник 2.5.0;
`SKILL.md` — EN-канон, свежий; `snippets/`) · `packages/task/lib/task/plan_lint.py` (второй SSOT
схемы) · `packages/task/commands/plan-*.md` (**предмет фазы P3** — исполнительный слой).

**Open risks:**
- **Канон 2.5.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами** (D44: adversarial-аудит №4
  отменён в пользу конфликт-скана). Механический класс закрыт скриптом; «правило непротиворечиво,
  но вредно» — нет. Ловится первым живым применением (фаза P3 — команды начинают исполнять канон)
  и регрессом по 9 корням (P4.1). Принято владельцем: цена трёх прошлых кругов выше этого риска.
- Правила фазы P2 живут в SSOT (RU + EN + линтер), но команды `/task:plan-*` их ещё НЕ исполняют —
  до закрытия P3 гейты держатся дисциплиной исполнителя, а не текстом команды.
- Два чужих плана флота несут WARNING по гейту H2 (VLT-REMED/P5, 2026.07.12-BASE/P5 — themeon):
  приняты владельцем как истинно-положительные (D34/D39); их правка — вне scope.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.
- EN-канон 764 строки (> ориентира 700); P3.6 добавит §13 — при регенерации сокращать прозу
  первым делом (`skiller budget --check-core` — ярус-0 не затронут, растёт ↻ on-trigger).

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: раскатка директив `i18n-keep` на остальные 158 локальных скиллов; миграция §3 Routing /
  `## Обсуждение` живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых
  планах (REGHUB — P4.2); правка `## Phase Handoff` двух чужих планов (вне scope); кросс-репо
  push-уведомление (роадмап); CHANGELOG + docs пакетов (P4.3); **[POSSIBLE-DEFECT]** нестабильный
  порядок вывода диагностик `plan-lint` между прогонами (пре-существующий, на счётчики/`--baseline`
  не влияет).
- open_questions: все девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`
  → незакрытых нет, `open-questions.md` плану не заводится (правило §3).
