# Память (agent-memory)

Долгосрочная память — внешний **Node-демон** `@agentmemory/agentmemory` (на `iii-sdk`).
maind его **оркестрирует** (не переписывает на Python) и говорит по HTTP, скоупя запросы
по проекту.

## Жизненный цикл

```bash
maind memory start     # запуск отдельной сессией, pidfile в data/, health-poll
maind memory status    # running / url / pid / порты / воркеры
maind memory stop      # SIGTERM→SIGKILL; чужой демон (без pidfile) не трогается
```

`maind start` без `--only` поднимает и память, и граф.

## Порты — из env/конфига

`memory.resolve_ports` берёт значения по приоритету: **env** (`AGENTMEMORY_PORT` /
`AGENTMEMORY_STREAM_PORT` / `AGENTMEMORY_URL`) → **`.maind.json`** (`memory.http_port` /
`stream_port` / `url`) → **дефолт** `4111/4112`. Никаких хардкодов — два узла на одной
машине разводятся по портам через `.env`.

## Scopes (namespace)

Изоляция проектов — логическая, в рамках одного демона:

| scope | назначение |
|:--|:--|
| `project:brain` | приватная память проекта brain |
| `project:swissknifeman` | приватная память swissknifeman |
| `global` | факты всей экосистемы |

## HTTP-контракт демона

| Операция | Запрос (agentmemory 0.9.x, сверено с живым демоном) |
|:--|:--|
| health | `GET /agentmemory/health` |
| store | `POST /agentmemory/remember {namespace, content, type}` |
| recall | `POST /agentmemory/search {query, namespace}` → `{results:[{observation, score}]}` |

Обёртка в `memory.py`: `store(url, scope, key, value)`, `recall(url, scope, query)`
(нормализует ответ в `[{score, text, id}]`), `forget`/`export` (best-effort). Конфиг
воркеров — `config/memory/iii-config.yaml` (7 воркеров `iii-*`, `service_name: maind`).

Дальше: [Граф →](/guide/graph)
