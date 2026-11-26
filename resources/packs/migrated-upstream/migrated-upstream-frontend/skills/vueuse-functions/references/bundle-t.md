<!-- source: references/templateRef.md -->
---
category: Component
---

::: info
This function will be removed in future version.

Vue 3.5 introduced the `useTemplateRef` API which can effectively replace the functionality of `templateRef`, therefore we recommend using the native approach.
:::

# templateRef

Shorthand for binding ref to template element.

## Usage

<!-- eslint-skip -->

```vue
<script lang="ts">
import { templateRef } from '@vueuse/core'

export default {
  setup() {
    const target = templateRef('target')

    // no need to return the `target`, it will bind to the ref magically
  },
}
</script>

<template>
  <div ref="target" />
</template>
```

### With JSX/TSX

```tsx
import { templateRef } from '@vueuse/core'

export default {
  setup() {
    const target = templateRef<HTMLElement | null>('target', null)

    // use string ref
    return () => <div ref="target"></div>
  },
}
```

### `<script setup>`

There is no need for this when using with `<script setup>` since all the variables will be exposed to the template. It will be exactly the same as `ref`.

```vue
<script setup lang="ts">
import { ref } from 'vue'

const target = ref<HTMLElement | null>(null)
</script>

<template>
  <div ref="target" />
</template>
```

## Type Declarations

```ts
/**
 * @deprecated Use Vue's built-in `useTemplateRef` instead.
 *
 * Shorthand for binding ref to template element.
 *
 * @see https://vueuse.org/templateRef
 * @param key
 * @param initialValue
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function templateRef<
  T extends HTMLElement | SVGElement | Component | null,
  Keys extends string = string,
>(key: Keys, initialValue?: T | null): Readonly<Ref<T>>
```

---

<!-- source: references/toObserver.md -->
---
category: '@RxJS'
---

# toObserver

Sugar function to convert a `ref` into an RxJS [Observer](https://rxjs.dev/guide/observer).

## Usage

<!-- TODO: import rxjs error if enable twoslash -->

```ts no-twoslash
import { from, fromEvent, toObserver, useSubscription } from '@vueuse/rxjs'
import { interval } from 'rxjs'
import { map, mapTo, startWith, takeUntil, withLatestFrom } from 'rxjs/operators'
import { shallowRef, useTemplateRef } from 'vue'

const count = shallowRef(0)
const button = useTemplateRef('buttonRef')

useSubscription(
  interval(1000)
    .pipe(
      mapTo(1),
      takeUntil(fromEvent(button, 'click')),
      withLatestFrom(from(count).pipe(startWith(0))),
      map(([curr, total]) => curr + total),
    )
    .subscribe(toObserver(count)), // same as ).subscribe(val => (count.value = val))
)
```

## Type Declarations

```ts
export declare function toObserver<T>(value: Ref<T>): NextObserver<T>
```

---

<!-- source: references/toReactive.md -->
---
category: Reactivity
---

# toReactive

Converts ref to reactive. Also made possible to create a "swapable" reactive object.

## Usage

```ts
import { toReactive } from '@vueuse/core'
import { ref } from 'vue'

const refState = ref({ foo: 'bar' })

console.log(refState.value.foo) // => 'bar'

const state = toReactive(refState) // <--

console.log(state.foo) // => 'bar'

refState.value = { bar: 'foo' }

console.log(state.foo) // => undefined
console.log(state.bar) // => 'foo'
```

## Type Declarations

```ts
/**
 * Converts ref to reactive.
 *
 * @see https://vueuse.org/toReactive
 * @param objectRef A ref of object
 */
export declare function toReactive<T extends object>(
  objectRef: MaybeRef<T>,
): UnwrapNestedRefs<T>
```

---

<!-- source: references/toRef.md -->
---
category: Reactivity
alias: resolveRef
---

# toRef

Normalize value/ref/getter to `ref` or `computed`.

## Usage

```ts
import { toRef } from '@vueuse/core'

const foo = ref('hi')

const a = toRef(0) // Ref<number>
const b = toRef(foo) // Ref<string>
const c = toRef(() => 'hi') // ComputedRef<string>
```

## Differences from Vue's `toRef`

VueUse's `toRef` is not the same as Vue’s `toRef` from the `vue` package.

### VueUse `toRef`

- Accepts **value**, **ref**, or **getter**
- Returns:
  - a **ref** for primitive values
  - a **ref** for existing refs
  - a **computed** for getter functions
- Does **not** accept `object + key`
- Getters always produce readonly computed values

### Vue `toRef`

- Accepts only:
  - a **reactive object + property key**, or
  - an existing **ref**
- Produces a **writable ref** linked to the underlying reactive object
- Does **not** accept primitive values
- Does **not** accept getter functions

### Summary

| Behavior                 | VueUse `toRef`            | Vue `toRef`             |
| ------------------------ | ------------------------- | ----------------------- |
| Accepts primitive values | ✔️                        | ❌                      |
| Accepts getter           | ✔️ (computed)             | ❌                      |
| Accepts existing ref     | ✔️                        | ✔️                      |
| Accepts object + key     | ❌                        | ✔️                      |
| Writable                 | ✔️ (except getter)        | ✔️                      |
| Purpose                  | Normalize to ref/computed | Bind to reactive object |

## Type Declarations

```ts
/**
 * Normalize value/ref/getter to `ref` or `computed`.
 */
export declare function toRef<T>(r: () => T): Readonly<Ref<T>>
export declare function toRef<T>(r: ComputedRef<T>): ComputedRef<T>
export declare function toRef<T>(r: MaybeRefOrGetter<T>): Ref<T>
export declare function toRef<T>(r: T): Ref<T>
export declare function toRef<T extends object, K extends keyof T>(
  object: T,
  key: K,
): ToRef<T[K]>
export declare function toRef<T extends object, K extends keyof T>(
  object: T,
  key: K,
  defaultValue: T[K],
): ToRef<Exclude<T[K], undefined>>
```

---

<!-- source: references/toRefs.md -->
---
category: Reactivity
---

# toRefs

Extended [`toRefs`](https://vuejs.org/api/reactivity-utilities.html#torefs) that also accepts refs of an object.

## Usage

<!-- eslint-disable array-bracket-spacing -->
<!-- eslint-disable ts/no-redeclare -->

```ts
import { toRefs } from '@vueuse/core'
import { reactive, ref } from 'vue'

const objRef = ref({ a: 'a', b: 0 })
const arrRef = ref(['a', 0])

const { a, b } = toRefs(objRef)
const [a, b] = toRefs(arrRef)

const obj = reactive({ a: 'a', b: 0 })
const arr = reactive(['a', 0])

const { a, b } = toRefs(obj)
const [a, b] = toRefs(arr)
```

## Use-cases

### Destructuring a props object

```vue
<script lang="ts">
import { toRefs, useVModel } from '@vueuse/core'

export default {
  setup(props) {
    const refs = toRefs(useVModel(props, 'data'))

    console.log(refs.a.value) // props.data.a
    refs.a.value = 'a' // emit('update:data', { ...props.data, a: 'a' })

    return { ...refs }
  }
}
</script>

<template>
  <div>
    <input v-model="a" type="text">
    <input v-model="b" type="text">
  </div>
</template>
```

## Type Declarations

```ts
export interface ToRefsOptions {
  /**
   * Replace the original ref with a copy on property update.
   *
   * @default true
   */
  replaceRef?: MaybeRefOrGetter<boolean>
}
/**
 * Extended `toRefs` that also accepts refs of an object.
 *
 * @see https://vueuse.org/toRefs
 * @param objectRef A ref or normal object or array.
 * @param options Options
 */
export declare function toRefs<T extends object>(
  objectRef: MaybeRef<T>,
  options?: ToRefsOptions,
): ToRefs<T>
```

---

<!-- source: references/tryOnBeforeMount.md -->
---
category: Component
---

# tryOnBeforeMount

Safe `onBeforeMount`. Call `onBeforeMount()` if it's inside a component lifecycle, if not, just call the function

## Usage

```ts
import { tryOnBeforeMount } from '@vueuse/core'

tryOnBeforeMount(() => {

})
```

## Type Declarations

```ts
/**
 * Call onBeforeMount() if it's inside a component lifecycle, if not, just call the function
 *
 * @param fn
 * @param sync if set to false, it will run in the nextTick() of Vue
 * @param target
 */
export declare function tryOnBeforeMount(
  fn: Fn,
  sync?: boolean,
  target?: ComponentInternalInstance | null,
): void
```

---

<!-- source: references/tryOnBeforeUnmount.md -->
---
category: Component
---

# tryOnBeforeUnmount

Safe `onBeforeUnmount`. Call `onBeforeUnmount()` if it's inside a component lifecycle, if not, do nothing

## Usage

```ts
import { tryOnBeforeUnmount } from '@vueuse/core'

tryOnBeforeUnmount(() => {

})
```

## Type Declarations

```ts
/**
 * Call onBeforeUnmount() if it's inside a component lifecycle, if not, do nothing
 *
 * @param fn
 * @param target
 */
export declare function tryOnBeforeUnmount(
  fn: Fn,
  target?: ComponentInternalInstance | null,
): void
```

---

<!-- source: references/tryOnMounted.md -->
---
category: Component
---

# tryOnMounted

Safe `onMounted`. Call `onMounted()` if it's inside a component lifecycle, if not, just call the function

## Usage

```ts
import { tryOnMounted } from '@vueuse/core'

tryOnMounted(() => {

})
```

## Type Declarations

```ts
/**
 * Call onMounted() if it's inside a component lifecycle, if not, just call the function
 *
 * @param fn
 * @param sync if set to false, it will run in the nextTick() of Vue
 * @param target
 */
export declare function tryOnMounted(
  fn: Fn,
  sync?: boolean,
  target?: ComponentInternalInstance | null,
): void
```

---

<!-- source: references/tryOnScopeDispose.md -->
---
category: Component
---

# tryOnScopeDispose

Safe `onScopeDispose`. Call `onScopeDispose()` if it's inside an effect scope lifecycle, if not, do nothing

## Usage

```ts
import { tryOnScopeDispose } from '@vueuse/core'

tryOnScopeDispose(() => {

})
```

## Type Declarations

```ts
/**
 * Call onScopeDispose() if it's inside an effect scope lifecycle, if not, do nothing
 *
 * @param fn
 */
export declare function tryOnScopeDispose(
  fn: Fn,
  failSilently?: boolean,
): boolean
```

---

<!-- source: references/tryOnUnmounted.md -->
---
category: Component
---

# tryOnUnmounted

Safe `onUnmounted`. Call `onUnmounted()` if it's inside a component lifecycle, if not, do nothing

## Usage

```ts
import { tryOnUnmounted } from '@vueuse/core'

tryOnUnmounted(() => {

})
```

## Type Declarations

```ts
/**
 * Call onUnmounted() if it's inside a component lifecycle, if not, do nothing
 *
 * @param fn
 * @param target
 */
export declare function tryOnUnmounted(
  fn: Fn,
  target?: ComponentInternalInstance | null,
): void
```
