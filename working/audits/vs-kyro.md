Да, пересечение существенное — особенно **между вашим SKM и KiroCrew**, а не только между SKM и редактором Kiro: у вас уже есть планирование, оркестрация, окружение агентов, skills, память, аналитика и управляющий интерфейс; у Crew — Gateway, агентные сессии, фоновые задачи, память и несколько способов взаимодействия с системой. [SKM README](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) · [KiroCrew Architecture](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

**Для вас я рекомендую не копировать KiroCrew целиком, а строить независимую систему управления разработкой, в центре которой — версионируемый план в выбранном хранилище, а исполнители, модели, checkout, интерфейсы и integrations подключаются отдельно.** Ниже — подробный проект такой системы: границы модулей, структура репозитория, хранение, API, исполнение, безопасность, проверки и последовательность перехода.

# SKM: целевая архитектура

## Границы этого разбора

Разбор вашего кода привязан к ревизии **`1603bfd8c988cf04505af55462c1596b5d82fde5`**, а не к состоянию репозитория из предыдущих обсуждений. [Зафиксированный коммит](https://github.com/academici/swissknifeman/commit/1603bfd8c988cf04505af55462c1596b5d82fde5)

Подтверждены текущая карта пакетов, позиционирование проекта, структура Planner и реализация его файлового хранилища; со стороны Kiro изучены предоставленная документация и архитектурный документ Crew. [SKM README](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) · [Planner](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner) · [Plan storage](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py) · [Crew Architecture](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

Это **архитектурный проект с подтверждёнными исходными точками**, но не завершённый построчный аудит всех файлов и всех страниц документации. Ниже отдельно отмечены существующее поведение, выводы из кода и предлагаемые решения; тесты проекта и платные агентные прогоны не запускались.

Все новые названия команд, API, таблиц и каталогов ниже — **проектируемый интерфейс**, а не утверждение, что он уже реализован.

## Главный архитектурный выбор

Ваш продукт стоит определить так:

> **SKM — provider-neutral control plane для управляемого исполнения планов разработки, с взаимозаменяемым хранилищем, проверяемыми результатами и независимым размещением исполнителей.**

В этой формулировке важны четыре вещи:

- **Control plane:** система управляет состоянием работы, а не просто генерирует инструкции агенту.
- **План — полноценная модель:** требования, решения, зависимости, проверки, review и история изменений связаны между собой.
- **Размещение независимо:** план может храниться на сервере, а код исполняться на ноутбуке.
- **Исполнитель заменяем:** Kiro, Claude Code, Codex или другой runtime не определяют устройство вашего ядра.

Не стоит делать главным отличием только «локально или Docker на сервере»: KiroCrew уже описывает локальный и удалённый запуск, Docker, Gateway и сохранение состояния между сессиями. [KiroCrew](https://github.com/kirodotdev/KiroCrew)

Ваша потенциально сильная специализация — **не место запуска, а строгая модель инженерной работы**: какой пункт выполняется, по какой версии требований, какие доказательства собраны, кто проверил результат и почему система считает его завершённым.

***

## Где пересекаются системы

### Разные значения harness

Здесь необходимо сначала договориться о терминах.

В текущем SKM пакет `harness` отвечает за окружение агентных клиентов: разрешения, MCP, hooks, agent packs и инструкции. [SKM: Packages](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md)

В архитектуре Crew **ACP harness — это runtime**, который владеет связью с моделью, инструментами, контекстом и агентной сессией; сам Crew находится выше него как Gateway. [Crew: Architecture Overview](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

Поэтому выражение «harness управляет оркестратором» у вас сейчас может смешивать разные обязанности.

Я предлагаю разделить их так:

| Компонент | Его ответственность | Чего он не делает |
|---|---|---|
| Control plane | Планы, запуски, политики, approvals, состояние | Не редактирует код самостоятельно |
| Orchestrator | Выбирает следующий допустимый шаг | Не хранит собственную альтернативную правду о плане |
| Worker | Получает задание, готовит среду, запускает runtime | Не решает самовольно, что весь план завершён |
| Agent runtime | Ведёт агентную сессию, вызывает модель и инструменты | Не владеет глобальной историей проекта |
| Environment projection | Создаёт конфигурацию конкретного клиента | Не содержит бизнес-логику плана |
| Surface | CLI, GUI, MCP, HTTP | Не обходит application commands |

**Первое изменение терминологии:** нынешний `harness` логически переименовать в **environment / client integration**, а runtime-интеграции выделить отдельно.

Переименование пакета необязательно делать первым коммитом. Сначала нужно провести границу в коде.

### Предметное пересечение

| Область | Что уже заявлено в SKM | Что есть в Crew | Что делать в целевой системе |
|---|---|---|---|
| Планы | JSON-планы, phases, items, decisions, checks. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | TaskRunner: specification, decomposition, execution, retry, replan, checkpoint. [Crew](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md) | Сделать план главным доменным объектом, отдельно от запуска |
| Оркестрация | Узкие роли scout, executor, reviewer, triager. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | Сессии, subagents, TaskRunner, cron, heartbeat. [Crew](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md) | Сохранить специализацию ролей, добавить durable execution |
| Окружение | Permissions, MCP, hooks, packs, инструкции. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | Конфигурация выбранного ACP backend и независимый tool gate. [Crew](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md) | Разделить projection и enforcement |
| Память | `maind`, общий memory hub и code graph. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | Cross-session memory, lessons, retrieval. [Crew](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md) | Не смешивать память с authoritative state |
| Обучение | `analyst`, candidate lessons и ручное promotion. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | Lessons и reusable skills. [Crew](https://github.com/kirodotdev/KiroCrew) | Оставить контролируемое promotion |
| Интерфейсы | Desktop/browser control plane. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | CLI, dashboard, desktop, messaging. [Crew](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md) | Один application API для всех surfaces |
| Размещение | README определяет SKM как локальный control layer. [SKM](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md) | Gateway работает на контролируемом пользователем локальном или удалённом хосте. [Crew](https://github.com/kirodotdev/KiroCrew) | Добавить серверный control plane и независимые workers |

**Вывод:** пересечение большое по набору подсистем. Но это не означает, что нужно переносить устройство Crew один в один.

***

## Что брать у Kiro

В документации Kiro хорошо просматривается продуктовая декомпозиция: specs, steering, hooks, MCP, permissions, custom agents, skills, powers и subagents — разные механизмы, а не один универсальный конфигурационный файл. [kiro](https://kiro.dev/docs/)

Для SKM полезно заимствовать **эти различия в ответственности**.

| Идея | Как применить в SKM |
|---|---|
| Specs | Разделить требования, проектирование и исполняемый план |
| Steering | Отдельные правила проекта, выбираемые по scope и контексту |
| Skills | Переиспользуемые инструкции с версией и происхождением |
| Hooks | Реакции на события, но не замена state machine |
| Custom agents | Ролевые профили, а не жёстко зашитые роли в engine |
| Powers / integration bundles | Пакет интеграции: инструкции, инструменты, конфигурация |
| Unified configuration | Один canonical project config с provider projections |
| Checkpoints | Отдельные контрольные точки workflow, сессии и рабочего дерева |
| Compaction | Управляемая сборка контекста, не «добавить всё в prompt» |

Это проектное сопоставление, а не обещание побитовой совместимости с форматами Kiro.

### Что брать у Crew

В архитектуре Crew особенно полезны три идеи: Gateway отдельно от runtime, capability-aware provider seam и разделение общих обязательных механизмов от пользовательских приложений. [Crew Architecture](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

Из этого для вас следуют конкретные решения:

1. **Не давать UI владеть workflow.**
2. **Не давать runtime владеть планом.**
3. **Не давать plugin подменять обязательную security policy.**
4. **Не расписывать provider-specific ветвления по всем модулям.**
5. **Не считать агентную сессию единицей долговечности плана.**

### Что не копировать

Документ Crew прямо отмечает, что установленный Python app исполняется в процессе Gateway и его permissions не ограничивают произвольный Python-доступ к памяти, filesystem и сети. [Crew: The app boundary](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

Для SKM я бы сделал более консервативный старт:

- Встроенные модули — доверенный код.
- Skills и шаблоны — данные.
- Внешние tools — отдельные процессы.
- Недоверенные backend plugins — **не загружать в процесс control plane**.
- Runtime adapters — явный allowlist и compatibility tests.
- Произвольный plugin marketplace — отложить.

Также вам пока не нужны десятки каналов общения, desktop pet, meeting tools или большой набор встроенных приложений. Это расширяет продукт, но не улучшает надёжность выполнения плана.

***

## Что мешает сейчас

Я бы не называл текущий SKM примитивным: по README у него уже десять функциональных пакетов и выраженная provider-neutral направленность. [SKM Packages](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md)

Проблема для следующего этапа — **не недостаток функций, а слишком близкое расположение доменной модели, файлового layout, локального checkout и способов интеграции**.

### План знает filesystem

Текущий `Plan` содержит `root: Path`, методы вычисления путей документов и свойства определения исходного checkout. [store.py](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Для файлового инструмента это понятно. Для взаимозаменяемых filesystem/database/API backend это неудачная граница.

**Предлагаемая замена:**

```python
@dataclass(frozen=True)
class PlanSnapshot:
    plan_id: PlanId
    revision_id: RevisionId
    schema_version: int
    specification: PlanSpecification
```

В `PlanSnapshot` не должно быть:

```text
root
repo_root
plans_root
item_path()
phase_path()
knowledge/*.json
```

Пути принадлежат filesystem adapter. Привязка к checkout — workspace binding.

### Сохранение не равно транзакции

В `save_many()` все документы сначала валидируются и подготавливаются, затем целевые файлы заменяются последовательно; при исключении выполняется best-effort восстановление уже заменённых файлов. [store.py: save_many / _write_all](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Из этого следует ограничение: **обработка исключения в работающем процессе не обеспечивает атомарность всей группы при аварийном завершении между заменами**. Это архитектурный вывод из последовательности операций, а не результат проведённого crash test. [store.py](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Отдельно журнал событий дописывается через `append_log()` в `log.jsonl`. [store.py: append_log](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Поэтому будущий контракт должен требовать:

> Изменение состояния, соответствующие события и idempotency receipt фиксируются одной логической транзакцией.

Нельзя просто написать SQL-аналог `save()` и считать задачу решённой.

### Идентичность связана с layout

Функции `phase_path()`, `item_path()` и `unit_path()` кодируют устройство каталога непосредственно в способе адресации объектов. [store.py: paths](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

В целевой модели нужно разделить:

```text
entity_id       стабильная идентичность
display_key     P1.2 / U1 — отображаемый номер
sort_order      положение в плане
storage_locator внутренняя деталь adapter
```

Переименование фазы или перенос пункта не должны менять его идентичность.

### Checkout слишком близко

Свойство `repo_root` текущего `Plan` выдаёт ошибку, если для плана не найден локально привязанный checkout. [store.py: Plan.repo_root](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Для выполнения проверки это разумная ошибка. Для чтения плана, редактирования требований, review архитектуры или просмотра истории отсутствие checkout не должно быть препятствием.

**Новое правило:** checkout требуется не плану, а конкретной execution capability.

***

## Независимые оси конфигурации

Это центральное решение всего проекта.

Не должно быть одного параметра:

```toml
mode = "cloud"
```

Он слишком многое смешивает.

Нужны независимые оси:

| Ось | Варианты |
|---|---|
| Доступ к состоянию | Embedded service или HTTP service |
| Хранение состояния | Filesystem, SQLite, PostgreSQL |
| Исполнение | Локальный worker, серверный worker, выбранный worker pool |
| Agent runtime | Kiro, Claude Code, Codex, другие adapters |
| Рабочее дерево | Существующий checkout, отдельный worktree, подготовленный clone |
| Артефакты | Локальный blob store или серверное object storage |

### Поддерживаемые сценарии

| Сценарий | План | Исполнитель | Где код |
|---|---|---|---|
| Полностью локальный | Filesystem | Локальный worker | Локальный checkout |
| Локальная БД | SQLite | Локальный worker | Локальный worktree |
| Сервер хранит планы | PostgreSQL через API | Локальный worker | На ноутбуке |
| Полностью серверный | PostgreSQL через API | Серверный worker | Серверный isolated checkout |
| Смешанный | PostgreSQL через API | Выбранный worker | На соответствующем хосте |

**Ключевой сценарий для приёмки:**

```text
Один CLI / один GUI

Проект A:
  plans.driver = filesystem
  runtime = claude

Проект B:
  plans.driver = http
  runtime = kiro
  worker = laptop

Проект C:
  plans.driver = database
  runtime = codex

Команды и типы результатов одинаковые.
```

Filesystem, database и HTTP должны поддерживаться параллельно как реализации. Это не последовательные стадии «сначала локально, потом всё переписать под облако».

***

## Логическая архитектура

Предлагаю **модульный монолит с отдельным worker-процессом**, а не микросервисы.

```text
CLI ─────────────┐
GUI ─────────────┤
MCP surface ─────┤
HTTP API ────────┘
                 │
                 ▼
       Application commands / queries
                 │
       ┌─────────┼──────────┐
       ▼         ▼          ▼
    Planning  Execution    Policy
       │         │          │
       └─────────┼──────────┘
                 │
       State repositories + UoW
                 │
         Filesystem / SQL

                 │
       Durable work assignments
                 │
                 ▼
              Worker
                 │
       ┌─────────┼────────────┐
       ▼         ▼            ▼
    Runtime   Workspace     Sandbox
    adapter   adapter       adapter
       │
       ▼
 Kiro / Claude / Codex / ...

Context, skills, templates, knowledge и learning
подключаются к этим потокам через явные contracts.
```

### Почему не микросервисы

Для вашего текущего масштаба я не вижу необходимости сразу выделять отдельные сервисы для planning, memory, skills, review, scheduling и analytics.

Разделение должно сначала существовать **в зависимостях и контрактах**, а не в Docker Compose.

Начальный server deployment:

```text
skm-api
skm-worker
postgres
```

Дополнительно:

```text
object storage — когда действительно нужны большие артефакты
reverse proxy — для HTTPS и внешнего доступа
```

Без обязательных Redis, Kafka, Kubernetes и отдельной vector database в первом релизе.

***

## Слои и зависимости

### Domain

В этом слое находятся:

- Сущности и value objects.
- Допустимые переходы состояний.
- Проверка зависимостей.
- Правила review.
- Инварианты завершения.
- Правила принятия результатов.
- Доменные события.

Domain не импортирует:

```text
FastAPI
SQLAlchemy
requests/httpx
Path для адресации хранилища
subprocess
provider-specific SDK
GUI framework
```

Обычный `Path` может существовать в модели технического входа проверки, но не как способ найти план.

### Application

Содержит сценарии:

```text
CreatePlan
RevisePlan
ValidatePlan
ApprovePlanRevision
StartRun
ClaimAssignment
RecordAttemptResult
RequestReview
AcceptReview
CompleteUnit
PauseRun
ResumeRun
CancelRun
ExportPlan
ImportPlan
```

Application:

1. Проверяет actor и доступ.
2. Загружает необходимые объекты.
3. Вызывает domain logic.
4. Фиксирует изменения через UoW.
5. Создаёт события и outbox records.
6. Возвращает типизированный результат.

Здесь нет provider-specific prompt string и SQL-запросов.

### Ports

Ports определяются потребностями application, а не удобством конкретного backend:

```text
PlanRepository
RunRepository
WorkQueue
UnitOfWork
ArtifactStore
AgentRuntime
WorkspaceManager
PolicyAuthority
ContextRetriever
SecretResolver
Clock
IdGenerator
```

Не надо создавать отдельный interface для каждой маленькой функции. Port нужен там, где действительно меняется внешняя реализация.

### Adapters

Здесь находятся:

```text
filesystem persistence
SQL persistence
HTTP client
Kiro ACP
Claude runtime integration
Codex runtime integration
Git worktree management
sandbox implementation
MCP transport
Obsidian export
```

### Entrypoints

Только разбор входа и представление результата:

```text
CLI argument → command DTO → application → output
HTTP body → command DTO → application → response
MCP call → command DTO → application → response
```

**Запрет:** endpoint или CLI handler самостоятельно меняет статус пункта в БД или JSON.

***

## Структура репозитория

Я бы сохранил monorepo, но отказался от необходимости держать каждый внутренний модуль как отдельный устанавливаемый пакет.

Начальная целевая структура:

```text
swissknifeman/
├── pyproject.toml
├── README.md
├── LICENSE
├── AGENTS.md
│
├── src/
│   └── skm/
│       ├── kernel/
│       │   ├── ids.py
│       │   ├── errors.py
│       │   ├── actor.py
│       │   ├── events.py
│       │   ├── clock.py
│       │   └── versions.py
│       │
│       ├── modules/
│       │   ├── planning/
│       │   │   ├── domain/
│       │   │   │   ├── plan.py
│       │   │   │   ├── specification.py
│       │   │   │   ├── revision.py
│       │   │   │   ├── requirement.py
│       │   │   │   ├── work_item.py
│       │   │   │   ├── unit.py
│       │   │   │   ├── dependency.py
│       │   │   │   ├── decision.py
│       │   │   │   ├── validation.py
│       │   │   │   └── events.py
│       │   │   ├── application/
│       │   │   │   ├── commands.py
│       │   │   │   ├── queries.py
│       │   │   │   ├── service.py
│       │   │   │   └── import_export.py
│       │   │   ├── ports.py
│       │   │   └── public.py
│       │   │
│       │   ├── execution/
│       │   │   ├── domain/
│       │   │   │   ├── run.py
│       │   │   │   ├── assignment.py
│       │   │   │   ├── attempt.py
│       │   │   │   ├── review.py
│       │   │   │   ├── checks.py
│       │   │   │   ├── budget.py
│       │   │   │   ├── lease.py
│       │   │   │   └── transitions.py
│       │   │   ├── application/
│       │   │   │   ├── orchestrator.py
│       │   │   │   ├── dispatcher.py
│       │   │   │   ├── result_handler.py
│       │   │   │   ├── recovery.py
│       │   │   │   └── cancellation.py
│       │   │   ├── worker/
│       │   │   │   ├── loop.py
│       │   │   │   ├── executor.py
│       │   │   │   ├── heartbeat.py
│       │   │   │   └── checks_runner.py
│       │   │   ├── ports.py
│       │   │   └── public.py
│       │   │
│       │   ├── policy/
│       │   │   ├── model.py
│       │   │   ├── evaluator.py
│       │   │   ├── approvals.py
│       │   │   ├── tool_intents.py
│       │   │   ├── audit.py
│       │   │   ├── ports.py
│       │   │   └── public.py
│       │   │
│       │   ├── context/
│       │   │   ├── assembly.py
│       │   │   ├── selection.py
│       │   │   ├── provenance.py
│       │   │   ├── materials.py
│       │   │   ├── memory.py
│       │   │   ├── ports.py
│       │   │   └── public.py
│       │   │
│       │   ├── extensions/
│       │   │   ├── registry.py
│       │   │   ├── manifests.py
│       │   │   ├── skills.py
│       │   │   ├── templates.py
│       │   │   ├── steering.py
│       │   │   ├── agent_profiles.py
│       │   │   ├── integrations.py
│       │   │   └── public.py
│       │   │
│       │   └── learning/
│       │       ├── candidates.py
│       │       ├── evaluation.py
│       │       ├── promotion.py
│       │       ├── deprecation.py
│       │       └── public.py
│       │
│       ├── adapters/
│       │   ├── persistence/
│       │   │   ├── filesystem/
│       │   │   │   ├── backend.py
│       │   │   │   ├── manifest.py
│       │   │   │   ├── locking.py
│       │   │   │   ├── recovery.py
│       │   │   │   └── legacy_v4.py
│       │   │   └── sql/
│       │   │       ├── backend.py
│       │   │       ├── models.py
│       │   │       ├── repositories.py
│       │   │       ├── uow.py
│       │   │       ├── queue.py
│       │   │       └── dialects.py
│       │   │
│       │   ├── clients/
│       │   │   └── http/
│       │   │       ├── client.py
│       │   │       ├── auth.py
│       │   │       └── retry.py
│       │   │
│       │   ├── runtimes/
│       │   │   ├── acp/
│       │   │   │   ├── transport.py
│       │   │   │   ├── protocol.py
│       │   │   │   └── events.py
│       │   │   ├── kiro/
│       │   │   │   ├── runtime.py
│       │   │   │   ├── capabilities.py
│       │   │   │   └── projection.py
│       │   │   ├── claude/
│       │   │   ├── codex/
│       │   │   ├── cursor/
│       │   │   └── grok/
│       │   │
│       │   ├── workspaces/
│       │   │   ├── existing_checkout.py
│       │   │   ├── git_worktree.py
│       │   │   └── managed_clone.py
│       │   ├── sandboxes/
│       │   ├── artifacts/
│       │   ├── knowledge/
│       │   └── exports/
│       │       ├── markdown.py
│       │       └── obsidian.py
│       │
│       ├── entrypoints/
│       │   ├── cli/
│       │   ├── api/
│       │   ├── mcp/
│       │   └── worker/
│       │
│       └── bootstrap/
│           ├── config.py
│           ├── composition.py
│           ├── providers.py
│           └── lifecycle.py
│
├── web/
│   ├── src/
│   └── package.json
│
├── resources/
│   ├── templates/
│   ├── skills/
│   ├── steering/
│   ├── agents/
│   └── integrations/
│
├── schemas/
│   ├── api/
│   ├── plan/
│   ├── events/
│   ├── extensions/
│   └── config/
│
├── migrations/
│   ├── sql/
│   └── data/
│
├── tests/
│   ├── unit/
│   ├── contracts/
│   ├── integration/
│   ├── architecture/
│   ├── recovery/
│   ├── security/
│   ├── migration/
│   ├── e2e/
│   └── evals/
│
├── deploy/
│   ├── docker/
│   ├── compose.yaml
│   └── examples/
│
└── docs/
    ├── architecture/
    ├── adr/
    ├── contracts/
    ├── operations/
    └── migrations/
```

Это **карта целевых владельцев**, а не требование сразу создать все эти файлы.

Первый вертикальный срез должен создать только то, что реально использует: planning, один application command, filesystem adapter, CLI и contract tests.

### Правила дерева

- В `kernel` нельзя складывать всё общее.
- В `public.py` находится поддерживаемый межмодульный интерфейс.
- Один модуль не импортирует private internals другого.
- Runtime adapter содержит свою специфику в своей папке.
- Общий ACP transport не знает про бизнес-логику Kiro.
- Шаблоны и skills не лежат вперемешку с orchestration engine.
- Сгенерированные provider projections не редактируются как canonical source.
- У каждого ресурса есть владелец, schema version и provenance.

***

## Судьба текущих пакетов

В текущем README назначение пакетов уже довольно хорошо разделено; рефакторинг должен сохранить полезные функции, но изменить границы владения. [SKM Packages](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md)

| Сейчас | Целевая роль | Что не переносить механически |
|---|---|---|
| `aicore` | Небольшой kernel, bootstrap, config и contracts | Всеобщую зависимость от растущего «центра всего» |
| `planner` | Planning domain и application | Filesystem paths внутри модели |
| `orch` | Execution control и worker | Собственный альтернативный статус плана |
| `harness` | Environment projections, runtime configuration, policy bindings | Security policy, реализованную только текстом инструкции |
| `skiller` | Extension registry и доставка skills | Зависимость engine от способа установки skill |
| `workspace` | Project registry и workspace bindings | Требование локального checkout для чтения плана |
| `maind` | Context, memory, knowledge adapters | Владение состоянием выполнения |
| `analyst` | Learning pipeline | Автоматическое изменение обязательных политик |
| `brain` | Optional Obsidian/Markdown projection | Второй authoritative store |
| `gui` | Клиент application API | Прямой доступ к JSON, SQL и orchestration internals |

Главная экономия сложности получится не от уменьшения числа директорий, а от удаления **сквозных зависимостей между этими обязанностями**.

***

## План как доменная модель

### Разделить три объекта

Нельзя хранить «план и всё происходящее» одним постоянно изменяемым документом.

Нужны:

```text
Plan
  стабильная идентичность

PlanRevision
  неизменяемая версия замысла и структуры работы

Run
  конкретное исполнение выбранной ревизии
```

Пример:

```text
Plan: внедрение авторизации

Revision 7:
  утверждённые требования и DAG

Run A:
  локальный запуск Claude
  остановлен после проверки

Run B:
  серверный запуск Kiro
  использует ту же Revision 7

Revision 8:
  изменены требования

Run C:
  отдельный запуск Revision 8
```

**Запущенный Run не должен незаметно переключаться на новую редакцию плана.**

### Состав спецификации

```text
PlanSpecification
├── brief
├── requirements
├── design
├── decisions
├── phases
├── work_items
├── units
├── dependencies
├── verification_requirements
├── review_requirements
├── material_references
└── execution_constraints
```

План определяет **что требуется**. Запуск хранит **что происходило**.

### Идентичность

Предлагаемые идентификаторы:

```text
plan_id
revision_id
requirement_id
item_id
unit_id
run_id
assignment_id
attempt_id
review_id
artifact_id
```

Отображаемые `PLAN3`, `P2.4`, `U1` остаются как aliases.

Внешний API не должен полагаться на то, что `P2.4` одновременно означает положение, уникальный ID и путь файла.

### Требования и traceability

Каждый исполняемый unit должен ссылаться на требования:

```json
{
  "unit_id": "unit-auth-refresh",
  "display_key": "P2.4/U1",
  "requirement_refs": [
    "req-session-refresh"
  ],
  "acceptance_criteria": [
    {
      "id": "ac-refresh-rotation",
      "statement": "Использованный refresh token нельзя применить повторно"
    }
  ]
}
```

Нужна проверяемая цепочка:

```text
Requirement
  → Unit
  → Acceptance criterion
  → Check / Review
  → Evidence
  → Accepted result
```

Если критерий не связан ни с проверкой, ни с review, план ещё не готов к исполнению.

***

## Review и завершение

В последнем зафиксированном коммите уже добавлены ограничение rework rounds и остановка на ручной проверке без verdict вместо расходования correction budget. Это важные свойства, которые следует сохранить отдельными инвариантами новой модели. [Коммит `1603bfd`](https://github.com/academici/swissknifeman/commit/1603bfd8c988cf04505af55462c1596b5d82fde5)

### Review — обязательный контракт

Для каждого unit предлагаю обязательный блок:

```json
{
  "review": {
    "mode": "required",
    "profile": "code-review",
    "independence": "separate-session",
    "max_rounds": 2,
    "required_evidence": [
      "diff",
      "checks",
      "acceptance-coverage"
    ]
  }
}
```

Число rounds здесь — пример настройки, не универсальный норматив.

Если review действительно не нужен:

```json
{
  "review": {
    "mode": "waived",
    "reason": "Изменение только отображаемого названия",
    "approved_by": "human:dmitry"
  }
}
```

**Отсутствие поля не равно освобождению от review.**

### Разные уровни проверки

| Уровень | Что проверяет |
|---|---|
| Unit review | Корректность ограниченного изменения |
| Item review | Совместимость нескольких units |
| Phase review | Выполнение цели этапа |
| Plan acceptance | Выполнение исходных требований |
| Security review | Специальные риски независимо от функционального успеха |

Не обязательно вызывать модель на каждом уровне. Часть gates может быть детерминированной.

### Что означает done

Предлагаемый domain invariant:

```text
Unit accepted, только если:

есть результат текущей попытки;
результат относится к правильной ревизии;
обязательные automated checks прошли;
ручные проверки имеют verdict;
review принят либо явно waived;
доказательства сохранены;
policy не запрещает принятие;
результат не отменён и не устарел.
```

Агент не может завершить unit сообщением «готово».

### Ручная проверка

Не смешивать:

```text
failed check
pending manual check
infrastructure error
unknown result
```

Например:

```text
manual_pending
  → не запускает correction loop;
  → не считается fail;
  → показывает, кто должен проверить;
  → может иметь deadline;
  → после verdict продолжает workflow.
```

Иначе система будет «исправлять» отсутствие человека.

***

## Хранилища и contracts

### Внешний контракт

Consumers должны работать через один client-facing интерфейс:

```python
class PlanningClient(Protocol):
    async def execute(
        self,
        command: PlanningCommand,
        *,
        idempotency_key: str,
    ) -> CommandResult: ...

    async def query(
        self,
        query: PlanningQuery,
    ) -> QueryResult: ...
```

Реализации:

```text
EmbeddedPlanningClient
  → local application service
  → filesystem или SQL

HttpPlanningClient
  → remote application service
  → server-selected persistence
```

Это важная тонкость:

> **HTTP — не ещё один SQL dialect и не просто repository с сетевыми CRUD-вызовами.**

### Почему не remote UoW

Не рекомендую строить такой поток:

```text
client opens transaction
  → GET plan
  → PATCH item
  → POST event
  → COMMIT
```

Обрыв сети между этими операциями создаст слишком много неопределённости.

Нужно:

```text
POST CompleteUnit
  → сервер сам проверяет инварианты
  → сервер сам выполняет транзакцию
  → клиент получает итог
```

На сервере используются те же application handlers, что и в embedded mode.

### Внутренний контракт

```python
class PlanRepository(Protocol):
    def get(
        self,
        plan_id: PlanId,
    ) -> PlanAggregate: ...

    def save(
        self,
        plan: PlanAggregate,
        *,
        expected_version: int,
    ) -> None: ...


class UnitOfWork(Protocol):
    plans: PlanRepository
    runs: RunRepository
    events: EventRepository
    outbox: OutboxRepository
    idempotency: IdempotencyRepository

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

Это эскиз границ. Конкретный sync/async стиль нужно выбрать единообразно после оценки текущего кода, а не смешивать произвольно.

### Гарантии всех backend

| Гарантия | Filesystem | SQL | HTTP |
|---|---|---|---|
| Проверка schema | Обязательна | Обязательна | На сервере |
| Optimistic concurrency | Обязательна | Обязательна | Через expected version |
| State + events атомарны | Обязательны | Обязательны | Серверная транзакция |
| Idempotency | Обязательна | Обязательна | Ключ передаётся серверу |
| Отсутствие зависимости от checkout | Обязательно | Обязательно | Обязательно |
| Export/import | Общий формат | Общий формат | Общий формат |
| Контрактные тесты | Общий suite | Общий suite | Общий suite |

Если filesystem backend не может обеспечить нужную гарантию, нельзя молча объявить его «почти совместимым». Нужно либо реализовать гарантию, либо явно ограничить capability.

***

## Filesystem backend

У вас уже есть canonical JSON, schema validation, locking и атомарная замена отдельных файлов — это полезная база, а не код, который обязательно нужно выбросить. [store.py](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan/store.py)

Но для нового контракта я предлагаю перестать использовать множество изменяемых JSON как независимые authoritative records.

### Новая организация

```text
project-state/
├── CURRENT
├── manifests/
│   ├── generation-000041.json
│   └── generation-000042.json
├── objects/
│   ├── <content-hash>
│   └── <content-hash>
├── locks/
│   └── project.lock
└── views/
    ├── plan.md
    └── graph.json
```

Идея:

- Objects неизменяемые.
- Manifest описывает согласованный набор records.
- `CURRENT` указывает на принятую generation.
- Views производные и восстанавливаемые.
- Writer сериализуется на уровне проекта.
- Reader читает одну согласованную generation.

### Порядок commit

```text
1. Получить project lock.
2. Перечитать CURRENT.
3. Проверить expected versions.
4. Выполнить command.
5. Валидировать изменённые records.
6. Записать новые immutable objects.
7. Записать новый manifest.
8. Синхронизировать необходимые записи.
9. Атомарно переключить CURRENT.
10. Освободить lock.
```

В manifest входят и изменения состояния, и ссылки на новые события, и idempotency receipt.

Если процесс упал до переключения `CURRENT`, новая generation не считается принятой. Если после — reader видит новую согласованную generation.

### Ограничения

Для первого filesystem backend предлагаю честную область применения:

- Один хост.
- Один writer на проект в каждый момент.
- Без обещания корректной работы на произвольном сетевом filesystem.
- Без прямого редактирования authoritative objects пользователем.
- Без distributed worker coordination через общую папку.

Ручное редактирование — через export/edit/import или отдельный structured editor с validation.

Это дороже текущего layout по реализации, но сохраняет реальную взаимозаменяемость с БД.

**Более простой путь:** оставить текущий layout как `legacy_v4` importer и compatibility reader, а новый runtime state по умолчанию перевести на SQLite. Filesystem при этом остаётся поддерживаемым backend, но его transactional implementation делается отдельной задачей, а не имитацией SQL.

***

## Реляционная модель

Я рекомендую SQL backend с двумя первоначальными целями:

```text
SQLite      локальный embedded mode
PostgreSQL  серверный mode
```

Общий application contract не означает, что SQL и locking должны быть одинаковыми. Различия остаются внутри adapter.

### Основные таблицы

| Таблица | Назначение |
|---|---|
| `projects` | Идентичность проекта |
| `project_memberships` | Доступ actors к проекту |
| `plans` | Идентичность плана, указатели на ревизии |
| `plan_revisions` | Неизменяемые редакции спецификации |
| `requirements` | Требования в рамках revision |
| `work_items` | Пункты плана в рамках revision |
| `units` | Исполняемые единицы в рамках revision |
| `dependency_edges` | Зависимости между units |
| `decisions` | Решения и основания |
| `material_refs` | Привязка материалов к revision/unit |
| `runs` | Запуски конкретной revision |
| `run_units` | Текущее состояние unit внутри run |
| `assignments` | Выданная работа |
| `attempts` | Попытки исполнения |
| `check_results` | Результаты проверок |
| `reviews` | Review и verdict |
| `approvals` | Человеческие разрешения |
| `workers` | Worker identity и capabilities |
| `leases` | Владение assignment |
| `artifacts` | Метаданные evidence и blobs |
| `events` | Долговечные доменные события |
| `outbox` | События для внешней доставки |
| `idempotency_receipts` | Результаты повторяемых commands |

Это целевая модель. Не все таблицы нужны в первом вертикальном срезе.

### Не JSON blob вместо БД

Не стоит делать только:

```sql
plans (
    id TEXT,
    document JSON
)
```

Так можно сохранить snapshot, но этого недостаточно для нормальной работы с зависимостями, review, очередью, историей запусков и конкурентными изменениями.

Практичный компромисс:

- Реляционные поля для идентичности, связей, статусов и индексов.
- Immutable JSON payload для полной воспроизводимой спецификации revision.
- Явная одна authoritative форма каждого значения.
- Производные поисковые таблицы можно пересоздать.

Нельзя хранить два независимо редактируемых статуса — один в JSON и один в колонке.

### Ограничения целостности

Обязательные constraints:

```text
plan_revision принадлежит существующему plan;
run ссылается на существующую immutable revision;
dependency не пересекает revision;
unit принадлежит той же revision, что и run;
review связан с конкретным attempt/result;
artifact привязан к owner и project;
idempotency key уникален в определённом scope;
lease имеет монотонный fencing token.
```

Полезные индексы:

```text
runs(project_id, status, created_at)
run_units(run_id, status)
assignments(status, available_at)
leases(expires_at)
events(project_id, sequence)
events(run_id, sequence)
reviews(run_id, unit_id, status)
```

### Четыре разных версии

Не смешивать:

```text
schema_version
  версия формата данных

revision_number
  версия спецификации плана

row_version / aggregate_version
  optimistic concurrency

event_sequence
  порядок событий
```

`updated_at` не заменяет ни одну из них.

***

## Долговечное исполнение

### Оркестратор — не главный агент

Я рекомендую **детерминированный orchestration engine с агентными шагами**, а не один LLM-supervisor, который самостоятельно ведёт workflow.

```text
Engine:
  определяет допустимый переход;
  выбирает ready units;
  выдаёт assignment;
  принимает результат;
  запускает review;
  ограничивает retries;
  фиксирует состояние.

Agent:
  исследует;
  предлагает;
  изменяет код;
  анализирует diff;
  возвращает structured result.
```

LLM может предложить новый план. Но не должен обходить правила переходов.

### State machine запуска

```text
created
  → validating
  → ready
  → running
  → waiting_approval
  → paused
  → succeeded
  → failed
  → cancelled
```

Это не линейная цепочка: часть переходов возвратная, часть terminal.

Для каждого перехода требуется таблица:

```text
from
command
preconditions
to
events
required permission
idempotency behavior
```

### State machine unit

```text
blocked
  → ready
  → assigned
  → executing
  → checking
  → manual_pending
  → reviewing
  → accepted
```

Отдельные исходы:

```text
rework_required
failed
cancelled
superseded
```

Не надо кодировать все исходы комбинацией `done=true`, `failed=false`, `reviewed=true`.

### Attempt — отдельная сущность

Каждый повтор создаёт новую попытку:

```text
Unit
  Attempt 1 → checks failed
  Attempt 2 → review rejected
  Attempt 3 → accepted
```

Старые результаты не перезаписываются.

Это позволяет понять:

- Что именно исправлялось.
- Кто исполнял.
- Какой контекст использовался.
- Почему предыдущая попытка отклонена.
- Какой результат сейчас принят.

***

## Leases и восстановление

### Почему недостаточно running

Если запись просто меняется на `running`, после падения процесса непонятно:

```text
задача ещё идёт;
процесс умер;
сеть пропала;
агент завис;
результат уже получен, но не записан.
```

Предлагаемый assignment:

```text
assignment_id
run_id
unit_id
attempt_id
worker_id
lease_expires_at
fencing_token
status
```

### Протокол worker

```text
1. Claim assignment.
2. Получить lease и fencing token.
3. Подготовить isolated workspace.
4. Начать выполнение.
5. Продлевать lease.
6. Сохранять evidence.
7. Отправить result с fencing token.
8. Сервер проверяет актуальность владения.
9. Сервер принимает или отклоняет результат.
```

### Важное ограничение fencing

Fencing token защищает принятие результата и операции, которые проверяют этот token.

Он **сам по себе не останавливает старый процесс** и не мешает ему продолжать писать в общий checkout или вызывать внешний API.

Поэтому обязательно:

- Отдельный workspace на attempt.
- Запрет общей рабочей директории для конкурирующих attempts.
- Интеграция результата только через проверяемый acceptance step.
- Heartbeat failure переводит worker в режим остановки.
- Внешние side effects имеют отдельную policy.
- Credentials по возможности короткоживущие и ограниченные.

### После потери lease

```text
lease expired
  → assignment lost
  → попытка помечается как ownership_lost
  → stale result не принимается
  → новая попытка получает новый workspace
```

Не надо автоматически считать, что старое выполнение ничего не успело сделать.

### Exactly once не обещать

Для внешних действий:

```text
создание PR;
отправка сообщения;
публикация пакета;
изменение инфраструктуры
```

нужен отдельный tool-intent protocol:

```text
intent created
  → approval, если требуется
  → executing
  → receipt recorded
```

Если процесс упал после внешнего действия, но до receipt:

```text
status = outcome_unknown
```

Далее — reconciliation или ручная проверка, а не слепой повтор.

***

## Checkpoints разных типов

Нельзя называть checkpoint всем сразу.

| Тип | Содержит | Что позволяет |
|---|---|---|
| Workflow checkpoint | State machine, completed steps, pending assignments | Продолжить orchestration |
| Workspace checkpoint | Commit, worktree state, patch, environment refs | Восстановить рабочее дерево |
| Session checkpoint | Runtime session reference и доступный transcript | Продолжить разговор, если runtime умеет |
| Context checkpoint | Manifest использованного контекста | Воспроизвести вход шага |
| Artifact checkpoint | Хеши evidence | Проверить неизменность результатов |

Особенно важно:

> Возможность продолжить workflow не должна зависеть от возможности восстановить старую агентную сессию.

Если runtime не умеет resume, worker создаёт новую сессию из durable task state и сохранённого контекста.

***

## Runtime adapters

### Два разных каталога

Предлагаю разделить:

```text
ClientIntegration
  как настроить пользовательский клиент:
  инструкции, команды, skills, permissions projection

AgentRuntime
  как запустить и контролировать сессию:
  start, stream, cancel, resume, result
```

Например, интеграция с редактором может существовать без unattended execution adapter.

Это не должно считаться ошибкой.

### Контракт runtime

```python
class AgentRuntime(Protocol):
    def capabilities(self) -> RuntimeCapabilities: ...

    async def start(
        self,
        request: AgentRequest,
    ) -> RuntimeSession: ...

    async def cancel(
        self,
        session: RuntimeSession,
    ) -> CancellationResult: ...
```

Поток runtime нормализуется:

```text
session_started
text_delta
tool_requested
tool_completed
usage_reported
checkpoint_available
session_completed
session_failed
```

### Capability matrix

Нужны не только `supported: true/false`, но и свойства:

```text
headless_execution
structured_result
session_resume
tool_interception
reliable_cancellation
usage_reporting
workspace_binding
native_subagents
mcp_support
```

Каждая capability имеет:

```text
status
evidence
tested_runtime_version
limitations
last_verified_at
```

Current SKM уже использует manifest provider capabilities как заявленный source of truth — эту идею стоит сохранить и расширить до runtime contracts. [SKM: Provider support](https://github.com/academici/swissknifeman/blob/1603bfd8c988cf04505af55462c1596b5d82fde5/README.md)

### Kiro как adapter

Crew описывает запуск Kiro через ACP и отдельный provider seam для выбранного harness. [Crew: ACP harness](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

Для SKM:

```text
adapters/runtimes/acp
  общий transport

adapters/runtimes/kiro
  Kiro-specific lifecycle
  configuration projection
  capability checks
  event normalization
```

Не следует делать так:

```python
if provider == "kiro":
    ...
```

в `planning`, `review`, `budget`, `GUI` и `workspace`.

Provider-specific различия разрешаются в adapter и capability negotiation.

***

## Контекст и знания

### Контекст собирается явно

Каждый агентный шаг получает `ContextManifest`:

```text
plan_revision
unit
relevant requirements
accepted decisions
required materials
selected steering
selected skills
previous attempt evidence
review feedback
workspace baseline
policy restrictions
```

Для каждого элемента:

```text
source_id
version
digest
selection_reason
trust_level
size
```

Это позволит ответить:

> Почему агент видел именно эти инструкции, а не другую редакцию?

### Не загружать всё

Рекомендуемая лестница:

```text
1. Обязательные системные ограничения.
2. Контракт текущей задачи.
3. Связанные требования.
4. Релевантные решения.
5. Нужные skills.
6. Нужные материалы.
7. Ограниченная история.
```

Если контекст не помещается, система должна фиксировать, что исключено или сокращено.

Не молча отрезать последние пункты prompt.

### Память не authoritative state

Разделение:

| Данные | Источник истины |
|---|---|
| Статус unit | Execution state |
| Утверждённое требование | Plan revision |
| Решение архитектуры | Decision record |
| Результат проверки | Check evidence |
| Пользовательская привычка | Memory |
| Полезный вывод | Curated lesson |
| Содержимое skill | Versioned extension |

Нельзя восстанавливать статус плана из summary разговора.

### Материалы

Для внешнего материала хранить:

```text
material_id
source_url
retrieved_at
content_digest
source_type
trust_level
local_artifact_ref
scope
```

Для обязательного материала:

```text
required_for = execution | review | acceptance
freshness_policy
```

Если материал недоступен:

```text
blocked_by_material
```

а не «агент попробует догадаться».

***

## Skills, шаблоны и steering

### Разные сущности

| Сущность | Что делает |
|---|---|
| Skill | Объясняет, как выполнять класс задач |
| Template | Задаёт структуру нового объекта |
| Steering | Устанавливает правила проекта или области |
| Agent profile | Определяет роль и предпочтения исполнения |
| Workflow definition | Задаёт допустимую последовательность этапов |
| Integration bundle | Связывает tools, настройки и инструкции |
| Policy | Устанавливает обязательные ограничения |

Главный запрет:

> Skill или agent profile не могут расширять permissions и отменять policy.

### Структура template

```text
resources/templates/feature/
├── manifest.yaml
├── brief.md.j2
├── requirements.yaml.j2
├── design.md.j2
└── plan.yaml.j2
```

Manifest:

```yaml
id: feature
version: 1.0.0
kind: plan-template
input_schema: feature-input.schema.json
output_schema: plan-specification.schema.json
required_sections:
  - requirements
  - acceptance_criteria
  - verification
```

### Структура skill

```text
resources/skills/code-review/
├── manifest.yaml
├── SKILL.md
├── references/
└── examples/
```

Metadata:

```text
id
version
supported_roles
required_capabilities
input_contract
output_contract
trust
provenance
```

### Steering

Правила должны быть адресными:

```text
global
project
directory
language
task-type
risk-category
```

Пример:

```yaml
id: backend-transactions
scope:
  directories:
    - src/backend
applies_to:
  - implementation
  - review
priority: project
```

Если два правила конфликтуют, нужна диагностируемая precedence model, а не надежда, что модель «сама поймёт».

### Immutable execution bundle

На старте Run фиксируется:

```text
plan revision
workflow version
agent profile version
skills versions
template provenance
effective policy digest
context selection configuration
```

Обновление skill в registry не должно менять уже выполняющийся Run.

Для применения новой версии — новый run или явно записанная controlled reconfiguration.

***

## Hooks и события

### Три класса hooks

Нельзя смешивать:

| Класс | Пример | Может блокировать |
|---|---|---|
| Enforcement | Запрет tool call | Да |
| Workflow | После checks запросить review | Через application command |
| Observation | Отправить метрику | Нет |

Для каждого hook:

```text
event_type
timeout
retry_policy
failure_policy
permissions
execution_location
```

### Ошибка hook

Пример правил:

```text
Security hook failed
  → deny

Metrics hook failed
  → record warning, continue

Notification hook failed
  → retry through outbox

Workflow hook failed
  → explicit workflow error
```

Не надо иметь одно универсальное `ignore_errors=true`.

### Outbox

Внешние подписчики не должны вызываться внутри state transaction:

```text
transaction:
  update state
  append domain event
  append outbox record
commit

dispatcher:
  deliver
  record receipt
  retry if needed
```

Для первого релиза достаточно database-backed outbox. Отдельный брокер необязателен.

***

## API и клиент

### Ресурсы

Предлагаемый API:

```text
/api/v1/projects
/api/v1/plans
/api/v1/plans/{id}/revisions
/api/v1/plans/{id}/validate
/api/v1/plans/{id}/approve
/api/v1/runs
/api/v1/runs/{id}
/api/v1/runs/{id}/pause
/api/v1/runs/{id}/resume
/api/v1/runs/{id}/cancel
/api/v1/reviews
/api/v1/approvals
/api/v1/artifacts
/api/v1/events
/api/v1/workers
```

Worker endpoints:

```text
/api/v1/worker/assignments/claim
/api/v1/worker/assignments/{id}/heartbeat
/api/v1/worker/assignments/{id}/result
```

### Изменение плана

Пример запроса:

```http
POST /api/v1/plans/plan-123/revisions
Idempotency-Key: revise-plan-123-request-7
If-Match: "aggregate-version-18"
```

```json
{
  "base_revision_id": "revision-7",
  "changes": {
    "title": "Авторизация с ротацией refresh token"
  },
  "reason": "Уточнение требования безопасности"
}
```

При конфликте:

```json
{
  "code": "VERSION_CONFLICT",
  "expected_version": 18,
  "actual_version": 19,
  "retryable": false
}
```

Клиент не должен автоматически перезатирать новую редакцию.

### Стриминг

В первом релизе:

```text
REST для commands/queries
SSE для событий и прогресса
```

События должны иметь cursor:

```text
event_id
project_sequence
run_id
type
payload
```

После reconnect клиент передаёт последний cursor и догружает пропущенное.

Важно разделить:

- Долговечные события state transitions.
- Высокочастотные text deltas агентной сессии.

Необязательно сохранять каждый token как отдельную строку domain event table.

### Общая модель ошибок

```text
NOT_FOUND
FORBIDDEN
VERSION_CONFLICT
SCHEMA_INVALID
DEPENDENCY_CYCLE
PLAN_NOT_READY
CAPABILITY_UNAVAILABLE
APPROVAL_REQUIRED
MANUAL_PENDING
LEASE_LOST
BUDGET_EXHAUSTED
OUTCOME_UNKNOWN
BACKEND_UNAVAILABLE
```

CLI, API и MCP возвращают одинаковый `code`, даже если представление разное.

***

## Конфигурация

Пример project config:

```toml
schema_version = 1

[project]
id = "project-agelto"

[plans]
driver = "http"
endpoint = "https://skm.example.com/api/v1"
credential_ref = "keyring:skm-production"

[execution]
worker_selector = ["dmitry-laptop"]
workspace_driver = "git-worktree"
max_parallel_units = 2

[agents]
executor = "claude"
reviewer = "kiro"

[artifacts]
driver = "control-plane"

[workflow]
profile = "reviewed-development"

[security]
profile = "workspace-contained"
```

Локальный вариант:

```toml
[plans]
driver = "database"
dsn = "sqlite:///~/.local/share/skm/state.db"
```

Файловый:

```toml
[plans]
driver = "filesystem"
root = "~/.local/share/skm/projects/project-agelto"
```

### Не все параметры переносимы

Разделить:

```text
project config
  переносимая идентичность и предпочтения

machine config
  пути, доступные runtimes, local checkout bindings

server config
  persistence, auth, worker admission

secret references
  не сами секреты
```

Абсолютный путь ноутбука не должен попадать в переносимый план.

### Precedence

Для обычных preferences:

```text
defaults
  → user
  → project
  → machine binding
  → invocation override
```

Для обязательных security restrictions — не «последний победил», а сужение:

```text
effective permissions =
  server ceiling
  ∩ project restrictions
  ∩ worker restrictions
  ∩ run scope
```

Изменение prompt, skill или project config не может расширить серверный ceiling.

### Диагностика

Нужна команда вида:

```text
skm config explain
```

Она показывает:

```text
effective value
source layer
overridden values
validation result
policy restriction
```

Секреты только маскируются.

***

## Сервер и Docker

### Разделить API и выполнение

**Не рекомендую** запускать control plane и произвольные команды агента в одном процессе и с одним filesystem-доступом.

Предлагаемые процессы:

| Процесс | Имеет доступ |
|---|---|
| API | State DB, auth, policy, artifact metadata |
| Worker | Свой workspace, runtime, scoped credentials |
| Database | Только database storage |
| Artifact service | Blob storage |

### Локальный режим

```text
skm local start
  → local control service
  → SQLite или filesystem
  → local worker
```

Одна пользовательская команда может запускать несколько внутренних компонентов. Пользователь не обязан управлять ими вручную.

### Серверный режим

```text
server:
  API + PostgreSQL

laptop:
  worker → outbound HTTPS → API
```

Это позволяет не открывать входящий порт на ноутбуке.

Отдельно можно добавить server-side worker:

```text
server worker:
  claims selected assignments
  prepares managed checkout
  runs isolated runtime
```

### Docker security

Минимальные правила:

- API не получает Docker socket.
- Agent workspace не содержит control plane secrets.
- Worker не монтирует весь home.
- Контейнер исполняется не от root.
- Database не публикуется наружу без необходимости.
- Внешний API доступен только с authentication и TLS.
- Secrets не встраиваются в образ.
- Версии runtime и worker image фиксируются.
- Рабочая директория отдельная для attempt.
- Привилегированные operations требуют отдельного execution profile.

Docker deployment сам по себе не должен считаться достаточной политикой изоляции.

***

## Безопасность

### Объекты доверия

| Объект | Уровень |
|---|---|
| Operator policy | Доверенный authority |
| Server configuration | Доверенная конфигурация |
| Project specification | Пользовательские данные |
| Repository files | Потенциально недоверенные данные |
| External documentation | Недоверенный input |
| Model output | Недоверенное предложение |
| Third-party skill | Недоверенная инструкция |
| Third-party executable plugin | Полноценный риск исполнения кода |

### Проверять действия

Не достаточно запретить в prompt:

```text
«Не читай ~/.ssh»
```

Нужны ограничения в execution boundary:

```text
filesystem mounts
OS sandbox
network policy
tool admission
credential scope
approval
```

Crew также разделяет PreToolUse gate, governance, sandbox, redaction и audit, причём его документ описывает различия между стандартным и строгим sandbox profile. [Crew: Security layers](https://github.com/kirodotdev/KiroCrew/blob/main/docs/architecture/overview.md)

Для SKM это означает: не переносить профиль с чужими компромиссами автоматически, а определить собственные безопасные defaults.

### Approval

Approval привязывать не к фразе «разрешаю всё», а к конкретному intent:

```text
actor
run
tool
normalized arguments digest
workspace
scope
expires_at
single_use
```

Если параметры изменились — старое approval не подходит.

### Policy во время run

Для воспроизводимости сохраняется policy snapshot.

Но отзыв доступа должен работать немедленно:

```text
recorded policy snapshot
  объясняет, с чем run стартовал

current authority
  может запретить дальнейшее выполнение
```

Нельзя продолжать опасное действие только потому, что старая revision когда-то его разрешала.

***

## Бюджеты и параллелизм

### Несколько бюджетов

Нужно отдельно ограничивать:

```text
model cost
tokens
wall-clock time
tool invocations
attempt count
review rounds
parallel units
external API usage
```

Отсутствие достоверного usage report не означает нулевую стоимость.

Если runtime не сообщает расход:

```text
usage_status = unknown
```

или используется явно помеченная оценка.

### Reservation

При параллельном запуске не должно происходить:

```text
два worker видят свободный бюджет;
каждый расходует весь остаток.
```

Нужен:

```text
reserve
  → execute
  → settle
  → release unused
```

Reservation фиксируется транзакционно.

### Конфликты кода

DAG-зависимости недостаточно для безопасного parallel execution.

Нужны два разных ограничения:

```text
logical dependency
  B требует результат A

workspace conflict
  A и B могут менять один модуль или файл
```

Для первого релиза предлагаю:

- Параллельное исследование разрешено.
- Параллельный review разрешён.
- Параллельные изменения — в отдельных worktrees.
- Интеграция изменений сериализована.
- После интеграции повторяются необходимые checks.
- При конфликте — отдельная integration task, не молчаливый merge.

***

## Наблюдаемость

### Что показывать

Для каждого Run:

```text
какая revision;
какой workflow;
кто выполняет;
какая попытка;
какой lease;
какой workspace;
какие skills;
какой runtime;
почему unit blocked;
чего ждёт approval;
какие checks выполнены;
почему review отклонён;
сколько бюджета осталось;
что требуется человеку.
```

### Почему заблокировано

Нужен структурированный `blocking_reason`:

```json
{
  "code": "WAITING_MANUAL_CHECK",
  "unit_id": "unit-auth-refresh",
  "check_id": "check-browser-session",
  "required_actor_role": "operator",
  "next_action": "record-verdict"
}
```

GUI не должен восстанавливать причину из текста последнего сообщения агента.

### Разделить журналы

```text
domain events
  что произошло с работой

runtime transcript
  что говорили агент и модель

tool audit
  какие действия были разрешены и выполнены

operational logs
  почему упал процесс или соединение

metrics
  задержки, throughput, failures, usage
```

У этих потоков разные retention и права доступа.

### Health и readiness

Отдельные проверки:

```text
API alive
database reachable
schema compatible
worker registered
runtime installed
runtime authenticated
sandbox available
artifact storage writable
queue progressing
```

`200 OK` у HTTP endpoint не означает готовность выполнять работу.

***

## Проверки архитектуры

Здесь стоит быть жёстким: правильные зависимости должны проверяться автоматически.

### Import boundaries

Примеры правил:

```text
planning.domain
  не импортирует adapters

execution.domain
  не импортирует runtimes

entrypoints
  не импортируют SQL models

web
  не содержит правил переходов state machine

provider adapter
  не изменяет plan status напрямую

learning
  не пишет operator policy

brain exporter
  не становится хранилищем статусов
```

### Размер ядра

Для каждого нового элемента `kernel` требуется ответ:

```text
какие минимум два независимых модуля его используют;
почему он не принадлежит одному из них;
какие зависимости он добавляет;
является ли contract стабильным.
```

Иначе `aicore` просто переедет в `kernel` и снова вырастет.

### Центральные ветвления

Architecture test должен обнаруживать ситуацию, когда новый provider требует изменений в:

```text
planning
execution domain
review engine
GUI
storage
```

Допустимое место provider selection — composition root и adapter registry.

***

## Матрица тестирования

### Domain tests

Проверяют без IO:

- Нельзя выполнить unit с незавершёнными dependencies.
- Нельзя принять результат другой revision.
- Нельзя завершить unit без обязательного review.
- Ручной pending не расходует rework rounds.
- Rework limit действительно ограничивает повтор.
- Нельзя принять stale attempt.
- Нельзя создать dependency cycle.
- Нельзя ослабить обязательную policy из plan.
- Изменение display key не меняет identity.

### Backend contract tests

Один набор для filesystem, SQLite, PostgreSQL и HTTP client/server:

```text
create
read
revise
validate
optimistic conflict
idempotent retry
state + event atomicity
pagination
export/import
unsupported schema
backend failure
```

Особенно важно:

```text
одна command;
одинаковые входы;
одинаковый domain result;
разные backend.
```

### Recovery tests

Обязательные fault points:

| Момент сбоя | Что должно произойти |
|---|---|
| До commit | Изменение не видно |
| После commit, до ответа | Retry возвращает прежний результат |
| Во время переключения FS generation | Видна старая или новая согласованная generation |
| После claim | Lease можно восстановить или признать потерянным |
| Во время agent execution | Attempt остаётся диагностируемым |
| После внешнего side effect | Не выполняется слепой повтор |
| Во время artifact upload | Частичный blob не считается evidence |
| Во время shutdown | Нет самовольного принятия незавершённых units |

### Security tests

- Repository file пытается изменить policy.
- Skill пытается расширить permissions.
- Worker получает assignment чужого проекта.
- Stale token отправляет result.
- Artifact endpoint раскрывает чужой blob.
- Approval повторно используется.
- Секрет попадает в transcript.
- Path traversal в export/import.
- Symlink выходит из workspace.
- Tool-call parameters изменяются после approval.

### Runtime contract tests

Сначала fake runtime:

```text
successful response
malformed result
timeout
cancel ignored
partial stream
tool request
usage missing
session resume unsupported
process crash
```

Платные live evals — отдельный opt-in suite с лимитами, а не часть обычного `pytest`.

### End-to-end критерии

```text
Создать план локально.
Выполнить unit через fake runtime.
Получить checks и review.
Перезапустить control plane.
Продолжить run.
Экспортировать план.
Импортировать на сервер.
Подключить local worker.
Продолжить новым run той же revision.
```

Миграция активного execution process между машинами не должна обещаться этим сценарием: перенос данных и перенос живой runtime session — разные задачи.

***

## Карта Planner

В текущем `planner/plan` уже выделены отдельные файлы для модели, schema, storage, execution, readiness, units, views, templating и других задач. Следующий шаг — не просто разложить их по другим папкам, а отделить pure rules от effects. [Текущий каталог](https://github.com/academici/swissknifeman/tree/1603bfd8c988cf04505af55462c1596b5d82fde5/packages/planner/lib/planner/plan)

Ниже — **предварительная карта владельцев по именам и назначению**, а не утверждение, что содержимое каждого файла уже полностью проверено.

| Текущий файл | Предполагаемый владелец | Что проверить при переносе |
|---|---|---|
| `model.py`, `_types.py` | Planning domain | Удалить storage-specific types |
| `store.py` | Filesystem adapter | Отделить snapshot model, locking, paths, events |
| `workspace.py` | Workspace/project bindings | Не связывать чтение плана с checkout |
| `schema.py`, `_jsonschema_core.py` | Validation adapter / contracts | Разделить format validation и domain invariants |
| `execution.py` | Execution application/domain | Отделить переходы от запуска процессов |
| `lifecycle.py` | Planning application | Проверить state mutations и side effects |
| `ops.py` | Несколько command handlers | Разделять по use case, не переносить «мешок операций» |
| `units.py` | Planning и execution | Разделить unit definition и run-unit state |
| `edges.py`, `parallel.py` | Dependency/conflict rules | Развести DAG и workspace conflicts |
| `readiness.py` | Planning validation | Вернуть structured findings |
| `check.py` | Validation/check contracts | Развести проверку плана и execution checks |
| `query.py`, `stats.py`, `catalog.py` | Read models | Не читать filesystem напрямую вне adapter |
| `gitops.py` | Git workspace adapter | Исключить Git из plan domain |
| `views.py` | Projection/export | Сделать полностью пересоздаваемым |
| `templating.py` | Extensions/templates | Версионировать template inputs/outputs |
| `context.py`, `snapshot.py` | Context и revision snapshots | Разделить execution context и plan snapshot |
| `budget.py` | Execution budgets | Reservation, unknown usage, settlement |
| `scout.py` | Workflow role implementation | Не позволять роли менять state в обход commands |
| `refs.py` | Domain identifiers / references | Удалить зависимость identity от path |
| `extensions.py`, `bridges.py` | Explicit extension contracts | Уменьшить неявное runtime discovery |
| `settings.py` | Config/bootstrap | Не импортировать config loader в domain |
| `cli.py` | CLI entrypoint | Только parsing, calls, presentation |

Для каждого файла перед переносом нужен небольшой migration record:

```text
current responsibilities
imports
side effects
public callers
target owner
behavior to preserve
tests proving preservation
```

***

## Стратегия перехода

### Этап A: зафиксировать поведение

Не начинать с переезда всех файлов.

Сделать:

1. Архитектурные решения в ADR.
2. Инвентаризацию публичных commands.
3. Список схем и текущих invariants.
4. Fixtures существующих планов.
5. Characterization tests для критических операций.
6. Отдельный список известных несовместимостей.

**Gate:** понятно, какое поведение сохраняется, а какое меняется намеренно.

### Этап B: чистый PlanSnapshot

Вынести из `Plan`:

```text
domain snapshot
filesystem locator
workspace binding
```

Старый CLI временно продолжает работать через compatibility facade.

**Gate:** validation и queries выполняются над snapshot без локального checkout.

### Этап C: первый command

Реализовать вертикально:

```text
RevisePlan
  → application handler
  → domain
  → UoW
  → filesystem adapter
  → event
  → typed result
```

**Gate:** consumer не знает JSON paths.

### Этап D: SQL backend

Добавить SQLite и PostgreSQL через общий port.

**Gate:** один contract suite проходит для обоих SQL вариантов и filesystem backend в заявленных capability boundaries.

### Этап E: HTTP boundary

Добавить:

```text
API
HTTP client
authentication
idempotency
optimistic concurrency
event cursor
```

**Gate:** тот же CLI переключает проект на HTTP без изменения workflow command.

### Этап F: durable execution

Вынести:

```text
run
attempt
assignment
lease
review
check results
```

Сначала fake runtime.

**Gate:** restart и потеря worker не повреждают state.

### Этап G: runtime adapters

Подключать по одному:

```text
existing runtime adapter
Kiro adapter
другие runtimes
```

Очередность определять не популярностью, а наличием надёжного headless lifecycle и ваших реальных сценариев.

**Gate:** adapter проходит compatibility suite, ограничения видимы пользователю.

### Этап H: UI и extensions

Перевести GUI на API/client contracts, затем вынести templates, skills и steering.

**Gate:** GUI не читает plan files и не пишет SQL.

### Этап I: learning и integrations

Подключить:

```text
analyst promotion
memory retrieval
Obsidian export
notifications
scheduling
```

**Gate:** отказ optional integration не разрушает plan execution.

***

## Миграция существующих планов

### Не конвертировать на месте

Предлагаемый процесс:

```text
scan
  → validate source
  → build migration manifest
  → import to staging
  → compare
  → verify references
  → activate
  → retain source read-only
```

### Migration manifest

Для каждого объекта:

```text
source path
source digest
source schema
legacy display key
new entity id
target revision
target digest
warnings
migration status
```

### Что сохранять

- Requirements.
- Decisions.
- Phases и порядок.
- Items и units.
- Dependencies.
- Checks.
- Review requirements.
- Historical events.
- Material references.
- Human comments.
- Неизвестные extension fields.

Неизвестное поле нельзя просто отбросить.

Если автоматическое сохранение невозможно:

```text
migration blocked
```

или:

```text
preserved as opaque legacy payload
```

с явным предупреждением и ограничениями.

### Проверки миграции

```text
число сущностей совпадает;
все ссылки разрешаются;
DAG эквивалентен;
aliases сохранены;
данные не потеряны;
старые timestamps не переписаны как новые;
import повторяем;
export детерминирован;
source остаётся неизменным.
```

Статусы старых планов нельзя автоматически объявлять подтверждёнными новой review policy. Для этого нужен explicit legacy acceptance marker.

***

## Первые ADR

Я бы начал с этих решений:

| ADR | Решение |
|---|---|
| Architecture style | Модульный монолит и отдельный worker |
| Plan identity | Stable ID отдельно от display key |
| Plan revisions | Неизменяемые specifications |
| Run ownership | Execution state отдельно от plan definition |
| Storage access | Embedded client или HTTP client |
| Persistence | Filesystem и SQL adapters |
| Transactions | State, events и idempotency receipt вместе |
| Execution | Deterministic engine, agentic steps |
| Recovery | Leases, fencing, isolated attempts |
| Review | Обязательный explicit review contract |
| Security | Policy вне контроля агента |
| Extensions | Skills как данные, executable plugins отдельно |
| Context | Versioned context manifest |
| Migration | Import/verify/activate без перезаписи источника |

Каждый ADR должен содержать:

```text
context
decision
alternatives
consequences
compatibility
verification
```

***

## Что отложить

Чтобы новая система не стала более «напичканной», чем текущая, я бы явно исключил из первого целевого релиза:

- Полноценный plugin marketplace.
- Недоверенные Python plugins внутри API процесса.
- Автоматическую генерацию и применение новых skills без approval.
- Сложную multi-tenant SaaS-модель.
- Offline multi-master синхронизацию.
- Перенос живой агентной сессии между машинами.
- Произвольные workflow scripts с доступом ко всему runtime.
- Автоматический выбор модели без наблюдаемости.
- Отдельный микросервис для каждого модуля.
- Обязательную vector database.
- Автоматический merge всех параллельных изменений.
- Десятки messaging integrations.
- Обещание exactly-once для внешних side effects.

Особенно важно: **«можно выгрузить на сервер» не требует сразу решать двустороннюю offline-синхронизацию**.

На первом этапе достаточно:

```text
export/import
```

или:

```text
проект выбирает один authoritative endpoint
```

Это гораздо более контролируемая модель.

***

## Проверяемая готовность системы

Я бы считал архитектуру действительно состоявшейся только после следующих демонстраций.

### Замена хранилища

```text
Один и тот же план:
  filesystem
  SQLite
  PostgreSQL через API

Одинаковые:
  commands
  validation
  revisions
  review semantics
  result types
```

### Независимость размещения

```text
План на сервере.
Worker на ноутбуке.
Checkout на ноутбуке.
Runtime Kiro или Claude.
GUI показывает серверное состояние.
```

### Надёжное восстановление

```text
Worker убит во время исполнения.
Lease истёк.
Старая попытка не принята.
Новая попытка стартовала из известного baseline.
История не потеряна.
```

### Review действительно обязателен

```text
Агент сказал «готово».
Проверки прошли.
Review отсутствует.

Unit не accepted.
```

### Provider действительно заменяем

```text
Добавлен новый runtime adapter.

Не изменены:
  planning domain
  execution transitions
  storage
  review invariants
  GUI business logic
```

### Ядро действительно компактное

```text
Отключены:
  learning
  Obsidian
  notifications
  advanced retrieval

Остались:
  plan
  run
  checks
  review
  policy
  durable state
  execution
```

***

## Конкретная стартовая задача

**Первым изменением я рекомендую не подключение Kiro и не PostgreSQL, а разрез `PlanSnapshot → RevisePlan → UoW → backend`.**

Его минимальный состав:

```text
planning/domain/specification.py
planning/domain/revision.py
planning/application/commands.py
planning/application/service.py
planning/ports.py
adapters/persistence/filesystem/backend.py
tests/contracts/test_plan_backend.py
```

Обязательные сценарии приёмки:

1. План читается без checkout.
2. Изменение создаёт новую revision.
3. Предыдущая revision остаётся доступной.
4. Неверный `expected_version` даёт conflict.
5. Повтор с тем же idempotency key не создаёт вторую revision.
6. Изменение и событие либо видны вместе, либо не видны.
7. CLI не знает, где лежат JSON.
8. Тот же handler затем работает с SQL backend без изменения domain logic.

**Именно после этого Kiro становится полезным подключаемым исполнителем, а сервер и Docker — способом размещения уже правильно разделённой системы, а не ещё одним набором условий внутри существующих модулей.**