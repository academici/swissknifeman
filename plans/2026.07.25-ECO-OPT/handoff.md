# HANDOFF — 2026-07-28 — after P2.2

**P2.2 закрыт `🟠 Done with deviations`** (`aec18754` — item-коммит). Ревизия шести интент-команд
и двенадцати файлов agent-packs по правилу A/B/C (`research/01` §1, расширено D19) под гайды
Claude 5. **Класс A — ПУСТ** (тот исход, который замер 2026-07-25 называл вероятным): единственный
кандидат во второй подкласс A — блок `SUPERVISION` оркестратора — разобран как внешний watchdog
фонового Workflow с действием на срабатывание и оставлен. Работа ушла в «добавить недостающее»:
**4 правки в 3 файлах** — кап делегирования в `design.md`/`research.md`/`review.md` (гайд Opus 5
§6) + ось `confidence ∈ {high,med,low}` в формате находки `review.md` Stage C (гайд Sonnet 5,
«Code review harnesses»). 15 файлов — «изменений нет» с разобранными кандидатами. Карта
`artifacts/P2.2/opus5-revision-map.md` — **18 разделов** (по разделу на файл-поверхность); её
ФОРМАТ и правило — то, что потребляет P2.3. Пины и `description` не тронуты (D16).
Отклонение (отсюда 🟠): item-коммит нёс 4 пути ВНЕ `Files` — три байтовые golden-фикстуры
Claude-проекции и сгенерированный `docs/reference/provider-commands.md`; без них
`packages/task/scripts/validate.sh` красный тремя тестами, то есть Validation недостижима.
Детали — `phases/P2.md` P2.2 Completion Notes.

**Next:** **P2.3** — все ЧЕТЫРЕ её гейта теперь сняты: (а) AGENT-RELIABILITY P2 терминальна — да;
(б) P6.3 терминальна — да; (в) P8.1/P8.2/P8.3 терминальны — да; **(г) P2.2 терминальна — да,
теперь**. P2.3 несёт cross-plan-класс работы (`plan-*.md` — носители канон-литералов), поэтому
перед удалением ЛЮБОЙ строки обязателен греп по `packages/task/tests/test_canon_literals.py` и
`packages/task/lib/task/plan_lint.py`. **Урок P2.2, который P2.3 наследует напрямую:** правка тела
команды тянет производные носители (golden-фикстуры + `docs/reference/provider-commands.md`) —
заложи их в дифф заранее, иначе `validate.sh` красный.

| Параметр | Значение |
|:--|:--|
| Model | opus — предписано Routing (`frontier/high`) |
| Thinking | high — предписано Routing |
| Context | continue (/clear) — ручной item |
| Суть | P2.3: правило A/B/C и формат карты P2.2 по пяти `plan-*.md` + пункт DoR дословно по спеке `research/14` |

**ЗАПУСК ВРУЧНУЮ: opus/high** (`Exec = manual` — открытые решения A/B/C + носители канон-литералов;
`/task:plan-exec` пинит sonnet/medium и обязан такой item отклонить):

```
/model opus
/effort high
/task:plan-run 2026.07.25-ECO-OPT P2.3
```

**Done:** **48/52 items терминальны** (29 🟢 · 18 🟠 · 1 ⛔). Закрыты фазы **P1** (1/2, 🟢),
**P3** (2/6, 🟠), **P4** (3/3, 🟠), **P5** (5/6, 🟠), **P8** (7/10, 🟠), **P9** (3/4, 🟠),
**P10** (1/4, 🟠), **P11** (6/8, 🟠); **P6** — все 3 item'а терминальны (1/3 🟢), Phase Status
Board ждёт отдельный `plan-close`.

**Remaining:** 4 items: P2.3 · P7.1–P7.3. Порядковые условия: P2.3 — все четыре предшественника
терминальны, идёт следующей; P7.1 + P7.3 → P7.2. Плюс отдельно висят фазовые закрытия
`/task:plan-close 2026.07.25-ECO-OPT P6` (все items терминальны, доска не обновлена) и — после
P2.3 — `plan-close` фазы P2.

**Sources of truth:** `plan.md` (§0 Meta `Last Updated`; §4 Phase Index; §6 Update Log — запись
закрытия P2.2) · `phases/P2.md` (Phase Status + P2.2 Completion Notes + ТЗ P2.3) ·
`artifacts/P2.2/opus5-revision-map.md` (правило A/B/C и ФОРМАТ карты — вход P2.3) ·
`research/01-P2-opus5-revision-map.md` §1 · `findings/P2-opus5-guide.md` ·
`findings/P2-claude5-family-and-migration.md` §1/§4 · `research/14-P6.3-dor-delta-spec.md`
(спека пункта DoR) · машинные гейты `packages/task/scripts/validate.sh`,
`packages/harness/scripts/validate.sh`, `packages/task/scripts/plan-lint.py`,
`packages/task/scripts/render-provider-commands.py --check`.

**Open risks:** (наследованные, без изменений этим заходом — полный список см. предыдущий
`handoff.md` git-историей, записи (40)–(48)) плюс:
(49) **`Files` items, правящих `packages/task/commands/*.md`, структурно неполон** — не называет
производные носители (байтовые golden-фикстуры `tests/fixtures_data/claude-command-golden/` и
сгенерированный `docs/reference/provider-commands.md`). P2.2 из-за этого закрыт 🟠; **P2.3 правит
пять тех же команд и наступит на то же**, если её `Files` не расширить или отклонение не принять
заранее.
(50) **Пре-существующий дрейф Codex-проекции** (снят на `915abad7` ДО правок P2.2):
`render-provider-commands.py --check` даёт drift `task.codex.plugin`, `task.codex.publication-lock`
и skill/runtime четырёх `plan-*` команд — наследие переписывания `plan-*.md` планом
AGENT-RELIABILITY. P2.2 добавил к нему `design`/`research`/`review` skill+runtime и НЕ чинил:
единственный регенератор пишет все артефакты сразу и утащил бы производные `plan-*.md` (чужие
поверхности) в item-коммит. Нужен ОДИН отдельный item: `render-provider-commands.py --write
--repair-owned --root .` разом. P2.3 добавит к дрейфу ещё пять `plan-*` проекций.
(51) **`confidence` в пяти agent-pack ревьюерах не добавлен** — носитель-канон
`packages/harness/configs/common/agent-packs/roles.json` (дословный дубль текста проекций) вне
`Files` P2.2; нужен item, правящий канон + пять проекций одним коммитом, и решение, как ось
соотносится с гейтом `GATE_MAX_CRITICAL`.

**Workarounds / Deferred / Open questions:**
· **workarounds** — нет.
· **deferred** — без изменений этим заходом (F1 roadmap-кандидат, расхождение flexcrm 142 vs
186, апстрим-URL `oss-dev/to-issues` 404, протокол backup-restore, `PreCompact`/`PostCompact`
хук — roadmap-кандидат); плюс перекалибровка порогов `skiller budget --first-turn` под токенайзер
Sonnet 5 (~+30%, D19) — кандидат для P3.1, зафиксирован в карте §3 п.3.
· **open questions** — без изменений; OQ-8 закрыт (D81), OQ-11 остаётся `Decision pending` до
закрытия P11.
