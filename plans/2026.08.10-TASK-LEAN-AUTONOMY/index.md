# Индекс плана — `plans/2026.08.10-TASK-LEAN-AUTONOMY/index.md`

**Обновлён:** 2026-08-11

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | стабильный contract и routing |
| `status.md` | generated owner view |
| `phases/<Pn>/<Pn>.md` | контекст и индекс фазы |
| `phases/<Pn>/<Pn.m>.md` | стабильное ТЗ пункта |
| `phases/<Pn>/<Pn.m>.state.md` | generated item state |
| `bundles/<Pn.m>.json` | generated ordered executor input |
| `decisions/` | решения и generated views |
| `brief/` | исходное намерение и уточнения владельца |
| `findings/` | repo evidence и external RAG |
| `research/` | синтез целевой operating model |
| `roadmap.md` | exact package-cwd карта solo launches, включая successor P2 |
| `handoff.md` | rolling next pointer |
| `journal.jsonl` | append-only execution history |
| `root/contracts/read-budget-v1.md` | plan-owned frozen D15 admission contract |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `brief/00-brief.md` | brief | P0, P1 | граница строгого каркаса и свободного execution |
| `brief/01-refinements.md` | brief | P0–P2 | compact/field-first acceptance, remediation F1–F20, telemetry и owner quality directive |
| `findings/01-repository-problem-map.md` | findings | P0.1, P0.2, P1.1 | конкретные противоречия и размер текущего процесса |
| `findings/02-external-rag.md` | findings | P0.1, P0.2 | verified design patterns и первичные источники |
| `findings/03-design-audit-2026-08-10.md` | findings | design-finish | три RED audit-захода и F1–F19 |
| `findings/04-design-finish-remediation-2026-08-10.md` | findings | audit design | deterministic remediation evidence |
| `findings/05-inline-audit-repair-friction.md` | findings | P0.2, P1.1, P1.2 | field feedback: audit bookkeeping repair stays in the same attempt |
| `findings/06-cross-project-execution-telemetry.md` | findings | P0.1–P1.2 | all available Agelto/SKM plans, journals, run reports, causes and real stop counterexamples |
| `findings/08-p1-read-budget-and-preflight.md` | findings | P1 | missing read-budget diagnosis, environment preflight and D9+D13 waiting evidence |
| `findings/09-p1-read-budget-measurement.md` | findings | P1 | D15 qualified unit, per-item/aggregate result and D74 anti-displacement answer |
| `findings/10-p1-final-audit-root-causes.md` | findings | P2.1, P2.2 | воспроизводимые причины семи Major findings и границы package ownership |
| `research/01-target-operating-model.md` | research | P0.1–P1.2 | единый strict-frame/adaptive-loop contract |
| `research/02-design-finish-reconciliation.md` | research | P0.1–P1.2 | package ownership, routing, GO/ADJUST, bundle policy |
| `research/03-task-transition-map.md` | research | P1.1 | bounded Task change map |
| `research/04-field-canary-protocol.md` | research | P1.2 | bounded field selectors and GO predicates |
| `research/05-design-finish-remediation-f11-f15.md` | research | P1.1, P1.2 | context/docs/D9/RAG/journal reconciliation F11–F15 |
| `research/06-design-finish-remediation-f16-f19.md` | research | P1.1, P1.2 | committed SSOT, real canary, release ledger и index reconciliation |
| `research/07-adaptive-failure-and-telemetry-synthesis.md` | research | P0.1–P1.2 | D12 decision table, D13 lean observability and verified Perplexity follow-up |
| `research/08-p1-design-premortem.md` | research | P1 design | 6–12 month failure clusters, owners and existing D15/D16/D9/D13 mitigations |
| `research/09-p2-quality-remediation-design.md` | research | P2.1–P2.3 | successor sequence, red-first cases, anti-shortcuts и requalification gates |
| `decisions/D9-external-ledger-prerequisite.md` | decision | P1.2 | owner-owned committed external-ledger prerequisite |
| `decisions/D10-field-canary-and-release-ledger.md` | decision | P1.1, P1.2 | exact no-event values и pre-D9 `[Unreleased]` owner |
| `decisions/D11-inline-nonmaterial-audit-repair.md` | decision | P0.2, P1.1, P1.2 | non-material audit bookkeeping repair inline без нового цикла |
| `decisions/D12-evidence-first-stop-taxonomy.md` | decision | P0.2, P1.1, P1.2 | actual-impact classification; terminal only acceptance/safety/authority |
| `decisions/D13-idempotent-correlated-lifecycle.md` | decision | P0.1, P1.1, P1.2 | repository-root reports, joined identity and idempotent close |
| `decisions/D14-preclose-audit-and-item-reconciliation.md` | decision | P1.1 | terminal items → candidate → fresh GREEN audit → phase close |
| `decisions/D15-read-budget-consumption.md` | decision | P1.1, P1.2 | consume unchanged frozen read-budget v1.1.0 without reopening P1.1 |
| `decisions/D16-go-through-preclose-audit.md` | decision | P1.2 | supersedes D8 GO direct-close branch; candidate audit precedes P1 close |
| `decisions/D17-bounded-audit-recovery.md` | decision | P1.1, P1.2 | замороженный cap: финальный RED P1 не переоткрывается |
| `decisions/D18-successor-remediation-after-p1-red.md` | decision | P2.1–P2.3 | owner-authorized rejection of debt and successor remediation boundary |
| `decisions/D19-p2-1-provider-parity-ownership.md` | decision | P2.1 | exact Files correction for context-enum parity regression |
| `decisions/D20-v2-write-site-forward-only-cutoff.md` | decision | P2.1 | v2 activation cutoff without retroactive P0/P1 mutation |
| `decisions/D21-p2-1-review-remediation-ownership.md` | decision | P2.1 | isolated-review scope amendment for tracked aggregate and canonical v2 phase completeness |
| `decisions/D21-p2-1-review-remediation-ownership.md` | decision | P2.1 | isolated-review scope amendment for tracked aggregate and canonical v2 phase completeness |

## Ключевые артефакты `root/`

`root/contracts/read-budget-v1.md` — plan-owned frozen copy v1.1.0 по D15. Она потребляется
Task admission до P1.2 и не меняет локальное решение D2 про repair envelope.
