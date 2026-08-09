Граница доказанного: два сценария выполнены на synthetic Layout-v2 плане `plan-v2-p5`; перевод пяти команд и проверка на живом плане флота остаются в P6.

# P5.5 — return-loop DecisionRequest acceptance

## Прогон 1 — технический вопрос

Allowlisted `plan_carrier` auto-answer записан в `decisions/queue.jsonl` как `policy`-ответ с
проверяемым provenance. В очереди 1 такой ответ из 3 typed events; он не оставляет subject P1.2
заблокированным.

## Прогон 2 — owner gate

Три одинаковых return events P1.1 пересекли frozen `same_return_max=2`. Адаптер оставил
`blocks=true`, создал authorization `DecisionRequest` с `on_timeout=park` и ссылками на
`journal.jsonl`, без копии owner packet. Только P1.1 имеет `🔴 Blocked`; P1.2 остался
`🟡 In progress`.

## Метрики

- Доля запросов, разрешённых policy без человека: 1/2 (50%).
- Припаркованных субъектов: 1.
- Оставшихся исполнимыми субъектов: 1.

Напечатанная доля policy-разрешений: 1/2.
Напечатано припарковано субъектов: 1.
Напечатано исполнимы субъектов: 1.

Проверки: `tests.test_plan_requests`, `tests.test_plan_authority`, queue/owner-status probes и
`packages/task/scripts/validate.sh`.
