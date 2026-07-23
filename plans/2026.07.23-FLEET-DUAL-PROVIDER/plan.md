# 2026.07.23-FLEET-DUAL-PROVIDER — Fleet rollout двух провайдеров

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.23-FLEET-DUAL-PROVIDER |
| Title | Последовательная двухпровайдерная настройка проектов |
| Version | 0.2.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | frontier |
| Design Passes | 3/3 — ecosystem-core fleet change: initial design, RED remediation, final cross-phase reconciliation |
| Last Updated | 2026-07-23 |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind |
| Execution Mode | phase-first |
| Target Operator Classes | implementation (exec) · frontier (design/audit) |
| Approval Owner | Dmitry Vostrikov — пользовательский запрос от 2026-07-23 |
| Home | repo:plans/2026.07.23-FLEET-DUAL-PROVIDER |

## 1. Context

Реализация dual-provider завершена, но первый fleet dry-run выявил, что connect
канал не может доставить Codex в consumer-репозитории. Требуется устранить этот
разрыв без неявной глобальной установки и без перезаписи user/managed drift.
После механизма раскатка идёт строго по одному зарегистрированному проекту,
фиксируя каждый сбой в плане и возвращаясь к owning source. Пропавшие временные
записи не являются целью автоматического удаления. RAG:— (repo-grounded:
findings/00-fleet-dry-run-2026-07-23.md).

## 2. Execution Rules

- Каждый проект применяется только после его dry-run и проверяется health/managed locks.
- `--repair` применяется лишь к подтверждённому managed-drift; чужие конфликты не перезаписывать.
- Любой новый fleet-отказ сначала воспроизводится тестом и исправляется в owning package.
- Временные отсутствующие реестровые пути пропускать с явной находкой, не удалять автоматически.
- Один item за раз; после terminal item обновлять status, journal и handoff.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P0.1 | frontier/high | manual | открытый fleet-contract carrier для внешнего Codex connect consumer |
| P0.2 | implementation/high | manual | меняет eligibility/failure semantics fleet sync |
| P1.1–P2.1 | implementation/high | manual | внешнее состояние/конфликты требуют проверки по каждому проекту |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Устранить блокер connect-проекции | 0/2 | 🟡 In progress |
| P1 | Пилот и стабилизация | 0/2 | ⬜ Not started |
| P2 | Последовательный fleet rollout | 0/1 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-23 | P1/P2 полностью детализированы до первого exec; carrier implementation остаётся P0 input. | Исполнимый fleet порядок и retry boundary должны быть проверяемы до provider writes. RAG:— (repo-grounded: findings/00-fleet-dry-run-2026-07-23.md) |
| D2 | 2026-07-23 | Drift остаётся fail-closed, repair — только явный. | Иначе автоматизация может стереть локальную работу. RAG:— (repo-grounded: packages/skiller/lib/skiller/skillset.py:857) |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-23 | issue-planner/frontier | Design pass 1/3: initial fleet dry-run converted into P0 carrier/eligibility design. |
| 2026-07-23 | issue-planner/frontier | Design pass 2/3: RED audit-1 разобран; добавлены parity acceptance, retry и полная карта rollout. |
| 2026-07-23 | issue-planner/frontier | Design pass 3/3: cross-phase reconciliation audit-2 — JIT removed, routing/files/budget reconciled. |
