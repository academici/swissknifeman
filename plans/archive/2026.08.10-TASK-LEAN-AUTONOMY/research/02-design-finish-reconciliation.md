# Design-finish reconciliation — F1–F10

Дата: 2026-08-10.

## Источники

- `findings/03-design-audit-2026-08-10.md` — RED audit и repair contracts F1–F10.
- `findings/01-repository-problem-map.md` — исходная repo-grounded проблема.
- `findings/02-external-rag.md` — verified design patterns для D1–D4.
- root/package `AGENTS.md` — exact package-cwd, generated-artifact и validation rules.

## Reconciliation

| Hotspot | Решение | Носители |
|:--|:--|:--|
| Routing/Task Contract | четыре single-item Routing rows; grouping только в roadmap | `plan.md`, D7 |
| Package cwd | P0.1 Harness, P0.2 Skiller, P1.1 Task, P1.2 root | D7, item `Files`, roadmap launch blocks |
| Bounded writes | только exact source/test/doc paths; generated outputs — named owner generator | четыре item specs |
| Validation | exact copy-pastable commands + affected package `validate.sh` в каждом owning item | четыре item specs |
| GO/ADJUST | GO closes green; ADJUST stays nonterminal with one durable owner request and waiting Next | D8, P1.2, P1 phase handoff |
| Provenance | D1–D6 gain actor/model/evidence links; pass 1/2 and pass 2/2 append through journal | decisions, journal, generated status |
| Context budget | raw ledgers/foreign plans removed from Required Reads; bounded synthesis drives execution | research 03/04, bundles |
| Cold start | each executable carrier pins cwd/model/effort/approval/sandbox | `roadmap.md`, `handoff.md` |

RAG:— (repo-grounded: cited plan/audit/AGENTS carriers).

## Stop conditions

Finish is ready for a fresh audit only when: all four Task Contracts build; generated state,
status, decisions and bundles are byte-current; every bundle has zero repeated `(path, selector)`
entries; targeted lint/citations/conflicts are green; package validation is green; the complete
plan is committed without ARTIFEX/docs/roadmap/ACTIVE foreign changes.

