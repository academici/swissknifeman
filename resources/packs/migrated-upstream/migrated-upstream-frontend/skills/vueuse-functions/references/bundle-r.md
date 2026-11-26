<!-- source: references/reactify.md -->
---
category: Reactivity
alias: createReactiveFn
---

# reactify

Converts plain functions into reactive functions. The converted function accepts refs as its arguments and returns a ComputedRef, with proper typing.

::: tip
Interested to see some application or looking for some pre-reactified functions?

Check out [⚗️ Vue Chemistry](https://github.com/antfu/vue-chemistry)!
:::

## Usage

Basic example

```ts
import { reactify } from '@vueuse/core'
import { shallowRef } from 'vue'

// a plain function
function add(a: number, b: number): number {
  return a + b
}

// now it accept refs and returns a computed ref
// (a: number | Ref<number>, b: number | Ref<number>) => ComputedRef<number>
const reactiveAdd = reactify(add)

const a = shallowRef(1)
const b = shallowRef(2)
const sum = reactiveAdd(a, b)

console.log(sum.value) // 3

a.value = 5

console.log(sum.value) // 7
```

An example of implementing a reactive [Pythagorean theorem](https://en.wikipedia.org/wiki/Pythagorean_theorem).

<!-- eslint-skip -->

```ts
import { reactify } from '@vueuse/core'
import { shallowRef } from 'vue'

const pow = reactify(Math.pow)
const sqrt = reactify(Math.sqrt)
const add = reactify((a: number, b: number) => a + b)

const a = shallowRef(3)
const b = shallowRef(4)
const c = sqrt(add(pow(a, 2), pow(b, 2)))
console.log(c.value) // 5

// 5:12:13
a.value = 5
b.value = 12
console.log(c.value) // 13
```

You can also do it this way:

```ts
import { reactify } from '@vueuse/core'
import { shallowRef } from 'vue'

function pythagorean(a: number, b: number) {
  return Math.sqrt(a ** 2 + b ** 2)
}

const a = shallowRef(3)
const b = shallowRef(4)

const c = reactify(pythagorean)(a, b)
console.log(c.value) // 5
```

Another example of making reactive `stringify`

```ts
import { reactify } from '@vueuse/core'
import { shallowRef } from 'vue'

const stringify = reactify(JSON.stringify)

const obj = shallowRef(42)
const dumped = stringify(obj)

console.log(dumped.value) // '42'

obj.value = { foo: 'bar' }

console.log(dumped.value) // '{"foo":"bar"}'
```

## Type Declarations

```ts
export type Reactified<T, Computed extends boolean> = T extends (
  ...args: infer A
) => infer R
  ? (
      ...args: {
        [K in keyof A]: Computed extends true
          ? MaybeRefOrGetter<A[K]>
          : MaybeRef<A[K]>
      }
    ) => ComputedRef<R>
  : never
export type ReactifyReturn<
  T extends AnyFn = AnyFn,
  K extends boolean = true,
> = Reactified<T, K>
export interface ReactifyOptions<T extends boolean> {
  /**
   * Accept passing a function as a reactive getter
   *
   * @default true
   */
  computedGetter?: T
}
/**
 * Converts plain function into a reactive function.
 * The converted function accepts refs as it's arguments
 * and returns a ComputedRef, with proper typing.
 *
 * @param fn - Source function
 * @param options - Options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function reactify<T extends AnyFn, K extends boolean = true>(
  fn: T,
  options?: ReactifyOptions<K>,
): ReactifyReturn<T, K>
/** @deprecated use `reactify` instead */
export declare const createReactiveFn: typeof reactify
```

---

<!-- source: references/reactifyObject.md -->
---
category: Reactivity
---

# reactifyObject

Apply `reactify` to an object

## Usage

```ts
import { reactifyObject } from '@vueuse/core'

const reactifiedConsole = reactifyObject(console)

const a = ref('42')

reactifiedConsole.log(a) // no longer need `.value`
```

## Type Declarations

```ts
export type ReactifyNested<
  T,
  Keys extends keyof T = keyof T,
  S extends boolean = true,
> = {
  [K in Keys]: T[K] extends AnyFn ? Reactified<T[K], S> : T[K]
}
export type ReactifyObjectReturn<
  T,
  Keys extends keyof T,
  S extends boolean = true,
> = ReactifyNested<T, Keys, S>
export interface ReactifyObjectOptions<
  T extends boolean,
> extends ReactifyOptions<T> {
  /**
   * Includes names from Object.getOwnPropertyNames
   *
   * @default true
   */
  includeOwnProperties?: boolean
}
/**
 * Apply `reactify` to an object
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function reactifyObject<T extends object, Keys extends keyof T>(
  obj: T,
  keys?: (keyof T)[],
): ReactifyObjectReturn<T, Keys, true>
export declare function reactifyObject<
  T extends object,
  S extends boolean = true,
>(
  obj: T,
  options?: ReactifyObjectOptions<S>,
): ReactifyObjectReturn<T, keyof T, S>
```

---

<!-- source: references/reactiveComputed.md -->
---
category: Reactivity
---

# reactiveComputed

Computed reactive object. Instead of returning a ref that `computed` does, `reactiveComputed` returns a reactive object.

## Usage

```ts
import { reactiveComputed } from '@vueuse/core'

const state = reactiveComputed(() => {
  return {
    foo: 'bar',
    bar: 'baz',
  }
})

state.bar // 'baz'
```

## Type Declarations

```ts
export type ReactiveComputedReturn<T extends object> = UnwrapNestedRefs<T>
/**
 * Computed reactive object.
 */
export declare function reactiveComputed<T extends object>(
  fn: ComputedGetter<T>,
): ReactiveComputedReturn<T>
```

---

<!-- source: references/reactiveOmit.md -->
---
category: Reactivity
---

# reactiveOmit

Reactively omit fields from a reactive object.

## Usage

### Basic Usage

```ts
import { reactiveOmit } from '@vueuse/core'

const obj = reactive({
  x: 0,
  y: 0,
  elementX: 0,
  elementY: 0,
})

const picked = reactiveOmit(obj, 'x', 'elementX') // { y: number, elementY: number }
```

### Predicate Usage

```ts
import { reactiveOmit } from '@vueuse/core'

const obj = reactive({
  bar: 'bar',
  baz: 'should be omit',
  foo: 'foo2',
  qux: true,
})

const picked = reactiveOmit(obj, (value, key) => key === 'baz' || value === true)
// { bar: string, foo: string }
```

### Scenarios

#### Selectively passing props to child

```vue
<script setup lang="ts">
import { reactiveOmit } from '@vueuse/core'

const props = defineProps<{
  value: string
  color?: string
  font?: string
}>()

const childProps = reactiveOmit(props, 'value')
</script>

<template>
  <div>
    <!-- only passes "color" and "font" props to child -->
    <ChildComp v-bind="childProps" />
  </div>
</template>
```

## Type Declarations

```ts
export type ReactiveOmitReturn<
  T extends object,
  K extends keyof T | undefined = undefined,
> = [K] extends [undefined] ? Partial<T> : Omit<T, Extract<K, keyof T>>
export type ReactiveOmitPredicate<T> = (
  value: T[keyof T],
  key: keyof T,
) => boolean
export declare function reactiveOmit<T extends object, K extends keyof T>(
  obj: T,
  ...keys: (K | K[])[]
): ReactiveOmitReturn<T, K>
export declare function reactiveOmit<T extends object>(
  obj: T,
  predicate: ReactiveOmitPredicate<T>,
): ReactiveOmitReturn<T>
```

---

<!-- source: references/reactivePick.md -->
---
category: Reactivity
---

# reactivePick

Reactively pick fields from a reactive object.

## Usage

### Basic Usage

```ts
import { reactivePick } from '@vueuse/core'

const obj = reactive({
  x: 0,
  y: 0,
  elementX: 0,
  elementY: 0,
})

const picked = reactivePick(obj, 'x', 'elementX') // { x: number, elementX: number }
```

### Predicate Usage

```ts
import { reactivePick } from '@vueuse/core'

const source = reactive({
  foo: 'foo',
  bar: 'bar',
  baz: 'baz',
  qux: true,
})
const state = reactivePick(source, (value, key) => key !== 'bar' && value !== true)
// { foo: string, baz: string }
source.qux = false
// { foo: string, baz: string, qux: boolean }
```

### Scenarios

#### Selectively passing props to child

```vue
<script setup lang="ts">
import { reactivePick } from '@vueuse/core'

const props = defineProps<{
  value: string
  color?: string
  font?: string
}>()

const childProps = reactivePick(props, 'color', 'font')
</script>

<template>
  <div>
    <!-- only passes "color" and "font" props to child -->
    <ChildComp v-bind="childProps" />
  </div>
</template>
```

#### Selectively wrap reactive object

Instead of doing this

```ts
import { useElementBounding } from '@vueuse/core'
import { reactive } from 'vue'

const { height, width } = useElementBounding() // object of refs
const size = reactive({ height, width })
```

Now we can just have this

```ts
import { reactivePick, useElementBounding } from '@vueuse/core'

const size = reactivePick(useElementBounding(), 'height', 'width')
```

## Type Declarations

```ts
export type ReactivePickReturn<T extends object, K extends keyof T> = {
  [S in K]: UnwrapRef<T[S]>
}
export type ReactivePickPredicate<T> = (
  value: T[keyof T],
  key: keyof T,
) => boolean
export declare function reactivePick<T extends object, K extends keyof T>(
  obj: T,
  ...keys: (K | K[])[]
): ReactivePickReturn<T, K>
export declare function reactivePick<T extends object>(
  obj: T,
  predicate: ReactivePickPredicate<T>,
): ReactivePickReturn<T, keyof T>
```

---

<!-- source: references/refAutoReset.md -->
---
category: Reactivity
alias: autoResetRef
---

# refAutoReset

A ref which will be reset to the default value after some time.

## Usage

```ts
import { refAutoReset } from '@vueuse/core'

const message = refAutoReset('default message', 1000)

function setMessage() {
  // here the value will change to 'message has set' but after 1000ms, it will change to 'default message'
  message.value = 'message has set'
}
```

::: info
You can reassign the entire object to trigger updates after making deep mutations to the inner value.

[Learn more about shallow refs →](https://vuejs.org/api/reactivity-advanced#shallowref)
:::

## Type Declarations

```ts
export type RefAutoResetReturn<T = any> = Ref<T>
/**
 * Create a ref which will be reset to the default value after some time.
 *
 * @see https://vueuse.org/refAutoReset
 * @param defaultValue The value which will be set.
 * @param afterMs      A zero-or-greater delay in milliseconds.
 */
export declare function refAutoReset<T>(
  defaultValue: MaybeRefOrGetter<T>,
  afterMs?: MaybeRefOrGetter<number>,
): RefAutoResetReturn<T>
/** @deprecated use `refAutoReset` instead */
export declare const autoResetRef: typeof refAutoReset
```

---

<!-- source: references/refDebounced.md -->
---
category: Reactivity
alias: useDebounce, debouncedRef
---

# refDebounced

Debounce execution of a ref value.

## Usage

```ts {5}
import { refDebounced } from '@vueuse/core'
import { shallowRef } from 'vue'

const input = shallowRef('foo')
const debounced = refDebounced(input, 1000)

input.value = 'bar'
console.log(debounced.value) // 'foo'

await sleep(1100)

console.log(debounced.value) // 'bar'
// ---cut-after---
function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}
```

An example with object ref.

```js
import { refDebounced } from '@vueuse/core'
import { shallowRef } from 'vue'

const data = shallowRef({
  name: 'foo',
  age: 18,
})
const debounced = refDebounced(data, 1000)

function update() {
  data.value = {
    ...data.value,
    name: 'bar',
  }
}

console.log(debounced.value) // { name: 'foo', age: 18 }
update()
await sleep(1100)

console.log(debounced.value) // { name: 'bar', age: 18 }
```

You can also pass an optional 3rd parameter including maxWait option. See `useDebounceFn` for details.

## Recommended Reading

- [**Debounce vs Throttle**: Definitive Visual Guide](https://kettanaito.com/blog/debounce-vs-throttle)

## Type Declarations

```ts
export type RefDebouncedReturn<T = any> = Readonly<Ref<T>>
/**
 * Debounce updates of a ref.
 *
 * @return A new debounced ref.
 */
export declare function refDebounced<T>(
  value: Ref<T>,
  ms?: MaybeRefOrGetter<number>,
  options?: DebounceFilterOptions,
): RefDebouncedReturn<T>
/** @deprecated use `refDebounced` instead */
export declare const debouncedRef: typeof refDebounced
/** @deprecated use `refDebounced` instead */
export declare const useDebounce: typeof refDebounced
```

---

<!-- source: references/refDefault.md -->
---
category: Reactivity
---

# refDefault

Apply default value to a ref.

## Usage

```ts
import { refDefault, useStorage } from '@vueuse/core'

const raw = useStorage('key')
const state = refDefault(raw, 'default')

raw.value = 'hello'
console.log(state.value) // hello

raw.value = undefined
console.log(state.value) // default
```

## Type Declarations

```ts
/**
 * Apply default value to a ref.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function refDefault<T>(
  source: Ref<T | undefined | null>,
  defaultValue: T,
): Ref<T>
```

---

<!-- source: references/refManualReset.md -->
---
category: Reactivity
---

# refManualReset

Create a ref with manual reset functionality.

## Usage

```ts
import { refManualReset } from '@vueuse/core'

const message = refManualReset('default message')

message.value = 'message has set'

message.reset()

console.log(message.value) // 'default message'
```

## Type Declarations

```ts
/**
 * Define the shape of a ref that supports manual reset functionality.
 *
 * This interface extends the standard `Ref` type from Vue and adds a `reset` method.
 * The `reset` method allows the ref to be manually reset to its default value.
 */
export interface ManualResetRefReturn<T> extends Ref<T> {
  reset: Fn
}
/**
 * Create a ref with manual reset functionality.
 *
 * @see https://vueuse.org/refManualReset
 * @param defaultValue The value which will be set.
 */
export declare function refManualReset<T>(
  defaultValue: MaybeRefOrGetter<T>,
): ManualResetRefReturn<T>
```

---

<!-- source: references/refThrottled.md -->
---
category: Reactivity
alias: useThrottle, throttledRef
---

# refThrottled

Throttle changing of a ref value.

## Usage

```ts
import { refThrottled } from '@vueuse/core'
import { shallowRef } from 'vue'

const input = shallowRef('')
const throttled = refThrottled(input, 1000)
```

An example with object ref.

```js
import { refThrottled } from '@vueuse/core'
import { shallowRef } from 'vue'

const data = shallowRef({
  count: 0,
  name: 'foo',
})
const throttled = refThrottled(data, 1000)

data.value = { count: 1, name: 'foo' }
console.log(throttled.value) // { count: 1, name: 'foo' } (immediate)

data.value = { count: 2, name: 'bar' }
data.value = { count: 3, name: 'baz' }
data.value = { count: 4, name: 'qux' }
console.log(throttled.value) // { count: 1, name: 'foo' } (still first value)

// After 1000ms, next change will be applied
await sleep(1100)
data.value = { count: 5, name: 'final' }
await nextTick()
console.log(throttled.value) // { count: 5, name: 'final' } (updated)
```

### Trailing

If you don't want to watch trailing changes, set 3rd param `false` (it's `true` by default):

```ts
import { refThrottled } from '@vueuse/core'
import { shallowRef } from 'vue'

const input = shallowRef('')
const throttled = refThrottled(input, 1000, false)
```

### Leading

Allows the callback to be invoked immediately (on the leading edge of the `ms` timeout). If you don't want this behavior, set the 4th param `false` (it's `true` by default):

```ts
import { refThrottled } from '@vueuse/core'
import { shallowRef } from 'vue'

const input = shallowRef('')
const throttled = refThrottled(input, 1000, undefined, false)
```

## Recommended Reading

- [Debounce vs Throttle: Definitive Visual Guide](https://kettanaito.com/blog/debounce-vs-throttle)
- [Debouncing and Throttling Explained Through Examples](https://css-tricks.com/debouncing-throttling-explained-examples/)

## Type Declarations

```ts
export type RefThrottledReturn<T = any> = Ref<T>
/**
 * Throttle execution of a function. Especially useful for rate limiting
 * execution of handlers on events like resize and scroll.
 *
 * @param value Ref value to be watched with throttle effect
 * @param  delay  A zero-or-greater delay in milliseconds. For event callbacks, values around 100 or 250 (or even higher) are most useful.
 * @param trailing if true, update the value again after the delay time is up
 * @param leading if true, update the value on the leading edge of the ms timeout
 */
export declare function refThrottled<T = any>(
  value: Ref<T>,
  delay?: number,
  trailing?: boolean,
  leading?: boolean,
): RefThrottledReturn<T>
/** @deprecated use `refThrottled` instead */
export declare const throttledRef: typeof refThrottled
/** @deprecated use `refThrottled` instead */
export declare const useThrottle: typeof refThrottled
```

---

<!-- source: references/refWithControl.md -->
---
category: Reactivity
alias: controlledRef
related: computedWithControl
---

# refWithControl

Fine-grained controls over ref and its reactivity.

## Usage

`refWithControl` uses `extendRef` to provide two extra functions `get` and `set` to have better control over when it should track/trigger the reactivity.

```ts
import { refWithControl } from '@vueuse/core'

const num = refWithControl(0)
const doubled = computed(() => num.value * 2)

// just like normal ref
num.value = 42
console.log(num.value) // 42
console.log(doubled.value) // 84

// set value without triggering the reactivity
num.set(30, false)
console.log(num.value) // 30
console.log(doubled.value) // 84 (doesn't update)

// get value without tracking the reactivity
watchEffect(() => {
  console.log(num.peek())
}) // 30

num.value = 50 // watch effect wouldn't be triggered since it collected nothing.
console.log(doubled.value) // 100 (updated again since it's a reactive set)
```

### `peek`, `lay`, `untrackedGet`, `silentSet`

We also provide some shorthands for doing the get/set without track/triggering the reactivity system. The following lines are equivalent.

```ts
import { refWithControl } from '@vueuse/core'
// ---cut---
const foo = refWithControl('foo')
```

```ts
import { refWithControl } from '@vueuse/core'

const foo = refWithControl('foo')
// ---cut---
// getting
foo.get(false)
foo.untrackedGet()
foo.peek() // an alias for `untrackedGet`
```

```ts
import { refWithControl } from '@vueuse/core'

const foo = refWithControl('foo')
// ---cut---
// setting
foo.set('bar', false)
foo.silentSet('bar')
foo.lay('bar') // an alias for `silentSet`
```

## Configurations

### `onBeforeChange()`

`onBeforeChange` option is offered to give control over if a new value should be accepted. For example:

```ts
import { refWithControl } from '@vueuse/core'
// ---cut---
const num = refWithControl(0, {
  onBeforeChange(value, oldValue) {
    // disallow changes larger then ±5 in one operation
    if (Math.abs(value - oldValue) > 5)
      return false // returning `false` to dismiss the change
  },
})

num.value += 1
console.log(num.value) // 1

num.value += 6
console.log(num.value) // 1 (change been dismissed)
```

### `onChanged()`

`onChanged` option offers a similar functionally as Vue's `watch` but being synchronized with less overhead compared to `watch`.

```ts
import { refWithControl } from '@vueuse/core'
// ---cut---
const num = refWithControl(0, {
  onChanged(value, oldValue) {
    console.log(value)
  },
})
```

## Type Declarations

```ts
export interface ControlledRefOptions<T> {
  /**
   * Callback function before the ref changing.
   *
   * Returning `false` to dismiss the change.
   */
  onBeforeChange?: (value: T, oldValue: T) => void | boolean
  /**
   * Callback function after the ref changed
   *
   * This happens synchronously, with less overhead compare to `watch`
   */
  onChanged?: (value: T, oldValue: T) => void
}
/**
 * Fine-grained controls over ref and its reactivity.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function refWithControl<T>(
  initial: T,
  options?: ControlledRefOptions<T>,
): ShallowUnwrapRef<{
  get: (tracking?: boolean) => T
  set: (value: T, triggering?: boolean) => void
  untrackedGet: () => T
  silentSet: (v: T) => void
  peek: () => T
  lay: (v: T) => void
}> &
  Ref<T, T>
/** @deprecated use `refWithControl` instead */
export declare const controlledRef: typeof refWithControl
```
