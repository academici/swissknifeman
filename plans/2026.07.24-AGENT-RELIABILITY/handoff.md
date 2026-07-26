# HANDOFF — 2026-07-26 — after P2.6

**Next:** P2.6 закрыт 🟢. Следующий шаг — **P2.7** (подключить write-site в командах
и сделать канон истинным): звонит уже готовые `task_contract.build`/`bundle_lint`
из тел `plan-exec`/`plan-close`, правит формулировку `plan-protocol@2.12.0` (F1),
создаёт `snippets/source-evidence-template.md`. Порядок строго последовательный:
P2.7 → P2.8 → P2.9; каждый следующий стартует только на терминальном предыдущем.

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `command.subagents` |
| Context | `continue (/clear) — ручной item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | P2.7: write-site `build → check` в `plan-exec.md`/`plan-close.md`, истинное утверждение `plan-protocol` §13, литеральный тест канона, `source-evidence-template.md`, `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`. Только `packages/task/commands/**` + канон — не трогает `packages/task/lib/**` (тело компилятора уже готово P2.6) |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P2.7
```

> Полные recovery-carrier'ы P2.7–P2.9 — `roadmap.md` §§ «P2.6…P2.9 (реопен D70)».
> Фоновый workflow-скрипт `plans/2026.07.24-AGENT-RELIABILITY/workflows/
> wf-agent-reliability-p2-7-9-remediation.js` (не запускался, не проверялся эту
> сессию) доступен как альтернативный batch-запуск P2.7→P2.8→P2.9 одной командой
> `Workflow({scriptPath: "…"})` — владелец решает сам, item-by-item или им.

**Done:**

- **P2.6 закрыт 🟢 Done** (item-коммит `a13614db`, bookkeeping — этот коммит):
  `task_contract.build(plan_dir, item_id, …)` — детерминированный producer
  Task Contract v1 из `phases/Pn.md` + `plan.md` §3 (таблица отображения —
  `findings/P2.6-contract-mapping.md`), типизированный отказ на пустом поле
  (`TaskContractBuildError`), CLI `python3 -m task.task_contract build --plan-dir
  … --item …`.
- `task_contract.bundle_lint(bundle_dir, manifest_path, verifier_path,
  declared_privacy)` — вычисляет минимизацию и классы содержимого (секреты/
  chain-of-thought/tool-payloads/raw-transcript-bodies) по факту байтов; два
  новых кода `BUNDLE_ARTIFACT_MISSING`/`BUNDLE_PRIVACY_MISMATCH`.
- `review_policy.LoopBudget.from_committed(plan_dir, phase_id, finding)` —
  восстанавливает per-finding счётчик из `journal.jsonl` + `## Audit Pn` с
  честным `"unknown"` вместо `0` (F5).
- `route_evidence.canonical_actor(model, effort)` — несёт модель, не класс
  (D72/F8, breaking-смена сигнатуры, единственный потребитель `journal.py`
  починен тем же item'ом); `capture_actual` получил опциональный `model=`.
- `task@0.6.0` — оба plugin.json + `command-routing.json`, полная регенерация
  (`render-provider-commands.py --write --repair-owned` → `--check` no-op,
  `skiller registry --check` — актуально), `claude-command-golden/plugin.json`
  синхронизирован вручную.
- **Self-conformance:** `build()` собран и прогнан allow/allow (`pre_mutation`/
  `pre_final`) для **P0.1**, **P2.1** и **P2.6** с живым `actual_route`,
  совпадающим с §3 Routing; байтовая детерминированность подтверждена.
- **Validation (9/9 пунктов, на `a13614db`):** `test_task_contract.py` 57/57 ·
  `test_review_policy.py` 51/51 · `test_route_evidence.py` 39/39 ·
  `test_journal.py` 26/26 · `test_plan_command_routing.py` 8/8 ·
  `render-provider-commands --check` no-op · `skiller registry --check`
  актуально · `bash validate.sh` OK (384 теста, fleet-wide plan-lint 0 ERROR /
  215 WARN — без изменения от базовой линии) · `plan-lint … --baseline
  756f5d83` — 0 ERROR / 1 WARN (предсуществующий), новых от рабочего дерева: 0.

**Remaining:**

- **P2.7** ⬜ — write-site в `plan-exec`/`plan-close`, истинный канон §13,
  `source-evidence-template.md`, `plan-protocol@2.13.0`/`skiller@0.6.0`/`task@0.7.0`.
- **P2.8** ⬜ — закоммиченный детерминированный генератор транскриптов, перепрогон
  замороженного банка P2.5, честный `covered`.
- **P2.9** ⬜ — бухгалтерия F6, F7, F10–F15 без мутаций кода (включая исправление
  строки §7 Exported `task` plugin/routing, названной в plan.md:409-410).
- После терминальных P2.6–P2.9 — `task:plan-close … P2` (снимает маркер
  «УСТАРЕЛ», пересобирает Phase Handoff), затем аудит фазы **заход 2/2**.
- **P3–P4** ⬜ — не стартуют до терминальной P2.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.15.1), §3 Routing (строки P2.6–P2.9), §4 Status Board
  (P2 = `4/9 🟡`), §5 D70–D73, §7 Contracts (P2.9 приводит строку `task`
  plugin/routing к факту).
- `phases/P2.md` — блок `## Audit P2 — 2026-07-26` (15 находок), P2.6 Completion
  Notes (полный список произведённого и self-conformance), ТЗ items P2.7–P2.9.
- `findings/P2.6-contract-mapping.md` — таблица отображения полей item'а на
  ключи Task Contract v1 (владеет P2.7's write-site — не пересказывать).
- `research/07-p2-reopen-remediation.md` — раскладка ремонта, контракт цепочки,
  границы, pre-mortem.
- `roadmap.md` — carrier'ы P2.6–P2.9; `journal.jsonl` — записи прогонов.

**Open risks:**

- **Риск повторения того же провала.** P2.7 обязан доказать write-site прогоном
  на реальных items ЭТОГО плана (не ссылкой на модуль) — `build`/`bundle_lint`
  теперь СУЩЕСТВУЮТ и протестированы, но их ещё НИКТО не зовёт из тела команды.
- **Cap аудитов.** `## Audit P2` — заход 1 из двух. Третий заход по канону — не
  автоматический раунд, а решение.
- **Дрейф генерируемых деревьев вне owner-карты.** P2.6 (как P2.7–P2.9)
  отсутствует в `remediation-map.json::baseline_owners` → `assert_generated_scope.py`
  не запускается; компенсация — `git show --stat a13614db` сверен вручную против
  `Files` (см. P2.6 Completion Notes).

**Workarounds / Deferred / Open questions:**

- **F9 (Minor) не чинится** — вне скоупа реопена, названный долг с
  `PROMOTE-CANDIDATE`.
- **Fresh-subagent dispatch** остаётся недоставленной позицией Scope P2.2;
  владелец — **P3.4**.
- **Docs-sync `packages/task/CLAUDE.md`** (не описывает compiler-модули P2.2–P2.6)
  — долг остаётся, естественный владелец — P2.7 либо P3.1 по D#-записи.
- **`plan.md` §4, строка фазы P0`** — `🟡 In progress` при четырёх терминальных
  items — предсуществующий дефект бухгалтерии P0.4, владелец —
  `task:plan-close … P0`; НЕ правится ремонтными items P2 (чужая поверхность, И2).
- **WARN `plan-lint` на `plan.md`** (длина строки Update Log P1.4) —
  предсуществующий, чужой владелец, не блокер.
- **Побочный workflow-артефакт вне Files** (carve-out `plans/<PLAN-ID>/**`):
  `workflows/wf-agent-reliability-p2-7-9-remediation.js` написан фоновым агентом
  по прямому запросу владельца в этой же сессии; не запускался и не проверялся —
  владелец сам решает, использовать batch-запуск или продолжать item-by-item.
