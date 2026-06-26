> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: nuxt
description: Use when working on Nuxt 4+ projects - provides server routes, file-based routing, middleware patterns, Nuxt-specific composables, and configuration with latest docs. Covers h3 v1 helpers (validation, WebSocket, SSE) and nitropack v2 patterns. Updated for Nuxt 4.3+.
license: MIT
---

# Разработка на Nuxt 4+

Прогрессивное руководство для проектов на Nuxt 4+ (v4.3+) с актуальными паттернами и соглашениями.

## Когда использовать

При работе с:

- Серверными маршрутами (API-эндпоинты, серверный middleware, серверные утилиты)
- Файловой маршрутизацией (страницы, лейауты, группы маршрутов)
- Middleware Nuxt (route guards, навигация)
- Плагинами Nuxt (расширения приложения)
- Специфичными для Nuxt возможностями (автоимпорты, слои, модули)

## Доступные руководства

Читайте конкретные файлы в зависимости от текущей задачи:

- **[references/server.md](references/server.md)** — API-маршруты, серверный middleware, валидация (Zod), WebSocket, SSE
- **[references/routing.md](references/routing.md)** — файловая маршрутизация, группы маршрутов, типизированный роутер, definePage
- **[references/middleware-plugins.md](references/middleware-plugins.md)** — route middleware, плагины, жизненный цикл приложения
- **[references/nuxt-composables.md](references/nuxt-composables.md)** — composables Nuxt (useRequestURL, useFetch, навигация)
- **[references/nuxt-components.md](references/nuxt-components.md)** — NuxtLink, NuxtImg, NuxtTime (предпочитать вместо HTML-элементов)
- **[references/nuxt-config.md](references/nuxt-config.md)** — конфигурация, модули, автоимпорты, слои

**Для composables Vue:** см. composables.md скилла `vue` (VueUse, паттерны Composition API)
**Для UI-компонентов:** используйте скилл `nuxt-ui`
**Для базы данных/хранилища:** используйте скилл `nuxthub`
**Для контент-ориентированных сайтов:** используйте скилл `nuxt-content`
**Для создания модулей:** используйте скилл `nuxt-modules`
**Для скаффолдинга проекта/CI:** используйте скилл `ts-library`

## Загрузка файлов

**Подумайте о загрузке этих справочных файлов в зависимости от вашей задачи:**

- [ ] [references/server.md](references/server.md) — если создаёте API-эндпоинты или серверный middleware
- [ ] [references/routing.md](references/routing.md) — если настраиваете страницы, лейауты или группы маршрутов
- [ ] [references/nuxt-composables.md](references/nuxt-composables.md) — если используете composables Nuxt (useFetch, useRequestURL и т. д.)
- [ ] [references/middleware-plugins.md](references/middleware-plugins.md) — если работаете с middleware или плагинами
- [ ] [references/nuxt-components.md](references/nuxt-components.md) — если используете компоненты Nuxt (NuxtLink, NuxtImg и т. д.)
- [ ] [references/nuxt-config.md](references/nuxt-config.md) — если редактируете nuxt.config.ts
- [ ] [references/project-setup.md](references/project-setup.md) — если настраиваете CI/ESLint/инструменты сборки

**НЕ загружайте все файлы сразу.** Загружайте только то, что относится к вашей текущей задаче.

## Быстрый старт

```ts
// server/api/hello.get.ts
import { z } from 'zod'

export default defineEventHandler(async (event) => {
  const { name } = await getValidatedQuery(event, z.object({
    name: z.string().default('world'),
  }).parse)
  return { message: `Hello ${name}` }
})
```

## Nuxt 4 против старых версий

**Вы работаете с Nuxt 4+.** Ключевые отличия:

| Старое (Nuxt 2/3) | Новое (Nuxt 4)                  |
| ----------------- | ------------------------------- |
| `<Nuxt />`        | `<NuxtPage />`                  |
| `context.params`  | `getRouterParam(event, 'name')` |
| `window.origin`   | `useRequestURL().origin`        |
| Строковые маршруты | Типизированный роутер с именами маршрутов |
| Отдельные layouts/ | Родительские маршруты с `<slot>` |

**Если вы не уверены в паттернах Nuxt 4, сначала прочитайте соответствующий файл руководства.**

## Актуальная документация

**Когда стоит загрузить свежую документацию:**

- Новые возможности Nuxt 4, не описанные здесь
- Конфигурация конкретного модуля
- Ломающие изменения или устаревания
- Продвинутые сценарии использования

**Официальные источники:**

- Nuxt: https://nuxt.com/docs
- h3 (серверный движок): https://v1.h3.dev/
- Nitro: https://nitro.build/

## Экономия токенов

Основной скилл: ~300 токенов. Каждый под-файл: ~800-1500 токенов. Загружайте только файлы, относящиеся к текущей задаче.
