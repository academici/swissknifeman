---
name: inertia-vue
bucket: frontend-backend
version: 0.3.0
description: "Inertia + Vue in Laravel: pages, forms, navigation and layered resources/js organization (pages, layouts, components, composables, stores, features, events, types, actions/wayfinder)."
risk: write
persona: oss-dev
tags: [inertia, vue, laravel, frontend, architecture, structure]
requires: []
produces_for: []
outputs: []
snippets: [structure.md, composable-example.ts, page-example.vue, feature-structure.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Inertia + Vue development

Apply on any edit under `resources/js/` and for "where does this file go?".

Laravel Boost: versioned Inertia basics (forms, navigation, API) = Boost skill inertia-vue; here = layered resources/js org + project conventions. Package: https://github.com/laravel/boost (skills in `vendor/laravel/boost/.ai/`).

## Algorithm

1. Navigation: only `<Link>` / `router.visit()` — no `<a href>` or `window.location` inside the app.
2. Forms: Inertia form helpers — `useForm` or `<Form>` component (with wayfinder `store.form()`); take errors and submit state from the helper, do not duplicate manually.
3. New file — pick layer per table:

| Layer | What goes in |
|:---|:---|
| `pages/` | Routable Inertia pages; domain subfolders (`Documents/`, `Orders/`) |
| `layouts/` | Page layout components |
| `components/` | Vue components: domain subfolders (`document/`, `order/`) + `shared/` for reusable |
| `composables/` | `use*` functions; domain subfolders + `shared/` |
| `stores/` | Pinia stores |
| `features/` | Feature-specific logic not fitting one composable (domain subfolders) |
| `events/` | Event bus + `adapters/`, `sideEffects/`, `plugins/` |
| `types/` | TS types and declarations |
| `actions/`, `routes/`, `wayfinder/` | Wayfinder autogen — do not edit by hand |
| `shared/` | Cross-domain modules that are not components/composables |
| `utils/` | Pure stateless helper functions |
| `config/` | Frontend config constants |
| `tests/` | Vitest tests, mirror of source structure |

4. Domain org inside layer: inside `components/`, `composables/`, `features/`, `pages/` — subfolders by domain (`document/`, `order/`, `auth/`, `notifications/`); shared → `shared/`.
5. Boundaries: pages and domain components reach backend via composables/actions layer (see skill `frontend-wayfinder/wayfinder`); logic in composables/features, components stay thin.

## Domain slices `features/<domain>/`

Large domain (request, order, document) goes in one vertical slice `resources/js/features/<domain>/`, not global `components/`/`composables/`, with fixed-role layers:

```
features/order/
├── actions/       # единственный слой с импортом @/wayfinder/routes/* (обёртки над роутами + execute())
├── composables/   # use*-функции домена; импортируют ТОЛЬКО ../actions
├── model/         # оркестрация уровня страницы: собирает composables в один useShowPage
└── config/        # доменные константы, дефолты, карты статусов/вкладок
```

Import boundary rule — dependencies strictly one-way, outside → inside:

```
Vue-компонент / page  →  composables (или model)  →  actions  →  @/wayfinder/routes/*
```

1. Only `actions/` knows wayfinder: all `@/wayfinder/routes/*` imports live in `features/<domain>/actions/` and nowhere else.
2. Components and pages do NOT call wayfinder routes directly — they call `use*` from `composables/` (or `model/`), which go to `actions/`.
3. `composables/` import only `../actions`, not `@/wayfinder/routes/*`.
4. Each layer re-exports public API via `index.ts` — only re-exported functions are visible outward.

Boundary is enforced via ESLint flat-config `no-restricted-imports`: pattern `@/wayfinder/routes/*` forbidden in domain Vue files, pointwise whitelist exempts few legacy files. ESLint flat-config setup + boundary rule → skill `frontend-linting/js-code-style`; full slice tree, example domain composable and boundary config → `snippets/feature-structure.md`.

## Which snippet to open

| Situation | File |
|:---|:---|
| "Where does this file go?" — full layer map with example paths | `snippets/structure.md` |
| Write a domain composable (use* function, form, navigation) | `snippets/composable-example.ts` |
| Create a new Inertia page with layout, form and `<Link>` | `snippets/page-example.vue` |
| Set up a domain slice `features/<domain>/` with import boundary | `snippets/feature-structure.md` |

## Quality checklist

- [ ] Navigation via `<Link>`/`router.visit()`, forms via `useForm`/`<Form>`
- [ ] File in correct layer and domain subfolder (table above)
- [ ] `actions/`, `routes/`, `wayfinder/` not hand-edited
- [ ] Logic in composables/features, component thin
- [ ] Shared components/composables in `shared/`, not copied between domains
- [ ] New module's test in mirror subfolder of `tests/`
- [ ] `@/wayfinder/routes/*` imports only in `features/<domain>/actions/`; domain components/composables go via `actions` layer
- [ ] Domain import boundary enforced by `no-restricted-imports` in ESLint flat-config, not "by convention"

## Links

- https://inertiajs.com/
- https://vuejs.org/guide/reusability/composables
- Related skills: `frontend-wayfinder/wayfinder`, `frontend-vue/vitest`, `frontend-vue/vue-composition-api`, `frontend-linting/js-code-style`, `frontend-vue/pinia-stores` (layer `stores/`), `frontend-linting/eslint-flat-config` (enforce import boundary `no-restricted-imports`), `frontend-tailwind/tailwind-conventions`

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: d9cd8f1d1c17651367f223be62a1f7f30a559d93839e181bf888bb01f2e57d25 -->
