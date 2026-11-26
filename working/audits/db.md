**Главный подтверждённый кандидат на рефакторинг — `planner.plan.store`: в нём одновременно находятся модель плана, поиск проекта, привязка checkout, файловый layout, блокировки, валидация, сериализация, запись и журнал событий. Именно разделение этих ответственностей даст больше пользы, чем простое переименование папок.** Это видно непосредственно из реализации [`store.py`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py).

Ниже — предметный разбор SwissKnifeMan без сравнений с другими продуктами: конкретные места, возможные ошибки, Python-приёмы, варианты структуры и последовательность изменений. **Важная граница:** целиком прочитан `store.py`, проверены текущая ревизия и состав каталогов Planner/Orch; содержимое остальных модулей в этой итерации не прочитано полностью, поэтому предложения по ним отделены от подтверждённых дефектов.

# Рефакторинг SwissKnifeMan

## Основание разбора

Репозиторий зафиксирован на коммите **`1603bfd8c988cf04505af55462c1596b5d82fde5`**. Последний коммит ограничивает unit rework rounds, обрабатывает manual checks без verdict как `MANUAL_PENDING` и включает изменение чтения machine-layer настроек hooks. Эти изменения нельзя потерять при перестройке кода. [Зафиксированный коммит](https://github.com/academici/swissknifeman/commit/1603bfd8c988cf04505af55462c1596b5d82fde5)

В Planner есть крупные модули: `lifecycle.py` — 80 207 байт, `check.py` — 56 659, `cli.py` — 52 499, `_types.py` — 33 501, `gitops.py` — 30 431. Это **размеры файлов, не количество строк и не доказательство плохого качества**, но полезные ориентиры для следующей декомпозиции. [Каталог `planner/plan`](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan)

В Orch уже есть отдельные `port.py`, `effects.py`, `events.py`, `journal.py`, `retry.py`, `worksource.py`, `worksource_file.py`, а также каталоги `bindings` и `conductor`. Поэтому вводить новые слои нужно после проверки существующих контрактов, а не создавать рядом второй аналогичный framework. [Каталог Orch](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/orch/lib/orch)

### Обозначения

- **Подтверждено:** конструкция непосредственно присутствует в прочитанном коде.
- **Сценарий риска:** из конструкции следует возможное нежелательное поведение; полный путь до пользовательской команды ещё требует проверки.
- **Предложение:** новый код или структура, а не описание уже существующей реализации.
- **Тест-предложение:** сценарий, который следует добавить; здесь он не запускался.

Это важно: отсутствие локальной проверки внутри функции ещё не означает, что внешний CLI обязательно позволяет её обойти.

***

## Что сохранить

Перед критикой — полезные свойства, которые уже реализованы.

В `save_many()` сначала валидируются и подготавливаются все документы, и только потом начинаются записи; новые значения `updated_at` применяются к переданным словарям после успешной записи. Это правильная последовательность, которую нужно сохранить при выделении persistence layer. [`store.py` · `save_many`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Файловая запись уже использует временный файл рядом с целевым, `flush`, `fsync`, `os.replace` и попытку синхронизации каталога. Не нужно заменять этот код простым `Path.write_text()` ради уменьшения количества строк. [`store.py` · `_stage`, `atomic_write`, `_sync_dir`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Также присутствуют защита от повторного захвата plan lock тем же потоком, запрет записи в старую копию мигрированных планов и диагностическое чтение повреждённых документов через `problems`. Это полезное поведение, а не «лишняя сложность», которую следует удалить. [`store.py` · `PlanLock`, `_guard_migrated`, `load_plan`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

**Цель рефакторинга: сохранить эти гарантии, но сделать их локальными, проверяемыми и не связанными со всеми остальными задачами модуля.**

***

## Карта подтверждённых находок

| ID | Место | Что требует изменения | Приоритет |
|---|---|---|---|
| RF-01 | `Plan.adopt` + `cached_property` | Возможен устаревший cached `source_root` | Высокий |
| RF-02 | `append_log(lock=...)` | Проверяется `held`, но не соответствие lock нужному плану | Высокий |
| RF-03 | `resolve_plan_dir` | Разные ветви разрешения имеют разную локальную проверку scope | Высокий |
| RF-04 | `load_plan` | Чтение нескольких файлов не создаёт согласованный snapshot само по себе | Высокий |
| RF-05 | `save_many` | Последовательные `replace` — не crash-atomic multi-document commit | Высокий |
| RF-06 | `save_many` + `append_log` | State и event не объединены одной операцией commit | Высокий для durable execution |
| RF-07 | `Plan` | Смешаны данные, размещение и checkout discovery | Архитектурный |
| RF-08 | `Plan.path` | Строковый `kind` и optional `key` допускают некорректные комбинации | Средний |
| RF-09 | `Plan` dictionaries | Чтение с ошибками и пригодная для мутации модель имеют один тип | Средний |
| RF-10 | `_write_all`, `_stage` | Ошибка cleanup способна затруднить диагностику исходной ошибки | Средний |
| RF-11 | `_write_all` rollback | Ошибки восстановления игнорируются без отдельного результата восстановления | Средний |
| RF-12 | `now`, warning globals, discovery | Скрытые process/environment dependencies | Средний |
| RF-13 | `log_lines`, short-ID lookup | Полное чтение журнала и сканирование планов | По измерениям |
| RF-14 | `canonical_dump` | Форматирование и криптографическая canonicalization не следует смешивать | На границе новой модели |
| RF-15 | весь `store.py` | Слишком много владельцев изменений в одном модуле | Архитектурный |

Все перечисленные конструкции находятся в прочитанном [`store.py`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py). Ниже — различия между непосредственно наблюдаемым кодом и условиями, при которых он создаёт проблему.

***

# Конкретные места в коде

## RF-01: устаревающий cache

### Что находится сейчас

`Plan.source_root` — `cached_property`, а `Plan.adopt()` обновляет `self.__dict__` содержимым другого snapshot. [`store.py` · `Plan.source_root`, `Plan.adopt`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

**Сценарий риска:** если у старого объекта `source_root` уже вычислен, а у нового — ещё нет, обновление словаря новым объектом не удаляет старое cached значение. Следовательно, `adopt()` не гарантирует замену всего вычисленного состояния. Это вывод из реализации, не результат запущенного теста. [`store.py`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Вариант A: локальное исправление

После обновления явно инвалидировать cache:

```python
def adopt(self, other: "Plan") -> None:
    self.root = other.root
    self.plan = other.plan
    self.brief = other.brief
    self.phases = other.phases
    self.items = other.items
    self.decisions = other.decisions
    self.units = other.units
    self.documents = other.documents
    self.problems = other.problems

    self.__dict__.pop("source_root", None)
```

Это **предлагаемый патч**, но в нём остаётся проблема разделяемых mutable dictionaries.

### Вариант B: заменить объект

Предпочтительнее:

```python
updated_plan = repository.load(plan_id)
```

вместо:

```python
old_plan.adopt(updated_plan)
```

Тогда не нужно синхронизировать внутреннее состояние старого объекта.

### Вариант C: убрать discovery из модели

Лучший целевой вариант:

```python
@dataclass(frozen=True, slots=True)
class PlanSnapshot:
    plan_id: str
    specification: "PlanSpecification"


class CheckoutResolver:
    def resolve(self, project_id: str) -> "CheckoutBinding | None":
        ...
```

`source_root` больше не кэшируется внутри плана: это отдельный результат разрешения окружения.

### Тест-предложение

```text
1. Загрузить snapshot A.
2. Обратиться к A.source_root.
3. Получить snapshot B с другим binding context.
4. Не обращаться к B.source_root.
5. Выполнить A.adopt(B).
6. Проверить, что старый source_root не сохранился.
```

**Выбор:** A — быстрый hotfix, B — хороший промежуточный шаг, C — правильная граница следующей версии.

***

## RF-02: lock не привязан к операции

### Что находится сейчас

`append_log()` при переданном `lock` проверяет только `lock.held`. Локальной проверки, что lock относится именно к `plan_dir`, в этой функции нет. [`store.py` · `append_log`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Это означает, что интерфейс допускает ошибочное использование:

```text
удерживается lock плана A;
append_log вызывается для плана B;
проверка held проходит.
```

Это **подтверждённая слабость контракта**, но не доказательство, что существующие callers уже так делают. [`store.py` · `PlanLock`, `append_log`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Минимальный вариант

Добавить:

```python
lock.assert_owned_for(plan_dir)
```

Проверять:

- Lock удерживается.
- Он относится к этому плану.
- Используется тем же владельцем исполнения.
- Объект не закрыт.

### Более сильный вариант

Не передавать raw lock вообще:

```python
with store.write_session(plan_id) as session:
    session.save_documents(changes)
    session.append_event(event)
```

Тогда у `append_event()` нет отдельного `plan_dir`: сессия уже связана с одним планом.

### Предлагаемые классы

```text
PlanLock
  технический механизм взаимного исключения

PlanWriteSession
  scoped интерфейс операций над одним планом

PlanCommit
  набор state changes + events

FilesystemCommitter
  физическое применение commit
```

Это не четыре обязательных больших класса. Первоначально `PlanWriteSession` может быть небольшим объектом вокруг существующих функций.

### Тест-предложение

```text
with lock(A):
    append event to B

Ожидание:
  немедленная ошибка до записи.
```

Ещё один:

```text
lock захвачен в потоке A;
используется как доказательство владения в потоке B.

Ожидание:
  отказ или явно документированная поддерживаемая семантика.
```

***

## RF-03: неодинаковая проверка путей

### Что находится сейчас

В `resolve_plan_dir()` ветка, распознавшая непосредственно существующий путь, вызывает `require_project_plans()`. В ветке поиска через `parent / ref` такой локальной проверки нет. [`store.py` · `resolve_plan_dir`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Поскольку `ref` здесь — произвольная строка, безопасный контракт должен явно различать ID, short ID и path. Сейчас это разделение выполняется эвристически. [`store.py` · `resolve_plan_dir`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Чего не утверждаю

Это не доказанный end-to-end обход доступа: внешняя команда может проверять аргументы раньше.

Но **сам resolver не обеспечивает одинаковую проверку каждого возвращаемого результата**.

### Вариант A: один выход

```python
def resolve_plan_dir(...):
    candidate = find_candidate(...)
    enforce_project_scope(candidate)
    return candidate
```

Правило:

> Ни один успешный branch не возвращает результат до общей проверки.

### Вариант B: типизированный reference

```python
@dataclass(frozen=True, slots=True)
class PlanIdRef:
    value: str


@dataclass(frozen=True, slots=True)
class PlanAliasRef:
    value: str


@dataclass(frozen=True, slots=True)
class PlanPathRef:
    path: Path
```

CLI преобразует строку в один из этих объектов. Внутри domain/application уже нет «строка может означать что угодно».

### Вариант C: разные команды

```text
plan show PLAN7
plan show --id <stable-id>
plan import --path <directory>
```

Для серверного API path reference вообще не нужен.

### Проверки

- `..` в ID не принимается как ID.
- Абсолютный путь не принимается как alias.
- Любая path-ветка проходит scope enforcement.
- Symlink проверяется по выбранной политике.
- Ошибка неоднозначности не заменяется выбором первого результата.

Проверка через `resolve()` полезна, но сама по себе не решает все filesystem races. Для операций с недоверенными путями нужен отдельный threat model.

***

## RF-04: snapshot не обязательно согласован

### Что находится сейчас

`load_plan()` последовательно читает plan, brief, phases, items, units, decisions и documents; внутри функции read lock не берётся. [`store.py` · `load_plan`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

**Сценарий риска:** если writer между этими чтениями обновляет несколько файлов, reader способен получить смесь старого и нового состояния. Атомарная замена отдельного файла не делает атомарным чтение всего каталога. Это условие необходимо проверить по callers и concurrency tests. [`store.py` · `load_plan`, `_write_all`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Вариант A: общий lock на чтение

Наиболее простой первый шаг:

```text
reader:
  получить plan lock;
  прочитать все документы;
  отпустить lock.
```

Плюсы:

- Небольшой объём изменений.
- Понятная семантика.
- Можно быстро покрыть тестами.

Минусы:

- Readers конкурируют с writer.
- Длинное чтение удерживает lock.
- Нужно не получить вложенный захват уже удерживаемого lock.

Поэтому нужны два уровня:

```text
load_consistent()
_load_unlocked()
```

Публичный и внутренний, с чёткими правилами использования.

### Вариант B: immutable generation

```text
CURRENT → generation-42

generation-42:
  полный согласованный набор документов
```

Reader сначала фиксирует generation и читает только её.

### Вариант C: transactional database

Snapshot формируется внутри read transaction.

**Для ближайшего рефакторинга я бы выбрал A.** Generations или SQL — отдельная смена persistence semantics, а не обязательная часть первого разбиения `store.py`.

***

## RF-05: multi-file save не равен transaction

### Что находится сейчас

`_write_all()` сначала создаёт временные файлы, затем последовательно выполняет `os.replace`; при исключении пытается восстановить уже заменённые файлы. Это аккуратная best-effort обработка ошибок процесса, но не единый crash-atomic commit группы файлов. [`store.py` · `_write_all`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Где реальная граница

```text
Python exception:
  код rollback может выполниться.

Процесс принудительно завершён:
  rollback не выполняется.

Сбой хоста:
  rollback не выполняется.
```

Поэтому функцию нужно описывать точно.

### Вариант A: честное имя

```text
ValidatedBatchWriter
```

или:

```text
BestEffortBatchWriter
```

Не называть её полноценным transaction manager.

### Вариант B: commit manifest

```text
commit prepared
  → files staged
  → commit marker
  → recovery completes/reverts
```

Но этот вариант требует:

- Долговечного журнала.
- Recovery при запуске.
- Определённой последовательности sync.
- Тестов каждого crash point.

Один файл `transaction.json` сам по себе проблему не решает.

### Вариант C: заменить persistence

Если следующим шагом уже предусмотрена SQLite, разумнее вложить усилия в repository/UoW boundary, а не писать собственную файловую СУБД.

**Рекомендация:** сейчас — зафиксировать гарантию и тесты; затем — единый transaction contract с несколькими реализациями.

***

## RF-06: state и event живут отдельно

### Что находится сейчас

`save_many()` меняет документы, а `append_log()` отдельно дописывает JSONL и синхронизирует файл. API модуля не объединяет эти действия в одну атомарную операцию. [`store.py` · `save_many`, `append_log`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Нежелательные исходы

```text
state изменился;
event не записался.
```

или:

```text
event есть;
соответствующее изменение не завершено.
```

Наличие plan lock предотвращает часть конкурентных конфликтов, но не объединяет разные filesystem operations в crash-atomic commit.

### Целевая операция

```python
commit = PlanCommit(
    expected_version=version,
    changes=changes,
    events=events,
    command_id=command_id,
)

repository.commit(commit)
```

В application layer:

```text
одна command
  → один логический commit
```

### Важное ограничение интерфейса

Нельзя написать абстракцию:

```python
with transaction():
    save()
    append_log()
```

и оставить внутри старые независимые записи.

Название `transaction` не создаёт гарантии. Реализация должна либо обеспечивать заявленную семантику, либо явно сообщать ограничение.

***

## RF-07: модель знает слишком многое

### Что находится сейчас

`Plan` хранит JSON dictionaries, `root`, вычисляет document paths, разрешает source checkout, учитывает текущую директорию и launcher context, а также может выдать `CHECKOUT_BINDING_MISMATCH`. [`store.py` · `Plan`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Это смешивает три независимые сущности:

```text
что представляет собой план;
где он хранится;
какой checkout сейчас доступен.
```

### Предлагаемая декомпозиция

```text
PlanSnapshot
  данные

PlanLocator
  где искать данные

PlanRepository
  как загрузить/сохранить

ProjectContext
  какой проект выбран

CheckoutBinding
  где исходный код

CheckoutResolver
  как найти binding
```

Не обязательно делать все шесть сущностей классами с десятками методов.

Например:

```python
@dataclass(frozen=True, slots=True)
class CheckoutBinding:
    project_id: str
    repository_id: str
    root: Path
```

`CheckoutResolver` может сначала быть обычной функцией.

### Что меняется в использовании

Плохо:

```python
run_checks(plan.repo_root, plan.items)
```

Лучше:

```python
checkout = checkout_resolver.require(project_id)
run_checks(checkout, check_request)
```

Теперь из сигнатуры видно, что проверке нужен checkout, а чтению плана — нет.

### Не стоит делать

```python
class Plan:
    @property
    def database(self): ...

    @property
    def api(self): ...

    @property
    def runtime(self): ...
```

Это только увеличит объект-всезнайку.

***

## RF-08: некорректные состояния в сигнатуре

### Что находится сейчас

`Plan.path(kind: str, key: str | None = None)` допускает комбинации вроде `kind="item", key=None`; unit reference разбирается regex, после чего match используется без отдельной проверки неуспеха. [`store.py` · `Plan.path`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

В результате ошибочный reference способен превратиться в техническую ошибку операций с `None`, а не в предметный `PlanError`.

### Вариант A: отдельные функции

Самое простое:

```python
layout.plan_path()
layout.brief_path()
layout.item_path(item_id)
layout.unit_path(item_id, unit_id)
```

Здесь невозможно забыть key для item без явной ошибки вызова.

### Вариант B: typed references

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ItemRef:
    item_id: str
    kind: Literal["item"] = "item"


@dataclass(frozen=True, slots=True)
class UnitRef:
    item_id: str
    unit_id: str
    kind: Literal["unit"] = "unit"
```

Тогда:

```python
def path_for(ref: ItemRef | UnitRef) -> Path:
    match ref:
        case ItemRef(item_id=item_id):
            ...
        case UnitRef(item_id=item_id, unit_id=unit_id):
            ...
```

### Вариант C: перегрузки

Можно оставить единый метод и добавить `@overload`, но runtime validation всё равно понадобится.

**Мой выбор:** A для filesystem adapter, B для ссылок между слоями. Перегрузки ради сохранения неудачной универсальной функции менее полезны.

***

## RF-09: diagnostic load и command load

### Что находится сейчас

`load_plan()` собирает ошибки в `problems`; отсутствующий или непрочитанный документ может быть представлен пустым словарём. Это полезно для диагностики повреждённого плана, но получившийся объект имеет тот же тип `Plan`, что и нормальный snapshot. [`store.py` · `_read_json`, `load_plan`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Основная проблема

Функция мутации по типу аргумента не понимает:

```text
передан проверенный план
```

или:

```text
частично загруженный набор документов для recovery.
```

### Предлагаемое разделение

```python
@dataclass(frozen=True, slots=True)
class LoadProblem:
    document: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PlanInspection:
    documents: "RawPlanDocuments"
    problems: tuple[LoadProblem, ...]
```

И разные операции:

```python
inspection = repository.inspect(plan_ref)

snapshot = repository.load_validated(plan_ref)
```

### Семантика

```text
inspect:
  максимально собрать доступные данные;
  вернуть findings;
  ничего не менять.

load_validated:
  либо пригодный snapshot;
  либо типизированная ошибка.
```

### Почему не просто `strict=True`

Флаг допустим как промежуточный шаг:

```python
load_plan(ref, strict=True)
```

Но два разных имени лучше выражают назначение и уменьшают риск случайного использования diagnostic object в command path.

***

## RF-10: cleanup не должен затмить ошибку

### Что находится сейчас

В `_write_all()` и `_stage()` есть удаление временных файлов в cleanup paths; `unlink()` в этих местах может само завершиться исключением. При неудачном сочетании ошибок это способно затруднить диагностику исходного сбоя. [`store.py` · `_write_all`, `_stage`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Предлагаемый приём

Разделить:

```text
primary failure
rollback failures
cleanup failures
```

Например:

```python
@dataclass(frozen=True, slots=True)
class CleanupFailure:
    path: Path
    message: str
```

Успешно выполненный cleanup не требует сообщения. Неуспешный — записывается как secondary diagnostic.

### Что использовать в Python

- `contextmanager` для одного ресурса.
- `ExitStack` для динамического набора ресурсов.
- Отдельные cleanup callbacks.
- `try/finally` с сохранением первичной ошибки.
- При поддерживаемой версии Python — notes к исключению для дополнительных сведений.

### Чего не делать

```python
with suppress(Exception):
    cleanup()
```

по всему коду.

Так можно скрыть неправильный path, сломанный invariant или программную ошибку.

Подавлять нужно только ожидаемые ошибки конкретной cleanup operation, сохраняя диагностическую информацию.

***

## RF-11: восстановление — отдельный результат

### Что находится сейчас

При rollback `_write_all()` игнорирует `OSError` восстановления, чтобы сообщить исходную ошибку. Это разумный приоритет primary failure, но caller не получает структурированного описания того, какие файлы не удалось восстановить. [`store.py` · `_write_all`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Предлагаемая ошибка

```python
class CommitFailed(Exception):
    def __init__(
        self,
        *,
        message: str,
        recovery_required: bool,
        affected_documents: tuple[str, ...],
    ) -> None:
        super().__init__(message)
        self.recovery_required = recovery_required
        self.affected_documents = affected_documents
```

### Ожидаемое поведение

```text
запись не удалась;
rollback полностью успешен:
  operation failed, state restored.

запись не удалась;
rollback частично неуспешен:
  recovery_required;
  список затронутых документов;
  дальнейшие мутации блокируются до проверки.
```

Не обязательно сразу делать сложный recovery framework.

Но caller должен отличать:

```text
ничего не изменилось
```

от:

```text
состояние может быть частично изменено.
```

***

## RF-12: скрытое окружение

### Что находится сейчас

`store.py` обращается к текущей директории, launcher context, workspace markers, process-global флагу `_LEGACY_WARNED` и глобальной функции времени `now()`. [`store.py` · discovery functions, `Plan.source_root`, `_warn_legacy_present`, `now`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

### Почему это усложняет код

Одинаковый вызов:

```python
open_plan("PLAN7")
```

может зависеть от:

```text
cwd;
launcher;
machine bindings;
markers;
состояния process globals.
```

Для пользовательского CLI discovery нормально. Для domain/application оно должно завершиться до вызова сценария.

### Предлагаемая граница

```text
CLI
  → resolve invocation context
  → choose project
  → construct services
  → execute explicit command
```

После composition:

```python
service.show_plan(
    project_id=project_id,
    plan_ref=plan_ref,
)
```

не ищет проект самостоятельно.

### Clock

Вместо patch глобального `now`:

```python
class Clock(Protocol):
    def now(self) -> datetime:
        ...
```

Для маленького модуля достаточно callable:

```python
clock: Callable[[], datetime]
```

Не нужен обязательный `SystemClockFactoryProvider`.

### Warnings

Вместо `print(stderr)` из persistence:

```python
@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
```

CLI печатает его, API возвращает в diagnostics, GUI отображает.

**Но audit events и diagnostics — разные сущности.** Предупреждение о legacy folder не нужно автоматически превращать в доменное событие плана.

***

## RF-13: журнал и discovery

### Что находится сейчас

`log_lines()` читает весь `log.jsonl` через `read_text()`, затем разбивает его на строки и собирает список; `read_log()` создаёт ещё один список событий. Поиск short ID сканирует plan directories и читает их `plan.json`. [`store.py` · `log_lines`, `read_log`, `resolve_plan_dir`, `short_id_of`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Это не обязательно проблема на текущем объёме данных. Но это конкретные места, где масштабирование может увеличить память и latency.

### Простой рефакторинг журнала

```python
def iter_log_records(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            yield parse_log_record(line_number, line)
```

Это пример нового кода; production version должна определить политику для незавершённой последней строки.

Совместимость:

```python
def read_log(...):
    return list(iter_log_records(...))
```

Consumers, которым нужен stream, больше не обязаны читать всё.

### Что не делать преждевременно

Не добавлять custom binary log, mmap и отдельный индекс без измерений.

Сначала:

- Размеры журналов.
- Время чтения.
- Максимальная память.
- Частота повторного чтения.
- Доля запросов «последние N».

### Short-ID index

Если измерения покажут проблему, alias index должен находиться в repository, а не в GUI cache.

Он должен:

- Перестраиваться.
- Обнаруживать collisions.
- Не становиться вторым independently editable источником истины.

***

## RF-14: canonical — неоднозначное слово

### Что находится сейчас

`canonical_dump()` упорядочивает ключи согласно schema properties, сериализует UTF-8 JSON с отступами и newline. `_order()` обрабатывает schema references и ветви `oneOf`. [`store.py` · `canonical_dump`, `_order`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Это полезная **стабильная форма представления для файлов**.

Но её не нужно без отдельного контракта использовать как:

```text
криптографическую идентичность спецификации;
формат подписи;
универсальный semantic digest.
```

### Предлагаемые имена

```text
SchemaOrderedJsonFormatter
  читабельное файловое представление

SpecificationDigest
  строго определённая идентичность содержимого
```

### Важная граница

```python
formatted_text = formatter.format(document)
digest = digester.digest(specification)
```

Разные назначения — разные contracts.

Если сейчас digest не нужен, второй компонент не создаётся.

### Что проверить отдельно

В Planner существует `_jsonschema_core.py`, а также отдельные `schema.py` и `_types.py`. По одному наличию файлов нельзя утверждать дублирование validation logic; это отдельный обязательный участок следующего чтения. [Каталог Planner](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan)

***

# Python-приёмы по назначению

## Функции раньше классов

Сейчас главная опасность — заменить «мясо из функций» на «мясо из сервисов».

Не нужно автоматически превращать:

```python
validate_dependency_graph(...)
```

в:

```python
class DependencyGraphValidationService:
    def execute(self, ...):
        ...
```

Если нет состояния и нескольких реализаций, функция обычно достаточна.

### Практическое правило

| Задача | Предпочтительная форма |
|---|---|
| Чистая проверка | Функция |
| Чистое преобразование | Функция |
| Набор связанных значений | Dataclass |
| Внешний ресурс | Context manager / adapter |
| Несколько взаимозаменяемых реализаций | Protocol |
| Долгоживущий объект с ресурсами | Небольшой класс |
| Сценарий с несколькими dependencies | Handler-функция или небольшой service |
| Глобальный mutable registry | По возможности убрать |

### Когда класс оправдан

```python
class FilesystemPlanRepository:
    def __init__(
        self,
        *,
        root: Path,
        loader: PlanLoader,
        committer: PlanCommitter,
    ) -> None:
        ...
```

У него есть связанная конфигурация и устойчивый public contract.

### Когда нет

```python
class UppercasePlanTitleService:
    def execute(self, title: str) -> str:
        return title.upper()
```

Это архитектурный шум.

***

## Dataclass без иллюзий

Для value objects предлагаю:

```python
@dataclass(frozen=True, slots=True)
class PlanId:
    value: str
```

Но не нужно создавать wrapper для каждой строки.

Осмысленные кандидаты:

```text
PlanId
RevisionId
ProjectId
UnitRef
ExpectedVersion
DocumentRef
CheckoutBinding
```

### Важное ограничение

Такой объект:

```python
@dataclass(frozen=True)
class Snapshot:
    items: dict[str, dict]
```

не становится deeply immutable: содержимое `items` всё ещё можно изменить.

Если нужна неизменяемая domain model:

- Использовать tuples вместо списков.
- Не отдавать mutable dictionaries наружу.
- Применять typed nested records.
- Либо честно считать объект mutable и управлять изменениями через application.

### Не нужно всё типизировать сразу

Первый безопасный шаг:

```text
typed command
typed result
typed identifier
typed error
```

После этого — typed internal model.

Иначе перевод большого JSON-дерева в классы одновременно с переносом storage станет слишком большим изменением.

***

## Protocol вместо общей базы

Не рекомендую:

```python
class BaseStorage:
    ...
```

с десятками optional методов.

Предпочтительнее:

```python
class PlanReader(Protocol):
    def load(self, plan_id: str) -> PlanSnapshot:
        ...


class PlanCommitter(Protocol):
    def commit(self, change: PlanCommit) -> CommitResult:
        ...
```

### Почему два интерфейса

Consumer, который только читает план, не получает write API.

Это особенно полезно для:

```text
GUI queries;
read-only MCP tools;
inspection commands;
export;
analytics.
```

### Не дробить бесконечно

Не надо превращать каждый метод в отдельный port.

Достаточно разделять по реальным потребителям и внешним границам.

### Без service locator

Плохо:

```python
def finish_unit(...):
    repository = Services.get("repository")
    clock = Services.get("clock")
```

Лучше:

```python
def finish_unit(
    command: FinishUnit,
    *,
    repository: PlanRepository,
    clock: Clock,
) -> FinishUnitResult:
    ...
```

Из сигнатуры видны зависимости.

***

## Pure core, imperative shell

Это наиболее полезный паттерн для текущей задачи.

### Чистое ядро

```python
def decide_next_state(
    current: UnitState,
    result: AttemptResult,
    policy: ReviewPolicy,
) -> TransitionDecision:
    ...
```

Не делает:

```text
read file;
write file;
run subprocess;
print;
read cwd;
send request;
get current time.
```

### Оболочка

```python
def handle_attempt_result(command, dependencies):
    current = dependencies.repository.load(...)
    decision = decide_next_state(...)
    dependencies.repository.commit(...)
```

### Польза именно для SKM

Можно отдельно тестировать:

```text
manual pending;
review rejected;
rework exhausted;
stale attempt;
blocked dependency;
accepted deviation.
```

без подготовки папок, Git repository и fake provider process.

Последний коммит уже содержит важные правила по manual pending и rework limit; при рефакторинге их стоит сначала закрепить именно такими isolated tests. [Коммит](https://github.com/academici/swissknifeman/commit/1603bfd8c988cf04505af55462c1596b5d82fde5)

***

## Типизированные результаты

Не рекомендую возвращать из одной функции:

```text
None;
False;
строку ошибки;
словарь;
Path.
```

Это общий принцип предлагаемого кода, а не утверждение, что конкретная непрочитанная функция SKM уже так делает.

### Вариант A: exceptions

Для ошибок команды:

```python
class VersionConflict(Exception):
    ...
```

Успешный return остаётся одного типа.

### Вариант B: discriminated result

Для ожидаемых workflow outcomes:

```python
@dataclass(frozen=True, slots=True)
class Ready:
    task_id: str


@dataclass(frozen=True, slots=True)
class WaitingForManualCheck:
    check_id: str


@dataclass(frozen=True, slots=True)
class Blocked:
    reasons: tuple[str, ...]
```

```python
ReadinessResult = Ready | WaitingForManualCheck | Blocked
```

### Где что применять

| Ситуация | Форма |
|---|---|
| Файл повреждён | Typed exception / diagnostic finding |
| Ожидается человек | Workflow outcome |
| Зависимость не завершена | Workflow outcome |
| Неверный аргумент API | Validation error |
| Неожиданная программная ошибка | Exception |
| Нет capability | Explicit unsupported outcome |

**Ожидание человека не должно выглядеть как авария процесса.**

***

## Явные ошибки

Текущий `PlanError` уже используется с предметными кодами вроде `PLAN_NOT_FOUND`, `PLAN_LOCKED`, `SCHEMA_INVALID`, `PLAN_SOURCE_UNBOUND`. Это хороший фундамент для стабильного error contract. [`store.py`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Предлагаю постепенно привести ошибки к форме:

```python
@dataclass(frozen=True, slots=True)
class ErrorDetails:
    code: str
    message: str
    target: str | None = None
    retryable: bool = False
```

Но не превращать все exceptions в одну потерявшую traceback структуру.

### Перевод ошибок

```text
adapter:
  OSError / database error

application:
  StorageUnavailable / VersionConflict

entrypoint:
  CLI exit code / HTTP status / MCP error
```

В CLI должно быть единое место отображения:

```text
красивый текст;
machine-readable JSON;
traceback в debug mode.
```

Domain не выбирает exit code.

***

# Законченный пример разреза

Следующий код — **новый эскиз**, а не копия из репозитория. Он показывает, как чистое решение отделить от persistence.

## Модель и правило

```python
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class Draft:
    draft_id: str
    title: str
    edit_version: int


@dataclass(frozen=True, slots=True)
class RenameDraft:
    draft_id: str
    title: str
    expected_version: int


class InvalidTitle(ValueError):
    pass


class VersionConflict(RuntimeError):
    pass


def rename_draft(
    current: Draft,
    command: RenameDraft,
) -> Draft:
    if current.edit_version != command.expected_version:
        raise VersionConflict("Draft has changed")

    title = command.title.strip()
    if not title:
        raise InvalidTitle("Title must not be empty")

    if title == current.title:
        return current

    return replace(
        current,
        title=title,
        edit_version=current.edit_version + 1,
    )
```

Здесь нет:

```text
Path;
SQL;
JSON;
cwd;
print;
subprocess;
provider.
```

## Application contract

```python
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class DraftRenamed:
    draft_id: str
    title: str
    edit_version: int
    occurred_at: datetime


class DraftRepository(Protocol):
    def get(self, draft_id: str) -> Draft:
        ...

    def save(
        self,
        draft: Draft,
        *,
        expected_version: int,
    ) -> None:
        ...


class EventWriter(Protocol):
    def append(self, event: DraftRenamed) -> None:
        ...


class DraftUnitOfWork(Protocol):
    drafts: DraftRepository
    events: EventWriter

    def commit(self) -> None:
        ...


UnitOfWorkFactory = Callable[
    [],
    AbstractContextManager[DraftUnitOfWork],
]
```

## Handler

```python
def handle_rename_draft(
    command: RenameDraft,
    *,
    uow_factory: UnitOfWorkFactory,
    clock: Callable[[], datetime],
) -> Draft:
    with uow_factory() as uow:
        current = uow.drafts.get(command.draft_id)
        updated = rename_draft(current, command)

        if updated is current:
            return current

        uow.drafts.save(
            updated,
            expected_version=current.edit_version,
        )

        uow.events.append(
            DraftRenamed(
                draft_id=updated.draft_id,
                title=updated.title,
                edit_version=updated.edit_version,
                occurred_at=clock(),
            )
        )

        uow.commit()
        return updated
```

### Что здесь существенно

- Domain проверяет expected version для понятной ошибки.
- Persistence **тоже** выполняет conditional update: одной проверки в памяти недостаточно.
- State и event входят в одну UoW.
- Clock подставляется.
- No-op не создаёт лишнее изменение.
- После commit возвращается новый объект.
- Rollback/close — обязанность context manager.

### Что не входит в пример

- Idempotency receipt.
- Authorization.
- Audit.
- Реализация filesystem transaction.
- SQL mapping.
- Полная draft specification.

Их нельзя считать автоматически реализованными из-за наличия интерфейсов.

***

# Варианты организации проекта

## Вариант A: бережное разделение

**Наиболее практичный первый этап.** Сохранить существующие packages и public imports, разделив крупные внутренние модули.

```text
packages/
└── planner/
    └── lib/
        └── planner/
            └── plan/
                ├── __init__.py
                ├── store.py
                │
                ├── domain/
                │   ├── identifiers.py
                │   ├── snapshot.py
                │   ├── transitions.py
                │   └── errors.py
                │
                ├── application/
                │   ├── commands/
                │   │   ├── rename.py
                │   │   ├── start.py
                │   │   └── complete.py
                │   ├── queries/
                │   │   ├── show.py
                │   │   └── readiness.py
                │   └── ports.py
                │
                ├── persistence/
                │   └── filesystem/
                │       ├── layout.py
                │       ├── loader.py
                │       ├── discovery.py
                │       ├── locking.py
                │       ├── writer.py
                │       ├── journal.py
                │       └── repository.py
                │
                ├── serialization/
                │   ├── json_format.py
                │   └── schema_validation.py
                │
                └── presentation/
                    ├── cli/
                    └── markdown/
```

`store.py` временно становится compatibility facade:

```python
from .persistence.filesystem.loader import load_plan
from .persistence.filesystem.locking import PlanLock
```

### Плюсы

- Небольшой риск для установщиков и imports.
- Удобно делать последовательными PR.
- Существующие тесты продолжают работать.
- Можно отдельно менять реализацию.

### Минусы

- Историческое имя `plan` остаётся большим namespace.
- Старые и новые пути временно сосуществуют.
- Нужно установить срок удаления facade.

### Когда выбирать

Если сейчас важнее не остановить ежедневную работу над системой.

**Это мой рекомендуемый старт.**

***

## Вариант B: модульный монолит

После стабилизации границ:

```text
src/
└── skm/
    ├── planning/
    │   ├── model/
    │   ├── commands/
    │   ├── queries/
    │   ├── validation/
    │   └── ports.py
    │
    ├── execution/
    │   ├── model/
    │   ├── conductor/
    │   ├── recovery/
    │   └── ports.py
    │
    ├── workspaces/
    │   ├── projects.py
    │   ├── bindings.py
    │   └── discovery.py
    │
    ├── context/
    │   ├── assembly.py
    │   ├── materials.py
    │   └── selection.py
    │
    ├── extensions/
    │   ├── skills.py
    │   ├── templates.py
    │   └── registry.py
    │
    ├── adapters/
    │   ├── filesystem/
    │   ├── sql/
    │   ├── runtimes/
    │   ├── git/
    │   └── exports/
    │
    ├── entrypoints/
    │   ├── cli/
    │   ├── api/
    │   └── mcp/
    │
    └── bootstrap/
        ├── composition.py
        └── config.py
```

### Плюсы

- Один основной Python distribution.
- Проще устанавливать и синхронизировать версии.
- Чёткие bounded modules.
- Меньше соблазна делать runtime discovery между собственными пакетами.

### Минусы

- Большой packaging migration.
- Нужно перенести public commands и resource paths.
- Можно случайно заменить старую связанность новой общей папкой `adapters`.

### Когда выбирать

Если отдельная установка каждого пакета не является существенным продуктовым требованием.

**Это мой предпочтительный долгосрочный вариант, но не первый PR.**

***

## Вариант C: независимые distributions

Сохранить multi-package модель, но формализовать contracts:

```text
packages/
├── skm-contracts/
├── skm-planner/
├── skm-execution/
├── skm-workspace/
├── skm-filesystem/
├── skm-sql/
├── skm-provider-claude/
├── skm-provider-codex/
├── skm-cli/
└── skm-gui/
```

### Плюсы

- Реально независимые releases.
- Optional installations.
- Внешние integrations могут использовать contracts.
- Provider adapters не обязаны входить в основной install.

### Минусы

- Dependency/version matrix.
- Более сложная разработка monorepo.
- Больше package metadata.
- Cross-package refactoring дороже.
- Есть риск создать слишком толстый `skm-contracts`.

### Когда выбирать

Только если действительно нужны независимые потребители и независимый lifecycle компонентов.

**Не выбирать просто потому, что «много пакетов выглядит модульно».**

***

## Сравнение вариантов

| Критерий | A: внутри текущих packages | B: модульный монолит | C: отдельные distributions |
|---|---|---|---|
| Риск первого перехода | Низкий | Средний/высокий | Высокий |
| Скорость локального рефакторинга | Высокая | Высокая после миграции | Ниже |
| Независимые releases | Сохраняются частично | Обычно не нужны | Основное преимущество |
| Простота установки | Текущее состояние | Наиболее простая | Наиболее сложная |
| Контроль зависимостей | Нужны architecture tests | Нужны architecture tests | Нужны tests и package constraints |
| Рекомендация | Начать здесь | Цель при отсутствии причин для C | Только при реальной необходимости |

***

# Декомпозиция по сценариям

## Не делить по случайным словам

Плохое разбиение:

```text
helpers.py
utils.py
common.py
misc.py
manager.py
service.py
```

Через несколько месяцев в каждом будет новая смесь.

Предпочтительнее:

```text
publish_revision.py
complete_unit.py
resolve_project.py
load_snapshot.py
append_event.py
format_plan_markdown.py
```

Названия говорят о причине изменения.

### Но не один файл на функцию

Плохая крайность:

```text
get_title.py
set_title.py
trim_title.py
validate_title_empty.py
```

Файл должен объединять связанное поведение.

Хорошо:

```text
rename.py
  command;
  validation;
  handler;
  result.
```

***

## Вертикальный срез commands

Для крупного lifecycle-модуля я предлагаю проверять разбиение по use cases:

```text
commands/
├── create_plan.py
├── start_item.py
├── record_unit_result.py
├── request_review.py
├── accept_review.py
├── complete_item.py
├── pause_plan.py
└── archive_plan.py
```

**Это проектная карта, а не результат полного чтения `lifecycle.py`.** Сам файл существует и имеет размер 80 207 байт; точные границы функций ещё нужно подтвердить по содержимому. [Planner lifecycle](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/lifecycle.py)

В каждом command:

```text
input DTO;
preconditions;
pure decision;
persistence;
event;
result.
```

### Не создавать общий LifecycleManager

Если он получит:

```text
start;
finish;
review;
archive;
git;
render;
context;
budget;
provider;
workspace
```

— это прежний файл в форме класса.

***

## Pipeline проверок

Для `check.py` целевая форма может быть такой:

```text
validation/
├── findings.py
├── context.py
├── pipeline.py
├── schema_checks.py
├── reference_checks.py
├── dependency_checks.py
├── readiness_checks.py
└── evidence_checks.py
```

Но факт наличия всех этих обязанностей в текущем `check.py` ещё нужно подтвердить чтением; сейчас известно только наличие и размер модуля. [Planner check](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/check.py)

### Предлагаемый контракт

```python
@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    message: str
    document: str
    pointer: str | None = None


Check = Callable[
    [ValidationContext],
    Iterable[Finding],
]
```

Pipeline:

```python
def validate(
    context: ValidationContext,
    checks: tuple[Check, ...],
) -> tuple[Finding, ...]:
    return tuple(
        finding
        for check in checks
        for finding in check(context)
    )
```

### Существенное правило

Checks не изменяют план.

```text
validate
```

и:

```text
repair
```

— разные команды.

Иначе запуск проверки может неожиданно переписать данные.

### Ошибка check implementation

Если в check произошёл `TypeError`, нельзя автоматически выдать пользователю:

```text
план невалиден
```

Это может быть ошибка самого validator. Нужно различать:

```text
Finding
```

и:

```text
ValidatorFailed
```

***

## CLI как адаптер

В Planner и Orch есть крупные CLI-модули: 52 499 и 71 369 байт соответственно. Это основание проверить смешение argument parsing, business logic и output, но не доказательство, что оно присутствует в каждой команде. [Planner CLI](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/cli.py) · [Orch CLI](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/orch/lib/orch/cli.py)

Предлагаемая структура:

```text
cli/
├── main.py
├── context.py
├── errors.py
├── output.py
├── plan_commands.py
├── unit_commands.py
├── review_commands.py
└── workspace_commands.py
```

### У handler три обязанности

```text
parse;
call application;
present result.
```

### Запрет

CLI handler не должен:

```text
сам менять status в dict;
сам открывать JSON для записи;
сам дописывать domain event;
сам выбирать provider-specific retry;
сам собирать SQL.
```

### Output отдельно

```text
Result → JSON renderer
Result → terminal renderer
Result → exit status
```

Это даст одинаковую семантику CLI/API/MCP без того, чтобы запускать CLI как subprocess из GUI.

***

## Orch: сначала переиспользовать

В Orch уже есть отдельные модули effects, events, journal, port, retry и worksource. Новое проектирование должно сначала выяснить их реальные contracts. [Orch source tree](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/orch/lib/orch)

Предлагаемые вопросы к чтению:

| Модуль | Что проверить |
|---|---|
| `port.py` | Это orchestration port, runtime port или несколько обязанностей? |
| `effects.py` | Описания effects отделены от их исполнения? |
| `events.py` | Есть ли typed events и стабильная сериализация? |
| `journal.py` | Какие durability и replay guarantees? |
| `retry.py` | Повторяются только безопасные операции? |
| `launch.py` | Отделены подготовка, запуск, monitoring и cancellation? |
| `worksource.py` | Не протекают ли filesystem paths в общий contract? |
| `worksource_file.py` | Можно ли добавить другую реализацию без изменения conductor? |
| `bindings/` | Находится ли provider-specific код только здесь? |
| `conductor/` | Есть ли единый владелец state transitions? |

### Возможная целевая форма

```text
conductor/
├── state.py
├── decisions.py
├── transitions.py
├── scheduler.py
└── recovery.py

runtime/
├── requests.py
├── results.py
├── capabilities.py
└── port.py

effects/
├── model.py
├── executor.py
└── handlers/

journal/
├── events.py
├── writer.py
└── replay.py
```

Не нужно применять эту структуру механически до чтения текущего кода.

***

# Библиотеки-кандидаты

Здесь важна честная граница: **официальная документация и актуальные версии перечисленных внешних библиотек в этой итерации не проверялись**. Поэтому это shortlist для технических проб, не готовый список зависимостей и не утверждение об их совместимости с текущим SKM.

## Сначала стандартная библиотека

| Задача | Кандидат | Как применять |
|---|---|---|
| Value objects | `dataclasses` | Typed commands, results, references |
| Contracts | `typing.Protocol` | Persistence/runtime ports |
| Ограниченные значения | `Enum`, `Literal` | Status, document kind, outcome |
| Управление ресурсами | `contextlib` | Locks, temporary files, connections |
| Чистое обновление объекта | `dataclasses.replace` | Новый snapshot вместо `adopt` |
| Граф зависимостей | `graphlib` | Рассмотреть для проверки DAG и ready-set |
| Optional plugin discovery | `importlib.metadata` | Только если нужны внешние distributions |
| Часы и deadline | `datetime`, `time.monotonic` | Разные назначения, не смешивать |
| Структурированные исключения | Обычные exception classes | Предметные ошибки и причины |

### Не использовать pattern только ради pattern

Например, `match/case` полезен для закрытого набора typed outcomes.

Но заменять им каждую пару `if` не нужно.

***

## Validation и serialization

| Кандидат | Где рассмотреть | Где не применять автоматически |
|---|---|---|
| `jsonschema` + `referencing` | Проверка существующих JSON Schema и references | Не заменять без compatibility suite |
| Pydantic | API/config boundary, typed DTO | Не дублировать независимо все существующие schemas |
| `attrs` + `cattrs` | Альтернативная модель typed records и преобразований | Не добавлять одновременно с Pydantic без причины |
| `msgspec` | Рассмотреть при доказанном bottleneck serialization | Не начинать с него ради гипотетической скорости |

### Главная опасность

Плохо:

```text
JSON Schema:
  одно правило

Pydantic model:
  похожее правило

domain:
  третье правило
```

Если всё редактируется вручную, drift практически заложен в процесс.

### Для SKM

Первый вариант, который стоит проверить:

```text
legacy JSON:
  существующая JSON Schema

boundary parsing:
  один контролируемый converter

domain:
  typed model + semantic invariants
```

Второй вариант:

```text
typed boundary model
  → generated external schema
```

Но переход должен быть намеренным и покрытым round-trip tests.

***

## Persistence

| Кандидат | Зачем пробовать | Ограничение |
|---|---|---|
| SQLAlchemy | SQL mapping, transactions, SQLite/PostgreSQL adapters | ORM object не должен стать domain model |
| Alembic | Версионируемые schema migrations | Data migrations всё равно проектируются отдельно |
| `sqlite3` | Минимальный локальный SQL adapter | Больше ручной дисциплины вокруг SQL и migrations |
| `portalocker` | Если нужен переносимый lock adapter | Lock не создаёт multi-file transaction |
| `filelock` | Альтернатива для простого lock contract | Проверить reentrancy, timeout и platform semantics |

### Что я бы не добавлял

Большой universal repository framework.

У вас предметные операции:

```text
load plan;
commit revision;
accept result;
record review.
```

Не обязательно строить:

```python
GenericRepository[TEntity, TKey, TFilter, TSort]
```

с универсальным query DSL.

***

## Тестирование и качество

| Кандидат | Конкретная польза |
|---|---|
| pytest | Characterization, integration, contract tests |
| Hypothesis | Необычные IDs, graph structures, state sequences |
| Import Linter | Запрет неверных межслойных imports |
| Grimp | Анализ import graph |
| Ruff | Единый lint baseline и постепенное ужесточение |
| Pyright | Проверка новых typed contracts |
| Coverage.py | Выявление непроверенных recovery branches |
| Radon или аналог | Измерение hotspots, не оценка качества по одной цифре |

В корне уже есть `ruff.toml` и `pyrightconfig.json`; это повод расширять существующий процесс, а не заводить параллельную систему проверок. Содержимое конфигураций в этой итерации не проверено. [Корень репозитория](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5)

### Самая полезная проба

Для Hypothesis я бы сначала выбрал не весь проект, а:

```text
reference parsing;
ID round-trip;
dependency cycle detection;
command state transitions;
serialization round-trip.
```

### Чего не делать с метриками

```text
файл больше N строк → разбить;
функция сложнее X → переписать.
```

Метрика должна подсказать место чтения, а не автоматически определить архитектуру.

***

## Retry и concurrency

Кандидат для controlled retry — Tenacity, но решение о безопасности повтора не должно принадлежать универсальному декоратору.

Плохо:

```python
@retry(...)
def do_everything():
    create_pr()
    save_result()
```

Если PR создан, а сохранение результата упало, повтор может создать второй PR.

Правильно разделить:

```text
read/reconnect retry;
idempotent command retry;
external side-effect reconciliation.
```

Для async/concurrency можно рассмотреть AnyIO, **если** в следующей версии действительно нужен единый structured-concurrency layer.

Не стоит одновременно держать:

```text
threading;
asyncio;
AnyIO;
ручные worker threads;
свои cancellation flags
```

без одного владельца lifecycle.

***

# Что не добавлять

## Контейнер зависимостей

На текущем этапе я бы не начинал с dependency-injection framework.

Обычный composition root:

```python
def build_services(config: AppConfig) -> Services:
    repository = build_repository(config.storage)
    checkout_resolver = build_checkout_resolver(config.workspace)

    return Services(
        planning=PlanningService(
            repository=repository,
            checkout_resolver=checkout_resolver,
        )
    )
```

Преимущества:

- Dependencies видны.
- Construction можно проверить.
- Нет скрытой магии.
- Ошибки configuration возникают при сборке.

Если wiring реально станет слишком большим — тогда оценивать framework.

***

## Универсальный plugin bus

Не нужно переносить внутренние функции проекта в плагины только ради расширяемости.

Разделить:

```text
встроенный модуль;
optional integration;
недоверенное расширение.
```

Их lifecycle и риски различаются.

Для трёх встроенных renderers достаточно статического registry:

```python
RENDERERS = {
    "markdown": render_markdown,
    "json": render_json,
}
```

Не нужны:

```text
decorator registration;
import side effects;
recursive module scanning;
global mutable registry
```

если нет реального внешнего plugin ecosystem.

***

## Всё через events

Не нужно превращать обычный вызов:

```python
validate_plan(snapshot)
```

в:

```text
emit validation-requested;
find subscriber;
execute subscriber;
emit validation-completed;
resolve correlation.
```

Events полезны для:

- Durable history.
- Integration delivery.
- Async reactions.
- Audit.
- Reconstruction of decisions.

Обычный синхронный domain call должен оставаться обычным вызовом.

***

## Всё в async

Filesystem parsing, чистая валидация и небольшие локальные операции не становятся лучше от добавления `async def`.

Сначала определить:

```text
где ожидание внешнего IO;
где CPU work;
где блокирующий subprocess;
кто владеет cancellation.
```

После этого выбирать execution model.

Смешанная система допустима, но boundaries должны быть явными.

***

# Проверки рефакторинга

## Architecture tests

Для новой части проекта я бы сразу установил правила:

```text
domain
  не импортирует persistence

domain
  не импортирует CLI

application
  не импортирует provider adapters

CLI
  не импортирует private SQL models

renderers
  не изменяют snapshots

filesystem layout
  не решает review policy

runtime adapter
  не присваивает plan status напрямую

learning
  не изменяет обязательные operator permissions
```

Это должны быть автоматические проверки, не только текст в `AGENTS.md`.

### Важный нюанс

Нельзя объявить правила на весь legacy tree и получить тысячу ошибок.

Сначала:

```text
новый namespace;
новые contracts;
запрет новых нарушений.
```

Затем постепенно расширять охват.

***

## Characterization tests

Перед переносом `store.py` нужны tests существующего поведения:

- Сохраняется schema key ordering.
- Сохраняется newline.
- Неверный документ не запускает запись группы.
- `updated_at` не меняется до успешного сохранения.
- Повторный lock в том же потоке не зависает.
- Запись в migrated source запрещается.
- Повреждённый JSON виден в inspection.
- Неоднозначный short ID выдаёт ошибку.
- Archive lookup работает как раньше.
- Launcher scope не теряется.

Это свойства непосредственно связанных функций текущего [`store.py`](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py); перечисленные tests — предложения, их текущее наличие здесь не проверено.

***

## Fault injection

Обычный happy-path тест не проверяет файловый commit.

Нужны искусственные сбои:

```text
не удалось создать первый temp;
не удалось создать второй temp;
не удалось заменить первый target;
не удалось заменить второй target;
не удалось восстановить первый target;
не удалось удалить temp;
не удалось sync directory;
процесс остановлен между replace.
```

### Что проверять

Не только exception type:

```text
какие файлы изменились;
что осталось во временных;
какой recovery status;
есть ли event;
можно ли безопасно повторить;
не скрыта ли primary failure.
```

### Никаких платных агентов

Эта часть тестируется без моделей и provider CLI.

Для orchestration сначала достаточно fake runtime с предсказуемыми outcomes.

***

## Contract tests

Когда появятся разные repositories:

```text
FilesystemPlanRepository
SqlPlanRepository
HttpPlanningClient
```

общий contract suite проверяет:

- Идентичность.
- Конкурентный conflict.
- No-op semantics.
- Тип результата.
- Error codes.
- Validation.
- Публикацию revision.
- Согласованность state/event.
- Idempotency.

Но не нужно притворяться, что HTTP client — repository с удалённой SQL transaction. Сетевой command должен целиком исполняться серверным application handler.

***

# Порядок рефакторинга

## PR 1: доказать поведение

Содержание:

```text
characterization tests;
tests RF-01;
tests RF-02;
tests RF-03;
fault-injection scaffold.
```

Без массовых перемещений.

### Приёмка

- Известно, какие guarantees уже есть.
- Новые tests описывают ожидаемое исправленное поведение.
- Нет изменения CLI contract.

***

## PR 2: локальные исправления

Содержание:

- Инвалидация cached checkout state или отказ от `adopt`.
- Проверка соответствия lock и plan.
- Общая scope check перед возвратом resolved path.
- Явная ошибка invalid unit reference.
- Диагностика secondary cleanup/recovery failures.

### Приёмка

Каждое исправление имеет отдельный минимальный test.

Не добавлять в этот PR БД, новые revisions и provider abstraction.

***

## PR 3: физическое разделение

Вынести из `store.py`:

```text
layout.py
loader.py
locking.py
writer.py
journal.py
discovery.py
```

Сохранить facade для существующих imports.

### Приёмка

- Семантика не меняется.
- Diff преимущественно механический.
- Нет новых cyclic imports.
- Все старые callers продолжают работать.

Это важно: механический перенос и изменение guarantees должны быть разными review units.

***

## PR 4: typed boundary

Добавить:

```text
PlanRef
DocumentRef
LoadProblem
PlanInspection
ValidatedPlanSnapshot
CommitResult
```

Не переводить всё JSON-дерево сразу.

### Приёмка

Нельзя случайно передать diagnostic load result в mutation handler.

***

## PR 5: один application command

Выбрать небольшой сценарий:

```text
rename;
pause;
изменение ограниченного metadata.
```

Вынести:

```text
command DTO;
pure rule;
handler;
repository contract;
event.
```

### Приёмка

Тот же сценарий вызывается из теста без CLI, cwd и файлового discovery.

***

## PR 6: transaction boundary

Определить:

```text
PlanCommit;
UnitOfWork;
expected version;
state + event;
recovery result.
```

И только затем подключать новый backend.

### Приёмка

Гарантии названы точно и проверены failure tests.

***

## PR 7: крупные lifecycle slices

Постепенно переносить сценарии из крупных модулей.

Правило:

```text
один use case;
один владелец mutation;
один contract;
одна серия tests.
```

Не «разнести весь lifecycle на 20 файлов» одним коммитом.

***

## PR 8: CLI и GUI boundaries

Перевести entrypoints на application contracts.

### Приёмка

- CLI не меняет документы напрямую.
- GUI не читает filesystem layout.
- Error translation централизован.
- Machine-readable results стабильны.

***

# Карта следующих чтений

Чтобы следующий проход был именно продолжением аудита, а не повторением общих идей, порядок должен быть таким.

| Очередь | Файл / область | Какой конкретный ответ нужен |
|---|---|---|
| 1 | `lifecycle.py` | Кто меняет каждый status и где проходит commit boundary |
| 2 | `units.py` | Где unit state дублируется с item/result state |
| 3 | `check.py` | Какие проверки pure, какие делают IO и какие меняют данные |
| 4 | `_types.py` + schemas | Где typed model расходится с runtime schema |
| 5 | `_jsonschema_core.py` | Какая поддержка schema keywords, refs и error paths |
| 6 | `ops.py` | Какие команды смешивают lookup, mutation, persistence и rendering |
| 7 | `gitops.py` | Какие operations имеют external side effects и rollback assumptions |
| 8 | `bridges.py`, `extensions.py` | Есть ли import-time registration и скрытые dependencies |
| 9 | `orch/port.py`, `effects.py` | Достаточны ли существующие ports, нужен ли новый contract вообще |
| 10 | `orch/journal.py`, `retry.py` | Как согласованы durable state, retries и resume |
| 11 | `orch/conductor` | Где state machine, где agent decisions, где recovery |
| 12 | `workspace`, `aicore`, `harness` | Что действительно общее, а что ошибочно стало общим |
| 13 | GUI boundaries | Где интерфейс обходит application layer |
| 14 | Tests и CI | Какие guarantees реально проверяются сейчас |

Файлы Planner и Orch в этой карте существуют в зафиксированной ревизии; вопросы в таблице — **план проверки**, а не уже найденные дефекты их содержимого. [Planner](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan) · [Orch](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/orch/lib/orch)

***

## Практическая рекомендация

**Для ближайшей версии выбрал бы вариант A: сохранить текущие packages, исправить локальные нарушения контрактов и выделить из `store.py` небольшие компоненты. После этого — провести один законченный command через typed application boundary.**

Первый измеримый результат должен выглядеть так:

```text
CLI выбирает проект.
Resolver возвращает явный PlanRef.
Repository загружает согласованный snapshot.
Pure function вычисляет изменение.
Application формирует commit.
Persistence сохраняет state и event с заявленными guarantees.
CLI только отображает typed result.
```

И главный критерий качества здесь не число папок и классов:

> **Чтобы понять, почему изменился статус или файл, должно быть достаточно прочитать один command handler, одно чистое правило и один persistence contract — без обхода всего проекта.**