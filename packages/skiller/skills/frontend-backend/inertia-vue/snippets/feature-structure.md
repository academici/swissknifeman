<!-- Source: anonymized production project -->

# Domain slice `features/<domain>/`

Large domain (application, order, document) does not spread across global
`components/` / `composables/`, and is assembled into one vertical slice
`resources/js/features/<domain>/`. Inside the slice - layers with fixed roles
and **unidirectional import graph**.

## Layer tree

```
resources/js/features/order/
├── actions/                  # is the only layer that imports @/wayfinder/routes/*
│   ├── orderActions.ts       # thin wrapper functions over wayfinder-routes + execute()
│   └── index.ts              # re-export public API actions-layer
├── composables/              # use*-domain functions; import ONLY../actions
│   ├── useOrderActions.ts    # links actions with sending status/validation
│   ├── useOrderForm.ts       # domain form (useForm/precognition)
│   ├── useOrderConfirmations.ts
│   ├── useOrderRealtime.ts
│   └── index.ts              # re-export public API composables-layer
├── model/                    # page level orchestration: collects composables into one useShowPage
│   └── useOrderShowPage.ts
└── config/                   # domain constants, defaults, status maps/tabs
    └── tabs.ts
```

## Import Boundary Rule

The direction of dependencies is strictly in one direction, from outside to inside:

```
Vue-component / page  →  composables (or model)  →  actions  →  @/wayfinder/routes/*
```

- **Only `actions/` knows about wayfinder.** All imports `@/wayfinder/routes/*`
  live in `features/<domain>/actions/` and nowhere else.
- **Components and pages do NOT jerk wayfinder-routes directly** — they call
  `use*`-functions from `composables/` (or `model/`), and they go to `actions/`.
- **`composables/` → only `../actions`**, not `@/wayfinder/routes/*` directly:
  business logic is decoupled from how exactly it is called backend.

The limit is not on trust, but **enforced ESLint flat-config** via
`no-restricted-imports`: pattern `@/wayfinder/routes/*` is prohibited in domain
Vue-files, dot whitelist excludes a few legacy files from the rule.
Configuration ESLint flat-config and the boundary rule - in the skill
`frontend-linting/js-code-style`.

```js
// eslint.config.cjs — import boundary for domain order
const orderVueFiles = [
  'resources/js/components/order/**/*.vue',
  'resources/js/pages/Orders/**/*.vue',
];

module.exports = [
  // ...
  {
    files: orderVueFiles,
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [{
          group: ['@/wayfinder/routes/*'],
          message:
            'In domain Vue-components use actions/composables-layer ' +
            'instead of straight ones wayfinder-imports.',
        }],
      }],
    },
  },
  {
    // point exceptions for unmigrated files
    files: ['resources/js/components/order/OrderForm.vue'],
    rules: { 'no-restricted-imports': 'off' },
  },
];
```

## Layer actions: wrapper over wayfinder

`actions/` — the only place with import `@/wayfinder/routes/*`. Each
subtle function: builds a route and calls a common one `execute()`.

```ts
// features/order/actions/orderActions.ts
import type { DataPayload } from '@/types/api-client';
import { execute } from '@/utils/api';
import {
    finish as finishRoute,
    store as storeRoute,
} from '@/wayfinder/routes/orders';

type FormProps = Record<string, unknown>;

export function storeOrder(formData: DataPayload, formProps: FormProps = {}): Promise<void> {
    return execute(storeRoute(), formData, formProps);
}

export function finishOrder(orderId: number, result: boolean, comment: string | null): Promise<void> {
    return execute(finishRoute({ order: orderId }), { result, comment });
}
```

```ts
// features/order/actions/index.ts — public API layer
export { finishOrder, storeOrder } from '@/features/order/actions/orderActions';
```

## Minicomposable: imports only actions

Composable links actions with sending status/validation. He **doesn't know**
neither about wayfinder-routes, neither about URL — only about functions from `../actions`.

```ts
// features/order/composables/useOrderActions.ts
import { finishOrder, storeOrder } from '@/features/order/actions';

type RunWithPending = (key: string, request: () => Promise<void>) => Promise<void>;

export function useOrderActions(options: {
    orderId: number;
    getFormData: () => Record<string, unknown>;
    runWithPending: RunWithPending;
}) {
    const { orderId, getFormData, runWithPending } = options;

    function store(): Promise<void> {
        return runWithPending('store', () => storeOrder(getFormData()));
    }

    function finish(result: boolean): Promise<void> {
        return runWithPending('finish', () => {
            const { comment } = getFormData();
            return finishOrder(orderId, result, (comment as string | null) ?? null);
        });
    }

    return { store, finish };
}
```

```ts
// features/order/composables/index.ts — public API layer
export { useOrderActions } from '@/features/order/composables/useOrderActions';
```

Page/component takes only public API slice:

```ts
// pages/Orders/Show.vue (script setup) — none @/wayfinder/routes/* here
import { useOrderActions } from '@/features/order/composables';
```

## Slice checklist

- [ ] Imports `@/wayfinder/routes/*` is only available in `features/<domain>/actions/`.
- [ ] `composables/` import backend-calls from `../actions`, not from wayfinder.
- [ ] Components/domain pages take only public API (`composables`/`model`).
- [ ] The border is fixed `no-restricted-imports` in ESLint flat-config, not «in words».
- [ ] Each layer will re-export the public API via `index.ts`.
