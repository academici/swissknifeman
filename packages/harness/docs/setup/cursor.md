# Настройка окружения Cursor

Как подключить проект к swissknifeman как **третьему managed-провайдеру**: permissions
(allowlist half), MCP хаба, autonomy и trusted self-host — без переписывания `AGENTS.md`.

## Проблема

У Cursor две независимые оси:

1. **Allowlist half** (project-scoped) — `.cursor/cli.json` + `.cursor/permissions.json`.
2. **Approval mode / Run Mode** (не project-scoped) — глобальный CLI config или UI IDE.

Harness публикует только (1). Autonomy в trusted-сессии требует launch flags **и** явной
установки Run Mode в IDE (freeze D2).

## Профили (semantic)

Источник: `packages/harness/configs/common/profile-catalog.json` +
`packages/harness/configs/cursor/config/profile-bindings.json`.

| Profile | Fleet | `.cursor/cli.json` | `.cursor/permissions.json` | Launch-only mode |
|:--|:--|:--|:--|:--|
| `observe` | да | read-biased allow | пустые allowlists + block_instructions | plan / allowlist |
| `workspace-contained` | **everyday default** | scoped workspace allow | scoped MCP/terminal | auto-review |
| `trusted-full-access` | **только self-host-apply** | broad allow + deny floor | `*:*` wildcards | unrestricted + Run Everything |

Shared **deny floor** (все три профиля, D4): секреты (`.env*`, `*.pem`, `*.key`) — отказ
даже под `--force`.

## Установка: everyday (fleet)

### 1. Включить провайдер в проекте

```json
// .swissknife.json
{
  "providers": {
    "selection": {
      "cursor": { "enabled": true }
    }
  }
}
```

### 2. Onboard + sync

```bash
cd ~/projects/my-app
maind onboard --cwd              # память, health hooks, MCP-каналы
maind sync --project <id>        # .cursor/mcp.json ← hub servers (merge-only)
maind health --cwd               # provider:cursor trust
```

Скиллы: `skiller sync` → `.agents/skills/` (Cursor discovery, без `.cursor/skills` writer).

### 3. Permissions (workspace-contained)

Managed shapes рендерятся harness profile engine в:

- `.cursor/cli.json` — `permissions.allow/deny` (CLI)
- `.cursor/permissions.json` — `mcpAllowlist`, `terminalAllowlist`, `autoRun`

Операторский аудит без записи:

```bash
harness doctor --settings --provider cursor --target .
```

::: warning Merge-only widening
Per-user и per-repo массивы **конкатенируются** (E14.2). Repo-файл не сужает broad
user-level allowlist — только расширяет. Observe/workspace-contained не гарантируют
сужение, если на машине уже широкий user profile.
:::

## Trusted self-host (только umbrella)

`trusted-full-access` для `repo:swissknifeman` — явная операция, не fleet default:

- `origin=operation`
- `operation_id=self-host-apply`
- `target_identity=repo:swissknifeman`

Любой другой target → `HARNESS_CURSOR_TRUSTED_NON_SELF_HOST_REFUSED`.

Артефакты (когда применены): broad allowlists, `.cursor/rules/swissknifeman-{core,launch,packages}.mdc`.

### Launch (CLI)

```bash
cd /path/to/swissknifeman
agent --workspace "$(pwd)" \
      --model composer-2.5 \
      --force --sandbox disabled --trust --approve-mcps \
      'task:plan-exec <PLAN-ID> <Pn.m>'
```

### IDE checklist (обязательно для trusted)

1. Workspace = корень репозитория (не подпапка без намерения).
2. **Run Mode → Run Everything** (Settings; не коммитится в репо).
3. `maind health --cwd` — connected, `provider:cursor trust` green.
4. Модель = pin из Routing (не `auto` для fixed frontier/implementation).
5. `.cursor/cli.json` deny floor на месте — отказ по секретам не transient error.

## MCP

| Команда | Куда пишет | Когда |
|:--|:--|:--|
| `maind sync` / `maind deploy` | `.cursor/mcp.json` | `providers.selection.cursor.enabled` |
| `harness mcp --target .` | `.mcp.json` | только Claude Code (legacy) |

Пресеты каталога: `packages/harness/configs/cursor/mcp/bindings.json` → secret refs only.

## Hooks

First ship: `security.safe-dirs` (`beforeShellExecution`, `failClosed: true`) в
`.cursor/hooks/`. Остальные lifecycle hooks — deferred (honest `unsupported` в matrix).

## Связь с skiller и maind

- `skiller integrate` / `maind onboard` — cross-package onboarding один раз.
- `skiller sync` — managed skills в `.agents/skills`.
- `maind sync` — MCP + memory hooks; cursor channel при enabled provider.
- Budget listing: `skiller budget --provider cursor`.

## См. также

- [Адаптер Cursor](/skiller/adapters/cursor) — полный цикл интеграции
- [Provider model roles](/task/reference/provider-model-roles) — pins и inventory
- [Permissions Claude Code](./claude) — sibling-провайдер (другие surfaces)
