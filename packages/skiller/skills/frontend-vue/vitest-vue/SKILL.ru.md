> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: vitest-vue
description: Vitest fast unit testing framework powered by Vite with Jest-compatible API. Use when writing tests, mocking, configuring coverage, or working with test filtering and fixtures.
metadata:
  author: Anthony Fu
  version: "2026.1.28"
  source: Generated from https://github.com/vitest-dev/vitest, scripts located at https://github.com/antfu/skills
---

Vitest — это тестовый фреймворк нового поколения на базе Vite. Он предоставляет Jest-совместимый API с нативной поддержкой ESM, TypeScript и JSX «из коробки». Vitest использует те же config, трансформеры, резолверы и плагины, что и ваше Vite-приложение.

**Ключевые возможности:**
- Нативная интеграция с Vite: использует пайплайн трансформаций Vite для быстрых, похожих на HMR, обновлений тестов
- Jest-совместимость: drop-in замена для большинства наборов тестов на Jest
- Умный режим watch: перезапускает только затронутые тесты на основе графа модулей
- Нативная поддержка ESM, TypeScript, JSX без настройки
- Многопоточные воркеры для параллельного выполнения тестов
- Встроенное измерение покрытия через V8 или Istanbul
- Snapshot-тестирование, утилиты моков и шпионов (spy)

> Скилл основан на Vitest 3.x, сгенерирован 2026-01-28.

## Core (Ядро)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Configuration | Интеграция конфигов Vitest и Vite, использование defineConfig | [core-config](references/core-config.md) |
| CLI | Интерфейс командной строки, команды и опции | [core-cli](references/core-cli.md) |
| Test API | функция test/it, модификаторы вроде skip, only, concurrent | [core-test-api](references/core-test-api.md) |
| Describe API | describe/suite для группировки тестов и вложенных наборов | [core-describe](references/core-describe.md) |
| Expect API | Утверждения с toBe, toEqual, матчерами и асимметричными матчерами | [core-expect](references/core-expect.md) |
| Hooks | beforeEach, afterEach, beforeAll, afterAll, aroundEach | [core-hooks](references/core-hooks.md) |

## Features (Возможности)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Mocking | Мок-функции, модули, таймеры, даты через утилиты vi | [features-mocking](references/features-mocking.md) |
| Snapshots | Snapshot-тестирование с toMatchSnapshot и inline-снимками | [features-snapshots](references/features-snapshots.md) |
| Coverage | Покрытие кода с провайдерами V8 или Istanbul | [features-coverage](references/features-coverage.md) |
| Test Context | Тестовые фикстуры, context.expect, test.extend для кастомных фикстур | [features-context](references/features-context.md) |
| Concurrency | Конкурентные тесты, параллельное выполнение, шардинг | [features-concurrency](references/features-concurrency.md) |
| Filtering | Фильтрация тестов по имени, паттернам файлов, тегам | [features-filtering](references/features-filtering.md) |

## Advanced (Продвинутое)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Vi Utilities | Хелпер vi: mock, spyOn, поддельные таймеры, hoisted, waitFor | [advanced-vi](references/advanced-vi.md) |
| Environments | Тестовые окружения: node, jsdom, happy-dom, кастомные | [advanced-environments](references/advanced-environments.md) |
| Type Testing | Тестирование на уровне типов с expectTypeOf и assertType | [advanced-type-testing](references/advanced-type-testing.md) |
| Projects | Мультипроектные workspace, разные конфиги для каждого проекта | [advanced-projects](references/advanced-projects.md) |

## Related Skills (Связанные скиллы)

- **`vue-testing-best-practices`** — паттерны тестирования Vue-компонентов через VTU: **загружать вместе для Vue-проектов**
- **`ts-library`** — если проект является TypeScript-пакетом

## Related Skills (Связанные скиллы)

- **[vue-testing-best-practices](.agents/skills/vue-testing-best-practices/SKILL.md)** — тестирование Vue-компонентов с VTU, моки Nuxt/Pinia, специфика SSR. Загружать вместе с `vitest` для тестов в Vue-проекте
- **[vite](.agents/skills/vite/SKILL.md)** — Vitest разделяет Vite-конфиг
- **[ts-library](.agents/skills/ts-library/SKILL.md)** — bundling и тесты библиотечного кода
