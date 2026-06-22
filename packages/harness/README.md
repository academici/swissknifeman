# harness

**Настройка окружения Claude Code** для проектов экосистемы academici: пресеты
permissions, режимы auto-approve/bypass, MCP-серверы и хуки (memory/notify/log).
Один из пакетов зонтика [`swissknifeman`](../../README.md) (рядом — `skiller`
для скиллов и `maind` для памяти/графа).

Раньше этот функционал жил внутри `skiller`; вынесен в отдельный пакет, потому что
к управлению скиллами он не относится — это про харнес Claude Code.

## Установка

```bash
./install.sh                 # симлинк harness в ~/.local/bin (пакет stateless)
# или из корня монорепо: ./install.sh  (ставит skiller · maind · harness)
```

## Использование

```bash
# permissions: автодетект стека (base + laravel/php/node/python/docker)
harness permissions --target .                 # или --preset base,laravel
harness permissions --list                     # доступные пресеты
harness permissions --target . --dry-run

# MCP-серверы → .mcp.json (merge-only)
harness mcp --list
harness mcp --target . --mcp context7,playwright

# хуки
harness hooks --global                         # файлы хуков в ~/.claude/hooks (раз на машину)
harness hooks --target . --auto-approve strict # включить авто-апрув по проекту
harness hooks --target . --memory core:federation

harness doctor                                 # диагностика
```

Запись в проекты — **merge-only**: существующие правила/серверы сохраняются, файл
бэкапится в `*.bak`.

## Пресеты

Источник истины — `configs/claude-code/`:

| Что | Где |
|:--|:--|
| permissions по стекам | `settings.{base,laravel,php-package,node,python,docker}.json` |
| глобальный baseline / bypass / строгий | `settings.{global,yolo,product-boundary}.json` |
| MCP-серверы | `mcp/{context7,playwright,filesystem,fetch,memory,github,sequential-thinking}.json` |
| хуки | `hooks/{auto-approve,memory,notify}/`, `hooks/log-bash-command.sh` |

Подробности по auto-approve и единой памяти — `configs/claude-code/README.md`.

## Разработка

```bash
bash scripts/validate.sh     # py_compile + bash -n + JSON + frontmatter + тесты
bash scripts/test.sh         # unittest
```

Гид для агентов — [CLAUDE.md](CLAUDE.md).
