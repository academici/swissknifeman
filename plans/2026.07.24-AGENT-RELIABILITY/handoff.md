# HANDOFF — 2026-07-26 — after P2.3

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.4

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Context | `same-session — item` |
| Суть | Реализовать route/budget evidence (required/actual/source/timestamp, fail-closed dispatch guard) поверх независимо-зелёного P2.1/P2.2 |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.4

РЕЖИМ: исполнение детализированного item'а (P2.4 ⬜, P2.3 закрыт 🟢 коммитом `77b574b5` — не реопен, не повторный дизайн).
ВХОД: phases/P2.md § P2.4 (ТЗ) → его Required Reads в объявленном порядке. Свежие входы: `packages/task/lib/task/task_contract.py` (независимо-зелёный компилятор), `packages/task/lib/task/review_policy.py` (P2.3, typed finding/loop breaker), `artifacts/P2.1/state-transition-cases.json` (машина, `route` deny-класс уже объявлен).
СКОУП: 1) D36-baseline: P2.4 в `remediation-map.json::baseline_owners`? СВЕРЬ ПЕРВЫМ — если P2.4 отсутствует в списке (как P2.1), `assert_generated_scope.py` НЕ запускается ни в одном режиме и `artifacts/P2.4/base-sha.txt` НЕ создаётся (Implementation Rules item'а решают окончательно, не этот прогноз); 2) `packages/task/lib/task/route_evidence.py` — normalized route schema (required/actual/source/timestamp), exact/over/under/unknown, dispatch guard (unknown actual effort → fail-closed), route-change boundary, usage/context budget fields; 3) интеграция через СУЩЕСТВУЮЩИЕ journal/doctor швы (`packages/harness/lib/harness/doctor.py`, `packages/analyst/lib/analyst/doctor.py`) — новая публичная схема/API вне P2.1-дизайна эскалирует на contribution-gate, не расширяется inline; 4) root записывает route ДО фактического dispatch fresh-subagent'а.
НЕ ТРОГАТЬ: `packages/task/commands/*.md` и `plan-protocol` канон (владелец P2.2, единый бамп уже закрыт); `packages/task/lib/task/task_contract.py`'s core-предикаты и `review_policy.py` (P2.2/P2.3 owned, независимо-зелёные); замороженные P0/P1/P2.1-контракты и их artifacts/**; pricing/guessed-effort/model-switching-unsupported-by-provider/fleet-config (Scope Excluded item'а).
```

**Done:**

- **P2.1 закрыт 🟢** (три контракта запечатаны, машина 135/135 ячеек) — детали `phases/P2.md` P2.1 Completion Notes.
- **P2.2 закрыт 🟢** (2026-07-26, `task:plan-run` под **sonnet/high** = предписанный §3 Routing `implementation/high`, точное совпадение). `task_contract.py` compiler + tiered-portability lint, `plan-protocol@2.12.0`/`skiller@0.5.0`/`task@0.4.0` — детали `phases/P2.md` P2.2 Completion Notes.
- **P2.3 закрыт 🟢** (2026-07-26, `task:plan-run` под **sonnet/high** = предписанный §3 Routing `implementation/high`, точное совпадение). Произведено:
  - `packages/task/lib/task/review_policy.py` — исполняемая политика `risk-review-loop-budget-v1.md`: seam-derived `finding_id` (split-ban), `reopens_product`-предикат, `LoopBudget` с `same_finding_max=2` (третье вхождение → `INCIDENT` без inline-ремонта), `cap_subject` по authority-профилю (`owner-gated→owner`, `self-host→agent`), `review_transition`/`same_finding_third` — исполняемая форма ячеек `state-transition-cases.json` по всем девяти состояниям, `validation_cadence`. Три новых reason-кода P2.1 реализованы впервые: `FINDING_IDENTITY_UNSTABLE`, `REOPEN_WITHOUT_PRODUCT_FINDING`, `AUTHORITY_PROFILE_UNDECLARED`.
  - `task_contract.py` получил ОДИН новый ленивый хук `evaluate_finding` — core-предикаты не тронуты, P2.2's 38 тестов прошли без изменений (+2 новых теста хука → 40/40).
  - Версии: `task` plugin/routing `plugin_version@0.5.0`. Полная регенерация: `render-provider-commands.py --write --repair-owned` (12 Claude + 24 Codex) → `--check` no-op; `skiller registry --check` — актуально (marketplace не затронут, ссылается на `source`-путь, не версию). `claude-command-golden/plugin.json` синхронизирован вручную.
  - Diff-scope guard: `failures: []`, `undeclared_drift: []` — item-коммит `77b574b5` (единственный, без companion).
  - Self-conformance: `plan-lint plans/2026.07.24-AGENT-RELIABILITY --baseline d5d60201` — 0 ERROR / 1 WARN, новых от диффа item'а: 0.
  - `## 7. Contracts § Exported`: строка `task` plugin/routing переведена `committed P2.2 → committed P2.3 (77b574b5)`, версия v0.4.0 → v0.5.0.

**Remaining:**

13/22 items. P2: 3/5 (P2.4 → P2.5, оба `solo` по `roadmap.md`) → P3 (5) → P4 (3).
Все items P2 детализированы; повторный дизайн-заход не требуется.

**Sources of truth:**

`plan.md` v1.14.2 (§3 Routing, §4 Status Board, §5 D9/D68, §7 Contracts) ·
`phases/P2.md` § P2.3 Completion Notes (факты закрытия) ·
`packages/task/lib/task/review_policy.py` · `packages/task/lib/task/task_contract.py`
`evaluate_finding` · `roadmap.md` § P2.4 · `journal.jsonl`.

**Open risks:**

- **Строка фазы P0 в `plan.md` §4 всё ещё протухла** (унаследовано от P2.1/P2.2's handoff — этим item'ом не правилось, чужая поверхность И2): `🟡 In progress` при четырёх терминальных items. Владелец правки — `task:plan-close 2026.07.24-AGENT-RELIABILITY P0`.
- **`packages/task/docs/reference/provider-commands.md` не входит в `artifacts/P1.1/remediation-map.json::owners.P2.2.paths`** (унаследовано от P2.2, этим item'ом не задето — P2.3 не трогал командные тела). Владелец правки карты — P1.1 (D#).
- `check_collision_owners` структурно несовместим с фазовой ремедиацией — без изменений с P2.1.
- Прежний долг: две находки A2 (порядок capture `base-sha` — ЗАКРЫТО и в P2.3: `assert_generated_scope.py baseline --capture-or-verify` прогнан ПОСЛЕ Required Reads, ДО первой записи, как D36 предписывает); `research/01–03` без ссылок на слой 1; A1 F11; `command.interactive-user-input` вне каталога capability; Claude enabled-set `unknown`; Claude-проекция `workflow-craft`; расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).
- **`review_policy.py`'s `LoopBudget`/`review_transition` — in-process, без persisted cross-session состояния.** P2.5 (historical failure scenarios end-to-end) — владелец доказательства реальной многосессионной/многовызовной последовательности против этой политики, не P2.3 (Pending Work item'а).

**Workarounds/Deferred/Open questions:**

- **workarounds:** нет новых этим item'ом (companion-коммит `79341e31` для `provider-commands.md` — process-резолюция P2.2, не изменение поведения, унаследовано).
- **deferred:** протухшая строка фазы P0 в §4; структурный фикс `check_collision_owners`/`remediation-map.json` (включая отсутствие `provider-commands.md` в owner-карте P2.2); `command.interactive-user-input`; Claude-проекция `workflow-craft`; расхождение провенанса harness-CLI ↔ maind-адаптера; исторический A2-долг (порядок base-sha теперь закрыт по факту исполнения P2.2/P2.3, но сама находка A2 формально вне скоупа authority D — остаётся названным долгом до отдельного решения владельца).
- **open_questions:** нет открытых для владельца — по D50 развилки закрываются записью.
