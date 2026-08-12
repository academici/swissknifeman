# Контракт read-budget v1

**Contract ID:** `read-budget`  
**Версия:** `1.1.0`  
**Статус:** frozen

Этот контракт задаёт границы обязательного чтения для новых executable master plans с
`Layout | v2`.

## Квалифицированная единица

Все пороги измеряются в оценённом верхнем пределе входных токенов от
`token-estimate-calibration` v2.0.0 для `codex/gpt-5.6-terra`, адаптера
`codex-exec-jsonl-v1`, протокола `differential-input-total-v2` и семантики
`provider-reported-input-total-v1`. Значения от другого провайдера, модели или протокола
не взаимозаменяемы без новой калибровки.

## Пороги

Для каждого item должен разрешиться полный mandatory read path:

```text
pass_item(i) = resolved(i) AND estimated_required_read_tokens(i) <= 100000
```

Каждый файл этого пути одновременно должен проходить:

```text
bytes(f) <= 262144 AND est_tokens(f) <= 25000
```

Неразрешимый mandatory input fail-closed и не считается нулём. Разбиение item или вынос
материала за пределы графа не считается улучшением без уменьшения общего mandatory-read
aggregate.

## Граница верхней оценки

Свойство верхней оценки установлено на ограниченном корпусе реальной plan prose и dense-ASCII
inputs, а не статистически доказано для всех файлов. Калибровка v2 добавляет класс
`dense_ascii` (`[0-9A-Za-z+/=]` runs не менее 32 символов): зафиксированы 8 реальных
принятых samples, 0 нарушений верхней границы и
`max_true_over_estimate = 1.0846677212727815`.

Наблюдаемая недооценка — это failure контракта, а не допуск. Она требует нового
калибровочного артефакта, D-record и повторной валидации; те же действия нужны при смене
провайдера, модели, probe protocol, classifier или semantics usage.

## Anti-displacement

Aggregate — суммарный mandatory-read weight полного закрытого графа плана, включая generated
carriers и per-file overhead. Каждый acceptance report печатает aggregate рядом с per-item
результатом и сравнением с состоянием до реструктурирования. Отчёт обязан ответить, мог ли
pass появиться лишь из-за дробления, переноса, cache, defer или исключения работы; положительный
либо неразрешённый ответ блокирует acceptance.

## Admission

У layout-v2 item ровно одно состояние admission:

- `historical-pre-v2` — исторический terminal item; его baseline не переписывается.
- `pending-producer` — отсутствующий input назван в Deliverables более раннего нетерминального
  producer item; это defer, не pass.
- `ready` — применяются оба порога; отсутствие или невалидная producer-связь блокируют работу.

Отчёт включает калибровку, максимум на item, aggregate до/после, неразрешимые inputs,
нарушения обоих лимитов и ответ на вопрос, не достигнут ли pass только переносом или
исключением работы.

## Изменение контракта

Изменение порога, единицы, применимости или anti-displacement semantics требует решения
владельца, нового D-record, новой калибровки при смене единицы, машинного измерения и
версии контракта.

Полные правила применения и отчётные поля: [read-admission](./plan-read-admission.md) и
[read-budget gate](./plan-read-budget-gate.md).

## Provenance

Контракт архивирован из плана `2026.08.10-TASK-LEAN-AUTONOMY`; исходный immutable carrier:
`plans/archive/2026.08.10-TASK-LEAN-AUTONOMY/root/contracts/read-budget-v1.md`.
