# HANDOFF — 2026-07-26 — after P2.2

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.3

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Context | `same-session — item` |
| Суть | Реализовать typed finding/review enforcement и loop breaker поверх независимо-зелёного P2.2 compiler'а |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.3

РЕЖИМ: исполнение детализированного item'а (P2.3 ⬜, P2.2 закрыт 🟢 коммитами `08e787b8` (Files) + `79341e31` (companion) — не реопен, не повторный дизайн).
ВХОД: phases/P2.md § P2.3 (ТЗ) → его Required Reads в объявленном порядке. Свежие входы: `packages/task/lib/task/task_contract.py` (независимо-зелёный компилятор, его policy hook — точка расширения), `artifacts/P2.1/state-transition-cases.json::review_policy` (типы находок/severity/reopen-предикат уже машиночитаемы).
СКОУП: 1) D36-baseline `assert_generated_scope.py baseline --owner P2.3 … --capture-or-verify` ПОСЛЕ Required Reads и ДО любой другой записи item'а; 2) `packages/task/lib/task/review_policy.py` + `test_review_policy.py` — ТОЛЬКО ПОСЛЕ pre-mutation гейта (не cold-start prerequisites); 3) расширить P2.2 compiler на его approved policy hook, НЕ править `packages/task/commands/*.md`/`plan-protocol` канон повторно (P2.2 — единственный владелец их бампа); 4) typed `finding_id` (seam-derived, split-ban), reopen-предикат (product/security-blocker/evidence-invalidates-acceptance), `same_finding_max=2` → третий → INCIDENT без inline-ремонта; 5) task plugin/routing bump `0.4.0 → 0.5.0`, полная регенерация adapters/locks/golden/marketplace (тела команд не меняются — второй прогон обязан быть no-op даже так); 6) `bash packages/task/scripts/validate.sh` зелёный, `assert_generated_scope.py generated-scope` без failures.
НЕ ТРОГАТЬ: `packages/task/commands/*.md` и `plan-protocol` канон повторно (владелец P2.2, единый бамп 2.11.0→2.12.0 уже закрыт — второй edit той же версии — гонка); `packages/task/lib/task/task_contract.py`'s core-предикаты (compiler остаётся независимо-зелёным, P2.3 только зовёт его policy hook); замороженные P0/P1/P2.1-контракты и их artifacts/**; `artifacts/P2.2/base-sha.txt` (владелец P2.2).
```

**Done:**

- **P2.1 закрыт 🟢** (три контракта запечатаны, машина 135/135 ячеек) — детали `phases/P2.md` P2.1 Completion Notes.
- **P2.2 закрыт 🟢** (2026-07-26, `task:plan-run` под **sonnet/high** = предписанный §3 Routing `implementation/high`, точное совпадение). Произведено:
  - `packages/task/lib/task/task_contract.py` — единый компилятор content-hash/precedence-conflict/12 pre-mutation + 3 pre-final кодов (`task-contract-v1.md`, цитируется, не пересказывается) + tier-классификация/lint `plan-portability-v1.md` (новый код `PORTABILITY_TIER_MISCLASSIFIED`, сверен с `artifacts/P2.1/state-transition-cases.json::new_reason_codes`). 38/38 юнит-тестов, включая table-driven сверку с P2.1's `portability_cases`.
  - `plan_lint.py` — tiered-portability lint (`_lint_tiered_portability_22`): ROLE-тест позиционный (Inputs/Required Reads/Validation), НЕ substring `tmp/` (D47); severity-cutoff `PORTABILITY_TIER_CANON_DATE = "2026.07.27"` (форвард-дата — fleet-замер вскрыл 58 ERROR в чужих планах `2026.07.18-FOREMAN`/`2026.07.25-ECO-OPT`, задокументировано D69). 176/176 тестов `test_plan_lint.py` (168 + 8 новых `TestTieredPortability`).
  - `packages/task/commands/{plan-exec,plan-close,plan-audit,plan-design}.md` — cross-reference абзацы к компилятору на pre-mutation/pre-final чекпоинтах.
  - Версии: `plan-protocol@2.12.0`, `skiller@0.5.0` (package API + `general`/`core` units), `task` plugin/routing `@0.4.0`. Полная регенерация: `render-provider-commands.py --write --repair-owned` (12 Claude + 24 Codex) → `--check` no-op; `skiller registry` → `registry --check` актуально; `claude-command-golden/`+`docs/reference/provider-commands.md` синхронизированы вручную (не покрыты `--write`, оба проверены зелёными тестами).
  - Diff-scope guard: `failures: []`, `undeclared_drift: []` на топологии из ДВУХ атомарных коммитов внутри шага 1 — `79341e31` (companion, `provider-commands.md`, вне owner-набора P1.1's `remediation-map.json`) ДО item-коммита `08e787b8` (ровно declared Files, `own_commits`).
  - Self-conformance (D47): `plan-lint plans/2026.07.24-AGENT-RELIABILITY` — **0 ERROR / 1 WARN** (WARN — предсуществующий, Update Log длина); fleet-wide `bash packages/task/scripts/validate.sh` — **0 ERROR / 215 WARN** (было 95 WARN на baseline, 120 новых — все legacy-severity от tiered-portability, 0 новых ERROR).
  - `## 7. Contracts § Exported`: три строки `plan-protocol@2.12.0`/`skiller@0.5.0`/`task@0.4.0` переведены `planned P2.2 → committed P2.2 (08e787b8)`; долг зеркальной `Consumed`-строки `2026.07.25-ECO-OPT` уже снят D58 (его D85) — новое уведомление не требуется.

**Remaining:**

15/22 items. P2: 2/5 (P2.3 → P2.4 → P2.5, все `solo` по `roadmap.md`) → P3 (5) → P4 (3).
Все items P2 детализированы; повторный дизайн-заход не требуется.

**Sources of truth:**

`plan.md` v1.14.1 (§3 Routing, §4 Status Board, §5 D69, §7 Contracts) ·
`phases/P2.md` § P2.2 Completion Notes (факты закрытия) ·
`packages/task/lib/task/task_contract.py` · `packages/task/lib/task/plan_lint.py`
`_lint_tiered_portability_22` · `roadmap.md` § P2.3 · `journal.jsonl`.

**Open risks:**

- **Строка фазы P0 в `plan.md` §4 всё ещё протухла** (унаследовано от P2.1's handoff — этим item'ом не правилось, чужая поверхность И2): `🟡 In progress` при четырёх терминальных items. Владелец правки — `task:plan-close 2026.07.24-AGENT-RELIABILITY P0`.
- **`packages/task/docs/reference/provider-commands.md` не входит в `artifacts/P1.1/remediation-map.json::owners.P2.2.paths`**, хотя детерминированно порождается той же командной канонизацией, что и объявленные Files (D69 Known Deviations). Companion-коммит `79341e31` — рабочая резолюция; настоящая потребность в правке карты владения — за P1.1 (D#).
- `check_collision_owners` структурно несовместим с фазовой ремедиацией — без изменений с P2.1.
- Прежний долг: две находки A2 (порядок capture `base-sha` — владельцы P2.2/P2.3, ЧАСТИЧНО закрыто этим item'ом: `assert_generated_scope.py baseline --capture-or-verify` теперь прогнан ПОСЛЕ Required Reads, ДО первой записи, как D36 предписывает — P2.3 обязан следовать тому же порядку); `research/01–03` без ссылок на слой 1; A1 F11; `command.interactive-user-input` вне каталога capability; Claude enabled-set `unknown`; Claude-проекция `workflow-craft`; расхождение провенанса harness-CLI ↔ maind-адаптера (P0.4).

**Workarounds/Deferred/Open questions:**

- **workarounds:** companion-коммит `79341e31` для `provider-commands.md` вне declared Files (D69, Known Deviations phases/P2.md P2.2) — процессная резолюция diff-scope guard, не изменение поведения.
- **deferred:** протухшая строка фазы P0 в §4; структурный фикс `check_collision_owners`/`remediation-map.json` (включая отсутствие `provider-commands.md` в owner-карте P2.2); `command.interactive-user-input`; Claude-проекция `workflow-craft`; расхождение провенанса harness-CLI ↔ maind-адаптера; две находки A2 (одна частично закрыта).
- **open_questions:** нет открытых для владельца — по D50 развилки закрываются записью.
