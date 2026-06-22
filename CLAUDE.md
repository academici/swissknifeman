# CLAUDE.md — academici (монорепо)

Гид для агентов по корню монорепо. Это **зонтик экосистемы academici**: один репозиторий —
несколько независимых пакетов и плагинов под общей крышей (имя `swissknifeman` = контейнер-«швейцарский
нож», НЕ один из инструментов). Каждый пакет — самостоятельный CLI (`skiller`, `harness`, `maind`);
единой консоли-обёртки пока нет (корневой управляющий слой — запланированная Фаза 2).

## Раскладка

```
<monorepo>/                     # репо `swissknifeman` (зонтик-контейнер)
├── install.sh                 # зонтичный установщик (делегирует install.sh пакетов)
├── core/                      # общий stdlib-only пакет `core` (дословные дубли: Env/term/text)
├── packages/
│   ├── skiller/               # реестр AI-скиллов (skills/, skm/, generate-skill/, lib/, bin/) — CLI skiller
│   ├── harness/               # настройка окружения Claude Code (configs/, lib/, bin/, commands/) — CLI harness
│   └── maind/                 # хаб памяти/графа/координации (lib/, bin/, commands/) — CLI maind
├── .claude-plugin/
│   └── marketplace.json       # ЕДИНЫЙ marketplace репо (генерируется), 20 плагинов
└── docs/                      # зонтичная документация (VitePress)
```

> **Имена ≠ роли.** Репо/marketplace/`~/.swissknifeman/` state — это зонтик `swissknifeman`
> (бренд экосистемы, не переименовываем). Инструмент управления скиллами — пакет/CLI `skiller`
> (бывш. inner `swissknifeman`; алиас `swissknifeman` сохранён в PATH). «hub/хаб» — только роль
> центрального узла mAInd в прозе, не имя сервера.

## Пакеты (у каждого свой CLAUDE.md — читай его при работе внутри)

| Пакет | Роль | CLI | Деталь |
|:--|:--|:--|:--|
| [`packages/skiller`](packages/skiller/CLAUDE.md) | реестр скиллов (раздаёт навыки в проекты) | `skiller` (алиас `swissknifeman`) | source истины скиллов; 2 канала connect/vendor |
| [`packages/harness`](packages/harness/CLAUDE.md) | настройка окружения Claude Code | `harness` | пресеты permissions, auto-approve/bypass, MCP-серверы, хуки (memory/notify). Source истины — `configs/claude-code/`. skiller делегирует сюда через subprocess |
| [`packages/maind`](packages/maind/CLAUDE.md) | память + граф + координация (хаб/шина) | `maind` | MCP-хаб, namespace-память, федерация графа. **Единый** — память (`agentmemory`) и graphify (граф кода) уже отдельные MCP-серверы; дробить maind не нужно |

Это **один монорепозиторий, не «соседние пакеты»**: maind координирует skiller через
`subprocess` (см. `packages/maind/lib/maind/orchestrate.py`); skiller так же делегирует окружение
в harness (`apply_permissions`/integrate → `harness permissions|mcp|hooks`). Все используют `core/`.

## CLI пакетов (три независимые команды)

```bash
skiller <cmd>              # реестр скиллов: connect, vendor, integrate, registry, status, … (алиас swissknifeman)
harness <cmd>              # окружение Claude Code: permissions, mcp, hooks, doctor
maind <cmd>                # хаб: memory, graph, onboard, deploy, sync, health, doctor, …
```

Единой консоли-обёртки пока нет (Фаза 2) — каждый пакет ставится в PATH своим `install.sh`
(зонтичный `install.sh` делегирует им). `skiller` ставится с back-compat алиасом `swissknifeman`.
Пути maind зашиты в `.mcp.json` онбордженных проектов — не ломать.

## Общий пакет `core`

**Дословные дубли** + **примитивы, которые оба пакета успели скопировать независимо** (сведены
к одному источнику истины): `core.term` (die/warn/now_iso/confirm), `core.text` (sanitize),
`core.env` (BaseEnv — ядро root/cmd/home), `core.io` (atomic_write_text/json — атомарная запись
tmp+`os.replace`), `core.repo` (find_repo_root/find_monorepo_root — единый поиск корня вместо
расходившихся копий). `Env` каждого пакета наследует `BaseEnv`, импорт — `from core import ...`.
Подключается через PYTHONPATH (без pip): лаунчеры/`test.sh`/`validate.sh` добавляют **корень
монорепо** (где лежит `core/`) опционально (fallback на standalone-раскладку пакета). stdlib-only.
Bash-лаунчеры и heredoc в `validate.sh` определяют корень своим способом (фикс. `../..` / поиск
`.git`) — осознанный дубль: `core` ещё не на PYTHONPATH в момент их работы.

## Единый marketplace

Один `.claude-plugin/marketplace.json` в корне репо объявляет все плагины (бакеты скиллов +
`skm` + `generate-skill` + `harness` + `maind`). Генерируется `skiller registry`: бакеты — из
`skills/**/SKILL.md`; соседние пакеты (`harness`, `maind`) — из их `packages/<name>/.claude-plugin/plugin.json`.
`source`-пути относительны корня репо (`./packages/...`). Имя marketplace — `swissknifeman` (= зонтик).
У каждой записи плагина есть поле **`package`** (провенанс: `skiller`/`harness`/`maind`) — имена
плагинов НЕ префиксуются (back-compat: плагины подключены как `<plugin>@swissknifeman`).
Плагины `harness`/`maind` — **только команды** (`/harness:*`, `/maind:*`), MCP-сервера в них нет;
MCP-инструменты хаба приходят в проект per-project сервером `maind` из его `.mcp.json`.

## Разработка

```bash
# тесты/валидация — по пакету (каждый знает свой core через PYTHONPATH):
bash packages/skiller/scripts/validate.sh
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
PYTHONPATH=. python3 -m unittest discover -s core/tests       # smoke-тесты пакета core
```

Конвенции пакетов — в их CLAUDE.md. Общее: **stdlib-only** в python, `Env` явно, atomic JSON,
сообщения на русском. Коммиты — Conventional Commits на русском.
