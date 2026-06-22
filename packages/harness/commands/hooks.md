---
description: "Включить хуки Claude Code (auto-approve/memory) по проекту или поставить файлы хуков глобально."
---
Настрой хуки харнеса.

Глобальная установка файлов хуков (один раз на машину — кладёт `auto-approve/`, `memory/`, `notify/`, `log-bash-command` в `~/.claude/hooks/`):
```
harness hooks --global [--dry-run]
```

По проекту (включить режимы — файлы хуков должны быть уже установлены глобально):
```
harness hooks --target . [--auto-approve strict|permissive|bypass|off] [--memory core:federation] [--file settings.json] [--dry-run]
```
- `--auto-approve` пишет `.claude/auto-approve.env.ini` и регистрирует хук на Bash/ExitPlanMode (merge-only).
- `--memory BRAIN:MODE` присоединяет проект к мозгу: `.swissknife.json:memory_brain` + `.claude/memory.env.ini`.

Разбери намерение из «$ARGUMENTS»; для bypass-режима предупреди, что он снимает подтверждения (только для контейнеров/VM).
