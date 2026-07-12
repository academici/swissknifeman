# HANDOFF — 2026-07-12 — after P1.3 (P1 закрыта, 3/3)

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P2.1

| Параметр | Значение |
|:--|:--|
| Model | fable или opus/high (D-роутинг: компрессия policy без потери семантики — вердикт-чувствительно) |
| Thinking | high |
| Context | fresh session, корень репо swissknifeman |
| Суть | P2.1 (harness: компрессия agent-router policy → v2, терс-EN ≤400 ток) — ГЕЙТ: нет (P1 закрыта) |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P1→P5+P7, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P2.1 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P2.md; нормы: findings/P0-rag-context-economy.md
````

**Done:** P1.1 (digest-бюджет) — `select_digest_items` в packages/maind/lib/maind/memory.py
(чистая функция, байт-бюджет 4000/item_max 500/shared_max=0 project-only, D10) + 4 константы
в constants.py + config-дефолты `memory.digest` в config.py + 3 CLI-флага
(`--budget-chars --item-max --shared-max`) + 9 новых тестов; `validate.sh` → 397 OK.
P1.2 (шаблоны хуков) — session-start-hook.sh переведён на `health --cwd --strict`: rc=0 →
тихий `exit 0`, rc≠0 → печать stdout, затем `exit 0`; memory-digest-hook.sh — бамп-комментарий
шапки (byte-change → stale для sync), вызов остался argless. 5 новых тестов; `validate.sh` → 402 OK.
P1.3 (гайдлайн межпроектной памяти) — ecosystem-mcp (источник, `packages/maind/templates/skills/
ecosystem-mcp/SKILL.md`) дополнен оговоркой «дайджест — только свой проект» + секцией
«Межпроектная задача (2+ проекта)»: 3 шага (`maind graph --project X`/`maind_graph_path` →
`maind memory recall --scope ns:<имя>` → `maind memory remember --scope ns:<имя>`, не
`--project --share`). Тот же гайдлайн — в локальных скиллах `maind-overview`,
`cross-project-optimizer`, `ecosystem-integration` (короткие оговорки + ссылки на источник и
доку, не переписывание). `docs/guide/memory.md` — абзац project-only(`shared_max=0`) в разделе
digest + новая секция «Межпроектная задача — как явно поднять shared-контекст»;
`docs/guide/namespaces.md` — та же оговорка-исключение у таблицы recall_scopes. Все команды
сверены `--help` на HEAD, MCP-имена (`maind_graph_path/neighbors`, `maind_memory_recall/store`)
сверены со списком `TOOLS` в `mcp.py` — не по памяти. 9 новых тестов
(`packages/maind/tests/test_p13_cross_project_memory_docs.py`); `validate.sh` → 411 тестов OK.
Фаза **P1 закрыта (3/3 🟢)**.
**Remaining:** 7 фаз / 19 items ⬜, P1 — 3/3 🟢 (закрыта) · P2 router v2 (1) ·
P3 описания скиллов (2, порядок P3.1→P3.2) · P4 agent-packs (2) · P5 footprint+телеметрия (4) ·
P6 rollout+замер (4, baseline ДО раскатки, Owner-гейты) · P7 bootstrap машины (2) ·
P8 доктрина+скиллы/доки+релиз v0.9.0 (4). Роутинг-отклонения: P2.1 — fable/opus (семантика
policy), P6.3 — AskUserQuestion per-project, P8.4 — approve Owner на тег. Workflow покрывает
P1→P5+P7; P6 и P8 — с человеком.
**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D14: D4 router сжать ·
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
