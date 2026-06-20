# Task Master AI

::: tip Только справка (docs-only)
Пресет для `integrate` не поставляется: Task Master требует ключей провайдера и создаёт
рабочие файлы в проекте. Подключай вручную и по необходимости.
:::

## Что это

Task Master (eyaltoledano) — AI-менеджер задач: парсит PRD (описание проекта/спринта) и
генерирует структурированный backlog с зависимостями и приоритетами. Работает как CLI и как
MCP-сервер.

- Репозиторий: <https://github.com/eyaltoledano/claude-task-master>
- npm: `task-master-ai`

## Установка

CLI:

```bash
npm install -g task-master-ai
task-master init
```

MCP (по требованию) — в `.mcp.json` проекта:

```json
{
  "mcpServers": {
    "task-master-ai": {
      "command": "npx",
      "args": ["-y", "--package=task-master-ai", "task-master-ai"],
      "env": { "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}" }
    }
  }
}
```

::: warning Нужен ключ и токен-бюджет
Требуется минимум один ключ провайдера (или OAuth Claude Code / Codex CLI). MCP-сервер
грузит ~36 инструментов (~21k токенов) — через `TASK_MASTER_TOOLS` (`core` / `standard` /
`all` или список) можно сузить.
:::

## Рабочий процесс

```bash
task-master parse-prd <prd>          # PRD → задачи
task-master list                     # список
task-master next                     # следующая задача
task-master set-status --id=<id> --status=done
```

Модели настраиваются тремя ролями (main / research / fallback) — указывай актуальные модели
Claude (например, Sonnet 4.6 для разбора, Haiku 4.5 для дешёвых операций).

## Нюансы

- Создаёт рабочие файлы (`.taskmaster/`) — реши, коммитить или в `.gitignore`.
- Хорошо стыкуется со spec-driven подходом: спецификация → PRD → задачи (см.
  [Spec Kit](./spec-kit)).
- Избыточен для мелких задач; в проектах academici базовый трекинг уже закрыт
  `general/task-brief-template` + GitHub Issues (`oss-dev/github-flow`).
