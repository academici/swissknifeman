# P6.1 — Baseline-замер (до раскатки)

Дата снятия: 2026-07-12. Обе команды-гейта отработали без ошибок (rc=0 каждая).

## Таблица 1 — `maind doctor --context` (флот, футпринт первого хода)

Команда: `maind doctor --context` (25 проектов; 1 неблокирующий WARN «неизвестный
ключ memory.digest» из config.json — вне scope item'а, read-only замер).

| Проект | context (ток) | Вердикт |
|:--|--:|:--|
| agelto | 34538 | WARN |
| diabox | 12180 | WARN |
| flexcrm | 31067 | WARN |
| axiomaerpsdk | 7859 | ELEVATED |
| azguard | 16942 | WARN |
| botkit | 15720 | WARN |
| vaulter | 19208 | WARN |
| swissknifeman | 12679 | WARN |
| axiomastudio | 5009 | OK |
| corex | 22504 | WARN |
| memster | 23274 | WARN |
| cms | 25599 | WARN |
| edufy | 22938 | WARN |
| vintera | 20521 | WARN |
| dterema | 19121 | WARN |
| dterema-app | 31444 | WARN |
| sibintek-insiders | 23477 | WARN |
| chatom | 25127 | WARN |
| perplexity-web-mcp | 11981 | WARN |
| loqum | 15774 | WARN |
| brain | 17733 | WARN |
| local-repo | 22291 | WARN |
| local-repo | n/a | n/a |
| local-repo | n/a | n/a |
| local-repo | n/a | n/a |

Итог: 1 OK, 1 ELEVATED, 20 WARN, 3 n/a (дубли `local-repo` без разрешимого пути —
fail-soft по конструкции P5.2). Медиана WARN-порога (10K) превышена почти везде —
подтверждает разведку P0 (стартовый бюджет должен быть 3–7K).

## Таблица 2 — `analyst sessions --weeks 2` (недельные медианы, 3 проекта)

Команда: `analyst sessions --project <id> --weeks 2 --json`.

| Проект | Неделя | Сессий | median first_turn_overhead | median fresh_per_turn | trend-warn |
|:--|:--|--:|--:|--:|:--|
| agelto | 2026-W27 | 33 | 57304 | 6412.2 | — |
| agelto | 2026-W28 | 44 | 50083.5 | 6530.9 | — |
| swissknifeman | 2026-W27 | 42 | 22287.5 | 4711.6 | — |
| swissknifeman | 2026-W28 | 44 | 29816.5 | 3768.2 | ⚠ +34% W27→W28 |
| brain | 2026-W27 | 8 | 24288.5 | 5341.3 | — |
| brain | 2026-W28 | 166 | 31317.5 | 8082.3 | ⚠ +29% W27→W28 |

agelto max-anomaly first_turn_overhead в окне — 139696 (сессия 7594c3a8, W28) —
совпадает с разведкой P0 (agelto max 139.7K).

## Детерминизм

Оба прогона (`doctor --context`, `analyst sessions ×3`) повторены дважды в рамках
item'а — числа идентичны (жёсткий read из существующих jsonl-транскриптов и
конфигов, без рандома/времени исполнения внутри метрик).
