# 2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION — План №1 — Рационализация swissknifeman по измеренной ценности

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION |
| Short ID | PLAN1 |
| Title | План №1 — Рационализация swissknifeman по измеренной ценности |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high |
| Repository | swissknifeman |
| Related Packages | core · task · skiller · harness · maind · analyst |
| Execution Mode | design-all → global design audit/fixes → evidence-gated execution |
| Target Operator Classes | P1–P3: frontier/high (Cursor `Grok 4.6`; Codex `gpt-5.6-sol/high`); P4: implementation/high (Cursor `Composer 2.5`; Codex `gpt-5.6-terra/high`); P5: selected only after terminal P4 GO-manifest admission by D8 |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| Design Passes | master 1/1; P1–P5 detail; one global audit plus one bounded contract-fix pass before execution |
| visibility | private |
| Paused By | — |

## 1. Context

Perplexity-аудит `audits/2026-09-20-perplexity.md` предлагает радикально упростить
постоянный контекст, Task, skills, provider parity и maind, но сам аудит не видел локальный
репозиторий и не мог измерить реальный эффект. Этот план превращает его в пять
крупных фаз: перепроверка и baseline; отдельный field audit corex, agentools
и edufy; измерение maind memory/code graph; отбор упрощений; внедрение только
доказавших ценность срезов. До первого execution все пять фаз детализируются,
затем один сквозной design audit фиксирует P1–P4 models/batches/review,
правило post-P4 выбора P5 и профильные поправки. Exact P5 route/review
фиксируются лишь после terminal P4 GO-manifest admission. RAG:— для
repository facts; RAG:✅ 2026-09-20 для
внешних предпосылок, перечисленных в `findings/00-design-baseline.md`.

## 2. Execution Rules

- Снача P1–P5 последовательно детализируются отдельными `task:plan-design`; закрытие predecessor execution не требуется для design, но сами evidence/output остаются жёсткими DoR-gates для execution.
- Каждая детализация имеет три ограниченных захода: evidence, contract, seal/lint; это не три полных аудита.
- После seal P5 один global design audit проверил весь план как единый contract, а не отдельную фазу.
- Global audit запечатал для P1–P4 solo batches, dependency order, semantic class/effort, Cursor- и Codex-native routes, capabilities/context и review; для P5 запечатано только детерминированное правило D8.
- Exact P5 route/review материализуются отдельным post-P4 admission только после terminal GREEN P4 и nonempty digest-bound GO manifest; неразрешённый manifest не получает default route.
- Найденные audit defects исправляются в owning phase/decision одним bounded contract-fix pass; затем повторяются focused audit checks. Незакрытая находка блокирует execution, а не создаёт бесконечный цикл.
- До GREEN глобального audit и регенерации Routing/bundles ни один `plan-run`, product write или consumer write не разрешён.
- Внешние изменяющиеся тезисы повторно проверяются Perplexity и обычным web search; несущие выводы открывают первичные источники.
- Field audit всегда read-only: consumer repository bytes читаются только из git-tracked files, без секретов, vendor/generated и без записи в грязные деревья corex/agentools/edufy; managed provenance-preserving run-report stores являются явным read-only исключением и не считаются consumer repository bytes.
- Нулевая telemetry — evidence gap, не доказательство нулевой ценности; сначала проверяются coverage и provider parity измерения.
- Новый механизм попадает в P5 только при measured failure и дешёвом enforcement; иначе — keep, disable, delete или roadmap trigger.
- Измерительная программа ограничена малым matched corpus и практическими effect sizes; статистическая лаборатория и full test programme вне scope.
- Продуктовые изменения валидируются focused и affected-package checks; fleet/release расширяются только на реальной integration/release границе.
- Чужие изменения и исходные dirty trees видимы, но не входят в кандидат и не подлежат cleanup.
- Никакого release, push, deployment, consumer rollout или изменения branch protection без отдельного owner authority.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| solo | P1.1 | frontier/high | manual | none | recommended: wide external/repository evidence packet, browser-backed Perplexity plus ordinary web verification and one shared baseline/measurement context make a separate routed run cheaper than rereading; product writes remain forbidden |
| solo | P2.1 | frontier/high | manual | light | recommended: один bounded multi-case packet с общей rubric, тремя изолированными read-only findings и последующим synthesis требует wide cross-project evidence context; execution route запечатывает общий design audit |
| solo | P3.1 | frontier/high | manual | light | recommended: measurement contract для memory/code graph и provider telemetry gap |
| solo | P4.1 | implementation/high | manual | light | recommended: bounded repo-local experiments и go/keep/defer/reject portfolio |
| solo | P5.1 | implementation/high | manual | light | recommended: эта строка задаёт лишь lower-bound для post-P4 выбора; exact model/effort/review фиксируются по D8 после terminal GO-manifest admission |

> Global design audit подтвердил solo batching и эти semantic rows для P1–P4.
> Provider projections additive: `frontier/high` = Cursor `Grok 4.6` или Codex
> `gpt-5.6-sol/high`; `implementation/high` = Cursor `Composer 2.5` или Codex
> `gpt-5.6-terra/high`. Exact P5 route/review появляются только после terminal P4 admission по D8.

## 5. Decision Log

Каталог решений: `decisions/`; собрать: `python3 packages/task/scripts/plan-views.py decisions`.
