# Индекс плана — `plans/2026.08.10-TASK-LEAN-AUTONOMY/index.md`

**Обновлён:** 2026-08-10

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
| `roadmap.md` | exact package-cwd карта четырёх solo launches |
| `handoff.md` | rolling next pointer |
| `journal.jsonl` | append-only execution history |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `brief/00-brief.md` | brief | P0, P1 | граница строгого каркаса и свободного execution |
| `brief/01-refinements.md` | brief | P1.2 | compact/field-first acceptance |
| `findings/01-repository-problem-map.md` | findings | P0.1, P0.2, P1.1 | конкретные противоречия и размер текущего процесса |
| `findings/02-external-rag.md` | findings | P0.1, P0.2 | verified design patterns и первичные источники |
| `findings/03-design-audit-2026-08-10.md` | findings | design-finish | RED audit F1–F10 |
| `findings/04-design-finish-remediation-2026-08-10.md` | findings | audit design | deterministic remediation evidence |
| `research/01-target-operating-model.md` | research | P0.1–P1.2 | единый strict-frame/adaptive-loop contract |
| `research/02-design-finish-reconciliation.md` | research | P0.1–P1.2 | package ownership, routing, GO/ADJUST, bundle policy |
| `research/03-task-transition-map.md` | research | P1.1 | bounded Task change map |
| `research/04-field-canary-protocol.md` | research | P1.2 | bounded field selectors and GO predicates |

## Ключевые артефакты `root/`

План не создаёт долгоживущих frozen contracts; целевой смысл остаётся в skill/commands и D1–D8.
