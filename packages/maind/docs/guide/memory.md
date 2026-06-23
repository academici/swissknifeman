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

Модель скоупов: при `maind onboard`/`sync` seed пишет базовый факт о связях в приватный
`project:<id>`, а короткий cross-ref — в бакеты группы (`ns:<имя>`; wildcard → `global`).
Запись через `maind memory remember` идёт в приватный scope; `--share` дублирует в группы.
Recall объединяет `project:<id>` + `ns:<все группы>` + `global` (`namespaces.recall_scopes`)
с дедупом по тексту. Так проект из `axioma` видит общий дом и инфраструктуру, но не приватную
память чужого проекта. Деривация бакетов — `namespaces.py`, seed — `seed.py`. Группы —
[Namespaces](./namespaces).

## Единый путь записи/чтения: хук + MCP через maind

Чтобы «запомнил» (хук памяти) и «вспомнил» (MCP/CLI) шли в ОДИН изолированный стор:

- **Хук памяти** в режиме `MODE=maind` (`~/.claude/hooks/memory/modes/maind.sh`) делегирует
  `remember`/`recall` в `maind memory`; scope берётся из проекта (`CLAUDE_PROJECT_DIR` →
  `match_cwd`), brain игнорируется. `maind onboard` сам пишет `<project>/.claude/memory.env.ini`
  `MODE=maind`.
- **MCP** `maind_memory_store|recall|forget` идут через те же `memory.py`-обёртки;
  `maind_memory_recall(project:<id>)` разворачивается в полный набор recall-scope'ов.
- **CLI** для человека: `maind memory remember|recall|forget [--project ID|--scope S] [--share]`.

## Авто-загрузка контекста на старте сессии (digest) и native-память

У нативной памяти Claude Code (`~/.claude/projects/<proj>/memory/MEMORY.md`) есть свойство,
которого у демона нет «из коробки»: она **авто-инжектится** в контекст каждой сессии. Чтобы
демон не проигрывал в этом (иначе агент должен ПОМНИТЬ сделать `recall` — недетерминированно):

- `MODE=maind` ставит SessionStart-хук `<project>/.claude/maind-memory.sh`, который зовёт
  **`maind memory digest`** (детерминированный дайджест памяти проекта: list+фильтр по
  scope-маркеру, приватный scope первым, свежее сверху; хук-безопасно — демон лёг → no-op) и
  инжектит его через `additionalContext` (Claude Code ≥ 2.1.59).
- Одновременно ставится **`autoMemoryEnabled:false`** — нативная авто-память выключается, чтобы
  не было дублирования. Демон становится единым источником и памяти, и стартового контекста.

**Гибко (per-project):** `maind onboard <id> --memory maind|native|off` (дефолт `maind`; в
интерактиве — вопрос). `native` делает revert (вернуть авто-память, снять digest-хук). Проверка
консистентности — в `maind health` (MODE=maind ⇒ native off + digest-хук на месте).

## Куда писать факт — правило роутинга (не плодить дубли)

Два слоя комплементарны, **не дублируй один и тот же факт в оба**:

- **maind** (`maind memory` / `maind_memory_*`) — память проекта и дома: приватное `project:<id>`,
  общее по тегу `--share`, ищется `recall`, видна кросс-проектно/кросс-агентно (Cursor и др.).
  Дайджест авто-инжектится на старте. ← **дефолт для проектов**.
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

## Проверка «реально ли работает» и troubleshooting

`maind health [--project ID]` гоняет **round-trip** write→recall→forget по приватному scope и
проверяет, что хук в `MODE=maind`. `--strict` падает при провале. Частые случаи:

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
> проектам + индекс). Для прикладных проектов канон — `MODE=maind` (демон), файловый
> `federation`/`core` оставлен для инфра-узлов.

Дальше: [Граф →](./graph)
