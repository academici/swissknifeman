# P4.6 — return-judgement acceptance

## Граница приёмки

`classified` на историческом корпусе недостижим по построению: объявлений шва до введения
механизма P4 нет. Исторический прогон доказывает только `provisional`-детект; полный
`classified` путь доказывается отдельно на тестовом плане.

## Исторический corpus — детерминированное артефактное воспроизведение

Два независимых запуска `measure_returns.py --json` совпали до байта (`cmp`). Они дали 10
журналов, 1109 записей и 87 return events — те же счётчики, что в `returns-baseline.json`.
`classified_share` равен `0.0`; семь fingerprint digest пересекли cap `2`.

Старый prose-claim P4 о восьми субъектах не подтверждается ни baseline, ни повторным расчётом:
оба дают семь (распределение count: `6, 3×6, 2×7, 1×33`). Корпус и baseline не менялись; прежний
текст не корректируется этим item'ом. Полный детерминированный снимок —
`historical-detect.json`.

## Тестовый план — полный `classified` путь

`packages/task/tests/data/plan-v2` объявляет seam и хранит три schema-valid независимых verdict
для событий `journal.jsonl:3`, `:5` и `:7`. Текущий gate выбирает только `:7`, а blocking
`owner-gate` packet сохраняет все три accepted event-scoped records в порядке истории. Это
synthetic acceptance, не утверждение о наличии исторического шва.

## Проверенный инвариант

Тест перебирает все пять значений closed enum. `JUSTIFIED` и `INSUFFICIENT_EVIDENCE` сохраняют
policy state; `AVOIDABLE`, `OUT_OF_SCOPE` и `MALFORMED` могут только потребовать раннюю остановку.
Ни один verdict не меняет digest/namespace, не уменьшает count и не снимает owner gate. Никакая
ветвь не может одновременно блокировать и разрешать continuation. Повторная schema-valid запись
того же event не переигрывает первую, неполный provenance игнорируется, self-judgement отвергается.

`validate_acceptance.py` повторяет исторический замер дважды, сравнивает снимок и baseline без
правки corpus, а также проверяет полный synthetic event-scoped packet. Скрипт запускается и из
detached item tree; его `--refresh-historical` режим является единственным генератором снимка.

Это артефактное воспроизведение сохранённого verdict; повторный вызов модели не выполнялся и не
заявляется воспроизводимым.
