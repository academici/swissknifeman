# HANDOFF — 2026-07-28 — after P3.4

**P3.4 закрыт `🟠 Done with deviations`** (item-коммит `8cfa0a3d`). Модель листингового бюджета в
`packages/skiller/lib/skiller/budget.py`: `_measure_skills`/`first_turn_report` теперь капают
каждую запись листинга на 1 536 симв (`description`+`when_to_use`) и держат сумму под потолком
`context_window × listing_fraction` (дефолт 1 000 000 × 0.01 = 10 000 ток, оба — параметры функций,
не константы), вместо прежнего суммирования ВСЕХ описаний активного набора (переучёт, тот же
класс, что был у `/context` до v2.1.196). Отчёт `--first-turn` показывает `raw_tokens`/`tokens`
обоими, когда расходятся. Единица бюджета (токены) сверена с живой эмпирикой
`findings/P3.1-listing-diagnosis.md` (10 000 ток дефолта почти точно совпадает с наблюдённым
`/context` `flexcrm` 9,9k ток) — правок под эту поправку не потребовалось, только явное
подтверждение записью. **Отклонение:** перекалибровка `CHARS_PER_TOKEN_*`/
`FIRST_TURN_TARGET_MAX`/`FIRST_TURN_WARN` через `count_tokens` на `claude-opus-5` (Scope Included
«б») НЕ выполнена — в исполнительной песочнице нет `ANTHROPIC_API_KEY`, `anthropic` SDK, `ant` CLI
(Code Guidance item'а явно предписывает этот путь на недоступности движка: реализовать модель
листинга, перекалибровку — в Pending Work, закрытие `🟠`). Точная команда для следующего захода —
`findings/P3.4-tokenizer-calibration.md` §3. Детали — `phases/P3.md` P3.4 Completion Notes.

**Next:** P3 остаётся `🟡 In progress` — свободна **P3.3** (owner-гейт OQ-4/OQ-5,
`Exec=manual`, frontier/high; ждёт owner-решения плана `2026.07.15-TELEMETRY-OPT`) — единственный
незакрытый item фазы P3. Вне P3 остаются independent-items: P2.2–P2.3 (P2.3 — ПОСЛЕ P6.3, D93) ·
P4 (3) · P6 (3) · P7 (3).

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — Exec=manual, frontier/high по Routing §3 |
| Context | continue (/clear) — ручной item |
| Суть | ЗАПУСК ВРУЧНУЮ: P3.3 — owner-решения OQ-4/OQ-5 плана `2026.07.15-TELEMETRY-OPT` (нужен владелец в контуре) |

```
ЗАПУСК ВРУЧНУЮ: opus/high — /model opus + /effort high + /task:plan-run 2026.07.25-ECO-OPT P3.3
```

**Done:** **41/52 items терминальны** (26 🟢 · 14 🟠 · 1 ⛔). Терминальны фазы **P1** (1/2, 🟢),
**P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). Плюс
P2.1 · P3.1 · P3.2 · P3.4 · P3.5 · P3.6 вне терминальных фаз (P3: 1/6 — только P3.1 считается 🟢,
P3.2/P3.4/P3.5/P3.6 терминальны как 🟠).

**Remaining:** 11 items, все `⬜ Not started`: P2.2–P2.3 · P3.3 · P4 (3) · P6 (3) · P7 (3).
Порядковые условия: P2.3 — ПОСЛЕ P6.3 (D93); P3.3 — owner-гейт (`Exec=manual`, frontier/high);
P6.1 — ПОСЛЕ P9.1 (снято); P4.2 — ПОСЛЕ P3.2 (снято, P3.2 уже терминален).

**Sources of truth:** `plan.md` (§4 Phase Index — `P3 1/6`; §6 Update Log — запись закрытия P3.4)
· `phases/P3.md` (P3.4 Completion Notes/Pending Work/Known Deviations) ·
`findings/P3.4-tokenizer-calibration.md` (модель листинга + сверка с эмпирикой P3.1 + точная
команда перекалибровки для следующего захода) · `packages/skiller/lib/skiller/budget.py` ·
машинные гейты `plans/verify-citations.py`, `plans/cross-plan-files.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей) плюс новый:
(32) `packages/skiller/lib/skiller/budget.py` — `FIRST_TURN_TARGET_MAX`/`FIRST_TURN_WARN`
(7 000/10 000 ток) и `CHARS_PER_TOKEN_CYR`/`CHARS_PER_TOKEN_LAT` (2.9/3.4) остаются на прежней
калибровке (RAG-оценка, не `count_tokens`) — следующий заход с сетевым доступом/креденшелами
обязан прогнать команду из `findings/P3.4-tokenizer-calibration.md` §3 перед доверием абсолютным
числам порогов (доля контекстного окна, которую они выражают, не переизмерена).

**Workarounds / Deferred / Open questions:** без изменений из предыдущего `handoff.md`
(OQ-10 остаётся закрытым вариантом (b)).
