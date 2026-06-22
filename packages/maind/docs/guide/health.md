# Healthcheck — связь проекта с хабом

Если в проекте не подняты память + maind MCP, разработка идёт «мимо» графа/памяти → пробелы.
`maind health` это диагностирует. Проверка **не блокирует** работу — всегда печатает статус и
подсказки.

## Диагностика

```bash
maind health --cwd                 # из каталога проекта (матч по local_path)
maind health --project flexcrm     # по id
maind health --project flexcrm --json
maind health --cwd --fix           # поднять память + дописать MCP-серверы
maind health --project flexcrm --strict   # exit 1, если не connected (для CI)
```

Проверяются три оси: демон памяти отвечает? agentmemory MCP в проекте? maind MCP в проекте?

| Статус | Смысл |
|:--|:--|
| `connected` | память доступна И оба MCP-сервера настроены |
| `partial` | что-то одно есть (например, MCP без демона) |
| `standalone` | ни демона, ни MCP — проект работает автономно |

Пример вывода:

```
⚠ mAInd health — project:flexcrm (scope project:flexcrm)
  [ok  ] демон памяти (http://127.0.0.1:4111)
  [FAIL] agentmemory MCP в проекте
  [ok  ] maind MCP в проекте
  статус: partial
    → нет agentmemory MCP в проекте → maind sync --only mcp --project flexcrm
```

`--fix` поднимает память (если лежит) и выполняет `sync --only mcp` для проекта, затем повторяет отчёт.

## Доставка «приоритета №1» в проекты

Чтобы проект сам напоминал про связь с хабом, два провиженера (вызываются из `maind sync`,
источник истины — `templates/health/*`):

- **health-doc** — управляемый блок (маркер `maind:healthcheck`) в `<project>/CLAUDE.md`;
  идемпотентно по content-hash, чужой текст файла сохраняется.
- **health-hook** — SessionStart-хук в `<project>/.claude/settings.json` (+ скрипт
  `.claude/maind-health.sh`); **не блокирует** сессию, выходит чисто даже если `maind` недоступен.

```bash
maind sync --project flexcrm --only health-doc,health-hook
maind sync --all --only health-doc,health-hook --mode update   # обновить устаревшие блоки
```

## Траблшутинг

- `демон памяти не запущен` → `maind start --only memory`.
- `нет … MCP в проекте` → `maind sync --only mcp --project <id>` (или `maind health --fix`).
- `missing-path` → у проекта нет `local_path` или путь не существует — поправьте `config.json`.

Дальше: [Sync →](./sync)
