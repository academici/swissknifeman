---
name: vue-router-best-practices
bucket: frontend-vue
version: 0.2.1
description: "Use for Vue Router 4 routes, navigation guards, redirects, lazy views, and scroll restoration."
risk: write
persona: oss-dev
tags: [vue, vue-router, frontend, routing, navigation-guards, lazy-loading, typescript]
requires: []
produces_for: []
outputs: []
snippets: [router-guards.ts]
adapters: [claude, cursor, fable]
license: MIT
author: github.com/vuejs-ai
sha256: ""
---

# Skill: Vue Router 4 — маршрутизация и навигация

## Контекст

Клиентская маршрутизация Vue 3 на Vue Router 4: объявление маршрутов, защита через гварды,
ленивая загрузка страниц, восстановление скролла, обработка сбоев навигации. Скилл собран вокруг
главной ломки Vue Router 4 — **отказа от колбэка `next()` в пользу возврата значения из гварда**
(см. миграцию ниже), плюс типобезопасные именованные маршруты и Composition API (`useRoute`/`useRouter`).

**Когда активировать:**
- создаётся или правится `router/index.ts`, массив `routes`, навигационные гварды;
- в коде есть `createRouter`, `beforeEach`/`beforeEnter`/`beforeRouteEnter`, `useRoute`/`useRouter`/`RouterLink`;
- вопрос «как защитить страницу авторизацией», «почему навигация висит / редирект зациклился»,
  «как лениво грузить компонент страницы», «как восстановить позицию скролла», «как типизировать маршруты».

**ГРАНИЦЫ.** Здесь — только маршрутизация. Синтаксис `<script setup>`, `ref`/`computed`/`watch` — в
`frontend-vue/vue`. Архитектура компонентов и where-to-split — в `frontend-vue/vue-best-practices`. Глобальное
состояние (в т.ч. флаг авторизации, который читает гвард) — в `frontend-vue/pinia-stores`. Гвард только
**спрашивает** стор, но не реализует логику стора.

## Алгоритм

1. **Именованные + typed routes.** У каждого маршрута задавай `name` (стабильный идентификатор) и
   навигируй по `name`, а не по строковому `path` — пути меняются, имена нет. Для типобезопасности
   расширяй `RouteMeta` через `declare module 'vue-router'` (типы `meta.requiresAuth`, `meta.roles`).
   В новых проектах можно включить experimental typed routes (`unplugin-vue-router`), но базовый
   контракт — именованные маршруты + типизированный `meta`.
2. **Lazy-loading view-компонентов.** View-компоненты (страницы) подключай динамическим импортом:
   `component: () => import('@/views/AdminView.vue')` — каждый попадёт в свой чанк и загрузится по
   требованию. Статический `import` оставляй только для часто используемых лэйаут-обёрток. Сбой
   загрузки чанка ловится через `router.onError`.
3. **route meta — для декларативных флагов.** Требования к маршруту (`requiresAuth`, `roles`, `title`,
   `layout`) держи в `meta`, а решение принимай в глобальном гварде, читая `to.meta`. Это держит
   логику доступа в одном месте, а маршруты — декларативными.
4. **Навигационные гварды на ВОЗВРАТ-API (главное).** В Vue Router 4 третий аргумент `next`
   **deprecated**. Гвард принимает `(to, from)` и **возвращает** значение:
   - `return undefined` / `return true` — пропустить навигацию;
   - `return false` — отменить, остаться на текущем маршруте;
   - `return '/login'` — редирект по path;
   - `return { name: 'login', query: { redirect: to.fullPath } }` — редирект объектом (типобезопасно);
   - `return new Error('...')` — отменить и триггернуть `router.onError()`.

   **Миграция `next()` → `return`** (показывай старый и новый код рядом):
   ```ts
   // БЫЛО (deprecated): легко забыть return после next() → двойная/висящая навигация
   router.beforeEach((to, from, next) => {
     if (!isAuthed()) next('/login') // забыл return
     next()                          // BUG: вызовется повторно
   })
   // СТАЛО: чистый возврат, без next, одна точка выхода на ветку
   router.beforeEach((to, from) => {
     if (!isAuthed()) return { name: 'login', query: { redirect: to.fullPath } }
     // ничего не вернули → навигация продолжается
   })
   ```
   Если **обязан** оставить legacy-`next()` — ровно один вызов на ветку и `return` сразу после него.
5. **Async-гвард через `await`, не через `next()` в колбэке.** Делай гвард `async` и просто
   `await`/`return`. Не вызывай `next()` внутри `.then()` — это источник гонок и двойных вызовов.
   Асинхронную загрузку (например, текущего пользователя) делай идемпотентной, чтобы повторная
   навигация не дёргала сеть.
6. **Защита от бесконечного редиректа.** Перед редиректом на `login`/`forbidden` проверь, что
   **целевой** маршрут — не сам `login`/`forbidden` (`if (to.name === 'login') return`). Иначе гвард
   будет редиректить страницу логина на саму себя.
7. **Per-route vs global.** `beforeEach` (global) — сквозные правила (авторизация, заголовок вкладки).
   `beforeEnter` (per-route) — правило, осмысленное только для конкретного маршрута (роль admin для
   `/admin`); можно массив гвардов. `beforeRouteEnter`/`beforeRouteUpdate`/`beforeRouteLeave`
   (in-component) — привязка к жизненному циклу компонента; в `<script setup>` используй
   `onBeforeRouteUpdate`/`onBeforeRouteLeave` из `vue-router`. **`beforeRouteEnter` не имеет `this`**
   (компонент ещё не создан) — нужный экземпляр получай иначе (см. reference).
8. **Реакция на смену параметров того же маршрута.** При навигации `/user/1` → `/user/2`
   компонент **переиспользуется**, `onMounted`/`created` не сработают повторно. Следи за параметром:
   `watch(() => route.params.id, load, { immediate: true })` — иначе данные останутся «застывшими».
   То же про `beforeEnter`: он не срабатывает при смене только параметров (см. reference).
9. **scrollBehavior.** Восстановление скролла задаётся в опции роутера: `savedPosition` (Назад/Вперёд)
   → якорь `to.hash` → `{ top: 0 }` для нового перехода.
10. **Обработка сбоев навигации.** Отменённая гвардом навигация (`return false`) — это **не ошибка**,
    а `NavigationFailure`. Различай через `isNavigationFailure(failure, NavigationFailureType.aborted)`
    в `afterEach` / в результате `await router.push(...)`. Реальные ошибки (исключения из гвардов,
    сбой lazy-чанка) лови в `router.onError`.
11. **Composition API.** В компоненте: `const route = useRoute()` (реактивный текущий маршрут, для
    чтения `params`/`query`/`meta`), `const router = useRouter()` (императивная навигация
    `router.push`/`replace`/`back`). Для кастомных навигационных ссылок — `useLink({ to })`
    (`href`, `isActive`, `navigate`). **Не деструктурируй `route`** напрямую — потеряешь
    реактивность; читай через `route.params.x` или `toRef`.

## Когда какой сниппет / reference открывать

| Ситуация | Где смотреть |
|:---|:---|
| Написать гварды (return-API, миграция next(), async, anti-loop, beforeEnter, scrollBehavior, onError) | `snippets/router-guards.ts` |
| `beforeEnter` не срабатывает при смене только `params` | `reference/router-beforeenter-no-param-trigger.md` |
| Нужен `this`/экземпляр компонента в `beforeRouteEnter` | `reference/router-beforerouteenter-no-this.md` |
| Гвард делает API-вызов — как правильно `await` | `reference/router-guard-async-await-pattern.md` |
| Пользователь застрял в бесконечном редиректе | `reference/router-navigation-guard-infinite-loop.md` |
| Подробный разбор deprecated `next()` и миграции | `reference/router-navigation-guard-next-deprecated.md` |
| Застывшие данные при навигации между одним маршрутом | `reference/router-param-change-no-lifecycle.md` |
| Слушатели/таймеры не очищаются при размонтировании view | `reference/router-simple-routing-cleanup.md` |
| Зачем Vue Router для production SPA (vs ручная маршрутизация) | `reference/router-use-vue-router-for-production.md` |

## Чеклист качества

- [ ] Маршруты имеют `name`; навигация и редиректы — по `name`/объекту, не по сырому `path`
- [ ] `RouteMeta` типизирован (`declare module 'vue-router'`); флаги доступа лежат в `meta`
- [ ] View-компоненты подключены ленивым `() => import(...)`
- [ ] В гвардах НЕТ `next()` — только `return undefined/false/path/route/Error` (или legacy: ровно один `next()` + `return` после)
- [ ] Async-гвард — `async` + `await`/`return`, без `next()` в `.then()`; загрузка идемпотентна
- [ ] Есть защита от бесконечного редиректа (целевой `login`/`forbidden` пропускается)
- [ ] Global (`beforeEach`) и per-route (`beforeEnter`) гварды разделены по назначению
- [ ] Смена `params` того же маршрута обрабатывается через `watch(() => route.params...)`
- [ ] Задан `scrollBehavior` (savedPosition → hash → top:0)
- [ ] `NavigationFailure` (отмена гвардом) отделена от реальных ошибок; есть `router.onError`
- [ ] В компонентах `useRoute`/`useRouter`, `route` не деструктурируется без `toRef`/`storeToRefs`

## Ссылки

- `frontend-vue/vue` — справочник API Composition API (`<script setup>`, `ref`/`computed`/`watch`): база, грузить вместе
- `frontend-vue/vue-composition-api` — проектные конвенции composables (где живёт логика загрузки данных по `route.params`)
- `frontend-vue/pinia-stores` — глобальное состояние, которое читает гвард (флаг авторизации, текущий пользователь, роли)
- `frontend-vue/vue-best-practices` — архитектура view-компонентов и разбиение на части
- https://router.vuejs.org/guide/advanced/navigation-guards.html · https://router.vuejs.org/guide/advanced/lazy-loading.html · https://router.vuejs.org/guide/advanced/scroll-behavior.html
- Провенанс импорта (antfu/vuejs-ai) — `upstream.json` (strategy=notify), `SYNC.md`; reference/ — оригинальные gotcha-заметки
