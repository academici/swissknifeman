# sequential-thinking MCP

## Что это

Официальный (Anthropic / Model Context Protocol) сервер: инструмент для **пошагового
структурированного рассуждения** — агент разбивает сложную задачу на явные шаги с
возможностью ревизий и ветвлений.

- Репозиторий: `modelcontextprotocol/servers` (`src/sequentialthinking`)
- npm: `@modelcontextprotocol/server-sequential-thinking`

## Установка

Пресетом (opt-in):

```bash
swissknifeman integrate --mcp sequential-thinking
```

Пресет — `configs/claude-code/mcp/sequential-thinking.json`:

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
}
```

## Когда полезен

Многошаговые задачи с неочевидной декомпозицией: сложный рефакторинг, разбор зависимостей,
архитектурные развилки. Современные модели Claude умеют extended thinking и так — сервер
даёт явный, наблюдаемый протокол шагов, который удобно ревизовать.
