<!-- Source: anonymized production Laravel project -->

# Layer map resources/js (Laravel + Inertia + Vue)

```
resources/js/
├── app.ts                  # entrypoint
├── pages/                  # routeable Inertia-pages
│   ├── Auth/
│   ├── Documents/          #   domain subfolders: List.vue, Show.vue, Edit.vue
│   └── Notifications/
├── layouts/                # layout-components (AppLayout.vue, GuestLayout.vue)
├── components/             # Vue-components
│   ├── document/           #   domain: DocumentTable.vue, DocumentForm.vue
│   ├── order/
│   └── shared/             #   reusable: Button.vue, Modal.vue
├── composables/            # use*-functions
│   ├── document/           #   useDocumentFilters.ts, useDocumentNavigation.ts
│   └── shared/             #   usePagination.ts, useDebounce.ts
├── stores/                 # Pinia-stories (useUserStore.ts)
├── features/               # feature-specific logic is larger composable
│   └── document/           #   export, wizards, multi-step scripts
├── events/                 # event bus
│   ├── adapters/           #   connecting transports (websocket etc.)
│   ├── sideEffects/        #   reactions to events (toasts, invalidation)
│   └── plugins/
├── types/                  # TS-types, .d.ts
├── actions/                # AUTOGENE Wayfinder (controller actions) — do not edit
├── routes/                 # AUTOGENE Wayfinder (named routes) — do not edit
├── wayfinder/              # AUTOGENE Wayfinder (internals) — do not edit
├── shared/                 # cross-domain modules (are not components or composables)
├── utils/                  # pure stateless functions (formatDate.ts)
├── config/                 # frontend constants
└── tests/                  # Vitest, structure mirror:
    ├── components/document/
    ├── composables/document/
    └── events/
```

## What do we put where?

| I would like to add | Layer | Example path |
|:---|:---|:---|
| New page with your URL | `pages/<Domain>/` | `pages/Documents/Show.vue` |
| Page wrapper (hat/sidebar) | `layouts/` | `layouts/AppLayout.vue` |
| Single Domain Component | `components/<domain>/` | `components/document/DocumentTable.vue` |
| Component for all domains | `components/shared/` | `components/shared/ConfirmModal.vue` |
| Reusable reactive logic | `composables/<domain or shared>/` | `composables/document/useDocumentFilters.ts` |
| Global state | `stores/` | `stores/useUserStore.ts` |
| Multi-step script / major feature | `features/<domain>/` | `features/document/export/` |
| Reaction to bus event | `events/sideEffects/` | `events/sideEffects/showToastOnDocumentSaved.ts` |
| Type/interface | `types/` | `types/document.ts` |
| Stateless helper function | `utils/` | `utils/formatDate.ts` |
| Test | `tests/` (mirror) | `tests/composables/document/useDocumentFilters.test.ts` |

## Rules

- Domain subfolders within each layer; general - `shared/`.
- `actions/`, `routes/`, `wayfinder/` are generated `php artisan wayfinder:generate` / vite-plugin - any manual edits will be overwritten.
- Domain components are not imported `@/wayfinder/routes/*` directly - via composables/actions (see skill `frontend-wayfinder/wayfinder`).
