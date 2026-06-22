# filesystem MCP

## Что это

Официальный (Anthropic / Model Context Protocol) сервер доступа к файловой системе — даёт
агенту чтение и запись в **явно разрешённых** каталогах.

- Репозиторий: `modelcontextprotocol/servers` (`src/filesystem`)
- npm: `@modelcontextprotocol/server-filesystem`

## Установка

Пресетом (opt-in):

```bash
skiller integrate --mcp filesystem
```

Пресет — `configs/claude-code/mcp/filesystem.json` (по умолчанию — корень проекта):

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
}
```

Разрешённые каталоги задаются аргументами — добавь нужные пути:

```json
"args": ["-y", "@modelcontextprotocol/server-filesystem", "./src", "./docs"]
```

## Ограничения

- Доступ строго в перечисленных каталогах — это граница безопасности; не расширяй её на
  секреты (`.env`, ключи, `~/.ssh`).
- В Claude Code уже есть нативные Read/Write/Edit; сервер полезен, когда нужен отдельный
  изолированный скоуп ФС для агента/субагента или другого MCP-клиента.
