# HANDOFF — 2026-07-15 — after P3.9

**Next:** `/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.10` (`Exec = plan-exec`, §3 Routing)

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — дописать ОДИН блок по готовой формулировке канона §11 |
| Context | continue (/clear) — ручной item |
| Суть | `plan-exec.md` ≤ 210 строк: обязанность §11 Contracts (item, бампающий frozen-контракт, обновляет `Exported` донора + `Consumed` потребителей того же корня; чужой репо — `open-questions.md` + Open risks) |

````
/task:plan-exec 2026.07.13-PLAN-PROTOCOL-GAP P3.10
````

**Done:** P1 (2/2 🟢), P2 (18/18 — терминальна, `🟠 Done with deviations`), P3 — **8/11**.
**Фаза P3 РЕОПЕНЕНА** (D48, 2026-07-15) после 🔴 RED аудита (`phases/P3.md` `## Audit P3`); реопен-дифф
закоммичен отдельно (`4bf6c1f`). Первая волна: P3.1 (`4cfc10a`) `plan-exec.md`; P3.2 (`0823cb4`)
`plan-close.md`; P3.3 (`f4ce8c9`) `plan-audit.md`; P3.4 (`c95caed`) `plan-design.md`; P3.5 (`b4146eb`, 🟠)
`plan-run.md`; P3.6 (`eea2a9a`) скилл **2.6.0** + EN-канон. Реопен-волна: P3.7 (`e08a7fe`) — Blocker J1
снят (D50); P3.8 (`d9ab955`) — правила, исполнимые собственным линтером (J3/A4/J8 + следы D40/D37/дельта).

**P3.9 закрыт 🟢 (`4d9252d`) — обе ✗ сквозной сверки в части `plan-close` сняты.** `plan-close.md`
доведён до канона пятью правилами под поднятым потолком **169 ≤ 180** (D49): (A1) режим `Pn` шаг 4
называет АДРЕСАТ `## 6. Update Log` — **плана (`plan.md`)**, не handoff (который перезаписывается
целиком) + свип адресатов обоих режимов (второй Update Log; `## Phase Status`→`phases/Pn.md`,
`## 4.`→`plan.md`); (A3) режим `Pn` получил финальный шаг 7 «Коммит закрытия фазы — ОДИН»
(`git add plans/<ID>` + `docs(plan): фаза Pn закрыта`), lint остаётся шагом 6 ПЕРЕД коммитом;
(status-rule) режим `Pn.m` шаг 4 несёт предикат material/process, **6 триггеров дословно** как
`plan-exec.md:107-115` (diff-сверка IDENTICAL, единственное отличие — переадресация `carve-out
выше`→`§8`); (J5/J6) режим `Pn` шаг 3 — агрегат Known Deviations перечислением непустых полей items,
запрет утверждать сверх полей (класс B1). Validation 7/7 (детали — P3.9 Completion Notes): `validate.sh`
exit 0, `plan-lint --baseline HEAD` K=0.

**Remaining:** 2 items реопена, порядок обязателен —

1. **P3.10 ← Next** (sonnet/medium, `/task:plan-exec`) — `plan-exec.md` ≤ 210: обязанность §11 Contracts
   (вторая ✗ сквозной сверки — `grep -c "Contracts\|Exported" plan-exec.md` → 0).
2. **P3.11** (opus/high, manual) — терминальный: скилл **2.7.0** (D56), **регенерация EN-канона**
   (`SKILL.md` протух с P3.7/P3.8 — Pending Work), `skiller registry`, повторная сквозная сверка
   «правило → команда» (→ 0 ✗) + семантическое ревью канона (D44).
3. Затем: `plan-close … P3` → `plan-audit … P3` → фаза **P4** (P4.1 регресс по флоту — **10 корней /
   30 планов**, D53; P4.2 эскалация REGHUB — чужой репо Brain; P4.3 доки + CHANGELOG).

**Sources of truth:** `plan.md` (Meta **1.5.0**, Status 🟡, §2 Execution Rules + carve-out D34, §3
Routing, §5 D-лог **D1–D56**, `## Обсуждение` — 10 развилок) · `phases/P3.md` (11 items;
`## Phase Handoff` помечен `> УСТАРЕЛ — фаза реопенена D48`; append-блок `## Audit P3`) ·
`phases/P4.md` (3 items) · `open-questions.md` (**OQ-1** — «мягкий пункт Validation», Decision
pending) · `findings/P3-reopen-gates-and-fleet.md` (§3 потолки/урок A1, §4 grep-инвентарь правил) ·
`findings/P3-command-layer.md` (матрица правил §2 — две ✗, потолки §3) · `roadmap/plan-audit-loop.md` ·
SSOT канона: `packages/skiller/skills/general/plan-protocol/` (`SKILL.ru.md` — источник, 2.6.0;
`SKILL.md` — EN-канон, **протух** до P3.11) · `packages/task/lib/task/plan_lint.py` · команды:
`plan-exec.md` (180/потолок **210** — растёт в P3.10) · `plan-close.md` (**169**/180) ·
`plan-audit.md` (115/115) · `plan-design.md` (169/185) · `plan-run.md` (28/45).

**Open risks:**
- **EN-канон `SKILL.md` протух** (RU правлен P3.7 и P3.8) ⇒ `packages/skiller/scripts/validate.sh`
  красен ровно одной ERROR («протухшие переводы»). Легально по §6/D17 (фазовая когерентность
  производного), снимает терминальный P3.11 — но до него commit-гейт скиллового пакета неполон.
- Канон 2.6.0/2.7.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44) — механический класс
  закрыт конфликт-сканом и сквозной сверкой; семантика — за повторным аудитом P3 и P4.1.
- Полнота гейта литералов (T1) **сужена честно** (D52/J8): динамически собранный шаблон и литерал
  из внешнего файла им не ловятся. Заводя новую форму сверки в `plan_lint.py`, расширяй сборщик —
  иначе класс G3 (слип перевода) воспроизведётся мимо гейта.
- Остаточные 35 WARN `plan-lint` по 6 планам монорепо (на `4d9252d`) — вне Scope items P3, чинятся
  не здесь (записи Update Log > 300 символов у старых планов и т. п.).
- P4.2 правит ЧУЖОЙ репозиторий (Brain-vault, план REGHUB) — коммит там отдельный.

**Workarounds/Deferred/Open questions:**
- workarounds: нет.
- deferred: **принятый долг аудита №4 P2** (D54 — J2/J7/J9/J10/J15/J17/J18: bookkeeping закрытых
  items задним числом НЕ переписывается, источник правды — append-блоки `## Audit P2*`); раскатка
  директив `i18n-keep` на остальные локальные скиллы; миграция §3 Routing / `## Обсуждение` живых
  планов на канон-форму (back-compat); заполнение `## 7. Contracts` в живых планах (REGHUB — P4.2);
  правка `## Phase Handoff` чужих планов (вне scope; WARNING vaulter корректен и остаётся);
  кросс-репо push-уведомление (роадмап); CLI-ступень `plan-lint --conflicts` (роадмап);
  CHANGELOG + docs пакетов (P4.3); **[POSSIBLE-DEFECT]** нестабильный порядок вывода диагностик
  `plan-lint` между прогонами (пре-существующий, на счётчики/`--baseline` не влияет).
- open_questions: **OQ-1** (`open-questions.md`) — «мягкий пункт Validation»: узаконить в §6 или
  запретить (J16, `## Обсуждение` п. 10, `Decision pending`); дедлайн — до закрытия P3 (терминальный
  item P3.11 правит §6). Остальные 9 развилок `## Обсуждение` несут `**Статус:** Resolved → D#`.
