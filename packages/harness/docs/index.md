# CLI harness — окружение Claude Code

`harness` — пакет настройки **окружения Claude Code**: пресеты permissions,
режимы auto-approve/bypass, MCP-серверы и хуки (memory/notify/log). Раньше этот
функционал жил внутри `skiller`; вынесен в отдельный пакет, потому что к
управлению скиллами он не относится. Источник истины пресетов —
`packages/harness/configs/claude-code/`.

Устанавливается симлинком в `~/.local/bin` (зонтичный `./install.sh` ставит
`skiller` · `harness` · `maind`). Пакет stateless — пишет в `.claude/` целевых
проектов и `~/.claude/hooks/`.

## Команды

### `harness permissions`

Вливает пресеты permissions в `.claude/settings*.json` (merge-only, бэкап `*.bak`).
Без `--preset` стек определяется автоматически (base + laravel/php-package/node/
python/docker). Подробности и список пресетов — [Permissions](./configs/claude-permissions).

```
harness permissions --target .                    # autodetect стека
harness permissions --target . --preset base,laravel,docker
harness permissions --target . --dry-run
harness permissions --list                        # доступные пресеты
harness permissions --global                      # baseline + файлы хуков в ~/.claude
```

### `harness mcp`

Добавляет MCP-серверы в `.mcp.json` из пресетов (merge-only, чужие серверы целы).
Каталог пресетов и описания — [Интеграции](./integrations/).

```
harness mcp --list
harness mcp --target . --mcp context7,playwright
harness mcp --target . --mcp context7 --dry-run
```

### `harness hooks`

Глобальная установка файлов хуков (раз на машину) и включение режимов по проекту.

```
harness hooks --global                            # auto-approve/memory/notify/log/review-gate → ~/.claude/hooks
harness hooks --target . --auto-approve strict    # strict|permissive|bypass|off
harness hooks --target . --memory core:federation # file|federation|agentmemory|off
```

- `--auto-approve` пишет `.claude/auto-approve.env.ini` и регистрирует PreToolUse-хук
  (Bash/ExitPlanMode), merge-only.
- `--memory BRAIN:MODE` присоединяет проект к мозгу: `.swissknife.json:memory_brain`
  + `.claude/memory.env.ini`.
- **review-gate** (`SubagentStop`) — детерминированный гейт архитектуры: прогоняет
  проверку проекта после субагента, `warn` → подсказка, `strict` → блок. Режим в
  `.claude/review-gate.env.ini` (`off|warn|strict`, дефолт `warn`), проверка в
  `.claude/review-gate.config.json` (`check_command`; пусто → no-op). Подробно —
  `hooks/review-gate/README.md`.

::: warning bypass снимает подтверждения
Режим `bypass` авто-одобряет всё, кроме жёсткого denylist — только для
контейнеров/VM, не на рабочей машине.
:::

### `harness agent-packs`

Раскатывает версионируемые паки субагентов/правил под стек (`backend-laravel`,
`node-frontend`, `python-backend`, `dart-flutter`) или роль (`role-cto` и др.)
поверх скиллов. Подробности — [Agent-packs](./configs/agent-packs).

```
harness agent-packs list
harness agent-packs render  --auto --pack <pack> --target .
harness agent-packs upgrade        --pack <pack> --target .
harness agent-packs doctor  --target . [--drift [--strict]]
```

- Каждый сгенерированный файл получает **provenance-header**
  (`swissknifeman:generated`) — пак/версия/edit-policy/точки расширения;
  правится не generated-core, а override-файл (`.claude/rules/<prefix>-reviewer-overrides.md`).
- `doctor --drift` (и `--strict` для CI) ловит generated-файлы, правленные
  локально мимо override; тот же сигнал попадает в `pack_drift` вердикта
  `maind analyze` (ATTENTION, не RED).

### `harness doctor`

Диагностика: наличие пресетов и `apply-permissions.sh`, установлены ли файлы
хуков в `~/.claude/hooks/`.

## Связь со skiller и maind

- `skiller connect`/`vendor`/`integrate` зовут `harness permissions` под капотом
  (`--no-permissions` отключает) — отдельно ставить не нужно.
- Память делит state со `skiller` (`~/.swissknifeman/`): установленные хуки
  `~/.claude/hooks/memory/` читают `topology.json`/`projects.json` оттуда.
- Плагин `harness@swissknifeman` даёт slash-команды `/harness:*`.
