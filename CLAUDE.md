# CLAUDE.md — maind

Гид по кодовой базе для агентов. Полная документация — `docs/` (VitePress, ru-RU); начни с
[`docs/ecosystem.md`](docs/ecosystem.md) (философия) → [`docs/architecture.md`](docs/architecture.md)
(композиция узла) → `docs/guide/*`.

## Что это

**mAInd** — хаб/шина экосистемы academici: общая память агентов, граф связей, реестры агентов и
проектов, MCP-сервер. Через него идут **два независимых механизма связывания**, оба работают по
namespace'ам:

- **agent-memory** — память/контекст (факты, поток изменений). Внешний Node-демон, maind его
  оркеструет; на проекты раскатывается MCP-клиент к нему.
- **graphify** — граф **кода** внутри проекта (символы/файлы). Отдельный MCP-сервер `graphify-mcp`,
  раскатывается на проекты по `--with-graphify`.

Плюс собственный **maind-граф** — топология **между** проектами (composer/doc/skills), федерация
(граф на проект + индекс), строится из источников истины (`derive`).

## Раскладка

- `bin/maind` — тонкий bash-лаунчер → `python3 -m maind <repo_root> <cmd> [args]`.
- `lib/maind/*.py` — вся логика, **stdlib-only** (без сторонних зависимостей в рантайме).
- `tests/` — `unittest`, без живого демона (`FakeMemoryServer`), изоляция в tmpdir.
- `docs/` — VitePress; `templates/health/` — управляемые артефакты; `config/memory/` — конфиг демона.

### Ключевые модули

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*(env, argv)`) |
| `common.py` | `Env` (frozen dataclass), atomic JSON, HTTP (urllib), `parse_args` |
| `config.py` | загрузка/валидация `.maind.json`, дефолты, маппинг из brain |
| `constants.py` | порты, типы узлов/рёбер, адаптеры, scope-бакеты |
| `memory.py` | оркестрация agent-memory демона + HTTP-обёртка (scope'ы) |
| `graph.py` | примитив property-графа (BFS/path/subgraph/stats) |
| `federation.py` | федерация: граф на проект + индекс; `graph_reader` (единый фасад) |
| `derive.py` | построение графа из источников истины (composer/doc/override/skills) |
| `namespaces.py` | изоляция связей по группам + scope-бакеты памяти |
| `seed.py` | seed-память: факт о связях в `project:<id>` + `ns:<группа>` |
| `mcp.py` | MCP-сервер (stdio JSON-RPC, 11 tools) |
| `deploy.py` / `sync.py` | провижининг MCP-серверов / единый провижининг (фан-аут) |
| `health.py` / `probe.py` | healthcheck связи проекта с хабом / read-only снимки |
| `workspace.py` | доверие Claude к проектам (`.claude/settings.local.json`) |
| `agents.py` / `projects.py` / `orchestrate.py` / `onboard.py` / `migrate.py` / `doctor.py` / `start.py` | реестры, оркестрация, онбординг, миграция, диагностика, запуск |

## Конвенции (соблюдай при правках)

- **stdlib-only** в `lib/maind/`. Никаких pip-зависимостей в рантайме.
- **`Env` передаётся явно** (frozen dataclass), без модульных глобалей — всё тестируемо в tmpdir.
- **Atomic JSON**: `common.atomic_write_json` (tmp + `os.replace`).
- **Сообщения — на русском** (`die(...)`, `warn(...)`), как в swissknifeman/brain.
- **Граф читается через `federation.graph_reader`**, не открывай стор напрямую.
- **Граф строится только из источников истины** (`derive`); ручные связи — `<repo>/.maind.graph.json`.
- **adapter** канонически `federation`/`disabled`; legacy (`memory`/`graphify`/`networkx`) нормализуется.
- **Память по namespace**: `project:<id>` (приватно) · `ns:<имя>` (группа) · `global` (вся экосистема).

## Разработка

```bash
bash scripts/test.sh          # unittest (без внешних зависимостей и живого демона)
bash scripts/validate.sh      # py_compile + bash -n + JSON + обязательные файлы + тесты
npm run docs:dev              # документация локально (VitePress)
```

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный.
