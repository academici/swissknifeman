# HANDOFF — 2026-07-27 — after P8.9

**P8.9 закрыт 🟢 Done** (`980ce398`) — **батч B5 (P8.8→P8.9) полностью закрыт.** `benchmark.json`
детерминирован: (1) инжектируемые часы (`clock_ns`/`now_iso` в `run_case`/`run_suite`/
`cmd_eval`, дефолт — реальное время, CLI без флагов не изменился); (2) метрики через
`fractions.Fraction` (точное среднее; stddev — √ дисперсии целочисленно, `math.isqrt`, БЕЗ
`math.sqrt`), строковый рендер ОДНОЙ функцией (`_fmt_frac`/`_stringify_fractions`) РОВНО один
раз перед записью — внутренние вычисления/старые тесты остались на Fraction без правки (`Fraction
== float` для точных отношений); (3) честный `provenance` (`llm`/`network` всегда `true` в этой
ветке — она недостижима без реального вызова `claude`, включая фейковый через
`SKM_CLAUDE_BIN`; `clock: "injected"|"wall"`; `baseline`); (4) `schema_version:
"skill-benchmark/v2"` — намеспейсовано против соседнего P3.3-контракта `system-bank-benchmark/v1`
в том же модуле; D97 подтверждён предстартовым чтением P3.3 (терминален, `### Consumed` не
несёт строки про `benchmark.json` ⇒ контракт остаётся ВНУТРЕННИМ, уведомление не требуется).
Греп внешних читателей `benchmark.json` — нет ни одного вне пакета. `test.sh` — `491 tests OK`
(+9 новых, включая 6 online через `SKM_CLAUDE_BIN`-фейк `claude`); `ruff` на изменённых файлах —
чисто (пред-существующая находка B904 в непричастном `publication.py` — не регрессия);
`validate.sh` — `230 skills checked — all valid`; ручная демонстрация (`skiller eval
general/anti-drift` офлайн, `git status --short` пуст до/после) — no-op подтверждён;
`docs-impact.py --staged` — OK.

**Next:** свободные к запуску (без порядковых условий друг относительно друга): **P8.10**
(solo, `task:plan-run` под `implementation/high` — `Exec=manual`, деривация §9) · **P9.3**
(frontier/high, manual) · **P1.1** (frontier/high, manual) · **P3.1** (implementation/medium,
manual — нужен оператор для `/doctor`/`/context`). Рекомендация — `P8.10`, т.к. это
единственный `plan-exec`-достижимый (через `plan-run`) item без owner-гейта; формально решает
владелец.

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P8.10: закрытый набор форм ячейки `Items` §3 Routing + диагностичный отказ компилятора `task_contract._find_routing_row` |

```
ЗАПУСК ВРУЧНУЮ: implementation/high — /model <M> + /effort <E> + /task:plan-run 2026.07.25-ECO-OPT P8.10
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1**
(`0b33116c`+`243254aa`) · **P10.2** (`47d6972d`) · **P10.3** (`ae54d790`) · **P10.4**
(`77bf9d8c`) — **фаза P10 закрыта** (1🟢+3🟠) · **P8.1** · **P8.2** · **P8.3** · **P8.4**
(`5b7cc15e`) · **P8.5** (`d12ccaf7`) · **P8.6** (`12ff61e1`) · **P8.7** (`fa1ee8bf`) — **батч
B4b закрыт** · **P8.8** (`4ee3ba6d`) · **P8.9** (`980ce398`) — **батч B5 закрыт** · **P9.1** ·
**P2.1** · **P3.2** · **P1.2** · **фаза P5 закрыта** (P5.1🟢 `629cf09d` · P5.2🟢 `1844ab29` ·
P5.3🟠 `930ad0ac` · P5.4🟢 `253ae4a6` · P5.5🟢 `88f0c7eb` · P5.6🟢 `9cafcac1`) — **25/44 items
закрыто**, 2 фазы терминальны (P5, P10), 5 фаз в работе (P8 — 7/10, P9 — 1/4, P2 — 1/3, P3 —
1/6, P1 — 1/2).

**Remaining:** 19/44 items. Свободные к запуску — см. Next. Порядковые условия: P2.3 — ПОСЛЕ
P8.1/P8.2/P8.3 и P6.3 (D93); P6.1 — ПОСЛЕ P9.1 (условие снято); P4.2 — ПОСЛЕ P3.2 (условие
снято). P8.10 предшественником других items НЕ является.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing; §4 Phase Index — P8 `7/10 🟡`;
§5 D124/D125; §6 Update Log) · `phases/P8.md` (`## Phase Status` — P8.1–P8.9 `🟢`/`🟠`, P8.10
`⬜`; P8.5–P8.9 Completion Notes) · `research/25-P8.5-routing-cell-form-2026-07-27.md`
(диагноз §3 Routing, целевой дизайн P8.10) · `roadmap.md` § P8.10 · машинные гейты
`plans/cross-plan-files.py`, `plans/verify-citations.py`, `packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `packages/maind/scripts/test.sh`
(`test_local_skills_reference_on_demand_model` P3.2 + `test_d108_…` P5.3) — пред-существующие,
долг вне `Files` любого закрытого item'а; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` не вычитана
(`[UNVERIFIED]`, D110); (3) P10.4 Pending Work — рендерер `.mcp.json` (D106); (4) P10.3 Pending
Work — `README.md:122` битая ссылка (кандидат `/task:fix`); (5) F13/F14 аудита P5 (заход 2) —
за владельцем P5/`maind`; (6) P10.2 Pending Work (b) — `verify-citations-known-exceptions.json`
не решён владельцем; (7) carve-out (б) канона `plan-protocol` не переписан (D118); (8) P8.4 job
`hygiene` не подтверждён реальным CI-run'ом; (9) `plans/2026.07.18-FOREMAN` несёт нелегальную
форму ячейки §3 — правит FOREMAN, не этот план; (10) матрица `docs/status.md` не сверена с
живыми контрактами (D2, отложено); (11) `public-hygiene` CI-гейт (P8.6) красный на текущем
дереве — `install.log` в `artifacts/p5-pilot/stage0/` (P8.6 Pending Work, owner); (12) три
CORE-скилла без активационной секции — унаследованный долг в `skill-sections-burndown.txt`
(P8.8, правка тел вне scope); (13) пред-существующая ruff-находка `B904` в
`packages/skiller/lib/skiller/publication.py:1037` — вне `Files` P8.9, не регрессия, не
починена (кандидат `/task:fix`).

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в §6 Update Log); машинный lint формы §3 в `plan_lint.py`; сверка полноты
матрицы `docs/status.md` (D2); удаление/gitignore `install.log` (P8.6 Pending Work, owner);
перевод `maind/provider_deploy.py` на `assert_safe_replace_target` (P8.7, roadmap-кандидат);
заполнение `triggers[]` у четырёх скиллов с `evals/` (P8.8, WARNING). Долг «перепиннуться на тег
Serena» держит `roadmap.md` § «Отложенное» (D110).
