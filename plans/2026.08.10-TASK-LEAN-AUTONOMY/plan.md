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
| Design Passes | 4/4; pass 1 — bootstrap/full detail, pass 2 — design-finish remediation F1–F20, pass 3 — owner-authorized successor P2 после финального RED P1, pass 4 — owner-authorized successor P3 по D23 после финального RED P2; D24 добавляет P3.3 forward fix; D17 не переоткрывается |
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
- Завершённые items делают фазу кандидатом, а не закрытой фазой: свежий зелёный audit этого
  кандидата предшествует `task:plan-close <PLAN-ID> Pn`. Первый RED либо unresolved `ATTENTION`
  разрешает ровно один repair-forward в явно названные owning items под неизменным ТЗ; terminal
  status не требует `plan-design`. Второй audit финальный: повторный non-GREEN — owner incident,
  третьего repair/audit/design-loop нет. Обычный Next никогда не предлагает `task:plan-close Pn.m`.
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
| — | P2.1 | implementation/high | manual | full | Task schema/command/verifier/docs-sync defects влияют на write-site и fail-closed guarantees |
| — | P2.2 | implementation/high | manual | full | Harness v2 driver и cross-package fixtures управляют исполнением планов; ошибка может направить агента по ложному Next |
| — | P2.3 | implementation/high | manual | full | Task status projection является owner-facing lifecycle truth; ложный Not started скрывает фактический прогресс и ломает agent routing |
| — | P2.4 | implementation/high | manual | full | root live canary и полная requalification являются acceptance всего successor-контракта |
| — | P3.1 | implementation/high | manual | full | Task fail-closed route, deterministic bundle и generated provider/docs truth влияют на каждый следующий plan-run |
| — | P3.3 | implementation/high | manual | full | official native launch provenance устраняет недостижимый provider probe только для manual plan-run |
| — | P3.2 | implementation/high | manual | full | root field requalification полного post-P2.3 anchor является acceptance D23 и не допускает product writes |

## 4. Update Log

| Date | Role / model | Change |
|:--|:--|:--|
| 2026-08-11 | owner-authorized repair design / gpt-5.6-terra/high | D24 добавляет P3.3: manual plan-run использует fresh native `-m` + `model_reasoning_effort` как честно названный launch provenance; provider telemetry и plan-exec не ослабляются. |
| 2026-08-11 | owner-authorized successor design / semantic gpt-5.6-sol/high | D23 отклоняет F1–F6 финального RED P2, замораживает P2 и создаёт P3.1/P3.2 с fail-closed Task remediation и новым product-free canary; actual selector/effort не аттестованы. |
| 2026-08-11 | plan-designer / gpt-5.6-sol/high | D22 вставляет Task-owned P2.3 status aggregation regression перед canary; прежний не начатый P2.3 становится P2.4 без переписывания terminal evidence. |
| 2026-08-11 | owner-authorized P2.1 review remediation / gpt-5.6-terra/high | D21 принимает Blocker/Major из isolated review: tracked aggregate генерируется, а v2 phase completeness проверяет canonical resolver. |
| 2026-08-11 | owner-authorized v2 forward-only activation / gpt-5.6-terra/high | D20 вводит отдельный v2 write-site cutoff 2026-08-12; immutable P0/P1 carriers не красятся задним числом. |
| 2026-08-11 | owner-authorized P2.1 contract correction / gpt-5.6-terra/high | D19 добавляет omitted provider parity owner/test в exact Files; acceptance и четыре root causes не меняются. |
| 2026-08-11 | owner-authorized successor design / gpt-5.6-sol/high | D18 отклоняет Major-долг финального RED P1, замораживает P1 и создаёт P2.1–P2.3 с package-owned remediation и новым live canary. |
| 2026-08-11 | owner-authorized lifecycle correction / gpt-5.6-sol/high | D17 устраняет off-by-one и конфликт RED→plan-design: один bounded repair между первым и финальным вторым audit. |
| 2026-08-11 | owner-authorized plan amendment / gpt-5.6-terra/high | Добавлен D14: phase candidate → fresh GREEN audit → phase close; `plan-close Pn.m` ограничен recovery reconciliation. |
| 2026-08-11 | plan-designer / gpt-5.6-sol/high | P1 доведена до DoR после P1.1: добавлен plan-owned frozen read-budget v1.1.0 по D15; P1.2 остаётся waiting на committed D9+D13 ledger. |

## 5. Decision Log

Каталог решений: `decisions/`; generated views собираются через
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.08.10-TASK-LEAN-AUTONOMY`.

## 7. Contracts

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| `root/contracts/read-budget-v1.md` | `2026.08.07-PLAN-ECONOMY` | v1.1.0 | v1.1.0 (2026-08-11) | D15 — plan-owned frozen copy; admission P1.1/P1.2 до P1.2 canary |
