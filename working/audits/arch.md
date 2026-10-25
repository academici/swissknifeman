Понял: **Kiro здесь — ориентир для сравнения архитектурных решений, а не зависимость вашей системы.** Для SKM предлагаю спроектировать самостоятельное хранилище из трёх связанных частей: **версионируемая модель работы в БД, неизменяемые физические файлы и отдельное состояние исполнения**.

Ниже — подробная техническая спецификация: таблицы, ключи, ревизии, workspaces, загрузка файлов через API, согласованность БД и файлового хранилища, миграция текущих JSON и проверки. **Это проект целевой модели, а не описание уже реализованной функциональности.**

# SKM: хранение задач и workspaces

## Основания и границы

Текущий HEAD репозитория — `1603bfd8c988cf04505af55462c1596b5d82fde5`; именно к нему привязан разбор существующих данных. [Зафиксированный коммит](https://github.com/academici/swissknifeman/commit/1603bfd8c988cf04505af55462c1596b5d82fde5)

Для этого проекта непосредственно проверены `plan.schema.json`, `item.schema.json`, `unit.schema.json` и реализация `store.py`. В текущей схеме item уже явно объединяет стабильную спецификацию и изменяемый результат; unit аналогично содержит и описание работы, и `status`/`outcome`. Это основная граница, которую необходимо изменить при переходе к БД. [Item schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json) · [Unit schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/unit.schema.json)

Полный перечень схем также включает brief, phase, decision, document, check-evidence, review-receipt, snapshot, context-pack и read-модели, но их содержимое в этой итерации не проверено полностью. Поэтому точное сопоставление полей ниже гарантированно опирается на три прочитанные основные схемы; для остальных задана целевая модель и процедура проверки перед миграцией. [Каталог схем](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1)

**Важное уточнение к предыдущему ответу:** обязательный independent review для каждого unit был предложением новой политики, а не существующим правилом SKM. В текущей item-схеме доступны `none`, `self`, `requested`; эту семантику нельзя молча менять при импорте. [Item schema: review](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json)

***

## Базовые решения

Предлагаемая модель:

```text
Workspace
  ├── Projects
  │     ├── Repository bindings
  │     ├── Plans
  │     │     ├── Drafts
  │     │     ├── Immutable revisions
  │     │     └── Runs
  │     │           ├── Tasks
  │     │           ├── Attempts
  │     │           ├── Checks
  │     │           ├── Reviews
  │     │           └── Evidence
  │     └── Project documents
  │
  ├── Files
  │     └── Immutable file versions
  │           └── Physical blobs
  │
  ├── Members
  ├── Workers
  └── Audit/events
```

Пять главных правил:

1. **План не равен запуску.** Изменение результата проверки не создаёт новую редакцию требований.
2. **Файл не равен пути.** У файла есть идентичность, версия и байты; путь — только способ размещения или отображения.
3. **Workspace не равен checkout.** Workspace существует без локального репозитория.
4. **Ревизия не меняется после публикации.** Исправление создаёт новую ревизию.
5. **БД и blob storage не притворяются одной транзакционной системой.** Их согласованность обеспечивается явными протоколами.

### Что выбрать первоначально

| Область | Начальный вариант | Следующее расширение |
|---|---|---|
| Локальная БД | SQLite | Не требуется для обычного локального режима |
| Серверная БД | PostgreSQL | Репликация и HA только по необходимости |
| Физические файлы | Локальный managed blob directory | S3-совместимый adapter |
| API | HTTP commands/queries | SSE для событий |
| Очередь работы | Таблицы БД | Отдельный брокер только при доказанной необходимости |
| Поиск | Реляционные индексы и текстовый поиск | Производный поисковый индекс |
| Миграции | Версионируемые schema/data migrations | Отдельные online migrations при росте |

Не нужно сначала строить распределённую платформу. Но локальная модель сразу должна иметь правильные идентичности и границы, чтобы серверный режим не потребовал переизобретать данные.

***

## Термины без неоднозначностей

### Workspace

**Workspace — логическая область владения и доступа.**

В ней находятся:

- Проекты.
- Планы.
- Загруженные файлы.
- Пользователи и service identities.
- Настройки.
- Квоты.
- Workers.
- История действий.

Workspace — не путь `~/.something`, не Docker volume и не git repository.

Пример:

```text
Workspace: Dmitry Personal

Projects:
  SwissKnifeMan
  Agelto
  Infrastructure
```

На диске у этого workspace может быть локальное размещение. На сервере — запись в БД и набор объектов в blob storage. Его идентичность от размещения не меняется.

### Project

**Project — область инженерной работы внутри workspace.**

Проект может иметь:

- Ноль репозиториев: например, предварительное исследование.
- Один репозиторий.
- Несколько репозиториев: backend, frontend, infrastructure.

Для первого релиза рекомендую правило:

> Проект принадлежит одному workspace. Перенос между workspaces — отдельная операция копирования/миграции, а не обычное изменение `workspace_id`.

Это существенно упрощает безопасность, ссылки и перенос файлов.

### Repository

**Repository — логическая идентичность исходного кода.**

Не следует идентифицировать репозиторий только строкой URL:

```text
git@github.com:academici/swissknifeman.git
https://github.com/academici/swissknifeman
https://github.com/academici/swissknifeman.git
```

Для системы это могут быть разные адреса одного repository.

Хранить нужно:

```text
repository_id
canonical_remote
known_remote_aliases
external_provider
external_repository_id, если известен
```

Переименование репозитория или изменение remote не должны уничтожать его историю.

### Checkout binding

**Checkout binding — размещение конкретного repository на конкретном хосте.**

```text
repository_id
host_id
local_path
binding_status
```

Абсолютный путь:

```text
/Users/dmitry/work/swissknifeman
```

не должен становиться частью переносимой спецификации плана.

### Execution workspace

Чтобы не смешивать два значения workspace, временное рабочее дерево попытки лучше называть:

```text
execution_environment
```

или:

```text
worktree
```

Например:

```text
Logical workspace:
  Dmitry Personal

Execution environment:
  /var/lib/skm/worktrees/attempt-123
```

***

## Источники истины

Это нужно зафиксировать до проектирования SQL.

| Данные | Источник истины | Что является производным |
|---|---|---|
| Идентичность workspace/project/plan | БД или соответствующий state backend | Названия папок |
| Спецификация опубликованного плана | Immutable revision records | Markdown-представление |
| Состояние запуска | Run/task/attempt records | Progress bar |
| Результат проверки | Check execution и evidence bindings | Текст «tests passed» |
| Review | Review record, target digest, findings | Summary сообщения |
| Байты файла | Managed blob storage | Локальная материализация |
| Версия файла | File version record | Имя файла |
| Аудит | Audit records | Operational logs |
| Контекст агента | Зафиксированный context manifest | Summary разговора |
| Полнотекстовый поиск | Производный индекс | Не authoritative data |

### Чего не должно быть

Плохая конструкция:

```text
item_specs.status = done

и одновременно:

item_specs.document_json.status = in_progress
```

Или:

```text
review.status = accepted

но receipt.json содержит RED
```

Каждое значение имеет **одно authoritative место**. Остальные представления либо генерируются, либо проверяются как snapshots.

***

## Общие правила схемы

### Идентификаторы

Использовать стабильные UUID, создаваемые приложением.

Важно не конкретное поколение UUID, а свойства:

- ID не зависит от имени.
- ID не зависит от номера пункта.
- ID можно создать до обращения к серверу.
- ID можно переносить между backend.
- ID не содержит filesystem path.

Сохранить привычные человеку обозначения:

```text
PLAN7
P2
P2.4
P2.4/U1
D3
V2
```

Но только как aliases/display keys.

Текущие схемы связывают идентичность с layout: plan `id` равен имени каталога, item `id` — имени файла, а unit ID локален относительно item. Новая модель должна сохранить эти значения для совместимости, но перестать использовать их как глобальные первичные ключи. [Plan schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/plan.schema.json) · [Item schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json) · [Unit schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/unit.schema.json)

### Scope в ключах

В таблицах с доступом через workspace нужен `workspace_id`.

Но добавлять колонку недостаточно. Связи должны проверять scope:

```text
attachment.workspace_id
  должен совпадать с
file_version.workspace_id
```

И:

```text
run.project_id
  должен совпадать с
plan.project_id
```

Использовать составные foreign keys и соответствующие `UNIQUE` constraints.

Не рассчитывать только на:

```python
assert file.workspace_id == current_workspace
```

в HTTP handler.

### Время

Для новых событий:

```text
created_at
updated_at
published_at
started_at
finished_at
```

— точное время в UTC.

Для legacy-поля, в котором была только дата:

```text
source_created_date
```

Не выдумывать время `00:00:00Z` и не выдавать его за исторически известное.

### Отсутствие и null

При импорте нужно различать:

```text
поле отсутствовало;
поле было явно null;
поле было пустым массивом;
поле имело default.
```

Это особенно важно для старых `route`, настроек review и неизвестных расширений.

Нормализованная модель может свести часть различий, но исходный документ сохраняется отдельно.

### Версии

Минимум четыре независимых версии:

| Поле | Значение |
|---|---|
| `schema_version` | Версия формата объекта |
| `revision_no` | Номер опубликованной спецификации плана |
| `row_version` / `edit_version` | Конкурентное изменение mutable объекта |
| `event_sequence` | Порядок событий потока |

Дополнительно у расширений:

```text
skill_version
workflow_version
policy_version
```

`updated_at` не заменяет optimistic concurrency.

***

## Модель ревизий

### Три уровня

```text
Plan
  → Draft
  → Published revision
```

**Plan** — долговечная идентичность.

**Draft** — редактируемый документ.

**Published revision** — неизменяемый согласованный snapshot.

Запуск:

```text
Run → Published revision
```

Никогда:

```text
Run → current draft
```

### Почему нужен draft

Если каждое нажатие в GUI создаёт опубликованную revision, история быстро станет бесполезной:

```text
Revision 101: исправлена запятая
Revision 102: добавлена строка
Revision 103: передумал
```

Предлагаемое разделение:

```text
draft edit_version:
  1 → 2 → 3 → ... → 41

publication:
  Plan revision 8
```

Редактирование draft защищается `edit_version`. Публикация создаёт `revision_no`.

### Что неизменно в revision

После публикации нельзя менять:

- Требования.
- Состав phases/items/units.
- Зависимости.
- Acceptance criteria.
- Check definitions.
- Review requirements.
- Привязанные версии файлов.
- Зафиксированные decisions.
- Execution constraints.
- Версии используемых extension definitions, если они включены в specification lock.

Исправление создаёт новую revision.

### Что не входит в revision

Не включать туда:

- Текущий процент выполнения.
- Кто сейчас выполняет unit.
- Lease expiration.
- Результаты последней проверки.
- Runtime transcript.
- Текущий worker heartbeat.
- Текущее имя локального checkout.
- Последний operational error.

Иначе статическая спецификация снова смешается с исполнением.

### Parent revision

Для первого релиза достаточно линейной истории публикаций:

```text
R1 → R2 → R3
```

Несколько drafts допустимы:

```text
R3
 ├── draft A
 └── draft B
```

Но после публикации A:

```text
R3 → R4
```

draft B должен пройти explicit rebase/merge перед публикацией.

**Не делать полноценный Git-подобный merge graph в первом релизе.**

Если он понадобится позже, появится:

```text
revision_parents
```

с несколькими родителями. Сейчас это ненужное усложнение.

***

## Таблицы владения

В следующих таблицах перечислены смысловые поля. Для mutable записей по умолчанию подразумеваются `created_at`, `updated_at`, `row_version`; для immutable — `created_at`, `created_by`.

### Workspace и доступ

| Таблица | Основные поля | Связи и ограничения |
|---|---|---|
| `workspaces` | `id`, `slug`, `title`, `state`, `settings_json`, `row_version` | `slug` уникален в пределах установки; состояния `active`, `suspended`, `archived` |
| `principals` | `id`, `kind`, `display_name`, `state` | `kind`: human, service, worker; удаление identity не должно уничтожать аудит |
| `principal_identities` | `principal_id`, `issuer`, `subject` | `UNIQUE(issuer, subject)`; внешняя authentication identity отдельно от отображаемого имени |
| `workspace_memberships` | `workspace_id`, `principal_id`, `role`, `state` | `PK(workspace_id, principal_id)` |
| `projects` | `workspace_id`, `id`, `slug`, `title`, `description`, `state`, `settings_json` | `UNIQUE(workspace_id, slug)` |
| `project_memberships` | `workspace_id`, `project_id`, `principal_id`, `role` | Не могут выдать доступ за пределами membership workspace |

Для личного режима это не требует полноценного SaaS.

Можно автоматически создавать:

```text
workspace: personal
principal: local-user
membership: owner
```

Но операции уже выполняются с actor identity.

### Исходный код и размещение

| Таблица | Основные поля | Связи и ограничения |
|---|---|---|
| `repositories` | `workspace_id`, `id`, `title`, `canonical_remote`, `provider`, `external_id` | Repository принадлежит workspace |
| `repository_remotes` | `workspace_id`, `repository_id`, `normalized_url`, `is_primary` | Несколько remote aliases |
| `project_repositories` | `workspace_id`, `project_id`, `repository_id`, `role`, `mount_name` | `mount_name` уникален в проекте |
| `hosts` | `workspace_id`, `id`, `name`, `platform`, `state` | Хост — не worker process |
| `checkout_bindings` | `workspace_id`, `id`, `host_id`, `repository_id`, `local_locator`, `state`, `last_verified_at` | Не экспортируются как переносимая спецификация |
| `workers` | `workspace_id`, `id`, `principal_id`, `host_id`, `capabilities_json`, `last_seen_at`, `state` | Worker identity и capability admission отдельно от checkout |

`local_locator` может содержать путь, но:

- Он доступен только соответствующему worker/оператору.
- Не возвращается всем читателям проекта.
- Не используется сервером как путь в собственной файловой системе.

***

## Таблицы планов

### Идентичность и публикации

| Таблица | Основные поля | Назначение |
|---|---|---|
| `plans` | `workspace_id`, `project_id`, `id`, `title`, `lifecycle_state`, `current_revision_id`, `next_revision_no`, `row_version` | Стабильная идентичность и указатель на текущую публикацию |
| `plan_aliases` | `workspace_id`, `project_id`, `plan_id`, `alias`, `alias_kind` | Старые IDs, `PLAN7`, внешние references |
| `plan_drafts` | `workspace_id`, `plan_id`, `id`, `base_revision_id`, `edit_version`, `schema_version`, `document_json`, `state` | Редактируемый canonical draft |
| `plan_revisions` | `workspace_id`, `plan_id`, `id`, `revision_no`, `parent_revision_id`, `schema_version`, `content_digest`, `published_by`, `published_at`, `change_reason` | Неизменяемый snapshot |
| `plan_publications` | `workspace_id`, `plan_id`, `revision_id`, `published_by`, `reason`, `event_id` | История активации; полезна для controlled rollback |
| `plan_entity_identities` | `workspace_id`, `plan_id`, `entity_id`, `entity_kind`, `created_at` | Стабильная идентичность phase/item/unit/etc. между revisions |
| `revision_members` | `workspace_id`, `plan_id`, `revision_id`, `entity_id`, `entity_kind`, `display_key` | Какие entities входят в конкретную revision |

### Зачем отдельный revision member

Пункт:

```text
entity_id = 7d...
```

может существовать в R3, измениться в R4 и отсутствовать в R5.

```text
plan_entity_identities:
  7d... / item

revision_members:
  R3 / 7d...
  R4 / 7d...
```

Отсутствие в R5 не удаляет старую identity и не ломает run по R3.

### Почему не одна универсальная таблица

`revision_members` — **не EAV-модель содержимого**.

Она хранит только:

- Принадлежность revision.
- Stable identity.
- Вид сущности.
- Display key.

Содержимое лежит в типизированных таблицах:

```text
phase_specs
item_specs
unit_specs
requirement_specs
decision_specs
check_specs
```

Это позволяет иметь общую адресацию и при этом нормальные FK и предметные constraints.

### Основные ограничения

```text
UNIQUE(plan_id, revision_no)

UNIQUE(plan_id, revision_id)

UNIQUE(plan_id, entity_id)

UNIQUE(plan_id, revision_id, entity_id)

UNIQUE(plan_id, revision_id, display_key)
```

Для typed tables membership проверяется вместе с `entity_kind`.

Например, строка `unit_specs` не может ссылаться на member вида `decision`.

***

## Содержимое ревизии

### Спецификация верхнего уровня

| Таблица | Поля |
|---|---|
| `plan_revision_specs` | `revision_id`, `goal`, `context_markdown`, `non_goals_json`, `rules_json`, `owner_ref`, `author_snapshot_json`, `settings_json`, `orchestration_json`, `sections_json` |
| `brief_specs` | `revision_id`, `schema_version`, `body_json` |
| `phase_specs` | `revision_id`, `phase_id`, `position`, `title`, `body_json` |
| `item_specs` | `revision_id`, `item_id`, `phase_id`, `position`, `title`, `summary`, `why`, `scope_json`, `route_json`, `review_json`, `authority_json`, `guidance_markdown`, `options_json` |
| `unit_specs` | `revision_id`, `unit_id`, `item_id`, `position`, `local_key`, `title`, `goal`, `work_kind`, `mode`, `route_json`, `instructions_markdown`, `parent_unit_id`, `options_json` |

Здесь `revision_id` в реальной DDL сопровождается scope-колонками там, где они нужны для составных FK.

### Что допустимо в JSONB

Не нужно превращать каждую строку текста в отдельную таблицу.

Подходящее содержимое JSONB:

- `scope.include/exclude`.
- Небольшой route object.
- Настройки commit message.
- Набор неиндексируемых rendering sections.
- Дополнительные provider-neutral preferences.
- Именованные extension payloads.

Не следует прятать в JSONB:

- Dependency edges.
- Идентичности.
- File version references.
- Run status.
- Ownership.
- Review verdict.
- Attempt number.
- Данные для claim queue.
- Связи, которые обязана защищать БД.

**Критерий:** если по значению строится связь, блокировка, доступ или обязательный запрос — ему обычно нужна явная колонка или отдельная таблица.

### Поле `options_json`

Это не «склад всего оставшегося».

Для него нужны:

```text
фиксированная JSON Schema;
явный schema_version;
запрет неизвестных core-полей;
namespaced extensions;
ограничение размера;
отсутствие authoritative дубликатов колонок.
```

Например:

```json
{
  "deliverables": [
    "Документация протокола восстановления"
  ],
  "extensions": {
    "academici/example": {
      "schema_version": 1,
      "value": "..."
    }
  }
}
```

Нельзя одновременно хранить `title` и в колонке, и в `options_json`.

***

## Требования и зависимости

### Дополнительные таблицы

| Таблица | Основные поля | Ограничение |
|---|---|---|
| `requirement_specs` | `revision_id`, `requirement_id`, `display_key`, `statement`, `priority`, `source_json` | Stable requirement identity |
| `acceptance_criteria` | `revision_id`, `criterion_id`, `owner_entity_id`, `statement`, `verification_mode` | Owner существует в той же revision |
| `entity_requirement_links` | `revision_id`, `entity_id`, `requirement_id`, `relation` | Typed relation, одинаковая revision |
| `dependency_edges` | `revision_id`, `dependent_entity_id`, `prerequisite_entity_id`, `dependency_kind`, `condition_json` | Нет self-edge; обе стороны той же revision |
| `entity_relations` | `revision_id`, `source_entity_id`, `target_entity_id`, `relation`, `note` | Неблокирующие связи отдельно от dependencies |
| `decision_specs` | `revision_id`, `decision_id`, `title`, `state`, `body_json` | Состояние decision относится к specification |
| `decision_bindings` | `revision_id`, `decision_id`, `entity_id`, `binding_kind` | Привязка решения к пунктам |

### Направление dependency

Зафиксировать одну семантику:

```text
dependent → prerequisite
```

Пример:

```text
B depends_on A

dependent_entity_id = B
prerequisite_entity_id = A
```

Это кажется мелочью, но устраняет частую путаницу в API, SQL и graph UI.

### Разные типы связей

Не смешивать:

```text
blocks
informs
consumes
conflicts
follows_up
supersedes
```

Только часть связей влияет на scheduler.

Например:

```text
A informs B
```

не означает, что B обязан ждать завершения A.

### Зависимости item и unit

В текущей схеме у item — зависимости на другие items того же плана, а у unit — локальные `U#` dependencies. При миграции эти значения нужно разрешать в правильном scope. [Item schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json) · [Unit schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/unit.schema.json)

Предлагаемые правила:

- Item dependency блокирует начало исполняемой работы dependent item.
- Unit dependency блокирует конкретную unit task.
- Ссылка на `U1` сначала разрешается внутри owning item.
- Межпунктовые unit dependencies в новом формате используют stable IDs.
- Перед публикацией компилируется эффективный execution graph.
- Циклы проверяются на этом графе, а не только отдельно в item edges.

### Параллельное редактирование DAG

Обычного `CHECK` недостаточно, чтобы гарантировать отсутствие циклов.

Предлагаемый протокол:

```text
редактируем draft;
проверяем draft целиком;
при publish сериализуем публикацию plan;
создаём immutable DAG;
запуск использует только этот DAG.
```

Это проще и надёжнее, чем позволить конкурентно менять граф активной revision.

***

## Проверки как спецификация

### Таблицы определений

| Таблица | Основные поля |
|---|---|
| `check_specs` | `revision_id`, `check_id`, `owner_entity_id`, `display_key`, `kind`, `definition_json`, `required`, `evidence_policy_json` |
| `entity_check_bindings` | `revision_id`, `entity_id`, `check_id`, `binding_role` |
| `criterion_check_bindings` | `revision_id`, `criterion_id`, `check_id` |
| `review_requirements` | `revision_id`, `owner_entity_id`, `mode`, `reviewer_constraints_json`, `rounds_max`, `reason`, `waiver_policy_json` |

Один item-check может использоваться несколькими units.

Это важно для текущего поля:

```json
"checks": ["V1", "V2"]
```

Не нужно копировать check definition в каждую unit.

### Улучшение формата check

Предлагаемый новый формат:

```json
{
  "id": "check-uuid",
  "display_key": "V1",
  "kind": "command",
  "runner": {
    "argv": [
      "python",
      "-m",
      "pytest",
      "tests/storage"
    ],
    "cwd": {
      "repository": "main",
      "path": "."
    },
    "timeout_seconds": 300
  },
  "required": true,
  "evidence": {
    "stdout": true,
    "stderr": true,
    "report_files": [
      "test-results.xml"
    ]
  }
}
```

Числа и пути здесь — пример нового контракта.

Предпочтение `argv`, а не shell string, — проектное решение для более предсказуемого выполнения.

Shell-команда допускается отдельным видом:

```text
kind = shell
```

с явно повышенным risk classification.

### Manual check

Отдельный вид:

```json
{
  "kind": "manual",
  "instructions": "Проверить восстановление сессии в браузере",
  "required_actor_role": "operator",
  "allowed_verdicts": [
    "pass",
    "fail"
  ]
}
```

У manual check нет выдуманного process exit code.

***

## Планы без units

Это нужно предусмотреть сразу.

Нельзя заставить старый item без units автоматически получить новую unit в опубликованной specification без объяснимого преобразования.

Предлагаемая модель:

```text
run_tasks
  task_kind = item | unit
```

Правило компиляции:

```text
item имеет units
  → исполняемые tasks создаются для units

item не имеет units
  → исполняемая task создаётся для item
```

При этом:

- Сам item с units остаётся агрегирующей сущностью.
- Одновременно исполнять и item task, и все его unit tasks нельзя.
- Правило компиляции имеет версию.
- Скомпилированный execution graph фиксируется в Run.

Это сохраняет совместимость, не загрязняя план искусственными units.

***

## Таблицы исполнения

### Запуски и задачи

| Таблица | Основные поля | Назначение |
|---|---|---|
| `runs` | `workspace_id`, `project_id`, `id`, `plan_id`, `revision_id`, `status`, `requested_by`, `execution_profile_json`, `compiler_version`, `row_version` | Исполнение одной immutable revision |
| `run_tasks` | `run_id`, `id`, `spec_entity_id`, `spec_entity_kind`, `status`, `current_attempt_id`, `accepted_attempt_id`, `blocking_reason_json`, `row_version` | Исполняемая item/unit |
| `run_task_edges` | `run_id`, `dependent_task_id`, `prerequisite_task_id`, `condition_json` | Скомпилированный граф запуска |
| `attempts` | `run_id`, `task_id`, `id`, `attempt_no`, `state`, `worker_id`, `runtime_id`, `started_at`, `finished_at`, `result_json` | Отдельная попытка |
| `assignments` | `run_id`, `task_id`, `attempt_id`, `id`, `state`, `available_at`, `required_capabilities_json` | Выдача работы |
| `assignment_leases` | `assignment_id`, `worker_id`, `fencing_token`, `expires_at`, `last_heartbeat_at` | Текущее владение |
| `execution_environments` | `attempt_id`, `host_id`, `repository_bindings_json`, `baseline_manifest_id`, `state`, `local_locator` | Рабочая среда попытки |
| `attempt_outputs` | `attempt_id`, `id`, `manifest_digest`, `manifest_json`, `sealed_at` | Неизменяемый результат, который проверяют |

### Ключевые constraints

```text
UNIQUE(run_id, spec_entity_id)

UNIQUE(task_id, attempt_no)

FK(run_id, revision_id)
  → runs / revision binding

FK(revision_id, spec_entity_id, spec_entity_kind)
  → revision_members

FK(task_id, accepted_attempt_id)
  → attempts of this task
```

`accepted_attempt_id` не может ссылаться на попытку соседней задачи.

### Почему отдельный attempt output

Проверка относится не просто к attempt:

```text
Attempt 3
```

а к конкретному результату:

```text
Attempt 3 / output manifest digest abc...
```

Если после проверки изменились файлы, это уже другой output.

Следовательно:

```text
tests passed для output A
```

не означает:

```text
tests passed для output B
```

даже если оба появились в одной агентной сессии.

***

## Результаты и review

### Таблицы

| Таблица | Основные поля |
|---|---|
| `check_executions` | `id`, `run_id`, `task_id`, `attempt_id`, `check_id`, `output_id`, `state`, `started_at`, `finished_at`, `exit_code`, `verdict`, `summary` |
| `manual_check_verdicts` | `check_execution_id`, `principal_id`, `verdict`, `comment`, `recorded_at`, `supersedes_id` |
| `reviews` | `id`, `run_id`, `task_id`, `attempt_id`, `output_id`, `round_no`, `reviewer_principal_id`, `reviewer_runtime_json`, `state`, `verdict`, `freshness_class`, `completed_at` |
| `review_findings` | `review_id`, `id`, `severity`, `category`, `message`, `location_json`, `state` |
| `review_finding_resolutions` | `finding_id`, `resolution_kind`, `target_attempt_id`, `comment`, `resolved_by` |
| `acceptance_decisions` | `id`, `run_id`, `task_id`, `attempt_id`, `output_id`, `decision`, `actor_id`, `basis_json` |
| `deviation_acceptances` | `id`, `run_id`, `task_id`, `criterion_id`, `reason`, `approved_by`, `approved_at` |

### Состояния check

Предлагаемый набор:

```text
pending
running
passed
failed
manual_pending
error
cancelled
unknown
```

Различия принципиальны:

```text
failed:
  проверка дала отрицательный результат

error:
  проверку не удалось корректно выполнить

manual_pending:
  нужен человек

unknown:
  исход потерян или нельзя достоверно установить
```

Не сводить всё к `exit != 0`.

### Review и freshness

В текущем item-result уже предусмотрены receipt, verdict `GREEN`/`ATTENTION`/`RED`, round и freshness `fresh`/`findings_only`. Эти значения нужно перенести без потери смысла. [Item schema: result.review](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json)

В новой модели review должен указывать:

```text
какая revision;
какая task;
какая attempt;
какой output manifest;
какая версия review profile;
какой reviewer;
какие evidence использованы.
```

`ATTENTION` не должен автоматически означать accepted.

Нужна явная policy:

```text
GREEN
  → может быть принято при выполнении остальных gates

ATTENTION
  → требуется принятие отклонений или дополнительное решение

RED
  → не принимается
```

### История ручного verdict

Если человек ошибся:

```text
pass → fail
```

не перезаписывать единственную запись без следа.

Добавлять новое решение:

```text
verdict 2 supersedes verdict 1
```

При этом текущее состояние check может обновляться как удобная operational projection.

***

## Файлы: четыре сущности

Это вторая ключевая часть системы.

```text
File
  → File version
      → Blob
          → Physical location
```

### File

Логический документ:

```text
Архитектурный аудит
```

Он может иметь несколько версий.

### File version

Конкретная версия:

```text
Архитектурный аудит, версия 3
```

Версия неизменяема.

### Blob

Конкретные байты:

```text
SHA-256 ...
size ...
```

Два file versions могут ссылаться на одинаковый blob.

Но это не означает, что пользователи автоматически получают доступ к обоим документам.

### Physical location

Размещение blob:

```text
local managed storage
```

или:

```text
object store / bucket / key / storage version
```

Перенос bytes из local storage в object storage не меняет `file_version_id`.

***

## Таблицы файлов

### Логические файлы

| Таблица | Основные поля | Правило |
|---|---|---|
| `files` | `workspace_id`, `id`, `project_id`, `title`, `current_version_id`, `state`, `classification`, `row_version` | Логический документ |
| `file_versions` | `workspace_id`, `file_id`, `id`, `version_no`, `blob_id`, `original_filename`, `declared_media_type`, `detected_media_type`, `description`, `created_by`, `source_json` | Immutable после публикации |
| `file_folders` | `workspace_id`, `project_id`, `id`, `parent_folder_id`, `name` | Только организация интерфейса |
| `file_folder_entries` | `folder_id`, `file_id`, `display_name` | Физический blob не перемещается |

Для `file_versions`:

```text
UNIQUE(file_id, version_no)

UNIQUE(workspace_id, file_id, id)
```

`files.current_version_id` должен ссылаться на версию этого же файла.

### Физические данные

| Таблица | Основные поля | Правило |
|---|---|---|
| `blobs` | `workspace_id`, `id`, `hash_algorithm`, `content_digest`, `size_bytes`, `availability_state`, `verified_at` | Content identity после верификации неизменна |
| `blob_locations` | `workspace_id`, `blob_id`, `id`, `backend_id`, `storage_key`, `storage_version`, `state`, `verified_at` | Один blob может иметь несколько копий |
| `storage_backends` | `id`, `kind`, `configuration_ref`, `state` | Credentials через secret references |
| `blob_inspections` | `blob_id`, `id`, `inspection_kind`, `engine_version`, `policy_version`, `verdict`, `details_json`, `completed_at` | История scan/validation |
| `blob_holds` | `workspace_id`, `blob_id`, `id`, `holder_kind`, `holder_id`, `expires_at` | Временная защита от GC |
| `blob_deletion_jobs` | `blob_id`, `state`, `not_before`, `reason`, `attempts`, `last_error` | Управляемое физическое удаление |

### Почему inspections отдельно

Результат антивирусной или иной проверки зависит от:

```text
engine version
rules version
policy
time
```

Поэтому:

```text
blob hash immutable
```

но:

```text
current admissibility может измениться
```

Не нужно переписывать файл, чтобы повторно его проверить.

### Классификация

Пример:

```text
public
internal
confidential
restricted
```

Но classification не заменяет authorization.

Она определяет дополнительные ограничения:

- Можно ли отправлять файл внешнему runtime.
- Можно ли создавать public download URL.
- Какой retention.
- Нужен ли отдельный approval.

***

## Связи файлов с работой

### Не использовать только owner_type

Слабая конструкция:

```text
attachments:
  owner_type = "unit"
  owner_id = "..."
```

Без FK такая связь может указывать куда угодно.

Рекомендую отдельные типизированные binding tables:

| Таблица | На что ссылается |
|---|---|
| `revision_file_bindings` | Revision или конкретная entity внутри revision |
| `draft_file_bindings` | Редактируемый draft |
| `attempt_file_bindings` | Attempt |
| `output_file_bindings` | Attempt output |
| `check_evidence_bindings` | Check execution |
| `review_evidence_bindings` | Review |
| `project_document_bindings` | Project |
| `context_file_bindings` | Context manifest |

Общие поля binding:

```text
workspace_id
owner identifiers
file_version_id
role
position
selector_json
required
note
```

### Всегда версия, не latest

Плохая ссылка:

```text
plan uses file.current_version
```

Хорошая:

```text
revision R7
  → file_version F3
```

Если в файл загружена F4:

```text
R7 продолжает использовать F3
```

Для обновления материала создаётся R8.

### Roles

Пример ролей:

```text
input
reference
deliverable
evidence
transcript
patch
report
source_snapshot
```

Не нужно создавать отдельную физическую копию blob для каждой роли.

### Selectors

Ссылка может указывать на часть материала:

```json
{
  "kind": "markdown-heading",
  "value": "Recovery protocol"
}
```

Или:

```json
{
  "kind": "page-range",
  "from": 12,
  "to": 18
}
```

Selector — часть binding, а не blob.

***

## Репозиторные пути и attachments

Не каждый путь из текущего плана нужно превращать в uploaded file.

Сейчас `task_files` — подсказка о вероятных изменениях, а `unit.files` — write set; это разные значения, и их нельзя объединять в одну колонку `files`. [Item schema: task_files](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json) · [Unit schema: files](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/unit.schema.json)

### Нужны разные контракты

```text
RepositoryPathRef
  repository_id
  relative_path
  ref / commit, когда фиксируется

FileVersionRef
  file_version_id

PlanEntityRef
  plan_id
  revision_id
  entity_id

ExternalSourceRef
  URL
  captured_file_version_id, если зафиксирован
```

### Таблицы

| Таблица | Поля |
|---|---|
| `entity_path_specs` | `revision_id`, `entity_id`, `repository_id`, `path_pattern`, `role`, `expected_change`, `position`, `note` |
| `entity_read_specs` | `revision_id`, `entity_id`, `target_kind`, typed target columns, `selector_json`, `required`, `why`, `position` |
| `external_sources` | `workspace_id`, `id`, `source_url`, `retrieved_at`, `captured_file_version_id`, `provenance_json` |

Для `entity_read_specs` должно выполняться:

```text
ровно один target:
  repository path
  file version
  plan entity
  external source
```

Не произвольный набор одновременно заполненных колонок.

### Фиксация кода

Относительный путь:

```text
src/auth.py
```

сам по себе не делает контекст воспроизводимым.

В execution baseline фиксируется:

```text
repository_id
commit/object identity
dirty patch artifact, если был
submodule state, если нужен
environment manifest
```

Не нужно автоматически обещать полную воспроизводимость среды только потому, что сохранён Git SHA.

***

## Загрузка через API

### Общий протокол

```text
1. Создать upload session.
2. Зарезервировать quota.
3. Передать байты во временное размещение.
4. Завершить передачу.
5. Проверить размер и checksum.
6. Выполнить security inspection.
7. Создать immutable managed blob.
8. Создать file version.
9. Привязать к draft/task/project.
10. Освободить временные ресурсы.
```

Отдельные шаги позволяют восстанавливаться после обрыва.

### Таблицы upload

| Таблица | Поля |
|---|---|
| `upload_sessions` | `workspace_id`, `id`, `principal_id`, `state`, `expected_size`, `expected_digest`, `received_size`, `expires_at`, `target_file_id`, `staging_locator`, `request_fingerprint` |
| `upload_parts` | `upload_id`, `part_no`, `size_bytes`, `part_digest`, `storage_receipt` |
| `quota_reservations` | `workspace_id`, `id`, `upload_id`, `reserved_bytes`, `expires_at`, `state` |

Для обычной небольшой загрузки `upload_parts` может вообще не использоваться.

### Состояния upload

```text
created
receiving
uploaded
verifying
quarantined
ready
rejected
expired
aborted
```

`uploaded` не равно `ready`.

Файл нельзя использовать как обязательный material до `ready`.

### API

Предлагаемый интерфейс:

```http
POST /api/v1/workspaces/{workspace_id}/uploads
```

```json
{
  "project_id": "project-uuid",
  "filename": "storage-design.pdf",
  "declared_media_type": "application/pdf",
  "size_bytes": 1048576,
  "sha256": "expected-content-digest",
  "target_file_id": null
}
```

Ответ:

```json
{
  "upload_id": "upload-uuid",
  "state": "created",
  "transport": {
    "kind": "api-stream",
    "method": "PUT",
    "endpoint": "/api/v1/uploads/upload-uuid/content"
  },
  "expires_at": "2026-10-25T18:00:00Z"
}
```

Затем:

```http
POST /api/v1/uploads/{upload_id}/complete
```

Завершение идемпотентно.

### Повторный complete

Если upload уже принят:

```text
тот же запрос
  → возвращает тот же file_version_id
```

Если body отличается:

```text
IDEMPOTENCY_CONFLICT
```

Не создавать новую версию на каждый retry.

***

## Согласованность БД и bytes

### Почему одной транзакции недостаточно

Предлагаемая система должна исходить из того, что:

```text
SQL commit
```

и:

```text
запись файла / object store operation
```

— разные границы отказа.

Поэтому нельзя делать вид:

```python
with db.transaction():
    upload_to_storage()
    insert_file_version()
```

что внешний upload автоматически откатится вместе с SQL.

### Рекомендуемый порядок

```text
A. Записать bytes в staging.

B. Проверить:
   размер;
   digest;
   media type;
   разрешённость содержимого.

C. Создать final immutable storage object.

D. Подтвердить, что final object доступен
   и соответствует ожидаемым bytes.

E. SQL transaction:
   создать/найти blob;
   зарегистрировать blob location;
   создать file version;
   создать binding;
   сохранить idempotency receipt;
   записать domain event/outbox.

F. Commit.

G. Удалить staging асинхронно.
```

### Почему bytes раньше ссылки

Если процесс падает после C, до E:

```text
остаётся orphan physical object
```

Его можно найти и удалить.

Если сначала опубликовать DB reference, а bytes ещё не готовы:

```text
план ссылается на несуществующий материал
```

Это существенно хуже для correctness.

### Таблица разрывов

| Сбой | Результат | Восстановление |
|---|---|---|
| Перед завершением upload | Неполный staging | Resume или expiration cleanup |
| После проверки, до final object | Нет опубликованной версии | Повторить promotion |
| После final object, до SQL commit | Orphan bytes | Reconciliation / GC |
| После SQL commit, до HTTP response | Версия существует | Idempotent retry |
| После commit, до удаления staging | Лишняя временная копия | Cleanup |
| Storage object пропал позже | DB metadata остаётся | Mark unavailable, alert, restore |

### Запрет overwrite

Финальные storage keys должны быть управляемыми и неизменяемыми.

Нельзя позволять:

```text
PUT /objects/plan-7/audit.pdf
```

перезаписывать bytes, уже использованные старой revision.

***

## Presigned upload и гонки

Это стоит предусмотреть, даже если первоначально bytes передаются через API.

### Опасный вариант

```text
выдать клиенту право писать прямо в final key;
проверить файл;
опубликовать DB reference;
клиент повторно пишет в тот же key.
```

Тогда проверенные и фактически читаемые bytes могут различаться.

### Безопасная модель

```text
client → staging key

server:
  verifies staged bytes;
  promotes to private final key;
  final key больше не доступен клиенту на запись.
```

Если backend поддерживает object version identity, она сохраняется в `blob_locations.storage_version`.

Материализация и download должны читать именно зафиксированную версию, а не случайный latest object.

### Локальный backend

Для локального размещения аналогично:

```text
staging
  → verify
  → managed final object
```

Пользовательское имя файла не используется как путь final object.

Final directory недоступен агенту на произвольную запись.

***

## Content addressing и дедупликация

### Digest

Для физических bytes:

```text
digest = SHA-256(exact bytes)
```

Это не зависит от имени файла.

Для JSON-ревизии нужен другой digest:

```text
digest = SHA-256(canonical specification manifest)
```

Нельзя смешивать эти значения.

### Текущая canonical JSON

Текущий `store.py` формирует JSON с порядком ключей по schema properties, отступами и завершающим newline. Это формат сохранения, который нужно учитывать при сохранении оригиналов, но не следует автоматически объявлять межсистемным cryptographic canonical format. [store.py: canonical_dump](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Для новой revision необходимо отдельно определить:

```text
canonicalization_version
encoding
key ordering
number rules
timestamp representation
array ordering
excluded generated fields
```

При этом:

- Текстовые значения не нормализуются неожиданно.
- Порядок смысловых массивов сохраняется.
- Digest не включает самого себя.
- Original import bytes имеют отдельный digest.
- Изменение canonicalization — новая версия алгоритма.

### Scope дедупликации

Для первого релиза рекомендую:

```text
deduplication scope = workspace
```

А не глобальная дедупликация между всеми пользователями.

Это уменьшает риски утечки существования чужого файла.

Даже если bytes совпадают:

```text
доступ к blob по digest
```

не предоставляется.

Доступ проверяется через logical file/version/binding.

### Не начинать с дедупликации

Дедупликация — оптимизация.

В первом релизе допустимо:

```text
два одинаковых uploads
  → два managed physical objects
```

если это упрощает надёжность.

Недопустимо экономить место ценой ошибок доступа или удаления используемых данных.

***

## Физический layout

### Локальное размещение

```text
skm-data/
├── instance.json
├── state/
│   └── skm.sqlite3
├── blobs/
│   └── workspace-uuid/
│       └── objects/
│           ├── 6a/
│           │   └── blob-uuid
│           └── f2/
│               └── blob-uuid
├── staging/
│   └── upload-uuid/
├── materialized/
│   └── run-uuid/
├── worktrees/
│   └── attempt-uuid/
├── backups/
└── logs/
```

Разделить:

```text
blobs:
  authoritative bytes

materialized:
  disposable copies for consumers

worktrees:
  execution state

staging:
  uncommitted uploads

logs:
  operational diagnostics
```

Нельзя очищать всё одной командой «почистить кэш».

### Storage locator

Сохранять:

```text
backend_id
storage_key
storage_version
```

Не сохранять абсолютный root path в каждой строке.

Например:

```text
backend_id = local-primary
storage_key = workspace-uuid/objects/6a/blob-uuid
```

Root:

```text
/var/lib/skm/blobs
```

остаётся конфигурацией backend.

### Материализация

Агент получает материал через managed materialization:

```text
file_version_id
  → authorize
  → resolve ready blob
  → verify/admit
  → create read-only materialization
```

Не выдавать агенту путь ко всему authoritative blob store.

***

## Публикация ревизии

Это одна из наиболее важных транзакций.

### Вход

```json
{
  "draft_id": "draft-uuid",
  "expected_edit_version": 42,
  "expected_base_revision_id": "revision-7",
  "change_reason": "Уточнён протокол загрузки",
  "idempotency_key": "publish-request-uuid"
}
```

### Подготовка вне транзакции

Можно заранее выполнить:

- JSON Schema validation.
- Проверку ссылок.
- Проверку graph.
- Вычисление manifest.
- Проверку размера specification.
- Формирование typed records.

Но результаты проверок, зависящих от mutable state, необходимо подтвердить в transaction.

### Внутри транзакции

```text
1. Проверить actor permissions.

2. Захватить plan row.

3. Проверить:
   draft принадлежит plan;
   edit_version совпадает;
   draft base всё ещё допустим;
   plan не archived.

4. Повторно проверить referenced file versions:
   scope;
   readiness;
   availability;
   отсутствие deleting.

5. Выделить revision_no из plan counter.

6. Вставить plan_revision.

7. Вставить revision_members.

8. Вставить typed specification records.

9. Вставить dependencies/check/read/file bindings.

10. Зафиксировать permanent references на blobs
    через file version bindings.

11. Изменить current_revision_id.

12. Закрыть draft как published.

13. Записать publication event/outbox.

14. Записать idempotency receipt.

15. Commit.
```

### Защита от двух публикаций

```text
draft A и draft B основаны на R7

A публикует R8

B пытается опубликоваться:
  BASE_REVISION_CHANGED
```

B не должен тихо стать R9, игнорируя изменения A.

### No-op публикация

Если specification digest совпадает с текущей revision:

```text
return existing revision
```

или:

```text
NO_CHANGES
```

Выбрать одно поведение и закрепить в contract tests.

***

## Изменения во время запуска

### Активный Run не перепривязывается

```text
Run A → R7

Публикуется R8.

Run A всё ещё → R7.
```

Пользователю доступны:

```text
продолжить R7;
остановить Run A;
создать Run B по R8;
перенести подтверждённые результаты через explicit carry-forward.
```

### Carry-forward

Не копировать `accepted=true` автоматически.

Нужна таблица:

```text
result_carry_forwards
```

Поля:

```text
source_run_id
source_task_id
source_attempt_id
source_output_id
target_run_id
target_task_id
compatibility_digest
decision
approved_by
reason
```

Проверяются:

- Не изменился ли смысл task.
- Не изменились ли требования.
- Не изменились ли checks.
- Не изменились ли обязательные materials.
- Не изменились ли dependencies.
- Допустим ли baseline кода.
- Сохраняется ли review validity.

Для первого релиза можно разрешить carry-forward только вручную.

### Переименование не равно новая работа

Если изменён только display key:

```text
P2.4 → P3.1
```

stable entity ID сохраняется.

Но полная эквивалентность результата всё равно определяется compatibility rules, а не совпадением ID.

***

## Leases и fencing

### Claim

В PostgreSQL worker claim может использовать блокировку подходящих assignment rows; конкретный SQL остаётся внутри dialect adapter.

В SQLite нужен отдельный корректный claim algorithm с сериализацией записи.

Общий контракт:

```text
одна assignment;
один текущий lease;
монотонный fencing token.
```

### Поля lease

```text
assignment_id
worker_id
fencing_token
expires_at
last_heartbeat_at
```

### Принятие результата

Result request содержит:

```text
assignment_id
attempt_id
worker_id
fencing_token
output_manifest_id
```

Сервер проверяет всё вместе.

Если lease уже переиздан:

```text
LEASE_LOST
```

Старый result не принимается.

### Ограничение

Fencing защищает только те операции, которые проверяют token.

Поэтому старый агент не должен продолжать писать в общее рабочее дерево:

```text
каждый attempt
  → отдельное execution environment
```

Иначе устаревший процесс может испортить файлы даже при корректном отказе принять его result.

***

## События и idempotency

### Таблицы

| Таблица | Поля |
|---|---|
| `domain_events` | `workspace_id`, `event_id`, `stream_kind`, `stream_id`, `stream_sequence`, `event_type`, `schema_version`, `actor_id`, `payload_json`, `recorded_at` |
| `outbox_messages` | `id`, `event_id`, `destination`, `state`, `available_at`, `attempts`, `last_error` |
| `consumer_receipts` | `consumer_id`, `event_id`, `processed_at` |
| `idempotency_receipts` | `workspace_id`, `principal_id`, `operation`, `key`, `request_digest`, `result_json`, `created_at`, `expires_at` |
| `audit_records` | `workspace_id`, `id`, `actor_id`, `action`, `target_json`, `decision`, `request_id`, `recorded_at` |

### State и event

Текущий store отдельно сохраняет документы и отдельно дописывает `log.jsonl`; переход к SQL должен объединить соответствующее изменение состояния и событие в одну транзакцию. [store.py: save_many / append_log](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

```text
transaction:
  mutate state
  append event
  append outbox
  save command receipt

commit
```

Не вызывать webhook до commit.

### Idempotency scope

Уникальность:

```text
workspace_id
principal_id
operation
key
```

Request digest включает значимые входы:

```text
body
target
expected version
relevant command options
```

Если key прежний, но digest другой:

```text
IDEMPOTENCY_KEY_REUSED
```

### Порядок событий

Не следует считать обычный autoincrement ID гарантией порядка commit.

Для первого варианта рекомендую:

```text
stream_sequence на уровне plan/run
```

с выделением sequence под transaction lock соответствующего aggregate.

Если нужен единый workspace cursor для SSE, можно использовать transactional workspace counter. Это сериализует выделение workspace events и должно быть осознанным компромиссом.

Нельзя потерять поздно закоммиченный event только потому, что клиент уже продвинул cursor за его числовой ID.

***

## Ограничения БД

### Обязательные FK

Вот минимальный список отношений, которые должна защищать сама БД:

```text
project → workspace

plan → project

revision → plan

parent revision → тот же plan

revision member → revision

typed spec → member правильного kind

unit → item той же revision

item → phase той же revision

dependency endpoints → та же revision

run → revision того же plan

task → entity этой revision

attempt → task этого run

review → attempt/output этой task

check execution → definition правильной revision

file version → file того же workspace

file binding → file version того же workspace

blob location → blob того же workspace
```

### Пример составной связи

Иллюстрация критичного принципа:

```sql
ALTER TABLE plan_revisions
ADD CONSTRAINT uq_revision_scope
UNIQUE (workspace_id, plan_id, id);

ALTER TABLE runs
ADD CONSTRAINT fk_run_revision_scope
FOREIGN KEY (
    workspace_id,
    plan_id,
    revision_id
)
REFERENCES plan_revisions (
    workspace_id,
    plan_id,
    id
);
```

Так нельзя создать run одного plan со случайной revision другого.

### Пример typed membership

```sql
ALTER TABLE revision_members
ADD CONSTRAINT uq_revision_member_kind
UNIQUE (
    workspace_id,
    plan_id,
    revision_id,
    entity_id,
    entity_kind
);
```

В `unit_specs`:

```sql
entity_kind TEXT NOT NULL DEFAULT 'unit'
CHECK (entity_kind = 'unit')
```

И составной FK:

```text
workspace_id, plan_id, revision_id, unit_id, entity_kind
  → revision_members
```

Это устраняет ситуацию:

```text
unit_specs.unit_id
  → decision entity
```

### CHECK constraints

Примеры:

```text
size_bytes >= 0

attempt_no >= 1

revision_no >= 1

position >= 0

dependent_entity_id != prerequisite_entity_id

finished_at >= started_at, когда оба известны

review rounds в допустимом диапазоне

required manual verdict имеет principal
```

### Что CHECK не заменит

Через application/domain validation проверяются:

- Отсутствие циклов.
- Смысловая полнота acceptance criteria.
- Соответствие path policy.
- Полнота review.
- Доступность требуемых runtime capabilities.
- Допустимость carry-forward.
- Согласованность сложного execution graph.

Но это не оправдание не делать обычные FK.

***

## Индексы под запросы

Индексы проектируются под реальные read paths.

| Запрос | Индекс |
|---|---|
| Планы проекта | `plans(workspace_id, project_id, lifecycle_state, updated_at, id)` |
| История revision | `plan_revisions(plan_id, revision_no)` |
| Состав revision | `revision_members(revision_id, entity_kind, display_key)` |
| Items фазы | `item_specs(revision_id, phase_id, position, item_id)` |
| Units item | `unit_specs(revision_id, item_id, position, unit_id)` |
| Prerequisites entity | `dependency_edges(revision_id, dependent_entity_id)` |
| Dependents entity | `dependency_edges(revision_id, prerequisite_entity_id)` |
| Runs проекта | `runs(workspace_id, project_id, status, created_at, id)` |
| Готовая работа | `assignments(state, available_at, id)` с учётом scope/pool |
| Просроченные leases | `assignment_leases(expires_at)` |
| Attempts task | `attempts(task_id, attempt_no)` |
| Evidence check | `check_evidence_bindings(check_execution_id)` |
| Файлы проекта | `files(workspace_id, project_id, state, updated_at, id)` |
| Версии файла | `file_versions(file_id, version_no)` |
| Blob lookup | `blobs(workspace_id, hash_algorithm, content_digest, size_bytes)` |
| Upload cleanup | `upload_sessions(state, expires_at)` |
| Outbox dispatch | `outbox_messages(state, available_at, id)` |
| Event replay | `domain_events(stream_kind, stream_id, stream_sequence)` |

### Pagination

Для длинных списков использовать cursor/keyset pagination.

Пример:

```text
updated_at + id
```

Один timestamp недостаточен: несколько записей могут иметь одинаковое время.

Для immutable истории:

```text
revision_no
```

или:

```text
stream_sequence
```

### Не индексировать всё

Каждый JSONB не должен автоматически получать тяжёлый универсальный индекс.

Сначала определить:

```text
какие фильтры действительно доступны API;
какие запросы критичны;
какие поля authoritative;
какие read models можно построить отдельно.
```

***

## Статусы и удаление

### Plan status

Текущий plan объединяет `active`, `paused`, `done`, `archived`. В новой модели эти значения нужно разнести по lifecycle и execution, сохранив legacy-представление для совместимости. [Plan schema: status](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/plan.schema.json)

Предлагаю:

```text
Plan lifecycle:
  active
  archived

Run status:
  created
  ready
  running
  waiting
  paused
  succeeded
  failed
  cancelled
```

`done` — не вечное свойство plan identity: после новой revision работа может снова потребоваться.

### Soft delete

Для пользовательского удаления:

```text
files.state = trashed
plans.lifecycle_state = archived
```

Но:

```text
trash file
```

не означает:

```text
удалить bytes, используемые старой revision
```

### Не CASCADE всё

Не использовать бездумно:

```sql
ON DELETE CASCADE
```

на цепочке:

```text
project
  → plan
  → runs
  → evidence
  → blobs
```

Случайная операция не должна уничтожать весь аудит и доказательства.

Для большинства долговечных сущностей:

```text
RESTRICT
```

и отдельная purge procedure.

CASCADE допустим для технических дочерних записей, жизнь которых полностью определяется owner, например частей ещё не опубликованной upload session.

***

## Garbage collection

### Что держит blob живым

Blob нельзя удалять, пока существует хотя бы одна допустимая ссылка:

- File version, связанная с опубликованной revision.
- Evidence принятого результата.
- Review evidence.
- Retained run.
- Активный draft binding.
- Незавершённый import.
- Backup hold.
- Legal/administrative hold, если такая функция включена.
- Незавершённая materialization/processing operation с hold.

### Не refcount как единственная истина

Поле:

```text
reference_count
```

может быть кэшем, но не единственным основанием удаления.

Иначе ошибка increment/decrement однажды удалит используемый файл.

### Протокол GC

```text
1. Найти кандидата.

2. Захватить blob row.

3. Повторно проверить:
   durable references;
   holds;
   retention;
   незавершённые операции.

4. Пометить:
   availability_state = deleting.

5. Commit.

6. Удалить physical locations.

7. Зафиксировать результат удаления.

8. Оставить tombstone metadata по retention policy.
```

### Гонка attachment и GC

Операция создания нового binding обязана проверить blob под согласованной блокировкой.

Если blob уже `deleting`:

```text
BLOB_NOT_ATTACHABLE
```

Нельзя:

```text
GC проверил отсутствие ссылок;
другая transaction добавила ссылку;
GC удалил bytes.
```

### Partial delete

Если удалена одна из двух физических копий, а вторая ещё существует:

```text
blob не считается полностью удалённым
```

Удаление locations отслеживается отдельно.

***

## Backup и восстановление

### Что резервировать

Не только SQL dump.

Нужен комплект:

```text
database backup
blob inventory
physical blob copies
schema migration version
storage configuration references
encryption key recovery procedure
backup manifest
```

Секреты не нужно складывать в открытом виде рядом с backup.

### Согласованный backup

Простой первоначальный протокол:

```text
1. Создать backup job.

2. Временно запретить физический GC.

3. Получить согласованный DB snapshot.

4. Выгрузить inventory blobs,
   на которые ссылается этот snapshot.

5. Скопировать нужные immutable blobs.

6. Проверить hashes.

7. Завершить backup manifest.

8. Снять GC hold.
```

Uploads могут продолжаться, если backup reader корректно работает со snapshot и нужные blobs защищены от удаления.

### Restore

```text
restore database в staging;
restore blobs;
проверить inventory;
проверить hashes;
проверить FK;
проверить schema compatibility;
выполнить consistency audit;
только затем activate.
```

### Приёмка

Backup не считается готовой функцией, пока не проведён restore test.

Наличие архива на диске недостаточно.

***

## Авторизация файлов

### Проверять не только URL

Скачивание:

```text
GET file_version
  → workspace access
  → project access
  → classification policy
  → binding visibility
  → blob availability
```

Знание `blob_id` или digest не предоставляет доступ.

### Download URL

Если используется краткоживущий storage URL:

- Он выдаётся после authorization.
- Имеет ограниченный срок.
- Не хранится в revision как постоянная ссылка.
- Не записывается в обычные logs целиком.
- Не используется как идентичность файла.

### Agent access

Worker получает только материалы assignment.

Не:

```text
вот credentials всего workspace blob storage
```

А:

```text
вот список разрешённых file_version_ids
и ограниченный способ их получить
```

### Upload restrictions

Проектные требования:

- Ограничение размера.
- Quota reservation.
- Проверка declared и detected media type.
- Безопасная обработка имени файла.
- Запрет path traversal.
- Запрет автоматического исполнения.
- Карантин до допуска.
- Ограничения archive extraction.
- Лимиты распаковки и вложенности.
- Безопасный preview.
- Отдельная policy внешней передачи модели.

PDF, HTML или Markdown следует считать input, а не trusted instruction.

***

## Соответствие текущему Plan JSON

### `plan.schema.json`

| Текущее поле | Целевое место | Преобразование |
|---|---|---|
| `$schema` | `schema_version` + source schema metadata | Сохранять исходный URI |
| `id` | `plan_aliases` | Новый `plan_id` отдельно |
| `short_id` | `plan_aliases` | Scope — project |
| `title` | `plans.title` и snapshot title revision | Live title и историческое название различать |
| `status` | Plan lifecycle + imported execution state | Не переносить одной колонкой |
| `pause` | Imported run pause / legacy snapshot | Сохранить reason, source date, source actor |
| `created` | `source_created_date` | Не выдумывать точное время |
| `updated_at` | Import provenance | Не выдавать за момент создания новой revision |
| `repository` | Repository binding | Строка разрешается в identity; unresolved сохраняется |
| `owner` | Owner reference + source label | Не превращать строку автоматически в authenticated principal |
| `authoring` | Actor snapshot / principal mapping | Сохранить исходную атрибуцию |
| `goal` | `plan_revision_specs.goal` | Без потерь |
| `context` | `context_markdown` | Без потерь |
| `non_goals` | `non_goals_json` | Порядок сохраняется |
| `rules` | Specification rules | Не становятся operator security policy |
| `phases` | `phase_specs.position` | Порядок явный |
| `links` | Plan relation records | Неразрешённые refs не терять |
| `contracts` | Contract definitions/bindings | Не оставлять только текстом при автоматизации |
| `settings` | Typed settings JSON | Legacy defaults фиксируются явно |
| `orchestration` | Execution preference spec | Не текущий run state |
| `sections` | Versioned section payload | Сохранить порядок |

Перечисленные поля и ограничения присутствуют в прочитанной plan-схеме. [Plan schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/plan.schema.json)

### Межплановые contracts

Дополнительные таблицы:

```text
contract_specs
contract_consumptions
plan_relations
```

`contract_consumptions`:

```text
consumer_revision_id
contract_name
provider_plan_id, если разрешён
provider_revision_id, если pinned
provider_contract_id, если разрешён
pinned_digest/version
reaction_policy
source_donor_label
```

Внешний package donor нельзя насильно превращать в plan ID.

***

## Соответствие Item JSON

| Текущее поле | Целевое место |
|---|---|
| `id` | Stable item identity + revision display key |
| `title`, `summary`, `why` | `item_specs` |
| `status` | Imported run task/aggregate state |
| `scope` | `item_specs.scope_json` |
| `depends_on` | `dependency_edges` |
| `related` | `entity_relations` |
| `decisions` | `decision_bindings` |
| `skills` | Versioned extension requirements |
| `reads` | `entity_read_specs` |
| `task_files` | `entity_path_specs`, role `change_hint` |
| `artifacts` | Artifact declarations и bindings |
| `rules`, `guidance` | Specification content |
| `examples` | Ordered read/example bindings |
| `validation` | `check_specs` |
| `deliverables` | Specification deliverables |
| `route` | Typed route preference |
| `review` | `review_requirements` |
| `authority` | Gate requirement |
| `rag.need` | Research requirement |
| `rag.status` | Imported execution/research state |
| `rag.captures` | Captured file bindings |
| `units` | `unit_specs.position` |
| `result` | Attempts, checks, review, acceptance records |
| `updated_at` | Source provenance |
| `orchestration` | Execution preference specification |
| `sections` | Versioned content |

Это сопоставление опирается на прочитанную item-схему, включая различия между `task_files`, artifacts, reads, review и lifecycle-owned result. [Item schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/item.schema.json)

### Не потерять состояния

Текущие:

```text
done_with_deviations
skipped
blocked
```

нельзя свести к:

```text
done / not done
```

Предлагаемое отображение:

```text
done_with_deviations
  → accepted result + deviation records

skipped
  → explicit skip acceptance + decision reference

blocked
  → blocking reason
```

Но imported state должен быть помечен как исторический, а не заново подтверждённый новой системой.

***

## Соответствие Unit JSON

| Текущее поле | Целевое место |
|---|---|
| `id` | Legacy local key |
| `item` | FK на item той же revision |
| `title`, `goal` | `unit_specs` |
| `files` | `entity_path_specs`, role `declared_write_scope` |
| `reads` | `entity_read_specs` |
| `depends_on` | Resolved unit dependencies |
| `checks` | Check definitions/bindings |
| `route`, `mode` | Unit execution preferences |
| `instructions` | `unit_specs.instructions_markdown` |
| `status` | Run task state |
| `outcome.agent` | Attempt actor snapshot |
| `outcome.registered_by` | Registering actor |
| `outcome.at` | Source event timestamp |
| `outcome.notes` | Attempt/result notes |
| `outcome.changed` | Observed changed-path records |
| `outcome.minutes` | Reported duration, не измеренная автоматически |
| `outcome.attempt_id` | Legacy attempt identity mapping |
| `outcome.evidence` | Evidence bindings после capture |
| `kind` | `unit_specs.work_kind` |
| `parent` | Unit parent FK в пределах owning item |
| `command` | Command/check specification |
| `outputs` | Output declarations |
| `sections` | Versioned content |
| `updated_at` | Import provenance |

Эти поля присутствуют в текущей unit-схеме; особенно важно сохранить различие между actor выполнения и actor регистрации результата. [Unit schema](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/schemas/plan/v1/unit.schema.json)

### Declared и observed paths

Хранить отдельно:

```text
declared write scope
```

и:

```text
observed changed paths
```

Первое — ожидание/ограничение. Второе — факт.

Вышел за scope:

```text
policy violation или review finding
```

а не автоматическое расширение declared scope.

***

## Улучшенный JSON-контракт

Не рекомендую полностью отказываться от JSON.

Он нужен для:

- API.
- Экспорта.
- Import.
- Snapshots.
- Fixtures.
- Filesystem backend.
- Diff/review спецификаций.

Но JSON должен отражать правильное разделение.

### Specification

```json
{
  "schema": "skm.plan-specification",
  "schema_version": 2,
  "plan_id": "plan-uuid",
  "revision": {
    "id": "revision-uuid",
    "number": 8,
    "parent_id": "revision-7-uuid"
  },
  "title": "Надёжное хранение планов",
  "goal": "Поддержать локальный и серверный backend",
  "phases": [],
  "items": [],
  "units": [],
  "requirements": [],
  "decisions": [],
  "checks": [],
  "dependencies": [],
  "materials": [],
  "extensions": {}
}
```

### Runtime state

```json
{
  "schema": "skm.run-state",
  "schema_version": 1,
  "run_id": "run-uuid",
  "plan_id": "plan-uuid",
  "revision_id": "revision-uuid",
  "status": "running",
  "tasks": []
}
```

### File reference

```json
{
  "kind": "file-version",
  "file_id": "file-uuid",
  "file_version_id": "version-uuid",
  "role": "reference",
  "required": true,
  "selector": {
    "kind": "markdown-heading",
    "value": "Recovery"
  }
}
```

### Не отдавать SQL row как API

Внешняя schema не обязана совпадать с таблицей один к одному.

API DTO — стабильный контракт. SQL layout — внутренняя реализация.

Иначе любое добавление индекса или нормализация превращается в breaking API change.

***

## Совместимость backend

### Две разные подстановки

```text
Client transport:
  embedded
  HTTP

State persistence:
  filesystem
  SQLite
  PostgreSQL

Blob persistence:
  local
  object storage
```

Не смешивать всё в одном enum.

Конфигурация может выглядеть так:

```toml
[state]
access = "embedded"
driver = "sqlite"
path = "~/.local/share/skm/state.sqlite3"

[blobs]
driver = "local"
root = "~/.local/share/skm/blobs"
```

Серверный проект:

```toml
[state]
access = "http"
endpoint = "https://skm.example.com/api/v1"
credential_ref = "keyring:skm"

[execution]
worker = "local"
```

### Filesystem backend

Он должен реализовать тот же domain contract, но не обязан притворяться SQL.

При этом новый SQL дизайн не должен оставлять старый filesystem backend с молча более слабой семантикой:

```text
atomic command
optimistic version
idempotency
immutable revision
stable references
```

Гарантии либо реализуются, либо ограничение явно показывается как capability.

### SQLite

Проектные требования локального SQL adapter:

- Foreign keys включены на каждом connection.
- Ограничены и протестированы конкурентные writers.
- Есть корректный busy/retry policy.
- Не предполагается произвольный shared network filesystem.
- Migration и backup реализованы с учётом выбранного journal mode.
- Lease/claim algorithm отдельный от PostgreSQL SQL.

### PostgreSQL

Проектные требования server adapter:

- Составные FK защищают scope.
- Row locks применяются в командах публикации/claim/GC.
- Transaction retries ограничены и идемпотентны.
- Миграции контролируются по версии.
- API role не имеет неограниченных прав администратора БД.
- При необходимости RLS — дополнительный барьер, не замена domain authorization.

***

## Миграция без потерь

### Дополнительные таблицы

| Таблица | Назначение |
|---|---|
| `import_jobs` | Состояние переноса |
| `import_source_objects` | Исходные paths, bytes digest, schema, capture |
| `legacy_identity_mappings` | Старый scope/key → новый stable ID |
| `import_findings` | Ошибки и предупреждения |
| `import_object_results` | Какой target получен из source object |

### Исходники сохраняются

Для каждого JSON:

```text
source relative path
exact original bytes
bytes digest
parsed schema URI
source timestamps
imported_at
```

Не только нормализованный JSONB.

Это позволяет:

- Проверить, что ничего не потеряно.
- Повторить converter.
- Разобрать ошибку migration.
- Сохранить неизвестные поля.
- Сравнить версии converter.

### Legacy identity mapping

Особенно важно:

```text
U1
```

не уникален в плане.

Mapping:

```text
source project
source plan
source item
source local unit key
  → new unit_id
```

А не:

```text
U1 → UUID
```

### История исполнения

Если старый JSON хранит только последний `result`:

```text
импортировать last-known state
```

Не реконструировать несуществующие попытки.

Можно создать:

```text
imported historical run
imported attempt/result
provenance = legacy_snapshot
verification_level = imported_unverified
```

Если log подтверждает дополнительные события, их можно импортировать отдельно. Но не выдавать догадки за точную историю.

### Evidence paths

Для каждого пути:

```text
разрешить относительно исходного scope;
проверить containment;
проверить существование;
прочитать bytes;
создать blob/file version;
создать binding.
```

Если файла нет:

```text
missing evidence reference
```

Не создавать пустой файл-заглушку и не отмечать evidence как verified.

### Активация

```text
scan
  → source capture
  → validate
  → transform
  → import staging
  → compare
  → consistency audit
  → activate
```

Исходная папка остаётся read-only до подтверждённой успешной проверки.

***

## Проверки целостности

Нужна отдельная команда вида:

```text
skm storage verify
```

Она не должна смешиваться с обычной проверкой plan readiness.

### Уровни

| Уровень | Что проверяет |
|---|---|
| Relational | FK, scope, orphan records |
| Specification | Schema, references, DAG, typed membership |
| Execution | Attempts, leases, accepted result consistency |
| Files | Metadata, locations, availability |
| Cryptographic | Blob digests и revision manifests |
| Migration | Source/target coverage |
| Authorization | Cross-workspace bindings |
| Recovery | Незавершённые uploads, imports, deletion jobs |

### Findings

```json
{
  "code": "MISSING_BLOB_LOCATION",
  "severity": "error",
  "workspace_id": "workspace-uuid",
  "blob_id": "blob-uuid",
  "referenced_by": [
    {
      "kind": "plan-revision",
      "id": "revision-uuid"
    }
  ],
  "repairability": "restore-required"
}
```

### Не всё чинить автоматически

Автоматически допустимо:

- Удалить просроченный staging.
- Перестроить search index.
- Повторить outbox delivery.
- Пересоздать disposable materialization.

Требует решения:

- Потерян authoritative blob.
- Несовпадение digest.
- Конфликт history.
- Неоднозначный legacy identity.
- Нарушение cross-workspace scope.

***

## Тесты отказов

### Конкурентность

Обязательные сценарии:

1. Два клиента редактируют один draft.
2. Два draft публикуются от одной base revision.
3. Два worker claim одной assignment.
4. Старый worker присылает result после потери lease.
5. GC удаляет blob одновременно с созданием binding.
6. Два upload одинаковых bytes.
7. File version создаётся одновременно с trash logical file.
8. Run создаётся одновременно с новой publication.
9. Повтор command после timeout.
10. Повтор idempotency key с другим body.

### Файлы и БД

Fault injection в точках:

```text
после staging write;
после checksum;
после promotion;
до DB commit;
после DB commit;
до HTTP response;
до staging cleanup;
между удалением двух blob locations.
```

### Ревизии

- Нельзя изменить опубликованный spec.
- Нельзя вставить unit в чужую revision.
- Нельзя сослаться на item другого plan.
- Нельзя удалить identity, используемую старой revision.
- Переименование display key не меняет ID.
- Новая revision не меняет Run старой revision.
- Новая версия файла не подменяет материал старой revision.

### Review

- Review output A не принимает output B.
- Manual pending не считается fail.
- Legacy `none` не превращается незаметно в `required`.
- `ATTENTION` требует установленного решения.
- Stale receipt не принимается как fresh.
- Rework не перезаписывает предыдущую attempt.

### Migration

- Импорт повторяем.
- Original bytes сохранены.
- Число сущностей сверено.
- Все refs либо разрешены, либо явно отмечены.
- Unknown fields не потеряны.
- Missing evidence не превращено в verified.
- Исторические dates не выданы за точные timestamps.

***

## Модульная реализация

Для этого подсистемного проекта достаточно следующих владельцев:

```text
src/skm/
├── planning/
│   ├── domain/
│   ├── commands/
│   ├── queries/
│   └── ports.py
│
├── execution/
│   ├── domain/
│   ├── commands/
│   ├── recovery/
│   └── ports.py
│
├── workspaces/
│   ├── domain/
│   ├── authorization/
│   └── bindings/
│
├── files/
│   ├── domain/
│   ├── uploads/
│   ├── publication/
│   ├── materialization/
│   ├── inspection/
│   ├── gc/
│   └── ports.py
│
├── persistence/
│   ├── sql/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── transactions/
│   │   └── dialects/
│   └── filesystem/
│
├── blob_storage/
│   ├── local/
│   └── object_store/
│
├── import_export/
│   ├── legacy_v1/
│   ├── manifests/
│   └── verification/
│
└── api/
    ├── plans/
    ├── runs/
    ├── files/
    ├── uploads/
    └── workers/
```

### Главные contracts

```text
PlanningService
ExecutionService
WorkspaceAuthority
FileService

StateUnitOfWork
PlanRepository
RunRepository
FileRepository

BlobStore
UploadTransport
ContentInspector
Materializer

ImportService
ConsistencyVerifier
```

`BlobStore` не решает:

```text
кому разрешён файл;
можно ли публиковать revision;
какая версия current;
можно ли принять task.
```

Он отвечает за bytes и подтверждённые storage operations.

***

## Что реализовать сначала

Не нужно создавать все перечисленные таблицы одним большим коммитом.

### Первый вертикальный срез

```text
Workspace
  → Project
  → Plan
  → Draft
  → Published revision
  → Item
  → Unit
```

Обязательные результаты:

- Stable IDs.
- Immutable revision.
- Expected edit version.
- Conflict при устаревшем draft.
- Typed membership.
- Ревизия читается без checkout.
- SQL и API не протекают в domain.

### Второй вертикальный срез

```text
Upload
  → Staging
  → Verified blob
  → File version
  → Draft binding
  → Published revision binding
```

Обязательные результаты:

- Retry complete безопасен.
- Published revision использует pinned version.
- Переименование файла не меняет bytes.
- Новая file version не меняет старый plan.
- Сбой между bytes и SQL восстанавливается.
- Missing bytes обнаруживаются consistency check.

### Третий вертикальный срез

```text
Run
  → Task
  → Attempt
  → Output
  → Check
  → Review
  → Acceptance
```

Сначала fake executor, без платных агентных вызовов.

### Четвёртый вертикальный срез

```text
Server API
  + local worker
  + remote plan state
  + managed local execution environment
```

Это и будет ваш основной проверочный сценарий:

```text
План и материалы хранятся на сервере.

Worker работает на ноутбуке.

Код остаётся в локальном repository/worktree.

Checks и review относятся к конкретному output.

Результаты и evidence возвращаются на сервер.

После перезапуска состояние не теряется.
```

### Финальный критерий дизайна

**Изменение места хранения не меняет смысл работы.**

Один и тот же план должен сохранять:

```text
identity;
revision;
dependencies;
pinned materials;
check definitions;
review requirements;
execution history;
evidence;
author attribution.
```

Независимо от того, хранится он локально в SQLite, на сервере в PostgreSQL или передаётся через API. Именно эту семантическую совместимость следует сделать обязательным contract suite — до GUI, автоматического обучения и дополнительных интеграций.