# HANDOFF — 2026-07-31 — after P1.4

**Next:** `/task:plan-exec 2026.07.31-SKM-LEAN P1.2`

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium — из §3 Routing (`implementation/medium`, `Exec = plan-exec`) |
| Context | continue (/clear) — ручной item |
| Суть | Обход 26 записей реестра флота инструментом, приведённым к факту P1.4 — baseline `findings/P1-fleet-baseline.md` |

```
/task:plan-exec 2026.07.31-SKM-LEAN P1.2
```

**Done:** **P1.4 закрыт 🟢** (`plan-run`, sonnet/high — маршрут совпал с предписанным §3 Routing
`implementation/high` без недобора/перебора). `plugins.py` приведён к трём живым фактам
`claude 2.1.220`: (1) `plugin_always_on_tokens(plugin_id, cwd)` — `cwd` обязательный параметр,
резолвинг local-scope плагина зависит от cwd его проекта (было — нет); (2) `_ALWAYS_ON_RE`
разбирает разделитель тысяч (`~1,275` → `1275`); (3) неполнота разведена на `broken[]`
(листинг сам объявил плагин сломанным полем `errors`, цену не взяли) отдельно от `unparsed[]`
(дрейф формата без объявленной поломки). Кэш: успех по `id` глобально, неудача не кэшируется.
`budget.py` `_format_plugins_block` печатает `broken` отдельной строкой. `docs/guide/cli.md`
обновлён под трёхклассовую неполноту.

**Живой смоук на `memster` (главная приёмка, до/после починки):** `plugins.total`
**2 946 → 10 852** — сверено независимым ручным прогоном `claude plugin details` по всем 18
enabled-id проекта (сумма распознанных — байт-в-байт 10 852); `unparsed: []`; `broken` — ровно
`brain@brain` с причиной из `errors`. Смоук на этом репозитории: `session_total` 14 866 >
`total` 11 920, `broken` печатается строкой. Не-регрессия: `--first-turn --json` без флага →
ключи `{sources, target, total, verdict}` — не изменились.

`test_plugins_aggregate.py`: 12 кейсов (было 8) — `test_thousands_separator_is_parsed`,
`test_cwd_reaches_details_call`, `test_errors_entry_that_resolves_counts_in_total_and_warnings`,
`test_failure_not_cached_retries_under_different_cwd` — новые; happy-path адаптирован под
`broken` (не удалён). Новая фикстура `plugin-details-architect.txt` — дословный вывод живого
`claude`, захвачена в этой сессии. `bash packages/skiller/scripts/test.sh` — 540 тестов, OK;
`validate.sh` — exit 0. Item-коммит `85b2b762`. Известное отклонение (process, не material):
Pre-mutation Task Contract и пометка `🟡 In progress` выполнены ПОСЛЕ начала правки кода, а не
до неё — детали в Known Deviations `phases/P1.md` P1.4.

**Remaining:** P1.2 (пере-замер флота инструментом P1.4) → P1.3 (порог + гейт владельца
OQ-1/OQ-4). Затем P2 → P3 → P4 → P5 → P6 → P7 по `roadmap.md`. Доска: P1 1/4 · P2 0/6 ·
P3 0/5 · P4 0/6 · P5 0/9 · P6 0/3 · P7 0/4 (терминальны два items — P1.1 `🟠` `487e68d0`,
P1.4 `🟢` `85b2b762`). Восемь items идут `Exec = plan-exec` (P1.2 · P2.4 · P2.6 · P5.2 · P5.3 ·
P5.6 · P6.3 · P7.2), остальные 28 — ручным маршрутом (`plan-run`, D18).

**Sources of truth:** `plans/2026.07.31-SKM-LEAN/plan.md` (§0 Meta v1.0.4, §3 Routing 37
строк, §5 D1–D82, §4 доска P1 1/4) · `phases/P1.md` (P1.4 — Completion Notes закрыты; P1.2 —
ТЗ ждёт исполнения инструментом P1.4; P1.1 без изменений) · `packages/skiller/lib/skiller/plugins.py`
(починенный агрегатор — вход P1.2) · `findings/P1-plugins-cwd-defect-2026-07-31.md` (сырьё,
подтверждено смоуком P1.4) · `open-questions.md` (OQ-1…OQ-6, OQ-8 — семь открытых, без
изменений) · `roadmap.md` (порядок P1.1 → P1.4 → P1.2 → P1.3).

**Open risks:** (прежние риски P1–P7 в силе, см. предыдущие handoff — правило двух SSOT)
плюс:

- **`brain@brain` — сломанный плагин в ЧУЖОМ репозитории** (`~/Vaults/Brain/.claude-plugin/plugin.json`,
  невалидный манифест). `scope: user` → в листинге КАЖДОГО проекта флота, класс `broken` будет
  непуст всегда, пока манифест не починен в репозитории `brain` — вне периметра этого плана.
  P1.4 сделал это видимым (было бы неотличимо от `unparsed` до починки), не исправил.
- **Кэш `details` живёт в ПРОЦЕССЕ, а обход флота запускает `skiller` процессом на проект** —
  экономия между проектами не работает: каждый проект платит ~17 вызовов × 0,76 с. Отсюда
  таймаут ≥ 120 с в P1.2 (Implementation Rules §8); если после P1.4 обход всё равно упрётся в
  таймаут, это вход для решения «кэш между процессами», а не повод молча ронять строки.
- **Числа P1.2/P1.3 средо-зависимы:** состав установленных плагинов — свойство машины
  владельца, а не репозитория; P1.2 обязан сверять с ручным прогоном, а не с константой
  10 852 (это число памятно только для сегодняшнего состава плагинов `memster`).

**Workarounds/Deferred/Open questions:** «—» / «—» / OQ-1…OQ-6, OQ-8 (семь открытых, без
изменений этим заходом), см. `open-questions.md`.
