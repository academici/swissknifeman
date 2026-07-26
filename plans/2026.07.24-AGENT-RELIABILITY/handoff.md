# HANDOFF — 2026-07-26 — after P2.4

**Next:** exec-items: task:plan-exec 2026.07.24-AGENT-RELIABILITY P2.5

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `medium` |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` |
| Суть | Прогнать immutable P0.3 bank через combined P1/P2 effective runtimes (P2.2–P2.4), доказать historical failure scenarios end-to-end |

```
/task:plan-exec 2026.07.24-AGENT-RELIABILITY P2.5
```

**Done:**

- **P2.1 закрыт 🟢** (три контракта запечатаны, машина 135/135 ячеек) — детали `phases/P2.md` P2.1 Completion Notes.
- **P2.2 закрыт 🟢** (2026-07-26, `task:plan-run` под **sonnet/high** = предписанный §3 Routing `implementation/high`, точное совпадение). `task_contract.py` compiler + tiered-portability lint, `plan-protocol@2.12.0`/`skiller@0.5.0`/`task@0.4.0` — детали `phases/P2.md` P2.2 Completion Notes.
- **P2.3 закрыт 🟢** (2026-07-26, `task:plan-run` под **sonnet/high** = предписанный §3 Routing `implementation/high`, точное совпадение). `review_policy.py` — typed finding/review enforcement, loop breaker, `evaluate_finding` хук в `task_contract.py`, `task@0.5.0` — детали `phases/P2.md` P2.3 Completion Notes.
- **P2.4 закрыт 🟢** (2026-07-26, `task:plan-run` под **sonnet/high** = предписанный §3 Routing `implementation/high`, точное совпадение). Произведено:
  - `packages/task/lib/task/route_evidence.py` — `required_route` (детерминированно из `CommandCatalog`), `capture_actual`/`classify` (`exact/over/under/unknown`), `dispatch_guard` (fail-closed строго ДО компиляции Task Contract — переиспользует ровно `ROUTE_UNDERSHOOT`/`CAPABILITY_UNSUPPORTED`, P0.2, новых кодов не минтит), `capability_support`, `route_change_boundary`, `capture_budget` (no-pricing, оси совпадают с `analyst.readers` `usage.totals`), `canonical_actor`, `build_task_contract_route` (байт-в-байт `task-contract-v1.schema.json` `$defs/route`).
  - `journal.py` получил `--route-evidence PATH` (взаимоисключающий с `--actor`).
  - `harness/doctor.py`/`analyst/doctor.py` — по одной строке про источник route evidence (analyst — опциональный `task.route_evidence`-чек).
  - `command-routing.json` НЕ тронут: `required_route` переиспользует уже собранный `CommandCatalog`, а не парсит JSON заново — exact-set схема файла принадлежит `command_catalog.py` (вне Files этого item'а).
  - Тесты: 36+8+17+10, все зелёные (на `97b4a7eb`); `render-provider-commands.py --check` и `skiller registry --check` — no-op.
  - Diff-scope guard: item-коммит `97b4a7eb` несёт ровно `Files` минус `command-routing.json` — посторонний дифф нет.
  - Known Deviations (process, не material): пропущена интерим-запись `🟡 In progress` и старт-запись журнала до начала работы (D21 п.3) — журнал несёт только финал-запись — детали `phases/P2.md` P2.4 Known Deviations.

**Remaining:**

12/22 items. P2: 4/5 (P2.5 — последний item фазы) → P3 (5) → P4 (3).
Все items P2 детализированы; повторный дизайн-заход не требуется.

**Sources of truth:**

`plan.md` v1.14.3 (§3 Routing, §4 Status Board, §5 D9/D68, §7 Contracts) ·
`phases/P2.md` § P2.4 Completion Notes (факты закрытия) ·
`packages/task/lib/task/route_evidence.py` · `packages/task/lib/task/task_contract.py` ·
`roadmap.md` § P2.5 · `journal.jsonl`.

**Open risks:**

- **Строка фазы P0 в `plan.md` §4 всё ещё протухла** (унаследовано от P2.1–P2.3's handoff — этим item'ом не правилось, чужая поверхность И2): `🟡 In progress` при четырёх терминальных items. Владелец правки — `task:plan-close 2026.07.24-AGENT-RELIABILITY P0`.
- **`packages/task/docs/reference/provider-commands.md` не входит в `artifacts/P1.1/remediation-map.json::owners.P2.2.paths`** (унаследовано от P2.2, этим item'ом не задето). Владелец правки карты — P1.1 (D#).
- `check_collision_owners` структурно несовместим с фазовой ремедиацией — без изменений с P2.1.
- Прежний долг: две находки A2 (порядок capture `base-sha` — закрыто по факту исполнения P2.2/P2.3); `research/01–03` без ссылок на слой 1; A1 F11; `command.interactive-user-input` вне каталога capability; Claude enabled-set `unknown`; Claude-проекция `workflow-craft`; расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).
- **`review_policy.py`'s `LoopBudget`/`review_transition` — in-process, без persisted cross-session состояния.** P2.5 — владелец доказательства реальной многосессионной/многовызовной последовательности против этой политики.
- **`plan-lint`: 1 WARN (`plan.md:366`, чужая P1.4 Update Log-строка >300 символов) — pre-existing, 0 новых от диффа P2.4** (`--baseline HEAD` на item-коммите `97b4a7eb`). Владелец правки — исполнитель P1.4/P1.5, не этот item.
- **`route_evidence.py`'s `dispatch_guard`/`build_task_contract_route` не подключены ни к одной реальной точке dispatch** (root supervisor / `plan-exec`/`plan-run` командные тела не зовут этот модуль — Scope P2.4 был библиотека+интеграционные швы, не переписывание командных тел, вне Files этого item'а). P2.5 (end-to-end historical scenarios) — первый потребитель, который реально прогоняет через route guard; если он этого не сделает — назвать долг явно, не молчать.

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых этим item'ом.
- **deferred:** протухшая строка фазы P0 в §4; структурный фикс `check_collision_owners`/`remediation-map.json`; `command.interactive-user-input`; Claude-проекция `workflow-craft`; расхождение провенанса harness-CLI ↔ maind-адаптера; исторический A2-долг; `route_evidence.py` не подключён к реальной dispatch-точке (см. Open risks).
- **open_questions:** нет открытых для владельца — по D50 развилки закрываются записью.
