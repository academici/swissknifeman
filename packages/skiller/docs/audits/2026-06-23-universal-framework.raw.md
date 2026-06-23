# Claude Code Agent Universal Framework
## Анализ открытых решений и система универсального наследования для swissknifeman

> **Назначение:** Этот документ — основа для доработки [academici/swissknifeman](https://github.com/academici/swissknifeman).
> Содержит только то, чего ещё нет в репозитории: анализ внешних решений, универсальная модель наследования агентов,
> предложения по расширению `packages/skiller` и `packages/harness`.

---

## 1. Анализ открытых GitHub-проектов

### 1.1 github/spec-kit — Spec-Driven Development

**Репозиторий:** [github/spec-kit](https://github.com/github/spec-kit)
**Концепция:** "Specification before code" — методология, при которой ИИ-агент не пишет код до тех пор, пока не существует исполняемой спецификации: `requirements.md → design.md → tasks.md`.

**Ключевые идеи для swissknifeman:**

| Концепция | Что делает spec-kit | Что можно взять |
|---|---|---|
| `speckit-specify` | Генерирует `requirements.md` перед любым кодом | Скилл-пресет `pre-code-spec` для агента |
| `speckit-design` | Создаёт `design.md` на основе требований | Шаблон субагента-архитектора |
| `speckit-tasks` | Разбивает дизайн на атомарные задачи | Интеграция с maind task-graph |
| Agent skills mode | `--integration claude --integration-options="--skills"` — устанавливает команды как agent skills | **Прямой паттерн для skiller** |
| Executable specs | Спецификации читаются агентом как инструкции, не документация | Формат SKILL.md с секцией `constraints:` |

**Что взять в swissknifeman:**
- Концепция "gate before code": субагент `spec-validator` блокирует реализацию без `design.md`
- Флаг `--integration-options="--skills"` — аналог `skiller connect --mode=agent-skills`
- Структура `tasks.md` как промежуточный артефакт между maind-графом и `.claude/agents/`

**Ссылки:**
- [Блог GitHub: Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [jabelk/claude-speckit-template](https://github.com/jabelk/claude-speckit-template) — готовый шаблон Claude Code + Spec Kit
- [FredAntB/Spec-Driven-Development](https://github.com/FredAntB/Spec-Driven-Development) — skill-обёртка для SDD

---

### 1.2 eyaltoledano/claude-task-master — Task Management System

**Репозиторий:** [eyaltoledano/claude-task-master](https://github.com/eyaltoledano/claude-task-master)
**Концепция:** AI-powered система управления задачами, интегрируемая в любой AI-агент через `.taskmaster/` директорию.

**Архитектурные решения:**

```
.taskmaster/
├── tasks/
│   ├── tasks.json          # граф зависимостей задач
│   └── task_001.txt        # детали задачи (контекст для субагента)
├── docs/
│   └── prd.txt             # Product Requirements Document
└── config.json             # модели, параметры, профиль проекта
```

**Что делает Task Master лучше текущего maind:**

| Функция | Task Master | maind сейчас | Gap |
|---|---|---|---|
| Dependency graph | Встроен в `tasks.json` | graphify отдельный MCP | Нет единого формата |
| Next task suggestion | `task-master next` — анализирует граф | Нет | **Добавить в maind** |
| Complexity scoring | Оценка сложности задачи 1-10 | Нет | **Нужен скилл** |
| Subtask expansion | Рекурсивное дробление задачи | Нет | **Паттерн для агентов** |
| PRD parsing | Агент читает PRD и создаёт задачи | Нет | **Интеграция со spec-kit** |
| Research mode | Субагент исследует перед реализацией | Нет | **Шаблон explore-агента** |

**Ключевой паттерн `CLAUDE.md` из Task Master:**
```markdown
## Development Workflow
1. Check task status: `task-master list`
2. Get next task: `task-master next`
3. Implement: use task details as spec
4. Update status: `task-master set-status --id=X --status=done`
5. Verify dependencies before marking complete
```

**Что взять в swissknifeman:**
- Формат `tasks.json` с полями `dependencies[]`, `status`, `complexity` — унифицировать с maind-графом
- Паттерн `research → plan → implement` как обязательный workflow в шаблонах агентов
- `config.json` с профилем проекта (стек, модели, порог сложности) — расширить `.swissknife.json`

**Ссылки:**
- [eyaltoledano/claude-task-master](https://github.com/eyaltoledano/claude-task-master)
- [Tutorial](https://github.com/eyaltoledano/claude-task-master/blob/main/docs/tutorial.md)

---

### 1.3 VoltAgent/awesome-claude-code-subagents — 100+ Subagents Collection

**Репозиторий:** [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents)
**Концепция:** Коллекция специализированных субагентов с чёткой структурой `.claude/agents/*.md`.

**Паттерны именования и организации:**

```
.claude/agents/
├── 01_architect.md         # нумерация = приоритет в /agents listing
├── 02_implementer.md
├── 03_reviewer.md
├── 04_tester.md
└── 05_documenter.md
```

**Best practices из коллекции:**

| Правило | Обоснование |
|---|---|
| Нумерация файлов `01_`, `02_` | Порядок отображения в `/agents`; агент выбирает первый подходящий |
| Короткий system prompt (< 500 символов) | Длинные промпты = перерасход токенов на каждый spawn |
| Явные trigger phrases | `"use proactively when X"` вместо надежды на автоопределение |
| `tools: [Read, Write, Bash]` — минимум | Scope tools = безопасность + предсказуемость |
| Один агент — одна ответственность | Нарушение SRP = непредсказуемое поведение |

**Что взять в swissknifeman:**
- Нумерацию файлов агентов как конвенцию в harness
- Генерацию агентов из профилей (`skiller generate-agent --profile=laravel`)
- Максимальный параллелизм 10 — документировать в CLAUDE.md

**Ссылки:**
- [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents)
- [0xfurai/claude-code-subagents](https://github.com/0xfurai/claude-code-subagents) — ещё 100+ агентов
- [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — 1000+ скиллов, совместимых с Claude Code, Codex, Gemini CLI

---

### 1.4 rahulvrane/awesome-claude-agents — Паттерны оркестрации

**Репозиторий:** [rahulvrane/awesome-claude-agents](https://github.com/rahulvrane/awesome-claude-agents)

**Четыре паттерна оркестрации:**

```
Sequential:   Agent A → Agent B → Agent C → Result
Parallel:     [Agent A, Agent B, Agent C] → merge → Result
Conditional:  Orchestrator → routing → [Agent X | Agent Y]
Review:       Agent Primary → Agent Reviewer → Final Result
```

**Критические ограничения (официально от Anthropic):**
- Максимум 10 параллельных субагентов одновременно
- При достижении лимита — очередь, следующие запускаются по мере завершения
- File lock pattern обязателен при параллельных правках: `create .lock` перед edit

**Решение конфликтов параллельных агентов:**
```markdown
## File Edit Policy (в CLAUDE.md)
- Only ONE agent may edit a file at a time
- Create `.lock` file before editing: `touch {file}.lock`
- Remove lock after edit: `rm {file}.lock`
- If lock exists — wait 30s, retry 3 times, then report conflict
```

---

### 1.5 alexop.dev — Полный стек Claude Code 2026

**Источник:** [Claude Code Explained (2026)](https://alexop.dev/posts/understanding-claude-code-full-stack/)

**Иерархия загрузки контекста (порядок важен):**

```
1. ~/.claude/CLAUDE.md          # глобальный (пользователь)
2. /project/CLAUDE.md           # проектный (корень)
3. /project/subdir/CLAUDE.md    # субдиректорный (при работе в subdir)
4. .claude/agents/*.md          # агенты (при вызове субагента)
5. Skills (deferred loading)    # скиллы (только при явном вызове)
```

**Ключевой вывод:** Skills загружаются отложенно — агент должен принять решение вызвать скилл.
**CLAUDE.md загружается всегда** — это единственный гарантированный контекст каждого хода.

**Deferred Tool Loading (новое в 2026):**
- Скиллы с тегом `deferred: true` загружаются только когда агент явно вызывает `load_skill`
- Снижает стартовый контекст, но требует явных маршрутизационных правил в CLAUDE.md

**Что это значит для swissknifeman:**
- AI Skills Index в CLAUDE.md — **критически важен**, не опционален
- `skiller connect` должен записывать маршрутизационные правила в CLAUDE.md проекта
- Субагенты из `.claude/agents/*.md` получают **собственный** CLAUDE.md-стек

---

## 2. Универсальная система наследования агентов

### 2.1 Проблема: текущий подход "один стек под проект"

Текущая схема предполагает ручную настройку `.claude/agents/` под каждый проект.
При переходе Laravel → Nuxt меняются скиллы, но схема агентов (reviewer, implementer, tester) — идентична.

**Цель:** Агент = универсальный шаблон + набор скиллов из профиля. Профиль меняется, агент — нет.

---

### 2.2 Модель наследования: три уровня

```
┌─────────────────────────────────────────────────────────────────┐
│  УРОВЕНЬ 1: ~/.claude/CLAUDE.md  (глобальный пользователь)      │
│  Содержит: identity, anti-drift, universal rules                │
│  Источник: harness global-config                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ наследует + расширяет
┌──────────────────────────▼──────────────────────────────────────┐
│  УРОВЕНЬ 2: /project/CLAUDE.md  (проектный)                     │
│  Содержит: AI Skills Index, stack profile, workflow rules       │
│  Источник: skiller connect --profile=laravel                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ наследует + специализирует
┌──────────────────────────▼──────────────────────────────────────┐
│  УРОВЕНЬ 3: .claude/agents/*.md  (субагенты)                    │
│  Содержит: role + skills ref + tools scope                      │
│  Источник: skiller generate-agents --profile=laravel            │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2.3 Профиль проекта: `.swissknife.json`

Единый файл конфигурации проекта — **источник истины** для генерации всех артефактов.

```json
{
  "profile": "laravel",
  "extends": "php-backend",
  "stack": {
    "framework": "laravel",
    "version": "11",
    "php": "8.3",
    "db": "postgresql",
    "queue": "redis"
  },
  "skills": {
    "required": ["laravel", "php", "postgresql", "api-rest"],
    "optional": ["filament", "livewire", "sanctum"],
    "review": ["security", "performance", "anti-drift"]
  },
  "agents": {
    "preset": "fullstack-review",
    "custom": []
  },
  "workflow": {
    "spec_required": true,
    "review_after_each_unit": true,
    "parallel_max": 5
  }
}
```

**Для Nuxt — только меняется профиль:**

```json
{
  "profile": "nuxt",
  "extends": "js-frontend",
  "stack": {
    "framework": "nuxt",
    "version": "3",
    "node": "22",
    "state": "pinia",
    "ui": "nuxt-ui"
  },
  "skills": {
    "required": ["nuxt", "vue3", "typescript", "pinia"],
    "optional": ["nuxt-ui", "tailwind"],
    "review": ["security", "performance", "anti-drift"]
  },
  "agents": {
    "preset": "fullstack-review"
  }
}
```

> **Агенты `fullstack-review` — идентичны для обоих проектов.** Меняются только скиллы.

---

### 2.4 Универсальные шаблоны агентов

Хранятся в `packages/skiller/profiles/agents/` как Mustache/Handlebars-шаблоны.

#### Шаблон: `orchestrator.md.tpl`

```markdown
---
name: orchestrator
description: >
  Главный оркестратор. Декомпозирует задачу, делегирует субагентам,
  собирает результаты. Используй при получении любой задачи разработки.
tools: [Read, TodoWrite, Task]
---

# Orchestrator — {{profile}}

## Stack
{{#stack}}
- {{key}}: {{value}}
{{/stack}}

## AI Skills Index
{{#skills.required}}
- Задача связана с {{name}} → загрузи скилл `{{skill_path}}`
{{/skills.required}}

## Workflow
1. Прочитай `.swissknife.json` — убедись в актуальности стека
2. Если нет `design.md` → вызови субагента `spec-writer` сначала
3. Декомпозируй на атомарные задачи (< 200 строк кода каждая)
4. Назначь субагентам: implementer → reviewer → tester
5. Параллельные задачи — только независимые домены (max {{workflow.parallel_max}})
6. Собери результаты, обнови `tasks.json`

## Anti-drift Rules
- Никогда не реализуй без плана
- Никогда не игнорируй скиллы из Skills Index
- При сомнении — спроси оркестратора (себя), не угадывай
```

#### Шаблон: `reviewer.md.tpl`

```markdown
---
name: reviewer
description: >
  Код-ревьюер. Вызывай ПОСЛЕ каждой единицы реализации.
  Специализация: {{profile}} — знает специфику стека.
tools: [Read, Bash]
---

# Reviewer — {{profile}}

## Чеклист ревью

### Универсальные правила (всегда)
- [ ] Нет hardcoded secrets, credentials
- [ ] Нет debug/console.log/dd() в production коде
- [ ] Обработка ошибок — не просто `catch (e) {}`
- [ ] Тесты покрывают happy path + edge cases

### Специфика стека: {{profile}}
{{#review_rules}}
- [ ] {{rule}}
{{/review_rules}}

## Скиллы для ревью
{{#skills.review}}
- При проверке {{domain}} → загрузи `{{skill_path}}`
{{/skills.review}}

## Формат вывода
```
REVIEW RESULT: [PASS|FAIL|WARN]
Issues: <список с severity>
Required fixes: <что обязательно исправить>
Suggestions: <что желательно>
```
```

#### Шаблон: `implementer.md.tpl`

```markdown
---
name: implementer
description: >
  Реализует конкретную атомарную задачу. Получает task_id,
  читает детали, пишет код строго по спецификации.
tools: [Read, Write, Edit, Bash]
---

# Implementer — {{profile}}

## Правила реализации
- Читай `tasks.json` для контекста задачи
- Проверяй зависимости перед реализацией
- После завершения — обнови статус задачи
- НЕ реализуй смежные задачи (только порученная)

## Skills Index для реализации
{{#skills.required}}
- Работаешь с {{domain}} → загрузи `{{skill_path}}` ДО написания кода
{{/skills.required}}

## File Lock Protocol
- Перед правкой файла: `touch {file}.lock`
- После правки: `rm {file}.lock`
- Если `.lock` существует — жди 30с, retry 3 раза
```

---

### 2.5 Профили стеков (расширение `packages/skiller/profiles/`)

```
packages/skiller/profiles/
├── base/
│   ├── agents/                 # базовые шаблоны агентов (tpl-файлы)
│   │   ├── orchestrator.md.tpl
│   │   ├── implementer.md.tpl
│   │   ├── reviewer.md.tpl
│   │   ├── tester.md.tpl
│   │   └── documenter.md.tpl
│   └── CLAUDE.md.tpl           # базовый шаблон CLAUDE.md
├── php-backend/
│   ├── extends: base
│   ├── review_rules.json       # PHP-специфичные правила ревью
│   └── skills_map.json         # domain → skill path
├── laravel/
│   ├── extends: php-backend
│   ├── review_rules.json       # Laravel-специфичные правила
│   └── skills_map.json
├── nuxt/
│   ├── extends: js-frontend
│   └── skills_map.json
├── vue3/
│   ├── extends: js-frontend
│   └── skills_map.json
└── js-frontend/
    ├── extends: base
    └── skills_map.json
```

**Цепочка наследования:** `laravel` → `php-backend` → `base`

Команда генерации агентов:
```bash
skiller generate-agents --profile=laravel --output=.claude/agents/
# Читает: profiles/laravel → profiles/php-backend → profiles/base
# Рендерит шаблоны с данными из .swissknife.json + skills_map.json
# Создаёт: 01_orchestrator.md, 02_implementer.md, 03_reviewer.md, ...
```

---

### 2.6 AI Skills Index в CLAUDE.md (генерируемый)

`skiller connect` должен **автоматически вписывать** этот блок в CLAUDE.md проекта:

```markdown
## AI Skills Index — {{profile}}
> Маршрутизационная таблица: задача → скилл. Загружай скилл ДО работы с доменом.

| Домен | Триггер | Скилл |
|---|---|---|
| Laravel роутинг, контроллеры, middleware | Работа с `routes/`, `app/Http/` | `skills/laravel/routing` |
| Eloquent, миграции, Query Builder | Работа с `app/Models/`, `database/` | `skills/laravel/eloquent` |
| Laravel API, Resources, Sanctum | Работа с API-эндпоинтами | `skills/laravel/api` |
| Filament admin panel | Работа с `app/Filament/` | `skills/filament/core` |
| PostgreSQL, индексы, транзакции | Сложные запросы, оптимизация | `skills/postgresql/core` |
| Безопасность, XSS, CSRF, SQL-injection | Любая форма ввода, аутентификация | `skills/security/php-web` |

**Правило:** prefer retrieval-led reasoning.
При любой задаче — сначала проверь этот индекс, загрузи скилл, потом пиши код.
```

---

### 2.7 Path-scoped rules (`.claude/rules/`)

Загружаются автоматически при работе с файлами по пути — агент не принимает решение.

```
.claude/rules/
├── laravel-api.md          # paths: ["app/Http/", "routes/api.php"]
├── laravel-models.md       # paths: ["app/Models/", "database/migrations/"]
├── filament.md             # paths: ["app/Filament/"]
└── tests.md                # paths: ["tests/"]
```

**Пример `laravel-api.md`:**
```markdown
---
paths:
  - "app/Http/"
  - "routes/api.php"
---

При работе с API-кодом:
- Использовать API Resources для всех ответов
- Валидация — Form Requests, не inline
- Аутентификация — Sanctum, проверить middleware
- Формат ответа: { data, meta, errors }
- Загрузи скилл: skills/laravel/api
```

Команда генерации:
```bash
skiller generate-rules --profile=laravel --output=.claude/rules/
```

---

### 2.8 Команды для добавления в skiller

```bash
# Инициализация проекта с профилем
skiller init --profile=laravel
# → создаёт .swissknife.json, подключает скиллы, генерирует агентов и rules

# Генерация агентов из профиля
skiller generate-agents --profile=laravel [--output=.claude/agents/]

# Генерация path-scoped rules
skiller generate-rules --profile=laravel [--output=.claude/rules/]

# Генерация/обновление AI Skills Index в CLAUDE.md
skiller inject-index --profile=laravel [--target=CLAUDE.md]

# Список доступных профилей
skiller profiles list

# Создание нового профиля на основе существующего
skiller profiles create myprofile --extends=laravel

# Валидация конфигурации агентов
skiller validate-agents [--path=.claude/agents/]
```

---

## 3. Таблица предложений по доработке swissknifeman

| # | Проблема | Решение | Уровень | Приоритет | Откуда |
|---|---|---|---|---|---|
| 1 | Агенты игнорируют скиллы | AI Skills Index автогенерируется в CLAUDE.md через `skiller inject-index` | skiller | 🔴 Критично | Vercel evals study |
| 2 | Нет универсальных шаблонов агентов | `profiles/base/agents/*.md.tpl` — Mustache-шаблоны, рендерятся под профиль | skiller | 🔴 Критично | VoltAgent collection |
| 3 | Нет профилей наследования | `profiles/` структура: `laravel → php-backend → base` | skiller | 🔴 Критично | — |
| 4 | `.swissknife.json` не используется для генерации | Расширить схему: `agents.preset`, `skills.required/optional/review`, `workflow` | skiller | 🔴 Критично | Task Master config |
| 5 | Нет path-scoped rules | `skiller generate-rules --profile=X` → `.claude/rules/*.md` с frontmatter `paths:` | skiller/harness | 🟠 Важно | Claude Code docs 2026 |
| 6 | Нет workflow для spec-first | Скилл `pre-code-spec` + субагент `spec-writer` + gate в orchestrator | skiller | 🟠 Важно | github/spec-kit |
| 7 | Нет формата task graph | `tasks.json` совместимый с Task Master + интеграция в maind | maind | 🟠 Важно | claude-task-master |
| 8 | Нет команды `skiller init` | Единая команда онбординга проекта (аналог `swissknifeman setup` но project-level) | skiller | 🟠 Важно | — |
| 9 | Нет file lock protocol | Документировать в CLAUDE.md, добавить в базовый шаблон агентов | harness | 🟡 Желательно | rahulvrane collection |
| 10 | Длинные system prompts агентов | Ограничение < 500 символов в шаблонах, скиллы выносятся в Skills Index | skiller | 🟡 Желательно | VoltAgent best practices |
| 11 | Нет нумерации агентов | Конвенция `01_orchestrator.md`, `02_implementer.md` в generate-agents | skiller | 🟡 Желательно | VoltAgent collection |
| 12 | Агенты создаются вручную | `skiller generate-agents --profile=X` автоматизирует | skiller | 🟡 Желательно | — |
| 13 | Нет валидации агентов | `skiller validate-agents` — проверка YAML frontmatter, триггеров, tools scope | skiller | 🟡 Желательно | — |
| 14 | Нет субагента-исследователя | Шаблон `explore-agent.md.tpl` — read-only, собирает контекст перед реализацией | skiller | 🟡 Желательно | Task Master research mode |
| 15 | Нет интеграции spec-kit | Опциональный скилл `sdd` + субагент `spec-writer` | skiller | 🔵 Опционально | github/spec-kit |
| 16 | maind не знает о зависимостях задач | Совместимость `memory/graph` с форматом `tasks.json` из Task Master | maind | 🔵 Опционально | claude-task-master |
| 17 | Нет команды `maind next-task` | Анализ графа зависимостей, предложение следующей готовой задачи | maind | 🔵 Опционально | claude-task-master |
| 18 | Нет complexity scoring | Субагент оценивает сложность задачи (1-10) перед назначением | skiller | 🔵 Опционально | Task Master |

---

## 4. Минимальный рабочий CLAUDE.md для Laravel-проекта

Этот шаблон генерируется командой `skiller init --profile=laravel`:

```markdown
# CLAUDE.md — {{project_name}}

> Стек: Laravel {{laravel_version}} / PHP {{php_version}} / PostgreSQL
> Сгенерировано: skiller init --profile=laravel
> Профиль: packages/skiller/profiles/laravel/

## AI Skills Index
> Загружай скилл ДО работы с доменом. Это не рекомендация — это правило.

| Домен | Скилл |
|---|---|
| Роутинг, контроллеры, middleware | `@laravel/routing` |
| Eloquent, миграции, QB | `@laravel/eloquent` |
| API, Resources, Sanctum | `@laravel/api` |
| Filament (если есть) | `@filament/core` |
| Безопасность, валидация | `@security/php-web` |

## Workflow
1. Получил задачу → проверь `tasks.json` на зависимости
2. Нет `design.md` → вызови субагента `spec-writer` сначала
3. Выбери скилл из Skills Index для домена
4. Реализуй атомарно (< 200 строк на единицу)
5. После каждой единицы → вызови субагента `reviewer`
6. Параллельные задачи только для независимых доменов

## Anti-drift Circuit Breaker
Если ловишь себя на:
- написании кода без плана → СТОП, создай `design.md`
- игнорировании скиллов → СТОП, загрузи по Skills Index
- правке нескольких файлов сразу без плана → СТОП, декомпозируй

## File Lock Protocol
Перед правкой файла: `touch {file}.lock`
После правки: `rm {file}.lock`
Параллельные агенты: проверяй lock перед правкой
```

---

## 5. Предложения по структуре репозитория

Изменения только в рамках существующей архитектуры — ничего не сломает текущий код:

```
packages/skiller/
├── profiles/                   # НОВОЕ — профили стеков
│   ├── base/
│   │   ├── agents/             # базовые .md.tpl шаблоны агентов
│   │   └── CLAUDE.md.tpl
│   ├── php-backend/
│   │   ├── profile.json        # { extends: "base", skills_map: {...} }
│   │   └── review_rules.json
│   ├── laravel/
│   │   ├── profile.json        # { extends: "php-backend", ... }
│   │   ├── skills_map.json
│   │   └── review_rules.json
│   ├── nuxt/
│   │   ├── profile.json        # { extends: "js-frontend", ... }
│   │   └── skills_map.json
│   └── js-frontend/
│       └── profile.json
├── lib/skiller/
│   ├── generate_agents.py      # НОВОЕ — рендеринг агентов из профиля
│   ├── generate_rules.py       # НОВОЕ — генерация path-scoped rules
│   └── inject_index.py         # НОВОЕ — вставка Skills Index в CLAUDE.md
└── skills/
    └── agent-framework/        # НОВОЕ — скилл-документация по шаблонам
        └── SKILL.md
```

```
packages/harness/
└── configs/claude-code/
    └── rules/                  # НОВОЕ — шаблоны path-scoped rules по профилям
        ├── laravel/
        └── nuxt/
```

---

## 6. Референсные ссылки

### Официальная документация
- [Claude Code Sub-agents docs](https://docs.anthropic.com/en/docs/claude-code/sub-agents) — официальные правила Anthropic
- [Claude Code Skills](https://code.claude.com/docs/en/skills) — официальная документация скиллов

### Анализируемые проекты
- [github/spec-kit](https://github.com/github/spec-kit) — Spec-Driven Development toolkit
- [eyaltoledano/claude-task-master](https://github.com/eyaltoledano/claude-task-master) — AI task management
- [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) — 100+ субагентов
- [rahulvrane/awesome-claude-agents](https://github.com/rahulvrane/awesome-claude-agents) — паттерны оркестрации
- [0xfurai/claude-code-subagents](https://github.com/0xfurai/claude-code-subagents) — ещё 100+ субагентов
- [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) — 1000+ скиллов
- [jabelk/claude-speckit-template](https://github.com/jabelk/claude-speckit-template) — Claude Code + Spec Kit шаблон
- [FredAntB/Spec-Driven-Development](https://github.com/FredAntB/Spec-Driven-Development) — SDD skill

### Статьи
- [Claude Code Explained 2026 (alexop.dev)](https://alexop.dev/posts/understanding-claude-code-full-stack/) — полный разбор 2026
- [Claude Code Sub-agents: 90% Performance Gain (codewithseb.com)](https://www.codewithseb.com/blog/claude-code-sub-agents-multi-agent-systems-guide)
- [Spec-driven development with AI (GitHub Blog)](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [VoltAgent 100+ subagents collection (dev.to)](https://dev.to/voltagent/100-claude-code-subagent-collection-1eb0)

