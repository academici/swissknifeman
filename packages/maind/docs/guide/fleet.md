# Fleet — межпроектный слой (оптимизатор)

`maind fleet` — точка входа для агента **межпроектной оптимизации**: across ~N похожих проектов
(общие пакеты-ядро) найти повторяющийся код/схемы и вынести общее в ядро. Сигнал собирается из
**трёх источников** (единого «слитого» графа кода нет и не нужно):

1. **топология** (`manifest`) → *где искать* — кто делит какие пакеты;
2. **дубли** (`duplicates`, движок jscpd) → *что именно* повторяется;
3. **общая память** (`features`/`log`) → *что недавно менялось* — корреляция похожих фич.

Точечную правку даёт [граф кода (Serena)](/guide/code-graph) в нужном проекте. Готовый сценарий —
скилл `cross-project-optimizer`.

## manifest — карта флота

```bash
maind fleet manifest        # JSON: проекты (пути/scopes/code) + shared_packages
```

`shared_packages` — first-party пакеты, которые требуют ≥2 проекта, с консьюмерами и провайдером:

```json
{ "package": "package:axioma-studio/azguard-core", "name": "azguard-core",
  "provider": "azguard", "consumers": ["azguard", "corex", "flexcrm"], "consumer_count": 3 }
```

Это готовые **группы оптимизации**: улучшение в общем пакете влияет на всех его консьюмеров.

## duplicates — кросс-проектные дубли (jscpd)

```bash
maind fleet duplicates --group azguard-core --min-tokens 60 [--json]   # по консьюмерам пакета
maind fleet duplicates --projects flexcrm,shop,crm [--json]            # по явному списку
```

Обёртка над [jscpd](https://github.com/kucherenko/jscpd) (через `npx`, language-agnostic).
Кросс-проектные клоны (`cross_project: true`) — первыми. Нужен Node.js/`npx` (первый запуск
ставит пакет).

**Игноры по умолчанию:** `**/vendor/**, **/node_modules/**, **/packages/**` — ориентированы на
**проекты-приложения** (исходник в `app/`/`src/`, а `packages/` у консьюмера — это симлинки на
другие проекты, их сканировать не надо). Для **пакета-монорепо** (исходник в `packages/*`)
переопредели игнор: `--ignore "**/vendor/**,**/node_modules/**"`. Порог — `--min-tokens` (меньше →
больше шума), паттерн — `--pattern` (дефолт `**/*.php`).

::: tip Дубли — кандидаты, не приговор
Похожий код бывает оправдан (разные предметные области). Решение о выносе — по смыслу (через
Serena), а не только по jscpd.
:::

## similar — семантически похожий код (эмбеддинги)

```bash
maind fleet similar --group azguard-core --threshold 0.85 [--json]
```

Поверх литеральных дублей jscpd: извлекает функции/классы по сгруппированным путям, эмбеддит их
**внешним** бэкендом и ищет кросс-проектные пары «похоже по смыслу, не дословно». Бэкенд —
pluggable через `code_graph.embed.command` в `.maind.json` (внешний инструмент `текст→вектор`,
плейсхолдеры `{input}`/`{output}`):

```jsonc
"code_graph": { "embed": { "command": ["my-embedder", "--in", "{input}", "--out", "{output}"] } }
```

Не настроен бэкенд → внятный `die` (доступен только `duplicates`). Извлечение чанков и
косинус-сравнение — на stdlib; эмбеддинг — внешний (как jscpd). MVP, развивается.

## features / log — корреляция фич через общую память

```bash
maind fleet log "добавил импорт CSV" --project flexcrm     # факт в ns:<группа> + global + приватный
maind fleet features --namespace axioma                    # факты группы: что где меняли
```

Маркер `maind:feature-log`. Агент-оптимизатор `recall`-ит их и замечает похожие изменения в разных
проектах → кандидат на общий хелпер. Требует поднятой [памяти](/guide/memory).

## Что уже есть, а что новое

| Кирпич | Откуда |
|:--|:--|
| перечислить проекты + пути | реестр `.maind.json` |
| доступ ко всем репозиториям | workspace-доверие хаба ([workspace](/guide/workspace)) |
| группы по общим пакетам | maind-граф топологии ([федерация](/guide/federation)) |
| корреляция фич | общая память + namespaces |
| **детектор дублей (jscpd)** | **новое** — `maind fleet duplicates` |

Дальше: [граф кода →](/guide/code-graph) · [Память →](/guide/memory)
