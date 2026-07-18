---
type: finding
plan: 2026.07.18-FOREMAN
source: claude-code-guide agent (first-party docs code.claude.com) + локальная проверка `claude --help`
date: 2026-07-18
verdict: verified (кроме флагов в разделе «Неопределённости»)
---

# Headless-возможности Claude Code — верифицированный факт-лист

Источники: https://code.claude.com/docs/en/headless.md · hooks.md · permission-modes.md ·
sessions.md · scheduled-tasks.md · agent-view.md · goal.md. Собрано агентом
claude-code-guide 2026-07-18; локально подтверждены флаги `--bg`, `--bare`,
`--permission-mode`, `--dangerously-skip-permissions` (`claude --help`).

## 1. `claude -p` (headless) грузит контекст как интерактив

| Аспект | Дефолт | С `--bare` |
|:--|:--|:--|
| Скиллы проекта (.claude/skills, плагины) | грузятся | нет |
| CLAUDE.md | грузится | нет |
| Хуки | грузятся и работают | нет |
| MCP (.mcp.json + ~/.claude) | грузятся | только через `--mcp-config` |

→ Главный вывод для Artifex: **воркер `claude -p` видит весь тулинг владельца** —
причина отказа от Cowork/Coder снимается.

## 2. Хуки — 31 событие

Ключевые для Artifex:
- **Notification** (не блокирует; matchers: `permission_prompt`, `idle_prompt`,
  `agent_needs_input`, `agent_completed` — последние два требуют CC ≥ v2.1.198).
- **Stop** (может блокировать: exit 2 / `{"decision":"block"}`).
- **PreToolUse** — авто-решение по permissions: `hookSpecificOutput.permissionDecision:
  allow|deny|ask|defer` + `updatedInput` + `additionalContext`.
- **PermissionRequest** — авто-approve узко скоупленных промптов структурным JSON.
- SessionStart/SessionEnd, PreCompact/PostCompact, SubagentStart/Stop, TaskCreated/Completed.

Все хуки — 5 типов хендлеров: command (произвольный shell — Telegram curl легален),
HTTP, MCP tool, prompt, agent.

## 3. Unattended permissions

| Режим | Поведение в `-p` |
|:--|:--|
| default/plan | промпт → headless-сессия падает |
| acceptEdits | авто-approve правок файлов + безопасных fs-команд; сеть/прочий Bash — блок |
| auto | классификатор; ~3 отказа или 20 всего → fallback на промпт (в headless = abort) |
| dontAsk | авто-deny всего вне `permissions.allow` + read-only; AskUserQuestion всегда deny |
| bypassPermissions | пропуск всех проверок кроме `ask`-правил + circuit breaker |

- `--allowedTools "Bash(git diff *),..."` — пре-approve по паттернам.
- **AskUserQuestion в headless — denied** → канал эскалации воркера = handoff
  (ATTENTION/Escalation Needed), не вопрос.
- **`defer` в `-p`**: хук может вернуть defer — процесс выходит с сохранённым pending
  tool call, Agent SDK-обёртка может собрать ввод и продолжить. Родной механизм
  remote-approve.

## 4. Сессии

- `--continue` (последняя в CWD) и `--resume <session-id>` работают в `-p`.
- `session_id` — в выводе `--output-format json`.
- Auto-compact в headless работает (порог не документирован).
- При resume НЕ восстанавливаются: `--mcp-config`, `--settings`, `--plugin-dir`,
  mid-session `/add-dir` — передавать заново.

## 5. Структурный вывод

- `--output-format json`: `result`, `session_id`, `total_cost_usd`, `is_error`,
  `num_turns`, `duration_ms`, разбивка по моделям; `--json-schema` → `structured_output`.
- `--output-format stream-json`: NDJSON, финальная строка — `result` с метаданными;
  `parent_tool_use_id` различает субагентов.

## 6. Нативные механизмы длинных прогонов

- **`claude --bg` + `claude agents`**: встроенный супервизор фоновых сессий
  (attach/logs/stop/respawn, worktree-изоляция, `--json`). 10 параллельных ≈ 10× квота.
- **`/goal "<условие>"`**: condition-loop (Haiku-евалюатор после каждого хода),
  работает в `-p`; требует включённых хуков.
- **`/loop`**: интервальный/динамический цикл в сессии; истекает через 7 дней.
- **Routines (`/schedule`)**: облачный cron, переживает ребут машины, но облачная
  среда ≠ локальные хуки/скиллы.
- v2.1.163+: фоновые Bash-задачи убиваются ~5s после финального результата `-p`
  (субагенты — 10 мин cap, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`).

## Неопределённости — СНЯТЫ в P0.4 (см. findings/headless-uncertainties-resolved-2026-07-18.md)

| Пункт | Статус (P0.4, 2026-07-18) |
|:--|:--|
| `--max-turns` | **RESOLVED: СУЩЕСТВУЕТ и работает** на 2.1.214 (live exec exit 0, num_turns:1) + `--max-budget-usd`; D7 переворачивается — драйвер лимитит ходы/стоимость штатными флагами. Прежнее «не найден» — промах grep |
| Порог auto-compact в `-p` | **RESOLVED: управляем** env `CLAUDE_CODE_AUTO_COMPACT_WINDOW` / `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (1-100), полностью не отключаем → драйверу нужен свой контроль размера (OQ-3) |
| AskUserQuestion в `auto` mode | **RESOLVED: не auto-approve** (требует ввода, не разрешения) → эскалация через handoff, не вопрос |
| Механика `defer` + Agent SDK resume | **[UNVERIFIED]: не гарантирована дока** → Layer 3/P4.3 опционален, MVP без него (OQ-2) |
| CC Tasks `~/.claude/tasks` | **[UNVERIFIED]: не first-party примитив** (только session-scoped /loop+Cron; локально dir отсутствует) → драйвер строит свою очередь (P0.6) |
| Баги #49525/#39973 | **RESOLVED: НЕ пофикшены** (closed not_planned/stale; #49525 «still broken 2.1.113/114») → permission-mode флагом, не хуком (D28) |
| quota-детект | **RESOLVED:** `is_error`+exit 1; 5h vs weekly по тексту «session/weekly limit»; reset-ts нет; релогин подхват на следующем запуске (D18) |
