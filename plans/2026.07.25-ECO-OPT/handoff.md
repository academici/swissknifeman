# HANDOFF — 2026-07-28 — after P3.6

**P3.6 закрыт `🟠 Done with deviations`** (item-коммит `aee52e79`). Политика вендоринга: раздел
«Когда переводить скилл в `fork`» + «Цена `fork`» в `packages/skiller/docs/guide/upstream-sync.md`
(две обязательные оси — механическая переприменимость правки × наблюдённый синк-долг, плюс
отсекающая ось дифф-поверхности; числовые пороги операционным критерием запрещены), классификация
всех **56/56** паспортов `upstream.json` (`findings/P3.6-vendoring-policy.md`, метод —
`git log --follow` по каждому: 17 уникальных коммитов на все 56 файлов, все — импорт/рефакторинг,
ни один не является реальным пересинком ⇒ **переводов стратегии: 0**, легальный и ожидаемый
исход). Устранено расхождение корневого `CLAUDE.md` — `strategy` дополнен `replace`.
**Отклонение:** `Validation` несёт 4 команды, 3 зелёные (`validate.sh`/`test.sh`/классификация),
четвёртая (`update-upstreams.sh --check`) красная — крах `IsADirectoryError` на
`voice-ai/voice-ai` (пустой `files[].path`, `skill_dir / "" == skill_dir`), пре-существующий
дефект чужого паспорта, не тронутого диффом P3.6 (правка `update-upstreams.sh`/паспорта — вне
Scope Excluded item'а). Также найден `oss-dev/to-issues` — `fetch failed: HTTP 404` (апстрим
переименовал/убрал файл). Оба зафиксированы в Pending Work `phases/P3.md` P3.6, не починены.
Детали — `phases/P3.md` P3.6 Completion Notes, `findings/P3.6-vendoring-policy.md`.

**Next:** P3 остаётся `🟡 In progress` — свободны **P3.3** (owner-гейт OQ-4/OQ-5,
`Exec=manual`, frontier/high) и **P3.4** (точность `budget.py`, `Exec=plan-exec`,
independent от P3.5/P3.6 по Phase Context). Обе не зависят друг от друга и от P3.6.
Рекомендованный следующий шаг — **P3.4** (`Exec=plan-exec`, дешевле начать без владельца
в контуре); P3.3 ждёт owner-решения OQ-4/OQ-5 плана `2026.07.15-TELEMETRY-OPT`.

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — implementation/medium по Routing §3 |
| Context | continue (/clear) |
| Суть | Исполнить P3.4 (точность `budget.py`: модель листингового бюджета + перекалибровка порогов через `count_tokens`) |

```
/task:plan-exec 2026.07.25-ECO-OPT P3.4
```

**Done:** **40/52 items терминальны** (26 🟢 · 13 🟠 · 1 ⛔). Терминальны фазы **P1** (1/2, 🟢),
**P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠), **P10** (1/4, 🟠), **P11** (6/8, 🟠). Плюс
P2.1 · P3.1 · P3.2 · P3.5 · P3.6 вне терминальных фаз (P3: 1/6 — только P3.1 считается 🟢, P3.2/
P3.5/P3.6 терминальны как 🟠).

**Remaining:** 12 items, все `⬜ Not started`: P2.2–P2.3 · P3.3–P3.4 · P4 (3) · P6 (3) · P7 (3).
Порядковые условия: P2.3 — ПОСЛЕ P6.3 (D93); P3.3 — owner-гейт (`Exec=manual`, frontier/high);
P3.4 — независима от P3.5/P3.6 (другой файл/риск-класс); P6.1 — ПОСЛЕ P9.1 (снято); P4.2 — ПОСЛЕ
P3.2 (снято, P3.2 уже терминален).

**Sources of truth:** `plan.md` (§4 Phase Index — `P3 1/6`; §6 Update Log — запись закрытия P3.6)
· `phases/P3.md` (P3.6 Completion Notes/Pending Work/Known Deviations) ·
`findings/P3.6-vendoring-policy.md` (полная классификация 56/56 + разбор дефекта `voice-ai`) ·
`packages/skiller/docs/guide/upstream-sync.md` § «Когда переводить скилл в `fork`» + «Цена
`fork`» · машинные гейты `plans/verify-citations.py`, `plans/cross-plan-files.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей) плюс новые:
(30) `packages/skiller/scripts/update-upstreams.sh --check` падает `IsADirectoryError` на
`voice-ai/voice-ai/upstream.json` (пустой `files[].path` у всех 5 записей) — пре-существующий
дефект, обнаружен P3.6, не починен (вне Scope: паспорт/скрипт не в `Files` item'а). Останавливает
`--check` на 56-й (последней алфавитно) записи; 55/56 остальных паспортов проверяются штатно.
(31) `oss-dev/to-issues/upstream.json` — апстрим `mattpocock/skills` вернул `HTTP 404` на
`SKILL.md` при `--check`: файл переименован/убран в апстриме, паспорт не обновлён.

**Workarounds / Deferred / Open questions:** без изменений из предыдущего `handoff.md`
(OQ-10 остаётся закрытым вариантом (b)).
