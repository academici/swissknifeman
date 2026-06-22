# Память (agent-memory)

Долгосрочная память — внешний **Node-демон** `@agentmemory/agentmemory` (на `iii-sdk`).
maind его **оркестрирует** (не переписывает на Python) и говорит по HTTP, скоупя запросы
по проекту.

## Жизненный цикл

```bash
maind memory start     # запуск отдельной сессией, pidfile в data/, health-poll
maind memory run       # foreground (exec node) — для systemd Type=simple
maind memory status    # running / url / pid / порты / воркеры
maind memory stop      # SIGTERM→SIGKILL; чужой демон (без pidfile) не трогается
```

`maind start` без `--only` поднимает и память, и граф. Для автозапуска при логине/загрузке —
зарегистрируйте демон как systemd-сервис: [`maind service install`](./systemd).

## Порты — из env/конфига

`memory.resolve_ports` берёт значения по приоритету: **env** (`AGENTMEMORY_PORT` /
`AGENTMEMORY_STREAM_PORT` / `AGENTMEMORY_URL`) → **`.maind.json`** (`memory.http_port` /
`stream_port` / `url`) → **дефолт** `4111/4112`. Никаких хардкодов — два узла на одной
машине разводятся по портам через `.env`.

## Scopes (бакеты памяти)

Один демон на хаб; изоляция — логическая, через **бакеты (scope)**. Память следует той же
namespace-модели, что и граф: внутри группы общая, между группами изолирована (паритет с
maind-графом по неймспейсам).

| scope | назначение |
|:--|:--|
| `project:<id>` | приватная память проекта (его собственные факты) |
| `ns:<имя>` | **общий бакет namespace-группы** — факты, видимые всем её проектам |
| `global` | вся экосистема: wildcard-инфраструктура (`["*"]`) + ecosystem-wide факты |

При `maind sync`/`onboard` seed пишет базовый факт о связях в приватный `project:<id>`, а
короткий cross-ref — в бакеты группы (`ns:<имя>`; для wildcard-проектов — в `global`). Агент
проекта читает свою память из `project:<id>` + `ns:<его группы>` + `global` (см.
`namespaces.recall_scopes`). Так проект из `axioma` видит факты группы `axioma` и инфраструктуру,
но не память чужого namespace. Деривация бакетов — `namespaces.py`
(`private_scope`/`group_scopes`/`recall_scopes`), seed — `seed.py`. Подробнее про группы —
[Namespaces](./namespaces).

## HTTP-контракт демона

| Операция | Запрос (agentmemory 0.9.x, сверено с живым демоном) |
|:--|:--|
| health | `GET /agentmemory/health` |
| store | `POST /agentmemory/remember {namespace, content, type}` |
| recall | `POST /agentmemory/search {query, namespace}` → `{results:[{observation, score}]}` |

Обёртка в `memory.py`: `store(url, scope, key, value)`, `recall(url, scope, query)`
(нормализует ответ в `[{score, text, id}]`), `forget`/`export` (best-effort). Конфиг
воркеров — `config/memory/iii-config.yaml` (7 воркеров `iii-*`, `service_name: maind`).

Дальше: [Граф →](./graph)
