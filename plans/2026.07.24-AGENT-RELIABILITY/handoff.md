# HANDOFF — 2026-07-26 — after P2.7

**Next:** design-item: task:plan-design 2026.07.24-AGENT-RELIABILITY P2.7

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `high` |
| Capabilities | `—` |
| Context | `cold-start — plan-step` |
| Model | Claude Opus |
| Thinking | `high` |
| Суть | P2.7 🔴 Blocked: review-заход остановил ремонт D70 — `plan-close.md` шаг 4 (pre-final) не fail-closed по факту (`("allow","n/a")` зеленит код упавшего `pre_mutation`), канон `plan-protocol@2.13.0` §13 утверждает больше факта (рецидив F1). Design-заход выбирает семантику route-оси при pre-final и чинит предикат — НЕ следующий item ремонта |

```
/task:plan-design 2026.07.24-AGENT-RELIABILITY P2.7

РЕЖИМ: ремедиация — починить `plan-close.md` шаг 4 (fail-closed на любом коде, отличном от
  `allow`, включая `n/a`) и внятную семантику route-оси при pre-final; привести §13 обеих
  языковых версий канона и литеральный тест `test_canon_literals.py` в соответствие с
  починенным фактом; пересмотреть статус P2.7 (материальный предикат требует минимум 🟠).
ВХОД: `plans/2026.07.24-AGENT-RELIABILITY/phases/P2.md` § P2.7 (Pending Work + Escalation
  Needed, полная запись остановки) → cold-start read ПЕРВЫМ.
СКОУП: 1) design-решение по route-оси pre-final (какой route подставлять, когда сессионный
  пин ниже минимума §3 Routing — новый route-литерал / отдельная проверка / снятие оси из
  pre-final-предиката); 2) фикс `plan-close.md` шаг 4 — exit 1 на ЛЮБОМ коде кроме `allow`;
  3) правка §13 SKILL.md/SKILL.ru.md + литерального теста под починенный факт; 4) пересчёт
  статуса P2.7 по status-rule (material: Scope исполнен иначе + acceptance не выполнен).
НЕ ТРОГАТЬ: `packages/task/lib/**` (владелец P2.6, закрыт); P2.8/P2.9 ТЗ (стартуют только
  после терминального P2.7); `plan-exec.md` шаг 2 (pre-mutation) — по находке review работает
  честно, чинить не за что.
```

> Строгая последовательность ремонта D70: P2.6 → P2.7 → P2.8 → P2.9. P2.7 остановлен на
> review (не design-, не audit-заходе) — 🔴 Blocked, Escalation Needed = yes. **P2.8/P2.9 НЕ
> СТАРТУЮТ** до терминального P2.7 (P2.8 потребляет Deliverables P2.7).
> Фоновый workflow-скрипт `plans/2026.07.24-AGENT-RELIABILITY/workflows/
> wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся) НЕ применим,
> пока P2.7 не терминален.

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`): `task_contract.build`/`bundle_lint`,
  `review_policy.LoopBudget.from_committed`, `canonical_actor` с моделью (D72), `task@0.6.0`.
- **P2.7 (item-коммит `d11c3b74`) частично доставлен, ОСТАНОВЛЕН review-заходом — 🔴 Blocked**
  (переклассифицирован из 🟢, код НЕ откатывается): write-site подключён в оба чекпоинта,
  `plan-run.md`/`plan-audit.md` синхронно правлены, `source-evidence-template.md` доставлен,
  §13 канона переписан + литеральный тест, публикация `plan-protocol@2.13.0`/`skiller@0.6.0`/
  `task@0.7.0` регенерирована и no-op на `--check` — эта часть НЕ откатывается. Дефект: pre-
  final (`plan-close.md` шаг 4) вычисляется как `n/a` на КАЖДОМ реальном прогоне (собственный
  пин команды `implementation/low` отсутствует в §3 Routing → `block:ROUTE_UNDERSHOOT`) и
  `("allow","n/a")` объявляет этот код зелёным — предикат нефальсифицируем, канон утверждает
  больше факта. Полная запись — `phases/P2.md` § P2.7 Pending Work/Escalation Needed.
- **D74 (измерено при исполнении, остаётся в силе):** CLI-форма `task_contract build` держит
  `route.actual` неразрешённым по конструкции — скормленный в `check` такой контракт роняет
  `pre_mutation` необработанным `ValueError` (`.index(None)`), а не типизированным кодом.
  Write-site зовёт компилятор его же документированным Python API
  (`build(..., actual_route=…)` + `evaluate`) вместо литерального shell-пайпа — тот же
  параметр, которым уже пользовался self-conformance P2.6. Форма вызова не оспаривается
  review-заходом; оспаривается только fail-closed-поведение шага 4.

**Remaining:**

- **P2.7** 🔴 — design-заход (этот launch-block) чинит `plan-close.md` шаг 4 + канон + статус;
  ПЕРВЫЙ следующий шаг, всё остальное блокировано им.
- **P2.8** ⬜ — заблокирован P2.7 (потребляет его Deliverables): закоммиченный
  детерминированный генератор транскриптов, перепрогон замороженного банка P2.5,
  честный `covered`. НЕ СТАРТУЕТ.
- **P2.9** ⬜ — заблокирован P2.7/P2.8: бухгалтерия F6, F7, F10–F15 без мутаций кода
  (включая приведение строки §7 Exported `task` plugin/routing к финальному факту
  v0.5.0-остатка, `plan.md:411`). НЕ СТАРТУЕТ.
- После терминальных P2.6–P2.9 — `task:plan-close … P2` (снимает маркер «УСТАРЕЛ»,
  пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta, §3 Routing (строки P2.6–P2.9), §4 Status Board (P2 = `6/9 🔴 Blocked`),
  §5 D70–D74, §7 Contracts (P2.7-строки — `committed`, но материально неполные).
- `phases/P2.md` — блок `## Audit P2 — 2026-07-26` (15 находок), P2.6 Completion Notes,
  **P2.7 Status/Pending Work/Escalation Needed (эта остановка, дословная запись)**, ТЗ
  items P2.8–P2.9.
- `findings/P2.6-contract-mapping.md` — таблица отображения полей item'а на ключи Task
  Contract v1.
- `packages/skiller/skills/general/plan-protocol/snippets/source-evidence-template.md` —
  исполнимая форма bundle-требований (доставлено P2.7, не откатывается).
- `research/07-p2-reopen-remediation.md` — раскладка ремонта, контракт цепочки, границы,
  pre-mortem.
- `roadmap.md` — carrier'ы P2.6–P2.9; `journal.jsonl` — записи прогонов.

**Open risks:**

- **Рецидив F1 в уменьшенном масштабе.** Канон `plan-protocol@2.13.0`, уже раздаваемый
  флоту через `general`/`core`, утверждает «fail-closed on any code other than allow» —
  факту не соответствует до фикса. Пока канон не поправлен, downstream-читатель получает
  ложную гарантию.
- **Cap аудитов.** `## Audit P2` — заход 1 из двух. Третий заход по канону — не
  автоматический раунд, а решение. Текущая остановка — review-заход, НЕ аудит-заход,
  третий design/audit-цикл не расходуется.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.7 (как P2.6/P2.8/P2.9) отсутствует в
  `remediation-map.json::baseline_owners` → `assert_generated_scope.py` не запускается;
  компенсация — ручная сверка `git show --stat d11c3b74` против `Files`.

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с `PROMOTE-CANDIDATE`.
- **Fresh-subagent dispatch** остаётся недоставленной позицией Scope P2.2; владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** (не описывает write-site P2.7/compiler-модули
  P2.2–P2.6) — долг остаётся, естественный владелец — P3.1 по D#-записи; наследуется design-
  заходом P2.7, если тот решит его подобрать, иначе остаётся отдельным долгом.
- **`plan.md` §4, строка фазы P0`** — `🟡 In progress` при четырёх терминальных items —
  предсуществующий дефект бухгалтерии P0.4, владелец — `task:plan-close … P0`; НЕ правится
  ремонтными items P2 (чужая поверхность, И2).
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) — предсуществующий,
  чужой владелец, не блокер.
- **Побочный workflow-артефакт вне Files** (carve-out `plans/<PLAN-ID>/**`):
  `workflows/wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся) —
  НЕ применим, пока P2.7 не терминален.
