---
name: document-writer
description: Use when writing blog posts or documentation markdown files - provides writing style guide (active voice, present tense), content structure patterns, and MDC component usage. Overrides brevity rules for proper grammar. Use nuxt-content for MDC syntax, nuxt-ui for component props.
license: MIT
---

> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

# Автор документации для экосистемы Nuxt

Руководство по написанию постов в блог и документации по образцам с официальных сайтов Nuxt.

## Когда использовать

- Написание постов в блог для проектов экосистемы Nuxt
- Создание или редактирование страниц документации
- Обеспечение единообразного стиля письма во всём контенте

## Стандарт письма

**Переопределение**: при написании документации соблюдайте правильную грамматику и полные предложения. Правило «жертвуй грамматикой ради краткости» здесь НЕ применяется.

Документация должна быть:

- Грамматически корректной
- Ясной и однозначной
- Правильно пунктуированной
- С полными предложениями (не обрывками)

Краткость по-прежнему ценится, но никогда — в ущерб ясности или корректности.

## Связанные скиллы

Для деталей по компонентам и синтаксису используйте эти скиллы:

| Скилл            | Использовать для                                |
| ---------------- | ----------------------------------------------- |
| **nuxt-content** | MDC-синтаксис, prose-компоненты, подсветка кода  |
| **nuxt-ui**      | Пропсы компонентов, темизация, UI-паттерны       |

## Доступные справочники

| Справочник                                                           | Назначение                                      |
| -------------------------------------------------------------------- | ----------------------------------------------- |
| **[references/writing-style.md](references/writing-style.md)**       | Залог, тон, структура предложений               |
| **[references/content-patterns.md](references/content-patterns.md)** | Frontmatter блога, структура, паттерны компонентов |

## Загрузка файлов

**Рассмотрите загрузку этих справочных файлов в зависимости от задачи:**

- [ ] [references/writing-style.md](references/writing-style.md) — если пишете прозу, улучшаете залог/тон или выстраиваете предложения
- [ ] [references/content-patterns.md](references/content-patterns.md) — если создаёте посты в блог, настраиваете frontmatter или используете MDC-компоненты

**НЕ загружайте все файлы сразу.** Загружайте только то, что относится к вашей текущей задаче.

## Краткая справка

### Паттерны письма

| Паттерн       | Пример                                             |
| ------------- | -------------------------------------------------- |
| Подлежащее-первым | "The `useFetch` composable handles data fetching." |
| Повелительный | "Add the following to `nuxt.config.ts`."           |
| Контекстный   | "When using authentication, configure..."          |

### Модальные глаголы

| Глагол   | Значение    |
| -------- | ----------- |
| `can`    | Опционально  |
| `should` | Рекомендуется |
| `must`   | Обязательно  |

### Паттерны компонентов (КОГДА использовать)

| Потребность       | Компонент                         |
| ----------------- | --------------------------------- |
| Информационная врезка | `::note`                       |
| Предложение       | `::tip`                           |
| Предостережение   | `::warning`                       |
| Обязательное      | `::important`                     |
| CTA (призыв к действию) | `:u-button{to="..." label="..."}` |
| Код из нескольких источников | `::code-group`             |

> По пропсам компонентов: см. скилл **nuxt-ui**

## Заголовки

- **H1 (`#`)**: без бэктиков — они отображаются некорректно
- **H2-H4**: бэктики работают нормально

## Рабочий процесс

1. Загрузите нужный справочный файл ([writing-style.md](references/writing-style.md) для прозы, [content-patterns.md](references/content-patterns.md) для структуры)
2. Набросайте контент, используя активный залог и настоящее время
3. Примените чек-лист ниже для проверки качества — если какой-то пункт не выполнен, переработайте и перепроверьте
4. Проверьте, что типы выносок соответствуют намерению (note/tip/warning/important)

## Пример

```md
# Getting Started with Authentication

Nuxt Better Auth provides a simple way to add authentication to your application.
Configure the module in your `nuxt.config.ts` to get started.

::note
Authentication requires a database connection. See the [database setup](/docs/database) guide for details.
::

## Installation

Add the module to your project:

~~~bash [Terminal]
pnpm add @onmax/nuxt-better-auth
~~~

The module auto-imports the `useUserSession` composable. Access the current user session from any component.
```

## Чек-лист

- [ ] Активный залог (85%+)
- [ ] Настоящее время
- [ ] 2-4 предложения на абзац
- [ ] Объяснение перед кодом
- [ ] Метки путей к файлам на блоках кода
- [ ] Подходящие типы выносок
- [ ] Нет бэктиков в заголовках H1
