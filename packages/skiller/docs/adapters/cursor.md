# Адаптер: Cursor

Полный цикл интеграции с Cursor как **третьим managed-провайдером** (Codex-sibling):
скиллы через `.agents/skills`, окружение через `.cursor/*`, без dual-write в
`.cursor/skills` и без переписывания Codex-owned `AGENTS.md`.

## Проекция и discovery

| Surface | Канал | Примечание |
|:--|:--|:--|
| Скиллы | `.agents/skills/` | Cursor читает нативно (D8); skiller **не** пишет `.cursor/skills` |
| Инструкции (extension) | `.cursor/rules/swissknifeman-*.mdc` | только self-host umbrella; trigger-scoped (D11) |
| MCP | `.cursor/mcp.json` | merge-only; пишет `maind sync` при включённом провайдере |
| CLI permissions | `.cursor/cli.json` | только `permissions`; `deny` переживает `--force` |
| IDE allowlists | `.cursor/permissions.json` | merge-only; repo только **расширяет** user-level |

Общий контракт репозитория Cursor уже подхватывает из `AGENTS.md`; в `.mdc` — только
`root.cursor.*` extension и строка precedence для `root.codex.*`.

## Установка (проект)

### 1. Включить провайдер

В `.swissknife.json` проекта:

```json
{
  "providers": {
    "selection": {
      "cursor": { "enabled": true }
    }
  }
}
```

Everyday fleet-путь — `workspace-contained`. `trusted-full-access` только для self-host
под гейтом `self-host-apply` / `repo:<name>` (см. [Harness setup: Cursor](/harness/setup/cursor)).

### 2. Скиллы (vendor/sync)

```bash
cd ~/projects/my-app

# Рекомендуемый путь: managed sync в .agents/skills (Cursor читает нативно)
skiller sync

# Legacy-совместимость
skiller vendor --agent cursor   # deprecated: копирует в .cursor/skills — избегайте dual-write
```

`render_cursor_publication` — ownership assertion: один writer на дерево скиллов, без
параллельной записи в `.agents` и `.cursor`.

### 3. MCP и память (onboard/sync)

```bash
maind onboard --cwd ~/projects/my-app    # первое подключение: память + MCP + health
maind sync --project my-app              # докатка MCP в .cursor/mcp.json
maind health --cwd                       # round-trip + provider:cursor trust
```

Hub-серверы (`plugin-core-maind`, `plugin-core-serena`) попадают в `.cursor/mcp.json`
через provider deploy, не через legacy `harness mcp` (тот пишет только `.mcp.json` Claude).

### 4. Permissions (everyday и trusted)

Everyday (`workspace-contained`) — scoped allowlists в `.cursor/permissions.json` и
`.cursor/cli.json` без Run Everything на флот.

Trusted self-host (`trusted-full-access`) — широкие allowlists **только** при явном
`operation_id=self-host-apply` и `target_identity=repo:swissknifeman`. Наследование
флотом запрещено (`HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN`).

Операторский контракт (shapes и аудит):

```bash
harness doctor --settings --provider cursor --target .
```

Публикация managed shapes на проект — через onboard/sync с включённым `cursor` в
`.swissknife.json`; подробности — [Harness setup: Cursor](/harness/setup/cursor).

## Autonomy: две дорожки

| Дорожка | Файлы | Launch / Run Mode |
|:--|:--|:--|
| Everyday onboard | `workspace-contained` shapes | Auto-review / allowlist; без `--force` на флот |
| Self-host trusted | `trusted-full-access` shapes | CLI: `--force --sandbox disabled --trust --approve-mcps`; IDE: **Run Everything** |

**Критично:** `approvalMode` и sandbox **не** project-scoped (E14.1). Режим — только
launch flags + UI Run Mode; harness пишет allowlist/deny half. `deny` в `.cursor/cli.json`
— единственный project-scoped floor под `--force`.

Семантика launch: instruction `root.cursor.launch-and-autonomy` (agent-requested rule
`swissknifeman-launch.mdc` на self-host).

## Launch-block (cold-start)

Таблица Model class / Effort / Context — provider-neutral (plan-protocol §8). Для Cursor
после таблицы — **Native Cursor command**:

```bash
agent --workspace <repo-cwd> \
      --model <model-selector> \
      --force --sandbox disabled --trust --approve-mcps \
      'task:<command> <arguments>'
```

- `--workspace`, не `-C` (freeze E3).
- Пин модели: `composer-2.5-fast` / `composer-2.5` / `claude-opus-5-thinking-high` — см.
  [Provider model roles](/task/reference/provider-model-roles).
- `auto` **не** заменяет fixed frontier/implementation pin.

IDE checklist (trusted): workspace root → Run Everything → MCP health → pinned model.

## Модели и Auto

Hand-verified inventory в `packages/task/configs/command-routing.json` →
`mappings.cursor.model_inventory`. Полный гайд (pins + inventory + Auto policy):
[Provider model roles](/task/reference/provider-model-roles).

## Delta-файлы скиллов

Специфика Cursor — в `adapters/cursor.md` внутри скилла (overrides для `.cursor/rules`).
Основной `SKILL.md` остаётся provider-neutral. Формат — в
[спецификации адаптерных дельт](../guide/adapter-deltas).

## Диагностика

```bash
skiller budget --provider cursor --target .
maind health --cwd
harness doctor --settings --provider cursor --target .
python3 packages/task/scripts/render-provider-commands.py --check --root .
```

## См. также

- [Harness setup: Cursor](/harness/setup/cursor) — permissions, MCP, профили
- [Provider model roles](/task/reference/provider-model-roles) — design/exec/audit/economy
- [Plan tooling: launch-block](/task/reference/plan-tooling) — handoff-форма
- Freeze: `.cursor/plans/2026.09.17-cursor-third-provider-design-freeze.md`
