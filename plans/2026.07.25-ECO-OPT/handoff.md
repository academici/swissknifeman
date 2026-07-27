# HANDOFF — 2026-07-27 — after P5.4

**P5.4 закрыт 🟢 Done.** Гейт связности «схема `.serena/project.yml` ↔ версия пина Serena»
(D111) добавлен в `packages/maind`: `constants.SERENA_SCHEMA_FIELDS` (12 обязательных ключей,
офлайновая копия факта) + `codegraph.check_schema_connectivity(config)` — офлайновая чистая
функция без сети/uvx, сверяет пин (`SERENA_SRC` + `code_graph.args`/`index_args` конфига) с
ключами, которые РЕАЛЬНО печатает `render_project_yaml` (не с копией). Только недостающие
обязательные ключи считаются расхождением; лишние (`project_name`) — нет (Scope Excluded).
Гейт не чинит расхождение — только называет оба файла и оба набора ключей в тексте ошибки;
решение (бампнуть пин / откатить шаблон) — за владельцем. 4 новых теста в
`tests/test_codegraph.py::TestSchemaConnectivity` (согласованное состояние зелёное; три
расщеплённых сценария — схема разошлась / пин отсутствует / пины разошлись между
`SERENA_SRC` и конфигом — красные с сообщением, называющим оба места). Анти-подгонка проверена
фактически: временная порча `SERENA_SCHEMA_FIELDS` дала реальный `FAIL`, дерево возвращено.
`bash packages/maind/scripts/test.sh`: 501 тестов, 3 FAIL — 2 старых известных
(`test_local_skills_reference_on_demand_model` P3.2, `test_d108_…` P5.3 Pending Work), 0 новых
(на item-коммите `253ae4a6`). `plan-lint`: 0 ERROR, 24 WARN (все старые — новых от диффа
item'а нет). Task Contract (pre-mutation + pre-final): `allow`/`allow`.

**Next:** следующий свободный item фазы P5 — **P5.1** (ступень 0 kill-gate), `Exec = manual`
(`implementation/medium`, hands-on `git worktree`-установка CRG в копии `flexcrm` — не
плановая команда). P5.2 логически идёт ПОСЛЕ P5.1 (потребляет его вердикт как вход) — не
свободен раньше.

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Capabilities | — |
| Context | continue (/clear) — ручной item |
| Суть | P5.1: ступень 0 (kill-gate) — изолированная установка CRG в `git worktree`-копии `flexcrm`, замер Ops/P_impact/L_evidence, вердикт skip/ступень-1 по числовому правилу D72. |

**ЗАПУСК ВРУЧНУЮ: implementation/medium** (плановая команда `/task:plan-exec` пинит sonnet/medium
и по Routing-гейту обязана отклонить `Exec = manual` item — используй голый промпт ниже, не
slash-команду):

```
Прочитай plans/2026.07.25-ECO-OPT/plan.md (Context, Execution Rules, §3 Routing строка P5.1,
Status Board), plans/2026.07.25-ECO-OPT/handoff.md, plans/2026.07.25-ECO-OPT/phases/P5.md
(Phase Context + весь P5.1 целиком: Intent/Why/Scope Included/Scope Excluded/Inputs/Required
Reads/Implementation Rules/Code Guidance/Validation/Deliverables) и Required Reads item'а по
списку. Исполни СТРОГО Scope Included P5.1 (ступень 0 kill-gate CRG в git worktree-копии
flexcrm), закрой item по протоколу plan-close (двухкоммитная топология, handoff, plan-lint).
```

Альтернатива (та же форма, через сессионные /model+/effort вместо ручного запуска, D18):
`/model sonnet` → `/effort medium` → `/task:plan-run 2026.07.25-ECO-OPT P5.1`.

**Done:** design-конвейер (3/3 паса + design-аудит RED + закрытие всех находок) · **P10.1** ·
**P10.2** · **P10.3** · **P10.4** (фаза P10 терминальна фактически, 3🟢+1🟠; перевод строки доски
делает `plan-close`) · **P8.1** · **P8.2** · **P8.3** · **P9.1** · **P2.1** · **P3.2** · **P1.2** ·
**P5.3** (🟠 Done with deviations) · **P5.4** (🟢 Done, эта сессия — коммит `253ae4a6`) —
**13/41 items закрыто**, 5 фаз в работе (P8 — 3/9, P9 — 1/4, P2 — 1/3, P3 — 1/6, P1 — 1/2,
P5 — 1🟢+1🟠 из 4).

**Remaining:** 28/41 items. **P5.1** свободен (не зависит от P5.3/P5.4/вердикта OQ-1) — Exec
manual. **P5.2** — ПОСЛЕ P5.1 (потребляет вердикт). **P10 готова к
`/task:plan-close 2026.07.25-ECO-OPT P10`** когда владелец сочтёт нужным. P2.3 — ПОСЛЕ
P8.1/P8.2/P8.3 и P6.3 (D93). P6.1 — ПОСЛЕ P9.1 (условие снято). P4.2 — ПОСЛЕ P3.2 (условие
снято).

**Sources of truth:** `plan.md` (§2 Execution Rules; §3 Routing — строки P5.1–P5.4; §5
D1–D111; §7 Contracts; Обсуждение 1–19; `## Audit design`; §6 Update Log — запись «P5.4
закрыт») · `phases/P5.md` (P5.4 Completion Notes — итог этого захода; P5.1/P5.2 — готовое ТЗ) ·
`research/08-P5-pilot-protocol.md` (протокол ступени 0/1) · `findings/P5-codegraph-vs-serena-
facts.md` · машинные гейты `plans/cross-plan-files.py`, `plans/verify-citations.py`,
`packages/task/scripts/plan-lint.py` · канон
`packages/skiller/skills/general/plan-protocol/SKILL.ru.md` §§6, 8, 9.

**Open risks:**
- **Новый failing-тест `test_provider_deploy.py::test_d108_…`** (со времён P5.3) — хардкод
  sha256 старого пина, фикс назван (замена литерала), не применён (файл вне `Files` P5.3);
  follow-up точечным коммитом, не блокирует другие items.
- **Пиннуется dev-коммит без релиз-нот и апстрим-QA** (D110): дельта `v1.6.1` → `1.6.2.dev0`
  планом НЕ вычитана ([UNVERIFIED]). Долг «перепиннуться на тег» — `roadmap.md` § «Отложенное».
- **`SERENA_SCHEMA_FIELDS` — офлайновая константа, которую следующий бамп пина обязан
  обновить ТЕМ ЖЕ швом** (комментарий-правило в `constants.py` рядом с полем) — гейт P5.4 не
  спасает от забытого обновления самой константы-ожидания, только от рассинхрона рендерера.
- **Дефект рендерера `.mcp.json` — системный** (P10.4 Pending Work, D106): доставка пина во флот
  остаётся ручной точечной правкой, ресинк недоступен.
- **Остаточный failing-тест `test_local_skills_reference_on_demand_model`** (P3.2 Pending Work)
  краснит `packages/maind/scripts/validate.sh` — зелёным считается прогон СВОИХ тестов.
- **`plan-lint` даёт WARNING «phase-first: P5 содержит активные 🟡 items, хотя P4 ещё не
  терминальна»** — ожидаемо (P5.3/P5.4 сознательно шли вне очереди фаз, D65), не дефект правки.
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
  + фикс литерала sha256 в `test_d108_…`.
- **open_questions:** новых не заведено. OQ-9 (владелец починки провайдерского контура) — открыт,
  P5.3/P5.4 его не дублируют. OQ-1 (adopt/skip/combine CRG) ждёт P5.1→P5.2. Срок выпуска
  апстримом тега со схемой `language_servers` — непроверяем по построению, планировать на него
  нельзя.
