---
description: "Диагностика окружения harness: пресеты permissions/MCP, скрипт, файлы хуков в ~/.claude."
---
Запусти диагностику окружения харнеса и кратко поясни результат.

```
harness doctor
```
Проверяет: наличие `configs/claude-code/` (пресеты settings/MCP), `scripts/apply-permissions.sh`, и установлены ли файлы хуков глобально в `~/.claude/hooks/` (`notify`/`auto-approve`/`memory`). Если хуков нет — предложи `harness hooks --global`.
