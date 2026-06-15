# Граф кода (код-MCP в проекте)

Граф **кода внутри проекта** (символы, файлы, ссылки, реализации) — отдельный, **универсальный**
слой: per-project MCP-сервер. По умолчанию это **[Serena](https://github.com/oraios/serena)** —
language-agnostic (через LSP, работает для PHP/TS/Python/Go/Rust/… одинаково), запускается через
`uvx`, без установки в каждый проект. Это даёт агенту точную навигацию по коду (найти определение,
все вызовы, реализации интерфейса, обзор символов файла) — и экономит токены против чтения файлов
целиком.

::: tip Историческое имя
В коде/конфиге слой исторически называется `graphify` (по черновику спецификации). Готового
инструмента с таким именем нет; **движок по умолчанию — Serena**. Имя поля сохранено для
совместимости; движок переопределяется (см. ниже).
:::

Три слоя экосистемы — разные задачи:

| Механизм | Что связывает | Как доставляется |
|:--|:--|:--|
| **agent-memory** | память/контекст (факты, решения) | демон на хабе + MCP-клиент в проекте |
| **maind-граф** | топология **между** проектами (зависимости) | федерация на хабе ([Федерация](/guide/federation)) |
| **код-MCP (Serena)** | **код внутри** проекта (символы/ссылки/реализации) | MCP-сервер в проекте (uvx Serena) |

## Включение (config-driven)

Поле проекта `graphify: true` в `.maind.json` — и `maind sync`/`onboard` раскатают код-MCP:

```json
{ "id": "flexcrm", "graphify": true }
```

```bash
maind sync --project flexcrm --only mcp     # допишет код-MCP в .mcp.json (если команда есть в PATH)
maind onboard flexcrm --with-graphify       # онбординг сразу с код-графом (флаг сохранится в конфиг)
```

Запись в `.mcp.json` проекта (дефолт — Serena):

```json
{ "mcpServers": {
    "serena": { "command": "uvx", "args": [
      "--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server",
      "--context", "ide-assistant", "--project", "/path/to/flexcrm",
      "--enable-web-dashboard", "false" ] } } }
```

Требуется `uvx` (из [uv](https://docs.astral.sh/uv/)) в PATH. Нет команды → корректный пропуск
(`skipped-not-installed`), остальные серверы пишутся, sync не падает.

## Переопределение движка (любой code-intelligence MCP)

Движок задаётся на проект — например, стек-специфичный сервер вместо Serena:

```json
{ "id": "flexcrm", "graphify": true,
  "graphify_server_name": "laravel-boost",
  "graphify_command": "php",
  "graphify_args": ["artisan", "boost:mcp"] }
```

Поля: `graphify_command` (бинарь, проверяется в PATH), `graphify_args` (аргументы; плейсхолдер
`{root}` → путь проекта), `graphify_server_name` (имя сервера в `.mcp.json`). Дефолты — в
`constants.CODE_MCP_*`.

## Когда использовать

- **agent-memory** — «о чём помнить»: решения, договорённости, контекст изменений.
- **код-MCP (Serena)** — «как устроен код»: навигация по символам/ссылкам/реализациям в репозитории.
- **maind-граф** — «кто от кого зависит»: топология пакетов/доков между проектами.

Дальше: [CLI →](/guide/cli)
