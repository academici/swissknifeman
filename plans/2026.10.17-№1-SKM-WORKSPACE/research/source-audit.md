# Аудит архитектуры SwissKnifeMan

Рекомендуемое направление: вынести планы и задачи из рабочих репозиториев в отдельный **portable workspace**, но не превращать весь домашний каталог SwissKnifeMan в Git-репозиторий. Синхронизировать следует только переносимые канонические данные; конфигурацию машины, runtime-state, кэши, логи, секреты и сгенерированные представления необходимо физически отделить.

> Отчёт основан на статическом аудите ветки `main`: архитектуре `aicore`, `planner`, `orch`, `gui`, `skiller`, текущей политике `.gitignore` и официальных рекомендациях провайдеров. Выполнение тестов и полный построчный аудит каждого `SKILL.md` в этой итерации не проводились.

## Ключевые выводы

1. **Направление с глобальным хранилищем планов правильное**, но Git-корнем лучше сделать не `~/.SwiftKnifeMan`, а вложенный каталог наподобие `~/.SwiftKnifeMan/workspace`. Это исключит случайную публикацию machine-local данных.
2. Уже существующая архитектура `aicore` разделяет `config`, `state`, `data`, `cache` по XDG и поддерживает изолированный `SKM_HOME`; новый workspace должен расширять эту модель, а не создавать второй несовместимый механизм путей. См. [`aicore/state/locations.py`](https://github.com/academici/swissknifeman/blob/main/packages/aicore/lib/aicore/state/locations.py).
3. Проекты должны связываться с планами через стабильный `project_id`, а не через абсолютный путь. Абсолютные пути относятся к конкретной машине и хранятся только в локальных bindings.
4. `views/`, raw role streams, runtime-state, блокировки, кэши, backups и машинные конфиги не должны синхронизироваться. Текущий репозиторий уже частично следует этому принципу в [`.gitignore`](https://github.com/academici/swissknifeman/blob/main/.gitignore).
5. Автоматические commit/push допустимы только как отдельная управляемая служба синхронизации. Git hooks не должны быть основным механизмом: они плохо наблюдаемы, не переносятся автоматически и способны неожиданно блокировать рабочий процесс.
6. GUI должен редактировать **конкретный слой конфигурации**, а не итоговый merged config. Пользователь должен видеть происхождение значения, область действия, переносимость, необходимость перезапуска и preview изменения.
7. Оркестратор уже имеет сильный pipeline и prompt manifests, но provider/model-specific адаптация промптов пока не выделена как полноценный контракт. Это главный следующий архитектурный слой.
8. Общая команда «печатать progress line перед каждым крупным шагом» не должна безусловно попадать всем моделям. Для Codex официальные рекомендации прямо предупреждают, что лишние preamble/status-инструкции могут ухудшать rollout; Claude, напротив, может выиграть от явного разделения сложного контекста на структурные блоки. [platform.claude](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
9. Аудит скиллов нужно перевести с проверки «безопасен ли текст» на проверку «улучшает ли он результат конкретной модели». Существующий skiller хорошо покрывает quarantine, budget и usage, но не измеряет semantic value и конфликты инструкций.
10. Миграцию планов следует сделать отдельной идемпотентной операцией с dry-run, digest verification и rollback, а не незаметным изменением поведения после обновления.

***

## Целевая модель данных

### Не Git-корень дома

Не рекомендуется:

```text
~/.SwiftKnifeMan/
├── .git/
├── config/
├── state/
├── cache/
├── Projects/
└── ...
```

При такой схеме любой новый служебный файл оказывается потенциально публикуемым. Безопасность зависит от постоянного обновления `.gitignore`, а забытый новый файл может содержать абсолютные пути, токены, локальные команды или части промптов.

Рекомендуется:

```text
~/.SwiftKnifeMan/
├── config/                    # machine-local, никогда не Git
├── state/                     # machine-local runtime
├── cache/                     # disposable
├── logs/                      # machine-local
├── devices/                   # локальная identity машины
└── workspace/                 # единственный portable Git root
    ├── .git/
    ├── .gitignore
    ├── .gitattributes
    ├── workspace.json
    ├── projects/
    ├── shared/
    └── migrations/
```

Если используется стандартная XDG-модель, физическое расположение может оставаться таким:

```text
~/.config/swissknifeman/
~/.local/state/swissknifeman/
~/.local/share/swissknifeman/
~/.cache/swissknifeman/
```

В этом случае portable workspace размещается, например, в:

```text
~/.local/share/swissknifeman/workspace/
```

`SKM_HOME` должен по-прежнему собирать все четыре machine-каталога под одним изолированным корнем для тестов и sandbox, но portable Git workspace остаётся отдельным явно разрешённым подкаталогом.

### Почему не `Projects/Plans/Tasks`

Иерархия `Projects/Plans/Tasks` двусмысленна: она может означать либо общие списки всех планов и задач, либо вложенность одного проекта. Лучше использовать project-first структуру:

```text
workspace/
└── projects/
    └── <project-id>/
        ├── project.json
        ├── plans/
        │   └── <plan-id>/
        ├── tasks/
        │   └── <task-id>.json
        ├── decisions/
        ├── materials/
        └── archive/
```

Это даёт следующие свойства:

- Проект можно экспортировать или архивировать одной директорией.
- Исключается глобальный конфликт одинаковых `plan-id`.
- Политики retention и attachments задаются на проект.
- GUI может лениво загружать один проект.
- Можно синхронизировать отдельный проект в будущем.
- Удаление локального checkout не удаляет знания и планы проекта.

### Стабильная идентичность

Рекомендуемый `project.json`:

```json
{
  "schema": "skm-project/v1",
  "project_id": "prj_01J...",
  "name": "swissknifeman",
  "created_at": "2026-10-17T09:00:00Z",
  "identity": {
    "git_remotes": [
      "github.com/academici/swissknifeman"
    ],
    "initial_commit": "optional-stable-anchor"
  },
  "aliases": [
    "skm"
  ],
  "status": "active"
}
```

В portable manifest не должно быть:

```json
{
  "path": "/Users/dmitry/dev/swissknifeman",
  "launcher": "/opt/homebrew/bin/claude",
  "python": "/Users/dmitry/.pyenv/..."
}
```

Привязка проекта на конкретной машине хранится отдельно:

```toml
# machine-local bindings.toml

[projects.prj_01J...]
path = "/Users/dmitry/dev/swissknifeman"
last_seen_remote = "git@github.com:academici/swissknifeman.git"
preferred_provider = "claude-code"
preferred_model_class = "implementation"
```

### Определение проекта

Алгоритм разрешения:

1. Если команда запущена через Launcher, использовать launcher-bound root.
2. Если указан `--project`, разрешить его через существующий `resolve_project`.
3. Получить нормализованные Git remotes.
4. Найти portable project manifest с совпадающей identity.
5. Если совпадение одно — создать или обновить локальный binding.
6. Если совпадений несколько — остановиться и запросить выбор.
7. Если remote отсутствует — использовать сохранённый local binding.
8. Если проект неизвестен — предложить `workspace project attach`.
9. Никогда не использовать абсолютный путь как переносимый идентификатор.

Нормализация remote должна приводить к одному виду:

```text
git@github.com:academici/swissknifeman.git
https://github.com/academici/swissknifeman.git
ssh://git@github.com/academici/swissknifeman.git
```

Результат:

```text
github.com/academici/swissknifeman
```

Не следует автоматически объединять проекты только по имени каталога.

***

## Структура плана

Текущий planner генерирует human views как производную канонического JSON и `log.jsonl`; `views/` уже считается generated output в [`planner/plan/views.py`](https://github.com/academici/swissknifeman/blob/main/packages/planner/lib/planner/plan/views.py). Это правильная модель: в Git должны попадать источники, а не их представление.

Рекомендуемая структура:

```text
plans/<plan-id>/
├── manifest.json
├── brief.json
├── phases/
│   └── <phase-id>.json
├── items/
│   └── <item-id>.json
├── units/
│   └── <unit-id>.json
├── decisions/
│   └── <decision-id>.json
├── documents/
│   └── <document-id>.json
├── materials/
│   ├── manifest.json
│   ├── notes/
│   ├── references/
│   ├── diagrams/
│   └── fixtures/
├── artifacts/
│   └── curated/
└── journal/
    └── <device-id>/
        └── <event-ulid>.json
```

Локально рядом могут существовать, но не синхронизироваться:

```text
plans/<plan-id>/
├── views/
├── context-cache/
├── runs/
├── role-streams/
├── scratch/
└── locks/
```

### Каноническое и производное

| Данные | Канонические | Git | Комментарий |
|---|---:|---:|---|
| `manifest.json` | Да | Да | Версия схемы, lifecycle, metadata |
| `brief.json` | Да | Да | Цель, ограничения, non-goals |
| `phases/*.json` | Да | Да | Типизированные фазы |
| `items/*.json` | Да | Да | Исполнимые элементы |
| `units/*.json` | Да | Да | Единицы работы |
| `decisions/*.json` | Да | Да | Архитектурные решения |
| `documents/*.json` | Да | Да | Структурированные документы |
| `materials/manifest.json` | Да | Да | Индекс дополнительных материалов |
| `materials/notes/*.md` | Да | Да | Если материал намеренно добавлен |
| `artifacts/curated/*` | Да | Да | Только явно опубликованные evidence |
| `views/` | Нет | Нет | Перестраивается |
| `context-cache/` | Нет | Нет | Зависит от checkout и модели |
| `runs/` | Нет | Нет | Runtime и потенциально секретный контекст |
| `role-streams/*.jsonl` | Нет | Нет | Большой объём и возможные секреты |
| `locks/` | Нет | Нет | Локальная конкурентность |
| `scratch/` | Нет | Нет | Временные файлы |
| `backups/` | Нет | Нет | Локальное восстановление |

### Дополнительные материалы

Чтобы дополнительные документы не перегружали исполнительную модель, каждый материал должен иметь metadata:

```json
{
  "schema": "plan-material/v1",
  "id": "mat_api_research",
  "path": "references/api-research.md",
  "kind": "research",
  "title": "API compatibility investigation",
  "summary": "Findings relevant to transport selection.",
  "relevance": [
    "item_transport_adapter"
  ],
  "load_policy": "on-demand",
  "sensitivity": "internal",
  "verified_at": "2026-10-17",
  "digest": "sha256:..."
}
```

Поддерживаемые `load_policy`:

- `always` — критический короткий документ.
- `for-role:<role>` — только planner, executor или reviewer.
- `for-item:<id>` — только конкретный item.
- `on-demand` — доступен context scout, но не загружается автоматически.
- `human-only` — никогда не попадает модели без явного запроса.
- `archived` — сохраняется, но не участвует в selection.

### Задачи и items

Не следует создавать вторую параллельную систему задач, если plan items уже выполняют ту же функцию.

Разделение должно быть формальным:

- **Plan item** — часть конкретного плана, имеет acceptance, write set и зависимости.
- **Standalone task** — входящая работа, ещё не включённая в план.
- **Run** — локальная попытка выполнения item/task.
- **Issue** — наблюдаемая проблема или follow-up.
- **Decision** — зафиксированный выбор.

После включения standalone task в план она получает связь:

```json
{
  "promoted_to": {
    "plan_id": "plan_gui_v2",
    "item_id": "item_config_transactions"
  }
}
```

Копировать её текст в два канонических места нельзя.

***

## Git-политика

### Рекомендуемый `.gitignore`

```gitignore
# Machine identity and local bindings
/device.json
/bindings.toml
/bindings.d/
/local/
/config/
/state/
/cache/
/logs/

# Secrets and environment
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
credentials.*
secrets.*
auth.*
tokens.*

# Runtime
**/locks/
**/*.lock
**/*.pid
**/tmp/
**/scratch/
**/runs/
**/state/
**/backups/

# Generated plan projections
projects/**/plans/**/views/
projects/**/plans/**/context-cache/
projects/**/plans/**/role-streams/
projects/**/plans/**/artifacts/raw/
projects/**/plans/**/*.jsonl

# GUI and indexes
gui.db
gui.db-*
**/indexes/
**/search-index/
**/thumbnails/

# Provider-local configuration
.claude/
.codex/
.grok/
.cursor/
.mcp.json
.mcp.json.bak

# OS/editor
.DS_Store
Thumbs.db
.idea/
.vscode/
*.swp
*.bak
```

Исключение всех `*.jsonl` может оказаться слишком широким, если журнал останется каноническим. Поэтому лучше перейти с общего `log.jsonl` на отдельные immutable event files либо явно разрешить только один канонический журнал.

### `.gitattributes`

```gitattributes
* text=auto

*.json text eol=lf
*.md text eol=lf
*.toml text eol=lf
*.yaml text eol=lf
*.yml text eol=lf

# Generated and local files should never reach merge,
# but this provides a defensive fallback.
**/views/** linguist-generated=true
```

Для канонических JSON нужен deterministic formatting:

- UTF-8.
- LF.
- Стабильный порядок ключей.
- Один завершающий newline.
- Запрет timestamp changes без семантического изменения.
- Stable IDs вместо array-index identity.

### Проблема `log.jsonl`

Один append-only `log.jsonl` конфликтует при параллельной работе двух компьютеров. Git не является надёжным multi-writer журналом для одного файла.

Предпочтительный формат:

```text
journal/
├── macbook-a/
│   ├── 01JB...json
│   └── 01JC...json
└── workstation-b/
    ├── 01JD...json
    └── 01JE...json
```

Каждое событие:

```json
{
  "schema": "plan-event/v1",
  "event_id": "01JD...",
  "device_id": "dev_...",
  "occurred_at": "2026-10-17T09:30:00Z",
  "entity": "item:item_gui_config",
  "type": "status_changed",
  "previous_revision": "sha256:...",
  "payload": {
    "from": "pending",
    "to": "in_progress"
  }
}
```

Материализатор сортирует события по причинным зависимостям и `event_id`. Если `previous_revision` не совпадает, возникает typed conflict, а не silent overwrite.

### Секреты

`.gitignore` не защищает данные, которые уже попали в Git history. Поэтому перед commit нужны:

- Secret scan staged content.
- Запрет абсолютных home paths.
- Запрет known provider token formats.
- Проверка файлов больше заданного лимита.
- Проверка неизвестных директорий верхнего уровня.
- Проверка executable files.
- Проверка symlink, выходящих за workspace.
- Отчёт, какие файлы будут опубликованы.

Команда:

```bash
swissknifeman workspace doctor --publish-safety
```

должна блокировать push при high-severity проблемах.

***

## Команды workspace

Наиболее понятный namespace:

```text
swissknifeman workspace ...
```

`sync` следует оставить операцией, а не названием сущности.

### Базовые команды

```bash
swissknifeman workspace init
swissknifeman workspace connect --remote <url>
swissknifeman workspace clone <url>
swissknifeman workspace status
swissknifeman workspace doctor
swissknifeman workspace sync
swissknifeman workspace pull
swissknifeman workspace push
swissknifeman workspace disconnect
```

### Управление проектами

```bash
swissknifeman workspace project attach [--project DIR]
swissknifeman workspace project list
swissknifeman workspace project show <project-id>
swissknifeman workspace project rebind <project-id> --path DIR
swissknifeman workspace project detach <project-id>
swissknifeman workspace project archive <project-id>
```

### Инициализация remote

Рекомендуемый сценарий:

```bash
swissknifeman workspace connect \
  --remote git@github.com:dmitry/swissknifeman-workspace.git
```

Операция должна:

1. Проверить, что remote доступен.
2. Определить: empty remote, существующий workspace или обычный неизвестный repo.
3. Не выполнять destructive reset.
4. Создать temporary clone.
5. Проверить schema/version.
6. Проверить отсутствие конфликтующего workspace identity.
7. Создать baseline `.gitignore` и `.gitattributes`.
8. Импортировать локальные portable данные.
9. Выполнить publish-safety scan.
10. Показать dry-run commit.
11. Предложить `--commit`, но не push по умолчанию.
12. При `--push` явно вывести branch и remote.

### Вывод init

```text
Workspace initialized

Root:      ~/.local/share/swissknifeman/workspace
Remote:    git@github.com:dmitry/swissknifeman-workspace.git
Branch:    main
Projects:  7 discovered, 4 attached
Portable:  132 files
Ignored:   418 files
Warnings:  2

No commit or push was performed.

Next:
  swissknifeman workspace doctor
  swissknifeman workspace sync --commit
  swissknifeman workspace push
```

***

## Синхронизация

### Режимы

| Режим | Поведение | Рекомендация |
|---|---|---|
| Manual | Только явный `workspace sync` | Default |
| On change | Debounce, local commit | Допустимо |
| Scheduled | Pull/reconcile/push по таймеру | Opt-in |
| On exit | После завершения Launcher session | Опционально |
| Git hooks | Commit/push из hooks | Не использовать как основной режим |

### Почему не автопуш по каждому событию

Автопуш после каждой мутации создаёт:

- большое количество служебных commits;
- гонки между компьютерами;
- push failures в середине операций;
- риск публикации незаконченного плана;
- проблемы при offline-режиме;
- merge conflict, который пользователь замечает слишком поздно.

Лучший режим:

```text
mutation
  -> atomic local write
  -> local change journal
  -> debounce 30–120 seconds
  -> validate
  -> create grouped commit
  -> pull --rebase equivalent with safety checks
  -> push
```

Но Git-команды должны выполняться не через непрозрачный shell hook, а через `WorkspaceSyncService` с audit events.

### Commit policy

Пример сообщений:

```text
skm(plan): update GUI configuration audit
skm(task): complete item item_config_transactions
skm(project): attach swissknifeman checkout
skm(material): add provider prompting research
skm(workspace): migrate schema v1 to v2
```

Один commit должен содержать завершённую логическую транзакцию. Изменение статуса item и соответствующее evidence не следует разделять.

### Conflict policy

Автоматически можно разрешать:

- добавление разных immutable files;
- независимые изменения разных entities;
- regeneration удалённых `views/`;
- пересоздание indexes.

Требуют typed conflict:

- два изменения одного поля одной revision;
- удаление против изменения;
- изменение schema/version;
- изменение project identity;
- одновременное редактирование одного decision;
- расхождение lifecycle state.

GUI должен показывать semantic conflict:

```text
Item item_gui_config

Local:
  status = done
  acceptance.V3 = pass

Remote:
  status = blocked
  blocker = "GUI schema mismatch"
```

Показывать пользователю сырой JSON merge conflict недостаточно.

### Активные runs

Runtime lease не должен синхронизироваться. Между компьютерами можно синхронизировать только informational presence:

```json
{
  "project_id": "prj_...",
  "item_id": "item_...",
  "device_id": "dev_...",
  "started_at": "...",
  "expires_at": "...",
  "kind": "advisory-claim"
}
```

Но этот claim:

- не заменяет локальный lock;
- автоматически истекает;
- не может навсегда заблокировать item;
- не считается доказательством работающего процесса;
- не должен коммититься при каждом heartbeat.

Для настоящей одновременной multi-device координации Git недостаточно; потребуется отдельный coordination backend. Для первого релиза advisory claim достаточно.

***

## Миграция планов

### Отдельная команда

```bash
swissknifeman workspace migrate discover
swissknifeman workspace migrate plan --project DIR --dry-run
swissknifeman workspace migrate apply --project DIR
swissknifeman workspace migrate verify
swissknifeman workspace migrate cleanup --project DIR
```

### Процесс

1. Найти `plans/`, `.swissknifeman/`, legacy locations и launcher registry.
2. Определить проект по Git identity.
3. Построить manifest всех канонических и производных файлов.
4. Исключить `views/`, cache, runtime, role streams и backups.
5. Скопировать канонические файлы во временную staging-директорию.
6. Провести schema validation.
7. Проверить digest каждого файла.
8. Атомарно переместить staging в workspace.
9. Обновить локальный binding.
10. Проверить, что planner читает новый источник.
11. Оставить старые файлы до явного cleanup.
12. При cleanup удалить их только после повторной digest verification.

### Совместимость

На переходный период resolver:

```text
portable workspace plan exists
  -> use portable

otherwise project-local legacy plan exists
  -> read legacy, emit warning

otherwise
  -> create portable
```

Dual-write запрещён: он почти гарантированно создаст divergence.

Нужен срок удаления legacy lookup, например через две minor-версии, но cleanup должен оставаться явной командой пользователя.

***

## GUI: архитектурный аудит

[`packages/gui/README.md`](https://github.com/academici/swissknifeman/blob/main/packages/gui/README.md) декларирует правильные базовые принципы:

- GUI является control plane, а не вторым источником истины.
- Frontend не пишет файлы напрямую.
- Backend формирует команды из зарегистрированных descriptors.
- Конфигурация меняется через safe transactions.
- Backend доступен только через loopback и session secret.
- GUI state является перестраиваемым индексом.

Однако статус документа указывает, что часть desktop/sidecar функциональности ещё является target layout. Наличие каталогов `desktop/` и `sidecar/` само по себе не доказывает готовность production path; необходимо проверять capability end-to-end.

### Главный риск конфигурации

Нельзя строить GUI по модели:

```text
effective config
  -> пользователь меняет поле
  -> GUI записывает итоговый merged config в один файл
```

Это уничтожает provenance и может перенести machine-local значение в portable слой.

Нужная модель:

```text
machine defaults
  + workspace portable
  + project portable
  + project local
  + invocation override
  = effective config
```

GUI показывает effective value, но редактирует выбранный слой.

### Metadata поля конфигурации

Для каждого schema field нужны:

```json
{
  "scope": ["machine", "workspace", "project", "invocation"],
  "portable": false,
  "secret": false,
  "restart_required": true,
  "provider_specific": true,
  "advanced": false,
  "deprecated": false,
  "ui": {
    "control": "model-selector",
    "group": "Execution",
    "help": "..."
  }
}
```

Без этих полей frontend вынужден угадывать семантику по имени параметра.

### Экран поля

```text
Preferred implementation provider

Effective value: claude-code
Source: Machine config
Portable: No
Applies to: This computer
Restart required: No

[ claude-code ▼ ]

Other layers:
  Workspace: not set
  Project: codex
  Invocation: not set
```

### Транзакция

Frontend отправляет не новый файл, а typed patch:

```json
{
  "schema": "config-patch/v1",
  "target": {
    "scope": "machine",
    "project_id": null
  },
  "base_revision": "sha256:...",
  "operations": [
    {
      "op": "replace",
      "path": "/providers/default",
      "value": "codex"
    }
  ]
}
```

Backend:

1. Перечитывает target layer.
2. Сравнивает `base_revision`.
3. Валидирует patch.
4. Показывает effective diff.
5. Проверяет cross-field constraints.
6. Пишет во временный файл.
7. Выполняет fsync.
8. Делает atomic replace.
9. Записывает audit event.
10. Возвращает новую provenance map.

### Preview

Перед применением:

```diff
Target: machine config
File: ~/.config/swissknifeman/config.toml

-[execution]
-default_provider = "claude-code"
+[execution]
+default_provider = "codex"

Effective changes:
  executor provider: claude-code -> codex
  reviewer provider: unchanged (grok)
  plan designer: unchanged (frontier route)
```

### Необходимые проверки GUI

#### Конфигурация

- Нельзя записать machine path в portable layer.
- Нельзя записать secret в workspace.
- Unknown keys сохраняются либо явно блокируются; они не должны тихо исчезать.
- Concurrent edit возвращает `CONFIG_REVISION_CONFLICT`.
- Validation failure не меняет файл.
- Неизменившийся patch не создаёт audit event.
- Rollback является новой транзакцией, а не history rewrite.
- Provider/model selector строится из model catalog.
- Удалённая модель отображается как unavailable, но старое значение не уничтожается автоматически.
- Поля с restart requirement дают конкретное действие.

#### Планы

- GUI выполняет domain mutation, а не редактирует JSON.
- `views/` отображаются как derived и могут перестраиваться.
- Материалы грузятся лениво.
- Большие attachments не включаются в context автоматически.
- Lifecycle transition валидируется backend.
- На конфликте показывается semantic merge.
- Изменение plan не требует, чтобы checkout репозитория находился по старому пути.

#### Синхронизация

- Видны ahead/behind/diverged.
- Видна последняя успешная синхронизация.
- Видно, какие файлы portable, ignored и suspicious.
- Push никогда не происходит из UI без отображаемой политики.
- Первое подключение remote требует explicit confirmation.
- Credential prompts обрабатываются вне логов и audit payload.

#### Desktop

- Tauri shell не получает произвольный filesystem access.
- Frontend не может передать backend произвольный argv.
- Deep links не выполняют команды.
- Session secret не попадает в URL history дольше необходимого.
- Browser и desktop используют одинаковый typed API.
- Sidecar version совместима со frontend contract version.

### Рекомендуемые экраны

- Workspace overview.
- Projects and bindings.
- Plans.
- Tasks inbox.
- Plan materials.
- Sync status.
- Semantic conflicts.
- Configuration layers.
- Providers and models.
- Orchestrator runs.
- Skills and instruction packs.
- Diagnostics.
- Audit trail.

***

## Оркестратор: сильные стороны

Текущий `orch` уже реализует зрелую последовательность: context, scout, executor, checks, review, triage, correction, registration и commit, а также resume закрытых стадий. Это описано в [`packages/orch/README.md`](https://github.com/academici/swissknifeman/blob/main/packages/orch/README.md).

Сильные решения:

- Engine-neutral contracts.
- Typed stage outputs.
- Capability matrix.
- Frozen launch plan с digest входов.
- Work source abstraction.
- Evidence gate перед регистрацией.
- Отдельные reviewer и triager.
- Исполнитель не получает весь plan автоматически.
- Scout output маркируется как leads, а не facts.
- Acceptance checks повторно запускаются conductor.
- Prompt manifest фиксирует blocks, origins, digests и token estimates.
- Resume не должен повторять закрытые шаги.
- Sandbox/write fence различаются по ролям.

Prompt assembly реализован централизованно в [`conductor/prompts.py`](https://github.com/academici/swissknifeman/blob/main/packages/orch/lib/orch/conductor/prompts.py), что создаёт хорошую точку для дальнейшей адаптации.

***

## Оркестратор: слабые места

### Provider policy не является контрактом

Prompt manifest содержит route:

```json
{
  "provider": "...",
  "model": "...",
  "effort": "..."
}
```

Но route metadata само по себе не доказывает, что prompt был адаптирован под provider/model family. Нужен отдельный versioned документ:

```json
{
  "schema": "prompt-profile/v1",
  "id": "claude-code/sonnet/executor/v3",
  "provider": "claude-code",
  "model_patterns": [".*sonnet.*"],
  "roles": ["executor"],
  "rendering": {
    "structure": "xml-boundaries",
    "progress_updates": "minimal",
    "examples": "contract-only"
  },
  "rules": [
    "separate instructions from untrusted context",
    "state output contract once"
  ]
}
```

Profile resolution:

```text
base role contract
  + repository rules
  + role skill pack
  + provider profile
  + model-family profile
  + task-mode profile
  + runtime evidence
  = rendered prompt
```

Каждый слой должен иметь digest и отображаться в prompt manifest.

### Общие progress lines

Сейчас роли получают требование печатать:

```text
[orch] <item> <step> <what>
```

перед каждым крупным шагом.

Для интерактивного процесса это полезно. Для headless coding role это может:

- расходовать output tokens;
- смешиваться с result contract;
- стимулировать модель останавливаться после описания плана;
- увеличивать вероятность невалидного final block.

Codex prompting guide рекомендует удалять лишние требования upfront plan, preambles и status updates, если они мешают rollout до завершения. [developers.openai](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide.md)

Предлагаемая политика:

| Role/provider | Progress |
|---|---|
| Claude interactive | Short milestone updates |
| Claude headless | Only conductor-owned events |
| Codex implementation | Suppress model progress |
| Grok reviewer | No progress unless needed |
| Researcher | Per-source structured events |
| Registrar | None |

Прогресс надёжнее собирать из tool/process events, а не просить модель воспроизводить протокол вручную.

### Дублирование инструкций

Сейчас возможны одновременно:

- canonical role text;
- machine/project stub;
- repository rules;
- named skills;
- embedded skills;
- conductor run rules;
- provider-native `AGENTS.md` или `CLAUDE.md`.

Codex автоматически читает применимые `AGENTS.md`, причём более глубокие файлы переопределяют верхние. Повторная вставка тех же правил в prompt увеличивает токены и может исказить precedence. [learn.chatgpt](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md)

Нужен `InstructionGraph`:

```text
instruction
├── semantic_id
├── origin
├── scope
├── precedence
├── provider_native
├── digest
└── conflicts_with
```

Перед render выполняются:

- deduplication по semantic ID;
- conflict detection;
- precedence resolution;
- provider-native suppression;
- token budget selection.

### Diff как единый блок

Передача полного diff reviewer может стать самым большим блоком prompt. Нужен дифф-пакет:

```text
change summary
changed paths
risk hotspots
API/schema changes
targeted diff chunks
full diff available on demand
```

Reviewer должен сначала получать:

- acceptance contract;
- changed paths;
- risk features;
- symbol-level diff;
- unresolved deviations;
- targeted test results.

Полный diff включается, только если помещается в бюджет или явно нужен.

### Проверки и review

Если acceptance checks дорогие, параллельный review экономит wall time. Но при очевидном compile/test failure reviewer тратит ресурсы на заведомо непринимаемый candidate.

Политика:

- Fast structural checks — до review.
- Expensive integration checks — параллельно с review.
- Reviewer получает статус `checks_pending`.
- Если fast check красный, review откладывается.
- Security review может запускаться независимо.

### Scout

Scout полезен, но его результат должен быть typed:

```json
{
  "entrypoints": [],
  "symbols": [],
  "likely_paths": [],
  "tests": [],
  "rules": [],
  "unknowns": [],
  "confidence": {}
}
```

Свободный текст затрудняет:

- дедупликацию;
- сравнение scout results;
- измерение точности;
- lazy loading;
- построение GUI.

### Контекст

Нужен `ContextPack/v1`:

```json
{
  "goal": {},
  "constraints": [],
  "non_goals": [],
  "acceptance": [],
  "write_scope": {},
  "repository_map": [],
  "evidence": [],
  "materials": [],
  "unknowns": [],
  "excluded": [
    {
      "source": "...",
      "reason": "budget"
    }
  ]
}
```

Контекстная модель должна отвечать не «что найдено», а:

- почему этот блок нужен данной роли;
- какой claim он поддерживает;
- насколько свежий;
- является ли он инструкцией или данными;
- можно ли ему доверять;
- сколько токенов он стоит.

***

## Адаптация под провайдеров

### Claude

Официальные рекомендации Anthropic предлагают ясные прямые инструкции, явный формат результата, структурирование сложного смешанного контекста и использование релевантных примеров. XML-теги особенно полезны там, где нужно разделить instructions, context, input и документы. [platform.claude](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md)

Рекомендуемый renderer:

```xml
<task>
  ...
</task>

<constraints>
  ...
</constraints>

<context>
  <document source="..." trust="repository">
    ...
  </document>
</context>

<acceptance>
  ...
</acceptance>

<output_contract>
  ...
</output_contract>
```

Не нужно превращать любой короткий prompt в XML. XML применяется только для границ между неоднородными блоками.

Для Sonnet:

- Конкретная задача.
- Ограниченный write set.
- Явные acceptance checks.
- Релевантные файлы и symbols.
- Один output contract.
- Минимум motivational text.
- Не повторять одно правило разными словами.
- Не просить описывать очевидный план до работы.
- Давать examples только для сложного закрытого формата.

### Codex

Codex лучше получает задачи, похожие на issue или PR: конкретные пути, компоненты, outcome, boundaries и validation. OpenAI отдельно рекомендует `AGENTS.md` для устойчивых repository instructions и ExecPlan для крупных изменений. [developers.openai](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex.md)

Рекомендуемая форма:

```markdown
## Goal

Implement workspace-backed plan storage.

## Scope

- packages/aicore/lib/aicore/state/locations.py
- packages/planner/...

## Required behavior

- ...
- ...

## Non-goals

- No background sync service in this item.
- No legacy cleanup.

## Validation

- command
- expected result
```

Для Codex:

- Не дублировать уже загруженный `AGENTS.md`.
- Не заставлять выдавать постоянные progress preambles.
- Давать полные repository-relative paths.
- Ссылаться на существующий аналог реализации.
- Указывать observable outcomes.
- Для значительных изменений передавать утверждённый ExecPlan.
- Не смешивать exploration и implementation в одной неограниченной задаче.

### Grok

Публичные рекомендации xAI для reasoning-моделей сводятся к прямому описанию задачи, ограничений и формата вывода; также следует перечислять только реально доступные инструменты. [docs.x](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech/prompting-guide)

Для Grok reviewer:

```markdown
## Objective

Find correctness, security, and contract violations in the candidate.

## Inputs

- Acceptance contract
- Changed paths
- Diff chunks
- Test results

## Guardrails

- Read-only.
- Report concrete failure scenarios.
- Do not report style preferences.

## Output

Return exactly review-findings/v1.
```

Не следует переносить voice-specific рекомендации xAI в coding roles без проверки. Provider profile должен ссылаться на тип workload, для которого рекомендация подтверждена.

***

## Plan design

Текущий model catalog явно запрещает auto-mode для plan design и plan audit и закрепляет frontier-capable модели в соответствующих ролях. Это правильная защита, но она должна проверяться не только catalog metadata, а непосредственно в launch plan. См. [`model-catalog.json`](https://github.com/academici/swissknifeman/blob/main/packages/aicore/configs/model-catalog.json).

### Рекомендуемый pipeline

```text
request normalization
  -> repository reconnaissance
  -> requirement synthesis
  -> architecture options
  -> owner decisions if necessary
  -> plan draft
  -> independent plan audit
  -> correction
  -> deterministic validation
  -> freeze
```

### Requirement synthesis

В frontier model передаются:

- цель пользователя;
- observable outcome;
- ограничения;
- non-goals;
- текущая архитектура;
- repository map;
- подтверждённые источники;
- неизвестные вопросы;
- project rules;
- планируемая granularity.

Не передаются:

- raw transcript всей сессии;
- повторяющиеся README;
- все скиллы проекта;
- generated views;
- runtime logs;
- нерелевантные исследования;
- machine config;
- provider credentials;
- устаревшие материалы без маркировки.

### Архитектурные варианты

До построения детального плана модель должна сформировать 2–3 варианта только там, где реально существует архитектурная развилка.

Пример:

| Решение | Вариант A | Вариант B | Рекомендация |
|---|---|---|---|
| Git root | Весь `SKM_HOME` | Вложенный portable workspace | B |
| Journal | Один JSONL | Immutable per-device events | B |
| Sync | Git hooks | Workspace service | Service |
| Project identity | Path | Stable ID + remote identity | Stable ID |

Если решение уже принято контрактом, генерировать фиктивные альтернативы не нужно.

### План как исполнимая спецификация

Каждый item должен иметь:

```json
{
  "id": "item_workspace_locations",
  "goal": "Introduce portable workspace path resolution.",
  "why": "Plans must survive checkout relocation.",
  "depends_on": [],
  "write_set": [],
  "read_context": [],
  "requirements": [],
  "non_goals": [],
  "acceptance": {
    "checks": [],
    "observations": []
  },
  "migration": {},
  "rollback": {},
  "risks": [],
  "materials": []
}
```

Фразы вроде «сделать качественно», «учесть edge cases», «следовать best practices» должны отклоняться validator как непроверяемые.

### Plan audit

Независимый auditor проверяет:

- Все ли цели покрыты items.
- Нет ли скрытых решений внутри implementation steps.
- Есть ли migration и rollback.
- Не дублируются ли канонические источники.
- Замкнут ли dependency graph.
- Реальны ли write sets.
- Проверяют ли acceptance checks поведение, а не существование файла.
- Не требует ли item недоступных credentials.
- Не смешаны ли крупные независимые изменения.
- Нет ли circular ownership между пакетами.
- Учтена ли backward compatibility.
- Можно ли выполнить item одной моделью в одном bounded run.
- Не включены ли machine-specific значения в portable data.

***

## Аудит скиллов

В репозитории существует крупный набор доменных и ролевых skills, а `skiller` уже имеет подсистемы budget, compatibility, audit, eval и post-run analysis. Существующая compatibility-проверка покрывает license, provenance, dangerous instruction patterns, token budget и известные tools для vendored skills; это полезный supply-chain уровень, но не semantic quality audit. См. [`quality/compat.py`](https://github.com/academici/swissknifeman/blob/main/packages/skiller/lib/skiller/quality/compat.py).

Post-run analyzer измеряет токены, cache usage, tools и explicit Skill calls, но сам документирует blind spot: native preload и auto-trigger могут быть невидимы, поэтому `DEAD` является эвристикой. См. [`quality/analyze.py`](https://github.com/academici/swissknifeman/blob/main/packages/skiller/lib/skiller/quality/analyze.py).

### Новая типизация

Skills следует разделить:

| Тип | Назначение | Пример |
|---|---|---|
| Domain knowledge | Факты и соглашения предметной области | Laravel, finance |
| Procedure | Последовательность специализированной работы | Security review |
| Tool usage | Как применять конкретный инструмент | Blender |
| Output contract | Структура результата | Review findings |
| Repository policy | Локальные правила проекта | Testing/layout |
| Provider adapter | Адаптация к модели | Claude/Codex/Grok |
| Role behavior | Ограничения роли | Reviewer/read-only |

Один skill не должен одновременно:

- задавать persona;
- менять tool permissions;
- определять output format;
- добавлять domain facts;
- переопределять autonomy policy.

### Manifest

```yaml
schema: skill/v2
id: quality/security-review
version: 2.1.0
purpose: Detect exploitable security defects in code changes.
roles:
  - reviewer
providers:
  - "*"
model_families:
  - "*"
triggers:
  - security-sensitive paths changed
  - authentication or authorization modified
non_triggers:
  - formatting-only change
allowed_tools:
  - Read
  - Grep
output_contract: review-findings/v1
budget:
  preferred_tokens: 900
  hard_max_tokens: 1600
conflicts:
  - quality/style-only-review
supersedes: []
verified_at: 2026-10-17
```

### Антипаттерны

Автоматический linter должен находить:

- «Делай качественно».
- «Будь внимателен».
- «Используй best practices» без конкретизации.
- «Никогда не ошибайся».
- Длинные persona-описания без влияния на outcome.
- Требование раскрывать chain of thought.
- Обязательный upfront plan для любой простой задачи.
- Обязательные progress updates для headless executor.
- Повтор project rules.
- Повтор output contract.
- Инструкции для tools, которых нет.
- Provider-specific syntax без provider guard.
- Жёстко записанное имя быстро устаревающей модели.
- Конфликтующие требования краткости и полного анализа.
- «Всегда запускай все тесты» при наличии conductor-owned checks.
- «Спроси пользователя при любой неопределённости».
- «Самостоятельно принимай любые решения».
- Указания менять файлы для read-only reviewer.
- Указания читать весь репозиторий.
- Указания загружать все связанные материалы.
- Недетерминированные критерии успеха.

### Семантические конфликты

Нужен compiler instruction graph, который обнаруживает:

```text
skill A: ask before scope expansion
skill B: never ask, continue autonomously
role: block outside write set
run policy: project-wide fence
```

Результат должен быть compile error либо детерминированное precedence resolution, а не скрытая борьба инструкций в prompt.

### Eval

Каждый значимый skill проверяется минимум четырьмя наборами:

1. Positive trigger — skill должен подключиться.
2. Negative trigger — не должен подключиться.
3. Benefit eval — с skill результат лучше baseline.
4. Cross-provider eval — skill не ломает Claude, Codex и Grok.

Метрики:

- Acceptance pass rate.
- First-pass pass rate.
- Review defect recall.
- False-positive rate.
- Correction rounds.
- Tokens.
- Wall time.
- Tool errors.
- Scope violations.
- Contract parse failures.
- Owner questions.
- Unsupported assumptions.

Skill сохраняется, если даёт измеримое улучшение или обеспечивает обязательную policy guarantee. Наличие красивого текста не является основанием.

### Жизненный цикл

```text
draft
  -> linted
  -> evaluated
  -> active
  -> degraded
  -> deprecated
  -> archived
```

Повторная проверка запускается при:

- новой major model family;
- изменении provider tools;
- изменении role contract;
- превышении token budget;
- росте correction rate;
- отсутствии наблюдаемого usage;
- появлении conflicting skill;
- устаревании cited guidance.

***

## Метрики оркестратора

Нужна аналитика не только по токенам, но и по качеству решений.

### На item

```json
{
  "first_pass_acceptance": false,
  "executor_rounds": 2,
  "review_rounds": 1,
  "confirmed_findings": 1,
  "rejected_findings": 0,
  "scope_deviations": 1,
  "owner_questions": 0,
  "prompt_tokens_by_role": {},
  "context_blocks_used": [],
  "context_blocks_excluded": [],
  "provider_profile": "...",
  "skill_set_digest": "..."
}
```

### На profile

- Parse failure rate.
- Invalid structured output rate.
- Tool misuse.
- Premature stop.
- Redundant status output.
- Acceptance success.
- Reviewer precision.
- Median correction rounds.
- Cost and latency.
- Context block effectiveness.

### Контекстная эффективность

Для каждого block:

```text
included
referenced by model
led to touched path
supported a finding
was duplicated
was stale
could be removed
```

Это позволит постепенно уменьшать prompts вместо постоянного добавления новых инструкций.

***

## Рекомендуемые изменения

### `aicore`

Целевые области:

- [`packages/aicore/lib/aicore/state/locations.py`](https://github.com/academici/swissknifeman/blob/main/packages/aicore/lib/aicore/state/locations.py)
- `packages/aicore/configs/config.schema.json`
- `packages/aicore/configs/gitignore-policy.json`

Добавить:

```python
workspace_root()
workspace_projects_dir()
workspace_project_dir(project_id)
machine_bindings_file()
device_identity_file()
```

Инвариант: workspace path разрешается централизованно, а не вычисляется отдельно planner, GUI и Launcher.

### `planner`

Добавить abstraction:

```python
class PlanRepository:
    def list_projects(...)
    def list_plans(project_id)
    def open_plan(project_id, plan_id)
    def mutate(...)
    def render_views(...)
```

Реализации:

```text
WorkspacePlanRepository
LegacyProjectPlanRepository   # read-only migration period
```

Plan object не должен предполагать, что plan root находится внутри source repository.

### `maind` / Launcher

Launcher должен:

1. Resolve текущий source project.
2. Resolve stable project ID.
3. Проверить binding.
4. Передать `SKM_PROJECT_ID`.
5. Передать `SKM_WORKSPACE_ROOT`.
6. Не передавать remote credentials.
7. Не создавать workspace Git commits самостоятельно.

### `gui`

Добавить bridges:

```text
gui-workspace
gui-sync
gui-skiller
```

GUI не должен импортировать внутренности planner/workspace напрямую; текущий принцип bridge-based integration следует сохранить.

### `orch`

Добавить:

```text
configs/prompt-profiles/
├── claude-code/
├── codex/
├── grok/
└── cursor/
```

И контракты:

```text
prompt-profile/v1
instruction-graph/v1
context-pack/v1
prompt-evaluation/v1
```

Manifest должен фиксировать:

- profile ID;
- profile digest;
- suppressed instructions;
- deduplicated instructions;
- conflicts resolved;
- native provider instructions;
- model family;
- task mode.

### `skiller`

Добавить команды:

```bash
skiller lint-modern
skiller conflicts
skiller eval-benefit
skiller eval-cross-provider
skiller explain-instructions
skiller retire-candidates
```

`explain-instructions` должен выводить итоговый instruction graph для конкретного run.

***

## Порядок реализации

### Фаза 0 — решения

Зафиксировать ADR:

- Portable workspace является отдельным Git root.
- Machine state не находится в portable repo.
- Project identity не основана на path.
- Views являются generated.
- Runtime не синхронизируется.
- Auto-sync opt-in.
- Git hooks не являются основным механизмом.
- Legacy plan storage становится read-only после миграции.
- Prompt profiles versioned и проверяемы.

### Фаза 1 — workspace core

Реализовать:

- Workspace location resolver.
- Workspace manifest.
- Device identity.
- Project manifest.
- Machine-local bindings.
- Project matching по remotes.
- `workspace init/status/doctor`.
- Publish-safety checks.

Acceptance:

- Перемещение checkout не теряет планы.
- Два checkout одного remote разрешаются в один project ID.
- Два проекта с одинаковым basename не объединяются.
- Machine path не попадает в workspace.
- `SKM_HOME` остаётся полностью изолированным.

### Фаза 2 — planner repository

Реализовать:

- `PlanRepository`.
- Workspace backend.
- Legacy reader.
- Views regeneration.
- Material manifests.
- Lazy context material loading.
- Per-device journal либо иной conflict-safe журнал.

Acceptance:

- Planner работает без `plans/` в source repo.
- Render создаёт `views/` локально.
- Удаление `views/` ничего не теряет.
- Plan open не требует старого checkout path.
- Generated files не показываются в Git status workspace.

### Фаза 3 — миграция

Реализовать:

- Discovery.
- Dry-run manifest.
- Apply.
- Digest verify.
- Rollback.
- Explicit cleanup.
- Migration report.

Acceptance:

- Повторный apply идемпотентен.
- Ошибка не оставляет partial project.
- Legacy files не удаляются автоматически.
- После cleanup planner продолжает работать.
- Сломанная schema блокирует миграцию до записи.

### Фаза 4 — Git sync

Реализовать:

- Remote connect/clone.
- Ahead/behind status.
- Grouped commits.
- Pull/reconcile.
- Typed conflicts.
- Push policy.
- Offline queue.
- Secret/path scanning.
- Audit trail.

Acceptance:

- Нет force push.
- Нет destructive reset.
- Diverged branch не перезаписывается.
- Unknown file требует решения.
- Secret blocks commit/push.
- Offline mutations сохраняются локально.
- Повторный sync безопасен.

### Фаза 5 — GUI workspace

Реализовать:

- Workspace overview.
- Bindings.
- Sync status.
- Portable/local classification.
- Migration UI.
- Conflict UI.
- Plan materials.
- Diagnostics.

Acceptance:

- Frontend не формирует Git argv.
- UI показывает конкретный target layer.
- Sync failure не теряет mutation.
- Conflict разрешается domain operation.
- Remote URL и branch видны до push.

### Фаза 6 — config UX

Реализовать:

- Schema annotations.
- Layer-aware editor.
- Provenance.
- ETag/revision.
- Preview.
- Atomic transaction.
- Audit.
- Restart impact.
- Provider/model selectors.

Acceptance:

- Merged config read-only.
- Machine setting не публикуется.
- Portable setting синхронизируется.
- Concurrent changes выявляются.
- Unknown keys не исчезают.
- Invalid patch ничего не пишет.

### Фаза 7 — prompt profiles

Реализовать:

- Prompt profile contract.
- Claude renderer.
- Codex renderer.
- Grok renderer.
- Provider-native instruction detection.
- Instruction deduplication.
- Model-family matching.
- Prompt manifest extension.

Acceptance:

- Один task даёт разные, но семантически эквивалентные prompts.
- Codex не получает лишние progress directives.
- Claude получает явные content boundaries на сложных prompts.
- Grok видит только реальные tools.
- Output contract остаётся одинаковым.
- Profile ID и digest воспроизводимы.

### Фаза 8 — conductor optimization

Реализовать:

- Typed scout result.
- ContextPack.
- Diff chunking.
- Fast-check gate.
- Risk-based routing.
- Context effectiveness telemetry.
- Dynamic review policy.
- Model fallback policy.

Acceptance:

- Resume не повторяет закрытый expensive step.
- Review не запускается после очевидного fast-check failure.
- Large diff не превышает budget.
- Excluded blocks отражены в manifest.
- Correction prompt содержит только необходимые evidence.
- Fallback не меняет model class скрыто.

### Фаза 9 — skills modernization

Реализовать:

- Skill v2 metadata.
- Instruction graph.
- Modern lint.
- Semantic conflict detection.
- Baseline A/B eval.
- Negative trigger tests.
- Cross-provider eval.
- Lifecycle/deprecation.

Acceptance:

- Каждый активный skill имеет purpose и triggers.
- Generic motivational phrases предупреждаются.
- Tool mismatch блокируется.
- Read-only role не получает write instruction.
- Набор скиллов не содержит конфликтующих output contracts.
- Skill без измеримой пользы становится retirement candidate.

***

## Приоритетный backlog

### P0

- ADR portable workspace.
- Stable project ID.
- Workspace resolver.
- Machine-local bindings.
- Workspace `.gitignore`.
- Migration dry-run.
- Secret/path scanner.
- Config scope metadata.
- Prompt profile contract.

### P1

- Workspace planner backend.
- Legacy migration.
- Manual Git sync.
- GUI configuration transactions.
- Provider-aware prompt rendering.
- Instruction deduplication.
- Typed context scout.
- ContextPack manifest.

### P2

- Background sync.
- Semantic merge UI.
- Per-device event journal.
- Skill semantic conflicts.
- Cross-provider evaluations.
- Dynamic risk routing.
- Prompt block effectiveness.

### P3

- Selective project sync.
- Encrypted materials.
- Remote coordination backend.
- Multi-user workspace.
- Shared team policies.
- Distributed run claims.

***

## Что не делать

- Не делать весь `~/.SwiftKnifeMan` Git-репозиторием.
- Не хранить абсолютные checkout paths в portable manifests.
- Не синхронизировать merged effective config.
- Не синхронизировать provider credentials.
- Не использовать dual-write старого и нового plan storage.
- Не рассчитывать на `.gitignore` как единственную защиту.
- Не выполнять автоматический force push.
- Не скрывать Git conflicts автоматическим выбором local или remote.
- Не коммитить `views/`.
- Не коммитить raw model transcripts.
- Не передавать все materials исполнителю.
- Не загружать все skills в каждый run.
- Не задавать всем провайдерам одинаковый prompt layout.
- Не повторять native `AGENTS.md` внутри Codex prompt.
- Не заставлять headless executor постоянно сообщать progress.
- Не смешивать output contract со стилистическим skill.
- Не считать skill полезным только потому, что он был загружен.
- Не разрешать GUI напрямую писать TOML/JSON или собирать shell-команды.
- Не выполнять migration cleanup без digest verification и явного подтверждения.

## Главная архитектурная формула

```text
Source repository
  = код + repository rules + tests

Portable workspace
  = проекты + планы + задачи + решения + отобранные материалы

Machine environment
  = providers + paths + credentials + local preferences

Runtime state
  = runs + leases + logs + raw streams + caches

Generated projections
  = views + indexes + context packs
```

Эти пять областей не должны смешиваться. Именно такое разделение позволит свободно перемещать checkout, использовать разные модели и конфигурации на разных компьютерах, синхронизировать планы через Git и при этом не перегружать исполнительную модель лишним контекстом.