---
name: vite-module-loader
bucket: frontend-vite
version: 0.1.0
description: "Vite as primary frontend bundler: base config, aliases, build practices"
risk: write
persona: oss-dev
tags: [vite, frontend, build, laravel, vue]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Vite Module Loader & Build Practices

Vite = primary frontend bundler (not Webpack); native ESM dev server.

## Base config (`vite.config.js` / `vite.config.ts`)

### 1. Aliases
- Use aliases to avoid deep relative paths (`../../../../components/Button.vue`).
- Standard: `@` → `src/` (or `resources/js/` in Laravel).

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
- Duplicate aliases in `tsconfig.json` (or `jsconfig.json`) for IDE.

### 2. Chunk splitting
- Split vendor libs (Vue, Vue Router, Pinia) into a separate chunk.

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

### 3. Dynamic imports (lazy loading)
- Don't import all components/pages eagerly. Use `import()` → separate chunks loaded on navigation. Critical for `vue-router`.

Bad:
```javascript
import Dashboard from './views/Dashboard.vue'
```
Good:
```javascript
const Dashboard = () => import('./views/Dashboard.vue')
```

## Laravel integration
- Inside Laravel: use `laravel-vite-plugin`; declare entry points (`input`).

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

## Links
- https://vitejs.dev/config/
- https://github.com/laravel/vite-plugin
- Related: `frontend-vite/vite-multi-build` (two independent builds: app + Filament), `devops/docker-vite` (Vite dev server as separate compose service, HMR in Docker), `frontend-wayfinder/wayfinder` (`wayfinder()` vite plugin in build), `frontend-tailwind/tailwind-conventions` (`@tailwindcss/vite` plugin, Tailwind v4 build)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 3101147779e30b27aefa2597806d24a4b6e6d6339367360294c079b3ca87a590 -->
