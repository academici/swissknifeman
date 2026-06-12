---
name: context-economy
bucket: general
version: 1.0.0
description: "Экономия контекста Claude Code в проекте: CLAUDE.md ≤200 строк, path-scoped правила .claude/rules/, /compact vs /clear, паттерн Plan→Clear→Execute, аудит MCP, маршрутизация моделей. Только официально поддерживаемые механизмы — без мифов вроде .claudeignore."
risk: draft
persona: oss-dev
tags: [tokens, context, claude-code, workflow]
requires: []
produces_for: []
outputs: [".claude/rules/*.md", ".claude/commands/*.md", "CLAUDE.md (trim)"]
snippets:
  - rules-example.md
  - command-prime.md
  - command-plan.md
  - command-execute.md
  - claude-md-checklist.md
adapters: [claude, cursor, fable]
sha256: ""
---

# Context Economy — дисциплина расхода токенов

## Контекст

CLAUDE.md и правила инжектируются в каждую сессию — каждые 100 лишних строк это постоянный налог на всю разработку. История сессии растёт с каждым ходом, MCP-схемы грузятся даже без использования. Этот скилл — проверенный по официальной документации набор приёмов (https://code.claude.com/docs/en/memory). Чего здесь нет, потому что оно не работает: `.claudeignore` не существует в Claude Code; `@import` в CLAUDE.md — организация, не экономия (импортированные файлы грузятся при старте целиком).

## Алгоритм

### 1. CLAUDE.md — ≤200 строк (официальный ориентир Anthropic)

- Оставлять: нестандартные команды сборки/тестов, архитектурные решения против дефолта фреймворка, запреты, пути к скиллам/правилам.
- Удалять: то, что модель знает из обучения (стандартный Laravel/TS), aspirational-правила («пиши чистый код»), контакты и расписания.
- Тест на строку: «удивит ли это правило опытного разработчика, нового в репо?» Нет → удалить.
- Заметки для людей — в HTML-комментарии `<!-- ... -->`: они вырезаются до инжекции в контекст (внутри code-блоков — сохраняются).
- Чеклист аудита: snippets/claude-md-checklist.md.

### 2. Path-scoped правила — `.claude/rules/*.md`

Тематические правила с `paths:` frontmatter грузятся только когда Claude читает совпадающие файлы; без `paths:` — каждую сессию наравне с CLAUDE.md:

```markdown
---
paths:
  - "app/Filament/**"
---
# Filament rules — грузятся только при работе с Filament-файлами
```

Шаблон: snippets/rules-example.md. Не путать со скиллами: SKILL.md и так лениво загружается (в контексте сессии живут только name+description), `paths:` для скиллов не нужен и не существует.

### 3. Сессии: /compact, /clear, Plan→Clear→Execute

- `/compact` — после завершения фичи (суммирует историю, сохраняет решения).
- `/clear` — при смене темы (полный сброс).
- Большие задачи — раздельные сессии: план в файл (`/plan` → `.claude/plans/<task>.md`) → `/clear` → выполнение с загрузкой только плана (`/execute`). Промежуточные попытки планирования не тянутся в контекст выполнения. Шаблоны команд: snippets/command-{prime,plan,execute}.md → скопировать в `.claude/commands/` проекта.

### 4. Вывод инструментов

В PHP-проектах — `laravel/pao` (см. скилл `pao`, bucket php): тесты/статанализ сжимаются до ~20 токенов JSON.

### 5. Аудит MCP и моделей

- MCP-сервер не использовался 7 дней → отключить (его схема грузится в каждый запрос). CLI вместо MCP, где возможно.
- Модель — нативно через `/model`: рутина/разведка — Haiku, архитектура/дебаг — старшая модель. Сторонние прокси-роутеры (claude-code-router) не использовать: лишний слой риска без нативных гарантий.

### 6. Жёсткая блокировка шума — permissions.deny

`permissions.deny: Read(...)` в `.claude/settings.json` — аппаратный блок чтения (`storage/logs/**`, `node_modules/**`, `*.lock`). Готовые пресеты: `configs/claude-code/` + `scripts/apply-permissions.sh`. В Laravel-проектах с Boost НЕ блокировать `vendor/**` — гайдлайны живут в `vendor/laravel/boost/.ai/`.

## Чеклист качества

- [ ] CLAUDE.md ≤200 строк, каждая строка проходит тест «удивит ли опытного»
- [ ] Тематические/локальные правила вынесены в `.claude/rules/` с `paths:`
- [ ] deny-пресет шума применён; `vendor/**` не заблокирован в Boost-проектах
- [ ] Команды prime/plan/execute скопированы в `.claude/commands/`
- [ ] MCP-серверы проверены за последние 30 дней

## Ссылки

- snippets/rules-example.md, snippets/claude-md-checklist.md
- snippets/command-prime.md, snippets/command-plan.md, snippets/command-execute.md
- https://code.claude.com/docs/en/memory — CLAUDE.md, rules, auto memory
- Скилл `pao` (php) — сжатие вывода PHP-инструментов
