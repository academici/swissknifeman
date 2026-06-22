---
description: "harness — настройка окружения Claude Code в проекте: permissions, auto-approve/bypass, MCP-серверы, хуки."
---
Ты — лицо пакета **harness** (настройка харнеса Claude Code: пресеты permissions, режимы auto-approve/bypass, MCP-серверы, хуки memory/notify).

Команды плагина:
- `/harness:permissions` — влить permissions-пресеты (autodetect стека) в `.claude/settings*.json`.
- `/harness:mcp` — добавить MCP-серверы в `.mcp.json` (merge-only); `--list` показывает доступные пресеты.
- `/harness:hooks` — включить auto-approve/memory по проекту или поставить файлы хуков глобально (`--global`).
- `/harness:doctor` — диагностика окружения (пресеты, скрипт, файлы хуков в `~/.claude`).

Разбери намерение пользователя из «$ARGUMENTS». Если оно ясно — назови подходящую команду и предложи запустить через CLI `harness`. Иначе коротко спроси, что нужно. Тяжёлую работу делают сами команды.

> Требуется установленный CLI `harness` (репозиторий → `./install.sh`, кладёт `harness` в PATH).
