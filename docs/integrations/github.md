# GitHub MCP

## Что это

Официальный GitHub MCP-сервер: управление Issues, Pull Requests, репозиториями и Actions
прямо из агента, без переключения на `gh`.

- Репозиторий: <https://github.com/github/github-mcp-server>
- Варианты: **remote** (хостит GitHub, `https://api.githubcopilot.com/mcp/`) или локальный
  Docker (`ghcr.io/github/github-mcp-server`)

## Установка

Пресетом (opt-in) — поставляется remote-вариант (без Docker и токенов в файле):

```bash
skiller integrate --mcp github
```

Пресет — `configs/claude-code/mcp/github.json`:

```json
{
  "type": "http",
  "url": "https://api.githubcopilot.com/mcp/"
}
```

Аутентификация — OAuth при первом обращении (или Bearer-PAT через заголовок
`Authorization`). Локальный вариант — Docker с `GITHUB_PERSONAL_ACCESS_TOKEN`.

## Ограничения и альтернатива

- Remote-сервер требует доступа к GitHub и аккаунта с нужными правами.
- В проектах academici git-процесс уже закрыт скиллами `oss-dev/github-flow` +
  `oss-dev/gh-review` поверх `gh` CLI. GitHub MCP полезен, когда нужно дать агенту прямые
  инструменты GitHub без shell — взвесь против привычного `gh`.
