# HANDOFF — 2026-07-26 — after P2.7

**Next:** run-items: task:plan-run 2026.07.24-AGENT-RELIABILITY P2.8

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | P2.8: сделать доказательство P2.5 (30/31) воспроизводимым из закоммиченных входов — детерминированный генератор транскриптов в `artifacts/P2.5/**`, перепрогон замороженного банка, честный `covered` (bundle-предикат P2.6 + template/канон P2.7, если кейс их читает) |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.8
```

> Полные recovery-carrier'ы P2.8–P2.9 — `roadmap.md` §§ «P2.6…P2.9 (реопен D70)».
> Фоновый workflow-скрипт `plans/2026.07.24-AGENT-RELIABILITY/workflows/
> wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся) доступен
> как альтернативный batch-запуск P2.8→P2.9 — владелец решает сам.

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 закрыт 🟢 Done** (item-коммит `d11c3b74`, bookkeeping — этот коммит):
  `plan-exec.md`'s Pre-mutation (шаг 2) и `plan-close.md`'s Pre-final (шаг 4) —
  ИСПОЛНЯЕМЫЕ, БЕЗУСЛОВНЫЕ write-site: каждый собирает Task Contract v1
  (`task_contract.build`) и проверяет (`task_contract.evaluate`), падая закрыто на любом
  коде, отличном от `allow`, с таблицей код→действие. `plan-run.md` подставляет наблюдаемый
  route сессии; `plan-audit.md` сверяет напечатанный результат в Completion Notes.
- **D74 (измерено при исполнении):** CLI-форма `task_contract build` держит `route.actual`
  неразрешённым по конструкции — скормленный в `check` такой контракт роняет
  `pre_mutation` необработанным `ValueError` (`.index(None)`), а не типизированным кодом.
  Write-site зовёт компилятор его же документированным Python API
  (`build(..., actual_route=…)` + `evaluate`) вместо литерального shell-пайпа — тот же
  параметр, которым уже пользовался self-conformance P2.6. Шаг остаётся обязательным и
  fail-closed; изменена только форма вызова.
- `snippets/source-evidence-template.md` — доставлен недостающий `Files` P2.2:
  bundle-манифест, команда верификации через `bundle_lint`, запрещённые классы содержимого.
- §13 канона (`plan-protocol@2.13.0`) переформулирован в истинное утверждение + новый
  параграф Evidence bundle; защищено литеральным тестом
  `TestTaskContractCanonClaimIsBackedByCommands` (`test_canon_literals.py`, 5 новых тестов).
- `plan-protocol@2.13.0` / `skiller@0.6.0` (package API + `general`/`core` units) /
  `task@0.7.0` — полная регенерация обеих публикаций
  (`render-provider-commands --check` no-op, `skiller registry --check` актуально,
  `check-translations.sh` чисто), `skm`/`repository-bootstrap` byte-identical.
- **Self-conformance:** write-site прогнан allow/allow (`pre_mutation`/`pre_final`) для
  **P2.1** (🟢), **P2.2** (🟠 — честный allow, разные оси предиката и статуса) и **P2.7**
  (текущий) с живым `actual_route`, совпадающим с §3 Routing.
- **Validation (10/10 пунктов, на `d11c3b74`):** `test_canon_literals.py` 10/10 ·
  `test_plan_command_routing.py` 8/8 · `test_task_contract.py` 57/57 ·
  `render-provider-commands --check` no-op · `skiller registry --check` актуально ·
  `check-translations.sh` чисто · `bash task/validate.sh` OK (388 тестов, fleet-wide
  plan-lint 0 ERROR / 215 WARN) · `bash skiller/validate.sh` OK (444 теста) ·
  `plan-lint … ` — 0 ERROR / 1 WARN (предсуществующий), новых от рабочего дерева: 0.

**Remaining:**

- **P2.8** ⬜ — закоммиченный детерминированный генератор транскриптов, перепрогон
  замороженного банка P2.5, честный `covered`.
- **P2.9** ⬜ — бухгалтерия F6, F7, F10–F15 без мутаций кода (включая приведение строки
  §7 Exported `task` plugin/routing к финальному факту v0.5.0-остатка, plan.md:411).
- После терминальных P2.6–P2.9 — `task:plan-close … P2` (снимает маркер «УСТАРЕЛ»,
  пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.15.2), §3 Routing (строки P2.6–P2.9), §4 Status Board
  (P2 = `5/9 🟡`), §5 D70–D74, §7 Contracts (P2.7-строки приведены к `committed`).
- `phases/P2.md` — блок `## Audit P2 — 2026-07-26` (15 находок), P2.6/P2.7 Completion
  Notes (полный список произведённого и self-conformance), ТЗ items P2.8–P2.9.
- `findings/P2.6-contract-mapping.md` — таблица отображения полей item'а на ключи Task
  Contract v1 (владеет write-site P2.7 — не пересказывать).
- `packages/skiller/skills/general/plan-protocol/snippets/source-evidence-template.md` —
  исполнимая форма bundle-требований (P2.7, недоставленный Files P2.2).
- `research/07-p2-reopen-remediation.md` — раскладка ремонта, контракт цепочки, границы,
  pre-mortem.
- `roadmap.md` — carrier'ы P2.6–P2.9; `journal.jsonl` — записи прогонов.

**Open risks:**

- **Cap аудитов.** `## Audit P2` — заход 1 из двух. Третий заход по канону — не
  автоматический раунд, а решение.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.7 (как P2.6/P2.8/P2.9) отсутствует в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается;
  компенсация — `git show --stat d11c3b74` сверен вручную против `Files` (см. P2.7
  Completion Notes).
- **P2.8 потребляет write-site P2.7** (bundle_lint/template, если её кейсы их читают) —
  первый реальный прогон вне self-conformance этого item'а.

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Fresh-subagent dispatch** остаётся недоставленной позицией Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** (не описывает write-site P2.7/compiler-модули
  P2.2–P2.6) — долг остаётся, естественный владелец — P3.1 по D#-записи.
- **`plan.md` §4, строка фазы P0`** — `🟡 In progress` при четырёх терминальных items —
  предсуществующий дефект бухгалтерии P0.4, владелец — `task:plan-close … P0`; НЕ правится
  ремонтными items P2 (чужая поверхность, И2).
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий,
  чужой владелец, не блокер.
- **Побочный workflow-артефакт вне Files** (carve-out `plans/<PLAN-ID>/**`):
  `workflows/wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся) —
  владелец сам решает, использовать batch-запуск или продолжать item-by-item.
