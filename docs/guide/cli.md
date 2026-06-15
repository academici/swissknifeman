# CLI

Лаунчер `bin/maind` — тонкий bash-обёртка: проверяет окружение и вызывает
`python3 -m maind <repo_root> <cmd> [args]`. Корень узла — каталог установки maind.

## Команды

```bash
maind start [--only memory|graph]      # поднять воркеры узла
maind status [--json]                  # сводка: память, граф, агенты, проекты

maind memory start                     # запустить демон памяти (Node)
maind memory stop                      # остановить (только свой, чужой не трогает)
maind memory status [--json]

maind graph query --from project:brain --depth 2 [--edge-types depends_on,uses] [--json]
maind graph neighbors --node project:maind --direction in
maind graph stats [--json]

maind agents register <id> [--project P --pid N --kind K]
maind agents heartbeat <id>
maind agents list [--all --json]
maind agents kill <id> [--force]

maind projects list [--json]
maind projects sync --from brain [--path DIR]

maind deploy [--project ID | --all] [--with-graphify] [--dry-run]   # MCP-серверы хаба на проекты
maind workspace sync [--dry-run] [--no-allow] [--no-mode]           # доверие Claude к проектам экосистемы
maind workspace status [--json]
maind run <project> <capability> [-- args]   # дёрнуть команду brain / swissknifeman
maind onboard <project> [--with-graphify] [--with-brain]            # единый онбординг

maind migrate from-brain <.projects.json> [--force]
maind migrate from-agentmemory <dir> [--force]

maind mcp                              # запустить как MCP-сервер (stdio)
maind doctor [--quiet]                 # диагностика окружения
maind version                          # git SHA + путь к узлу
```

## Как это устроено

- Разбор аргументов — `common.parse_args` (флаги `--x` + позиционные), не argparse.
- Каждая команда — функция `cmd_X(env, argv)` из словаря `COMMANDS` в `cli.py`.
- Контекст запуска — frozen-dataclass `Env` (корень узла, команда, HOME) — передаётся
  явно, без модульных глобалей. Поэтому всё легко тестируется.

Дальше: [Память →](/guide/memory)
