> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: nuxt-modules
description: "Use when creating Nuxt modules: (1) Published npm modules (@nuxtjs/, nuxt-), (2) Local project modules (modules/ directory), (3) Runtime extensions (components, composables, plugins), (4) Server extensions (API routes, middleware), (5) Releasing/publishing modules to npm, (6) Setting up CI/CD workflows for modules. Provides defineNuxtModule patterns, Kit utilities, hooks, E2E testing, and release automation."
license: MIT
---

# Разработка модулей Nuxt

Руководство по созданию модулей Nuxt, расширяющих функциональность фреймворка.

**Связанные скиллы:** `nuxt` (основы), `vue` (рантайм-паттерны)

## Быстрый старт

```bash
npx nuxi init -t module my-module
cd my-module && npm install
npm run dev        # Запустить playground
npm run dev:build  # Сборка в режиме watch
npm run test       # Прогнать тесты
```

## Доступные материалы

- **[references/development.md](references/development.md)** — анатомия модуля, defineNuxtModule, утилиты Kit, хуки
- **[references/testing-and-publishing.md](references/testing-and-publishing.md)** — E2E-тестирование, лучшие практики, релиз, публикация
- **[references/ci-workflows.md](references/ci-workflows.md)** — готовые к копированию шаблоны CI/CD-воркфлоу

## Загрузка файлов

**Подумайте о загрузке этих справочных файлов в зависимости от задачи:**

- [ ] [references/development.md](references/development.md) — если разрабатываете функциональность модуля, используете defineNuxtModule или работаете с утилитами Kit
- [ ] [references/testing-and-publishing.md](references/testing-and-publishing.md) — если пишете E2E-тесты, публикуете в npm или следуете лучшим практикам
- [ ] [references/ci-workflows.md](references/ci-workflows.md) — если настраиваете CI/CD-воркфлоу для своего модуля

**НЕ загружайте все файлы сразу.** Загружайте только то, что относится к вашей текущей задаче.

## Типы модулей

| Тип            | Расположение     | Сценарий использования           |
| -------------- | ---------------- | -------------------------------- |
| Опубликованный | npm-пакет        | дистрибуция `@nuxtjs/`, `nuxt-`  |
| Локальный      | каталог `modules/` | расширения уровня проекта       |
| Inline         | `nuxt.config.ts` | простые одноразовые хуки          |

## Структура проекта

```
my-module/
├── src/
│   ├── module.ts           # Точка входа
│   └── runtime/            # Внедряется в приложение пользователя
│       ├── components/
│       ├── composables/
│       ├── plugins/
│       └── server/
├── playground/             # Тестирование при разработке
└── test/fixtures/          # E2E-тесты
```

## Ресурсы

- [Module Guide](https://nuxt.com/docs/guide/going-further/modules)
- [Nuxt Kit](https://nuxt.com/docs/api/kit)
- [Module Starter](https://github.com/nuxt/starter/tree/module)
