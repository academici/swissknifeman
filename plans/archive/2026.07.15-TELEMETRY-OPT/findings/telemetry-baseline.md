# Телеметрия swissknifeman-экосистемы — доказательная база плана оптимизации
Окно: последние 4 дня (2026-07-11 … 07-15). Источник: 114 run-reports (schema v2) в `*/.claude/runs/`, 8 проектов.
Агрегатор: scratchpad/agg.py (find-based, читает usage/workflows/error_loops/tool_failures/reads/retrieval).

## Токены (totals, 4 дня)
- out **13.9M** · in 338.4K · cache_read **2.3B** · cache_creation 57.9M
- cache_hit ≈ **100%** во ВСЕХ проектах; low_cache_runs(<90%) = **0/114** → промах-кэша НЕТ.
- Вес стоимости = объём контекста (2.3B cache_read), не промахи. Драйвер: большой always-on
  контекст × 114 сессий + fan-out воркфлоу (субагенты перечитывают системный промпт).
- Model out: **Opus 8.1M** · Sonnet 5.4M · Fable 290K · Haiku 38K. Opus доминирует
  (task:design/review/plan-audit пинят Opus/xhigh — намеренно, но самый дорогой рычаг).

Топ проектов по out: vaulter 3.8M (cache_rd 745M!), swissknifeman 3.2M, dterema 2.5M, corex 2.4M, vintera 1.4M.

## Workflow — главный дефект
- dterema `dterema-site-p3-api`: **15× async_launched в ОДНОМ сеансе** (657a7deb, 07-15T04:18),
  agents=None, статус завершения не записан НИ разу. `p2-filament` ×3, `figma-recon` ×2 — та же схема.
- Диагноз: async-launch воркфлоу НЕ рапортует о завершении/провале обратно в сессию → цикл
  перезапускает идентичный named-workflow → повторный fan-out жжёт токены. Это «постоянные
  одни и те же итерации / RED» из жалобы.
- Всего workflow-записей: 23 (dterema 19, corex 2, swissknifeman 1, vintera 1).

## Churn на тул-фейлах: 328 за 4 дня (~2.9/run)
Категоризация (scratchpad):
- 118 DENY(policy) — by-design (rm в защищённых/опасные), но агенты повторно долбятся в запрет
  (напр. `rm -rf .claude/skills/plan-protocol`). Устранимо обучением safe-путям (harness safe-dirs).
- 103 Bash exit≠0 — реальные ошибки команд.
- **46 EDIT/WRITE «not-read-first» + 16 edit string-not-found/not-unique** — 100% устранимый churn.
- reread(extra) **392** — перечитывание одних файлов.
- Playwright ~11 — флак браузера (vintera/dterema фронт).
- test_failures всего 7 — тесты зелёные.
- retrieval.repeated_queries = 0 — RAG-дублей нет.

## Фазовая раскладка (подтверждена как охват плана)
- P1 Workflow completion-signal: async→обязательный рапорт о завершении/провале; анти-релонч
  идентичного named-workflow; детект «N× один и тот же wf» в run-report/analyst.
- P2 Churn-гейт файл-операций: read-before-edit правило/хук; сжать 46+16 фейлов + reread 392.
- P3 Model-routing аудит: где Opus/xhigh реально нужен vs Sonnet/Fable; политика по task:*; цель — сдвиг Opus-доли.
- P4 Permission-friction: 118 DENY — обучить safe-путям, убрать повторные тычки в запрет.

## Решения (зафиксированы с пользователем)
- Дизайн-синтез плана — **Opus 4.8 / high** (пин /task:plan-design). Research-fanout и exec — Fable/Sonnet.
- Охват — **все 4 фазы**.
