# HANDOFF — 2026-07-27 — after P8.8

**P8.8 закрыт 🟢 Done** (`4ee3ba6d`): три детерминированных гейта в `validate.sh` (секции
1c/5c/5d) — (1) CORE-девятка обязана нести активационную (ERROR+рэтчет
`scripts/skill-sections-burndown.txt`, 3 стартовые строки) и ссылочную (ERROR без исключений)
секции тела; (2) тонкие проекции `.claude|.agents/skills/*/SKILL.md` не дублируют канон по
парам из `publication-lock.json` (0 находок, максимум тела — 4 строки); (3) `evals.json` ⇒
обязателен `pressure.json` с ≥1 сценарием (ERROR, долг 0), новое поле `triggers[]` — форма в
`eval.py::validate_pressure`, непокрытый `should_trigger` даёт WARN (12 WARN на живом дереве).
Пять негативных прогонов на копии пакета — все дали `exit 1` с ожидаемым текстом ((e) —
изолированная проверка python-логики, полный прогон в synthetic tmpdir маскировался
посторонней ERROR `marketplace.json missing` — артефакт неполного репро, не поведения
проверки). `validate.sh` — `230 skills checked — all valid (98 warning(s))`; `test.sh` — `482
tests OK` (+1 новый); `docs-impact.py --staged` — OK.

**Next:** P8.9: `skiller eval` — детерминизм отчёта (последний item батча B5, общий `eval.py`).

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | same-session — item |
| Суть | Инжектируемые часы + `Fraction` вместо float + `provenance` + `schema_version: 2` в `quality/eval.py`; читает P3.3 AGENT-RELIABILITY `schema_version: "system-bank-benchmark/v1"` (не заводить второй словарь версий) |

```
/task:plan-exec 2026.07.25-ECO-OPT P8.9
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(`0b33116c`+`243254aa`) · **P10.2** (`47d6972d`) · **P10.3** (`ae54d790`) · **P10.4**
(`77bf9d8c`) — **фаза P10 закрыта** (1🟢+3🟠) · **P8.1** · **P8.2** · **P8.3** · **P8.4**
(`5b7cc15e`) · **P8.5** (`d12ccaf7`) · **P8.6** (`12ff61e1`) · **P8.7** (`fa1ee8bf`) — **батч
B4b закрыт** · **P8.8** (`4ee3ba6d`) · **P9.1** · **P2.1** · **P3.2** · **P1.2** · **фаза P5
закрыта** (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` · P5.3🟠 `930ad0ac` · P5.4🟢 `253ae4a6` ·
P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) — **24/44 items закрыто**, 2 фазы терминальны (P5, P10),
5 фаз в работе (P8 — 6/10, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2).

**Remaining:** 20/44 items. Свободные к запуску: **P8.9** (см. Next, ПОСЛЕДНИЙ item батча B5)
· **P8.10** (solo, `task:plan-run` под `implementation/high`) · **P9.3** · **P1.1**
(frontier/high, manual) · **P3.1** (нужен оператор). Порядковые условия: P2.3 — ПОСЛЕ
P8.1/P8.2/P8.3 и P6.3 (D93); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2 (условие
снято). P8.10 предшественником других items НЕ является.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing; §4 Phase Index — P8 `6/10 🟡`;
§5 D124/D125; §6 Update Log) · `phases/P8.md` (`## Phase Status` — P8.4–P8.8 `🟢`, P8.9/P8.10
`⬜`; P8.5–P8.8 Completion Notes) · `research/25-P8.5-routing-cell-form-2026-07-27.md`
(диагноз §3 Routing, целевой дизайн P8.10) · `roadmap.md` § B5 и § P8.10 · машинные гейты
`plans/cross-plan-files.py`, `plans/verify-citations.py`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а, кандидат на отдельный фикс-item за владельцем
`maind`; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` не вычитана (`[UNVERIFIED]`, D110); (3)
P10.4 Pending Work — рендерер `.mcp.json` (D106); (4) P10.3 Pending Work — `README.md:122`
битая ссылка (кандидат `/task:fix`); (5) F13/F14 аудита P5 (заход 2) — за владельцем
P5/`maind`; (6) P10.2 Pending Work (b) — `verify-citations-known-exceptions.json` не решён
владельцем; (7) carve-out (б) канона `plan-protocol` не переписан (D118); (8) P8.4 job
`hygiene` не подтверждён реальным CI-run'ом; (9) `plans/2026.07.18-FOREMAN` несёт нелегальную
форму ячейки §3 — правит FOREMAN, не этот план; (10) матрица `docs/status.md` не сверена с
живыми контрактами (D2, отложено); (11) `public-hygiene` CI-гейт (P8.6) красный на текущем
дереве — `plans/2026.07.25-ECO-OPT/artifacts/p5-pilot/stage0/install.log` нарушает правило
«лог-файл»; удаление/`.gitignore` — owner-решение (P8.6 Pending Work); (12) три CORE-скилла
(`general/context-economy`, `general/compact-responses`, `research/query-craft`) остаются без
активационной секции — унаследованный долг в `scripts/skill-sections-burndown.txt`, правка
тел — вне scope P8.8 (не этот item).

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py`; сверка полноты
матрицы `docs/status.md` (D2); удаление/gitignore `install.log` (P8.6 Pending Work, owner);
перевод `maind/provider_deploy.py` на `assert_safe_replace_target` (P8.7 Deliverables,
roadmap-кандидат); заполнение `triggers[]` у четырёх скиллов с `evals/` (P8.8, WARNING —
заполняется при их следующей правке). Долг «перепиннуться на тег Serena» держит `roadmap.md`
§ «Отложенное» (D110).
