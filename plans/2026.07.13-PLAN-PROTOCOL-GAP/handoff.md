# HANDOFF — 2026-07-15 — after P3

**Next:** ЗАПУСК ВРУЧНУЮ: `opus/high` — item P3.7 (`Exec = manual`, §3 Routing)

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — переформулировка предиката гейта, бьющего по флоту |
| Context | continue (/clear) — ручной item |
| Суть | J1 (Blocker): гейт «Phase Handoff протух» ловит СЛОВО, а не субъект утверждения — предикат якорится на первую непустую строку + отрицание; 2 анти-регресс-теста на живых формах флота |

````
Исполни item P3.7 мастер-плана `plans/2026.07.13-PLAN-PROTOCOL-GAP` (репо swissknifeman,
/home/vostrikov/projects/packages/swissknifeman) — строго по ТЗ, с обязательным закрытием item'а
и перезаписью handoff.

Читай РОВНО в этом порядке, ничего сверх: (1) plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md —
§1 Context, §2 Execution Rules, §3 Routing, §4 Status Board, D48/D50 в §5; (2) этот handoff.md;
(3) plans/2026.07.13-PLAN-PROTOCOL-GAP/phases/P3.md — Phase Context + item P3.7 целиком;
(4) файлы из Required Reads item'а в указанном порядке.

Протокол исполнения — packages/task/commands/plan-exec.md (пп. 3–8: топология ДВУХ коммитов,
коммит-гигиена по явным путям, status-rule, якорь дерева для чисел, plan-lint --baseline HEAD
ПОСЛЕ перезаписи handoff, гейт K = 0). Routing-гейт п. 2 не применяй: item предписан
`opus/high · Exec = manual`, ты и есть ручной запуск под предписанной моделью — подтверди это
строкой в отчёте.

Суть P3.7: предикат WARNING-гейта «Phase Handoff протух» (plan_lint.py) переформулировать так,
чтобы он судил по ПЕРВОЙ непустой строке блока и не срабатывал при отрицании («НЕ закрыта»);
2 анти-регресс-теста на живых формах флота (themeon — молчит, vaulter — WARN); след семантики
гейта — в SKILL.ru.md §3. Гейт остаётся WARNING. Расширять регион до EOF ЗАПРЕЩЕНО (D39).
IF-THEN: новое срабатывание где-либо во флоте ИЛИ погашенный vaulter → СТОП + эскалация, не
подгонка порога.
````

**Done:** P1 (2/2 🟢), P2 (18/18: 17 🟢 + 1 🟠 — терминальна, `🟠 Done with deviations`).
**Фаза P3 РЕОПЕНЕНА** (D48, 2026-07-15): была закрыта 🟠 (6/6), получила **🔴 RED** аудита
(`phases/P3.md` `## Audit P3`). Шесть закрытых items остаются в силе: P3.1 (`4cfc10a`)
`plan-exec.md` — routing-гейт, топология двух коммитов, коммит-гигиена, status-rule, якорь дерева;
P3.2 (`0823cb4`) `plan-close.md` — enum 8 форм `Next`, две формы заголовка handoff, `Context` из
enum'а трёх; P3.3 (`f4ce8c9`) `plan-audit.md` — правила остановки (D44) + чеклист канона; P3.4
(`c95caed`) `plan-design.md` — канон-Routing, скелет 16 полей, реопен-протокол; P3.5 (`b4146eb`, 🟠)
`plan-run.md` — команда без пина модели (D18/D43); P3.6 (`eea2a9a`) — скилл **2.6.0** (§13 + блок §9),
EN-канон регенерирован, сквозная сверка «правило → команда»: **39 ✓ / 2 ✗**.

**Что нашёл аудит (вход реопена):** **A1** (Major) — `plan-close.md` при сжатии под потолок 145
потерял слово «плана» = единственный АДРЕСАТ секции `## 6. Update Log`; воспроизвелось на первом
живом прогоне: закрытие фазы P3 записало Update Log **в `handoff.md`** (шаблон такой секции не имеет),
а строки в `plan.md` не появилось. **A2** (Major) — `## Phase Handoff` P3 утверждал «расхождений не
найдено» при фактических 2 ✗ (снят маркером `> УСТАРЕЛ`). **A3** (Minor) — режим `Pn` `plan-close`
не содержит шага коммита. **A4** (Nit) — DoR-гейт грепает append-блок `## Audit Pn`. Плюс долги
аудита №4 P2 без дома: **J1** (Blocker — гейт бьёт по легальной форме themeon), J3, J8, J11, J12/J13.

**Remaining:** 5 items реопена, порядок обязателен —

1. **P3.7 ← Next** (opus/high, manual) — J1 (Blocker): предикат гейта. Идёт ПЕРВЫМ: ложный WARNING
   уже роздан флоту скиллом 2.6.0.
2. **P3.8** (opus/high, manual) — правила, невыполнимые собственным линтером: J3 (шаг 1 реопена →
   Status Board как единственный носитель статуса фазы), A4 (регион грепа), J8 (полнота T1),
   J11 (следы D40/D37 в каноне), J13 (дельта вместо абсолютов по чужим корням).
3. **P3.9** (opus/high, manual) — `plan-close.md` ≤180: адресат Update Log (A1), шаг коммита (A3),
   status-rule (6 триггеров дословно), механический агрегат Known Deviations (J5/J6).
4. **P3.10** (sonnet/medium, `/task:plan-exec`) — `plan-exec.md` ≤210: обязанность §11 Contracts.
5. **P3.11** (opus/high, manual) — терминальный: скилл **2.7.0**, регенерация EN, `skiller registry`,
   повторная сквозная сверка (41 проверка → 0 ✗).
6. Затем: `plan-close … P3` → `plan-audit … P3` → фаза **P4** (3 items: регресс по флоту P4.1 —
   ТЗ синхронизировано на **10 корней / 30 планов**, D53; эскалация REGHUB P4.2 — чужой репо Brain;
   доки + CHANGELOG P4.3).

**Sources of truth:** `plan.md` (Meta **1.5.0**, Status 🟡, §2 Execution Rules + carve-out D34, §3
Routing — 5 новых строк, §5 D-лог **D1–D56**, `## Обсуждение` — 10 развилок) · `phases/P3.md`
(11 items; `## Phase Handoff` помечен `> УСТАРЕЛ — фаза реопенена D48`; append-блок `## Audit P3`) ·
`phases/P4.md` (3 items) · `open-questions.md` (**OQ-1** — «мягкий пункт Validation», Decision
pending) · `findings/P3-reopen-gates-and-fleet.md` (обе формы гейта J1 + инвентарь флота + потолки) ·
`findings/P3-command-layer.md` (матрица правил §2, потолки §3) · `roadmap/plan-audit-loop.md` ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник 2.6.0, 844
строки; `SKILL.md` — EN-канон, 781) · `packages/task/lib/task/plan_lint.py` · команды: `plan-exec.md`
(180 → потолок **210**) · `plan-close.md` (145 → потолок **180**) · `plan-audit.md` (115/115) ·
`plan-design.md` (169/185) · `plan-run.md` (28/45).

**Open risks:**
- **Закрытие фазы P3 живёт ТОЛЬКО в рабочем дереве** (A3): `plan.md`/`phases/P3.md`/`handoff.md`
  modified, bookkeeping-коммита нет — режим `Pn` команды `plan-close` шага коммита не содержит.
  Реопен-дифф (эта сессия) коммитится отдельно ДО первого item'а (прецедент P2.5/P2.9: дифф
  `plan-design` отделяется собственным коммитом).
- **Гейт приёмки §2 мерится ПАРНЫМ прогоном, не абсолютами** (D53): 10 корней / 30 живых планов
  (`findings/P3-reopen-gates-and-fleet.md` §2). Прежние «9 корней / 26 планов» ложны — ТЗ P4.1
  синхронизировано.
- **Снятие ложного WARNING themeon уменьшит счётчик флота на 1** — это исправление, а не «новый
  WARNING»; истинный (vaulter/VLT-REMED) обязан сохраниться. Проверяется в Validation P3.7.
- Канон 2.6.0/2.7.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44) — механический класс
  закрыт конфликт-сканом и сквозной сверкой; семантика — за аудитом P3 (повторным) и P4.1.
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: **принятый долг аудита №4 P2** (D54 — J2/J7/J9/J10/J15/J17/J18: bookkeeping закрытых
  items задним числом НЕ переписывается, источник правды — append-блоки `## Audit P2*`); раскатка
  директив `i18n-keep` на остальные локальные скиллы; миграция §3 Routing / `## Обсуждение` живых
  планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых планах (REGHUB — P4.2);
  правка `## Phase Handoff` чужих планов (вне scope); кросс-репо push-уведомление (роадмап);
  CLI-ступень `plan-lint --conflicts` (роадмап); CHANGELOG + docs пакетов (P4.3);
  **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик `plan-lint` между прогонами
  (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: **OQ-1** (`open-questions.md`) — «мягкий пункт Validation»: узаконить в §6 или
  запретить (J16, `## Обсуждение` п. 10, `Decision pending`); дедлайн — до закрытия P3 (терминальный
  item P3.11 правит §6). Остальные 9 развилок `## Обсуждение` несут `**Статус:** Resolved → D#`.
