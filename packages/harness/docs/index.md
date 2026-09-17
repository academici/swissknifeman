# CLI harness — окружение агентов

`harness` — пакет настройки **окружения Claude Code, Codex и Cursor**: пресеты permissions,
режимы auto-approve/bypass, MCP-серверы и хуки (memory/notify/log). Раньше этот
функционал жил внутри `skiller`; вынесен в отдельный пакет, потому что к
управлению скиллами он не относится. Источник истины пресетов Claude —
`packages/harness/configs/claude-code/`; Cursor shapes —
`packages/harness/configs/cursor/`.

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

Добавляет MCP-серверы в `.mcp.json` (Claude Code) из пресетов (merge-only, чужие серверы целы).
Для **Cursor** MCP в `.cursor/mcp.json` пишет `maind sync` при включённом провайдере.
Каталог пресетов и описания — [Интеграции](./integrations/).

```
harness mcp --list
harness mcp --target . --mcp context7,playwright
harness mcp --target . --mcp context7 --dry-run
```

Cursor MCP и permissions — [Настройка Cursor](./setup/cursor).

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

### `harness safe-dirs`

Machine-owned allowlist доверенных директорий: внутри его корней auto-approve
пропускает `rm`/`rmdir` мимо deny_hard (код под git — удаление обратимо), вне —
блокирует как раньше. Конфиг живёт **в корне монорепо swissknifeman** —
`safe-dirs.json` (gitignored, шаблон `safe-dirs.example.json` — тот же паттерн,
что `config.json` узла maind); лестница поиска хуком: `$SKM_SAFE_DIRS_CONFIG`
(эксклюзивный override) → корень монорепо (через realpath лаунчера из PATH) →
legacy `~/.swissknifeman/safe-dirs.json` (`init` мигрирует его в репо
автоматически). Вердикт считает `hooks/auto-approve/lib/safedirs.py` строго
fail-closed: argv через shlex, realpath против symlink-escape/`..`, containment
по компонентам, защита `.git` и самого корня, глобы по статическому префиксу;
любая shell-магия (`$VAR`, `$( )`, backticks, `xargs rm`) → deny.
Project-override конфига хука на allowlist **не влияет** (безопасность).

```
harness safe-dirs init                                  # конфиг с дефолтами
harness safe-dirs list                                  # эффективный allowlist глазами хука
harness safe-dirs add ~/projects                        # добавить корень (--exclude — изъятие)
harness safe-dirs prune-ask --global --all-projects     # снять старые ask-правила rm
```

Дефолт `include_registered_projects=true` — онбордженные проекты из
`~/.swissknifeman/projects.json` попадают в allowlist автоматически.

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

### `harness instructions`

Управляет двенадцатью проекциями корневых/пакетных инструкций (`CLAUDE.md`/`AGENTS.md`
в корне и по одному на пакет) из общего канона `configs/common/instructions/**` —
механизм, три наблюдения (`stale-source`/`managed-drift`/`ownership-conflict`) и
два машинных гейта подробно разобраны в [канон корневых инструкций](./reference/instruction-canon).

```
harness instructions plan                         # no-write снимок
harness instructions check                        # + гейт покрытия литералов
python3 -m harness.instructions --check            # модульная точка (тот же вердикт)
harness instructions apply --authorize CLAUDE.md,packages/harness/AGENTS.md
harness instructions repair --authorize <цели> --observed-hash <target=hash,...> \
  --preimage-dir adjacent-backup
harness instructions adopt --authorize <цель> --owner-decision D# \
  --mapping mapping.json --preimage-dir preimages/
```

- `plan`/`check` — no-write; `apply`/`repair`/`adopt` пишут только после явной
  авторизации оператора (`--authorize`), список целей — АЛФАВИТНЫЙ по пути.
- `apply`/`repair` создают/чинят цели, уже находящиеся под управлением;
  `--preimage-dir` у `repair` — фиксированная строка `adjacent-backup`.
- `adopt` принимает под управление СУЩЕСТВУЮЩИЙ неуправляемый файл: требует
  `--owner-decision`, `--mapping` и `--preimage-dir` (каталог pre-image'ов) все три.
- Ручная правка управляемых блоков (между HTML-маркерами) запрещена навсегда —
  следующий `check`/`repair` увидит это как `managed-drift`.

### `harness doctor`

Диагностика: наличие пресетов и `apply-permissions.sh`, установлены ли файлы
хуков в `~/.claude/hooks/`. Provider audit:

```
harness doctor --settings --provider cursor --target .
harness doctor --provider-audit
```

## Связь со skiller и maind

- `skiller connect`/`vendor`/`integrate` зовут `harness permissions` под капотом
  (`--no-permissions` отключает) — отдельно ставить не нужно.
- Память делит state со `skiller` (`~/.swissknifeman/`): установленные хуки
  `~/.claude/hooks/memory/` читают `topology.json`/`projects.json` оттуда.
- Плагин `harness@swissknifeman` даёт slash-команды `/harness:*`.
