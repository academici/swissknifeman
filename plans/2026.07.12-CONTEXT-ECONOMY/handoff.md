# HANDOFF — 2026-07-12 — after P5.1

**Next:** /task:plan-exec 2026.07.12-CONTEXT-ECONOMY P5.2

| Параметр | Значение |
|:--|:--|
| Model | sonnet/medium (дефолт SSOT — P5 без роутинг-отклонений) |
| Thinking | medium |
| Context | fresh session, корень репо swissknifeman |
| Суть | P5.2 (`maind doctor --context`, флот-агрегация) — ГЕЙТ: нет (P5.1 закрыт зелёным) |

Основной путь (D14) — общий workflow-исполнитель с per-item роутингом моделей
(автономно P1→P5+P7, стоп перед Owner-гейтами P6/P8; запуск строго scriptPath):

````
Workflow({scriptPath: "plans/2026.07.12-CONTEXT-ECONOMY/workflows/wf-context-economy-exec.js"})
````

Альтернатива — поштучно:

````
/task:plan-exec 2026.07.12-CONTEXT-ECONOMY P5.2 — ТЗ: plans/2026.07.12-CONTEXT-ECONOMY/phases/P5.md
````

**Done:** P1 (3/3 🟢) — digest-бюджет (`select_digest_items` project-only shared_max=0, D10),
тихий health-хук, гайдлайн межпроектной памяти в скиллах/доках. P2.1 (фаза P2 1/1 🟢) — policy
config.json agent-router сжат до 1186 симв ≈296 ток. P3 (2/2 🟢) — рэтчет описаний скиллов
закрыт целиком. **P4 (2/2 🟢) закрыта целиком:** диета `description` 44 агентов 10 паков +
регрессионный cap-тест + `.bak`-warn в doctor. **P5.1 закрыт (фаза P5 1/4 🟡):**
`skiller budget --first-turn [--target DIR] [--json] [--strict]` — `first_turn_report`/
`format_first_turn_report` в `packages/skiller/lib/skiller/budget.py`: 5 источников (skills
tier-0 через `resolve_active_set`, `.claude/agents/*.md` frontmatter, CLAUDE.md + `.claude/rules/*.md`
без `paths:`, живой `subprocess`-прогон SessionStart-хуков — timeout=10s, fail-soft per-hook,
парсинг `hookSpecificOutput.additionalContext` либо сырой stdout, MCP tool-defs — статичная таблица
`KNOWN_MCP_TOOLS` (`maind`=11 точно из `mcp.py::TOOLS`, остальные — инженерная прикидка, не
RAG-verified построчно) × `TOKENS_PER_MCP_TOOL`=150 по `.mcp.json`, неизвестный сервер —
`FALLBACK_MCP_TOOLS`). Вердикт `OK ≤7K · ELEVATED ≤10K · WARN >10K`; `--strict` → exit 1 при WARN.
7 тестов (`packages/skiller/tests/test_budget_first_turn.py`, tmpdir-фикстура): суммирование
источников, n/a на сломанном хуке (не исключение), CLI `--json`/`--strict`, known/unknown MCP,
path-scoped rule исключается из суммы. Живой прогон `--target agelto` — skills 5571, agents 2343,
hooks 265 (все ненулевые, как требует Validation), MCP 10950, CLAUDE.md 15409 → итог 34538 WARN.
`validate.sh` 379 тестов, exit 0.
**Remaining:** P5 footprint+телеметрия (P5.2–P5.4, 3 items) · P6 rollout+замер (4, baseline ДО
раскатки, Owner-гейты; включает P6.2 resync router-артефакта на машину/флот — D3, а также раскатку
P4-диеты на подключённые проекты через `agent-packs upgrade`) · P7 bootstrap машины (2) ·
P8 доктрина+скиллы/доки+релиз v0.9.0 (5). Роутинг-отклонения: P6.3 — AskUserQuestion
per-project, P8.4 — approve Owner на тег. Workflow покрывает P1→P5+P7; P6 и P8 — с человеком.
**Sources of truth:** plans/2026.07.12-CONTEXT-ECONOMY/plan.md (D-лог D1–D16) · phases/P1.md–P8.md
(P5.1 Completion Notes в phases/P5.md) ·
findings/P0-rag-context-economy.md (нормы бюджетов, использованы в порогах P5.1) ·
findings/P0-rag-bootstrap-memory-sync.md ·
scratchpad сессии 4af788f3 (analyze_sessions.py — референс, переносится в analyst в P5.3).
**Open risks:** P5.2 (`maind doctor --context`) зовёт `skiller budget --first-turn --target <path>
--json` subprocess по флоту ~17 проектов — на проекте без skiller/битым выводом отчёт должен
показывать `n/a`, скан не должен падать (fail-soft уже заложен в P5.1 JSON-контракте: `tokens: null`
per-источник плюс общий `total`/`verdict`, P5.2 переиспользует эти поля, не дублирует математику);
P6 меняет ~17 проектов — сбой волны >3 проектов = стоп+эскалация (в P6.2); encoded-cwd формат
jsonl-каталогов в P5.3 проверить на живых каталогах, не угадывать.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: OTEL-пресет P5.4 (D7 — допустим ⛔ Skipped с roadmap-стабом) · межкомпьютерная
  память (D12 — roadmap/cross-machine-memory.md пишется в P7.2) · burn-down `desc-burndown.txt`
  (64 скилла, из P3) — легальный, но неразрешённый долг; сокращать по мере правок конкретных
  скиллов (не отдельный item плана) · KNOWN_MCP_TOOLS в budget.py — инженерная прикидка числа
  tool-схем per сервер (не RAG-verified построчно), пересмотреть при живом расхождении
- open_questions: —
