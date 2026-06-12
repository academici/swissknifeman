---
name: wayfinder
bucket: frontend
version: 0.1.0
description: "Laravel Wayfinder: типобезопасные роуты и controller actions для фронтенда. Генерация, именованные импорты, form(), архитектурные границы импортов через ESLint."
risk: write
persona: oss-dev
tags: [wayfinder, laravel, typescript, routes, inertia, eslint]
requires: []
produces_for: []
outputs: []
snippets: [wayfinder-usage.ts, eslint-boundaries.cjs, vite-wayfinder.js]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Laravel Wayfinder

## Контекст

Wayfinder автогенерирует типизированные TS-функции для каждого Laravel-роута и controller action. Фронтенд вызывает `show(1)` вместо хардкода `/documents/1` — TypeScript ловит несоответствия при изменении роутов на этапе компиляции.

Применять когда: фронтенд вызывает backend-роуты, верстаются формы/ссылки на endpoints, падают route-related TS-ошибки, встречаются импорты из `@/actions` или `@/routes`.

## Алгоритм

1. **Генерация**: `php artisan wayfinder:generate --no-interaction` (для form-хелперов добавить `--with-form`). В dev поставить vite-плагин `wayfinder()` — автоген при изменении роутов, ручная регенерация не нужна.
2. **Импорты — ТОЛЬКО именованные** (tree-shaking):
   `import { show, store } from '@/actions/App/Http/Controllers/DocumentController'`. Default-импорты запрещены — тянут весь файл в бандл.
3. **Использование**: `show(1)` → `{ url, method }`; `show.url(1)` → строка; `show.get(1)` / `store.post()` / `update.patch(1)` / `destroy.delete(1)`; `store.form()` → `{ action, method }` для `<Form v-bind="store.form()">`; query: `show(1, { query: { page: 1 } })`.
4. **Архитектурная граница**: доменные Vue-компоненты НЕ импортируют `@/wayfinder/routes/*` напрямую — только через слой actions/composables. Закрепить ESLint-правилом `no-restricted-imports` (точечный whitelist для легитимных исключений). Строковые литералы вместо enum в доменном коде ловить через `no-restricted-syntax`.
5. **Route model binding**: если роут ждёт модель, передавать объект с ключом параметра (`show({ document: 1 })`), а не «голый» id, — TypeScript подскажет точную сигнатуру.
6. **После изменения роутов**: без vite-плагина — регенерировать вручную; проверить, что TS-импорты резолвятся и URL соответствуют ожиданиям.

## Когда НЕ применять

- Backend-only задачи без фронтенд-вызовов роутов.
- Проект без Wayfinder — сначала установить пакет и сгенерировать типы, потом применять паттерны.

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Импорты, методы, query-параметры, `<Form>` — примеры использования | `snippets/wayfinder-usage.ts` |
| Настроить ESLint-границы: запрет прямых wayfinder-импортов и строковых литералов вместо enum | `snippets/eslint-boundaries.cjs` |
| Подключить vite-плагин wayfinder() и алиасы `@/routes`, `@` | `snippets/vite-wayfinder.js` |

## Чеклист качества

- [ ] Нет хардкода URL — все обращения к backend через wayfinder-функции
- [ ] Только именованные импорты из `@/actions/...` и `@/routes/...`
- [ ] Доменные Vue-компоненты не импортируют `@/wayfinder/routes/*` напрямую (есть ESLint-правило)
- [ ] Vite-плагин `wayfinder()` подключён, либо после изменения роутов выполнен `wayfinder:generate`
- [ ] Формы используют `store.form()` / `update.form(id)` вместо ручных `action`/`method`
- [ ] Автогенерённые `@/actions`, `@/routes`, `@/wayfinder` не редактируются руками

## Ссылки

- https://github.com/laravel/wayfinder
- https://laravel.com/docs/wayfinder (актуальную версию проверить)
- Связанные скиллы: `frontend/inertia-vue` (слои resources/js), `frontend/vitest` (exclude автогена из coverage)
