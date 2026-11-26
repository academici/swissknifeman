### 6.1 Коды ожидания задачи (`BlockingCode`, поле `task.blocking_reason.code`; владелец — execution §4.19)

Не ошибки. Полный объект причины: `code`, `since`, `next_check_at`, `resolver_role`, `allowed_actions`, `deadline_at`,
`refs` (образец `examples/execution/blocking-reasons.json`, схема `urn:skm:execution:blocking-reason:v1`).

| Код | Кто разрешает | Код | Кто разрешает |
|---|---|---|---|
| `WAITING_OWNER` | owner | `BLOCKED_BY_DEPENDENCY` | система (зависимости) |
| `WAITING_ANSWER` | аудитория вопроса | `BLOCKED_BY_MATERIAL` | владелец материала (`planning.assess_material`) |
| `WAITING_ADVISOR` | advisor/consilium | `BLOCKED_BY_BUDGET` | owner (лимит) |
| `WAITING_MANUAL_CHECK` | роль check-а | `BLOCKED_BY_CAPABILITY` | оператор (worker с нужными метками) |
| `WAITING_APPROVAL` | `intent.approve` | `BLOCKED_BY_POLICY` | owner (полномочия) |
| `WAITING_PROVIDER` | время (rate/quota reset) | `BLOCKED_BY_INTEGRATION` | система (slot, конфликт) |
| `WAITING_BUDGET_RESET` | время/owner | `SUSPECTED_STALL` | система/owner |
| | | `RECOVERING` | система (процедура восстановления) |
