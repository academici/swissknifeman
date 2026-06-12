---
name: vitest
bucket: frontend
version: 0.1.0
description: "Vitest для Vue/Inertia-проекта на Laravel: jsdom, globals, тесты в resources/js/tests зеркалят исходники, coverage v8 с обязательным exclude автогенерённого кода."
risk: write
persona: oss-dev
tags: [vitest, testing, vue, coverage, jsdom, laravel]
requires: []
produces_for: []
outputs: []
snippets: [vitest.config.ts, component-test.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Vitest (Vue/Inertia на Laravel)

## Контекст

Юнит-тесты фронтенда Laravel + Inertia + Vue через Vitest. Ключевые решения: `environment: jsdom` (DOM-API для компонентов), `globals: true` (describe/it/expect без импортов), тесты живут в `resources/js/tests/**` и **зеркалят структуру исходников** (components/, composables/, events/, stores/...). Coverage — provider v8; автогенерённый код (wayfinder/, actions/, routes/) и сами тесты обязаны быть исключены из coverage, иначе метрики бессмысленны.

Применять когда: настраивается Vitest в Laravel/Inertia-проекте, пишутся тесты компонентов/composables, падает резолв алиасов в тестах, coverage показывает мусорные проценты из-за автогена.

## Алгоритм

1. **Конфиг** `vitest.config.ts`: плагин `vue()` (с теми же `transformAssetUrls`, что в vite.config), алиасы `@/routes` → `resources/js/wayfinder/routes` и `@` → `resources/js` — идентичные основной сборке, иначе тесты не резолвят импорты.
2. **Секция test**: `environment: 'jsdom'`, `globals: true`, `include: ['resources/js/tests/**/*.{test,spec}.{ts,js}']`.
3. **Структура тестов** — зеркало исходников: `composables/document/useDocumentFilters.ts` → `tests/composables/document/useDocumentFilters.test.ts`. Новый слой исходников = новая подпапка в tests/.
4. **Coverage**: `provider: 'v8'`, reporter text/html/lcov, `include: ['resources/js/**/*.{ts,vue}']`; **обязательный exclude**: `tests/**`, entrypoints (`app.ts`, `bootstrap.ts`) и весь автоген — `actions/**`, `routes/**`, `wayfinder/**`.
5. **Скрипты**: `test` (watch), `test:run`, `test:coverage` (`vitest run --coverage`).
6. **Тесты компонентов** — `@vue/test-utils` `mount()`; composables тестировать как обычные функции, оборачивая в компонент-носитель только когда нужен lifecycle/inject.

## Когда НЕ применять

- E2E и браузерные сценарии — это Dusk/Playwright, не Vitest.
- Тесты PHP-бэкенда — Pest/PHPUnit (см. бакет php).

## Когда какой сниппет открывать

| Ситуация | Файл |
|:---|:---|
| Создать/поправить конфиг: jsdom, алиасы, include, coverage exclude | `snippets/vitest.config.ts` |
| Написать первый тест компонента или composable | `snippets/component-test.ts` |

## Чеклист качества

- [ ] Алиасы в vitest.config идентичны vite.config (`@/routes` до `@`)
- [ ] `environment: jsdom`, `globals: true`, include указывает на `resources/js/tests/**`
- [ ] Тест лежит в зеркальной подпапке относительно исходника
- [ ] Coverage exclude содержит `tests/**`, `actions/**`, `routes/**`, `wayfinder/**`, entrypoints
- [ ] В package.json есть `test`, `test:run`, `test:coverage`
- [ ] `vitest run` зелёный локально перед коммитом

## Ссылки

- https://vitest.dev/config/
- https://vitest.dev/guide/coverage
- https://test-utils.vuejs.org/
- Связанные скиллы: `frontend/inertia-vue` (структура resources/js), `frontend/wayfinder` (что считается автогеном)
- Скилл `quality/test-strategy` — стратегия пирамиды и coverage policy
