# Агенты

Реестр запущенных агентов узла — в `~/.maind/agents.json` (атомарная запись). Состояние
агента **не хранится**, а выводится при чтении из возраста последнего heartbeat и живости
pid — файл хранит только факты.

## Жизненный цикл

```bash
maind agents register vault-architect --project brain --pid 12345 --kind worker
maind agents heartbeat vault-architect      # обновить last_heartbeat
maind agents list [--all] [--json]          # без --all скрывает dead
maind agents kill vault-architect [--force] # SIGTERM (или SIGKILL) + снять с реестра
```

## Состояния

| Состояние | Условие |
|:--|:--|
| `alive` | свежий heartbeat, pid жив (или не задан) |
| `stale` | возраст heartbeat > `heartbeat_interval_ms × 3` |
| `dead` | pid задан, но процесс не существует |

`heartbeat_interval_ms` берётся из `agents.heartbeat_interval_ms` конфига (дефолт 30000).
`reap()` удаляет `dead`/`stale` агентов.

## API (`agents.py`)

```python
register(env, "id", pid=..., project=..., kind=...)   # upsert, registered_at один раз
heartbeat(env, "id")
listing(env, config)                                  # каждый агент с полем state
kill(env, "id", force=False)
reap(env, config)                                     # вернёт число удалённых
```

## Связь с графом

Агент из `projects[].agents` материализуется в графе как `agent:<id>` с ребром
`belongs_to` к проекту — см. [Граф](/guide/graph).

Дальше: [Проекты →](/guide/projects)
