# observer — capture-слой (PreToolUse / PostToolUse / Stop)

ЭКСПЕРИМЕНТАЛЬНО, per-project. Лёгкий project-local захват сессии для post-hoc
разбора скиллом `system/session-observer`. Дополняет сырой session-JSONL
(`~/.claude/projects/…`) вычисленными алертами (LOOP) и компактной записью.

**Никогда не блокирует** — это наблюдатель, не гейт (гейт архитектуры —
`review-gate`). Все события → `exit 0`.

## Включение (per-project, два шага)

1. **Флаг:** `.claude/observer.env.ini` → `ENABLED=true` (дефолт `false` = no-op).
   Через Claude — `/observe on` (скилл `system/session-observer`).
2. **Проводка** (opt-in, не глобально — иначе хук на КАЖДЫЙ tool-call у всех):
   ```
   harness hooks --target . --preset observer   # или apply-permissions --preset observer
   ```
   добавляет в `.claude/settings.local.json` хуки PreToolUse/PostToolUse/Stop →
   `~/.claude/hooks/observer/observer.sh`.

## Что пишет → `.claude/observer/`

| Файл | Содержание |
|---|---|
| `runtime.jsonl` | поток PRE/POST по tool-call + алерты (`LOOP` при 3+ ошибках подряд) |
| `last_report.md` | краткий итог на Stop (число вызовов, алертов) |
| `archive/<ts>.jsonl` | архив лога по завершении сессии |
| `error_count` | служебный счётчик (сбрасывается на успех/Stop) |

Каталог `.claude/observer/` — добавь в `.gitignore` проекта.

## Разбор

`/observe session` (скилл `system/session-observer`) читает `runtime.jsonl` +
архив + session-JSONL + `git diff` → 3-осевая аналитика слабых мест
(агенты/скиллы/настройки) → learnings через memory-хук.
