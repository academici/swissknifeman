# Context7 MCP

## Что это

Context7 от Upstash — MCP-сервер, который на лету подтягивает **актуальную документацию
библиотек** прямо в контекст Claude Code. Решает дрейф версий: обучающие данные модели
имеют cutoff-дату, а Flutter/Dart, Laravel, Node и прочие экосистемы обновляются
постоянно. С Context7 агент получает живые docs с привязкой к версии.

- Репозиторий: <https://github.com/upstash/context7>
- Транспорт: remote HTTP, эндпоинт `https://mcp.context7.com/mcp` (без локальной установки)

## Установка

`context7` — **dev-дефолт**: ставится в любую среду разработки (всё, кроме obsidian-vault)
без флага:

```bash
skiller integrate
```

Пресет — `configs/claude-code/mcp/context7.json`:

```json
{
  "type": "http",
  "url": "https://mcp.context7.com/mcp"
}
```

::: tip API-ключ опционален
Без ключа сервер работает с rate-limit. Для более высоких лимитов получи ключ на
`context7.com/dashboard` и добавь заголовок:

```json
{
  "type": "http",
  "url": "https://mcp.context7.com/mcp",
  "headers": { "CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}" }
}
```
:::

## Использование

Активация — строка **`use context7`** в конце запроса:

```
Как реализовать chunked-обработку Eloquent в актуальном Laravel? use context7
```

Сервер экспортирует два инструмента, которые агент вызывает сам:

| Tool | Назначение |
|---|---|
| `resolve-library-id` | поиск библиотеки по имени → context7-совместимый ID |
| `get-library-docs` | документация по ID + topic |

## Ограничения

- Узкоспециализированные/закрытые библиотеки могут быть не проиндексированы — для них
  пригодится [fetch](./fetch) или прямое чтение исходников.
- Кэш на стороне Upstash: только что вышедший патч может приехать с задержкой.
- Зависимость от внешнего сервиса (uptime Upstash).
