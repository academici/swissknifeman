# HANDOFF — 2026-07-14 — after P3.3

**Next:** `/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.4`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — копипаст готовых формулировок, Validation детерминированна (§3 Routing) |
| Context | continue (/clear) — ручной item |
| Суть | `plan-design.md`: эмит канон-Routing с колонкой `Exec`, скелет 16 полей, блок «Реопен фазы» (4 шага, маркер `> УСТАРЕЛ`), `## 7. Contracts`, RAG-enum трёх маркеров, новые пункты DoR |

```
/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.4
```

**Done:** P1, P2 терминальны (P2 — 🟠 Done with deviations, 18/18, скилл `plan-protocol` 2.5.0).
**P3 (3/6):** P3.1 (`4cfc10a`) — `plan-exec.md`: routing-гейт, топология двух коммитов,
коммит-гигиена, status-rule, якорь дерева (180 строк). P3.2 (`0823cb4`) — `plan-close.md`:
enum 8 форм `Next` (D40), две формы заголовка handoff (D30), `Context` из enum'а трёх
значений, снятие маркера `> УСТАРЕЛ`, честный lint закрытия (145 строк).
**P3.3 закрыт** (item-коммит `f4ce8c9`, bookkeeping — этот): `plan-audit.md` **65 → 115 строк**
(на `f4ce8c9`) — (I) **правила остановки** (D44): scope-граница («выполнены ли Deliverables фазы
по её Scope Included»), порог severity (`severity НАХОДКИ ≠ вердикт ФАЗЫ`; `RED` только на
сломанном ПРОДУКТЕ фазы, бухгалтерия → `ATTENTION` + Pending Work), потолок 2 раунда с печатью
номера захода и строкой `AUDIT-CAP:` при ≥3, дефолт ремедиации — follow-up items в СЛЕДУЮЩЕЙ
фазе (реопен — только при дефекте в Deliverable закрытой фазы), конфликт-скан ПЕРЕД
adversarial-проходом; (II) **чеклист канона 2.5.0**: status-rule, топология/гигиена коммита,
честность lint-отчёта (`--baseline`, гейт K=0), якорь дерева, протухший `## Phase Handoff`,
`Last Updated`, развилки, cross-plan notification, RAG-enum трёх маркеров, `Context` из enum'а
(«fresh session» — 0 вхождений); (III) три пункта PROMOTE аудита №4 (**D46**).

**Remaining:**

1. **P3** (3/6): **P3.4 `plan-design` ← Next** (`/task:plan-exec`, sonnet/medium) → P3.5
   `plan-run` (sonnet/medium) → **P3.6 терминальный** (ЗАПУСК ВРУЧНУЮ, opus/high — §13 SSOT +
   EN-канон 2.6.0 + `skiller registry` + сквозная сверка «правило → команда»).
2. P4 (3 items): регресс по флоту (P4.1), закрытие эскалации REGHUB (P4.2, чужой репо Brain),
   доки + CHANGELOG (P4.3).
3. Аудит фазы P3 — уже по НОВЫМ правилам остановки (они в тексте `plan-audit.md` с P3.3):
   один заход, `RED` только на сломанном продукте, бухгалтерия → `ATTENTION` + Pending Work,
   реопена по умолчанию нет.

**Sources of truth:** `plan.md` (Meta **1.4.0**, §2 Execution Rules + carve-out D34, §3 Routing —
**P3.1/P3.3/P3.6 = opus/manual**, §5 D-лог **D1–D46**, `## Обсуждение` — 9 развилок со статусами) ·
`phases/P3.md` (6 items, P3.1–P3.3 🟢) · `phases/P4.md` (скелет) · `findings/P3-command-layer.md`
(матрица дыр §2, потолки объёма §3) · `roadmap/plan-audit-loop.md` (спека класса audit-loop) ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник 2.5.0;
`SKILL.md` — EN-канон; `snippets/`) · `packages/task/lib/task/plan_lint.py` ·
`packages/task/commands/plan-exec.md` (эталон формулировок, 180/180) · `plan-close.md` (145/145) ·
**`plan-audit.md` — правлен (115/115), эталон правил остановки**.

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
  `plan-audit.md` 115/115. P3.5 обязан дописать в launch-block `plan-exec`/`plan-close` строку
  про `/task:plan-run` ⇒ сперва высвободить строки сокращением ПРОЗЫ либо согласовать поднятие
  потолка (`findings/P3-command-layer.md` §3).
- Канон 2.5.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44): механический класс закрыт
  конфликт-сканом. Первое живое применение — эта фаза (P3.1–P3.3 расхождений канона не нашли).
- Две команды (`plan-design`, новая `plan-run`) правил канона ещё НЕ несут — до закрытия P3 их
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
