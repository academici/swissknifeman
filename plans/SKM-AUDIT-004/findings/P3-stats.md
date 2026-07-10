# P3.1 — Сырая статистика флота (read-only)

Снято 2026-07-07. Все команды read-only; `git status --porcelain` до/после —
только предсуществующие `M plans/ACTIVE.md` / `?? plans/SKM-AUDIT-004/`; новых
файлов в `~/.swissknifeman/` не появилось (сверено `ls -la`). Источник флота —
`~/.swissknifeman/projects.json` (20 проектов, все `channel` из двух конфигов —
некоторые проекты фигурируют дважды: раз как `vendor`-запись, раз как
`marketplace`-запись, см. таблицу 4).

## 1. Флот: проект → onboarded → health

Источник: `maind projects status` (текстовый вывод; JSON-эквивалент —
`maind projects status --json`).

Хаб: память up (`http://127.0.0.1:4111`), граф 236 узлов / 601 рёбер,
docs-watcher up. Прогонов: `maind status --json` (см. также) — 20/20 сконфигурировано.

| Проект | Статус | mcp[a/m/c] | trust | skills | packs | agent-pack warning |
|:--|:--|:--|:--|--:|--:|:--|
| agelto | connected | `-mc` | ✓ | 124 | 1 | ⚠ ожидает `_common` |
| diabox | connected | `-m-` | ✓ | 17 | 0 | — |
| flexcrm | connected | `-mc` | ✓ | 142 | 2 | — |
| axiomaerpsdk | connected | `-m-` | ✓ | 0 | 1 | — |
| azguard | connected | `-mc` | ✓ | 95 | 3 | — |
| botkit | connected | `-mc` | ✓ | 95 | 2 | ⚠ ожидает `laravel-package, _common` |
| vaulter | connected | `-mc` | · (не доверен) | 0 | 1 | ⚠ ожидает `laravel-package, _common` |
| swissknifeman | connected | `-m-` | ✓ | 0 | 2 | — |
| axiomastudio | connected | `-m-` | ✓ | 0 | 0 | — |
| corex | connected | `-mc` | ✓ | 0 | 1 | ⚠ ожидает `laravel-package, _common` |
| memster | connected | `-mc` | ✓ | 0 | 2 | — |
| cms | connected | `-mc` | ✓ | 27 | 0 | ⚠ ожидает `laravel-package, _common` |
| edufy | connected | `-mc` | ✓ | 0 | 2 | — |
| vintera | connected | `-m-` | ✓ | 30 | 0 | — |
| dterema | connected | `-mc` | ✓ | 96 | 4 | ⚠ ожидает `laravel-package` |
| dterema-app | connected | `-mc` | ✓ | 35 | 0 | — |
| sibintek-insiders | connected | `-mc` | ✓ | 3 | 0 | ⚠ ожидает `laravel-package, _common` |
| chatom | connected | `-mc` | · (не доверен) | 0 | 2 | — |
| perplexity-web-mcp | connected | `-mc` | · (не доверен) | 0 | 0 | — |
| loqum | connected | `-m-` | · (не доверен) | 0 | 0 | — |

Факт: 20/20 `connected`; 16/20 `trust✓`, 4/20 `trust·` (vaulter, chatom,
perplexity-web-mcp, loqum — не доверены в `.claude/settings.local.json`,
совпадает с `maind status`: `workspace.trusted: 16/20`). 8/20 проектов несут
⚠ agent-pack warning (пак ожидает роль-профиль, не установлен) — все, кроме
`agelto`/`dterema`, ждут одновременно `laravel-package` и `_common`.
`skills=0` у 8 проектов — это marketplace-канал (`connect`), где число скиллов
не считается тем же полем, что у vendor (см. §4 про двойные записи).

## 2. analyst: по проектам

Источник (по каждому проекту, `cd <path> && analyst status --json`) и число
run-report'ов — `find <path>/.claude/runs -maxdepth 1 -iname '*.json' | wc -l`
(run-report'ы пишет SessionEnd-хук harness независимо от analyst; `digest`
потребляет их по требованию — наличие run-report ≠ наличие урока).

| Проект | run-report'ов | analyst-state | ephemeral | candidate | curated | deprecated | curated-ready | promote_failed | events |
|:--|--:|:--|--:|--:|--:|--:|--:|--:|--:|
| agelto | 30 | есть | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| azguard | 10 | нет | — | — | — | — | — | — | — |
| vaulter | 9 | есть | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| chatom | 6 | нет | — | — | — | — | — | — | — |
| swissknifeman | 4 | нет | — | — | — | — | — | — | — |
| остальные 15 проектов | 0 | нет | — | — | — | — | — | — | — |

Факт: **только 2 из 20 проектов** (agelto, vaulter) имеют каталог
`.claude/analyst/` (лог уроков) вообще; из них ни один урок не в состоянии
`curated`. 5/20 проектов накопили run-report'ы (agelto/azguard/vaulter/chatom/
swissknifeman), но `digest` явно прогонялся (или дал непустой результат)
только на 2 — на azguard/chatom/swissknifeman **есть сырьё, но нет
`analyst` state** (непросмотренные run-report'ы — сигнал из `295951c`,
подтверждён числом: 10+6+4=20 run-report'ов без единого извлечённого урока).

**token-report** (источник `<project>/.claude/analyze/usage-trend.ndjson`,
команда `analyst token-report --json`, пишет тот же SessionEnd-хук
независимо от analyst-стора): файл существует только у 2/20 проектов —
`agelto` (42 записи) и `swissknifeman` (4 записи), у остальных 18 —
`no-trend-file`. Снятые срезы:

- agelto: `rolling.n=20`, `median_out=81726`, `median_in=464`, `p90_out=141472`.
- swissknifeman: `rolling.n=4` (весь трек короче окна K=20), `median_out=243475`,
  `median_in=109395`, `p90_out=632188`; по срезу `--by model` — 2 модели в
  окне (`claude-haiku-4-5-20251001`: 1 сессия, `out=560302`, `ratio_median≈2.30`,
  regression=true; `claude-opus-4-8`: 2 сессии, `avg_out=72556`,
  `ratio_median≈0.30`, regression=false).

`token-report` умеет: rolling-baseline (медиана+p90, K=20) по `in`/`out`,
срез `--by model|role`, pinned `--baseline set` (сравнение с фиксированной
базой), `--vs-baseline` (regression-флаг на сессию). На 18/20 проектов не
считается вообще — нет входных данных.

## 3. skiller budget: CORE-резидент и топы

Источник: `skiller budget --check-core --json` (снято из корня
swissknifeman; CORE-политика едина для всех проектов — снимать per-project
не нужно, состав `CORE_SKILLS` глобальный).

```
resident_core_tier0: 705 ток
target (RESIDENT_BUDGET_TARGET): 750 ток
skills: 9 / 9 (missing=0)
status: OK
```

Факт: на момент снятия (2026-07-07, после фиксов P2) CORE-резидент **НЕ
превышает** target — 705 < 750 (запас 45 ток). Известный сигнал из
`plan.md`/`packages/skiller/CLAUDE.md` («на 2026-07 фактический резидент
превышает RESIDENT_BUDGET_TARGET») **устарел на момент снятия** — либо был
верен до недавних правок (P2 diff/дешёвые модели), либо `CORE_SKILLS`
сократился с 8 до текущих 9 без обновления комментария (в `CLAUDE.md`
сказано «8 скиллов», гейт видит 9 — расхождение самого текста CLAUDE.md,
не кода; отдельная находка для P3.2/P5, не фиксится здесь — P3.1 read-only).

Топ-бюджет снят на конфиге `swissknifeman` (общий `--target`/`--config` не
задан → берётся `.swissknife.json` текущего проекта, который тянет полные
бакеты `general`+`oss-dev`, не CORE-only — см. §4): `skiller budget --json`
без флагов.

```
count=35, tier0=2455, tier1=46684
```

По бакетам (⊕ always / ↻ bodies / скиллов):

| Бакет | ⊕ always | ↻ bodies | ⌥ on-demand | скиллов |
|:--|--:|--:|--:|--:|
| general | 1402 | 24266 | 11028 | 20 |
| oss-dev | 627 | 13978 | 10187 | 10 |
| quality | 136 | 2996 | 2147 | 2 |
| research | 130 | 3928 | 0 | 1 |
| architect | 122 | 1261 | 1481 | 1 |
| devops | 38 | 255 | 0 | 1 |

Топ-10 самых тяжёлых description (⊕ always, постоянный налог) в этом наборе:

| Скилл | ⊕ always ток |
|:--|--:|
| general/verify-claims | 133 |
| research/query-craft | 130 |
| architect/domain-modeling | 122 |
| oss-dev/issue-triage | 114 |
| general/mcp-advisor | 107 |
| oss-dev/resolving-merge-conflicts | 103 |
| quality/tdd-discipline | 100 |
| general/grill-with-docs | 98 |
| general/writing-style | 98 |
| oss-dev/to-issues | 92 |

## 4. Распределение подключённых бакетов/плагинов по проектам

Источник: `~/.swissknifeman/projects.json` (`projects[].channel` +
`projects[].plugins`/`buckets`). Массив несёт **обе** конфиг-системы
(`.swissknife.json` = connect/legacy-vendor и `.swissknifeman/config.json` =
vendor `sync`) как отдельные записи на один и тот же путь — отсюда дубли
путей (`agelto`, `azguard`, `cms`, `dterema`, `app`/`dterema-app` встречаются
по 2 раза: одна запись `channel:vendor` с пустым `plugins`, другая
`channel:marketplace` со списком плагинов). Это НЕ ошибка данных — два
разных канала на одном проекте (см. `packages/skiller/CLAUDE.md` §«Два
конфига проекта»); фиксирую как факт для P3.2, не как находку.

14 проектов имеют `channel:marketplace` (bucket-granular) с непустым
`plugins[]`. Частота плагина по этим 14:

| Плагин | Проектов | Плагин | Проектов |
|:--|--:|:--|--:|
| core | 13 | operator | 6 |
| task | 13 | laravel-auth | 5 |
| devops | 12 | laravel-data-layer | 5 |
| quality | 12 | php-packages | 4 |
| system | 12 | general | 2 |
| php | 10 | frontend* (5 отдельных) | 1 каждый |
| laravel-testing | 9 | ai | 1 |
| architect | 9 | | |
| oss-dev | 7 | | |

Кандидат «подключено редко/точечно» (не обязательно неиспользуемо — нужен
P3.2 с сопоставлением стека проекта): `frontend`/`frontend-linting`/
`frontend-tailwind`/`frontend-vite`/`frontend-vue` — по 1 проекту
(`dterema-app`, ожидаемо: единственный node-frontend в списке), `ai` — 1
(`loqum`). `general` держат только 2 проекта из 14 marketplace
(`swissknifeman` и `loqum`) — **оба на устаревшем наборе `core+general+
oss-dev+task`**, не мигрированы на CORE-only паттерн, который сам же
`skiller connect` подсказывает при апдейте (см. `packages/skiller/CLAUDE.md`
§CORE-политика: «connect... подсказывает онбордженным снять старые
general/oss-dev»). `swissknifeman` — сам монорепо-хаб реестра, edge-кейс не
показателен для остального флота; `loqum` — обычный кандидат на миграцию.

## Итог (сырьё для P3.2, без интерпретации)

- Флот: 20/20 connected, 16/20 доверены, 8/20 с невыполненным agent-pack
  требованием (все ждут `_common`, часть ещё и `laravel-package`).
- analyst-цикл почти не используется: state есть у 2/20 проектов, run-report
  накоплен у 5/20 (20 «непросмотренных» run-report'ов на 3 проектах без
  единого урока), token-trend — у 2/20.
- CORE-резидент сейчас в пределах target (705/750) — сигнал из
  `plan.md`/`CLAUDE.md` об excess не подтверждается на момент снятия;
  расхождение числа CORE_SKILLS в тексте `packages/skiller/CLAUDE.md` (8 vs
  фактических 9) — отдельно зафиксировано.
- 2 marketplace-проекта (`swissknifeman`, `loqum`) всё ещё на legacy
  `general+oss-dev` вместо CORE-only.
