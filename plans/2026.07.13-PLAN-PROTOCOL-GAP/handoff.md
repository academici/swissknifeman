# HANDOFF — 2026-07-14 — after P3.4

**Next:** `/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.5`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — копипаст готовых формулировок, Validation детерминированна (§3 Routing) |
| Context | continue (/clear) — ручной item |
| Суть | `plan-run.md`: новая команда БЕЗ пина модели (Exec=manual без ритуала, D18) — тело ≤ 45 строк |

```
/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.5
```

**Done:** P1, P2 терминальны (P2 — 🟠 Done with deviations, 18/18, скилл `plan-protocol` 2.5.0).
**P3 (4/6):** P3.1 (`4cfc10a`) — `plan-exec.md`: routing-гейт, топология двух коммитов,
коммит-гигиена, status-rule, якорь дерева (180 строк). P3.2 (`0823cb4`) — `plan-close.md`:
enum 8 форм `Next` (D40), две формы заголовка handoff (D30), `Context` из enum'а трёх
значений, снятие маркера `> УСТАРЕЛ`, честный lint закрытия (145 строк). P3.3 (`f4ce8c9`) —
`plan-audit.md`: правила остановки (D44) + чеклист канона 2.5.0 (115 строк).
**P3.4 закрыт** (item-коммит `c95caed`, bookkeeping — этот): `plan-design.md` **148 → 169
строк** — (1) §3 Routing в выжимке схемы — канон-таблица `| Items | Model/effort | Exec |
Почему |` с деривацией Exec (§9); (2) режимы `new`/`from-draft` — явное требование ВСЕХ
16 полей в скелет-item'ах (значение «—» легально, поле — нет); (3) новый блок «Реопен
фазы» в mode `<PLAN-ID> Pn` — 4 шага + маркер `> УСТАРЕЛ — фаза реопенена <D#>` дословно +
форма заголовка handoff `after Pn`; (4) схема — добавлены `## 7. Contracts` и
`## Обсуждение` (опциональные, по заголовку); (5) RAG-enum ТРЁХ маркеров в «Требования к
качеству»; (6) 4 новых пункта DoR-чеклиста. Validation: `grep -c` → 169 (≤185); grep по
7 маркерам → 18 попаданий (≥7); `validate.sh` зелёный (35 pre-existing WARN, 0 новых
ERROR); smoke-план в scratchpad (не коммитился) → `plan-lint` → 0 ошибок, 0 предупреждений.

**Remaining:**

1. **P3** (2/6 осталось): **P3.5 `plan-run` ← Next** (`/task:plan-exec`, sonnet/medium) →
   **P3.6 терминальный** (ЗАПУСК ВРУЧНУЮ, opus/high — §13 SSOT + EN-канон 2.6.0 +
   `skiller registry` + сквозная сверка «правило → команда»).
2. P4 (3 items): регресс по флоту (P4.1), закрытие эскалации REGHUB (P4.2, чужой репо Brain),
   доки + CHANGELOG (P4.3).
3. Аудит фазы P3 — по НОВЫМ правилам остановки (`plan-audit.md` с P3.3): один заход,
   `RED` только на сломанном продукте, бухгалтерия → `ATTENTION` + Pending Work, реопена
   по умолчанию нет.
4. P3.5 обязан вписать в `plan-exec.md`/`plan-close.md` launch-block-строку про новую
   команду `/task:plan-run`, при этом оба тела УЖЕ на потолке объёма (180/180, 145/145) —
   сперва высвободить строки сокращением ПРОЗЫ либо согласовать поднятие потолка
   (`findings/P3-command-layer.md` §3).

**Sources of truth:** `plan.md` (Meta **1.4.0**, §2 Execution Rules + carve-out D34, §3 Routing —
**P3.1/P3.3/P3.6 = opus/manual**, §5 D-лог **D1–D46**, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P3.md` (6 items, P3.1–P3.4 🟢) · `phases/P4.md` (скелет) · `findings/P3-command-layer.md`
(матрица дыр §2, потолки объёма §3) · `roadmap/plan-audit-loop.md` (спека класса audit-loop) ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник 2.5.0;
`SKILL.md` — EN-канон; `snippets/`) · `packages/task/lib/task/plan_lint.py` ·
`packages/task/commands/plan-exec.md` (180/180) · `plan-close.md` (145/145) ·
`plan-audit.md` (115/115) · **`plan-design.md` — правлен (169/185), эталон канон-Routing/DoR**.

**Open risks:**
- **Долги аудита №4 P2 без носителя** (детали — Pending Work P3.3): (а) бухгалтерия плана его не
  отражает — D44 и Update Log говорят «аудит отменён», а блок `## Audit P2 (четвёртый)`
  (`phases/P2.md:3028`, 🔴 RED: 1 Blocker + 6 Major) записан и маршрутизирован владельцем;
  принятый долг (J2/J7/J9/J10/J15) не внесён D#; (б) **J1 (Blocker — ложно-положительный
  WARNING-гейт `plan_lint` на легальной форме `themeon/2026.07.12-BASE` P5) и J3 (шаг 1 реопена
  vs ERROR линтера) items'ов не получили**, хотя маршрутизация их обещала; Phase Context P3
  исключает `plan_lint.py` из scope фазы ⇒ нужен item P3.7 либо фаза P5 — **решение владельца**;
  (в) J5/J6 (механический агрегат Known Deviations в `plan-close`) — P3.2 закрыт без него.
- Три тела команд на потолке объёма: `plan-exec.md` 180/180, `plan-close.md` 145/145,
  `plan-audit.md` 115/115; `plan-design.md` 169/185 (16 строк запаса). P3.5 обязан дописать
  в launch-block `plan-exec`/`plan-close` строку про `/task:plan-run` ⇒ сперва высвободить
  строки сокращением ПРОЗЫ либо согласовать поднятие потолка (`findings/P3-command-layer.md` §3).
- Канон 2.5.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44): механический класс закрыт
  конфликт-сканом. P3.1–P3.4 расхождений канона не нашли.
- Одна команда (`plan-run`, новая) правил канона ещё НЕ несёт — до закрытия P3 её
  гейты держатся дисциплиной исполнителя.
- Два чужих плана флота несут WARNING по гейту H2 (VLT-REMED/P5, 2026.07.12-BASE/P5 — themeon);
  по аудиту №4 один из них (themeon) — **ложно-положительный** (J1), см. долг выше.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: раскатка директив `i18n-keep` на остальные локальные скиллы; миграция §3 Routing /
  `## Обсуждение` живых планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых
  планах (REGHUB — P4.2); правка `## Phase Handoff` чужих планов (вне scope); кросс-репо
  push-уведомление (роадмап); CLI-ступень `plan-lint --conflicts` (роадмап, по накоплению);
  CHANGELOG + docs пакетов (P4.3); **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик
  `plan-lint` между прогонами (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: девять развилок `plan.md` `## Обсуждение` несут `**Статус:** Resolved → D#`;
  НОВЫЙ незакрытый вопрос — дом для J1/J3 (item P3.7 vs фаза P5, решение владельца), см. Open
  risks; трекер `open-questions.md` плану пока не заводится (решение — за `plan-design`).
