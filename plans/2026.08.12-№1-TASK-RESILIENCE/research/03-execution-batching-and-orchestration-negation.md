# Execution batching и negation-aware orchestration lint

## 1. Почему batch/solo потерялся при формировании плана

Дефект был системным расхождением четырёх носителей:

1. `plan-protocol` уже называл каноническую шестиколоночную таблицу
   `Batch | Items | Model class/effort | Exec | Review | Почему`.
2. `snippets/plan-template.md` продолжал создавать legacy-таблицу из четырёх колонок.
3. `task:plan-design` называл `Batch` и `Review` опциональными и допускал пустой Routing.
4. `plan-lint` проверял только грамматику `Items`, а `handoff` — только наличие route/command;
   наличие и сохранение Batch машиной не проверялись.

Поэтому DoR мог быть зелёным при item-level route, но без ответа «solo или одна цепочка», а
следующий handoff закономерно схлопывался до одного item. Минимальный repro до исправления:
`python3 packages/task/scripts/plan-lint.py plans/2026.08.12-№1-TASK-RESILIENCE` возвращал
`OK`; после установки schema-гейта тот же немигрированный план дал 20 ERROR: legacy Routing,
18 items без Batch/solo и execution handoff без Batch.

Системное исправление: обязательные `Batch`/`Review` для всех новых numbered layout-v2 plans,
полное/однократное покрытие items, phase-local adjacent группы с единым Exec и обязательная строка
Batch в каждом execution handoff. Канон, шаблоны и все handoff-writer commands синхронизированы.

## 2. Разумная грань группировки

Группа выгодна, когда соседние items одной фазы имеют producer→consumer зависимость либо общий
набор файлов, Required Reads, setup или Validation, и продолжение в одной сессии дешевле повторного
холодного старта. Отдельные commits, Deliverables и per-item close не являются причиной дробить:
полный lifecycle каждого item сохраняется внутри batch.

`solo` оправдан только конкретной границей: несовместимый Exec, owner/irreversible gate,
специальная capability, широкая смена surface/validation либо ожидаемый context overflow. Batch
не пересекает phase audit/close; launch использует максимум route/review и union capabilities.

Применение к этому плану:

| Группа | Items | Решение |
|:--|:--|:--|
| B-P0-EVIDENCE | P0.1–P0.2 | общий gap→acceptance producer chain; уже закрыта |
| solo | P0.3 | отдельная Perplexity capability и mandatory evidence checkpoint |
| B-P1-CUTOVER | P1.1–P1.3 | единая inventory→migration→removal цепочка |
| B-P2-IDENTITY | P2.1–P2.2 | общий identity/reference parser и canon |
| B-P3-CONTINUE | P3.1–P3.3 | единый nonterminal/command/lint false-positive seam |
| B-P4-BLOCK | P4.1–P4.2 | candidate→isolated confirmer producer chain |
| B-P5-DELIVERY | P5.1–P5.2 | receipt→candidate/audit/close lifecycle |
| solo | P5.3 | смена на cross-package generator/docs surface и широкий validation budget |
| solo | P6.1/P6.2/P6.3 | release tree, irreversible tag и external rollout — три hard boundaries |

## 3. Новый roadmap: negation-aware orchestration detection

Источник: `roadmap/2026.08.12-task-orchestration-negation-lint.md`.

Подтверждённая причина находится в `packages/task/lib/task/plan_lint_checks/common.py` и
`parsing.py`: keyword-only `ORCHESTRATION_MARKER_RE` ищет `scriptPath|оркестрац|мультиагент|multi-agent`,
а оба layout parser-path вычисляют `declares_orchestration` через `any(search(line))`. Поэтому
строка «оркестрация не заявлена/не требуется» становится positive declaration. Engine затем честно,
но на неверном boolean, выдаёт warning об отсутствующем workflow.

Существующие regressions проверяют positive declaration, script-present, отсутствие marker,
not-started phase и marker после `## Audit`. Не покрыты:

- heading/строка с явным отрицанием и sequential chain;
- line-scoped negation;
- positive declaration на другой строке после отрицания;
- одинаковое правило в обоих layout parser-path.

P3.3 вводит один line-scoped semantic predicate: `scriptPath`/явное positive declaration включает
workflow requirement; отрицание в том же утверждении не включает; отдельное последующее positive
утверждение снова включает. P5.3 проверяет, что canonical meaning доехал до generated provider/docs
surface. План Agelto не переписывается эвфемизмами.
