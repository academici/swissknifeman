---
name: ts-library
description: Use when authoring TypeScript libraries or npm packages - covers project setup, package.json exports, build tooling (tsdown/unbuild), API design patterns, type inference tricks, testing, and publishing to npm. Use when bundling, configuring dual CJS/ESM output, or setting up release workflows.
license: MIT
---

> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

# Разработка TypeScript-библиотек

Паттерны для создания высококачественных TypeScript-библиотек, извлечённые из изучения unocss, shiki, unplugin, vite, vitest, vueuse, zod, trpc, drizzle-orm и других.

## Когда использовать

- Старт новой TypeScript-библиотеки (одиночный пакет или монорепо)
- Настройка экспортов package.json для двойного формата CJS/ESM
- Конфигурация tsconfig для разработки библиотеки
- Выбор инструментов сборки (tsdown, unbuild)
- Проектирование типобезопасных API (паттерны builder, factory, plugin)
- Написание продвинутых типов TypeScript
- Настройка vitest для тестирования библиотеки
- Конфигурация release-процесса и CI

**Для разработки модулей Nuxt:** используй скилл `nuxt-modules`

## Быстрая справка

| Работаешь над...      | Загрузи файл                                                       |
| --------------------- | ------------------------------------------------------------------ |
| Настройка нового проекта | [references/project-setup.md](references/project-setup.md)      |
| Экспорты пакета       | [references/package-exports.md](references/package-exports.md)     |
| Опции tsconfig        | [references/typescript-config.md](references/typescript-config.md) |
| Конфигурация сборки   | [references/build-tooling.md](references/build-tooling.md)         |
| Конфигурация ESLint   | [references/eslint-config.md](references/eslint-config.md)         |
| Паттерны проектирования API | [references/api-design.md](references/api-design.md)         |
| Приёмы вывода типов   | [references/type-patterns.md](references/type-patterns.md)         |
| Настройка тестирования | [references/testing.md](references/testing.md)                    |
| Release-процесс       | [references/release.md](references/release.md)                     |
| Настройка CI/CD       | [references/ci-workflows.md](references/ci-workflows.md)           |

## Загрузка файлов

**Рассмотри загрузку этих справочных файлов в зависимости от твоей задачи:**

- [ ] [references/project-setup.md](references/project-setup.md) — если начинаешь новый проект TypeScript-библиотеки
- [ ] [references/package-exports.md](references/package-exports.md) — если настраиваешь экспорты package.json или двойной формат CJS/ESM
- [ ] [references/typescript-config.md](references/typescript-config.md) — если настраиваешь или изменяешь tsconfig.json
- [ ] [references/build-tooling.md](references/build-tooling.md) — если настраиваешь tsdown, unbuild или скрипты сборки
- [ ] [references/eslint-config.md](references/eslint-config.md) — если настраиваешь ESLint для разработки библиотеки
- [ ] [references/api-design.md](references/api-design.md) — если проектируешь публичные API, паттерны builder или plugin-системы
- [ ] [references/type-patterns.md](references/type-patterns.md) — если работаешь с продвинутыми типами TypeScript или выводом типов
- [ ] [references/testing.md](references/testing.md) — если настраиваешь vitest или пишешь тесты для кода библиотеки
- [ ] [references/release.md](references/release.md) — если настраиваешь release-процесс или версионирование
- [ ] [references/ci-workflows.md](references/ci-workflows.md) — если настраиваешь GitHub Actions или CI/CD-конвейеры

**НЕ загружай все файлы сразу.** Загружай только то, что относится к твоей текущей задаче.

## Процесс новой библиотеки

1. Создай структуру проекта → загрузи [references/project-setup.md](references/project-setup.md)
2. Настрой экспорты `package.json` → загрузи [references/package-exports.md](references/package-exports.md)
3. Настрой сборку через tsdown → загрузи [references/build-tooling.md](references/build-tooling.md)
4. Проверь сборку: `pnpm build && pnpm pack --dry-run` — убедись, что вывод включает `.mjs`, `.cjs`, `.d.ts`
5. Добавь тесты → загрузи [references/testing.md](references/testing.md)
6. Настрой release → загрузи [references/release.md](references/release.md)

## Быстрый старт

```json
// package.json (минимальный)
{
  "name": "my-lib",
  "type": "module",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.cjs"
    }
  },
  "main": "./dist/index.cjs",
  "module": "./dist/index.mjs",
  "types": "./dist/index.d.ts",
  "files": ["dist"]
}
```

```ts
// tsdown.config.ts
import { defineConfig } from 'tsdown'

export default defineConfig({
  entry: ['src/index.ts'],
  format: ['esm', 'cjs'],
  dts: true,
})
```

## Ключевые принципы

- ESM-first: `"type": "module"` с выводом в `.mjs`
- Двойной формат: всегда поддерживай потребителей и CJS, и ESM
- `moduleResolution: "Bundler"` для современного TypeScript
- tsdown для большинства сборок, unbuild для сложных случаев
- Умные значения по умолчанию: определяй окружение, не навязывай конфигурацию
- Tree-shakeable: ленивые геттеры, корректный `sideEffects: false`

_Эффективность по токенам: основной скилл ~300 токенов, каждая справка ~800-1200 токенов_
