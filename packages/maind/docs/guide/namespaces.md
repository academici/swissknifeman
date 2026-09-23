# Namespaces — изоляция связей

Namespace — это **группа проектов**. Внутри группы связи (граф) и память общие; между группами —
изолированы. Один механизм для систем связывания хаба: **maind-граф** (топология между проектами)
и **память** (`agent-memory`).

## Объявление

Проект объявляет членство полем `namespaces` в `config.json` (maind-only, как `tags`):

```jsonc
{ "id": "flexcrm",  "namespaces": ["axioma"] }
{ "id": "azguard",  "namespaces": ["axioma", "*"] }   // ещё и общая инфраструктура
{ "id": "diabox",   "namespaces": ["diabox"] }
{ "id": "legacyapp" }                                  // нет поля → группа default
```

| Значение | Смысл |
|:--|:--|
| нет поля / `[]` | неявный `default` → прежнее поведение (всё связано внутри default) |
| `["axioma"]` | связь только с проектами, у которых тоже есть `axioma` |
| `["*"]` (wildcard) | общая инфраструктура: связывается со ВСЕМИ группами |

Необязательный реестр `namespaces: { axioma: { name, description } }` в `config.json` даёт
метаданные и подсказки на опечатки; членство задаётся в самих проектах.

## Граф: изоляция в точке создания ребра

Межпроектное ребро A↔B строится, **только если A и B делят хотя бы один namespace**
(`namespaces.link_allowed`, применяется в `derive.*`). Поэтому сторы физически не содержат
меж-namespace мостов, и всё ниже (union, индекс, query) изолируется само; `rebuild_index`
дублирует гейт как defense-in-depth.

## Память: бакеты по namespace

Память следует той же модели через scope-бакеты:

| бакет | кто видит |
|:--|:--|
| `project:<id>` | сам проект (приватно) |
| `ns:<имя>` | все проекты группы `<имя>` |
| `global` | вся экосистема (wildcard-инфраструктура + ecosystem-wide) |

`namespaces` управляет связями графа. Память использует отдельный opt-in
`memory_namespaces`; seed и обычный recall остаются в `project:<id>`. Общий `ns:<группа>`
поднимается только явным recall со scope — подробнее → [Память](./memory).

## Команды и пример

```bash
maind namespaces                          # группы и их проекты-члены
maind projects list --namespace axioma    # проекты группы
maind graph --cross --namespace axioma    # межпроектный слой одной группы
maind sync --namespace axioma --only graph,memory   # фан-аут по группе
```

Пример: `flexcrm` и `azguard` в `axioma` — связаны в графе и делят `ns:axioma` память; `diabox`
в своей группе их не видит. `azguard` с `["axioma","*"]` — мост: виден и в `axioma`, и как общая
инфраструктура всем.

## Кэш BRAIN-доков в памяти

Документы проекта (BRD, архитектура, API-контракты и т.п.) можно закэшировать в память maind,
чтобы агент поднимал их через `recall` вместо перечитывания файлов при каждом запросе — экономия
контекста на повторных прогонах. **Команды `maind memory store`/флагов `--key`/`--file` не
существует** — реальная запись в память идёт через `maind memory remember`, у которой только
флаги `--project`|`--scope`, `--share`, `--type`, `--json` (см. `lib/maind/memory.py:_cmd_remember`).
«Ключ» темы документа (`docs:brd`, `docs:architecture`, …) передаётся через `--type`:

```bash
# записать документ как факт с типом-ключом docs:brd
content="$(cat docs-private/dev/BRD.md)"
maind memory remember --scope project:loqum --type docs:brd "$content"

# вспомнить позже (запрос — по смыслу текста, а не точное совпадение ключа)
maind memory recall --scope project:loqum "docs:brd"
```

Обёртка над несколькими документами разом — `packages/maind/scripts/cache-brain-docs.sh`:

```bash
scripts/cache-brain-docs.sh --scope project:loqum \
  docs:brd=docs-private/dev/BRD.md \
  docs:architecture=docs-private/dev/Architecture_Loqum.md
```

Рекомендуемые ключи (`--type`) для проектов с BRAIN-документацией:

| ключ (`--type`) | что кэшируется |
|:--|:--|
| `docs:brd` | требования и цели (BRD) |
| `docs:architecture` | архитектура (C4, компоненты) |
| `docs:api` | API-контракты |
| `docs:glossary` | глоссарий терминов |

Это ручной/скриптовый шаг (не часть `maind onboard`/`sync`) — если понадобится авто-кэширование
на онбординге, это отдельная доработка `provision/onboard.py`, не описанная здесь.

Дальше: [Граф кода (Serena) →](./code-graph)
