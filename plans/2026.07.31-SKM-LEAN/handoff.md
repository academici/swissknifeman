# HANDOFF — 2026-08-01 — after P4.2

**Next:** manual: `implementation/high` — P4.3 `Exec = manual` (`plan.md` §3, `roadmap.md`
строка P4.3: solo, батч запрещён критерием §9 — P4.4/P4.6 сцеплены с ним по данным).

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | `worker` — запуск `claude -p /task:plan-exec` под таймаутом, дефенсивный разбор конверта живой версии |

````
Прочитай plans/2026.07.31-SKM-LEAN/phases/P4.md item P4.3 целиком (Intent, Why, Scope
Included/Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance,
Validation, Deliverables) и исполни его строго по ТЗ. ПЕРВЫМ Required Read —
plans/2026.07.31-SKM-LEAN/root/contracts/driver-plan-protocol-v2.md §6 (транспортный слой,
поля конверта) и §9 U1-U3 ([UNVERIFIED] пункты, закрываются этим item'ом наблюдением).
Пометь item 🟡 In progress до начала практической работы, затем закрой по правилам
plan-protocol (Task Contract pre-mutation/pre-final, Completion Notes, Known Deviations,
журнал, два коммита).
````

**Done:** Этим заходом — **P4.2** (`plan_reader`, `manual`-путь, сессия sonnet/high), второй
item фазы P4.

- Реализован `packages/harness/lib/harness/run/plan_reader.py` (item-коммит **`69629f30`**) —
  очередь исполнения фазы: item'ы в порядке `## Phase Status`, терминальные исключены
  (`excluded_terminal`), маршрут (S2 — `task.task_contract build`), значение ячейки `Exec` (S4 —
  собственный разбор, зеркало `task_contract._find_routing_row`), форма `Next` (S5 —
  ТОЛЬКО префиксный токен закрытого enum'а 11 форм, легаси-входы совместимости НЕ резолвятся).
- Закрытый набор причин отказа вождения реализован целиком: `EXEC-NOT-PLAN-EXEC` ·
  `ROUTING-INCONSISTENT` · `ROUTING-UNRESOLVED` · `NEXT-FORM-UNSUPPORTED` · `PLAN-UNREADABLE`
  (через `degraded`) · `ITEM-TERMINAL`. Деривация §9 маршрута используется РОВНО на отказ
  (D31) — право вождения только из дословного значения `Exec`.
- Drift-тест «зеркало матчера»: синтетическая таблица §3 (одиночная форма/диапазон/список
  через запятую) через `plan_reader._resolve_exec_cell` и через
  `task_contract._find_routing_row` дала совпадающее множество покрытых item'ов.
- Committed-фикстура `packages/harness/tests/fixtures_data/run/sample-plan/` заведена
  (переиспользуется P4.3–P4.6): порядок очереди, исключение терминального item'а, диапазонная
  форма §3, drivable-кейс.
- `bash packages/harness/scripts/test.sh` — **562 теста**, зелёный (10 новых); `validate.sh` —
  `OK`; `grep -rn "import task\|packages/task/lib" packages/harness/lib/harness/run/` — пусто
  (D29 держится); ручной прогон на живых фазах P4/P5 — очередь и причины отказов печатаются без
  трейсбека.
- Task Contract (D76): `pre_mutation: allow`, `pre_final: allow` (actual_route
  `implementation/high`, `source=self-attested`, `model=sonnet`).

**Remaining:** доска: P1 3/4 (🟠) · P2 5/6 (🟠) · P3 2/6 (🟠, терминальна) · **P4 2/6
(🟡 In progress)** · P5 0/9 (⬜) · P6 0/3 (⬜) · P7 0/4 (⬜). Всего 38 items. Следующий —
**P4.3** (`worker`), далее строго последовательно P4.4 → P4.5 → P4.6: items фазы сцеплены по
данным, оркестрация не заявлена.

**Sources of truth:** `packages/harness/lib/harness/run/plan_reader.py` (реализация) ·
`plans/2026.07.31-SKM-LEAN/root/contracts/driver-plan-protocol-v2.md` (§2 источники, §3
собственные разборы) · `phases/P4.md` P4.2 Completion Notes · `plan.md` §4 доска, §6 Update
Log, `## 0. Meta` · `roadmap.md` (маршрут P4.3 — `Exec = manual`, solo) · `journal.jsonl`.

**Open risks:** без изменений по содержанию от предыдущего handoff, кроме закрытия пункта про
P4.2, плюс:

- **Пять `[UNVERIFIED]` контракта с адресами** — без изменений: U1/U2/U3 закрываются
  наблюдением в **P4.3** (следующий item); U4 вне скоупа плана (D9); U5 меряет **P4.6**.
- **Контракт пинован на `06fefc87`, канон живёт своей жизнью** — перед волной сверяются три
  строки (версия скилла, `git rev-parse HEAD`, `claude --version`); расхождение — сверить шесть
  якорей §8 и бампнуть контракт, невозможность сверить — стоп и эскалация.
- **Два WARN линтера по фазе P4** — латентные ложные срабатывания на ТЕКСТЕ фазы (без
  изменений от предыдущего захода): DoR-строка с буквальной формой маркера-плейсхолдера
  `phases/P4.md:67`; `оркестрац` без понимания отрицания в `:87` и в `Required Reads` P4.6.
  Адрес — `plan-close <ID> P4` либо отдельный fix-item.
- **Второй собственный разбор драйвера теперь РЕАЛИЗОВАН** (не только контрактом назван) —
  любой новый факт без источника из S1–S3 обязан править контракт P4.1, а не расширять
  `plan_reader.py` третьей точкой разбора (правило §8 контракта, зеркало Code Guidance P4.2).
- (в силе) остаток `desc-trigger-burndown.txt` 61 запись · 221/229 скиллов без тиров
  `model:`/`effort:` · `paths:` не раскатан (D98) · `disable-model-invocation` только на 4
  пилотных · 14 файлов evals-заглушек · **OQ-9** (`ACCEPTANCE_NOT_PUBLIC` против D77, владелец
  вне плана) · долг **D90** · 3 дефекта в `snippets/` `devops/db-test-preflight` · кандидаты под
  `context: fork` отложены · конфликт правил в ТЗ P3.6 · токен `contradictory evidence` вне
  enum §10 · дефект генератора `.mcp.json.example` · path-scoped rules только на пилоте
  `dterema/app` · `resolve_active_set` слеп к плагинам · Boost/`.ai`-CLAUDE.md флот не покрыт
  P2.2 · пять секций-кандидатов P2.1 резидентны (D89) · гейт размера файла целиком · токенная
  оценка продублирована в двух пакетах · `closure/P1.json` hash устарел (D87) · остаточная
  находка `verify-citations` в `phases/P2.md` (P2.3).
- **В рабочем дереве есть чужой дифф** (`.gitignore`, удалённый `RESEARCH/AUDIT-loqum-findings.md`,
  неотслеживаемые `.swissknife/`, `audits/`) — этим заходом не тронут и не коммитился.

**Workarounds/Deferred/Open questions:** обходных приёмов этим заходом не применялось. Отложено
контрактом явно: экономика волны (U5 → P4.6), Codex-водитель (U4 → вне плана, D9). Новых open
questions не заведено; открытых остаётся **три** — OQ-3 · OQ-6 · OQ-8 — плюс OQ-9 (владелец
протокола, вне этого плана).
