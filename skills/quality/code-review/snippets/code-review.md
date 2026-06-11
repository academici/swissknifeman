# Code review (SOVA)

## Когда активировать

- Пользователь просит ревью или разбор PR.
- Перед merge нетипично большого изменения.
- Проверка чужого кода в домене Ticket, Meeting, участников.
- Нужна быстрая сверка с архитектурой Strict и контрактами workflow.

## Порядок (кратко)

1. Понять границы изменения: один слой или несколько (см. **`cross-layer-change-checklist`** при multi-layer).
2. Проверить границы **Action ↔ Service**, контроллер, политики — по **`.ai/guidelines/architecture.md`** и **`docs/dev/backend-patterns.md`**.
3. Если затронуты заявки/переходы/abilities — **`ticket-workflow`** и согласованность enum/policy/route/UI из **`.ai/guidelines/project-development.md`**.
4. Тесты: покрытие, русские человекочитаемые имена сценариев, минимальный test-gate для workflow при необходимости — **`testing-rules`**, **`pest-testing`**.
5. Безопасность — раздел ниже (поверх **`spatie-security`**).

## Архитектура слоёв

- Один публичный `execute()` у Action; без `Request` в Action/Service-сценариях домена.
- Мутации и транзакционная граница use-case — в Action; `*Service` без записи в домен и без `Request`.
- Контроллер: HTTP → validate → Action → ответ; без оркестрации мутаций через «use-case Service».
- Именованные аргументы PHP везде, где применимо правило проекта.

Подробности и антипаттерны: **`docs/dev/backend-patterns.md`**, **`docs/dev/code-organization.md`**.

## Домен Ticket и workflow

- Переходы статусов и политики не расходятся с **`TicketStatus::transitionDefinitions()`** и гейтами.
- При смене перехода/permission синхронно enums, policies, routes, фронт — см. dependency map в **`.ai/guidelines/project-development.md`**.

Активируй **`ticket-workflow`**, если ревью касается статусов, Stage, Actions, Policy.

## Многослойные изменения

Если затронуты backend + policy + HTTP + frontend + тесты — пройди чеклист **`cross-layer-change-checklist`**. При необходимости оркестрации задачи — **`complex-task-orchestrator`**.

## Тесты

- Feature-тесты для HTTP и сценариев доступа; для чистой логики — unit.
- Имена тестов и описания на русском (правило проекта).
- **`RefreshDatabase`** / изоляция **`{{project_name}}_test`** — **`testing-rules`**.
- Минимальный набор команд и Docker vs хост — таблица в **`testing-rules`**.

## Security pass (SOVA)

Сначала опирайся на навык **`spatie-security`** (общие практики Laravel и безопасность кода).

Дополнительно по проекту:

- **Авторизация:** согласованность Permission enum, методов Policy и вызовов `Gate`; негативные кейсы в тестах там, где меняется доступ.
- **Загрузки и медиа:** коллекции, видимость файлов, конверсии — **`medialibrary-development`**.
- **Конфигурация:** секреты и окружение только через файлы `config/*`, не `env()` снаружи конфигов.
- **Ввод пользователя:** валидация в Form Request; массовое присвоение — только разрешённые поля.

## Generated и контекст агента

- Не предлагать правки в **`CLAUDE.md`**, **`AGENTS.md`**, **`GEMINI.md`** и игнорируемых копиях — источник правды **`.ai/`** и **`boost.json`**, затем **`php artisan boost:update`** (**`ai-context-workflow`**).
- Ревью зафиксировало новую или иную архитектурную договорённость — в той же задаче синхронизировать **`docs/dev/*`** (и при необходимости **`docs/workflow/*`**) и правила в **`.ai/guidelines/`** / **`.ai/skills/`**, затем генерация.
