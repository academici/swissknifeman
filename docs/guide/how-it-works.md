# Как это всё работает вместе

Эта страница — сквозная картина: что подключается к проекту, где физически лежат данные, и что
происходит, когда агент выполняет задачу. Если после неё остались вопросы — значит, тут чего-то
не хватает; дополняйте.

## Три разные вещи (не путать)

Слова «граф» и «база» в экосистеме означают **три независимых** механизма с разными задачами:

| Механизм | Что хранит | Где живёт | Статус |
|:--|:--|:--|:--|
| **agent-memory** | факты/решения/контекст (общая память) | демон на хабе `:4111` | работает (под systemd) |
| **maind-граф** | топология **между** проектами (кто от кого зависит) | в хабе `data/graphs/<id>.db` | работает |
| **graphify** | граф **кода внутри** проекта (символы/файлы/вызовы) | отдельный MCP-сервер в проекте | **опционален**, бинаря пока нет |

Ключевое: **agent-memory централизован специально** (в этом смысл общей памяти — проекты видят
решения друг друга внутри namespace). **graphify, наоборот, пер-проектный** — код у каждого свой.
maind-граф — это НЕ код, а топология зависимостей.

## 1. Топология: что подключено к проекту

```mermaid
graph TB
  subgraph proj["проект (напр. flexcrm)"]
    MCPJSON[".mcp.json"]
    SKILL[".claude/skills/ecosystem-mcp"]
  end
  subgraph hub["хаб mAInd"]
    MEM["agent-memory daemon :4111"]
    GR["maind-граф: data/graphs/*.db"]
    SRV["maind MCP-сервер"]
  end
  GFY["graphify-mcp (опц., в проекте)"]
  MCPJSON -- "agentmemory" --> MEM
  MCPJSON -- "maind" --> SRV
  MCPJSON -. "graphify (если graphify:true)" .-> GFY
  SRV --> GR
  SRV --> MEM
```

`.mcp.json` проекта перечисляет MCP-серверы. Клиент (Claude Code) при старте сессии их поднимает —
и их инструменты появляются у агента. Скилл `ecosystem-mcp` объясняет агенту, что это и когда звать.

## 2. Поток выполнения задачи (pull, не «перехват»)

MCP-серверы **пассивны**: они не следят за кодом и ничего не «перехватывают». Запрос инициирует
**сама модель**, когда решает вызвать инструмент.

```mermaid
sequenceDiagram
  participant A as Агент в проекте
  participant M as MCP (agentmemory / maind)
  participant D as Демон/граф на хабе
  A->>M: recall("прошлые решения по X")
  M->>D: search namespace=project:flexcrm (+ns:axioma, +global)
  D-->>M: факты
  M-->>A: контекст
  Note over A: ...агент делает работу...
  A->>M: store("принятое решение Y")
  M->>D: remember namespace=project:flexcrm
```

scope (`project:flexcrm`) зашит в `.mcp.json` проекта (`AGENTMEMORY_NAMESPACE`), поэтому проект по
умолчанию пишет/читает **свою** память + общие бакеты группы. Никакой автоматики «само записалось»
нет — агент явно вызывает `store`/`recall` (скилл `ecosystem-mcp` подсказывает когда).

## 3. Три слоя данных — кто за что

```mermaid
flowchart LR
  subgraph code["код проекта"]
    GFY["graphify: символы/файлы/вызовы (опц.)"]
  end
  subgraph topo["между проектами"]
    MG["maind-граф: зависимости composer/доки/скиллы"]
  end
  subgraph mem["общая память"]
    AM["agent-memory: факты/решения по namespace"]
  end
  GFY -. "навигация по коду" .-> DEV["агент"]
  MG -. "связи проекта" .-> DEV
  AM -. "история/контекст" .-> DEV
```

- **agent-memory** отвечает на «что мы уже решали».
- **maind-граф** — на «что с чем связано» (зависимости, соседи по экосистеме).
- **graphify** — на «где определён этот символ / кто его вызывает» (когда включён).

## 4. Namespace-изоляция в действии

Связи и память изолируются по группам. Внутри группы — общее, между группами — закрыто; `["*"]` —
инфраструктура, видна всем.

```mermaid
graph TB
  subgraph axioma["namespace: axioma"]
    FX["flexcrm"]
    AZ["azguard"]
    NSA["ns:axioma (общая память группы)"]
    FX --- NSA
    AZ --- NSA
  end
  subgraph dbx["namespace: diabox"]
    DB["diabox"]
    NSD["ns:diabox"]
    DB --- NSD
  end
  GL["global (вся экосистема)"]
  NSA --- GL
  NSD --- GL
```

flexcrm видит: `project:flexcrm` + `ns:axioma` + `global`. diabox из другой группы `ns:axioma`
**не видит**. Так же режутся и рёбра графа: межпроектная связь строится, только если проекты делят
namespace.

## Надёжность «всё всегда поднято»

- Демон памяти — под **systemd** (`maind service install`), автозапуск + авто-рестарт. Для старта
  при загрузке ОС (без логина) — `loginctl enable-linger $USER`. См.
  [Демон памяти (systemd)](/guide/systemd).
- MCP-серверы прописаны в `.mcp.json` каждого проекта — клиент поднимает их сам при старте сессии.
- SessionStart-хук печатает статус связи; чинит — `maind health --cwd --fix`.

Дальше: [Память →](/guide/memory) · [Граф →](/guide/graph) · [Namespaces →](/guide/namespaces) ·
[graphify →](/guide/graphify).
