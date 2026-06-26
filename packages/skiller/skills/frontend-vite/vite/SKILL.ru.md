> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: vite
description: Vite build tool configuration, plugin API, SSR, and Vite 8 Rolldown migration. Use when working with Vite projects, vite.config.ts, Vite plugins, or building libraries/SSR apps with Vite.
metadata:
  author: Anthony Fu
  version: "2026.1.31"
  source: Generated from https://github.com/vitejs/vite, scripts at https://github.com/antfu/skills
---

# Vite

> Основано на Vite 8 beta (на движке Rolldown). Vite 8 использует бандлер Rolldown и трансформер Oxc.

Vite — это фронтенд-инструмент сборки нового поколения с быстрым dev-сервером (нативный ESM + HMR) и оптимизированными продакшен-сборками.

## Предпочтения

- Используйте TypeScript: предпочитайте `vite.config.ts`
- Всегда используйте ESM, избегайте CommonJS

## Ядро (Core)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Конфигурация | `vite.config.ts`, `defineConfig`, условные конфиги, `loadEnv` | [core-config](references/core-config.md) |
| Возможности | `import.meta.glob`, query-параметры ресурсов (`?raw`, `?url`), `import.meta.env`, HMR API | [core-features](references/core-features.md) |
| Plugin API | специфичные для Vite хуки, виртуальные модули, порядок плагинов | [core-plugin-api](references/core-plugin-api.md) |

## Сборка и SSR (Build & SSR)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Сборка и SSR | режим библиотеки (library mode), режим middleware для SSR, `ssrLoadModule`, JavaScript API | [build-and-ssr](references/build-and-ssr.md) |

## Продвинутое (Advanced)

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Environment API | поддержка нескольких окружений (multi-environment) в Vite 6+, кастомные рантаймы | [environment-api](references/environment-api.md) |
| Миграция на Rolldown | изменения в Vite 8: бандлер Rolldown, трансформер Oxc, миграция конфига | [rolldown-migration](references/rolldown-migration.md) |

## Быстрая справка (Quick Reference)

### Команды CLI

```bash
vite              # Запустить dev-сервер
vite build        # Продакшен-сборка
vite preview      # Предпросмотр продакшен-сборки
vite build --ssr  # SSR-сборка
```

### Типовой конфиг

```ts
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [],
  resolve: { alias: { '@': '/src' } },
  server: { port: 3000, proxy: { '/api': 'http://localhost:8080' } },
  build: { target: 'esnext', outDir: 'dist' },
})
```

### Официальные плагины

- `@vitejs/plugin-vue` — поддержка Vue 3 SFC
- `@vitejs/plugin-vue-jsx` — Vue 3 JSX
- `@vitejs/plugin-react` — React с Oxc/Babel
- `@vitejs/plugin-react-swc` — React с SWC
- `@vitejs/plugin-legacy` — поддержка устаревших браузеров
