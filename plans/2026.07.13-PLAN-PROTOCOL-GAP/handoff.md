# HANDOFF — 2026-07-15 — after P3.10

**Next:** «ЗАПУСК ВРУЧНУЮ: opus/high»

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — терминальный item: canon-authoring + семантическая сверка, не механика |
| Context | continue (/clear) — ручной item |
| Суть | Скилл `plan-protocol` 2.6.0 → 2.7.0 (D56): i18n-keep директивы на литералы P3.7–P3.10, регенерация EN-канона, `skiller registry`, повторная сквозная сверка «правило → команда» (→ 0 ✗) |

````
Терминальный item фазы P3 (реопен). Прочитай plans/2026.07.13-PLAN-PROTOCOL-GAP/plan.md
(Context, Execution Rules, §3 Routing, Status Board), handoff.md, phases/P3.md (Phase
Context + item P3.11 целиком), Required Reads item'а — в этом порядке. Затем исполни
Scope Included P3.11 (скилл 2.7.0, регенерация EN-канона, registry, повторная сквозная
сверка матрицы findings/P3-command-layer.md §2, актуализация packages/task/CLAUDE.md при
расхождении) и закрой item по протоколу канона (7 шагов ЗАКРЫТИЯ), включая закрытие фазы
P3 (терминальный item фазы).
````

**Done:** P1 (2/2 🟢), P2 (18/18 — терминальна, `🟠 Done with deviations`), P3 — **9/11**.
**Фаза P3 РЕОПЕНЕНА** (D48, 2026-07-15) после 🔴 RED аудита (`phases/P3.md` `## Audit P3`); реопен-дифф
закоммичен отдельно (`4bf6c1f`). Первая волна: P3.1 (`4cfc10a`) `plan-exec.md`; P3.2 (`0823cb4`)
`plan-close.md`; P3.3 (`f4ce8c9`) `plan-audit.md`; P3.4 (`c95caed`) `plan-design.md`; P3.5 (`b4146eb`, 🟠)
`plan-run.md`; P3.6 (`eea2a9a`) скилл **2.6.0** + EN-канон. Реопен-волна: P3.7 (`e08a7fe`) — Blocker J1
снят (D50); P3.8 (`d9ab955`) — правила, исполнимые собственным линтером (J3/A4/J8 + следы D40/D37/дельта);
P3.9 (`4d9252d`) — `plan-close.md` доведён до канона (A1/A3/status-rule/J5-J6).

**P3.10 закрыт 🟢 (`be3b636`) — обе ✗ сквозной сверки P3.6 сняты.** `plan-exec.md` (180 → **188** строк,
≤ 210) получил блок «Contracts (§11)» внутри п. 7 шаг 2 (bookkeeping): item, бампающий замороженный
контракт, ОБЯЗАН в том же bookkeeping-коммите обновить `Exported` донора и `Consumed` каждого
плана-потребителя того же корня `plans/`; потребитель в другом репо — `open-questions.md` донора +
Open risks `handoff.md`. Формулировка — копия `SKILL.ru.md` §11, diff-сверка без расхождений.
Validation: `grep -c "Contracts"` → 2 (было 0), `grep -c "Exported\|Consumed"` → 2 (было 0, на
`be3b636`); `wc -l` → 188 (≤210, на `be3b636`); `validate.sh` exit 0 (134 теста); `plan-lint
--baseline HEAD` K=0.

**Remaining:** 1 item реопена —

1. **P3.11 ← Next** (opus/high, manual) — терминальный: скилл **2.7.0** (D56), **регенерация
   EN-канона** (`SKILL.md` протух с P3.7–P3.10 — Pending Work), `skiller registry`, повторная
   сквозная сверка «правило → канон» (→ 0 ✗, было 39 ✓ / 2 ✗) + семантическое ревью (D44) + закрытие
   фазы P3 (Phase Status ↔ Status Board, `## Phase Handoff`, снятие маркера `> УСТАРЕЛ`).
2. Затем: `plan-close … P3` (если P3.11 не закрывает фазу сам) → `plan-audit … P3` → фаза **P4**
   (P4.1 регресс по флоту — **10 корней / 30 планов**, D53; P4.2 эскалация REGHUB — чужой репо Brain;
   P4.3 доки + CHANGELOG).

**Sources of truth:** `plan.md` (Meta **1.5.0**, Status 🟡, §2 Execution Rules + carve-out D34, §3
Routing, §5 D-лог **D1–D56**, `## Обсуждение` — 10 развилок) · `phases/P3.md` (11 items;
`## Phase Handoff` помечен `> УСТАРЕЛ — фаза реопенена D48`; append-блок `## Audit P3`) ·
`phases/P4.md` (3 items) · `open-questions.md` (**OQ-1** — «мягкий пункт Validation», Decision
pending) · `findings/P3-reopen-gates-and-fleet.md` (§3 потолки/урок A1, §4 grep-инвентарь правил) ·
`findings/P3-command-layer.md` (матрица правил §2 — обе ✗ сняты P3.9/P3.10, счёт ждёт P3.11) ·
`roadmap/plan-audit-loop.md` · SSOT канона: `packages/skiller/skills/general/plan-protocol/`
(`SKILL.ru.md` — источник, 2.6.0; `SKILL.md` — EN-канон, **протух** до P3.11) ·
`packages/task/lib/task/plan_lint.py` · команды: `plan-exec.md` (**188**/210) · `plan-close.md`
(169/180) · `plan-audit.md` (115/115) · `plan-design.md` (169/185) · `plan-run.md` (28/45).

**Open risks:**
- **EN-канон `SKILL.md` протух** (RU правлен P3.7–P3.10) ⇒ `packages/skiller/scripts/validate.sh`
  красен ровно одной ERROR («протухшие переводы»). Легально по §6/D17 (фазовая когерентность
  производного), снимает терминальный P3.11 — но до него commit-гейт скиллового пакета неполон.
- Канон 2.6.0/2.7.0 не проходил СЕМАНТИЧЕСКОГО ревью свежими глазами (D44) — механический класс
  закрыт конфликт-сканом и сквозной сверкой; семантика — за повторным аудитом P3 и P4.1.
- Полнота гейта литералов (T1) **сужена честно** (D52/J8): динамически собранный шаблон и литерал
  из внешнего файла им не ловятся. Заводя новую форму сверки в `plan_lint.py`, расширяй сборщик —
  иначе класс G3 (слип перевода) воспроизведётся мимо гейта.
- Остаточные 35 WARN `plan-lint` по 6 планам монорепо (на `be3b636`) — вне Scope items P3, чинятся
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
