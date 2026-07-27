# HANDOFF — 2026-07-27 — after P8.6

**P8.6 закрыт 🟢 Done** (`12ff61e1`): `scripts/public-hygiene.py` + `scripts/verify-tag.py` +
два теста (6+6) + шаг `public-hygiene` в job `hygiene` и новый job `release-tag`
(`on: push: tags: ['v*']`) в `.github/workflows/hygiene.yml` + раздел в `docs/develop.md` +
строка `CHANGELOG.md`. **Pending Work (не блокер):** `public-hygiene.py` на текущем дереве даёт
код 1 — единственное нарушение `plans/2026.07.25-ECO-OPT/artifacts/p5-pilot/stage0/install.log`
(артефакт P5.1, вне `Files` P8.6); Validation спеки явно допускает этот исход, удаление файла —
owner-решение (не выполнено этим item'ом). Детали — `phases/P8.md` P8.6 Completion Notes.

**Next:** последний item батча B4b: task:plan-exec 2026.07.25-ECO-OPT P8.7

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | same-session — item |
| Суть | `assert_safe_replace_target` в `core/io.py` + тест — общий пакет, независим от P8.4/P8.5/P8.6 |

```
/task:plan-exec 2026.07.25-ECO-OPT P8.7

РЕЖИМ: исполнение последнего item'а батча B4b по готовому ТЗ (реопена нет)
ВХОД: plans/2026.07.25-ECO-OPT/phases/P8.md — секция P8.7 (Required Reads) · plan.md §3 Routing
СКОУП: `assert_safe_replace_target(path)` в `core/io.py` (+ докстринг с дублями в
       `maind/provider_deploy.py`) + вызов в `atomic_write_text` перед `os.replace` +
       `core/tests/test_io.py` (≥5 тестов: нет файла/обычный файл/симлинк/жёсткая ссылка/
       tmp удалён при отказе) + строка CHANGELOG. Закрытие ПОЛНЫМ протоколом §8.
НЕ ТРОГАТЬ: `maind/provider_deploy.py` (перевод на хелпер — roadmap-кандидат, названный в
       докстринге) · `core/paths.py` (containment — не дублировать) · сигнатуры существующих
       функций (новый параметр только с дефолтом = проверка включена)
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(`0b33116c`+`243254aa`) · **P10.2** (`47d6972d`) · **P10.3** (`ae54d790`) · **P10.4**
(`77bf9d8c`) — **фаза P10 закрыта** (1🟢+3🟠) · **P8.1** · **P8.2** · **P8.3** · **P8.4**
(`5b7cc15e`) · **P8.5** (`d12ccaf7`) · **P8.6** (`12ff61e1`) · **P9.1** · **P2.1** · **P3.2** ·
**P1.2** · **фаза P5 закрыта** (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` ·
P5.4🟢 `253ae4a6` · P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) — **22/44 items закрыто**, 2 фазы
терминальны (P5, P10), 5 фаз в работе (P8 — 4/10, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2).

**Remaining:** 22/44 items. Свободные к запуску: **P8.7** (батч B4b, последний, см. Next) ·
**P8.8 → P8.9** (батч B5) · **P8.10** (solo, `task:plan-run` под `implementation/high`) ·
**P9.3** · **P1.1** (frontier/high, manual) · **P3.1** (нужен оператор). Порядковые условия:
P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2
(условие снято). P8.7 — общий пакет `core/io.py`, независим от P8.4–P8.6 носителем; P8.10
предшественником других items НЕ является.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing; §4 Phase Index — P8 `4/10 🟡`;
§5 D124/D125; §6 Update Log) · `phases/P8.md` (`## Phase Status` — P8.5/P8.6 `🟢`, P8.7 `⬜`;
P8.5/P8.6 Completion Notes) · `research/25-P8.5-routing-cell-form-2026-07-27.md` (диагноз §3
Routing, целевой дизайн P8.10) · `roadmap.md` § B4b/B5 и § P8.10 · машинные гейты
`plans/cross-plan-files.py`, `plans/verify-citations.py`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` не вычитана
(`[UNVERIFIED]`, D110); (3) P10.4 Pending Work — рендерер `.mcp.json` (D106); (4) P10.3 Pending
Work — `README.md:122` битая ссылка (кандидат `/task:fix`); (5) F13/F14 аудита P5 (заход 2) —
за владельцем P5/`maind`; (6) P10.2 Pending Work (b) — `verify-citations-known-exceptions.json`
не решён владельцем; (7) carve-out (б) канона `plan-protocol` не переписан (D118); (8) P8.4 job
`hygiene` не подтверждён реальным CI-run'ом; (9) `plans/2026.07.18-FOREMAN` несёт нелегальную
форму ячейки §3 (`P4.1–P4.2, P4.4`) — правит FOREMAN, не этот план; (10) матрица
`docs/status.md` не сверена с живыми контрактами (D2, отложено); **(11) НОВОЕ: `public-hygiene`
CI-гейт (P8.6) красный на текущем дереве** — `plans/2026.07.25-ECO-OPT/artifacts/p5-pilot/
stage0/install.log` нарушает правило «лог-файл»; удаление/`.gitignore` — owner-решение (P8.6
Pending Work), гейт этим не чинится молча.

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py`; сверка полноты
матрицы `docs/status.md` (D2); удаление/gitignore `install.log` (P8.6 Pending Work, owner).
Долг «перепиннуться на тег Serena» держит `roadmap.md` § «Отложенное» (D110).
