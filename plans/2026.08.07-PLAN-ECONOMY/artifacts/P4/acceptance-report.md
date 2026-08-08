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

`packages/task/tests/data/plan-v2` объявляет seam и хранит schema-valid независимый verdict
`AVOIDABLE`. `plan-views.py returns --gate --json` выдаёт `classified`, `occurrences=3`, `cap=2`,
блокирующий `owner-gate`, owner packet и выбранную первую запись суждения. Это synthetic acceptance,
не утверждение о наличии исторического шва.

## Проверенный инвариант

Тест перебирает все пять значений closed enum. `JUSTIFIED` и `INSUFFICIENT_EVIDENCE` сохраняют
policy state; `AVOIDABLE`, `OUT_OF_SCOPE` и `MALFORMED` могут только потребовать раннюю остановку.
Ни один verdict не меняет digest/namespace, не уменьшает count и не снимает owner gate. Повторная
schema-valid запись не переигрывает первую, неполный provenance игнорируется, self-judgement
отвергается.

Это артефактное воспроизведение сохранённого verdict; повторный вызов модели не выполнялся и не
заявляется воспроизводимым.
