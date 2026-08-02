# P1-fleet-baseline — резидентный первый ход по флоту

Якорь: swissknifeman `3003d352`, снято 2026-07-31 14:02 UTC. Измеритель: `skiller budget --first-turn --with-plugins` (после починки P1.4 — `cwd`-резолвинг local-scope, тысячный разделитель, класс `broken` отделён от `unparsed`). Хуковая составляющая (SessionStart живьём, таймаут 10с на проект) средо-зависима — побайтовая воспроизводимость между прогонами НЕ гарантируется.

Записей реестра (enabled): 26 · измерено: 22 · пропущено (n/a): 4 · из них stale (`id: local-repo`): 4

## Таблица по флоту

| id | skills | agents | claude_md | hooks | mcp | total | verdict | plugins Σ | session_total | session_verdict |
|:--|--:|--:|--:|--:|--:|--:|:--|--:|--:|:--|
| agelto | 5630 | 930 | 15524 | 265 | 10350 | 32699 | WARN | 2946 ⛔broken | 35645 | WARN |
| diabox | 2559 | 0 | 7187 | 245 | 2250 | 12241 | WARN | 1936 ⛔broken | 14177 | WARN |
| flexcrm | 5630 | 940 | 15141 | 387 | 7500 | 29598 | WARN | 14493 ⛔broken | 44091 | WARN |
| axiomaerpsdk | 3164 | 265 | 2976 | 261 | 2250 | 8916 | ELEVATED | 9189 ⛔broken | 18105 | WARN |
| azguard | 5107 | 1287 | 1580 | 742 | 3150 | 11866 | WARN | 2077 ⛔broken | 13943 | WARN |
| botkit | 5107 | 974 | 1436 | 246 | 3150 | 10913 | WARN | 8741 ⛔broken | 19654 | WARN |
| vaulter | 5661 | 984 | 396 | 1620 | 8400 | 17061 | WARN | 10016 ⛔broken | 27077 | WARN |
| swissknifeman | 2559 | 567 | 2388 | 1156 | 5250 | 11920 | WARN | 2946 ⛔broken | 14866 | WARN |
| axiomastudio | 2559 | 0 | 0 | 261 | 2250 | 5070 | OK | 5737 ⛔broken | 10807 | WARN |
| corex | 5107 | 0 | 1902 | 0 | 5250 | 12259 | WARN | 8741 ⛔broken | 21000 | WARN |
| memster | 6173 | 934 | 9182 | 930 | 5250 | 22469 | WARN | 10852 ⛔broken | 33321 | WARN |
| cms | 5630 | 694 | 11512 | 260 | 6000 | 24096 | WARN | 8741 ⛔broken | 32837 | WARN |
| edufy | 5630 | 914 | 8490 | 257 | 6300 | 21591 | WARN | 10097 ⛔broken | 31688 | WARN |
| vintera | 5474 | 0 | 7288 | 157 | 0 | 12919 | WARN | 9512 ⛔broken | 22431 | WARN |
| dterema | 5630 | 1615 | 127 | 617 | 0 | 7989 | ELEVATED | 10097 ⛔broken | 18086 | WARN |
| dterema-app | 5474 | 393 | 13658 | 267 | 0 | 19792 | WARN | 9512 ⛔broken | 29304 | WARN |
| sibintek-insiders | 5630 | 945 | 8733 | 1190 | 5550 | 22048 | WARN | 10097 ⛔broken | 32145 | WARN |
| chatom | 6024 | 711 | 7384 | 1554 | 8700 | 24373 | WARN | 10508 ⛔broken | 34881 | WARN |
| perplexity-web-mcp | 2459 | 0 | 3216 | 163 | 5550 | 11388 | WARN | 5724 ⛔broken | 17112 | WARN |
| loqum | 2101 | 0 | 9398 | 153 | 2550 | 14202 | WARN | 5675 ⛔broken | 19877 | WARN |
| brain | 4399 | 0 | 6695 | 1376 | 6300 | 18770 | WARN | 8212 ⛔broken | 26982 | WARN |
| local-repo | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a (stale registry entry (local_path не существует)) |
| local-repo | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a (stale registry entry (local_path не существует)) |
| local-repo | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a (stale registry entry (local_path не существует)) |
| local-repo | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a (stale registry entry (local_path не существует)) |
| agentools | 2559 | 0 | 0 | 160 | 3150 | 5869 | OK | 3985 ⛔broken | 9854 | ELEVATED |

Каждое `n/a` — причина в той же строке таблицы (см. столбец `n/a (...)`).

Доля строк с необъяснённой неполнотой (`unparsed`, if-then-триггер D81): 0/22 (0%). Порог эскалации — четверть измеренных строк.

## Записи класса `broken`

Сам листинг объявил плагин сломанным (`errors`) — известный дефект ЧУЖОГО репозитория, не дрейф формата этого измерителя.

| проект | plugin id | причина |
|:--|:--|:--|
| agelto | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| diabox | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| flexcrm | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| axiomaerpsdk | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| azguard | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| botkit | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| vaulter | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| swissknifeman | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| axiomastudio | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| corex | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| memster | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| cms | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| edufy | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| vintera | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| dterema | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| dterema-app | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| sibintek-insiders | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| chatom | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| perplexity-web-mcp | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| loqum | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| brain | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |
| agentools | brain@brain | Plugin brain has an invalid manifest file at /home/vostrikov/Vaults/Brain/.claude-plugin/plugin.json. Validation errors: commands: Invalid input, skills: Invalid input |

## Сводная статистика (по измеренным строкам)

Число строк, по которым считаны перцентили: 22 (`session_total`, плагин-инклюзивный).

- min: 9854
- медиана: 21716
- p75: 32031
- p90: 34725
- max: 44091

Распределение по действующим порогам (`session_verdict`, n=22): OK=0 · ELEVATED=1 · WARN=21

## До/после починки P1.4 (контрольный проект `memster`)

Первый заход (до починки P1.4, дефектный, отброшен D80, живёт только как факт этой записи — в git не попал): `plugins Σ` = 2946 при `plugins.partial: true` на 22/22 измеренных строк того прогона.

Этот прогон (после починки P1.4): `plugins Σ` = 10852 (дельта +7906).

## Бриф → замер → дельта (пять чисел из `brief/00-brief.md`)

`total` (проектная поверхность, БЕЗ плагинов) сравнивается с числом брифа — брифовые замеры не несли `--with-plugins`.

| id | бриф | замер (`total`) | дельта | замер (`session_total`) |
|:--|--:|--:|--:|--:|
| swissknifeman | 10757 | 11920 | +1163 | 14866 |
| agelto | 32611 | 32699 | +88 | 35645 |
| flexcrm | 29354 | 29598 | +244 | 44091 |
| botkit | 10843 | 10913 | +70 | 19654 |
| diabox | 11996 | 12241 | +245 | 14177 |

Расхождения объясняются дрейфом измеряемых проектов между сессией брифа и этим прогоном (состав скиллов/MCP/агентов меняется независимо от плана) и тем, что `total` брифа не включал marketplace-плагины (P1.1) — не подгонкой.

## Границы этого замера

Файл — сырьё для P1.3 (порог) и не выбирает вариант A/B/C. Read-only по отношению к измеряемым репозиториям; реестр (4 stale-записи `local-repo`) этим item'ом не чистится (D15).
