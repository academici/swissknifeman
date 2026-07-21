---
name: harness-operations
description: "Операционная карта пакета harness (настройка окружения Codex): команды permissions/mcp/hooks/agent-packs/doctor, каталог пресетов (settings.* по стекам, mcp/<name>.json, режимы auto-approve), подсистема agent-packs (персона/стек-паки с шаблонизацией). Активировать при любой задаче, затрагивающей packages/harness/ — пресеты permissions, MCP-серверы, хуки (auto-approve/memory/notify/review-gate), agent-packs, или когда нужно решить «какой пресет/MCP/режим подключить проекту»."
---

# Операции harness (окружение Codex)

Внутренний скилл (не экспортируется). Только **факты** — карта возможностей пакета
`harness`. Карта skiller (раздача скиллов) — `package-architecture`; онбординг в хаб —
`ecosystem-integration`. harness настраивает ОКРУЖЕНИЕ Codex в проекте (permissions,
MCP, хуки, agent-packs); skiller делегирует сюда через subprocess.

## Когда активировать

- Задача трогает `packages/harness/` (lib, configs/Codex/, scripts, хуки).
- Нужно решить, какой **пресет permissions / MCP-сервер / режим auto-approve** подключить
  проекту под его стек.
- Вопрос «как harness раздаёт окружение», «что такое agent-packs», «почему промпт не
  авто-одобряется».

## CLI (источник истины — `configs/Codex/`)

```bash
harness permissions --target . [--preset a,b] [--file F] [--global] [--dry-run] [--list]
harness mcp         --target . --mcp context7,playwright [--list] [--dry-run]
harness hooks       --global                         # файлы хуков в ~/.Codex/hooks (раз на машину)
harness hooks       --target . --auto-approve strict --memory core:federation
harness agent-packs <list|render|upgrade|doctor> [--pack P] [--target DIR]
                    [--auto] [--answer K=V] [--install-only] [--allow-shell off|safe|full] [--dry-run]
harness doctor
```

Запись в проекты — **merge-only**, существующее не затирается, бэкап `*.bak`. Все writer'ы
атомарны (tmp+`mv`/`os.replace`).

## Каталог пресетов (`configs/Codex/`)

| Что | Файлы | Назначение |
|:--|:--|:--|
| **settings (permissions)** | `settings.{base,laravel,php-package,node,python,docker,global,yolo,product-boundary,agent-teams,observer}.json` | allow/ask/deny по стекам; вливаются merge-only в `.Codex/settings*.json` |
| **MCP-серверы** | `mcp/{context7,fetch,filesystem,github,memory,perplexity,playwright,sequential-thinking}.json` | голые объекты конфига → `.mcp.json` |
| **auto-approve** | `hooks/auto-approve/` (режимы `strict`/`permissive`/`bypass`/off) | PreToolUse-хук; порядок `deny_hard`→`deny_block`→`allow`; списки в `config.json` |
| **memory** | `hooks/memory/` (`file`/`federation`/`agentmemory`) | единая память; делит state со skiller (`~/.swissknifeman/`) |
| **notify / review-gate / log** | `hooks/{notify,review-gate}/`, `hooks/log-bash-command.sh` | ОС-уведомления; детерминированный гейт архитектуры на SubagentStop; лог Bash |

**Режимы auto-approve:** `strict` (allowlist-first, безопасный дефолт — read-only авто-allow,
мутации → промпт, катастрофа → deny) · `permissive` (denylist-first, только доверенный проект) ·
`bypass` (всё кроме `deny_hard` — только контейнер/VM) · `off`. ⚠️ Интерпретаторы (`python -c`,
`awk`/`sed`) НЕ авто-одобряются (тело в кавычках невидимо анализатору) — `trust_inline_interpreters`
выкл по умолчанию. ⚠️ `review-gate` исполняет `check_command` только из machine-owned config
(не из project-local — RCE), если не выставлен `ALLOW_PROJECT_CONFIG=1`.

**safe-dirs (rm в доверенных папках):** `rm`/`rmdir` с целями строго внутри allowlist-корней
проходят мимо `deny_hard` — allowlist MACHINE-OWNED `<монорепо>/safe-dirs.json` (в КОРНЕ репо,
gitignored, шаблон `safe-dirs.example.json` — паттерн maind config.json; лестница хука:
`$SKM_SAFE_DIRS_CONFIG` → корень монорепо через realpath PATH-лаунчера → legacy
`~/.swissknifeman/safe-dirs.json`, `init` мигрирует его в репо). Команды:
`harness safe-dirs init|list|add|remove|prune-ask`; дефолт включает онбордженные проекты из
`projects.json`. Вердикт — `hooks/auto-approve/lib/safedirs.py`, fail-closed (shlex-argv,
realpath, containment, защита `.git`/корня; глобы по статическому префиксу; `$VAR`/`$( )`/
`xargs rm` → deny). Project-override конфига хука на allowlist НЕ влияет. Ask-правила
`Bash(rm -r*)` из пресетов убраны (hook-allow не пробивает статический ask) — на старых
проектах снять `harness safe-dirs prune-ask --global --all-projects`.

## agent-packs (персона/стек-паки)

`configs/Codex/agent-packs/` — параметризованные наборы агентов+хуков+settings,
раскатываемые в проект под РОЛЬ или СТЕК (поверх скиллов skiller):

- **Стек-паки:** `backend-laravel`, `node-frontend`, `python-backend`, `dart-flutter` (детект по типу).
- **Роль-паки:** `role-cto`, `role-founder`, `role-maintainer`, `role-tech-lead` (выбираются явно,
  тянутся поверх любого стека) + `_common` (общая база).
- `pack.json`: `{pack, version, description, stack.shape, requires.{skills, harness_presets}, interview[]}`.
- Шаблонизация тел: блоки `<!-- pack:if KEY -->…<!-- pack:endif -->`; ответы из `interview[]`
  детерминированно (профиль/`--answer K=V`). `--allow-shell off|safe|full` — политика shell в хуках пака.
- Lock: `.Codex/agent-pack.lock.json` (идемпотентный render).
- Профиль проекта (`skiller profiles/*.json`) объявляет `agent_pack: [...]` — `integrate`/`onboard`
  раскатывают их через harness.

## Ключевые модули (`lib/harness/`)

`cli.py` (диспетчер) · `common.py` (`Env(BaseEnv)`, реэкспорт core) · `settings.py` (merge-only
writer'ы) · `permissions.py` (обвязка `scripts/apply-permissions.sh`) · `mcp.py` (`block_mcp`/
`available_mcp`) · `hooks.py` (`block_autoapprove`/`block_memory`/`install_global`) ·
`agentpacks.py` (рендер паков) · `doctor.py`.

## Кросс-зависимости

- **skiller делегирует сюда** через subprocess (`skiller connect`/`vendor`/`integrate` зовут
  `harness permissions|mcp|hooks`; резолв `SKM_HARNESS_BIN` → `<монорепо>/packages/harness/bin/harness`;
  нет harness → graceful skip).
- **Память делит state со skiller** (`~/.swissknifeman/topology.json`/`projects.json`); пути в
  установленных хуках НЕ менять (back-compat).
- `.swissknife.json:memory_brain` пишет harness (`hooks --memory`), валидирует skiller (`CONFIG_KEYS`).

## Чеклист (правки harness)

- [ ] stdlib-only в `lib/harness/`; `Env` явно (frozen); сообщения на русском.
- [ ] Запись в проект merge-only + `*.bak` + атомарно.
- [ ] Новый пресет/MCP/хук → в `configs/Codex/`; bash-хуки проходят `bash -n` (validate.sh).
- [ ] Хук исполняет недоверенный ввод? → только machine-owned/opt-in (см. review-gate).
- [ ] После правок плагина/команд — `skiller registry` (общий marketplace подхватывает harness).
- [ ] `bash packages/harness/scripts/validate.sh` зелёный.

## Связанные

`package-architecture` (skiller/раздача), `ecosystem-integration` (хаб/онбординг),
`project-tooling-runbook` (мультиисточник скиллов + Boost-как-MCP).
