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

## Cross-machine режим: `memory.role` (ADR-0001)

По умолчанию узел — `standalone` (сегодняшний режим, свой демон на loopback; back-compat —
существующие узлы поведения не меняют). Для нескольких постоянных машин
(`docs/adr/ADR-0001-cross-machine-memory.md`) — единственный живой демон на
**host**-машине, остальные — **client**:

```json
"memory": {
  "role": "host",                          // | "standalone" (дефолт) | "client"
  "url": "http://<HOST_LAN_IP>:4111",       // ОБЯЗАТЕЛЕН для role=client, НЕ loopback
  "bind_host": "auto",                      // только role=host: LAN-адрес ЭТОЙ машины (или явный IP)
  "secret_file": "memory.secret"            // путь (относительно корня узла), 0600
}
```

- **`role=client` запрещает поднимать локальный демон КОДОМ** (не только документацией):
  `maind memory start`/`maind memory run`/`maind service install` откажут с ненулевым
  кодом — второй писатель ломает единственность стора (LWW/перезапись целого scope при
  конфликте, `findings/P4-cross-machine-facts.md` §4). Указывайте хост через `memory.url`.
- **`secret_file`** — bearer-токен для `AGENTMEMORY_SECRET` на хосте; порядок разрешения:
  env `AGENTMEMORY_SECRET` → `memory.secret_file` → без токена (анонимно, как сегодня).
  Секрет НЕ хранится инлайном в конфиге (диффы/копии конфига light его бы утекли) и не
  печатается в логах/сообщениях об ошибке.
- **LAN-стадия (ближайшая, D80).** Транспорт — LAN: демон бинденд не на `127.0.0.1`, а на
  **конкретный LAN-адрес хоста**. Адрес машины НЕ хранится в репозитории: tracked
  `config/memory/iii-config.yaml` остаётся портируемым шаблоном (`host: 127.0.0.1`), а адрес
  задаёт узел — `memory.bind_host` в `config.json` (gitignored) либо env `AGENTMEMORY_BIND_HOST`;
  `auto` берёт LAN-IPv4 текущей машины. При старте maind рендерит из шаблона рантайм-копию
  `data/iii-config.runtime.yaml` (gitignored) с подставленным `workers[iii-http].host` и отдаёт её
  демону (`AGENTMEMORY_III_CONFIG`), поэтому `npm install`/апгрейд движка адрес не сбросят, а
  перенос на другой комп = `bind_host: "auto"` (или другой IP) + `memory.url` у клиентов, без правки
  репо. Не-loopback `bind_host` допустим только при `memory.role=host`. Bind
  `0.0.0.0` ЗАПРЕЩЁН (поверхность атаки на весь LAN + key expiry перестаёт быть
  предохранителем); `iii-stream` (стрим-порт) НЕ бинденд на LAN — cross-machine
  store/recall/forget/export идут только через `iii-http` REST.
  При срабатывании триггера **`tailscale serve`** (третья постоянная машина ИЛИ работа вне
  LAN) — правка ОБРАТИМА одной строкой: `host` возвращается к `127.0.0.1`, публикация
  делается снаружи (`tailscale serve --http=4111 127.0.0.1:4111`), `AGENTMEMORY_SECRET`
  остаётся включённым (ADR-0001).
- **Различение «недоступен» от «неавторизован» (401).** `GET /agentmemory/health` ВСЕГДА
  публичен у движка (даже с заданным секретом) — «демон отвечает» ≠ «наши вызовы
  авторизованы». `maind doctor`/`maind health` различают это явным протектед-вызовом
  (`memory.check_auth`), а не полагаются на `ping`.
- **Известные ограничения LAN-стадии** (полностью — `root/adr/ADR-0001-cross-machine-memory.md`):
  секрет — единственный предохранитель (нет автоотзыва по key expiry, как у Tailscale);
  ротация секрета — ручная операция; сегмент LAN шире tailnet (кто в том же сегменте и
  получил секрет — читает/пишет память ВСЕХ проектов); офлайн-машина (нет сети до хоста)
  работает БЕЗ памяти — локального кэша/очереди отложенной записи НЕТ (сознательный отказ,
  версионирования/идемпотентности записи у контракта `store` нет).

## Scopes (бакеты памяти) и где живёт изоляция

| scope | назначение |
|:--|:--|
| `project:<id>` | приватная память проекта (его собственные факты) |
| `ns:<имя>` | **общий бакет namespace-группы** — факты, видимые всем её проектам |
| `global` | вся экосистема: wildcard-инфраструктура (`["*"]`) + ecosystem-wide факты |

> ⚠️ **Изоляция — на стороне maind, не движка.** agentmemory 0.9.x — **единый
> глобальный пул**: поле `namespace` в `remember`/`search`/`memories` он
> **игнорирует**, `sessionId` тоже, а присланный `type` **переопределяет** своим
> классификатором (сверено живым `curl`). Дословно сохраняется только `content`.
> Поэтому scope-изоляцию обеспечивает **сам maind**: при записи встраивает маркер
> `[[s:<scope>]]` в начало контента, при чтении — фильтрует результаты глобального
> поиска по этому маркеру и снимает его (`memory.mark_scope`/`split_scope`).
> Без этого слоя проект видел бы «приватную» память чужих проектов. Не пишите в
> демон в обход maind (`maind memory` / `maind_memory_*` MCP) — записи без маркера
> будут невидимы для scoped-recall.

Модель скоупов: seed пишет один обновляемый факт о связях только в приватный
`project:<id>`. Graph namespaces (`namespaces`) и разрешённые общие области памяти
(`memory_namespaces`) разделены. Обычный recall читает только `project:<id>`; `ns:<имя>`
читается или записывается лишь при явно переданном `scope`. Автоматической публикации seed
в общий бакет нет. Деривация бакетов — `namespaces.py`, seed — `seed.py`. Группы —
[Namespaces](./namespaces).

## Единый путь записи/чтения: хук + MCP через maind

Чтобы «запомнил» (хук памяти) и «вспомнил» (MCP/CLI) шли в ОДИН изолированный стор:

- **Ручной режим `MODE=manual`** — рекомендуемый: память доступна через MCP/CLI, но не
  загружается в каждую сессию; нативная авто-память также выключена.
- **Legacy auto-режим `MODE=maind`** (`~/.claude/hooks/memory/modes/maind.sh`) делегирует
  `remember`/`recall` в `maind memory`; scope берётся из проекта (`CLAUDE_PROJECT_DIR` →
  `match_cwd`), brain игнорируется. `maind onboard` сам пишет `<project>/.claude/memory.env.ini`
  `MODE=maind`.
- **MCP** `maind_memory_store|recall|forget` идут через те же `memory.py`-обёртки;
  `maind_memory_recall(project:<id>)` остаётся в приватном scope. Общий `ns:*` указывается явно.
- **CLI** для человека: `maind memory remember|recall|forget [--project ID|--scope S] [--share]`.

## Авто-загрузка контекста на старте сессии (digest) и native-память

У нативной памяти Claude Code (`~/.claude/projects/<proj>/memory/MEMORY.md`) есть свойство,
которого у демона нет «из коробки»: она **авто-инжектится** в контекст каждой сессии. Чтобы
демон не проигрывал в этом (иначе агент должен ПОМНИТЬ сделать `recall` — недетерминированно):

- `MODE=maind` ставит SessionStart-хук `<project>/.claude/maind-memory.sh`, который зовёт
  **`maind memory digest`** (детерминированный дайджест памяти проекта: list+фильтр по
  scope-маркеру, приватный scope первым, свежее сверху; байт-бюджет + per-item обрезка; хук-
  безопасно — демон лёг → no-op) и инжектит его через `additionalContext` (Claude Code ≥ 2.1.59).
- Одновременно ставится **`autoMemoryEnabled:false`** — нативная авто-память выключается, чтобы
  не было дублирования. Демон становится единым источником и памяти, и стартового контекста.
- **Дайджест — project-only по умолчанию.** `shared_max=0` (дефолт): в `additionalContext` идёт
  ТОЛЬКО приватная память проекта (`project:<id>`); `ns:<группа>`/`global` в дайджест не
  попадают вовсе, даже если факты там есть. Это осознанное сужение (context-economy: общий
  namespace без оговорки раздувал старт каждой сессии и тянул чужой контекст группы —
  «negative» был только у digest, не у recall/графа). Когда `shared_max=0`, digest печатает
  однострочную подсказку `(межпроектное: maind memory recall --scope ns:<name> — digest
  project-only)`. Включить shared в дайджест явно — `--shared-max N` (CLI) или
  `memory.digest.shared_max` в конфиге проекта; тогда добавляются N свежайших shared-фактов
  после private. См. «Межпроектная задача» ниже — как поднять общий контекст без изменения
  дефолта дайджеста.

**Гибко (per-project):** `maind onboard <id> --memory manual|maind|native|off` (дефолт
`manual`). `maind` явно включает старый SessionStart digest; `native` возвращает авто-память.
Проверка консистентности — в `maind health`.

## Межпроектная задача — как явно поднять shared-контекст

Дайджест на старте сессии несёт только свой проект (см. выше). Когда задача реально
межпроектная («проанализируй проект A и B и улучши общее между ними») — поднимай shared-
контекст тремя явными шагами (без изменения дефолта дайджеста):

1. **Связи** — какие проекты вообще связаны и как: `maind graph --project <id>` (CLI, короткая
   форма `view`) или MCP `maind_graph_path`/`maind_graph_neighbors` — путь/соседи в графе.
2. **Контекст группы** — поднять общую память namespace явно (её нет в дайджесте):
   `maind memory recall --scope ns:<имя> "<запрос>"` (CLI) или `maind_memory_recall` c этим
   `scope` (MCP).
3. **Запись вывода** — межпроектный факт пишется в scope группы, не в приватный `project:<id>`,
   иначе другие проекты группы его не увидят: `maind memory remember --scope ns:<имя> "<факт>"`
   (CLI) или `maind_memory_store` с `scope: "ns:<имя>"` (MCP).

Скилл-ориентир с этим же гайдлайном раскатан в каждый подключённый проект — `ecosystem-mcp`
(источник — `packages/maind/templates/skills/ecosystem-mcp/SKILL.md`). Межпроектная оптимизация
кода (дубли/общие пакеты) — отдельный локальный скилл `cross-project-optimizer`
(`maind fleet manifest|duplicates|features`).

## Куда писать факт — правило роутинга (не плодить дубли)

Два слоя комплементарны, **не дублируй один и тот же факт в оба**:

- **maind** (`maind memory` / `maind_memory_*`) — явная долговременная память: приватное
  `project:<id>` по умолчанию, общий scope только по прямому запросу. Для continuity используйте
  ключ `active-handoff`: новая запись заменяет старую. Ключи `progress`, `checkpoint`,
  `session-log` отклоняются — этот журнал принадлежит репозиторию.
- **native MEMORY.md** — выключена при `MODE=maind`. Если осознанно `--memory native`: только
  мелкий курируемый набор инвариантов «всегда под рукой», без копий maind-фактов.
- **file-federation (`MODE=file/federation`, brain `core`)** — legacy, только для инфра-узлов
  (brain/swissknifeman). Для app-проектов не использовать.

## HTTP-контракт демона

| Операция | Запрос (agentmemory 0.9.x, сверено с живым демоном) |
|:--|:--|
| health | `GET /agentmemory/health` |
| store | `POST /agentmemory/remember {namespace, content, type}` — `content` несёт маркер `[[s:<scope>]]` |
| recall | `POST /agentmemory/search {query, namespace, limit}` → `{results:[{observation, score}]}` (фильтр по маркеру — в maind) |
| forget | `POST /agentmemory/forget {memoryId}` — **именно `memoryId`** (не `{namespace,id}` → HTTP 400) |

Обёртка в `memory.py`: `store`/`recall` (маркер + фильтр + нормализация в `[{score, text, id}]`),
`forget`/`export`. Конфиг воркеров — `config/memory/iii-config.yaml` (7 воркеров `iii-*`).

При настроенном `memory.secret_file`/`AGENTMEMORY_SECRET` все протектед-вызовы несут
`Authorization: Bearer <секрет>` (`core.http` — аддитивный параметр `headers`, дефолт не
меняет ничего); `GET /agentmemory/health` — исключение, он публичен всегда. Бюджет ожидания
(таймауты/ретраи) — `MEMORY_LIGHT_TIMEOUT_S`/`MEMORY_HEAVY_TIMEOUT_S`/`MEMORY_RETRIES` в
`constants.py`, измерено в `plans/archive/2026.07.25-ECO-OPT/findings/P4.2-remote-link-measure.md`;
ретраятся только read-вызовы (`export`), не мутации (`store`/`forget` — риск дубля без
operation-id в контракте).

## Проверка «реально ли работает» и troubleshooting

`maind health [--project ID]` выполняет read-only проверку. Мутирующий **round-trip**
write→recall→forget запускается только с `--deep`; `--strict --deep` падает при его провале.
Частые случаи:

- **remember и recall расходятся** (записал — не вспоминается): хук не в `MODE=maind` (пишет в
  файловый `core`-brain мимо демона) → `maind onboard <id>` или поставь `.claude/memory.env.ini`
  `MODE=maind` + переподними сессию.
- **`forget` отдаёт HTTP 400**: старый payload `{namespace,id}` — нужен `{memoryId}` (починено).
- **recall видит «приватные» факты чужого проекта**: запись шла в обход maind (без маркера) —
  пиши только через `maind memory` / `maind_memory_*`.
- **граф проекта пуст**: derive не прогонялся → `maind graph derive --project <id>` (онбординг
  делает это сам; пустой у свежего app-проекта без внутри-экосистемных зависимостей — норма).

> **Коллизия имён «federation».** В хуке памяти `MODE=federation` — это файловый бэкенд
> (`~/.swissknifeman/memory/<brain>/*.md`), он НЕ связан с graph-federation maind (граф по
> проектам + индекс). Для прикладных проектов канон — `MODE=manual` (демон по запросу), файловый
> `federation`/`core` оставлен для инфра-узлов.

Дальше: [Граф →](./graph)
