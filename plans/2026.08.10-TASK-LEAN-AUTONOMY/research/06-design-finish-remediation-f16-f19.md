# Design-finish reconciliation — F16–F19

Дата: 2026-08-11.

## Источники

- `findings/03-design-audit-2026-08-10.md` — audit заход 3 и repair contracts F16–F19.
- `research/04-field-canary-protocol.md` — прежний scorecard без no-event outcome.
- `research/05-design-finish-remediation-f11-f15.md` — D9 и предшествующая reconciliation.
- root `AGENTS.md` и worktree `plan-protocol` v2 — committed SSOT, single root changelog и
  generated-view boundaries. RAG:— (repo-grounded: перечисленные carriers).

## Reconciliation

| Finding | Закрытие в ТЗ | Acceptance carrier |
|:--|:--|:--|
| F16 committed SSOT | complete target-plan stable/generated carriers коммитятся отдельно от foreign ARTIFEX, `docs/reference.md`, root `roadmap/` и `plans/ACTIVE.md`; gates повторяются на полученном git-ref | clean target-plan diff + targeted lint/citations/views/bundles/contracts at committed ref |
| F17 no-event canary | D10 назначает один real P1.2 live window и два exact `not-observed` значения; bounded replay остаётся сравнением, не canary runtime | `findings/P1.2-field-canary.md` scorecard с `local_repair` и `material_review` closed values |
| F18 release ledger | P1.1 владеет factual root `[Unreleased]` записью до D9; P1.2 не пишет changelog и ADJUST не отменяет запись | P1.1 Files/Validation/Deliverables + D10 ADJUST rule |
| F19 index | индекс связывает refinements, audit, research-05/06 и D9/D10 с P1 | `index.md` без status/Next duplication |

## Invariants preserved

D1–D9 не отменены и не ослаблены. P0/P1 не исполняются в design-finish. Package/product code,
foreign ARTIFEX, dirty `docs/reference.md`, root `roadmap/` и `plans/ACTIVE.md` не входят в write
или commit scope. Generated state/status/decision/bundle views обновляются только owner generator.

## Post-commit gate repair

Первый commit `a9812f07` оказался не финальным: после последней bundle generation был удалён один
лишний EOF blank line из этого stable research carrier, но `bundles/P1.2.json` не был повторно
собран. Git-ref `--check` честно вернул stale digest. Причина — нарушенный projection order после
editorial edit, не смена provenance class. Fixing commit регенерирует bundle после последнего
stable byte, повторяет gates на новом git-ref и сохраняет первый commit в истории.
