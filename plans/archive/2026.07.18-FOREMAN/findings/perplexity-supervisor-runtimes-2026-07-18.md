---
type: finding
plan: 2026.07.18-FOREMAN
source: perplexity-web search_advanced (web+social), 2026-07-18
urls:
  - https://pyshine.com/Gas-Town-Multi-Agent-AI-Coding-Orchestration/
  - https://deepwiki.com/mikeyobrien/ralph-orchestrator/2.2-quick-start-guide
  - https://venturebeat.com/orchestration/claude-codes-tasks-update-lets-agents-work-longer-and-coordinate-across
verdict: verified по вторичным источникам; детали (лицензия Ralph, формат ~/.claude/tasks, версии Gas Town) перепроверить по first-party в P0.4/P0.6
---

# Perplexity: готовые супервизор-рантаймы с durable file-state и resume

Запрос: рантаймы-оркестраторы флотов Claude Code с файловым состоянием, crash-resume
по папке (не session id), мандатами/зонами ответственности.

## Вердикт для владельца: ход мыслей ПОДТВЕРЖДЁН

«Run-folder по аналогии с plans/ + resume по папке, а не по сессии; сиюминутный state
НЕ в общую память» — это мейнстрим-паттерн зрелых оркестраторов 2026. Точной готовой
реализации «resume-by-folder как первичный ключ + декларативный мандат» нет ни у кого —
но есть три донора шаблонов.

## 1. Gas Town (Steve Yegge) — MIT, ~15k★, v1.2.0 (май 2026), активный

Мульти-агентный оркестратор флотов (20–30 агентов: CC/Codex/Copilot/Gemini).

- **Иерархия ролей с явными мандатами** (≈ наша D11-рекурсия): Mayor (общая координация),
  Witness (здоровье воркеров одного rig'а, детект застрявших, восстановление),
  Deacon (кросс-rig патруль, эскалация), Refinery (merge-очередь).
- **Durable state**: hooks = git worktrees (переживают краши), beads = git-backed
  ledger задач (durable ID независимы от сессий), convoys = батчи со stall-детектом,
  Seance = discovery прошлых прогонов через `.events.jsonl`.
- Resume — по bead/convoy/hook, НЕ по session id. OTEL-телеметрия.
- Для Artifex: **референс архитектуры ролей и зон ответственности** (Witness ≈ проектный
  Artifex, Deacon ≈ корневой), beads уже в нашем аудите (D15е). Целиком не брать —
  свой тяжёлый мир (tmux, риги), у нас plan-protocol как SSOT.

## 2. Ralph orchestrator — state-layout как ШАБЛОН run-folder

Документированный стабильный формат состояния в workspace:

- `events-*.jsonl` — журнал per run (append-only);
- `tasks.jsonl` — append-only задачи с маркерами завершения;
- `memories.md` — durable память под git;
- `specs/` — артефакты требований.
- Termination-контур: LOOP_COMPLETE-сигнал, max_iterations (100), max_runtime (4ч),
  **output similarity ≥90% на последних итерациях = разрыв цикла** (готовая эвристика
  для нашего P5-thrash-детекта!).
- Resume естественно «по папке»: перезапустил в том же workspace — увидел state.

## 3. Claude Code Tasks — first-party примитив (2026)

- Задачи в `~/.claude/tasks` — переживают краши терминала/ребут машины.
- **DAG-зависимости** («blocked by») из коробки.
- `CLAUDE_CODE_TASK_LIST_ID` — НЕСКОЛЬКО сессий делят один task list (координация
  параллельных воркеров first-party!). `CLAUDE_CODE_ENABLE_TASKS` — opt-in/out.
- Для Artifex: кандидат на роль DAG-очереди items вместо собственной; проверить формат
  и стабильность по first-party доке (P0.4) — если пригоден, P2-очередь сильно дешевеет.

## Проекция на Artifex

1. **Run-folder канон** — строим свой (по аналогии с plans/), слизывая layout Ralph:
   `brief/` (мандат), `state.json`, `journal.jsonl`, отчёты. Готового нет — D16.
2. **Мандат/зоны** — референс ролей Gas Town для иерархии D11.
3. **Thrash-эвристика similarity ≥90%** — в копилку P5.1 (дёшево, дополняет mem0-машину
   состояний и cost-aware сигнал).
4. **CC Tasks** — потенциальный first-party кусок для очереди/DAG (P0.4 проверка).
5. Сиюминутный state — в run-folder, НЕ в mAInd; в mAInd — только итоги прогона (D4/D16).
