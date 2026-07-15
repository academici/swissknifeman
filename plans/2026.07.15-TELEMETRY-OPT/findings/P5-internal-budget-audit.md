# P5.1 — Внутренний аудит always-on бюджета (skiller budget)

Инструмент: `bash packages/skiller/bin/skiller budget --first-turn --target <dir> --json` (+
`bash packages/skiller/bin/skiller budget --target <dir>` для трёхъярусной разбивки по бакетам/скиллам).
Числа — из инструмента (`budget.py`, единый источник токен-математики), не на глаз.

## Замеренные проекты (5, разного стека)

| Проект | Стек | Канал | `.swissknife*` |
|:--|:--|:--|:--|
| `packages/swissknifeman` | python-монорепо (себя) | marketplace/standalone | — |
| `packages/vaulter` | php-package (Laravel-пакет) | marketplace/connect | `.swissknife.json` buckets |
| `memster` | laravel-project | marketplace/connect | `.swissknife.json` buckets |
| `dterema/app` | node-frontend (Vue/Nuxt) | marketplace/connect | `.swissknife.json` buckets |
| `packages/erp-sdk` | dart-flutter | marketplace/connect | CORE-only |

## Таблица компонент (`skiller budget --first-turn`)

| Проект | skills ⊕ | agents | CLAUDE.md+rules | hooks (live) | MCP tool-defs | **Итого** | Вердикт |
|:--|--:|--:|--:|--:|--:|--:|:--|
| swissknifeman | 2498 (36 скиллов) | 567 (6) | 4203 | 1156 (1 хук) | 2250 (2 сервера: maind, perplexity-web) | **10674** | WARN |
| vaulter | 5598 (84) | 984 (11) | 396 (269+rules) | 1487 (3 хука) | 8400 (4: maind, perplexity-web, playwright, serena) | **16865** | WARN |
| memster | 6113 (92) | 934 (10) | 9182 (9055+rules) | 930 (1 хук) | 5250 (3: maind, perplexity-web, serena) | **22409** | WARN |
| dterema/app | 5426 (79) | 393 (5) | 13658 (13535+rules) | 267 (1 хук) | 10650 (7: dterema-nuxt-docs, figma, maind, naive-ui, perplexity-web, playwright, serena) | **30394** | WARN |
| erp-sdk | 2498 (36) | 265 (3) | 1531 | 261 (1 хук) | 2250 (2: maind, perplexity-web) | **6805** | OK |

Порог `skiller budget --first-turn`: target ≤7K OK · ≤10K ELEVATED · >10K WARN
(`packages/skiller/lib/skiller/budget.py:193-194`). **4 из 5 замеренных проектов — WARN**
(единственный OK — erp-sdk, CORE-only набор без доп. бакетов/MCP).

## Кандидаты сжатия (ранжировано по измеренному резиденту)

### К1 — MCP tool-defs: главный измеренный рычаг на MCP-тяжёлых проектах
**Резидент:** 2250 (2 сервера, baseline maind+perplexity-web) → **8400** (vaulter, +playwright+serena)
→ **10650** (dterema/app, 7 серверов, **35% от итогового 30394**).
Оценка `KNOWN_MCP_TOOLS`×150 ток/тул (`budget.py:200-206`): serena=20, playwright=21, github=20 —
самые дорогие резидентные серверы. dterema/app держит 7 серверов одновременно (включая
project-specific `dterema-nuxt-docs`, `figma`, `naive-ui`) — крупнейший измеренный вклад в WARN
среди 5 проектов. Рычаг совпадает с уже канонизированным правилом (`context-economy` §5: «MCP
сервер не используется 7 дней → отключить», ladder §9: «MCP ~10-20k ток/сервер — держать 1-2 на
задачу»), но **измерено впервые кросс-проектно с числами** — раньше правило было качественным.

### К2 — CLAUDE.md сверх ≤200 строк на 2 из 5 проектов
**Резидент:** dterema/app **13658** (CLAUDE.md=13535, ≈4× больше следующего по размеру),
memster **9182** (CLAUDE.md=9055). Против swissknifeman (4203, монорепо-гид, сам превышает
целевые ≤200 строк, но кратно меньше) и erp-sdk (1531) / vaulter (396, уже подстрижен).
Оба проекта нарушают собственный канон репо (`context-economy` §1: «CLAUDE.md ≤200 lines»,
ladder §9: «CLAUDE.md trim — up to ~92%, highest per-repo ROI»). Это внешние по отношению к
swissknifeman проекты (memster/dterema — не пакеты монорепо) — правка их CLAUDE.md вне scope
этого item'а (measure-only), но backlog-кандидат с наибольшим единичным числом среди всех
компонент всех 5 проектов.

### К3 — Топ ⊕always-описания повторяются across проектов (⊕always-налог × N подписчиков)
Один и тот же набор дорогих `description` встречается в ⊕always-топе ВСЕХ 3 php/laravel-стек
проектов (vaulter/memster/dterema-app используют общий бакет `architect`/`system`/`general`):
`architect/dev-engineering-super-skill` 133 ток · `architect/domain-modeling` 128 ·
`php/production-readiness-checklist` 128 · `system/agent-packs` 120 · `system/session-observer` 117 ·
`architect/codebase-design` 117 · `general/verify-claims` 110 — присутствуют одновременно в
3/5 замеренных проектов (все, кто подписан на бакет `architect`/`system`). Сжатие ЭТИХ
description'ов даёт множитель N (число подписанных проектов), а не разовую экономию одного
репо — измеримо выше ROI на 1 ток-правку, чем локальная правка одного CLAUDE.md.
Оценка: сжатие топ-7 на ~30% (≈260 ток суммарно) экономит ≈260×N резидента на КАЖДОМ подписанном
проекте за сессию — точное число подписчиков вне данных этого item'а (не в `budget.py`), нужен
замер числа проектов на бакет `architect`/`system` (P5.3/backlog).

## Инструмент-сбои
Нет — `skiller budget --first-turn` отработал на всех 5 проектах без n/a-источников
(предупреждение `WARN: 'session-observer' requires 'shared-memory'` на 3 проектах —
конфигурационный шум resolve_requires, НЕ сбой измерения: числа сошлись, tier0 посчитан).

## Пробелы / вне scope этого item'а
- Правки-сжатия (CLAUDE.md/description/MCP-набор) — НЕ делаются здесь (Scope Excluded P5.1).
- Число проектов-подписчиков на бакеты `architect`/`system` (нужно для точного множителя К3) —
  не измерено (не входит в `budget.py`), кандидат для P5.3/backlog-уточнения.
- Внешние best-practices (P5.2) — отдельный item.
