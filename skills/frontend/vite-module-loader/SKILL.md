---
name: vite-module-loader
bucket: frontend
version: 0.1.0
description: "Vite как основной сборщик Frontend-проектов: базовая конфигурация, алиасы, build-практики"
risk: write
persona: oss-dev
tags: [vite, frontend, build]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Vite Module Loader & Build Practices

Vite используется как основной сборщик для Frontend проектов (вместо Webpack). Он обеспечивает моментальный запуск дев-сервера за счет нативных ES-модулей.

## Базовая Конфигурация (`vite.config.js` / `vite.config.ts`)

### 1. Алиасы (Aliases)

Используйте алиасы для предотвращения глубоких относительных путей (типа `../../../../components/Button.vue`).
Стандартный паттерн — использовать `@` для указания на папку `src/` (или `resources/js/` в Laravel).

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```
*Не забудьте продублировать алиасы в `tsconfig.json` (или `jsconfig.json`), чтобы IDE их понимала.*

### 2. Разделение Чанков (Chunk Splitting)

По умолчанию Vite собирает всё приложение в один или несколько больших файлов. Для оптимизации загрузки (особенно при обновлениях) вендорные библиотеки (Vue, Vue Router, Pinia) лучше выносить в отдельный чанк.

```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            return 'vendor'; // Все зависимости из node_modules пойдут в vendor.js
          }
        }
      }
    }
  }
})
```

### 3. Динамические Импорты (Lazy Loading)

Не импортируйте все компоненты и страницы сразу. Используйте динамический импорт `import()`, чтобы Vite создал для них отдельные чанки, которые загрузятся только при переходе пользователя на эту страницу.

**Плохо:**
```javascript
import Dashboard from './views/Dashboard.vue'
```

**Хорошо:**
```javascript
const Dashboard = () => import('./views/Dashboard.vue')
```
Это критически важно при настройке `vue-router`.

## Интеграция с Laravel

Если Vite используется внутри Laravel проекта, используется плагин `laravel-vite-plugin`.
В `vite.config.js` мы указываем точки входа (entry points).

```javascript
import { defineConfig } from 'vite';
import laravel from 'laravel-vite-plugin';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/js/app.js'],
            refresh: true, // Автоматическая перезагрузка при изменении blade файлов
        }),
        vue(),
    ],
});
```
