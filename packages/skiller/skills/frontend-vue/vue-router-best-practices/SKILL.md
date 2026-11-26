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

# Skill: Vue Router 4 — routing and navigation

## Context

Client routing Vue 3 on Vue Router 4: route announcement, protection through guards,
lazy page loading, scroll recovery, navigation failure handling. Skill is gathered around
main breakdown Vue Router 4 — **callback refusal `next()` in favor of returning the value from guard**
(see migration below), plus type-safe named routes and Composition API (`useRoute`/`useRouter`).

**When to activate:**
- is being created or edited `router/index.ts`, array `routes`, navigation guards;
- is in the code `createRouter`, `beforeEach`/`beforeEnter`/`beforeRouteEnter`, `useRoute`/`useRouter`/`RouterLink`;
- question «how to protect a page with authorization», «why the navigation hangs / redirect went into a loop»,
  «how to lazily load a page component», «how to restore scroll position», «how to type routes».

**BOUNDARIES.** Here - only routing. Syntax `<script setup>`, `ref`/`computed`/`watch` — in
`frontend-vue/vue`. Component architecture and where-to-split — in `frontend-vue/vue-best-practices`. Global
status (incl. authorization flag that guard reads) — in `frontend-vue/pinia-stores`. Guard only
**asks** store, but does not implement the store logic.

## Algorithm

1. **Named + typed routes.** For each route, set `name` (stable identifier) and
   navigate by `name`, and not by string `path` — paths change, names do not. For type safety
   expand `RouteMeta` via `declare module 'vue-router'` (types `meta.requiresAuth`, `meta.roles`).
   In new projects you can enable experimental typed routes (`unplugin-vue-router`), but basic
   contract - named routes + typed `meta`.
2. **Lazy-loading view-components.** View-components (pages) connect by dynamic import:
   `component: () => import('@/views/AdminView.vue')` — everyone will end up in their own chunk and load according to
   requirement. Static `import` leave only for frequently used layout wrappers. Crash
   chunk loading is caught via `router.onError`.
3. **route meta — for declarative flags.** Route requirements (`requiresAuth`, `roles`, `title`,
   `layout`) keep in `meta`, and make your decision in the global guard by reading `to.meta`. This holds
   access logic in one place, and routes are declarative.
4. **Navigation guards on RETURN-API (main).** B Vue Router 4 third argument `next`
   **deprecated**. Guard accepts `(to, from)` and **returns** value:
   - `return undefined` / `return true` — skip navigation;
   - `return false` — cancel, stay on current route;
   - `return '/login'` — redirect by path;
   - `return { name: 'login', query: { redirect: to.fullPath } }` — redirect object (type safe);
   - `return new Error('...')` — cancel and trigger `router.onError()`.

   **Migration `next()` → `return`** (show old and new code side by side):
   ```ts
   // WAS (deprecated): easy to forget return after next() → double/floating navigation
   router.beforeEach((to, from, next) => {
     if (!isAuthed()) next('/login') // forgot return
     next()                          // BUG: will be called again
   })
   // NOW: net return, no next, one exit point per branch
   router.beforeEach((to, from) => {
     if (!isAuthed()) return { name: 'login', query: { redirect: to.fullPath } }
     // did not return anything → navigation continues
   })
   ```
   If **obliged** leave legacy-`next()` — exactly one call per branch and `return` immediately after it.
5. **Async-guard via `await`, not via `next()` in the callback.** Do the guard `async` and simply
   `await`/`return`. Don't call `next()` inside `.then()` — is a source of races and double calls.
   Asynchronous loading (for example, current user) make it idempotent so that it can be repeated
   navigation did not work on the network.
6. **Protection against endless redirect.** Before redirecting to `login`/`forbidden` check that
   **target** route - not itself `login`/`forbidden` (`if (to.name === 'login') return`). Otherwise guard
   will redirect the login page to itself.
7. **Per-route vs global.** `beforeEach` (global) — end-to-end rules (authorization, tab title).
   `beforeEnter` (per-route) — rule that is meaningful only for a specific route (role admin for
   `/admin`); you can have an array of guards. `beforeRouteEnter`/`beforeRouteUpdate`/`beforeRouteLeave`
   (in-component) — binding to component lifecycle; in `<script setup>` use
   `onBeforeRouteUpdate`/`onBeforeRouteLeave` from `vue-router`. **`beforeRouteEnter` does not have `this`**
   (component has not yet been created) — get the required copy otherwise (see reference).
8. **Reaction to changing the parameters of the same route.** When navigating `/user/1` → `/user/2`
   component **is reused**, `onMounted`/`created` will not work again. Follow the parameter:
   `watch(() => route.params.id, load, { immediate: true })` — otherwise the data will remain «frozen».
   Same about `beforeEnter`: it does not work when changing only the parameters (see reference).
9. **scrollBehavior.** Scroll recovery is set in the router option: `savedPosition` (Back/Forward)
   → anchor `to.hash` → `{ top: 0 }` for a new transition.
10. **Handle navigation failures.** Navigation canceled by the guard (`return false`) — this **not an error**,
    a `NavigationFailure`. Distinguish through `isNavigationFailure(failure, NavigationFailureType.aborted)`
    in `afterEach` / as a result `await router.push(...)`. Real errors (exceptions from guards,
    failure lazy-chunk) catch in `router.onError`.
11. **Composition API.** In the component: `const route = useRoute()` (reactive current route, for
    read `params`/`query`/`meta`), `const router = useRouter()` (imperative navigation
    `router.push`/`replace`/`back`). For custom navigation links - `useLink({ to })`
    (`href`, `isActive`, `navigate`). **Don't destructure `route`** directly - you'll lose
    reactivity; read through `route.params.x` or `toRef`.

## When what snippet / reference open

| Situation | Where to watch |
|:---|:---|
| Write guards (return-API, migration next(), async, anti-loop, beforeEnter, scrollBehavior, onError) | `snippets/router-guards.ts` |
| `beforeEnter` does not work when changing only `params` | `reference/router-beforeenter-no-param-trigger.md` |
| Needed `this`/component instance in `beforeRouteEnter` | `reference/router-beforerouteenter-no-this.md` |
| Guard does API-call - how to do it correctly `await` | `reference/router-guard-async-await-pattern.md` |
| User stuck in endless redirect | `reference/router-navigation-guard-infinite-loop.md` |
| Detailed analysis deprecated `next()` and migrations | `reference/router-navigation-guard-next-deprecated.md` |
| Frozen data when navigating between one route | `reference/router-param-change-no-lifecycle.md` |
| Listeners/timers are not cleared when unmounted view | `reference/router-simple-routing-cleanup.md` |
| Why Vue Router for production SPA (vs manual routing) | `reference/router-use-vue-router-for-production.md` |

## Quality checklist

- [ ] Routes have `name`; navigation and redirects - by `name`/object, not raw `path`
- [ ] `RouteMeta` typed (`declare module 'vue-router'`); access flags are in `meta`
- [ ] View-components are connected lazy `() => import(...)`
- [ ] In the guards NO `next()` — only `return undefined/false/path/route/Error` (or legacy: exactly one `next()` + `return` after)
- [ ] Async-guard - `async` + `await`/`return`, without `next()` in `.then()`; loading is idempotent
- [ ] There is protection against endless redirect (target `login`/`forbidden` skipped)
- [ ] Global (`beforeEach`) and per-route (`beforeEnter`) guards are divided by purpose
- [ ] Change `params` of the same route is processed via `watch(() => route.params...)`
- [ ] Set `scrollBehavior` (savedPosition → hash → top:0)
- [ ] `NavigationFailure` (canceled by guard) is separated from real errors; yes `router.onError`
- [ ] In components `useRoute`/`useRouter`, `route` is not destructured without `toRef`/`storeToRefs`

## Links

- `frontend-vue/vue` — reference API Composition API (`<script setup>`, `ref`/`computed`/`watch`): base, ship together
- `frontend-vue/vue-composition-api` — design conventions composables (where the logic for loading data by `route.params`)
- `frontend-vue/pinia-stores` — global state read by guard (authorization flag, current user, roles)
- `frontend-vue/vue-best-practices` — architecture view-components and partitioning
- https://router.vuejs.org/guide/advanced/navigation-guards.html · https://router.vuejs.org/guide/advanced/lazy-loading.html · https://router.vuejs.org/guide/advanced/scroll-behavior.html
- Import provenance (antfu/vuejs-ai) — `upstream.json` (strategy=notify), `SYNC.md`; reference/ — original gotcha-notes
