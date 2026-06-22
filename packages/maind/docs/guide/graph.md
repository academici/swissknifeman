# Граф связей

Граф — это **топология между проектами**: кто от кого зависит, кто что предоставляет, какие
скиллы используют. Движок — чистый **stdlib** (BFS/кратчайший путь, без сторонних зависимостей),
персист в node-link JSON. Раскладка — **федерация**: граф на проект (`data/graphs/<id>.db`) плюс
тонкий регенерируемый индекс `_index.db` (см. [Федерация](./federation)).

> Этот граф (maind-граф) связывает **топологию между проектами**; память (`agent-memory`) связывает
> **контекст/факты**. Это независимые механизмы хаба, работают по [namespace'ам](./namespaces). Граф
> *кода внутри проекта* (символы/файлы) — это отдельная плоскость, [код-граф (Serena)](./code-graph).

## Типы узлов и рёбер

| Узел (`<type>:<key>`) | | Ребро | |
|:--|:--|:--|:--|
| `project` | проект экосистемы | `depends_on` | межпроектная зависимость (из composer) |
| `package` | composer/npm-пакет | `requires` | проект требует пакет |
| `skill` | скилл из swissknifeman | `provided_by` | пакет/скилл предоставлен проектом/тулом |
| `tool` | swissknifeman / boost / brain | `uses` | проект использует скилл / doc-связь |
| `doc` · `agent` · `memory` · `entity` | прочие домены | `relates_to` · `belongs_to` · `knows` | override / прочее |

Узлы именуются `<type>:<key>` (например `project:brain`) — бесконфликтная склейка доменов,
тип выводится из id.

## Откуда берутся связи (derive, без ручного дубля)

`maind graph derive` строит сторы проектов из **источников истины**, помечая рёбра планом
(`code|doc|meta|runtime`) и источником (`via`) — `derive.py`:

| План (`via`) | Источник | Рёбра |
|:--|:--|:--|
| `code` | `composer.json`/`package.json` (+ path-repos) | `project ─requires→ package`, `package ─provided_by→ project`, cross `project ─depends_on→ project` |
| `doc` | Brain frontmatter `uses:/used_by:` (**только чтение**) | `project ─uses→ project` |
| `override` | `<repo>/.maind.graph.json` | объявленные `relates_to`/… (runtime/API) |
| `skills` | `skills-lock.json` | `project ─uses→ skill ─provided_by→ tool` |

Истина остаётся в composer/Brain/lock — `_index.db` лишь регенерируемый кэш. Конфиг-поля проекта
(`dependencies`/`agents`) графом **не материализуются**: чтобы объявить связь, которой нет в коде,
используйте `.maind.graph.json` (план `override`).

## API (`graph.py` — примитив)

```python
g.neighbors("project:maind", depth=1, direction="in")   # кто зависит от maind
g.path("project:flexcrm", "project:azguard")            # кратчайший путь (BFS)
g.subgraph(["project:brain", "project:maind"])          # индуцированный подграф
g.stats()                                               # узлы/рёбра/компоненты/степень
```

Читать федерированный граф нужно через `federation.graph_reader(env, config)` (единый фасад),
а не открывать стор напрямую.

## CLI

```bash
maind graph derive --all                 # собрать графы всех проектов из источников
maind graph rebuild                      # пересобрать только _index.db
maind graph stats                        # сводка по федерации
maind graph query --from project:flexcrm --depth 2 [--edge-types depends_on]
maind graph neighbors --node project:maind --direction in
maind graph --project flexcrm            # граф одного проекта
maind graph --cross [--namespace axioma] # межпроектный слой (опц. одной группы)
```

## Пример: что увидишь

Собрать граф проекта и посмотреть его подграф (реальный вывод для `corex`):

```console
$ maind graph derive --project corex
  corex              узлов 12, рёбер 14 (code 10, doc 5, override 0)

$ maind graph view --project corex
граф проекта corex: 12 узлов, 14 рёбер
  package:corex/core               package    core
  package:corex/crm                package    crm
  project:flexcrm                  project
  project:azguard                  project
  …
  package:corex/core           —provided_by→ project:corex             [code]
  project:corex                —requires→ package:axioma-studio/azguard-core  [code]

$ maind graph stats
Граф: 15 узлов, 22 рёбер, 1 компонент(ы), max степень 14
  узлы:  package=9, project=6
  рёбра: provided_by=9, requires=7, uses=6
```

## Те же запросы из агента (MCP)

В сессии проекта эти связи доступны как MCP-инструменты сервера `maind` — агент зовёт их сам:

| Инструмент | Аргументы | Отвечает на |
|:--|:--|:--|
| `maind_graph_project` | `{ "project": "corex" }` | подграф проекта + исходящие кросс-рёбра |
| `maind_graph_neighbors` | `{ "node": "project:corex", "depth": 1, "direction": "in" }` | кто зависит от corex |
| `maind_graph_query` | `{ "from": "project:flexcrm", "depth": 2, "edge_types": "depends_on" }` | обход от узла по типам рёбер |
| `maind_graph_path` | `{ "from": "project:flexcrm", "to": "project:azguard" }` | кратчайший путь между проектами |

Это **pull**: инструменты пассивны, вызов инициирует модель (скилл `ecosystem-mcp` подсказывает когда).
Память — отдельные инструменты той же сессии: `maind_memory_recall` / `maind_memory_store` / `maind_memory_links`.

## Адаптер

`graph.adapter` в конфиге: `federation` (по умолчанию, единственная раскладка) либо `disabled`
(граф-команды недоступны). Устаревшие `memory`/`graphify`/`networkx` принимаются с предупреждением
и нормализуются в `federation`.

Дальше: [Федерация →](./federation)
