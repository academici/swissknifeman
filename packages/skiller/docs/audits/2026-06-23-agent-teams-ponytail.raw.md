# Claude Code Agent Teams + Ponytail: Полное руководство по внедрению

> Документ охватывает: (1) экспериментальная Mesh-архитектура Agent Teams, (2) практики из репозитория [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail), (3) интеграция обоих подходов в проектах на Laravel и Nuxt с гибкой системой наследования агентов.

---

## 1. Agent Teams: архитектура и принципы

### 1.1 Что это и как отличается от субагентов

Claude Code Agent Teams — экспериментальная функция (начиная с v2.1.178 + Opus 4.6), позволяющая запускать **несколько независимых сессий Claude**, которые общаются напрямую друг с другом через Mesh-сеть, а не только через главного оркестратора.

**Принципиальное отличие:**

| Характеристика | Субагенты | Agent Teams (Mesh) |
|---|---|---|
| Топология коммуникации | Hub-and-spoke (только через главный агент) | Mesh (любой ↔ любой) |
| Контекст каждого агента | Своё окно, результат возвращается к главному | Своё окно, полностью независимый |
| Координация | Главный агент управляет всем | Shared task list + самостоятельное назначение задач |
| Общение между агентами | Только через главный | Прямые сообщения + broadcast |
| Стоимость токенов | Ниже (результаты суммируются) | Выше (каждый — отдельный инстанс Claude) |
| Лучшие сценарии | Быстрые изолированные задачи | Совместная работа, дебаты, кросс-слойная координация |
| Настройка | Встроена в Claude Code | Требует переменной окружения |

### 1.2 Включение функции

**Вариант 1 — глобальный (постоянный):**

```json
// ~/.claude/settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "teammateMode": "auto"
}
```

**Вариант 2 — переменная окружения (на сессию):**

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
claude --teammate-mode auto
```

**Режимы отображения** (`teammateMode`):

| Режим | Поведение | Требования |
|---|---|---|
| `in-process` | Все агенты в одном терминале (default) | Любой терминал |
| `auto` | Split panes если есть tmux/iTerm2, иначе in-process | tmux или iTerm2 |
| `tmux` | Принудительный split через tmux | tmux |
| `iterm2` | Принудительный split через iTerm2 | iTerm2 + `it2` CLI |

### 1.3 Компоненты архитектуры

```
~/.claude/teams/{session-id}/config.json   ← runtime-состояние, не редактировать вручную
~/.claude/tasks/{session-id}/              ← общий task list (персистентный между сессиями)
```

Четыре компонента команды:

1. **Team Lead** — главная сессия, создаёт команду, распределяет задачи, синтезирует результаты
2. **Teammates** — независимые инстансы Claude Code, каждый со своим CLAUDE.md и скиллами
3. **Shared Task List** — общая очередь задач с состояниями `pending → in_progress → completed`, поддерживает dependencies
4. **Mailbox** — система сообщений: direct messages (один агент) и broadcast (все агенты)

### 1.4 Управление командой: шпаргалка

```bash
# Клавиатурные сокращения в in-process режиме:
# Shift+Up/Down  — выбрать агента
# Enter          — открыть сессию агента и писать ему напрямую
# Escape         — прервать текущий ход агента
# Ctrl+T         — переключить отображение task list
# x              — остановить выбранного агента
```

**Требование план-аппрувала** (для рискованных задач):
```text
Spawn architect teammate to refactor auth module.
Require plan approval before any changes.
```

**Quality gates через хуки:**

```json
// ~/.claude/settings.json
{
  "hooks": {
    "TeammateIdle": [{
      "hooks": [{
        "type": "command",
        "command": "node .claude/hooks/quality-gate.js",
        "timeout": 30
      }]
    }],
    "TaskCompleted": [{
      "hooks": [{
        "type": "command",
        "command": "node .claude/hooks/task-validator.js",
        "timeout": 30
      }]
    }]
  }
}
```

> **Выход с кодом 2** из хука → задача не завершается, агент получает обратную связь и продолжает работу.

### 1.5 Когда использовать Agent Teams vs субагенты

**Используй Agent Teams когда:**
- Изменения затрагивают несвязанные слои (API + фронт + тесты) одновременно
- Нужно проверить конкурирующие гипотезы (debugging)
- Требуется архитектурный дебат между агентами
- Независимые модули разрабатываются параллельно

**Оставайся на субагентах когда:**
- Задача последовательная или с tight dependencies
- Нужна только параллелизация без коммуникации → `/batch` быстрее
- Бюджет токенов ограничен (Agent Teams = ~3-4x дороже)

---

## 2. Ponytail: что внедрить в проект

[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) — плагин-скилл для AI-агентов, реализующий принцип "lazy senior dev": писать только необходимый минимум кода, используя YAGNI-лесенку.

### 2.1 Результаты бенчмарков (реальные сессии Claude Code)

Измерено на реальных сессиях Claude Code, редактирующих `tiangolo/full-stack-fastapi-template` (FastAPI + React), 12 задач, Haiku 4.5, n=4:

| Метрика | Без ponytail | С ponytail | Экономия |
|---|---|---|---|
| Строки кода (LOC) | baseline | -54% среднее (до -94% на перегруженных задачах) | ↓54% |
| Токены | baseline | -22% | ↓22% |
| Стоимость | baseline | -20% | ↓20% |
| Время | baseline | -27% | ↓27% |
| Безопасность | 100% | **100%** | = |

ponytail — единственный инструмент из сравниваемых, который снижает ВСЕ метрики при 100% сохранении безопасности.

### 2.2 Семиступенчатая лесенка (ядро подхода)

```
1. Нужно ли это вообще?          → нет: пропустить (YAGNI)
2. Уже есть в codebase?          → переиспользовать
3. Stdlib это умеет?              → использовать
4. Нативная платформенная фича?   → использовать
5. Установленная зависимость?     → использовать
6. Это одна строка?               → одна строка
7. Только тогда: минимум, который работает
```

Лесенка применяется **после** понимания задачи, а не вместо него.

### 2.3 Файлы и структура репозитория

```
ponytail/
├── AGENTS.md                        ← главное правило (всегда загружается агентами)
├── skills/
│   ├── ponytail/SKILL.md            ← основной скилл (full mode)
│   ├── ponytail-review/SKILL.md     ← ревью на over-engineering
│   ├── ponytail-audit/SKILL.md      ← аудит всего репозитория
│   └── ponytail-debt/SKILL.md       ← учёт ponytail:-комментариев
├── hooks/
│   ├── claude-codex-hooks.json      ← конфиг хуков для Claude Code
│   ├── ponytail-activate.js         ← активация на SessionStart
│   ├── ponytail-mode-tracker.js     ← трекинг mode на UserPromptSubmit
│   └── ponytail-instructions.js     ← инъекция инструкций в промпт
├── .agents/rules/                   ← правила для CodeWhale/Antigravity
├── .claude-plugin/                  ← плагин для Claude Code
└── commands/                        ← slash-команды
```

### 2.4 Установка в Claude Code

```bash
# Через плагин-маркетплейс
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Или вручную скопировать `AGENTS.md` в корень проекта — агент подхватит правила автоматически без плагина.

### 2.5 Slash-команды

| Команда | Что делает |
|---|---|
| `/ponytail [lite\|full\|ultra\|off]` | Установить интенсивность или проверить текущий уровень |
| `/ponytail-review` | Ревью текущего diff на over-engineering, возвращает delete-list |
| `/ponytail-audit` | Аудит всего репозитория, не только diff |
| `/ponytail-debt` | Сбор `ponytail:`-комментариев в реестр технического долга |
| `/ponytail-gain` | Показать метрики экономии из бенчмарков |

**Уровни режимов:**
- `lite` — мягкие подсказки, не прерывает стиль агента
- `full` (default) — полная лесенка на каждой задаче
- `ultra` — максимальная агрессивность к удалению кода
- `off` — полное отключение

### 2.6 Ключевые правила из AGENTS.md для встраивания в проект

```markdown
# Правила из ponytail (AGENTS.md)

## Принцип минимального кода
Перед написанием кода остановись на первой ступени лесенки, которая держит:
1. Это вообще нужно? (YAGNI)
2. Уже есть в кодовой базе? Переиспользуй.
3. Stdlib умеет это? Используй.
4. Нативная фича платформы? Используй.
5. Установленная зависимость решает? Используй.
6. Это одна строка? Одна строка.
7. Только тогда — минимум, который работает.

## Исправление багов
Ищи корневую причину, а не симптом. Grep каждый caller затронутой функции
и исправь общую функцию один раз.

## Запрещено без явного запроса
- Абстракции без запроса
- Новые зависимости, если можно обойтись
- Шаблонный код без цели
- Удаление > добавление
- Скучное > умное

## Обязательно всегда
- Валидация входных данных на trust boundaries
- Обработка ошибок, предотвращающая потерю данных
- Безопасность и доступность
- Один runnable тест для нетривиальной логики
```

### 2.7 Скилл ponytail-review: формат вывода

Скилл ревью возвращает строго форматированные результаты:

```
L12-38: stdlib: 27-строчный валидатор email. "@" in email, 1 строка.
L4: native: moment.js импортирован для одного вызова format. Intl.DateTimeFormat, 0 зависимостей.
L88: yagni: AbstractRepository с одной реализацией. Встрой до появления второй.
L52-71: delete: retry wrapper вокруг идемпотентного локального вызова. Ничего не заменяет.

net: -47 строк возможно.
```

Теги: `delete:` / `stdlib:` / `native:` / `yagni:` / `shrink:`

---

## 3. Интеграция: Agent Teams + Ponytail + Гибкое наследование

### 3.1 Универсальная структура директорий проекта

Эта структура работает для **любого фреймворка** (Laravel, Nuxt, Django и т.д.) — меняются только скиллы, схема агентов остаётся единой.

```
project-root/
├── CLAUDE.md                          ← главный файл (≤200 строк), AI Skills Index
├── AGENTS.md                          ← наследуется из ponytail или проекта
├── .claude/
│   ├── settings.json                  ← env, hooks, teammateMode
│   ├── agents/                        ← определения агентов (субагенты + teammates)
│   │   ├── _base.md                   ← БАЗОВЫЙ шаблон (наследуется всеми)
│   │   ├── _reviewer.md               ← универсальный ревьюер (наследует _base)
│   │   ├── laravel-implementer.md     ← Laravel-специфичный агент
│   │   ├── nuxt-implementer.md        ← Nuxt-специфичный агент
│   │   └── tester.md                  ← универсальный тестировщик
│   ├── rules/                         ← path-scoped правила (автозагрузка)
│   │   ├── api.md                     ← paths: [app/Http/Controllers/**]
│   │   ├── models.md                  ← paths: [app/Models/**]
│   │   └── frontend.md                ← paths: [resources/js/**, pages/**)
│   ├── skills/                        ← проектные скиллы
│   │   ├── laravel-conventions.md
│   │   ├── nuxt-conventions.md
│   │   └── api-standards.md
│   └── hooks/
│       ├── quality-gate.js            ← TaskCompleted: quality gate
│       └── task-validator.js          ← TeammateIdle: принуждение к скиллам
└── ponytail.config.json               ← PONYTAIL_DEFAULT_MODE и настройки
```

### 3.2 Система наследования: _base → специализация → проект

Ключевая идея: **каждый агент наследует базовый шаблон через `@include`** в `CLAUDE.md`, добавляя только специфичные скиллы и ограничения. Схема одинакова для всех проектов.

**`.claude/agents/_base.md`** (универсальный базовый шаблон):

```markdown
---
# Базовый агент: наследуется всеми специализированными агентами
name: base-agent
version: "1.0"
---

## Обязательные правила (применяются всегда)

### Скилл минимального кода (ponytail)
Перед написанием кода применяй лесенку:
1. YAGNI — нужно ли вообще?
2. Уже есть в codebase? → переиспользовать
3. Stdlib/платформа умеет? → использовать
4. Установленная зависимость? → использовать
5. Одна строка? → одна строка
6. Минимум, который работает

### Anti-drift блок
ОБЯЗАТЕЛЬНО: при получении задачи проверь список скиллов ниже.
Если задача пересекается с описанием скилла — загрузи скилл через `load_skill`.
Не пропускай этот шаг.

### Коммуникация
- Сообщай о прогрессе через task list, а не через ленд-агента
- При блокировке → прямое сообщение зависимому агенту
- Перед завершением задачи → проверка quality gate

### Запрещено
- Писать код без понимания задачи
- Создавать абстракции без явного запроса
- Игнорировать существующие паттерны в codebase

## AI Skills Index
| Тип задачи | Скилл | Файл |
|---|---|---|
| Любое ревью | ponytail-review | skills/ponytail-review/SKILL.md |
| Аудит репозитория | ponytail-audit | skills/ponytail-audit/SKILL.md |
| Оптимизация | ponytail | AGENTS.md |
```

**`.claude/agents/_reviewer.md`** (универсальный ревьюер, наследует `_base`):

```markdown
---
name: reviewer
extends: _base                     # ← наследование
role: "Code reviewer"
triggers:
  - "review"
  - "code quality"
  - "over-engineering"
---

@include .claude/agents/_base.md   # ← явный include базового шаблона

## Специализация ревьюера

### Порядок ревью
1. Загрузи `ponytail-review` скилл
2. Проверь diff по лесенке ponytail
3. Проверь соответствие конвенциям проекта (скилл ниже)
4. Верни delete-list + список нарушений

### AI Skills Index (дополнение к base)
| Тип задачи | Скилл |
|---|---|
| Framework-конвенции | [PROJECT_SKILL] |  ← placeholder, переопределяется
| Security | .claude/skills/security.md |
| API стандарты | .claude/skills/api-standards.md |
```

**`.claude/agents/laravel-implementer.md`** (Laravel-специфичный, наследует `_base`):

```markdown
---
name: laravel-implementer
extends: _base
project_type: laravel
skills:
  - .claude/skills/laravel-conventions.md
  - .claude/skills/api-standards.md
---

@include .claude/agents/_base.md

## Laravel-специфичные правила

### Обязательные скиллы для Laravel задач
- При работе с Controller → загружай `laravel-conventions` скилл
- При работе с Eloquent → проверяй N+1, используй eager loading
- API resources → всегда через `JsonResource`, не `toArray()`
- Валидация → `FormRequest`, не в контроллере

### AI Skills Index (Laravel)
| Задача | Скилл | Файл |
|---|---|---|
| Controllers/Routes | laravel-conventions | .claude/skills/laravel-conventions.md |
| Eloquent Models | laravel-conventions | .claude/skills/laravel-conventions.md |
| API стандарты | api-standards | .claude/skills/api-standards.md |
| Тесты | .claude/skills/testing-laravel.md | |
| Ревью | ponytail-review | AGENTS.md |
```

**`.claude/agents/nuxt-implementer.md`** (Nuxt-специфичный, аналогичная структура):

```markdown
---
name: nuxt-implementer
extends: _base
project_type: nuxt
skills:
  - .claude/skills/nuxt-conventions.md
  - .claude/skills/api-standards.md
---

@include .claude/agents/_base.md

## Nuxt-специфичные правила

### Обязательные скиллы для Nuxt задач
- Composables вместо Options API
- `useFetch`/`useAsyncData` — не голый `fetch`
- Server routes в `server/api/` для BFF-паттернов
- Auto-imports — не явные imports из `#imports`

### AI Skills Index (Nuxt)
| Задача | Скилл | Файл |
|---|---|---|
| Composables/Components | nuxt-conventions | .claude/skills/nuxt-conventions.md |
| Server API routes | api-standards | .claude/skills/api-standards.md |
| State management | .claude/skills/nuxt-state.md | |
| Ревью | ponytail-review | AGENTS.md |
```

### 3.3 CLAUDE.md с Agent Teams поддержкой

```markdown
# Project: [PROJECT_NAME]

## Обязательно к прочтению первым делом
- Тип проекта: [laravel|nuxt|...]
- Агент-определения: .claude/agents/
- Базовый шаблон всех агентов: .claude/agents/_base.md

## AI Skills Index (маршрутизатор)
| Запрос | Агент | Скилл |
|---|---|---|
| Реализация фичи | [project]-implementer | .claude/agents/[project]-implementer.md |
| Code review | reviewer | .claude/agents/_reviewer.md |
| Тесты | tester | .claude/agents/tester.md |
| Ревью diff | (текущий агент) | skills/ponytail-review/SKILL.md |
| Аудит repo | (текущий агент) | skills/ponytail-audit/SKILL.md |

**ПРАВИЛО**: При получении задачи → сначала найди строку в таблице → загрузи указанный скилл.

## Agent Teams: когда активировать
Запрашивай команду (`spawn N teammates`) при:
- Задача затрагивает 3+ независимых модуля
- Нужны конкурирующие гипотезы для дебага
- Кросс-слойная работа (API + фронт + тесты параллельно)

Spawn-шаблоны:
```

**Full-stack фича:**
```text
Spawn 3 teammates:
1. laravel-implementer: реализует API endpoint
2. nuxt-implementer: реализует фронтенд для этого endpoint  
3. reviewer: ревьюит оба diff по ponytail-review скиллу
Требуй plan approval перед любыми изменениями.
```

**Параллельный дебаг:**
```text
Spawn 2 teammates для исследования бага [описание]:
1. hypothesis-a: исследует [причина А], только read-only
2. hypothesis-b: исследует [причина Б], только read-only
Обменяйтесь находками, затем сообщите lead-агенту единый вывод.
```

```markdown
## Модуль boundaries (предотвращение конфликтов)
- `app/Http/` — только laravel-implementer
- `resources/js/` — только nuxt-implementer  
- `tests/` — только tester
- Shared модели: координация через task list, не параллельная запись

## Запрещено
- Писать код без загрузки соответствующего скилла
- Параллельная запись в один файл несколькими агентами
- Broadcast всей команде — только direct messages
```

### 3.4 Settings.json с полной конфигурацией

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    "PONYTAIL_DEFAULT_MODE": "full"
  },
  "teammateMode": "auto",
  "cleanupPeriodDays": 7,
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "command -v node >/dev/null 2>&1 && node \"${CLAUDE_PLUGIN_ROOT}/hooks/ponytail-activate.js\" || exit 0",
        "timeout": 5,
        "statusMessage": "Loading ponytail..."
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "command -v node >/dev/null 2>&1 && node \"${CLAUDE_PLUGIN_ROOT}/hooks/ponytail-mode-tracker.js\" || exit 0",
        "timeout": 5
      }]
    }],
    "TaskCompleted": [{
      "hooks": [{
        "type": "command",
        "command": "node .claude/hooks/quality-gate.js",
        "timeout": 30
      }]
    }],
    "TeammateIdle": [{
      "hooks": [{
        "type": "command",
        "command": "node .claude/hooks/skill-enforcement.js",
        "timeout": 15,
        "statusMessage": "Checking skill compliance..."
      }]
    }]
  }
}
```

### 3.5 Хук принуждения к скиллам (skill-enforcement.js)

```javascript
// .claude/hooks/skill-enforcement.js
// TeammateIdle hook: проверяет, что агент загрузил нужный скилл
// Exit code 2 → агент получает feedback и продолжает работу

const payload = JSON.parse(process.env.HOOK_PAYLOAD || '{}');
const transcript = payload.transcript || '';

// Признаки того, что агент НЕ загружал скилл
const skillLoadIndicators = [
  'load_skill', 'ponytail-review', 'laravel-conventions',
  'nuxt-conventions', 'api-standards'
];

const hasLoadedSkill = skillLoadIndicators.some(s => transcript.includes(s));
const isCodeTask = /implement|create|write|fix|refactor|add/.test(
  (payload.task_description || '').toLowerCase()
);

if (isCodeTask && !hasLoadedSkill) {
  console.error(
    'SKILL ENFORCEMENT: Задача кодирования обнаружена, но скилл не был загружен.\n' +
    'Обязательно: проверь AI Skills Index в CLAUDE.md и загрузи соответствующий скилл.\n' +
    'Затем повтори задачу с применением правил скилла.'
  );
  process.exit(2); // блокирует завершение задачи, агент получает feedback
}

process.exit(0);
```

### 3.6 Таблица решений: что использовать в каждом сценарии

| Сценарий | Инструмент | Конфиг |
|---|---|---|
| Разработка одной фичи в Laravel | Субагент `laravel-implementer` | `.claude/agents/laravel-implementer.md` |
| Разработка одной фичи в Nuxt | Субагент `nuxt-implementer` | `.claude/agents/nuxt-implementer.md` |
| Full-stack фича (API + фронт) | Agent Teams: 2 implementers + reviewer | Spawn-шаблон в CLAUDE.md |
| Code review любого проекта | Субагент `reviewer` → скилл ponytail-review | `.claude/agents/_reviewer.md` |
| Аудит репозитория | Один агент → скилл ponytail-audit | `skills/ponytail-audit/SKILL.md` |
| Дебаг со сложной причиной | Agent Teams: 2+ hypothesis-агента | Spawn-шаблон для дебага |
| Рефакторинг нескольких модулей | Agent Teams с module-boundaries | CLAUDE.md module boundaries секция |
| Ежедневные небольшие задачи | Одиночная сессия + ponytail full mode | `PONYTAIL_DEFAULT_MODE=full` |
| Смена проекта (Laravel → Nuxt) | Одна схема агентов, смена скиллов | Только `*-implementer.md` файл |

### 3.7 Чеклист внедрения

#### Фаза 1: Базовая установка (день 1)
- [ ] Установить ponytail: `/plugin install ponytail@ponytail`
- [ ] Добавить `AGENTS.md` из ponytail в корень проекта
- [ ] Создать `~/.claude/settings.json` с `PONYTAIL_DEFAULT_MODE: "full"`
- [ ] Проверить: `/ponytail` показывает текущий режим

#### Фаза 2: Скилл-система (день 2-3)
- [ ] Создать `.claude/agents/_base.md` (базовый шаблон)
- [ ] Создать `.claude/agents/_reviewer.md`
- [ ] Создать `.claude/agents/[project]-implementer.md`
- [ ] Написать `.claude/skills/[project]-conventions.md`
- [ ] Обновить `CLAUDE.md` с AI Skills Index и таблицей маршрутизации

#### Фаза 3: Agent Teams (день 4-5)
- [ ] Включить `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"` в settings.json
- [ ] Добавить `TeammateIdle` и `TaskCompleted` хуки
- [ ] Создать `.claude/hooks/skill-enforcement.js`
- [ ] Добавить spawn-шаблоны в CLAUDE.md
- [ ] Тест: `/ponytail-review` на реальном diff

#### Фаза 4: Тонкая настройка (неделя 2)
- [ ] Настроить `module boundaries` в CLAUDE.md
- [ ] Проверить через ponytail-audit накопленный технический долг
- [ ] Настроить `TeamateModeModel` для дорогих задач (Sonnet для teammates)
- [ ] Добавить `.claude/agents/tester.md`

---

## 4. Известные ограничения и обходные пути

| Ограничение | Версия | Обходной путь |
|---|---|---|
| Agent Teams экспериментальны | v2.1.178+ | Тестировать на не-продакшн задачах |
| Resume session не сохраняет team config | Любая | task list персистентен, задачи не теряются |
| Teammate модель не наследует `/model` лида | По умолчанию | Явно указать в spawn prompt или `/config` → Default teammate model |
| Broadcast дорог при большой команде | Всегда | Только direct messages, broadcast — исключение |
| `tmux` ограничен на некоторых ОС | Всегда | `iTerm2 + it2 CLI` или `in-process` режим |
| ponytail хуки требуют `node` в PATH | Всегда | Для nvm/nix — добавить в non-interactive shell PATH |

---

## 5. Ссылки

- [Claude Code Agent Teams — официальная документация](https://code.claude.com/docs/en/agent-teams)
- [Agent Teams Guide — claudefa.st](https://claudefa.st/blog/guide/agents/agent-teams)
- [DietrichGebert/ponytail — репозиторий](https://github.com/DietrichGebert/ponytail)
- [ponytail AGENTS.md](https://github.com/DietrichGebert/ponytail/blob/main/AGENTS.md)
- [ponytail-review SKILL.md](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail-review/SKILL.md)
- [ponytail hooks](https://github.com/DietrichGebert/ponytail/blob/main/hooks/claude-codex-hooks.json)
- [Agentic benchmark — результаты](https://github.com/DietrichGebert/ponytail/blob/main/benchmarks/results/2026-06-18-agentic.md)
- [swissknifeman — скиллы Дмитрия](https://github.com/academici/swissknifeman)
