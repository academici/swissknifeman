# RUN-FIXTURE — Фикстурный план для драйвера exec-волны (P4.2)

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | RUN-FIXTURE |
| Title | Фикстурный план для драйвера exec-волны |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-08-01 |
| Repository | swissknifeman |
| Related Packages | harness |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) |
| Approval Owner | dv |

## 1. Context

Синтетический план для юнит-тестов `harness/run/plan_reader.py` (P4.2) —
переиспользуется P4.3–P4.6. НЕ боевой план, не участвует в plan-протоколе флота.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P1.1 | implementation/medium | plan-exec | одиночная форма ячейки `Items` — базовый drivable-кейс |
| P1.3–P1.5 | implementation/medium | plan-exec | диапазонная форма одной фазы — покрывает P1.3 (P1.4/P1.5 в фазе нет) |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Фаза раз | 1/3 | 🟡 In progress |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | Фикстура закрытым набором форм §3 Routing | покрыть drivable/range без второго парсера |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | Фикстура создана (P4.2) |
