> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: vitepress
description: VitePress static site generator powered by Vite and Vue. Use when building documentation sites, configuring themes, or writing Markdown with Vue components.
metadata:
  author: Anthony Fu
  version: "2026.1.28"
  source: Generated from https://github.com/vuejs/vitepress, scripts located at https://github.com/antfu/skills
---

VitePress — это генератор статических сайтов (SSG), построенный на Vite и Vue 3. Он берёт Markdown-контент, применяет тему и генерирует статический HTML, который превращается в SPA для быстрой навигации. Идеально подходит для документации, блогов и маркетинговых сайтов.

**Ключевые особенности:**
- Файловая маршрутизация на основе `.md`-файлов
- Vue-компоненты работают прямо в Markdown
- Быстрый HMR с мгновенными обновлениями (<100 мс)
- Тема по умолчанию, оптимизированная под документацию
- Встроенный поиск (локальный или Algolia)

**Перед работой с проектами на VitePress:**
- Проверьте `.vitepress/config.ts` на предмет конфигурации сайта
- Загляните в `.vitepress/theme/` — там пользовательские расширения темы
- Каталог `public/` содержит статические ресурсы, отдаваемые «как есть»

> Скилл основан на VitePress 1.x, сгенерирован 2026-01-28.

## Ядро (Core)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Конфигурация | Настройка файла конфигурации, defineConfig, метаданные сайта | [core-config](references/core-config.md) |
| CLI | Интерфейс командной строки: dev, build, preview, init | [core-cli](references/core-cli.md) |
| Маршрутизация | Файловая маршрутизация, исходный каталог, rewrites | [core-routing](references/core-routing.md) |
| Markdown | Frontmatter, контейнеры, таблицы, якоря, включения (includes) | [core-markdown](references/core-markdown.md) |

## Возможности (Features)

### Код и контент

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Блоки кода | Подсветка синтаксиса, подсветка строк, diff, focus | [features-code-blocks](references/features-code-blocks.md) |
| Vue в Markdown | Компоненты, script setup, директивы, шаблонизация | [features-vue](references/features-vue.md) |
| Загрузка данных | Загрузчики данных на этапе сборки, createContentLoader | [features-data-loading](references/features-data-loading.md) |
| Динамические маршруты | Генерация страниц из данных, paths-файлы загрузчика | [features-dynamic-routes](references/features-dynamic-routes.md) |

## Тема (Theme)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Конфигурация темы | Навигация, сайдбар, поиск, ссылки на соцсети, футер | [theme-config](references/theme-config.md) |
| Кастомизация | CSS-переменные, слоты, шрифты, глобальные компоненты | [theme-customization](references/theme-customization.md) |
| Своя тема | Создание тем с нуля, интерфейс темы | [theme-custom](references/theme-custom.md) |

## Продвинутое (Advanced)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Интернационализация | Многоязычные сайты, настройка локалей | [advanced-i18n](references/advanced-i18n.md) |
| Совместимость с SSR | Серверный рендеринг, ClientOnly, динамические импорты | [advanced-ssr](references/advanced-ssr.md) |

## Рецепты (Recipes)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Развёртывание | GitHub Pages, Netlify, Vercel, Cloudflare, Nginx | [recipes-deploy](references/recipes-deploy.md) |
