# HANDOFF — 2026-07-27 — after P5.5

**P5.5 закрыт 🟢 Done** (item-коммит `88f0c7eb`): пин Serena
`@026b007bb889366283c925527e9a3bab317f66c1` перенесён из gitignored `config.json` в
ВЕРСИОНИРУЕМЫЕ носители политики — `config.example.json` (`code_graph.args`+`index_args`),
`.mcp.json.example` (`serena.args`), пример в `packages/maind/docs/guide/code-graph.md` — тем же
значением, что несёт `constants.SERENA_SRC` (F1 аудита фазы P5, D115/D116). Двойная охрана:
офлайновый тест `test_tracked_templates_pin_serena_same_as_source` (`test_constants.py`) сверяет
шаблоны побайтно с `constants.SERENA_SRC`; вызов `codegraph.check_schema_connectivity` врезан в
`maind doctor` (блок `if config:`) — печатает `[ok ]`/`[FAIL]`, расхождения не чинит (D111). Путь
регрессии `packages/maind/install.sh:100-101` (`cp config.example.json → config.json`) назван и
подтверждён: свежая установка раньше копировала непиннованный шаблон, воспроизводя D65.
Краснота обоих гейтов проверена фактически (снятие `@REF` из шаблона → тест падает с
`AssertionError`, называющим файл/поле; снятие пина из `config.json` → `doctor` даёт `[FAIL]` +
exit 1) и деревья возвращены (`git diff` пуст, `config.json` сверен `cmp`). `bash
packages/maind/scripts/test.sh -v` — 502 теста, 2 FAIL без изменений от baseline
(`test_local_skills_reference_on_demand_model` P3.2, `test_d108_…` P5.3). `plan-lint.py
--baseline HEAD` (на item-коммите `88f0c7eb`) — 0 ERROR / 24 WARN, K=0 от диффа Scope.

**Next:** исполнить **P5.6** (D117) — сужение `SERENA_SCHEMA_FIELDS` до факта апстрима (2 ключа),
починка докстринга `render_project_yaml`, регресс-тест в обе стороны. Затем `/task:plan-close`
фазы P5.

| Параметр | Значение |
|:--|:--|
| Model | Sonnet 5 (`implementation`) |
| Thinking | medium — §3 Routing строка P5.6; предписанная реализация, открытых решений нет |
| Context | NEW SESSION — item плана |
| Суть | `SERENA_SCHEMA_FIELDS` сужается до `{project_name, language_servers}` (факт апстрима, D117) + чинится докстринг `render_project_yaml` + регресс-тест в обе стороны. |

```
/task:plan-exec 2026.07.25-ECO-OPT P5.6
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1** ·
**P10.2** · **P10.3** · **P10.4** (фаза P10 терминальна фактически, 3🟢+1🟠, ждёт `plan-close`) ·
**P8.1** · **P8.2** · **P8.3** · **P9.1** · **P2.1** · **P3.2** · **P1.2** · **P5.1**🟢 ·
**P5.2**🟢 · **P5.3**🟠 · **P5.4**🟢 · **P5.5**🟢 (фаза P5 — 4/6, ждёт P5.6) —
**16/43 items закрыто**, 1 фаза терминальна (P10 готова к закрытию), 6 фаз в работе
(P5 — 4/6, P8 — 3/9, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2).

**Remaining:** 27/43 items. **P5.6** — следующий (порядок: общий `CHANGELOG.md`; жёсткой
зависимости по коду нет). **P10 готова к `/task:plan-close 2026.07.25-ECO-OPT P10`** (независимо
от P5). P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93). P6.1 — ПОСЛЕ P9.1 (условие снято). P4.2 — ПОСЛЕ
P3.2 (условие снято). Свободные одиночные items: P1.1 (frontier/high, manual), P3.1 (нужен
оператор), P8.4–P8.9, P9.3.

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing — строка P5.6; §4 Phase Index —
P5 `4/6 🟡 In progress`; §5 D115/D116/D117; §6 Update Log) · `phases/P5.md` (`## Phase Status` —
статус фазы и 6 items; ТЗ P5.6; блок `## Audit P5 — 2026-07-27` — источник находок F1/F2; P5.5
Completion Notes) · `findings/P5-audit-closure-facts.md` §3 (факт апстрима
`FIELDS_WITHOUT_DEFAULTS = {project_name, language_servers}`, слой 1 P5.6) ·
`findings/P5.3-serena-pin-and-provider-gate.md` (§10 — две истории версии) ·
`closure/P5.json` (P5.5 обновлён вручную под carve-out; полная регенерация — задача
следующего `plan-close`, см. `limitations`) · `open-questions.md` (OQ-1 закрыт D113; OQ-9
открыт) · машинные гейты `plans/cross-plan-files.py`, `plans/verify-citations.py`,
`packages/task/scripts/plan-lint.py`.

**Open risks:** (1) второй красный тест `validate.sh` (`test_d108_…`, следствие бампа
`SERENA_SRC` в P5.3) не почищен — долг вне `Files` P5.3, кандидат на отдельный фикс-item за
владельцем `maind`; (2) дельта Serena `v1.6.1` → `1.6.2.dev0` планом не вычитана
(`[UNVERIFIED]`, D110 Consequences) — значение пина переоткрытию не подлежит без нового D#;
(3) `constants.SERENA_SCHEMA_FIELDS` до закрытия P5.6 по-прежнему подписана чужим фактом
(12 ключей вместо двух, F2 аудита) — активный дефект, носитель P5.6.

**Workarounds / Deferred / Open questions:** обходок в коде нет. Отложено владельцем: **F8**
(хеши item-коммитов в строках §6 Update Log — плановая дисциплина, не фазовая). Долг
«перепиннуться на тег, когда апстрим выпустит релиз со схемой `language_servers`» держит
`roadmap.md` § «Отложенное» (срок непроверяем, в item не превращается — D110).
