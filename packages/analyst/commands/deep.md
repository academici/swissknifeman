---
description: Глубокий разбор прогонов агентом-аналитиком (digest-first) — скрипты собирают JSON-выжимки, агент строит каузальный нарратив; raw-транскрипты запрещены.
argument-hint: "[фокус разбора: «почему дорого», «resolve CONFLICT», «деградация роли X», …]"
allowed-tools: Bash(mkdir:*), Bash(maind:*), Bash(analyst:*), Read, Write, Task
---
## Сбор выжимок (digest-first — агент получит ТОЛЬКО эти JSON)
!`mkdir -p .claude/analyst/deep`
!`maind analyze --cwd --json > .claude/analyst/deep/analyze.json 2>&1 || true`
!`analyst token-report --json > .claude/analyst/deep/token-report.json 2>&1 || true`
!`analyst review --json > .claude/analyst/deep/review.json 2>&1 || true`

Три команды выше уже отработали и записали выжимки в `.claude/analyst/deep/`
(`analyze.json`, `token-report.json`, `review.json`). Дальше:

1. **Запусти субагента `analyst`** (Task, subagent_type `analyst`). В промпт передай:
   - **пути** к трём JSON-файлам (`.claude/analyst/deep/analyze.json`,
     `.claude/analyst/deep/token-report.json`, `.claude/analyst/deep/review.json`) —
     именно пути, НЕ содержимое;
   - фокус разбора от пользователя: «$ARGUMENTS» (пусто — полный плейбук:
     стоимость/патологии, hidden scope expansion, качество handoff, деградация
     cheap-моделей, resolve CONFLICT-уроков, тексты remediation).
   **Запрещено** (и тебе, и субагенту): читать raw-транскрипты сессий
   (`~/.claude/**/*.jsonl` и любые session-логи) и передавать их содержимое —
   вход агента только выжимки; если какой-то из файлов содержит текст ошибки
   вместо JSON (например, нет usage-trend) — так и передай, агент учтёт пробел данных.

2. **Прими результат агента**: каузальный нарратив + блок findings JSON
   (схема — контракт `analyst ingest`, см. описание агента).

3. **Сохрани findings** в `.claude/analyst/deep/findings.json` (ровно тот JSON,
   что вернул агент, без правок) и выполни:
   `analyst ingest --file .claude/analyst/deep/findings.json`
   Пустые findings (`"findings": []`) — ingest не запускай, так и скажи владельцу.

4. **Покажи владельцу**: нарратив агента, итог ingest (сколько уроков в ephemeral,
   сколько пропущено как дубли), находки с маркером PROMOTE-CANDIDATE — отдельным
   списком с напоминанием, что промоут делает только человек:
   `analyst review` → `analyst promote <id>`.

Инварианты: никакого авто-промоута (все уроки агента — только ephemeral, гейт — человек);
сырьё остаётся LOCAL (наружу — числа и абстракции). Команда on-demand — после серии
ATTENTION или еженедельно, не per-session.

> Требуются CLI `analyst` и `maind` в PATH (репозиторий swissknifeman → `./install.sh`).
