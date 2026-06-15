<!-- Source: anonymized production project -->

# Доменный срез `features/<домен>/`

Крупный домен (заявка, заказ, документ) не размазывается по глобальным
`components/` / `composables/`, а собирается в один вертикальный срез
`resources/js/features/<домен>/`. Внутри среза — слои с фиксированными ролями
и **однонаправленным графом импортов**.

## Дерево слоя

```
resources/js/features/order/
├── actions/                  # единственный слой, который импортирует @/wayfinder/routes/*
│   ├── orderActions.ts       # тонкие функции-обёртки над wayfinder-роутами + execute()
│   └── index.ts              # реэкспорт публичного API actions-слоя
├── composables/              # use*-функции домена; импортируют ТОЛЬКО ../actions
│   ├── useOrderActions.ts    # связывает actions с состоянием отправки/валидацией
│   ├── useOrderForm.ts       # форма домена (useForm/precognition)
│   ├── useOrderConfirmations.ts
│   ├── useOrderRealtime.ts
│   └── index.ts              # реэкспорт публичного API composables-слоя
├── model/                    # оркестрация уровня страницы: собирает composables в один useShowPage
│   └── useOrderShowPage.ts
└── config/                   # доменные константы, дефолты, карты статусов/вкладок
    └── tabs.ts
```

## Правило границ импортов

Направление зависимостей — строго в одну сторону, снаружи внутрь:

```
Vue-компонент / page  →  composables (или model)  →  actions  →  @/wayfinder/routes/*
```

- **Только `actions/` знает про wayfinder.** Все импорты `@/wayfinder/routes/*`
  живут в `features/<домен>/actions/` и нигде больше.
- **Компоненты и страницы НЕ дёргают wayfinder-роуты напрямую** — они вызывают
  `use*`-функции из `composables/` (или `model/`), а те идут в `actions/`.
- **`composables/` → только `../actions`**, не `@/wayfinder/routes/*` напрямую:
  бизнес-логика отвязана от того, как именно вызывается backend.

Граница не на доверии, а **enforced ESLint flat-config** через
`no-restricted-imports`: паттерн `@/wayfinder/routes/*` запрещён в доменных
Vue-файлах, точечный whitelist выводит из-под правила немногие легаси-файлы.
Конфигурация ESLint flat-config и правило-граница — в скилле
`frontend/js-code-style`.

```js
// eslint.config.cjs — граница импортов для домена order
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
            'В доменных Vue-компонентах используйте actions/composables-слой ' +
            'вместо прямых wayfinder-импортов.',
        }],
      }],
    },
  },
  {
    // точечные исключения для немигрированных файлов
    files: ['resources/js/components/order/OrderForm.vue'],
    rules: { 'no-restricted-imports': 'off' },
  },
];
```

## Слой actions: обёртка над wayfinder

`actions/` — единственное место с импортом `@/wayfinder/routes/*`. Каждая
функция тонкая: строит роут и вызывает общий `execute()`.

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
// features/order/actions/index.ts — публичный API слоя
export { finishOrder, storeOrder } from '@/features/order/actions/orderActions';
```

## Мини-composable: импортирует только actions

Composable связывает actions с состоянием отправки/валидацией. Он **не знает**
ни про wayfinder-роуты, ни про URL — только про функции из `../actions`.

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
// features/order/composables/index.ts — публичный API слоя
export { useOrderActions } from '@/features/order/composables/useOrderActions';
```

Страница/компонент берёт только публичный API среза:

```ts
// pages/Orders/Show.vue (script setup) — никаких @/wayfinder/routes/* здесь
import { useOrderActions } from '@/features/order/composables';
```

## Чеклист среза

- [ ] Импорты `@/wayfinder/routes/*` есть только в `features/<домен>/actions/`.
- [ ] `composables/` импортируют backend-вызовы из `../actions`, не из wayfinder.
- [ ] Компоненты/страницы домена берут только публичный API (`composables`/`model`).
- [ ] Граница закреплена `no-restricted-imports` в ESLint flat-config, не «на словах».
- [ ] Каждый слой реэкспортит публичное API через `index.ts`.
