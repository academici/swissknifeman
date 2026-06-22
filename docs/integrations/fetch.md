# fetch MCP

## Что это

Официальный (Anthropic / Model Context Protocol) сервер: тянет URL и отдаёт содержимое как
markdown. Полезен, чтобы агент сам читал внешнюю документацию или страницы.

- Репозиторий: `modelcontextprotocol/servers` (`src/fetch`)
- Пакет: `mcp-server-fetch` (**Python**, PyPI) — запускается через `uvx`

::: warning Рантайм — Python/uv
В отличие от остальных серверов набора, это **не npm**-пакет. Нужен
[uv](https://github.com/astral-sh/uv) (`uvx`). Если uv не установлен — поставь его или
используй [Context7](./context7) для документации библиотек.
:::

## Установка

Пресетом (opt-in):

```bash
skiller integrate --mcp fetch
```

Пресет — `configs/claude-code/mcp/fetch.json`:

```json
{
  "command": "uvx",
  "args": ["mcp-server-fetch"]
}
```

## Ограничения

- robots.txt уважается по умолчанию; для отдельных сайтов нужен флаг `--ignore-robots-txt`.
- Большие страницы отдаются кусками (есть параметры длины и старта).
- В Claude Code есть нативный WebFetch — сервер нужен, когда fetch требуется как
  MCP-инструмент (для субагентов, воркфлоу или другого клиента).
