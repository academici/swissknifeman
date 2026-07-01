# run-report — архивный захват исхода прогона (SessionEnd)

Один **Python-хук** Claude Code (`SessionEnd`), который в конце сессии читает транскрипт и
пишет структурированный **run-report** в `<project>/.claude/runs/<session_id>.json`. Отсюда
[`maind analyze`](../../../../../maind/) собирает пост-ран отчёт «всё ли сработало как надо».

Захват **универсальный** (generic): исход снимается из транскрипта для ЛЮБОЙ задачи — не только
dev-loop-воркфлоу. Поэтому `dev-loop.js`/паки трогать не нужно (verified perplexity-web по
офиц. докам: SessionEnd получает `transcript_path`+`session_id`+`cwd` и может писать на диск).

## Что извлекает (защитно, деградирует по наличию)

| Срез | Источник в транскрипте |
|:--|:--|
| `tools.by_name` / `.total` | все `tool_use`-блоки (Bash/Edit/Write/Workflow/Task/…) |
| `bash.tests` / `.lints` | Bash-команды по паттерну (pytest/phpunit/pest/ruff/pint/validate.sh…) + `ok` из `is_error` |
| `bash.failed` | Bash-команды, чей `tool_result.is_error=true` |
| `tool_failures` | любой `tool_result.is_error=true` (инструмент + срез вывода) |
| `files_changed` | `file_path`/`notebook_path` из Edit/Write/MultiEdit/NotebookEdit + `toolUseResult.filePath` |
| `workflows` | `toolUseResult` воркфлоу (`workflowName`/`status`/`summary`) |
| `devloop` | best-effort: JSON с `tool_failures`/`workarounds`/`deferred`/`open_questions`/`results` в результате воркфлоу/агента |

## Файлы

| Файл | Роль |
|:--|:--|
| `run-report.py` | SessionEnd-хук: stdin → транскрипт → `.claude/runs/<sid>.json` (атомарно, ретеншн) |
| `_lib.py` | защитный **строчный** парсер транскрипта (без слурпа) — тестируемо отдельно |
| `env.ini` | `ENABLED` (kill-switch) + `RUNS_KEEP` (ретеншн). Per-project override в `.claude/run-report.env.ini` |

## Установка / включение

```bash
harness hooks --global                      # копирует хук в ~/.claude/hooks/run-report/
harness hooks --target . --run-report on     # включить в проекте (env.ini + регистрация SessionEnd)
maind analyze --project <id>                 # разбор накопленных run-report'ов
```

## I/O-контракт (для отладки)

Хук читает JSON payload на stdin (`transcript_path`/`session_id`/`cwd`/`reason`), пишет файл
`<cwd>/.claude/runs/<session_id>.json` и ничего в stdout (SessionEnd stdout не виден модели).
Каталог `runs/` **само-игнорируется** (`.gitignore` = `*`): run-report'ы эфемерны/машинно-локальны,
не засоряют `git status` (и не ломают проверку «чистое дерево» в `maind analyze`).

```bash
echo '{"transcript_path":"/path/to/session.jsonl","cwd":"/proj","session_id":"s1"}' \
  | python3 run-report.py          # → /proj/.claude/runs/s1.json
echo 'not json{' | python3 run-report.py   # → exit 0, ничего не пишет
```

## Честные лимиты (не переобещаем)

- **Схема транскрипта не заморожена** официально (verified perplexity-web: стабильна к
  аддитивным изменениям, но не контракт) → парс **защитный**, на ошибке хук молчит (exit 0),
  а `maind analyze` деградирует на форензику (bash-лог + git-diff).
- **`SessionEnd` = одна запись на сессию** — несколько задач в одной сессии сольются в один
  run-report. Нужен per-turn — потребуется `Stop`-вариант (follow-up).
- **`bash.tests`/`.lints` — эвристика по паттернам команд**; `ok` берётся из `is_error`
  tool_result (надёжно), но классификация «это тест/линт» может промахнуться на нетипичных командах.
- **`devloop` — best-effort**: зависит от того, вынес ли воркфлоу структурный результат в
  транскрипт; нет — довольствуемся `workflows[].summary`.
