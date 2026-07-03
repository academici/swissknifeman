# CLAUDE.md — maind

Гид по кодовой базе для агентов. Полная документация — `docs/` (VitePress, ru-RU); начни с
[`docs/ecosystem.md`](docs/ecosystem.md) (философия) → [`docs/architecture.md`](docs/architecture.md)
(композиция узла) → `docs/guide/*`.

## Что это

**mAInd** — хаб/шина экосистемы academici: общая память агентов, граф связей, реестры агентов и
проектов, MCP-сервер. Это **control-plane (хаб)** над **тремя независимыми плоскостями связывания**
— они не знают друг о друге (см. импорты: `memory.py` и `graph.py` не пересекаются), встречаются
только в оркестрации (`onboard`/`sync`). Все три изолированы по namespace'ам:

| Плоскость | Что связывает | Движок / где живёт | Чем «индексируется» |
|:--|:--|:--|:--|
| **agent-memory** | память/контекст (факты, поток изменений) | внешний Node-демон (порт 4111/4112), maind оркеструет; на проект — MCP-клиент | пишется по ходу работы |
| **maind-граф** | топология **между** проектами (composer/doc/skills) | хаб-сайд: федерация (граф на проект + индекс) | `maind graph derive` из источников истины |
| **код-граф** | символы/файлы **внутри** проекта | **Serena** (LSP, через `uvx`), per-project MCP-сервер | сам, на лету через LSP |

> «код-граф» исторически назывался **graphify** — инструмента с таким именем не существует, движок
> по факту Serena. Имя `graphify` (флаг `--with-graphify`, поля `graphify_*`, `graph.adapter=graphify`)
> сохраняется только как **legacy-alias** ради обратной совместимости.

## Раскладка

- `bin/maind` — тонкий bash-лаунчер → `python3 -m maind <repo_root> <cmd> [args]`.
- `lib/maind/*.py` — вся логика, **stdlib-only** (без сторонних зависимостей в рантайме).
  Плотно-связное ядро (память/граф/федерация/namespaces/derive + cli/common/config/mcp/health/
  probe/verify) — на верхнем уровне; слабо-связанные окраины сгруппированы в подпакеты
  `provision/` (deploy·sync·onboard·orchestrate·migrate·service·start·workspace·skilldoc) и
  `analysis/` (fleet·analyze·audit). Импорт: `maind.provision.<mod>` / `maind.analysis.<mod>`.
- `tests/` — `unittest`, без живого демона (`FakeMemoryServer`), изоляция в tmpdir.
- `docs/` — VitePress; `templates/health/` — управляемые артефакты; `config/memory/` — конфиг демона.
- `.claude-plugin/` + `commands/*.md` — **плагин Claude Code**: тонкое лицо над CLI (slash-команды
  `/maind:*` → `bin/maind`). **Только команды, без MCP-сервера** — инструменты хаба даёт per-project
  сервер `maind` из `.mcp.json` проекта. Логики нет — обёртки; см. `docs/guide/plugin.md`.

### Ключевые модули

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*(env, argv)`) |
| `common.py` | `Env` (frozen dataclass), atomic JSON, HTTP (urllib), `parse_args` |
| `config.py` | загрузка/валидация `config.json` (в корне монорепо; legacy `.maind.json`), дефолты, маппинг из brain |
| `constants.py` | порты, типы узлов/рёбер, адаптеры, scope-бакеты |
| `memory.py` | оркестрация agent-memory демона + HTTP-обёртка (scope'ы) |
| `graph.py` | примитив property-графа (BFS/path/subgraph/stats) |
| `federation.py` | федерация: граф на проект + индекс; `graph_reader` (единый фасад) |
| `derive.py` | построение графа из источников истины (composer/doc/override/skills) |
| `namespaces.py` | изоляция связей по группам + scope-бакеты памяти |
| `seed.py` | seed-память: факт о связях в `project:<id>` + `ns:<группа>` |
| `mcp.py` | MCP-сервер (stdio JSON-RPC, 11 tools) |
| `deploy.py` / `sync.py` | провижининг MCP-серверов / единый провижининг (фан-аут) |
| `fleet.py` | межпроектный слой: manifest · duplicates (jscpd) · similar (эмбеддинги) · feature-log |
| `codegraph.py` | политика графа кода (секция `code_graph` конфига) + провиженер `.serena/project.yml` (Serena); alias `graphify_*`→`code_*` |
| `health.py` / `probe.py` | healthcheck связи проекта с хабом / read-only снимки |
| `verify.py` | пруф-оф-лайф 3 плоскостей: память (seed vs реал/last-write), покрытие графа, Serena — отличает «поднято» от «реально пишут» |
| `analyze.py` | пост-ран разбор прогона «всё ли сработало»: run-report (SessionEnd-хук harness) + bash-лог + observer + git + health → вердикт GREEN/ATTENTION/RED (repass = dev-loop `tool_failures` → ПОВТОРНЫЙ ПРОХОД) |
| `skilldoc.py` | провиженер скилла `ecosystem-mcp` (инструкция про MCP-инструменты/связи) в проекты |
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
