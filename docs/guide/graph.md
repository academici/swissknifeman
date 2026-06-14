# Граф связей

Один граф на всю экосистему — это «общая связь». Движок по умолчанию — чистый **stdlib**
(без сторонних зависимостей), персист в node-link JSON (`data/graph.db`).

## Типы узлов и рёбер

| Узел (`<type>:<key>`) | | Ребро | |
|:--|:--|:--|:--|
| `project` | проект экосистемы | `uses` | проект/агент использует скилл |
| `agent` | запущенный агент | `knows` | агент знает единицу памяти |
| `memory` | единица памяти | `relates_to` | связь двух памятей |
| `skill` | скилл из swissknifeman | `belongs_to` | память/агент принадлежит проекту |
| `entity` | произвольная сущность | `depends_on` | межпроектная зависимость |

Узлы именуются `<type>:<key>` (например `project:brain`) — это даёт бесконфликтную склейку
доменов и позволяет выводить тип из id.

## API (`graph.py`)

```python
g.add_node("project:brain", "project", name="Brain")
g.add_edge("project:swissknifeman", "project:maind", "depends_on")
g.neighbors("project:maind", depth=1, direction="in")   # кто зависит от maind
g.path("project:swissknifeman", "project:maind")        # кратчайший путь (BFS)
g.subgraph(["project:brain", "project:maind"])          # индуцированный подграф
g.stats()                                               # узлы/рёбра/компоненты/степень
```

## CLI

```bash
maind graph stats
maind graph query --from project:brain --depth 2
maind graph neighbors --node project:maind --direction in --edge-types depends_on
```

## Автозасев из конфига

`maind start` и `maind migrate from-brain` регистрируют проекты из `.maind.json` как узлы
и материализуют `dependencies`→`depends_on`, `skills`→`uses`, `agents`→`belongs_to`.

## Адаптеры

`graph.adapter` в конфиге: `memory` (stdlib, по умолчанию) · `graphify` / `networkx`
(опциональные, lazy-import; нужны только если выбраны явно) · `disabled`.

Дальше: [Агенты →](/guide/agents)
