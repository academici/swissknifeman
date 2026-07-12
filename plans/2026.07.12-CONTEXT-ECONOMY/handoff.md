# HANDOFF — 2026-07-12 — after P0.0

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P1.1

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | автономный пролёт P1→P5+P7 workflow'ом (D14) ЛИБО поштучно с P1.1 |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P1→P5+P7, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P1.1 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P1.md; нормы: findings/P0-rag-context-economy.md; гейт: сперва закоммитить/запарковать грязное дерево (skills/ai/mcp-builder/ + regen-артефакты) отдельным коммитом
````

**Done:** — (план создан plan-design'ом, исполнение не начиналось; закрытых items нет)
**Remaining:** все 8 фаз / 22 items ⬜: P1 maind digest+health+гайдлайн памяти (3) ·
P2 router v2 (1) · P3 описания скиллов (2, порядок P3.1→P3.2) · P4 agent-packs (2) ·
P5 footprint+телеметрия (4) · P6 rollout+замер (4, baseline ДО раскатки, Owner-гейты) ·
P7 bootstrap машины (2) · P8 доктрина+скиллы/доки+релиз v0.9.0 (4). Роутинг-отклонения:
P2.1 — fable/opus (семантика policy), P6.3 — AskUserQuestion per-project, P8.4 — approve
Owner на тег. Workflow покрывает P1→P5+P7; P6 и P8 — с человеком.
**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D12: D4 router сжать ·
D6 описания+бакеты · D9 версии/тег · D10 digest project-only, supersede D5 · D12 память между
машинами → roadmap) · phases/P1.md–P8.md · findings/P0-rag-context-economy.md (нормы бюджетов,
OTEL, декомпозиция инцидента) · findings/P0-rag-bootstrap-memory-sync.md (bootstrap-паттерн,
запрет shared-папки для стора) · scratchpad сессии 4af788f3 (analyze_sessions.py — референс,
переносится в analyst в P5.3).
**Open risks:** живой прогон SessionStart-хуков в P5.1 исполняет чужие скрипты — обязателен
fail-soft/timeout (в ТЗ); P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация
(в P6.2); encoded-cwd формат jsonl-каталогов в P5.3 проверить на живых каталогах, не угадывать.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет P5.4 (D7 — допустим ⛔ Skipped с roadmap-стабом) · межкомпьютерная
  память (D12 — roadmap/cross-machine-memory.md пишется в P7.2)
- open_questions: —
