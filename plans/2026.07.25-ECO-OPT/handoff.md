# HANDOFF — 2026-07-27 — after P8.5

**P8.5 закрыт 🟢 Done** (`d12ccaf7`): `docs/status.md` (21 строка матрицы, 5 пакетов + `core` +
корневой роутер, зрелость — словарь `plan-protocol` § Statuses) + `scripts/status-check.py` +
`scripts/test-status-check.py` (6 тестов) + шаг `status-check` в CI-job `hygiene` + запись в nav
VitePress + строка `CHANGELOG.md`. Validation: 6/6 тестов OK, `status-check` код 0 («21 строк(и),
0 ошибок»), `docs-impact.py --staged` код 0. Детали — `phases/P8.md` P8.5 Completion Notes.

**Next:** exec-items батча B4b (продолжение): task:plan-exec 2026.07.25-ECO-OPT P8.6 P8.7

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | same-session — item |
| Суть | Батч **B4b** остатком: CI-гигиена P8.6 (дописывает `.github/workflows/hygiene.yml`, читает уже готовый job `hygiene` после P8.5) → `core/io.py` P8.7 |

```
/task:plan-exec 2026.07.25-ECO-OPT P8.6 P8.7

РЕЖИМ: исполнение двух items батча B4b по готовым ТЗ (реопена нет, ТЗ этим заходом не правились)
ВХОД: plans/2026.07.25-ECO-OPT/phases/P8.md — секции P8.6, P8.7 (Required Reads каждого) ·
      plans/2026.07.25-ECO-OPT/roadmap.md § B4b · plan.md §3 Routing
СКОУП: 1) P8.6 — `scripts/public-hygiene.py` и `scripts/verify-tag.py` + два теста + шаг в
       `hygiene` и job `release-tag` + раздел в `docs/develop.md` 2) P8.7 —
       `assert_safe_replace_target` в `core/io.py` + тест 3) каждый item закрывается ПОЛНЫМ
       протоколом §8 (item-коммит по своим `Files` → бухгалтерия → handoff → plan-lint с
       атрибуцией K) 4) P8.4/P8.5 — терминальны, повторный проход запрещён
НЕ ТРОГАТЬ: `packages/task/lib/task/task_contract.py` и канон `plan-protocol` — это скоуп P8.10,
       отдельный запуск · §3 Routing плана · ТЗ и статусы прочих items
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(`0b33116c`+`243254aa`) · **P10.2** (`47d6972d`) · **P10.3** (`ae54d790`) · **P10.4**
(`77bf9d8c`) — **фаза P10 закрыта** (1🟢+3🟠) · **P8.1** · **P8.2** · **P8.3** · **P8.4**
(`5b7cc15e`) · **P8.5** (`d12ccaf7`) · **P9.1** · **P2.1** · **P3.2** · **P1.2** · **фаза P5
закрыта** (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` · P5.4🟢 `253ae4a6` · P5.5🟢
`88f0c7eb` · P5.6🟢 `9cafcac1`) — **21/44 items закрыто**, 2 фазы терминальны (P5, P10), 5 фаз в
работе (P8 — 3/10, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2).

**Remaining:** 23/44 items. Свободные к запуску: **P8.6 → P8.7** (батч B4b, см. Next) ·
**P8.8 → P8.9** (батч B5) · **P8.10** (solo, `task:plan-run` под `implementation/high`) ·
**P9.3** · **P1.1** (frontier/high, manual) · **P3.1** (нужен оператор). Порядковые условия:
P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2
(условие снято). Внутри P8: P8.6 → P8.7 не связаны носителем (P8.7 правит `core/io.py`,
независим), но батч B4b исполняется последовательно по ТЗ; P8.10 предшественником других
items НЕ является.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing — построчные ряды; §4 Phase
Index — P8 `3/10 🟡`; §5 D124/D125; §6 Update Log) · `phases/P8.md` (`## Phase Status` — P8.5
`🟢`, P8.6/P8.7 `⬜`; P8.5 Completion Notes) · `research/25-P8.5-routing-cell-form-2026-07-27.md`
(диагноз, замер, целевой дизайн P8.10) · `roadmap.md` § B4b/B5 и § P8.10 · машинные гейты
`plans/cross-plan-files.py`, `plans/verify-citations.py`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — оба
пред-существующие, долг вне `Files` любого закрытого item'а, кандидат на отдельный фикс-item за
владельцем `maind`; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` планом не вычитана
(`[UNVERIFIED]`, D110 Consequences); (3) P10.4 Pending Work — починка системного расхождения
рендерера `.mcp.json` (роадмап-кандидат, D106); (4) P10.3 Pending Work — `README.md:122`
ссылается на несуществующий `roadmap/self-learning-memory.md` (кандидат `/task:fix`);
(5) F13/F14 из аудита P5 (заход 2) — вне carve-out закрытия, Pending Work за владельцем
P5/`packages/maind`; (6) P10.2 Pending Work (b) — владелец не решил про
`plans/verify-citations-known-exceptions.json`; (7) carve-out (б) канона `plan-protocol`
(SKILL.ru.md §6) текстом ещё не переписан (D118); (8) P8.4 job `hygiene` не подтверждён реальным
CI-run'ом — доказательство локальное построчное, первый живой PR/push даст подтверждение;
(9) чужой живой план `plans/2026.07.18-FOREMAN` несёт ту же нелегальную форму ячейки
(`P4.1–P4.2, P4.4`) — его 3 items не строят Task Contract; починка — за FOREMAN, не этим планом
(P8.10 сделает отказ самообслуживаемым); (10) матрица `docs/status.md` (P8.5) НЕ сверена с
живыми контрактами «команда есть, строки нет» — приём D2, отложен D41, названо на самой странице.

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в строках §6 Update Log — плановая дисциплина, не фазовая); машинный lint
формы §3 в `plan_lint.py` (канон фиксирует «`plan-lint` не парсит секцию 3»); сверка полноты
матрицы `docs/status.md` со списком реальных возможностей (D2, кандидат follow-up). Долг
«перепиннуться на тег, когда апстрим выпустит релиз со схемой `language_servers`» держит
`roadmap.md` § «Отложенное» (срок непроверяем, в item не превращается — D110).
