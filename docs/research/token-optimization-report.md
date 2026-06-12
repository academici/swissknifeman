---
title: Token Optimization Report
project: swissknifeman / academici
date: 2026-06-12
version: 1.0.0
---

# Token Optimization — Полный анализ и рекомендации

> **Цель документа:** Максимально снизить расход токенов в процессе разработки Laravel-проекта с AI-агентами (Claude Code, Cursor), не теряя качества финального результата.

---

## 1. Проблема: откуда утекают токены

Каждый агентский сеанс тратит токены на нескольких уровнях. Важно понимать все источники:

| Уровень | Типичный расход | Контроль |
|---|---|---|
| Системный промпт (CLAUDE.md + skills) | 20 000–30 000 до первого сообщения | Высокий |
| Вывод инструментов (тесты, PHPStan) | 2 000–12 000 на итерацию | Высокий |
| Промежуточные ответы агента | 500–3 000 на ход | Средний |
| История контекста (накопление сессии) | растёт экспоненциально | Средний |
| MCP-серверы (schema при каждом вызове) | 200–800 на инструмент | Низкий |

Источник: [Boringbot, 2026](https://boringbot.substack.com/p/how-to-save-millions-in-claude-tokens) — 20k–30k токенов грузится до первого символа.

---

## 2. PHP-инструменты: PAO и waaseyaa/agent-output

### 2.1 Laravel PAO (рекомендован)

**Репозиторий:** https://github.com/laravel/pao  
**Автор:** Nuno Maduro  
**Поддержка:** PHPUnit 12–13, Pest, Paratest, PHPStan, Rector, Laravel Artisan  
**PHP:** ≥ 8.3 | **Laravel:** ≥ 12

**Что делает:** Автоматически определяет, запущены ли инструменты внутри AI-агента (через ENV-переменные `CLAUDE_CODE`, `CURSOR_AGENT`, `DEVIN_*`, `GEMINI_*` и др.) и заменяет многословный вывод на компактный JSON. Человек в терминале видит обычный вывод — агент получает JSON.

**Экономия:**
| Инструмент | Обычный вывод | PAO (агент) | Экономия |
|---|---|---|---|
| PHPUnit (полный прогон) | ~10 000 токенов | ~20 токенов | **99.8%** |
| Pest | ~8 000 токенов | ~20 токенов | **99.8%** |
| PHPStan | ~2 000 токенов | ~40 токенов | **98%** |
| Laravel Artisan | очищается от декора | компактный текст | ~60–80% |

**Установка:**
```bash
composer require laravel/pao --dev
# Никакого конфига — работает автоматически через autoloader
```

**Пример агентского вывода (PHPUnit):**
```json
{
  "result": "passed",
  "tests": 1002,
  "passed": 1002,
  "failed": 0,
  "duration_ms": 321
}
```

**При ошибках:**
```json
{
  "result": "failed",
  "tests": 1002,
  "passed": 1001,
  "failed": 1,
  "failures": [
    {
      "test": "UserTest::it_validates_email",
      "file": "tests/Unit/UserTest.php",
      "line": 45,
      "message": "Expected true, got false"
    }
  ]
}
```

> **Источник:** [Laravel News, 2026-05-13](https://laravel-news.com/pao-agent-optimized-output-for-php-testing-tools) / [Official Laravel Blog](https://laravel.com/blog/introducing-laravel-pao-cleaner-output-for-ai-agents)

---

### 2.2 waaseyaa/agent-output (альтернатива для монорепо / кастомных CI-гейтов)

**Репозиторий:** https://github.com/jonesrussell/waaseyaa-agent-output  
**Отличие от PAO:** Покрывает кастомные `bin/check-*` скрипты, не только стандартные инструменты.

Измерения на реальном пакете:
- Стандартный вывод PHPUnit: **2 209 байт**
- NDJSON-конверт: **117 байт**
- **Экономия: 94.7%**

Установка:
```bash
composer require waaseyaa/agent-output --dev
```

Регистрация PHPUnit extension в `phpunit.xml.dist`:
```xml
<extensions>
  <bootstrap class="Waaseyaa\AgentOutput\Listener\AgentOutputPhpUnitExtension"/>
</extensions>
```

> **Источник:** [jonesrussell.github.io, 2026-05-23](https://jonesrussell.github.io/blog/agent-output-php-ci-tools/)

---

## 3. CLAUDE.md / AGENTS.md — правила экономии

### 3.1 Размер — главный рычаг

CLAUDE.md инжектируется в **каждый запрос** сессии. Каждые 100 строк — это постоянный налог на всю разработку.

| Размер | Токены | Рекомендация |
|---|---|---|
| >500 строк | >5 000 токенов | ❌ Критически много |
| 200–500 строк | 2 000–5 000 токенов | ⚠️ Нужна оптимизация |
| <200 строк | <2 000 токенов | ✅ Официальный ориентир Anthropic |
| <100 строк | <1 000 токенов | ✅✅ Цель |
| 60 строк | ~600 токенов | ✅✅✅ Лучшие команды |

> **Исследование AGENTS.md (2026):** Файлы контекста при превышении ~500 строк снижают success rate и увеличивают стоимость на 20%+. Источник: [Reddit r/ClaudeAI](https://www.reddit.com/r/ClaudeAI/comments/1r7mvja/)

### 3.2 Принципы наполнения CLAUDE.md

**Оставлять:**
- Нестандартные команды сборки/тестирования
- Архитектурные решения, противоречащие дефолту фреймворка
- Проектные ограничения (что нельзя трогать)
- Путь к скиллам и правилам

**Удалять:**
- Всё, что Claude уже знает из обучения (Next.js, TypeScript, стандартные паттерны Laravel)
- Списки команды, контакты, расписания встреч
- Aspirational guidelines ("пиши чистый код", "будь внимательен")
- FAQ, на которые нельзя действовать

**Тест:** Удивит ли это правило опытного разработчика, новому в репо? Если нет — удалить.

### 3.3 HTML-комментарии — бесплатные заметки

```markdown
<!-- Это примечание для команды, агент его не видит и токены не тратит -->
## Реальное правило для агента
```

HTML-комментарии (`<!-- ... -->`) вырезаются перед инжекцией в контекст. Используй для пояснений, которые нужны людям, но не агенту.

> **Источник:** [Boringbot, 2026](https://boringbot.substack.com/p/how-to-save-millions-in-claude-tokens)

---

## 4. Path-scoped rules — скиллы грузятся только по необходимости

Вместо одного большого CLAUDE.md — модульные правила с `paths:` frontmatter. Claude загружает правило только тогда, когда открывает файл из указанного пути.

```markdown
---
paths:
  - "app/Filament/**"
  - "app/Http/**"
---
# Filament rules
# ...эти правила грузятся ТОЛЬКО при работе с Filament-файлами
```

Правила **без** frontmatter — грузятся как второй CLAUDE.md каждый раз.  
Правила **с** `paths:` — нулевая стоимость до триггера.

**Экономия:** До 41% overhead reduction по данным сообщества.

---

## 5. .claudeignore — блокировка шума

```
# .claudeignore — минимальный стартовый набор
node_modules/
dist/
build/
.next/
vendor/
storage/logs/
*.lock
package-lock.json
yarn.lock
coverage/
*.generated.*
*.min.js
*.min.css
_ide_helper*.php
.phpunit.cache/
```

Дополнительно — жёсткий запрет через `permissions.deny` в `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Read(node_modules/**)",
      "Read(vendor/**)",
      "Read(storage/logs/**)",
      "Read(*.lock)"
    ]
  }
}
```

`.claudeignore` — сигнальный уровень (агент не включает проактивно).  
`permissions.deny` — аппаратный блок (агент не может прочитать даже при желании).

---

## 6. Управление контекстом сессии

### 6.1 /compact и /clear

| Команда | Когда использовать | Эффект |
|---|---|---|
| `/compact` | После завершения фичи | Суммирует историю, сохраняет ключевые решения |
| `/clear` | При смене темы/задачи | Полный сброс, нет переноса старого контекста |

Накопление контекста растёт **геометрически** — каждый последующий ход дороже предыдущего.

### 6.2 Plan → Clear → Execute (раздельные сессии)

```
Сессия 1 (ПЛАН):
  → Обсудить задачу, изучить код
  → Сохранить план в .claude/plans/feature-name.md
  → Закрыть сессию

Сессия 2 (ВЫПОЛНЕНИЕ):
  → Загрузить ТОЛЬКО план-документ
  → Выполнить
```

Агент стартует с минимальным контекстом и фокусом только на плане. Промежуточные попытки из первой сессии не занимают токены.

> **Источник:** [claudefa.st best practices, 2026](https://claudefa.st/blog/guide/development/agentic-engineering-best-practices)

---

## 7. Команды (.claude/commands/) — вместо повторных промптов

Любое действие, которое ты пишешь дважды — должно стать командой.

```
.claude/
└── commands/
    ├── commit.md         # /commit — коммит по правилам проекта
    ├── review.md         # /review — code review
    ├── plan.md           # /plan — структурированный план задачи
    ├── prime.md          # /prime — загрузка контекста сессии
    └── execute.md        # /execute — выполнение плана из файла
```

Стартовые 5 команд, которые стоит создать немедленно:
1. `/commit` — форматированный коммит по Conventional Commits
2. `/review` — code review по стандартам проекта
3. `/plan` — план без выполнения, результат в файл
4. `/prime` — загрузка стартового контекста сессии
5. `/execute` — выполнение плана из файла предыдущей сессии

---

## 8. Compact Response Mode — скилл для агента

В проекте уже есть `skills/general/compact-responses/SKILL.md`. Он правильный по направлению, но требует усиления.

**Текущее состояние:** Общие правила — "код без объяснений", "один абзац". Нет поведенческих шаблонов для конкретных ситуаций разработки.

**Что добавить в скилл:**

```markdown
## Compact Response Mode (Enhanced)

### Принципы
- Промежуточные шаги: не выводить. Только финал.
- Тесты прошли: `✓ tests passed (N)` — не весь вывод
- Тесты упали: только провалившийся тест + сообщение об ошибке
- Изменения в коде: только изменённые фрагменты, не весь файл
- Не повторять содержимое задачи обратно
- Не писать "Я понял", "Сейчас сделаю", "Готово, вот результат"

### Финальный отчёт задачи
Единственный момент расширенного вывода:
- Что сделано (список)
- Что НЕ сделано и почему (если есть)
- Файлы изменены (список путей)
- Команды для проверки
```

---

## 9. MCP-серверы — аудит ежемесячно

Каждый подключённый MCP-сервер добавляет схему инструментов в системный промпт при каждом запросе. Даже если сервер не используется.

**Правило:** Отключай MCP-серверы, которые не использовались 7 дней.  
**Предпочтение:** CLI-инструменты вместо MCP там, где возможно (экономия ~40%).

---

## 10. Модели — маршрутизация по сложности

| Задача | Модель | Обоснование |
|---|---|---|
| Сложная архитектура, ревью, дебаггинг | Claude Sonnet 4.5 / Opus | Нужна глубина |
| Рутинные правки, форматирование | Haiku / Flash | В 10× дешевле |
| Поиск файлов, навигация по коду | Haiku | Только разведка |

Команды сообщают экономию 70–85% при авторотации по сложности задачи.  

> **Источник:** [Finout, Claude Code Pricing 2026](https://www.finout.io/blog/claude-code-pricing-2026)

---

## 11. Рекомендации для swissknifeman

На основе анализа текущей структуры проекта (`skills/general/`, `skills/php/`):

### Немедленные действия

1. **Установить PAO:**
   ```bash
   composer require laravel/pao --dev
   ```
   Нет конфига — работает сразу. Экономия до 99.8% на тестах.

2. **Добавить `.claudeignore`** в корень проекта с блокировкой `vendor/`, `*.lock`, `coverage/`.

3. **Улучшить `compact-responses` скилл** (см. раздел 8).

4. **Создать `.claude/commands/`** минимум с `prime.md` и `plan.md`.

5. **Аудит CLAUDE.md:** Проверить размер. Если >200 строк — провести trim.

### Архитектурные улучшения

6. **Path-scoped rules для скиллов:** Добавить `paths:` frontmatter в тяжёлые скиллы (`filament`, `laravel-best-practices`), чтобы они не грузились при работе с git-командами или документацией.

7. **Разделить сессии Plan/Execute:** Закрепить в `task-brief-template` скилле как обязательный шаг — план в отдельной сессии, выполнение — в новой.

8. **`.claude/settings.json`** с `permissions.deny` для `vendor/**` и `storage/logs/**`.

---

## 12. Reference — быстрая выжимка с ссылками

| Инструмент / Ресурс | Что делает | Ссылка |
|---|---|---|
| **laravel/pao** | Сжимает PHPUnit/Pest/PHPStan до ~20 токенов в агент-среде | https://github.com/laravel/pao |
| **waaseyaa/agent-output** | То же + кастомные CI-скрипты, NDJSON, -94.7% | https://jonesrussell.github.io/blog/agent-output-php-ci-tools/ |
| **drona23/claude-token-efficient** | Готовый CLAUDE.md шаблон с правилами экономии | https://github.com/drona23/claude-token-efficient |
| **claude-code-router** | Авторотация модели по сложности задачи (-70–85%) | https://github.com/musistudio/claude-code-router |
| **Finout: Claude Code Pricing 2026** | Полный гайд по оптимизации затрат Claude Code | https://www.finout.io/blog/claude-code-pricing-2026 |
| **Boringbot: Save millions in Claude tokens** | Анализ 20+ вирусных репо, практические выводы | https://boringbot.substack.com/p/how-to-save-millions-in-claude-tokens |
| **claudefa.st best practices** | Plan→Clear→Execute, команды, эволюция системы | https://claudefa.st/blog/guide/development/agentic-engineering-best-practices |
| **Официальный Laravel Blog: PAO** | Официальный анонс PAO с примерами JSON | https://laravel.com/blog/introducing-laravel-pao-cleaner-output-for-ai-agents |
| **Laravel News: PAO** | Обзор с примерами вывода | https://laravel-news.com/pao-agent-optimized-output-for-php-testing-tools |
| **Reddit: AGENTS.md research** | Исследование: >500 строк = +20% стоимость | https://www.reddit.com/r/ClaudeAI/comments/1r7mvja/ |

---

## Итог: приоритизированный план внедрения

```
Приоритет 1 (сегодня, 30 мин):
  ✓ composer require laravel/pao --dev
  ✓ Добавить .claudeignore
  ✓ Добавить permissions.deny в .claude/settings.json

Приоритет 2 (эта неделя):
  ✓ Аудит CLAUDE.md — trim до <200 строк
  ✓ Улучшить compact-responses скилл
  ✓ Создать .claude/commands/prime.md и plan.md

Приоритет 3 (следующий спринт):
  ✓ Path-scoped rules для тяжёлых скиллов
  ✓ Добавить paths: frontmatter в filament, laravel-best-practices
  ✓ Закрепить Plan→Clear→Execute в task-brief-template скилле
  ✓ Рассмотреть claude-code-router для авторотации моделей
```
