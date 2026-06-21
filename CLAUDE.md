# CLAUDE.md — academici (монорепо)

Гид для агентов по корню монорепо. Это **зонтик экосистемы academici**: один репозиторий —
несколько независимых пакетов и плагинов под общей крышей, единая консоль `academici`.

## Раскладка

```
academici/
├── bin/academici              # единая консоль-роутер (домен → под-бинарник)
├── install.sh                 # зонтичный установщик (ставит academici + делегирует пакетам)
├── core/                      # общий stdlib-only пакет `core` (дословные дубли: Env/term/text)
├── packages/
│   ├── swissknifeman/         # реестр AI-скиллов (skills/, skm/, generate-skill/, lib/, bin/)
│   └── maind/                 # хаб памяти/графа/координации (lib/, bin/, commands/, .mcp.json)
├── .claude-plugin/
│   └── marketplace.json       # ЕДИНЫЙ marketplace репо (генерируется), 19 плагинов
└── docs/                      # зонтичная документация (VitePress)
```

## Пакеты (у каждого свой CLAUDE.md — читай его при работе внутри)

| Пакет | Роль | CLI | Деталь |
|:--|:--|:--|:--|
| [`packages/swissknifeman`](packages/swissknifeman/CLAUDE.md) | реестр скиллов (раздаёт навыки в проекты) | `swissknifeman` | source истины скиллов; 2 канала connect/vendor |
| [`packages/maind`](packages/maind/CLAUDE.md) | память + граф + координация (хаб/шина) | `maind` | MCP-хаб, namespace-память, федерация графа |

Это **один монорепозиторий, не «соседние пакеты»**: maind координирует swissknifeman через
`subprocess` (см. `packages/maind/lib/maind/orchestrate.py`), оба используют общий `core/`.

## Консоль `academici` (единая точка входа)

```bash
academici maind <cmd>      # → packages/maind/bin/maind
academici skm   <cmd>      # → packages/swissknifeman/bin/swissknifeman
academici <cmd>            # авто-роут уникальной команды без префикса
academici doctor|status    # сводка по обоим пакетам
```

Под-бинарники `maind`/`swissknifeman` остаются самостоятельными (их пути зашиты в `.mcp.json`
онбордженных проектов — не ломать). `academici` их не заменяет, а сводит в одну точку.

## Общий пакет `core`

Только **дословные дубли**, исторически копировавшиеся между пакетами: `core.term` (die/warn/
now_iso/confirm), `core.text` (sanitize), `core.env` (BaseEnv — ядро root/cmd/home). `Env` каждого
пакета наследует `BaseEnv`, импорт — `from core import ...`. Подключается через PYTHONPATH (без
pip): лаунчеры/`test.sh`/`validate.sh` добавляют **корень монорепо** (где лежит `core/`)
опционально (fallback на standalone-раскладку пакета). stdlib-only.

## Единый marketplace

Один `.claude-plugin/marketplace.json` в корне репо объявляет все плагины (бакеты скиллов +
`skm` + `generate-skill` + `maind`). Генерируется `swissknifeman registry`: бакеты — из
`skills/**/SKILL.md`; соседние пакеты (`maind`) — из их `packages/<name>/.claude-plugin/plugin.json`.
`source`-пути относительны корня репо (`./packages/...`). Имя marketplace — `swissknifeman`.

## Разработка

```bash
# тесты/валидация — по пакету (каждый знает свой core через PYTHONPATH):
bash packages/swissknifeman/scripts/validate.sh
bash packages/maind/scripts/validate.sh
PYTHONPATH=. python3 -m unittest discover -s core/tests       # smoke-тесты пакета core
```

Конвенции пакетов — в их CLAUDE.md. Общее: **stdlib-only** в python, `Env` явно, atomic JSON,
сообщения на русском. Коммиты — Conventional Commits на русском.
