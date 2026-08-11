# 2026.08.10-TASK-LEAN-AUTONOMY — Lean Task autonomy

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.10-TASK-LEAN-AUTONOMY |
| Title | Lean Task autonomy |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high (semantic `task:plan-design` route; actual running selector/effort not independently attested) |
| Repository | swissknifeman |
| Related Packages | harness · skiller · task |
| Execution Mode | contract-first, adaptive execution |
| Target Operator Classes | implementation (execution) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Design Passes | 2/2; pass 1 — bootstrap/full detail, pass 2 — design-finish remediation F1–F10; post-audit finish закрыл F11–F19; final audit attempt 4 закрыл F20 inline и owner-requested Agelto/SKM telemetry refinement D12/D13 без нового design/audit pass; следующий шаг — P0.1 |
| Paused By | — |

## 1. Context

Task уже содержит полезные идеи локального repair и продолжения в owning-root, но его always-on
инструкции и plan-команды обросли буквальными стадиями, обязательными handoff и повторными
аудитами. В живых планах это создаёт десятки проходов и огромный повторно читаемый корпус.

План сохраняет строгий initial contract, но делает исполнение адаптивным внутри явного repair
envelope. Сначала сокращается instruction/skill/command surface и стабилизируется лёгкое run
evidence, затем исправляются только runtime-переходы, которые терминализируют procedural/
transient/dependency/unrelated signal без проверки actual impact. Приёмка проходит через полевой
canary, а не через новую исчерпывающую proof-систему.

## 2. Execution Rules

- Intent, acceptance, scope, safety и authority gates фиксируются до исполнения.
- Owning-agent может группировать соседние ready items и менять локальный порядок, сохраняя
  зависимости, наблюдаемый acceptance и границы решения D1.
- Обратимый дефект в scope исправляется сразу; minor/nit не создаёт отдельную сессию или аудит.
- До stop/retry действует D12: `observe → minimal reproduce → classify → act → verify`; raw tool,
  status, dirty-tree, route или audit signal не является product outcome без actual impact.
- Procedural/transient/dependency-not-ready/unrelated-pre-existing продолжаются, repair'ятся или
  ждут bounded condition в том же attempt; terminal остаются только reproduced acceptance,
  safety и authority. Unknown non-idempotent write fail-closed до state reconciliation.
- Routing correction происходит до journal start; future carrier не блокирует producer;
  process terminalization требует PID/output/state check; inherited red оценивается по delta.
- Повтор одного failure fingerprint требует смены тактики и максимум одного scoped review.
- Новый audit/review требует записанного material trigger; прежний verdict переиспользуется,
  пока scope/SHA/risk не изменились.
- Non-material deterministic plan-bookkeeping defect из audit исправляется inline тем же root по
  D11; один gate rerun завершает тот же attempt без ATTENTION/re-audit/design-pass handoff.
- Owner stop обязателен для authority/security/privacy/destructive/irreversible, изменения
  acceptance или public/frozen semantics и доказанного no-progress.
- Проверки кода — safety net; продуктовый verdict требует живого canary из D5.
- Generated projections меняются только через owning generator.
- После принятого пункта обновляются journal, generated state/status и rolling handoff; отдельное
  закрытие фазы не запускается, если тот же root уже может продолжить ready item.
- D13 делает новый run evidence repository-root, start/terminal identity коррелируемым, а close
  идемпотентным; telemetry coverage gap не превращается в product RED.
- Полные ссылки на пункты в человеческом тексте используют форму
  `2026.08.10-TASK-LEAN-AUTONOMY Pn.m`.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| — | P0.1 | implementation/high | manual | full | Harness instruction canon, projections и D13 root run evidence: D4/D6 safety + fleet-wide lifecycle surface требуют high/full |
| — | P0.2 | implementation/high | manual | full | Skiller-owned D1–D4/D6/D11/D12 plan canon и provider projections: fleet-wide semantic surface требует high/full |
| — | P1.1 | implementation/high | manual | full | Task-owned D11–D13 command/runtime/lifecycle transitions и lint regressions: correctness-critical protocol surface требует high/full |
| — | P1.2 | implementation/high | manual | full | repository-root causal field verdict и stop-tax evidence: без product writes, но acceptance всего плана требует high/full |

## 5. Decision Log

Каталог решений: `decisions/`; generated views собираются через
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.08.10-TASK-LEAN-AUTONOMY`.
