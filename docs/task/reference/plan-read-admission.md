# Stage-aware admission бюджета чтения

`task.plan_weight` для планов Layout v2 различает момент применения D2, не меняя единицу,
порог `100000`, single-read limits или anti-displacement D74. Публичный контракт находится в
`plans/<PLAN-ID>/root/contracts/read-budget-v1.md`; числовых fallback в коде нет.

## Состояния

- `historical-pre-v2` — item был терминален не позже journal-события активации Layout v2.
  Его измерение остаётся baseline evidence, закрытое ТЗ не переписывается ради зелёного исхода.
- `pending-producer` — каждый отсутствующий обязательный вход связан с существующим
  незавершённым predecessor item, а его `Deliverables` называет тот же путь. Это deferred,
  не pass и не нулевой вес.
- `ready` — до мутации обязательны D2(a) и D2(b). Generic missing, unresolved entry, невалидный
  producer edge или отсутствующий output уже терминального producer дают fail-closed.

Producer объявляется на соответствующей позиции `Required Reads`:

```text
2) `root/contracts/bundle-v1.md` (producer: P3.1)
```

Компактная форма `producer=P3.1` эквивалентна. Producer обязан существовать раньше consumer,
а его `Deliverables` — адресовать отсутствующий путь. Ручного `admission_state`, warning-mode,
allowlist или baseline-exception нет.

## Вывод и API

### Обязательный путь по раскладке

`plan-weight item` выбирает путь только по объявленному `Layout`:

- v1 сохраняет legacy-порядок `plan → handoff → phase → Required Reads`;
- v2 измеряет ровно пять carrier-ролей `plan-core → phase-context → item-spec →
  item-input-bundle → item-state`. `handoff.md` в executor path v2 не входит.

Для v2 инструмент сначала проверяет byte-freshness generated bundle и state. Затем он читает
только перечисленные bundle selections, сверяет digest исходника и выбранного фрагмента и считает
их как `bundle-input`. Повтор одного источника с тем же selector не удваивает вес; разные selectors
одного источника остаются разными единицами чтения. Stale carrier, digest mismatch или
неразрешимый selection дают fail-closed gap, а не нулевой вес.

```bash
python3 packages/task/scripts/plan-weight.py item plans/<PLAN-ID> Pn.m --json
```

Item-запись содержит `admission_state`, `producer_item`, `producer_edges`, раздельные
`admission_gaps`, `d2a_pass`, `d2b_pass` и `admission_pass`. Последнее поле boolean только для
`ready`; у historical/pending оно равно `null`. Сводка `totals.admission` несёт версию/путь
контракта, числа состояний, gap codes и `ready_failed`.

Измерение остаётся в `task.plan_weight`; `task.plan_admission` только классифицирует stage и
проверяет producer edges. Потребители pre-mutation обязаны вызывать этот API, не заводить второй
счётчик веса или собственную трактовку missing inputs.
