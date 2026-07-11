---
description: "Диагностика окружения harness: пресеты permissions/MCP, скрипт, файлы хуков; аудит настроек Claude Code (--settings)."
---
Запусти диагностику окружения харнеса и кратко поясни результат.

```
harness doctor
```
Проверяет: наличие `configs/claude-code/` (пресеты settings/MCP), `scripts/apply-permissions.sh`, и установлены ли файлы хуков глобально в `~/.claude/hooks/` (`notify`/`auto-approve`/`memory`). Если хуков нет — предложи `harness hooks --global`.

## Аудит настроек Claude Code (`--settings`)

```
harness doctor --settings [--target P] [--json] [--profile NAME]
```
Отдельная ветка (settings-doctor): читает все слои настроек Claude Code целевого проекта (`user → project → local → managed`), строит эффективную конфигурацию с провенансом и репортит конфликты по таксономии проверок. Не пишет на диск (read-only).

- `--target P` — проект для аудита (по умолчанию текущий каталог);
- `--profile NAME` — сверять с явным policy-профилем, перекрывая декларацию `.swissknife.json:policy_profile`;
- `--json` — единственный вывод в stdout: машинный документ (`{"target","profile","counts","findings","exit"}`) для CI/fleet-скана;
- **exit-code**: `0` — чисто (нет находок либо только заметки), `1` — есть предупреждения, `2` — есть ошибки. `--json` кода не меняет.

Фасад того же аудита из реестра скиллов — `skiller doctor --settings [--target P]` (делегирует сюда через subprocess).
