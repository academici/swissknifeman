# plan-v2 — Демо-план

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | plan-v2 |
| Title | Демо-план |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Repository | swissknifeman |
| Related Packages | task |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) |
| Approval Owner | dv |
| Home | repo:swissknifeman |
| Design Passes | 1/1 |
| visibility | private |

## 1. Context

Демо для unittest plan_lint.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P1.1 | implementation/medium | run | fixture v2 |

## 5. Decision Log

Каталог решений: `decisions/`; собрать: `python3 packages/task/scripts/plan-views.py decisions`.
