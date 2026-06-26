> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: nuxt-seo
description: Nuxt SEO meta-module with robots, sitemap, og-image, schema-org. Use when configuring SEO, generating sitemaps, creating OG images, or adding structured data.
license: MIT
---

# Nuxt SEO

```bash
npx nuxi module add @nuxtjs/seo
```

## Когда использовать

Работа с:

- Настройкой SEO (URL сайта, имя, индексируемость)
- Генерацией robots.txt и sitemap.xml
- Динамической генерацией OG-изображений
- Структурированными данными JSON-LD (schema.org)
- Хлебными крошками и каноническими URL

## Загрузка файлов

**Рассмотрите загрузку этих справочных файлов в зависимости от вашей задачи:**

- [ ] [references/site-config.md](references/site-config.md) — если настраиваете URL сайта, имя или основу SEO
- [ ] [references/crawlability.md](references/crawlability.md) — если настраиваете robots.txt или sitemap.xml
- [ ] [references/og-image.md](references/og-image.md) — если генерируете динамические OG-изображения
- [ ] [references/schema-org.md](references/schema-org.md) — если добавляете структурированные данные JSON-LD
- [ ] [references/utilities.md](references/utilities.md) — если работаете с хлебными крошками, каноническими URL или проверкой ссылок

**НЕ загружайте все файлы сразу.** Загружайте только то, что относится к вашей текущей задаче.

## Site Config

Основа для всех SEO-модулей. Настройте `site` в `nuxt.config.ts`, доступ через `useSiteConfig()`. Полный список опций см. в [references/site-config.md](references/site-config.md).

## Обзор модулей

| Модуль            | Назначение      | Ключевой API                  |
| ----------------- | --------------- | ----------------------------- |
| nuxt-site-config  | Общий конфиг    | `useSiteConfig()`             |
| @nuxtjs/robots    | robots.txt      | `useRobotsRule()`             |
| @nuxtjs/sitemap   | sitemap.xml     | `defineSitemapEventHandler()` |
| nuxt-og-image     | OG-изображения  | `defineOgImage()`             |
| nuxt-schema-org   | JSON-LD         | `useSchemaOrg()`              |
| nuxt-seo-utils    | Meta-утилиты    | `useBreadcrumbItems()`        |
| nuxt-link-checker | Проверка ссылок | Проверки на этапе сборки       |

## Nuxt Content v3

Используйте `asSeoCollection()` для автоматических sitemap, og-image и schema-org из frontmatter:

```ts
// content.config.ts
import { defineCollection, defineContentConfig } from '@nuxt/content'
import { asSeoCollection } from '@nuxtjs/seo/content'

export default defineContentConfig({
  collections: {
    posts: defineCollection(asSeoCollection({ type: 'page', source: 'posts/**' }))
  }
})
```

**Важно:** Загружайте `@nuxtjs/seo` перед `@nuxt/content` в массиве modules:

```ts
export default defineNuxtConfig({
  modules: ['@nuxtjs/seo', '@nuxt/content']
})
```

Поля frontmatter: `ogImage`, `sitemap`, `robots`, `schemaOrg`.

## Связанные скиллы

- [nuxt-content](../nuxt-content/SKILL.md) — для рендеринга MDC с SEO-frontmatter

## Ссылки

- [Документация](https://nuxtseo.com)
- [GitHub](https://github.com/harlan-zw/nuxt-seo)

## Экономия токенов

Основной скилл: ~250 токенов. Каждый под-файл: ~400-600 токенов. Загружайте только файлы, относящиеся к текущей задаче.
