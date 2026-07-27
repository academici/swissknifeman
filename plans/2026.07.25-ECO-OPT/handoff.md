# HANDOFF — 2026-07-27 — after P5.3

**P5.3 закрыт 🟠 Done with deviations.** Шаги 2–4 под пином D110 исполнены: `SERENA_SRC`
(`packages/maind/lib/maind/constants.py`), `code_graph.args`/`index_args` (`config.json`) и
`serena.args` десяти живых `.mcp.json` (`agelto`, `flexcrm`, `vaulter`, `swissknifeman`, `corex`,
`memster`, `cms`, `edufy`, `chatom`, `perplexity-web-mcp`) пиннованы на одну и ту же строку
`@026b007bb889366283c925527e9a3bab317f66c1` (побайтно сверено). Smoke зелёный на ДВУХ типах
проектов (python-монорепо `swissknifeman`, php/laravel `flexcrm`): полный JSON-RPC цикл
`initialize`→`tools/call get_symbols_overview` вернул реальные символы, фатала `KeyError:
'languages'` больше нет — все 15 зарегистрированных проектов грузятся без ошибки. Гигиена
процессов (гашение строго своего `Popen.pid`, без `pkill` по паттерну) выдержана. Повторный скан
(`serena-pin-drift.json`, секция «ПОСЛЕ») — 10/10 живых пиннованы и резолвят `Serena 1.6.2.dev0`.
Повторный `maind sync --only mcp --dry-run` подтверждает, что `unmanaged-target` (P10.4/D106,
OQ-9) не исчез сам — item лишь прикладывает доказательство, второго адреса не заводит.
**Отклонение:** бамп `SERENA_SRC` разбил `packages/maind/tests/test_provider_deploy.py::
test_d108_inventory_uses_configured_server_names_without_changing_bindings` — тест хардкодит
sha256 рендера, зависящий от значения пина; фактический хеш сегодня —
`sha256:1d6d757436dc238647a841e6bb7c9efdfa137d5f82c680b7a88d28f1c325fd9d` вместо ожидаемого в тесте
`sha256:8adaa29018516734a6af1137fb797562861eb221fe425b03d5d0bcc1d43e4f2f`; файл не входит в `Files`
этого item'а — фикс назван (заменить литерал), не применён здесь. Остаточный failing-тест
`test_local_skills_reference_on_demand_model` (P3.2 Pending Work) — известный, не новый. Детали —
`findings/P5.3-serena-pin-and-provider-gate.md` §12, `phases/P5.md` P5.3 Completion Notes/Pending
Work/Known Deviations.

**Next:** exec-items: task:plan-exec 2026.07.25-ECO-OPT P5.4

Свободный выбор владельца: **P5.4** (гейт связности, теперь идёт ПОСЛЕ закрытого P5.3, `Exec =
plan-exec`) либо **P5.1** (ступень 0 kill-gate, не зависит от P5.3). Дефект `test_d108_…` —
самостоятельный follow-up, не блокирующий: точечный фикс литерала хеша в тесте, вне Files P5.3.

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P5.4: офлайновый гейт связности «схема `.serena/project.yml` ↔ версия пина» в `packages/maind` — читает `Required Reads`, пишет детектор + тесты, НЕ трогает значение пина. |

```
/task:plan-exec 2026.07.25-ECO-OPT P5.4
```

Альтернатива (фикс найденного теста, если владелец хочет закрыть его раньше P5.4):

```
Замени в packages/maind/tests/test_provider_deploy.py литерал ожидаемого sha256 в
test_d108_inventory_uses_configured_server_names_without_changing_bindings с
"sha256:8adaa29018516734a6af1137fb797562861eb221fe425b03d5d0bcc1d43e4f2f" на
"sha256:1d6d757436dc238647a841e6bb7c9efdfa137d5f82c680b7a88d28f1c325fd9d"
(новое значение — прямое следствие пина Serena @026b007b… из P5.3, D110), прогони
bash packages/maind/scripts/test.sh и закоммить точечно.
```

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1** ·
**P10.2** · **P10.3** · **P10.4** (фаза P10 терминальна фактически, 3🟢+1🟠; перевод строки доски
делает `plan-close`) · **P8.1** · **P8.2** · **P8.3** · **P9.1** · **P2.1** · **P3.2** · **P1.2** ·
**P5.3** (🟠 Done with deviations, эта сессия — коммит `930ad0ac`) — **12/41 items закрыто**, 5 фаз
в работе (P8 — 3/9, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2, P5 — 0🟢+1🟠 из 4).

**Remaining:** 29/41 items. **P5.4** свободен (идёт ПОСЛЕ P5.3 — условие снято). **P5.1/P5.2**
свободны (не зависят от P5.3). **P10 готова к `/task:plan-close 2026.07.25-ECO-OPT P10`** когда
владелец сочтёт нужным. P2.3 — ПОСЛЕ P8.1/P8.2/P8.3 и P6.3 (D93). P6.1 — ПОСЛЕ P9.1 (условие
снято). P4.2 — ПОСЛЕ P3.2 (условие снято).

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing — строки P5.3/P5.4; §5 D1–D111;
§7 Contracts; Обсуждение 1–19; `## Audit design`; §6 Update Log — запись «P5.3 закрыт») ·
`phases/P5.md` (P5.3 Completion Notes/Pending Work/Known Deviations — итог этого захода; P5.4 —
готовое ТЗ) · `findings/P5.3-serena-pin-and-provider-gate.md` (§12 — что изменено, smoke, повторный
скан, `unmanaged-target` живым) · `artifacts/P5.3/serena-pin-drift.json` (секции ДО/ПОСЛЕ) ·
`roadmap.md` (§ «Отложенное» — три долга D109–D111, включая «перепиннуться на тег») ·
`open-questions.md` (OQ-9) · машинные гейты `plans/cross-plan-files.py`,
`plans/verify-citations.py`, `packages/task/scripts/plan-lint.py` · канон
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §§6, 8, 9.

**Open risks:**
- **Новый failing-тест `test_provider_deploy.py::test_d108_…`** — хардкод sha256 старого пина,
  прямое следствие D110; фикс назван (замена литерала), не применён (файл вне `Files` P5.3);
  follow-up точечным коммитом, не блокирует другие items.
- **Пиннуется dev-коммит без релиз-нот и апстрим-QA** (D110): дельта `v1.6.1` → `1.6.2.dev0`
  планом НЕ вычитана ([UNVERIFIED]). Долг «перепиннуться на тег» — `roadmap.md` § «Отложенное».
- **Апстрим может force-push'нуть/переписать историю**, и запиненный SHA перестанет резолвиться —
  тогда следующий бамп эскалирует, а не подменяет ссылку молча.
- **Две истории версии в репо остаются разъехавшимися до закрытия P5.4** — сегодня согласованность
  держится только текстом ТЗ; P5.4 — следующий свободный item, который это чинит машинно.
- **Дефект рендерера `.mcp.json` — системный** (P10.4 Pending Work, D106): доставка пина во флот
  остаётся ручной точечной правкой, ресинк недоступен (подтверждено ещё раз этим заходом).
- **Остаточный failing-тест `test_local_skills_reference_on_demand_model`** (P3.2 Pending Work)
  краснит `packages/maind/scripts/validate.sh` — задевает и P5.3 (закрыт), и P5.4 (следующий,
  оба в пакете `maind`): зелёным считается прогон СВОИХ тестов.
- **`plan-lint` даёт WARNING «phase-first: P5 содержит активные 🟡/🟠 items, хотя P4 ещё не
  терминальна»** — ожидаемо (P5.3 сознательно шёл вне очереди фаз, D65), не дефект правки.
- **`packages/task/lib/task/plan_lint.py` несёт 8 нерезолвящихся бэйр-ссылок `P0.3 рек#N`**
  (P1.2 Pending Work) · **39 находок `verify-citations.py`** без follow-up (P10.2) ·
  **`verify-citations-known-exceptions.json` не заведён** (P10.2) · **`README.md:122` ссылается на
  несуществующий `roadmap/self-learning-memory.md`** (P10.3) · **`research/11` §2 частично отменён
  D103, файл не переписан**.
- Prior-риски в силе (не повторяются дословно): P3.1 нельзя закрыть без оператора · P3.5 — самая
  «дальнобойная» правка · корневой `CLAUDE.md`/`AGENTS.md` — три писателя (D79) · P8 держит шесть
  оставшихся items на горячем hotspot'е · P9 не параллелится · P7.1 работает на живых items ·
  LAN-стадия памяти: секрет — единственный предохранитель · pressure-eval P6.3 по построению слаб ·
  двенадцать внутриплановых связок держатся ТЕКСТОМ.

**Workarounds/Deferred/Open questions:**
- **workarounds:** ручная точечная правка `.mcp.json` вместо `maind sync` (D65/D106); офлайновая
  константа-ожидание схемы в P5.4 вместо запроса к апстриму (сеть в гейте запрещена — иначе
  flaky); двенадцать связок «порядок вместо инструмента»; `STALE_SOURCE`/`UPDATE` для тира 1
  усыновления (P10.4); человеческий арбитраж вместо LLM-judge (D71); правило активации плагина
  Codex — текстом (D84); `## 7. Contracts` — каталог, не машинная сверка (D97); собственный
  файловый счётчик петли review-gate (P9.1); резолвер `core.resolve_plan_dir` не экспортирован
  через `core/__init__.py` (P10.3).
- **deferred:** всё из `roadmap.md` § «Отложенное», включая три долга D109–D111 (перепиннуться на
  тег · вычитка дельты `v1.6.1` → `1.6.2.dev0` · обобщение гейта связности на другие внешние пины
  репо) + починка расхождения рендерера `.mcp.json` (P10.4/D106) + follow-up на 39 находок
  `verify-citations.py` + `verify-citations-known-exceptions.json` + битая ссылка `README.md:122`
  + фикс литерала sha256 в `test_d108_…` (новый, этот заход).
- **open_questions:** новых не заведено. OQ-9 (владелец починки провайдерского контура) — открыт,
  P5.3/P5.4 его не дублируют. Срок выпуска апстримом тега со схемой `language_servers` —
  непроверяем по построению, планировать на него нельзя.
