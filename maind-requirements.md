# mAInd — Requirements Document

> **Статус:** Draft v0.1 · Июнь 2026
> **Репозиторий:** `academici/maind`
> **Слоган:** The central intelligence layer of the academici ecosystem

---

## 1. Обзор

**mAInd** — главный хаб всей экосистемы academici. Это не утилита и не вспомогательный пакет — это
живой мозг: хранит долгосрочную память агентов, строит граф связей между сущностями, координирует
рой агентов и является единым источником истины о топологии всех проектов.

Пакет объединяет три компонента-донора и добавляет новый слой оркестрации поверх:

| Источник | Что переходит в mAInd |
|:---|:---|
| `academici/swissknifeman` | Модуль `agent-memory` (`.agentmemory/`) целиком |
| `safishamsi/graphify` | Граф-движок: nodes, edges, traversal |
| `academici/brain` | `.projects.json` → становится `.maind.json` (расширенная версия) |

---

## 2. Позиционирование в экосистеме

```
┌─────────────────────────────────────────────────────┐
│                    mAInd (этот пакет)               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ agent-memory │  │   graphify   │  │  agents   │ │
│  │  (из SKM)    │  │  (граф связей│  │  runtime  │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│               ↕ .maind.json ↕                       │
└─────────────────────────────────────────────────────┘
         ↑                    ↑
  swissknifeman             brain
  (навыки / скиллы)     (документация)
```

**mAInd** — вершина иерархии. Остальные пакеты подключаются к нему, а не к друг другу напрямую.

---

## 3. Что переносится из swissknifeman

### 3.1 Модуль agent-memory

Текущее расположение в swissknifeman: `.agentmemory/` — конфиг воркеров `iii-*`.

В mAInd этот модуль становится первым классом, а не вспомогательным каталогом.

**Переносится целиком:**

- `.agentmemory/iii-config.yaml` → `config/memory/iii-config.yaml` (новый путь)
- Весь рантайм воркеров: `iii-http`, `iii-state`, `iii-queue`, `iii-pubsub`, `iii-cron`,
  `iii-stream`, `iii-observability`
- `data/state_store.db` и `data/stream_store` — хранилища состояния
- Все MCP-интеграции через `agentmemory` сервер (порты 4111/4112)

**Что расширяется:**

- `iii-state` получает второй адаптер: `graph` (через graphify) — для хранения связей как
  first-class граждан рядом с KV-памятью
- `iii-observability` переключается на `service_name: maind` и полный pipeline логов в stdout
- Добавляется `iii-agents` воркер — реестр запущенных агентов с heartbeat

**Что остаётся в swissknifeman:**

- Всё что связано со скиллами: `skills.json`, `buckets.json`, профили, registry, vendor
- Логика установки/синхронизации скиллов в IDE-адаптеры

После переноса swissknifeman получает `agent-memory` как зависимость от mAInd, а не
держит его у себя:

```json
// swissknifeman/package.json — после переноса
{
  "dependencies": {
    "@academici/maind": "^1.0.0"
  }
}
```

---

## 4. Что добавляется: Graphify

**Репозиторий:** [safishamsi/graphify](https://github.com/safishamsi/graphify)

Graphify встраивается как граф-движок для хранения и обхода связей между сущностями экосистемы:
проектами, агентами, памятью, скиллами.

**Интеграция:**

- Каждая сущность в `agent-memory` получает граф-идентификатор (node)
- Отношения между сущностями (project → uses → skill, agent → wrote → memory) — edges
- API mAInd предоставляет unified интерфейс: `memory.get()` + `graph.neighbors()` через один вызов
- Graphify становится вторым бэкендом для `iii-state` наряду с KV-файлом

**Типы сущностей в графе:**

| Node type | Описание |
|:---|:---|
| `project` | Проект экосистемы (из `.maind.json`) |
| `agent` | Запущенный агент с идентификатором сессии |
| `memory` | Единица долгосрочной памяти агента |
| `skill` | Скилл из swissknifeman |
| `entity` | Произвольная именованная сущность (пользователь, документ, факт) |

**Типы рёбер:**

| Edge type | Описание |
|:---|:---|
| `uses` | Проект/агент использует скилл |
| `knows` | Агент имеет доступ к единице памяти |
| `relates_to` | Связь между двумя памятями |
| `belongs_to` | Память/агент принадлежит проекту |
| `depends_on` | Межпроектная зависимость |

---

## 5. Конфигурация: `.maind.json`

`.maind.json` — главный конфиг узла. Является **надмножеством** `.projects.json` из `brain`.

### 5.1 Отношение к `.projects.json`

`.projects.json` из `brain` не исчезает — он остаётся **fallback-конфигом** для обратной
совместимости. Логика приоритета:

```
.maind.json   (primary — если есть)
    ↓ fallback
.projects.json  (legacy — только чтение, только поля совместимые с brain)
```

CLI mAInd при запуске читает сначала `.maind.json`, и если его нет — подхватывает `.projects.json`
с предупреждением о миграции.

### 5.2 Схема `.maind.json`

```jsonc
{
  // ── Мета ──────────────────────────────────────────────────────────
  "_version": "1",
  "_comment": "Главный конфиг узла mAInd. Надмножество .projects.json",

  // ── Идентификация узла ────────────────────────────────────────────
  "node": {
    "id": "brain",                      // уникальный slug узла
    "name": "Academici Brain",          // человекочитаемое имя
    "role": "primary",                  // primary | secondary | mirror
    "description": "Central knowledge and agent hub"
  },

  // ── Память ────────────────────────────────────────────────────────
  "memory": {
    "enabled": true,
    "config_path": "config/memory/iii-config.yaml",
    "http_port": 4111,
    "stream_port": 4112,
    "data_dir": "./data"
  },

  // ── Граф ──────────────────────────────────────────────────────────
  "graph": {
    "enabled": true,
    "adapter": "graphify",              // graphify | memory | disabled
    "persist": true,
    "persist_path": "./data/graph.db"
  },

  // ── Агенты ────────────────────────────────────────────────────────
  "agents": {
    "registry_enabled": true,
    "heartbeat_interval_ms": 30000,
    "max_idle_ms": 300000,
    "definitions": [
      // Дескрипторы агентов, которые крутятся на этом узле
      {
        "id": "vault-architect",
        "description": "Senior architect for brain vault",
        "skills": ["architect", "oss-dev"],
        "memory_scope": "project:brain",
        "autostart": false
      }
    ]
  },

  // ── Проекты (надмножество .projects.json) ─────────────────────────
  "projects": [
    {
      // Поля совместимые с .projects.json (legacy)
      "id": "brain",
      "name": "Brain",
      "repo": "academici/brain",
      "local_path": "~/projects/brain",
      "type": "obsidian-vault",

      // Расширения mAInd
      "graph_node": true,               // регистрировать как node в графе
      "memory_scope": "project:brain",  // изолированный scope памяти
      "agents": ["vault-architect"],    // связанные агенты
      "tags": ["primary", "docs"],
      "status": "active",               // active | archived | planning
      "dependencies": []                // id других проектов
    },
    {
      "id": "swissknifeman",
      "name": "SwissKnifeMan",
      "repo": "academici/swissknifeman",
      "local_path": "~/projects/packages/swissknifeman",
      "type": "node-package",

      "graph_node": true,
      "memory_scope": "project:swissknifeman",
      "agents": [],
      "tags": ["package", "skills"],
      "status": "active",
      "dependencies": ["maind"]
    }
  ],

  // ── Интеграции ────────────────────────────────────────────────────
  "integrations": {
    "swissknifeman": {
      "enabled": true,
      "skills_sync": true              // автоматически подтягивать новые скиллы
    },
    "brain": {
      "enabled": true,
      "projects_sync": true,           // синк из .projects.json при старте
      "sync_direction": "import"       // import | export | bidirectional
    }
  },

  // ── MCP-серверы ───────────────────────────────────────────────────
  "mcp": {
    "servers": [
      {
        "name": "agentmemory",
        "transport": "http",
        "url": "http://127.0.0.1:4111/mcp",
        "enabled": true
      },
      {
        "name": "graphify",
        "transport": "http",
        "url": "http://127.0.0.1:4113/mcp",
        "enabled": true
      }
    ]
  },

  // ── Observability ─────────────────────────────────────────────────
  "observability": {
    "service_name": "maind",
    "log_level": "info",
    "metrics_enabled": true,
    "traces_enabled": false
  }
}
```

### 5.3 Поля совместимые с `.projects.json`

Следующие поля являются обязательными для совместимости с `brain` CLI (`brain sync`):

| Поле | Тип | Описание |
|:---|:---|:---|
| `projects[].id` | string | Уникальный slug проекта |
| `projects[].name` | string | Человекочитаемое имя |
| `projects[].repo` | string | GitHub slug `owner/repo` |
| `projects[].local_path` | string | Локальный путь |
| `projects[].type` | string | Тип проекта |

Все остальные поля являются расширениями mAInd и игнорируются `brain` при чтении fallback.

---

## 6. Архитектура пакета

### 6.1 Структура репозитория

```
academici/maind/
├── .maind.example.json       ← пример конфига (как .swissknife.example.json в SKM)
├── config/
│   └── memory/
│       └── iii-config.yaml   ← перенесено из SKM/.agentmemory/
├── lib/
│   └── maind/
│       ├── __init__.py
│       ├── cli.py            ← CLI: maind start | status | agents | graph
│       ├── config.py         ← парсинг .maind.json + fallback .projects.json
│       ├── memory.py         ← интерфейс к agent-memory воркерам
│       ├── graph.py          ← интерфейс к graphify
│       ├── agents.py         ← реестр агентов, heartbeat, lifecycle
│       ├── projects.py       ← реестр проектов, синк с brain
│       └── mcp.py            ← MCP server для внешних агентов
├── bin/
│   └── maind                 ← точка входа CLI
├── data/                     ← gitignored, runtime данные
│   ├── state_store.db
│   ├── stream_store/
│   └── graph.db
├── tests/
├── docs/
├── install.sh
├── package.json
└── README.md
```

### 6.2 Компоненты

**Memory Layer** (`lib/maind/memory.py`)
Обёртка над `iii-*` воркерами. Предоставляет API:
- `memory.store(scope, key, value, ttl?)` — сохранить факт
- `memory.recall(scope, query)` — семантический поиск по памяти
- `memory.forget(scope, key)` — удалить факт
- `memory.export(scope)` — дамп всей памяти скоупа

**Graph Layer** (`lib/maind/graph.py`)
Обёртка над graphify. API:
- `graph.node(type, id, meta?)` — создать/обновить узел
- `graph.edge(from, type, to, meta?)` — создать/обновить ребро
- `graph.neighbors(id, edge_type?, depth?)` — обход соседей
- `graph.path(from, to)` — кратчайший путь между узлами
- `graph.subgraph(ids[])` — подграф по набору узлов

**Agent Registry** (`lib/maind/agents.py`)
- Регистрация агента при старте: `agents.register(id, meta)`
- Heartbeat loop: обновление `last_seen` каждые N секунд
- `agents.list(status?)` — активные/все агенты
- `agents.kill(id)` — принудительная остановка
- `agents.scope(id)` — изолированный memory + graph scope агента

**Projects Registry** (`lib/maind/projects.py`)
- Загрузка `.maind.json` с fallback на `.projects.json`
- `projects.list(status?)` — все проекты
- `projects.get(id)` — проект по id
- `projects.sync_from_brain(path)` — импорт из `.projects.json`
- `projects.export_to_brain(path)` — экспорт совместимого подмножества

**MCP Server** (`lib/maind/mcp.py`)
mAInd сам является MCP-сервером для внешних агентов (Claude, Cursor, etc.).
Экспонирует tools:
- `maind_memory_store`, `maind_memory_recall`
- `maind_graph_query`, `maind_graph_neighbors`
- `maind_agents_list`, `maind_projects_list`

---

## 7. CLI

```bash
# Старт всех воркеров
maind start

# Запустить только memory воркеры
maind start --only memory

# Запустить только граф
maind start --only graph

# Статус воркеров
maind status

# Список агентов
maind agents list
maind agents kill <id>

# Граф
maind graph query --from project:brain --depth 2
maind graph stats

# Проекты
maind projects list
maind projects sync --from brain --path ~/projects/brain

# Миграция
maind migrate from-brain .projects.json    # импорт legacy конфига
maind migrate from-skm .agentmemory/       # импорт модуля из SKM
```

---

## 8. Фазы реализации

### Phase 1 — Foundation (Memory + Config)

- [ ] Создать репозиторий `academici/maind`
- [ ] Перенести `.agentmemory/` → `config/memory/iii-config.yaml`
- [ ] Реализовать `config.py` с поддержкой `.maind.json` + fallback `.projects.json`
- [ ] Реализовать `memory.py` (обёртка над iii-*)
- [ ] CLI: `maind start`, `maind status`
- [ ] `.maind.example.json` с полной схемой
- [ ] `install.sh` (аналог brain/swissknifeman)
- [ ] Обновить swissknifeman: убрать `.agentmemory/`, добавить зависимость на maind

### Phase 2 — Graph Layer

- [ ] Интегрировать graphify как зависимость
- [ ] Реализовать `graph.py` — все методы API
- [ ] Расширить `iii-state` для dual-backend (KV + graph)
- [ ] Автоматическая регистрация проектов из `.maind.json` как nodes
- [ ] CLI: `maind graph query`, `maind graph stats`

### Phase 3 — Agent Runtime

- [ ] Реализовать `agents.py` — registry + heartbeat
- [ ] Изолированные скоупы памяти и графа для каждого агента
- [ ] Добавить `iii-agents` воркер в `iii-config.yaml`
- [ ] CLI: `maind agents list`, `maind agents kill`
- [ ] Интеграция с `brain` агентами (AGENTS.md)

### Phase 4 — MCP + Integrations

- [ ] MCP-сервер: tools для memory/graph/agents/projects
- [ ] `.mcp.json` с записью `maind` сервера
- [ ] Синк с `brain` через `projects.sync_from_brain()`
- [ ] Синк скиллов через swissknifeman API
- [ ] Обновить `brain/CLAUDE.md` — добавить mAInd в карту MCP-серверов

---

## 9. Зависимости

| Пакет | Версия | Роль |
|:---|:---|:---|
| `graphify` (safishamsi) | latest | Граф-движок |
| `agent-memory` (iii-*) | из SKM | Memory воркеры |
| `@anthropic/sdk` | latest | MCP protocol |
| `yaml` | ^2 | Парсинг iii-config.yaml |
| `zod` / `jsonschema` | latest | Валидация .maind.json |

---

## 10. Альтернативные названия

Рассматривались следующие имена перед финальным выбором `mAInd`:

### Synapse
**Синапс** — точка передачи сигнала между нейронами. Идеально описывает роль пакета как
посредника между агентами: именно через синапс один агент «знает» о другом. Минус — звучит
как связующий слой, а не как центральный мозг. Больше подходит для middleware или event-bus.

### Loom
**Ткацкий станок** — плетёт нити-связи между агентами и памятью в единое полотно.
Сильная образная метафора для граф-движка. Короткое, звонкое, нестандартное для AI-пакетов.
Минус — не очевиден AI-контекст: без пояснения звучит как weaving/crafts инструмент.

### Axon
**Аксон** — длинный отросток нейрона, по которому проходит сигнал от одного нейрона к другому.
Технически точно (пакет проводит информацию между агентами), коротко, запоминаемо.
Минус — Axon уже занят: популярный Java-фреймворк для event-driven микросервисов.

### Apex
**Вершина, высшая точка** — прямая метафора «самого главного пакета» экосистемы.
Универсально читается на любом языке, легко произносится. Маркетингово сильное.
Минус — очень широко используется (APEX Oracle, Apex Legends и т.д.), трудно гуглить.

### Aipex
**AI + Apex** — гибридное слово. Мгновенно понятен AI-контекст + смысл «вершины иерархии».
Звучит как продуктовое имя стартапа. Минус — написание неочевидно (aipex vs aipix vs AIpex),
труднее воспринимается на слух.

### Lumex
**Lumen + Memory eXchange** — свет знаний и обмен памятью. Звучит как бренд медтеха или
оптики. Необычно для AI-мира — выделяется. Минус — метафора косвенная, суть пакета не
читается без пояснения. Хорош как название продукта/SaaS, слабее как имя пакета.

---

> **Финальный выбор: `mAInd`** — единственное имя, которое одновременно: (1) мгновенно
> читается как «разум/мозг», (2) содержит **AI** как визуальный маркер, (3) произносится как
> обычное английское слово, (4) нет конфликтов с существующими пакетами в npm/PyPI,
> (5) органично вписывается в экосистему рядом с `brain`, `swissknifeman`.

