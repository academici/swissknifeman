# Граф связей

Граф — это **топология между проектами**: кто от кого зависит, кто что предоставляет, какие
скиллы используют. Движок — чистый **stdlib** (BFS/кратчайший путь, без сторонних зависимостей),
персист в node-link JSON. Раскладка — **федерация**: граф на проект (`data/graphs/<id>.db`) плюс
тонкий регенерируемый индекс `_index.db` (см. [Федерация](/guide/federation)).

> Граф связывает **код/топологию**; память (`agent-memory`) связывает **контекст/факты**. Это два
> независимых механизма хаба, оба работают по [namespace'ам](/guide/namespaces). Граф *кода внутри
> проекта* (символы/файлы) — это [graphify](/guide/code-graph), отдельный слой.

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

## Адаптер

`graph.adapter` в конфиге: `federation` (по умолчанию, единственная раскладка) либо `disabled`
(граф-команды недоступны). Устаревшие `memory`/`graphify`/`networkx` принимаются с предупреждением
и нормализуются в `federation`.

Дальше: [Федерация →](/guide/federation)
