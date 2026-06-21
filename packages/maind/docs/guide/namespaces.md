# Namespaces — изоляция связей

Namespace — это **группа проектов**. Внутри группы связи (граф) и память общие; между группами —
изолированы. Один механизм для двух систем связывания хаба: **граф** (`graphify`/топология) и
**память** (`agent-memory`).

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

`seed` пишет cross-ref о связях проекта в его `ns:<имя>` (wildcard → `global`); агент читает
`project:<id>` + `ns:<свои группы>` + `global` (`namespaces.recall_scopes`).

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

Дальше: [graphify (граф кода) →](/guide/code-graph)
