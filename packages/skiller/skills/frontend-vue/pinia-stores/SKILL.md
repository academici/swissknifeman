---
name: pinia-stores
bucket: frontend-vue
version: 0.1.0
description: "Pinia (Vue 3) global state: setup stores (defineStore with function), ref=state/computed=getters/function=actions, use*Store naming, store composition, access outside components, hydration, persist. Activate creating/editing resources/js/stores/**, defineStore, useXxxStore, or 'how to store global state / share data between components'."
risk: write
persona: oss-dev
tags: [pinia, vue, frontend, state-management, store, architecture]
requires: []
produces_for: []
outputs: []
snippets: [useExampleStore.ts, store-in-component.vue, store-composition.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Pinia stores (Vue 3)

## Scope

Global (shared-across-components) Vue 3 state on Pinia: counters, current user, cart, open modals, reference-data cache — anything surviving one component's unmount and read from multiple places.

Activate when:
- file under `resources/js/stores/**` (or `src/stores/**`) created/edited;
- code has `defineStore(...)`, import `from 'pinia'`, `useXxxStore()` call;
- question "share data between unrelated components", "where to move state out of a component", "access state from a plain `.ts` module (outside a component)".

BOUNDARY vs skill `frontend-vue/vue-composition-api`: there = `<script setup>`, local state of ONE component (`ref`/`computed`/`watch` inside component). Here = GLOBAL state living in Pinia, accessible everywhere. State needed only by current component is NOT a store — keep `ref` in component or extract a composable. Create a store when state is read/changed from ≥2 unrelated places or must survive navigation.

## Rules

1. Register Pinia ONCE per app. At startup (`app.ts`/`main.ts`): `const pinia = createPinia()` + `app.use(pinia)`. Without it any `useXxxStore()` throws. One `pinia` instance per app; SSR — new instance per request.
2. Setup stores ONLY: `defineStore('id', () => { ... })` with a setup function. Do NOT use option store `defineStore('id', { state, getters, actions })` in new code.
3. Inside setup, three roles by value type:
   - `ref()`/`reactive()` → state;
   - `computed()` → getters (derived, cached);
   - plain `function` → actions (state mutations + async).
4. Return everything public from setup: `return { count, doubleCount, increment }`. Not returned = private (e.g. internal `let pulseTimer`). A state-`ref` MUST be in `return` or Pinia won't treat it as state (devtools/SSR/persist).
5. Naming: file and factory `use<Domain>Store` (`useCartStore`, `useNotificationsStore`); first `defineStore` arg = stable string `id` (`'cart'`, `'notifications'`) — key in devtools and persisted storage, don't change it carelessly.
6. One store = one domain. Don't dump unrelated entities into a "global" store. Split by domain (`useAuthStore`, `useCartStore`, `useUiStore`); files in `resources/js/stores/`, domain subfolders as they grow.
7. In component: `const store = useXxxStore()` in `<script setup>`. Call methods straight off store (`store.increment()`). To destructure state/getters keeping reactivity → `storeToRefs(store)` (plain `const { count } = store` breaks reactivity). Actions can be destructured as-is (not reactive).
8. Access outside component (`.ts` modules, event bus, ws adapters): call `useXxxStore()` INSIDE the function/handler, not at module top level — Pinia may not be installed at import time. Pass a specific `pinia` as first arg only in code before `app.use(pinia)` or server code outside request lifecycle.
9. Hydration / server init: don't duplicate what backend already rendered. Server passes initial value via props/initial-state — owner component seeds it via `onMounted(() => store.init(props.initialValue))` (or equivalent). Store holds `init(payload)` / `setX(...)` that seeds state; live updates (events, ws) go through actions.
10. SSR: create `createPinia()` per request (a shared singleton store would leak between users). Initial state serialized on server, rehydrated on client — on client don't overwrite it with a refetch if value already arrived.
11. persist only when needed: `localStorage`/`sessionStorage` via plugin `pinia-plugin-persistedstate` and `persist` option in `defineStore`. Persist only what must survive reload (UI prefs, draft); do NOT persist tokens/sensitive or server cache.
12. Store composition (store in store): inside one store's setup call `useOtherStore()` and read its state/getters / call its actions — derived state without duplication. Avoid mutual cycles (A↔B); extract shared into a third store or action param.

## setup store anatomy

```ts
export const useCounterStore = defineStore('counter', () => {
  // state
  const count = ref(0)
  // getter
  const doubleCount = computed(() => count.value * 2)
  // приватное (НЕ в return) — недоступно снаружи
  let timer: ReturnType<typeof setTimeout> | null = null
  // action
  function increment() { count.value++ }

  return { count, doubleCount, increment } // всё публичное
})
```

Easy-to-break rules:
- State-`ref` not in `return` → not store state (absent from devtools/SSR/persist). Return it.
- `const { count } = store` in component → reactivity lost. Use `storeToRefs(store)` for state/getters.
- `useStore()` at top level of plain `.ts` module → "getActivePinia() was called but there was no active Pinia". Call inside a function.
- Mutating state directly from outside (`store.count = 5` in component) is technically possible, but concentrate mutations in actions — else logic isn't reusable/testable.

## Which snippet

| Case | File |
|:---|:---|
| New setup store (state/getters/actions, private field, init from server) | `snippets/useExampleStore.ts` |
| Use store in component: `storeToRefs`, calling actions, hydration in `onMounted` | `snippets/store-in-component.vue` |
| Composition: one store uses another + store access outside component | `snippets/store-composition.ts` |

## Quality checklist

- [ ] `createPinia()` created and `app.use(pinia)` called once (server — per request)
- [ ] Store is setup form `defineStore('id', () => {...})`, not option form
- [ ] `ref`=state, `computed`=getters, `function`=actions; all public in `return`
- [ ] Name `use<Domain>Store`, stable string `id`; one store = one domain
- [ ] In component state/getters via `storeToRefs`, mutations via actions
- [ ] Outside component `useXxxStore()` called inside a function, not at module top level
- [ ] Server initial state seeded via `init/setX`, not overwritten by a refetch
- [ ] `persist` enabled only where state must survive reload
- [ ] No mutual cycles between stores in composition

## Links

- https://pinia.vuejs.org/core-concepts/ (setup stores, getters, actions)
- https://pinia.vuejs.org/cookbook/composing-stores.html
- https://pinia.vuejs.org/ssr/ (hydration, per-request instance)
- https://prazdevs.github.io/pinia-plugin-persistedstate/
- Related skills: `frontend-vue/vue-composition-api` (local component state), `frontend-backend/inertia-vue` (where `stores/` sits in layered `resources/js`), `frontend-backend/laravel-echo-client` (live store updates via realtime events)

<!-- ru-source-sha256: 962f03ef79fd5003c371afb0e4bb744d9ac15a18301d41a8c3135e1ee993d968 -->
