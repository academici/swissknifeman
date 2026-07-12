# HANDOFF — 2026-07-12 — after P8.1

**Next:** P8.2 (скиллы и доки репо: синхронизация с философией релиза).

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium |
| Thinking | medium — не редактирование по шаблону: нужно свежее чтение `--help` новых команд + Completion Notes P5.1–P5.3/P7.1–P7.2/P3.2, чек-лист прохода из phases/P8.md P8.2 Code Guidance |
| Context | fresh session — handoff свежий, рекомендован `/clear` (ручной item, оркестрации не требует по P8.5-критерию: единичный item без независимого parallelizable scope) |
| Суть | Пройти локальные скиллы (package-architecture, harness-operations, project-tooling-runbook, ecosystem-setup-шаблон maind) + package-доки — отразить footprint-бюджет/`skiller budget --first-turn`/`maind doctor --context`/`analyst sessions`/bootstrap-машины/desc-гейт/digest project-only; убрать устаревшие утверждения; таблица прохода в Completion Notes |

```
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P8.2
```

**Done:** P1–P7 закрыты (см. Update Log plan.md). P8.1 закрыт (фаза P8 1/5 🟡):
доктрина budget-гейта для always-on инжектов — 3 строки в root CLAUDE.md «Рамки»
(файл 182 строки, ≤200 держит) + компактная запись памяти mAInd (scope `ns:axioma`,
key `first-turn-budget-doctrine`, id `mem_mrhonmn9_c3173fce7977`, 400 симв);
`maind_memory_recall("first-turn бюджет", ns:axioma)` подтверждён (запись первой,
score 19.1). Коммит `04476f9`.

**Remaining:** P8.2–P8.5 (4 items): P8.2 скиллы/доки-синхронизация (должна честно
отразить и ограничение эффекта P6.4, не только достижения P1–P5/P7); P8.3
релиз-подготовка (CHANGELOG, версии D9, registry, validate, паспорт
findings/P8-release.md); P8.4 approve Owner + тег v0.9.0 — **ручной стоп-гейт**,
тег только с явного approve (D17 исключение это НЕ отменяет); P8.5 task-package
доктрина оркестрации (критерий Workflow + session-restart discipline в
plan-protocol/plan-exec, живой инцидент этой же сессии P1–P4, D16).

**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D17) ·
phases/P1.md–P8.md · findings/P0-rag-context-economy.md ·
findings/P0-rag-bootstrap-memory-sync.md · findings/P6-baseline.md ·
findings/P6-rollout.md · findings/P6-buckets.md · findings/P6-after.md ·
docs/rejected-optimizations.md · roadmap/cross-machine-memory.md · root
CLAUDE.md «Философия и рамки» (доктрина P8.1, новая строка).

**Open risks:**
- P8.1 доктрина ограничена явно (Scope Excluded): область — hook
  additionalContext / description скилла-агента-команды / CLAUDE.md-блок /
  MCP-сервер; `skiller budget --first-turn` НЕ покрывает CLAUDE.md/rules и MCP
  tool-defs как управляемые рычаги (P6.4-находка) — доктрина этот разрыв не
  закрывает, только называет; если Owner захочет расширить область — отдельный
  item, не расширение P8.1 задним числом.
- vendor-измерение (`budget.py`↔`skillset.py`, находка P6.3 §0) остаётся
  неотремонтированным — будущие сравнения через `doctor --context` продолжат
  мерить фиктивный autodetect-профиль там, где подключён vendor-канал.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: как в предыдущем handoff (OTEL-пресет D7, межкомпьютерная память D12,
  манифест `profile`-поле, burn-down desc-burndown.txt, KNOWN_MCP_TOOLS, encode_cwd
  `.`/`_`, flexcrm/sova `.swissknifeman/config.json` отсутствует, vintera legacy-
  имена бакетов, dterema 9-файловый конфликт, 4 проекта `.pack-new` ручной мерж,
  починка `budget.py`/`doctor --context` под vendor-канал, sibintek-insiders
  недо-поставка laravel-filament/frontend-vue/azguard, memster base `frontend`
  бакет, agelto vendor-бакет `general`) + два кандидата из P6.4 Pending Work
  (per-project CLAUDE.md-диета фронтовых проектов; per-project MCP-сервер ревизия
  `core:mcp-advisor`) — оба вне Scope этого плана, кандидаты для нового
  item/фазы/плана.
- open_questions: —
