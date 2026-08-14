# 2026.08.14-№1-TASK-PHASE-CLOSE — План №1 — Task phase-close fast path, Slice A

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.08.14-№1-TASK-PHASE-CLOSE |
| Title | План №1 — Task phase-close fast path, Slice A |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high (`provider-thread-state`, verified 2026-08-14) |
| Repository | swissknifeman |
| Related Packages | task · skiller · aggregate docs |
| Execution Mode | phase-first, evidence-led |
| Target Operator Models | implementation (execution) · frontier (design/audit) |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Design Passes | 1/1 — 2 phases, 3 items, measured problem and bounded package scope |

## 1. Context

Slice A возвращает быстрый путь `terminal evidence → justified close` без ослабления
fail-closed semantics. Измеренный P1 инцидент показал, что один GREEN audit
одновременно виден delivery/lint и не виден close gate из-за legacy spelling subject.
Текущая first-audit policy также подменяет integration risk историческим `Review`
и числом items.

План вводит один handwritten `Phase Assurance | v1`, канонизирует audit subject на
write/read seams, даёт narrow direct close только isolated зелёным phases и после
package validation закрывает исходную P1 на её existing audit. Broader repeat-audit broker
и validation receipt reuse остаются в Slice B/C до их собственных triggers.

## 2. Execution Rules

- Работу в `packages/task/**` начинать из fresh `codex -C packages/task`; читать root и package AGENTS.
- `lib/task/` остаётся stdlib-only; один смысл имеет одного owner'а.
- Generated provider/registry/docs artifacts менять только owning generators и проверять `--check`.
- Старые journal rows append-only; legacy subject не переписывать.
- Valid assurance хешировать канонически, legacy absence не добавлять в digest.
- Latest audit evidence не обходится direct-close declaration'ом.
- Review и item count не входят в first-audit blockers; objective red/material evidence всегда гейтит.
- Slice A не проектирует typed impact/receipt/budget machinery из Slice B/C.
- P2.1 не изменяет P1 product carriers и не запускает P1 item Validation/audit.
- Каждый item закрывается двумя коммитами по plan-protocol: product, затем bookkeeping.
- Обычный local reversible defect исправлять в том же root; owner gate только для authority/safety/frozen scope.
- Перед handoff пройти affected package validation и root plan lint; не выдавать skipped check за green.
- Release-visible policy change записать в root `CHANGELOG.md [Unreleased]`.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| B1 | P1.1 | implementation/high | plan-exec | full | runtime/schema foundation и P1.2 делят package reads, policy seams и focused tests; public phase contract требует high/full |
| B1 | P1.2 | implementation/high | plan-exec | full | consumer/publication vertical продолжает P1.1 без повтора setup и закрывает provider parity/package validation |
| solo | P2.1 | implementation/high | plan-exec | full | cross-plan closure мутирует previously audited carriers только после committed P1 policy; phase/hard commit boundary делает context reuse unsafe |

## 5. Decision Log

Решения находятся в `decisions/`; собрать или проверить их виды:
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.08.14-№1-TASK-PHASE-CLOSE [--check]`.
