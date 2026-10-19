# Журнал прогона плана SKM-CHANGES (наблюдатель и исполнение)

Записи в хронологическом порядке: что произошло, что исправлено, каким коммитом, как проверить.
Каждая правка механизма (`packages/orch`, `bridges/`, `packages/planner`) перечислена здесь для проверки.

## 2026-10-19

### R1. Claim пункта с маршрутом не на дефолтного исполнителя отклоняется (ROUTE_MISMATCH)

- Симптом: `orch conduct run --plan … --items P1.1 --scenario full --frozen --debug` → `run end stopped CLAIM_BLOCKED — P1.1: ROUTE_MISMATCH: P1.1 selects provider 'codex'`. Пункт остался `todo`, роль не запускалась.
- Причина: `packages/orch/lib/orch/conductor/application/loop.py` `claim_actor` передаёт `source claim --actor` дефолтного исполнителя конфигурации (claude-code/sonnet). Мост `bridges/planner-orch/worksource.py` `op_claim` использует этот actor в `plan start`, а планировщик сверяет его с маршрутом пункта (codex/gpt-6.1-sol) — `packages/planner/lib/planner/plan/lifecycle.py:673`, `validate_route`.
- Исправление: `op_claim` берёт исполнителя из опций пункта (последняя ступень `role: executor` в слоях оркестровки, самый конкретный слой) и передаёт её в `plan start`; без такой ступени поведение прежнее.
- Проверка: тест `bridges/planner-orch/tests/test_worksource.py` (новый), весь файл зелёный (49 тестов до правки).
- Коммит: `b447f6981`.

- Проверки: `test_worksource.py` 50/50; `bridges/planner-orch/scripts/test.sh` (с PLANNER_ROOT и SKM_ORCH_ROOT) 177 тестов OK; `public-hygiene` 0 нарушений (исправлена строка аудита с ссылкой в рабочий каталог).
- Наблюдение: `scripts/affected-tests.py` без переменных окружения пропускает тесты моста (skipped), запуск нужно делать с PLANNER_ROOT и SKM_ORCH_ROOT.
