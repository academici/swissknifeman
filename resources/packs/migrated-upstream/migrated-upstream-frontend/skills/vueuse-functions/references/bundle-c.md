<!-- source: references/computedAsync.md -->
---
category: Reactivity
alias: asyncComputed
---

# computedAsync

Computed for async functions.

## Usage

```ts
import { computedAsync } from '@vueuse/core'
import { shallowRef } from 'vue'

const name = shallowRef('jack')

const userInfo = computedAsync(
  async () => {
    return await mockLookUp(name.value)
  },
  null, // initial state
)
```

### Evaluation State

Pass a ref to track if the async function is currently evaluating.

```ts
import { computedAsync } from '@vueuse/core'
import { shallowRef } from 'vue'

const evaluating = shallowRef(false)

const userInfo = computedAsync(
  async () => { /* your logic */ },
  null,
  evaluating, // can also be passed via options: { evaluating }
)
```

### onCancel

When the computed source changes before the previous async function resolves, you may want to cancel the previous one. Here is an example showing how to incorporate with the fetch API.

```ts
import { computedAsync } from '@vueuse/core'
import { shallowRef } from 'vue'

const packageName = shallowRef('@vueuse/core')

const downloads = computedAsync(async (onCancel) => {
  const abortController = new AbortController()

  onCancel(() => abortController.abort())

  return await fetch(
    `https://api.npmjs.org/downloads/point/last-week/${packageName.value}`,
    { signal: abortController.signal },
  )
    .then(response => response.ok ? response.json() : { downloads: '—' })
    .then(result => result.downloads)
}, 0)
```

### Lazy

By default, `computedAsync` will start resolving immediately on creation. Specify `lazy: true` to make it start resolving on the first access.

```ts
import { computedAsync } from '@vueuse/core'
import { shallowRef } from 'vue'

const evaluating = shallowRef(false)

const userInfo = computedAsync(
  async () => { /* your logic */ },
  null,
  { lazy: true, evaluating },
)
```

### Error Handling

Use the `onError` callback to handle errors from the async function.

```ts
import { computedAsync } from '@vueuse/core'
import { shallowRef } from 'vue'

const name = shallowRef('jack')

const userInfo = computedAsync(
  async () => {
    return await mockLookUp(name.value)
  },
  null,
  {
    onError(e) {
      console.error('Failed to fetch user info', e)
    },
  },
)
```

### Shallow Ref

By default, `computedAsync` uses `shallowRef` internally. Set `shallow: false` to use a deep ref instead.

```ts
import { computedAsync } from '@vueuse/core'
import { shallowRef } from 'vue'

const name = shallowRef('jack')

const userInfo = computedAsync(
  async () => {
    return await fetchNestedData(name.value)
  },
  null,
  { shallow: false }, // enables deep reactivity
)
```

## Caveats

- Just like Vue's built-in `computed` function, `computedAsync` does dependency tracking and is automatically re-evaluated when dependencies change. Note however that only dependencies referenced in the first call stack are considered for this. In other words: **Dependencies that are accessed asynchronously will not trigger re-evaluation of the async computed value.**

- As opposed to Vue's built-in `computed` function, re-evaluation of the async computed value is triggered whenever dependencies are changing, regardless of whether its result is currently being tracked or not.

## Type Declarations

```ts
/**
 * Handle overlapping async evaluations.
 *
 * @param cancelCallback The provided callback is invoked when a re-evaluation of the computed value is triggered before the previous one finished
 */
export type AsyncComputedOnCancel = (cancelCallback: Fn) => void
export interface AsyncComputedOptions<
  Lazy = boolean,
> extends ConfigurableFlushSync {
  /**
   * Should value be evaluated lazily
   *
   * @default false
   */
  lazy?: Lazy
  /**
   * Ref passed to receive the updated of async evaluation
   */
  evaluating?: Ref<boolean>
  /**
   * Use shallowRef
   *
   * @default true
   */
  shallow?: boolean
  /**
   * Callback when error is caught.
   */
  onError?: (e: unknown) => void
}
/**
 * Create an asynchronous computed dependency.
 *
 * @see https://vueuse.org/computedAsync
 * @param evaluationCallback     The promise-returning callback which generates the computed value
 * @param initialState           The initial state, used until the first evaluation finishes
 * @param optionsOrRef           Additional options or a ref passed to receive the updates of the async evaluation
 */
export declare function computedAsync<T>(
  evaluationCallback: (onCancel: AsyncComputedOnCancel) => T | Promise<T>,
  initialState: T,
  optionsOrRef: AsyncComputedOptions<true>,
): ComputedRef<T>
export declare function computedAsync<T>(
  evaluationCallback: (onCancel: AsyncComputedOnCancel) => T | Promise<T>,
  initialState: undefined,
  optionsOrRef: AsyncComputedOptions<true>,
): ComputedRef<T | undefined>
export declare function computedAsync<T>(
  evaluationCallback: (onCancel: AsyncComputedOnCancel) => T | Promise<T>,
  initialState: T,
  optionsOrRef?: Ref<boolean> | AsyncComputedOptions,
): Ref<T>
export declare function computedAsync<T>(
  evaluationCallback: (onCancel: AsyncComputedOnCancel) => T | Promise<T>,
  initialState?: undefined,
  optionsOrRef?: Ref<boolean> | AsyncComputedOptions,
): Ref<T | undefined>
/** @deprecated use `computedAsync` instead */
export declare const asyncComputed: typeof computedAsync
```

---

<!-- source: references/computedEager.md -->
---
category: Reactivity
alias: eagerComputed
---

# computedEager

Eager computed without lazy evaluation.

::: info
This function will be removed in future version.
:::

::: tip
Note💡: If you are using Vue 3.4+, you can use `computed` right away, you no longer need this function.
In Vue 3.4+, if the computed new value does not change, `computed`, `effect`, `watch`, `watchEffect`, `render` dependencies will not be triggered.
See: https://github.com/vuejs/core/pull/5912
:::

Learn more at [Vue: When a computed property can be the wrong tool](https://dev.to/linusborg/vue-when-a-computed-property-can-be-the-wrong-tool-195j).

- Use `computed()` when you have a complex calculation going on, which can actually profit from caching and lazy evaluation and should only be (re-)calculated if really necessary.
- Use `computedEager()` when you have a simple operation, with a rarely changing return value – often a boolean.

## Usage

```ts
import { computedEager } from '@vueuse/core'

const todos = ref([])
const hasOpenTodos = computedEager(() => !!todos.length)

console.log(hasOpenTodos.value) // false
toTodos.value.push({ title: 'Learn Vue' })
console.log(hasOpenTodos.value) // true
```

## Type Declarations

```ts
export type ComputedEagerOptions = WatchOptionsBase
export type ComputedEagerReturn<T = any> = Readonly<ShallowRef<T>>
/**
 *
 * @deprecated This function will be removed in future version.
 *
 * Note: If you are using Vue 3.4+, you can straight use computed instead.
 * Because in Vue 3.4+, if computed new value does not change,
 * computed, effect, watch, watchEffect, render dependencies will not be triggered.
 * refer: https://github.com/vuejs/core/pull/5912
 *
 * @param fn effect function
 * @param options WatchOptionsBase
 * @returns readonly shallowRef
 */
export declare function computedEager<T>(
  fn: () => T,
  options?: ComputedEagerOptions,
): ComputedEagerReturn<T>
/** @deprecated use `computedEager` instead */
export declare const eagerComputed: typeof computedEager
```

---

<!-- source: references/computedInject.md -->
---
category: Component
---

# computedInject

Combine `computed` and `inject`. Useful for creating a computed property based on an injected value.

## Usage

In Provider Component

```ts twoslash include main
import type { InjectionKey, Ref } from 'vue'
import { provide, ref } from 'vue'

interface Item {
  key: number
  value: string
}

export const ArrayKey: InjectionKey<Ref<Item[]>> = Symbol('symbol-key')

const array = ref([{ key: 1, value: '1' }, { key: 2, value: '2' }, { key: 3, value: '3' }])

provide(ArrayKey, array)
```

In Receiver Component

```ts
// @filename: provider.ts
// @include: main
// ---cut---
import { computedInject } from '@vueuse/core'

import { ArrayKey } from './provider'

const computedArray = computedInject(ArrayKey, (source) => {
  const arr = [...source.value]
  arr.unshift({ key: 0, value: 'all' })
  return arr
})
```

### Default Value

You can provide a default value that will be used if the injection key is not provided by a parent component.

```ts
import { computedInject } from '@vueuse/core'

const computedArray = computedInject(
  ArrayKey,
  (source) => {
    return source.value.map(item => item.value)
  },
  ref([]), // default source value
)
```

### Factory Default

Pass `true` as the fourth argument to treat the default value as a factory function.

```ts
import { computedInject } from '@vueuse/core'

const computedArray = computedInject(
  ArrayKey,
  (source) => {
    return source.value.map(item => item.value)
  },
  () => ref([]), // factory function for default
  true, // treat default as factory
)
```

### Writable Computed

You can also create a writable computed property by passing an object with `get` and `set` functions.

```ts
import { computedInject } from '@vueuse/core'

const computedArray = computedInject(ArrayKey, {
  get(source) {
    return source.value.map(item => item.value)
  },
  set(value) {
    // handle setting the value
    console.log('Setting value:', value)
  },
})
```

## Type Declarations

```ts
export type ComputedInjectGetter<T, K> = (
  source: T | undefined,
  oldValue?: K,
) => K
export type ComputedInjectGetterWithDefault<T, K> = (
  source: T,
  oldValue?: K,
) => K
export type ComputedInjectSetter<T> = (v: T) => void
export interface WritableComputedInjectOptions<T, K> {
  get: ComputedInjectGetter<T, K>
  set: ComputedInjectSetter<K>
}
export interface WritableComputedInjectOptionsWithDefault<T, K> {
  get: ComputedInjectGetterWithDefault<T, K>
  set: ComputedInjectSetter<K>
}
export declare function computedInject<T, K = any>(
  key: InjectionKey<T> | string,
  getter: ComputedInjectGetter<T, K>,
): ComputedRef<K | undefined>
export declare function computedInject<T, K = any>(
  key: InjectionKey<T> | string,
  options: WritableComputedInjectOptions<T, K>,
): ComputedRef<K | undefined>
export declare function computedInject<T, K = any>(
  key: InjectionKey<T> | string,
  getter: ComputedInjectGetterWithDefault<T, K>,
  defaultSource: T,
  treatDefaultAsFactory?: false,
): ComputedRef<K>
export declare function computedInject<T, K = any>(
  key: InjectionKey<T> | string,
  options: WritableComputedInjectOptionsWithDefault<T, K>,
  defaultSource: T | (() => T),
  treatDefaultAsFactory: true,
): ComputedRef<K>
```

---

<!-- source: references/computedWithControl.md -->
---
category: Reactivity
alias: controlledComputed
---

# computedWithControl

Explicitly define the dependencies of computed.

## Usage

```ts twoslash include main
import { computedWithControl } from '@vueuse/core'

const source = ref('foo')
const counter = ref(0)

const computedRef = computedWithControl(
  () => source.value, // watch source, same as `watch`
  () => counter.value, // computed getter, same as `computed`
)
```

With this, the changes of `counter` won't trigger `computedRef` to update but the `source` ref does.

```ts
// @include: main
// ---cut---
console.log(computedRef.value) // 0

counter.value += 1

console.log(computedRef.value) // 0

source.value = 'bar'

console.log(computedRef.value) // 1
```

### Manual Triggering

You can also manually trigger the update of the computed by:

```ts
// @include: main
// ---cut---
const computedRef = computedWithControl(
  () => source.value,
  () => counter.value,
)

computedRef.trigger()
```

### Deep Watch

Unlike `computed`, `computedWithControl` is shallow by default.
You can specify the same options as `watch` to control the behavior:

```ts
const source = ref({ name: 'foo' })

const computedRef = computedWithControl(
  source,
  () => counter.value,
  { deep: true },
)
```

## Type Declarations

```ts
export interface ComputedWithControlRefExtra {
  /**
   * Force update the computed value.
   */
  trigger: () => void
}
export interface ComputedRefWithControl<T>
  extends ComputedRef<T>, ComputedWithControlRefExtra {}
export interface WritableComputedRefWithControl<T>
  extends WritableComputedRef<T>, ComputedWithControlRefExtra {}
export type ComputedWithControlRef<T = any> =
  | ComputedRefWithControl<T>
  | WritableComputedRefWithControl<T>
export declare function computedWithControl<T>(
  source: WatchSource | MultiWatchSources,
  fn: ComputedGetter<T>,
  options?: WatchOptions,
): ComputedRefWithControl<T>
export declare function computedWithControl<T>(
  source: WatchSource | MultiWatchSources,
  fn: WritableComputedOptions<T>,
  options?: WatchOptions,
): WritableComputedRefWithControl<T>
/** @deprecated use `computedWithControl` instead */
export declare const controlledComputed: typeof computedWithControl
```

---

<!-- source: references/createEventHook.md -->
---
category: Utilities
---

# createEventHook

Utility for creating event hooks

## Usage

Creating a function that uses `createEventHook`

```ts
import { createEventHook } from '@vueuse/core'

export function useMyFetch(url) {
  const fetchResult = createEventHook<Response>()
  const fetchError = createEventHook<any>()

  fetch(url)
    .then(result => fetchResult.trigger(result))
    .catch(error => fetchError.trigger(error.message))

  return {
    onResult: fetchResult.on,
    onError: fetchError.on,
  }
}
```

Using a function that uses `createEventHook`

```vue
<script setup lang="ts">
import { useMyFetch } from './my-fetch-function'

const { onResult, onError } = useMyFetch('my api url')

onResult((result) => {
  console.log(result)
})

onError((error) => {
  console.error(error)
})
</script>
```

## Type Declarations

```ts
/**
 * The source code for this function was inspired by vue-apollo's `useEventHook` util
 * https://github.com/vuejs/vue-apollo/blob/v4/packages/vue-apollo-composable/src/util/useEventHook.ts
 */
type Callback<T> =
  IsAny<T> extends true
    ? (...param: any) => void
    : [T] extends [void]
      ? (...param: unknown[]) => void
      : [T] extends [any[]]
        ? (...param: T) => void
        : (...param: [T, ...unknown[]]) => void
export type EventHookOn<T = any> = (fn: Callback<T>) => {
  off: () => void
}
export type EventHookOff<T = any> = (fn: Callback<T>) => void
export type EventHookTrigger<T = any> = (
  ...param: Parameters<Callback<T>>
) => Promise<unknown[]>
export interface EventHook<T = any> {
  on: EventHookOn<T>
  off: EventHookOff<T>
  trigger: EventHookTrigger<T>
  clear: () => void
}
export type EventHookReturn<T> = EventHook<T>
/**
 * Utility for creating event hooks
 *
 * @see https://vueuse.org/createEventHook
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createEventHook<T = any>(): EventHookReturn<T>
```

---

<!-- source: references/createGenericProjection.md -->
---
category: '@Math'
---

# createGenericProjection

Generic version of `createProjection`. Accepts a custom projector function to map arbitrary type of domains.

Refer to `createProjection` and `useProjection`

## Type Declarations

```ts
export type ProjectorFunction<F, T> = (
  input: F,
  from: readonly [F, F],
  to: readonly [T, T],
) => T
export type UseProjection<F, T> = (input: MaybeRefOrGetter<F>) => ComputedRef<T>
export declare function createGenericProjection<F = number, T = number>(
  fromDomain: MaybeRefOrGetter<readonly [F, F]>,
  toDomain: MaybeRefOrGetter<readonly [T, T]>,
  projector: ProjectorFunction<F, T>,
): UseProjection<F, T>
```

---

<!-- source: references/createGlobalState.md -->
---
category: State
related: createSharedComposable
---

# createGlobalState

Keep states in the global scope to be reusable across Vue instances.

## Usage

### Without Persistence (Store in Memory)

```ts
// store.ts
import { createGlobalState } from '@vueuse/core'
import { shallowRef } from 'vue'

export const useGlobalState = createGlobalState(
  () => {
    const count = shallowRef(0)
    return { count }
  }
)
```

A bigger example:

```ts
// store.ts
import { createGlobalState } from '@vueuse/core'
import { computed, shallowRef } from 'vue'

export const useGlobalState = createGlobalState(
  () => {
    // state
    const count = shallowRef(0)

    // getters
    const doubleCount = computed(() => count.value * 2)

    // actions
    function increment() {
      count.value++
    }

    return { count, doubleCount, increment }
  }
)
```

### With Persistence

Store in `localStorage` with `useStorage`:

```ts twoslash include store
// store.ts
import { createGlobalState, useStorage } from '@vueuse/core'

export const useGlobalState = createGlobalState(
  () => useStorage('vueuse-local-storage', 'initialValue'),
)
```

```ts
// @filename: store.ts
// @include: store
// ---cut---
// component.ts
import { useGlobalState } from './store'

export default defineComponent({
  setup() {
    const state = useGlobalState()
    return { state }
  },
})
```

## Type Declarations

```ts
export type CreateGlobalStateReturn<Fn extends AnyFn = AnyFn> = Fn
/**
 * Keep states in the global scope to be reusable across Vue instances.
 *
 * @see https://vueuse.org/createGlobalState
 * @param stateFactory A factory function to create the state
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createGlobalState<Fn extends AnyFn>(
  stateFactory: Fn,
): CreateGlobalStateReturn<Fn>
```

---

<!-- source: references/createInjectionState.md -->
---
category: State
---

# createInjectionState

Create global state that can be injected into components.

## Usage

```ts twoslash include useCounterStore
// useCounterStore.ts
import { createInjectionState } from '@vueuse/core'
import { computed, shallowRef } from 'vue'

const [useProvideCounterStore, useCounterStore] = createInjectionState((initialValue: number) => {
  // state
  const count = shallowRef(initialValue)

  // getters
  const double = computed(() => count.value * 2)

  // actions
  function increment() {
    count.value++
  }

  return { count, double, increment }
})

export { useProvideCounterStore }

// If you want to hide `useCounterStore` and wrap it in default value logic or throw error logic, please don't export `useCounterStore`
export { useCounterStore }

export function useCounterStoreWithDefaultValue() {
  return useCounterStore() ?? {
    count: shallowRef(0),
    double: shallowRef(0),
    increment: () => {},
  }
}

export function useCounterStoreOrThrow() {
  const counterStore = useCounterStore()
  if (counterStore == null)
    throw new Error('Please call `useProvideCounterStore` on the appropriate parent component')
  return counterStore
}
```

```vue
<!-- RootComponent.vue -->
<script setup lang="ts">
// @filename: useCounterStore.ts
// @include: useCounterStore
// ---cut---
import { useProvideCounterStore } from './useCounterStore'

useProvideCounterStore(0)
</script>

<template>
  <div>
    <slot />
  </div>
</template>
```

```vue
<!-- CountComponent.vue -->
<script setup lang="ts">
// @filename: useCounterStore.ts
// @include: useCounterStore
// ---cut---
import { useCounterStore } from './useCounterStore'

// use non-null assertion operator to ignore the case that store is not provided.
const { count, double } = useCounterStore()!
// if you want to allow component to working without providing store, you can use follow code instead:
// const { count, double } = useCounterStore() ?? { count: shallowRef(0), double: shallowRef(0) }
// also, you can use another hook to provide default value
// const { count, double } = useCounterStoreWithDefaultValue()
// or throw error
// const { count, double } = useCounterStoreOrThrow()
</script>

<template>
  <ul>
    <li>
      count: {{ count }}
    </li>
    <li>
      double: {{ double }}
    </li>
  </ul>
</template>
```

```vue
<!-- ButtonComponent.vue -->
<script setup lang="ts">
// @filename: useCounterStore.ts
// @include: useCounterStore
// ---cut---
import { useCounterStore } from './useCounterStore'

// use non-null assertion operator to ignore the case that store is not provided.
const { increment } = useCounterStore()!
</script>

<template>
  <button @click="increment">
    +
  </button>
</template>
```

## Provide a custom InjectionKey

```ts
// useCounterStore.ts
import { createInjectionState } from '@vueuse/core'
import { computed, shallowRef } from 'vue'

// custom injectionKey
const CounterStoreKey = 'counter-store'

const [useProvideCounterStore, useCounterStore] = createInjectionState((initialValue: number) => {
  // state
  const count = shallowRef(initialValue)

  // getters
  const double = computed(() => count.value * 2)

  // actions
  function increment() {
    count.value++
  }

  return { count, double, increment }
}, { injectionKey: CounterStoreKey })
```

## Provide a custom default value

```ts
// useCounterStore.ts
import { createInjectionState } from '@vueuse/core'
import { computed, shallowRef } from 'vue'

const [useProvideCounterStore, useCounterStore] = createInjectionState((initialValue: number) => {
  // state
  const count = shallowRef(initialValue)

  // getters
  const double = computed(() => count.value * 2)

  // actions
  function increment() {
    count.value++
  }

  return { count, double, increment }
}, { defaultValue: 0 })
```

## Type Declarations

```ts
export type CreateInjectionStateReturn<
  Arguments extends Array<any>,
  Return,
> = Readonly<
  [
    /**
     * Call this function in a provider component to create and provide the state.
     *
     * @param args Arguments passed to the composable
     * @returns The state returned by the composable
     */
    useProvidingState: (...args: Arguments) => Return,
    /**
     * Call this function in a consumer component to inject the state.
     *
     * @returns The injected state, or `undefined` if not provided and no default value was set.
     */
    useInjectedState: () => Return | undefined,
  ]
>
export interface CreateInjectionStateOptions<Return> {
  /**
   * Custom injectionKey for InjectionState
   */
  injectionKey?: string | InjectionKey<Return>
  /**
   * Default value for the InjectionState
   */
  defaultValue?: Return
}
/**
 * Create global state that can be injected into components.
 *
 * @see https://vueuse.org/createInjectionState
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createInjectionState<
  Arguments extends Array<any>,
  Return,
>(
  composable: (...args: Arguments) => Return,
  options?: CreateInjectionStateOptions<Return>,
): CreateInjectionStateReturn<Arguments, Return>
```

---

<!-- source: references/createProjection.md -->
---
category: '@Math'
related: useProjection, createGenericProjection
---

# createProjection

Reactive numeric projection from one domain to another.

## Usage

```ts
import { createProjection } from '@vueuse/math'

const useProjector = createProjection([0, 10], [0, 100])
const input = ref(0)
const projected = useProjector(input) // projected.value === 0

input.value = 5 // projected.value === 50
input.value = 10 // projected.value === 100
```

## Type Declarations

```ts
export declare function createProjection(
  fromDomain: MaybeRefOrGetter<readonly [number, number]>,
  toDomain: MaybeRefOrGetter<readonly [number, number]>,
  projector?: ProjectorFunction<number, number>,
): UseProjection<number, number>
```

---

<!-- source: references/createRef.md -->
---
category: Reactivity
---

# createRef

Returns a `deepRef` or `shallowRef` depending on the `deep` param.

## Usage

```ts
import { createRef } from '@vueuse/core'
import { isShallow, ref } from 'vue'

const initialData = 1

const shallowData = createRef(initialData)
const deepData = createRef(initialData, true)

isShallow(shallowData) // true
isShallow(deepData) // false
```

## Type Declarations

```ts
export type CreateRefReturn<
  T = any,
  D extends boolean = false,
> = ShallowOrDeepRef<T, D>
export type ShallowOrDeepRef<
  T = any,
  D extends boolean = false,
> = D extends true ? Ref<T> : ShallowRef<T>
/**
 * Returns a `deepRef` or `shallowRef` depending on the `deep` param.
 *
 * @example createRef(1) // ShallowRef<number>
 * @example createRef(1, false) // ShallowRef<number>
 * @example createRef(1, true) // Ref<number>
 * @example createRef("string") // ShallowRef<string>
 * @example createRef<"A"|"B">("A", true) // Ref<"A"|"B">
 *
 * @param value
 * @param deep
 * @returns the `deepRef` or `shallowRef`
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createRef<T = any, D extends boolean = false>(
  value: T,
  deep?: D,
): CreateRefReturn<T, D>
```

---

<!-- source: references/createReusableTemplate.md -->
---
category: Component
outline: deep
---

# createReusableTemplate

Define and reuse template inside the component scope.

## Motivation

It's common to have the need to reuse some part of the template. For example:

```vue
<template>
  <dialog v-if="showInDialog">
    <!-- something complex -->
  </dialog>
  <div v-else>
    <!-- something complex -->
  </div>
</template>
```

We'd like to reuse our code as much as possible. So normally we might need to extract those duplicated parts into a component. However, in a separated component you lose the ability to access the local bindings. Defining props and emits for them can be tedious sometimes.

So this function is made to provide a way for defining and reusing templates inside the component scope.

## Usage

In the previous example, we could refactor it to:

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate()
</script>

<template>
  <DefineTemplate>
    <!-- something complex -->
  </DefineTemplate>

  <dialog v-if="showInDialog">
    <ReuseTemplate />
  </dialog>
  <div v-else>
    <ReuseTemplate />
  </div>
</template>
```

- `<DefineTemplate>` will register the template and renders nothing.
- `<ReuseTemplate>` will render the template provided by `<DefineTemplate>`.
- `<DefineTemplate>` must be used before `<ReuseTemplate>`.

> **Note**: It's recommended to extract as separate components whenever possible. Abusing this function might lead to bad practices for your codebase.

### Options API

When using with [Options API](https://vuejs.org/guide/introduction.html#api-styles), you will need to define `createReusableTemplate` outside of the component setup and pass to the `components` option in order to use them in the template.

```vue
<script>
import { createReusableTemplate } from '@vueuse/core'
import { defineComponent } from 'vue'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate()

export default defineComponent({
  components: {
    DefineTemplate,
    ReuseTemplate,
  },
  setup() {
    // ...
  },
})
</script>

<template>
  <DefineTemplate v-slot="{ data, msg, anything }">
    <div>{{ data }} passed from usage</div>
  </DefineTemplate>

  <ReuseTemplate :data="data" msg="The first usage" />
</template>
```

### Passing Data

You can also pass data to the template using slots:

- Use `v-slot="..."` to access the data on `<DefineTemplate>`
- Directly bind the data on `<ReuseTemplate>` to pass them to the template

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate()
</script>

<template>
  <DefineTemplate v-slot="{ data, msg, anything }">
    <div>{{ data }} passed from usage</div>
  </DefineTemplate>

  <ReuseTemplate :data="data" msg="The first usage" />
  <ReuseTemplate :data="anotherData" msg="The second usage" />
  <ReuseTemplate v-bind="{ data: something, msg: 'The third' }" />
</template>
```

### TypeScript Support

`createReusableTemplate` accepts a generic type to provide type support for the data passed to the template:

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

// Comes with pair of `DefineTemplate` and `ReuseTemplate`
const [DefineFoo, ReuseFoo] = createReusableTemplate<{ msg: string }>()

// You can create multiple reusable templates
const [DefineBar, ReuseBar] = createReusableTemplate<{ items: string[] }>()
</script>

<template>
  <DefineFoo v-slot="{ msg }">
    <!-- `msg` is typed as `string` -->
    <div>Hello {{ msg.toUpperCase() }}</div>
  </DefineFoo>

  <ReuseFoo msg="World" />

  <!-- @ts-expect-error Type Error! -->
  <ReuseFoo :msg="1" />
</template>
```

Optionally, if you are not a fan of array destructuring, the following usages are also legal:

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

const { define: DefineFoo, reuse: ReuseFoo } = createReusableTemplate<{
  msg: string
}>()
</script>

<template>
  <DefineFoo v-slot="{ msg }">
    <div>Hello {{ msg.toUpperCase() }}</div>
  </DefineFoo>

  <ReuseFoo msg="World" />
</template>
```

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

const TemplateFoo = createReusableTemplate<{ msg: string }>()
</script>

<template>
  <TemplateFoo.define v-slot="{ msg }">
    <div>Hello {{ msg.toUpperCase() }}</div>
  </TemplateFoo.define>

  <TemplateFoo.reuse msg="World" />
</template>
```

::: warning
Passing boolean props without `v-bind` is not supported. See the [Caveats](#boolean-props) section for more details.
:::

### Props and Attributes

By default, all props and attributes passed to `<ReuseTemplate>` will be passed to the template. If you don't want certain props to be passed to the DOM, you need to define the runtime props:

```ts
import { createReusableTemplate } from '@vueuse/core'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate({
  props: {
    msg: String,
    enable: Boolean,
  }
})
```

If you don't want to pass any props to the template, you can pass the `inheritAttrs` option:

```ts
import { createReusableTemplate } from '@vueuse/core'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate({
  inheritAttrs: false,
})
```

### Passing Slots

It's also possible to pass slots back from `<ReuseTemplate>`. You can access the slots on `<DefineTemplate>` from `$slots`:

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate()
</script>

<template>
  <DefineTemplate v-slot="{ $slots, otherProp }">
    <div some-layout>
      <!-- To render the slot -->
      <component :is="$slots.default" />
    </div>
  </DefineTemplate>

  <ReuseTemplate>
    <div>Some content</div>
  </ReuseTemplate>
  <ReuseTemplate>
    <div>Another content</div>
  </ReuseTemplate>
</template>
```

## Caveats

### Boolean props

As opposed to Vue's behavior, props defined as `boolean` that were passed without `v-bind` or absent will be resolved into an empty string or `undefined` respectively:

```vue
<script setup lang="ts">
import { createReusableTemplate } from '@vueuse/core'

const [DefineTemplate, ReuseTemplate] = createReusableTemplate<{
  value?: boolean
}>()
</script>

<template>
  <DefineTemplate v-slot="{ value }">
    {{ typeof value }}: {{ value }}
  </DefineTemplate>

  <ReuseTemplate :value="true" />
  <!-- boolean: true -->

  <ReuseTemplate :value="false" />
  <!-- boolean: false -->

  <ReuseTemplate value />
  <!-- string: -->

  <ReuseTemplate />
  <!-- undefined: -->
</template>
```

## References

This function is migrated from [vue-reuse-template](https://github.com/antfu/vue-reuse-template).

Existing Vue discussions/issues about reusing template:

- [Discussion on Reusing Templates](https://github.com/vuejs/core/discussions/6898)

Alternative Approaches:

- [Vue Macros - `namedTemplate`](https://vue-macros.sxzz.moe/features/named-template.html)
- [`unplugin-vue-reuse-template`](https://github.com/liulinboyi/unplugin-vue-reuse-template)

## Type Declarations

```ts
type ObjectLiteralWithPotentialObjectLiterals = Record<
  string,
  Record<string, any> | undefined
>
type GenerateSlotsFromSlotMap<
  T extends ObjectLiteralWithPotentialObjectLiterals,
> = {
  [K in keyof T]: Slot<T[K]>
}
export type DefineTemplateComponent<
  Bindings extends Record<string, any>,
  MapSlotNameToSlotProps extends ObjectLiteralWithPotentialObjectLiterals,
> = DefineComponent & {
  new (): {
    $slots: {
      default: (
        _: Bindings & {
          $slots: GenerateSlotsFromSlotMap<MapSlotNameToSlotProps>
        },
      ) => any
    }
  }
}
export type ReuseTemplateComponent<
  Bindings extends Record<string, any>,
  MapSlotNameToSlotProps extends ObjectLiteralWithPotentialObjectLiterals,
> = DefineComponent<Bindings> & {
  new (): {
    $slots: GenerateSlotsFromSlotMap<MapSlotNameToSlotProps>
  }
}
export type ReusableTemplatePair<
  Bindings extends Record<string, any>,
  MapSlotNameToSlotProps extends ObjectLiteralWithPotentialObjectLiterals,
> = [
  DefineTemplateComponent<Bindings, MapSlotNameToSlotProps>,
  ReuseTemplateComponent<Bindings, MapSlotNameToSlotProps>,
] & {
  define: DefineTemplateComponent<Bindings, MapSlotNameToSlotProps>
  reuse: ReuseTemplateComponent<Bindings, MapSlotNameToSlotProps>
}
export interface CreateReusableTemplateOptions<
  Props extends Record<string, any>,
> {
  /**
   * Inherit attrs from reuse component.
   *
   * @default true
   */
  inheritAttrs?: boolean
  /**
   * Props definition for reuse component.
   */
  props?: ComponentObjectPropsOptions<Props>
}
/**
 * This function creates `define` and `reuse` components in pair,
 * It also allow to pass a generic to bind with type.
 *
 * @see https://vueuse.org/createReusableTemplate
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createReusableTemplate<
  Bindings extends Record<string, any>,
  MapSlotNameToSlotProps extends ObjectLiteralWithPotentialObjectLiterals =
    Record<"default", undefined>,
>(
  options?: CreateReusableTemplateOptions<Bindings>,
): ReusableTemplatePair<Bindings, MapSlotNameToSlotProps>
```

---

<!-- source: references/createSharedComposable.md -->
---
category: State
related: createGlobalState
---

# createSharedComposable

Make a composable function usable with multiple Vue instances.

> [!WARNING]
> When used in a **SSR** environment, `createSharedComposable` will **automatically fallback** to a non-shared version.
> This means every call will create a fresh instance in SSR to avoid [cross-request state pollution](https://vuejs.org/guide/scaling-up/ssr.html#cross-request-state-pollution).

## Usage

```ts
import { createSharedComposable, useMouse } from '@vueuse/core'

const useSharedMouse = createSharedComposable(useMouse)

// CompA.vue
const { x, y } = useSharedMouse()

// CompB.vue - will reuse the previous state and no new event listeners will be registered
const { x, y } = useSharedMouse()
```

## Type Declarations

```ts
export type SharedComposableReturn<T extends AnyFn = AnyFn> = T
/**
 * Make a composable function usable with multiple Vue instances.
 *
 * @see https://vueuse.org/createSharedComposable
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createSharedComposable<Fn extends AnyFn>(
  composable: Fn,
): SharedComposableReturn<Fn>
```

---

<!-- source: references/createTemplatePromise.md -->
---
category: Component
outline: deep
---

# createTemplatePromise

Template as Promise. Useful for constructing custom Dialogs, Modals, Toasts, etc.

## Usage

```vue
<script setup lang="ts">
import { createTemplatePromise } from '@vueuse/core'

const TemplatePromise = createTemplatePromise<ReturnType>()

async function open() {
  const result = await TemplatePromise.start()
  // button is clicked, result is 'ok'
}
</script>

<template>
  <TemplatePromise v-slot="{ promise, resolve, reject, args }">
    <!-- your UI -->
    <button @click="resolve('ok')">
      OK
    </button>
  </TemplatePromise>
</template>
```

## Features

- **Programmatic** - call your UI as a promise
- **Template** - use Vue template to render, not a new DSL
- **TypeScript** - full type safety via generic type
- **Renderless** - you take full control of the UI
- **Transition** - use support Vue transition

This function is migrated from [vue-template-promise](https://github.com/antfu/vue-template-promise)

## Usage

`createTemplatePromise` returns a **Vue Component** that you can directly use in your template with `<script setup>`

```ts twoslash include main
import { createTemplatePromise } from '@vueuse/core'

const TemplatePromise = createTemplatePromise()
const MyPromise = createTemplatePromise<boolean>() // with generic type
```

In template, use `v-slot` to access the promise and resolve functions.

```vue
<template>
  <TemplatePromise v-slot="{ promise, resolve, reject, args }">
    <!-- you can have anything -->
    <button @click="resolve('ok')">
      OK
    </button>
  </TemplatePromise>
  <MyPromise v-slot="{ promise, resolve, reject, args }">
    <!-- another one -->
  </MyPromise>
</template>
```

The slot will not be rendered initially (similar to `v-if="false"`), until you call the `start` method from the component.

```ts
// @include: main
// ---cut---
const result = await TemplatePromise.start()
```

Once `resolve` or `reject` is called in the template, the promise will be resolved or rejected, returning the value you passed in. Once resolved, the slot will be removed automatically.

### Passing Arguments

You can pass arguments to the `start` with arguments.

```ts twoslash include passing-arguments
import { createTemplatePromise } from '@vueuse/core'

const TemplatePromise = createTemplatePromise<boolean, [string, number]>()
```

```ts
// @include: passing-arguments
// ---cut---
const result = await TemplatePromise.start('hello', 123) // Pr
```

And in the template slot, you can access the arguments via `args` property.

```vue
<template>
  <TemplatePromise v-slot="{ args, resolve }">
    <div>{{ args[0] }}</div>
    <!-- hello -->
    <div>{{ args[1] }}</div>
    <!-- 123 -->
    <button @click="resolve(true)">
      OK
    </button>
  </TemplatePromise>
</template>
```

### Singleton Mode

Use the `singleton` option to ensure only one instance of the promise can be active at a time. If `start` is called while a promise is already active, it will return the existing promise instead of creating a new one.

```ts
import { createTemplatePromise } from '@vueuse/core'

const TemplatePromise = createTemplatePromise<boolean>({
  singleton: true,
})

// These will return the same promise if called in quick succession
const result1 = TemplatePromise.start()
const result2 = TemplatePromise.start() // returns the same promise as result1
```

### Transition

You can use transition to animate the slot.

```vue
<script setup lang="ts">
const TemplatePromise = createTemplatePromise<ReturnType>({
  transition: {
    name: 'fade',
    appear: true,
  },
})
</script>

<template>
  <TemplatePromise v-slot="{ resolve }">
    <!-- your UI -->
    <button @click="resolve('ok')">
      OK
    </button>
  </TemplatePromise>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.5s;
}
.fade-enter,
.fade-leave-to {
  opacity: 0;
}
</style>
```

Learn more about [Vue Transition](https://vuejs.org/guide/built-ins/transition.html).

### Slot Props

The slot provides the following props:

| Prop          | Type                                     | Description                                               |
| ------------- | ---------------------------------------- | --------------------------------------------------------- |
| `promise`     | `Promise<Return> \| undefined`           | The current promise instance                              |
| `resolve`     | `(v: Return \| Promise<Return>) => void` | Resolve the promise with a value                          |
| `reject`      | `(v: any) => void`                       | Reject the promise                                        |
| `args`        | `Args`                                   | Arguments passed to `start()`                             |
| `isResolving` | `boolean`                                | `true` when resolving another promise passed to `resolve` |
| `key`         | `number`                                 | Unique key for list rendering                             |

```vue
<template>
  <TemplatePromise v-slot="{ promise, resolve, reject, args, isResolving }">
    <div v-if="isResolving">
      Loading...
    </div>
    <div v-else>
      <button @click="resolve('ok')">
        OK
      </button>
      <button @click="reject('cancelled')">
        Cancel
      </button>
    </div>
  </TemplatePromise>
</template>
```

## Motivation

The common approach to call a dialog or a modal programmatically would be like this:

```ts
const dialog = useDialog()
const result = await dialog.open({
  title: 'Hello',
  content: 'World',
})
```

This would work by sending these information to the top-level component and let it render the dialog. However, it limits the flexibility you could express in the UI. For example, you could want the title to be red, or have extra buttons, etc. You would end up with a lot of options like:

```ts
const result = await dialog.open({
  title: 'Hello',
  titleClass: 'text-red',
  content: 'World',
  contentClass: 'text-blue text-sm',
  buttons: [
    { text: 'OK', class: 'bg-red', onClick: () => {} },
    { text: 'Cancel', class: 'bg-blue', onClick: () => {} },
  ],
  // ...
})
```

Even this is not flexible enough. If you want more, you might end up with manual render function.

```ts
const result = await dialog.open({
  title: 'Hello',
  contentSlot: () => h(MyComponent, { content }),
})
```

This is like reinventing a new DSL in the script to express the UI template.

So this function allows **expressing the UI in templates instead of scripts**, where it is supposed to be, while still being able to be manipulated programmatically.

## Type Declarations

```ts
export interface TemplatePromiseProps<Return, Args extends any[] = []> {
  /**
   * The promise instance.
   */
  promise: Promise<Return> | undefined
  /**
   * Resolve the promise.
   */
  resolve: (v: Return | Promise<Return>) => void
  /**
   * Reject the promise.
   */
  reject: (v: any) => void
  /**
   * Arguments passed to TemplatePromise.start()
   */
  args: Args
  /**
   * Indicates if the promise is resolving.
   * When passing another promise to `resolve`, this will be set to `true` until the promise is resolved.
   */
  isResolving: boolean
  /**
   * Options passed to createTemplatePromise()
   */
  options: TemplatePromiseOptions
  /**
   * Unique key for list rendering.
   */
  key: number
}
export interface TemplatePromiseOptions {
  /**
   * Determines if the promise can be called only once at a time.
   *
   * @default false
   */
  singleton?: boolean
  /**
   * Transition props for the promise.
   */
  transition?: TransitionGroupProps
}
export type TemplatePromise<
  Return,
  Args extends any[] = [],
> = DefineComponent<object> & {
  new (): {
    $slots: {
      default: (_: TemplatePromiseProps<Return, Args>) => any
    }
  }
} & {
  start: (...args: Args) => Promise<Return>
}
/**
 * Creates a template promise component.
 *
 * @see https://vueuse.org/createTemplatePromise
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createTemplatePromise<Return, Args extends any[] = []>(
  options?: TemplatePromiseOptions,
): TemplatePromise<Return, Args>
```

---

<!-- source: references/createUnrefFn.md -->
---
category: Utilities
related: reactify
---

# createUnrefFn

Make a plain function accepting ref and raw values as arguments.
Returns the same value the unconverted function returns, with proper typing.

::: tip
Make sure you're using the right tool for the job. Using `reactify`
might be more pertinent in some cases where you want to evaluate the function on each changes of it's arguments.
:::

## Usage

```ts
import { createUnrefFn } from '@vueuse/core'
import { shallowRef } from 'vue'

const url = shallowRef('https://httpbin.org/post')
const data = shallowRef({ foo: 'bar' })

function post(url, data) {
  return fetch(url, { data })
}
const unrefPost = createUnrefFn(post)

post(url, data) /* ❌ Will throw an error because the arguments are refs */
unrefPost(url, data) /* ✔️ Will Work because the arguments will be auto unref */
```

## Type Declarations

```ts
export type UnrefFn<T> = T extends (...args: infer A) => infer R
  ? (
      ...args: {
        [K in keyof A]: MaybeRef<A[K]>
      }
    ) => R
  : never
/**
 * Make a plain function accepting ref and raw values as arguments.
 * Returns the same value the unconverted function returns, with proper typing.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function createUnrefFn<T extends Function>(fn: T): UnrefFn<T>
```
