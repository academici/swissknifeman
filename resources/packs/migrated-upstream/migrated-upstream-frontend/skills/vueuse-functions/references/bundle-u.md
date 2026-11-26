<!-- source: references/unrefElement.md -->
---
category: Component
---

# unrefElement

Retrieves the underlying DOM element from a Vue ref or component instance

## Usage

```vue
<script setup lang="ts">
import { unrefElement } from '@vueuse/core'
import { onMounted, useTemplateRef } from 'vue'

const div = useTemplateRef('div') // will be bound to the <div> element
const hello = useTemplateRef('hello') // will be bound to the HelloWorld Component

onMounted(() => {
  console.log(unrefElement(div)) // the <div> element
  console.log(unrefElement(hello)) // the root element of the HelloWorld Component
})
</script>

<template>
  <div ref="div" />
  <HelloWorld ref="hello" />
</template>
```

## Type Declarations

```ts
export type VueInstance = ComponentPublicInstance
export type MaybeElementRef<T extends MaybeElement = MaybeElement> = MaybeRef<T>
export type MaybeComputedElementRef<T extends MaybeElement = MaybeElement> =
  MaybeRefOrGetter<T>
export type MaybeElement =
  | HTMLElement
  | SVGElement
  | VueInstance
  | undefined
  | null
export type UnRefElementReturn<T extends MaybeElement = MaybeElement> =
  T extends VueInstance ? Exclude<MaybeElement, VueInstance> : T | undefined
/**
 * Get the dom element of a ref of element or Vue component instance
 *
 * @param elRef
 */
export declare function unrefElement<T extends MaybeElement>(
  elRef: MaybeComputedElementRef<T>,
): UnRefElementReturn<T>
```

---

<!-- source: references/until.md -->
---
category: Watch
---

# until

Promised one-time watch for changes

## Usage

#### Wait for some async data to be ready

```ts
import { until, useAsyncState } from '@vueuse/core'

const { state, isReady } = useAsyncState(
  fetch('https://jsonplaceholder.typicode.com/todos/1').then(t => t.json()),
  {},
)

;(async () => {
  await until(isReady).toBe(true)

  console.log(state) // state is now ready!
})()
```

#### Wait for custom conditions

> You can use `invoke` to call the async function.

```ts
import { invoke, until, useCounter } from '@vueuse/core'

const { count } = useCounter()

invoke(async () => {
  await until(count).toMatch(v => v > 7)

  alert('Counter is now larger than 7!')
})
```

#### Timeout

```ts
import { until } from '@vueuse/core'
// ---cut---
// will be resolve until ref.value === true or 1000ms passed
await until(ref).toBe(true, { timeout: 1000 })

// will throw if timeout
try {
  await until(ref).toBe(true, { timeout: 1000, throwOnTimeout: true })
  // ref.value === true
}
catch (e) {
  // timeout
}
```

#### More Examples

```ts
import { until } from '@vueuse/core'
// ---cut---
await until(ref).toBe(true)
await until(ref).toMatch(v => v > 10 && v < 100)
await until(ref).changed()
await until(ref).changedTimes(10)
await until(ref).toBeTruthy()
await until(ref).toBeNull()

await until(ref).not.toBeNull()
await until(ref).not.toBeTruthy()
```

## Type Declarations

```ts
export interface UntilToMatchOptions extends ConfigurableFlushSync {
  /**
   * Milliseconds timeout for promise to resolve/reject if the when condition does not meet.
   * 0 for never timed out
   *
   * @default 0
   */
  timeout?: number
  /**
   * Reject the promise when timeout
   *
   * @default false
   */
  throwOnTimeout?: boolean
  /**
   * `deep` option for internal watch
   *
   * @default 'false'
   */
  deep?: WatchOptions["deep"]
}
export interface UntilBaseInstance<T, Not extends boolean = false> {
  toMatch: (<U extends T = T>(
    condition: (v: T) => v is U,
    options?: UntilToMatchOptions,
  ) => Not extends true ? Promise<Exclude<T, U>> : Promise<U>) &
    ((
      condition: (v: T) => boolean,
      options?: UntilToMatchOptions,
    ) => Promise<T>)
  changed: (options?: UntilToMatchOptions) => Promise<T>
  changedTimes: (n?: number, options?: UntilToMatchOptions) => Promise<T>
}
type Falsy = false | void | null | undefined | 0 | 0n | ""
export interface UntilValueInstance<
  T,
  Not extends boolean = false,
> extends UntilBaseInstance<T, Not> {
  readonly not: UntilValueInstance<T, Not extends true ? false : true>
  toBe: <P = T>(
    value: MaybeRefOrGetter<P>,
    options?: UntilToMatchOptions,
  ) => Not extends true ? Promise<T> : Promise<P>
  toBeTruthy: (
    options?: UntilToMatchOptions,
  ) => Not extends true ? Promise<T & Falsy> : Promise<Exclude<T, Falsy>>
  toBeNull: (
    options?: UntilToMatchOptions,
  ) => Not extends true ? Promise<Exclude<T, null>> : Promise<null>
  toBeUndefined: (
    options?: UntilToMatchOptions,
  ) => Not extends true ? Promise<Exclude<T, undefined>> : Promise<undefined>
  toBeNaN: (options?: UntilToMatchOptions) => Promise<T>
}
export interface UntilArrayInstance<T> extends UntilBaseInstance<T> {
  readonly not: UntilArrayInstance<T>
  toContains: (
    value: MaybeRefOrGetter<ElementOf<ShallowUnwrapRef<T>>>,
    options?: UntilToMatchOptions,
  ) => Promise<T>
}
/**
 * Promised one-time watch for changes
 *
 * @see https://vueuse.org/until
 * @example
 * ```
 * const { count } = useCounter()
 *
 * await until(count).toMatch(v => v > 7)
 *
 * alert('Counter is now larger than 7!')
 * ```
 */
export declare function until<T extends unknown[]>(
  r: WatchSource<T> | MaybeRefOrGetter<T>,
): UntilArrayInstance<T>
export declare function until<T>(
  r: WatchSource<T> | MaybeRefOrGetter<T>,
): UntilValueInstance<T>
```

---

<!-- source: references/useAbs.md -->
---
category: '@Math'
---

# useAbs

Reactive `Math.abs`.

## Usage

```ts
import { useAbs } from '@vueuse/math'

const value = ref(-23)
const absValue = useAbs(value) // Ref<23>
```

## Type Declarations

```ts
/**
 * Reactive `Math.abs`.
 *
 * @see https://vueuse.org/useAbs
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useAbs(
  value: MaybeRefOrGetter<number>,
): ComputedRef<number>
```

---

<!-- source: references/useActiveElement.md -->
---
category: Elements
---

# useActiveElement

Reactive `document.activeElement`. Returns a shallow ref that updates when focus changes.

## Usage

```vue
<script setup lang="ts">
import { useActiveElement } from '@vueuse/core'
import { watch } from 'vue'

const activeElement = useActiveElement()

watch(activeElement, (el) => {
  console.log('focus changed to', el)
})
</script>
```

### Shadow DOM Support

By default, `useActiveElement` will traverse into shadow DOM to find the deeply active element. Set `deep: false` to disable this behavior.

```ts
import { useActiveElement } from '@vueuse/core'

// Only get the shadow host, not the element inside shadow DOM
const activeElement = useActiveElement({ deep: false })
```

### Track Element Removal

Set `triggerOnRemoval: true` to update the active element when the currently active element is removed from the DOM. This uses a `MutationObserver` under the hood.

```ts
import { useActiveElement } from '@vueuse/core'

const activeElement = useActiveElement({ triggerOnRemoval: true })
```

## Component Usage

```vue
<template>
  <UseActiveElement v-slot="{ element }">
    Active element is {{ element?.dataset.id }}
  </UseActiveElement>
</template>
```

## Type Declarations

```ts
export interface UseActiveElementOptions
  extends ConfigurableWindow, ConfigurableDocumentOrShadowRoot {
  /**
   * Search active element deeply inside shadow dom
   *
   * @default true
   */
  deep?: boolean
  /**
   * Track active element when it's removed from the DOM
   * Using a MutationObserver under the hood
   * @default false
   */
  triggerOnRemoval?: boolean
}
export type UseActiveElementReturn<T extends HTMLElement = HTMLElement> =
  ShallowRef<T | null | undefined>
/**
 * Reactive `document.activeElement`
 *
 * @see https://vueuse.org/useActiveElement
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useActiveElement<T extends HTMLElement>(
  options?: UseActiveElementOptions,
): UseActiveElementReturn<T>
```

---

<!-- source: references/useAnimate.md -->
---
category: Animation
---

# useAnimate

Reactive [Web Animations API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API).

## Usage

### Basic Usage

The `useAnimate` function returns the animation instance and control functions.

```vue
<script setup lang="ts">
import { useAnimate } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const {
  isSupported,
  animate,

  // actions
  play,
  pause,
  reverse,
  finish,
  cancel,

  // states
  pending,
  playState,
  replaceState,
  startTime,
  currentTime,
  timeline,
  playbackRate,
} = useAnimate(el, { transform: 'rotate(360deg)' }, 1000)
</script>

<template>
  <span ref="el" style="display:inline-block">useAnimate</span>
</template>
```

### Custom Keyframes

Either an array of keyframe objects, or a keyframe object, or a `ref`. See [Keyframe Formats](https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API/Keyframe_Formats) for more details.

```ts
import { useAnimate } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
// ---cut---
const keyframes = { transform: 'rotate(360deg)' }
// Or
const keyframes = [
  { transform: 'rotate(0deg)' },
  { transform: 'rotate(360deg)' },
]
// Or
const keyframes = ref([
  { clipPath: 'circle(20% at 0% 30%)' },
  { clipPath: 'circle(20% at 50% 80%)' },
  { clipPath: 'circle(20% at 100% 30%)' },
])

useAnimate(el, keyframes, 1000)
```

### Options

The third argument accepts a duration number or an options object with the following additional properties on top of [KeyframeAnimationOptions](https://developer.mozilla.org/en-US/docs/Web/API/Element/animate#parameters):

```ts
import { useAnimate } from '@vueuse/core'

useAnimate(el, keyframes, {
  duration: 1000,
  // Start playing immediately (default: true)
  immediate: true,
  // Commit the end styling state to the element (default: false)
  commitStyles: false,
  // Persist the animation (default: false)
  persist: false,
  // Callback when animation is initialized
  onReady(animate) {
    console.log('Animation ready', animate)
  },
  // Callback when an error occurs
  onError(e) {
    console.error('Animation error', e)
  },
})
```

### Delaying Start

Set `immediate: false` to prevent the animation from starting automatically.

```ts
import { useAnimate } from '@vueuse/core'

const { play } = useAnimate(el, keyframes, {
  duration: 1000,
  immediate: false,
})

// Start the animation manually
play()
```

## Type Declarations

```ts
export interface UseAnimateOptions
  extends KeyframeAnimationOptions, ConfigurableWindow {
  /**
   * Will automatically run play when `useAnimate` is used
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Whether to commits the end styling state of an animation to the element being animated
   * In general, you should use `fill` option with this.
   *
   * @default false
   */
  commitStyles?: boolean
  /**
   * Whether to persists the animation
   *
   * @default false
   */
  persist?: boolean
  /**
   * Executed after animation initialization
   */
  onReady?: (animate: Animation) => void
  /**
   * Callback when error is caught.
   */
  onError?: (e: unknown) => void
}
export type UseAnimateKeyframes = MaybeRef<
  Keyframe[] | PropertyIndexedKeyframes | null
>
export interface UseAnimateReturn extends Supportable {
  animate: ShallowRef<Animation | undefined>
  play: () => void
  pause: () => void
  reverse: () => void
  finish: () => void
  cancel: () => void
  pending: ComputedRef<boolean>
  playState: ComputedRef<AnimationPlayState>
  replaceState: ComputedRef<AnimationReplaceState>
  startTime: WritableComputedRef<CSSNumberish | number | null>
  currentTime: WritableComputedRef<CSSNumberish | null>
  timeline: WritableComputedRef<AnimationTimeline | null>
  playbackRate: WritableComputedRef<number>
}
/**
 * Reactive Web Animations API
 *
 * @see https://vueuse.org/useAnimate
 * @param target
 * @param keyframes
 * @param options
 */
export declare function useAnimate(
  target: MaybeComputedElementRef,
  keyframes: UseAnimateKeyframes,
  options?: number | UseAnimateOptions,
): UseAnimateReturn
```

---

<!-- source: references/useArrayDifference.md -->
---
category: Array
---

# useArrayDifference

Reactive get array difference of two arrays.

By default, it returns the difference of the first array from the second array, so call `A \ B`, [Relative Complement](<https://en.wikipedia.org/wiki/Complement_(set_theory)>) of B in A.

You can pass the `symmetric` option to get the [Symmetric difference](https://en.wikipedia.org/wiki/Symmetric_difference) of two arrays `A △ B`.

## Usage

### Use with reactive array

```ts
import { useArrayDifference } from '@vueuse/core'

const list1 = ref([0, 1, 2, 3, 4, 5])
const list2 = ref([4, 5, 6])
const result = useArrayDifference(list1, list2)
// result.value: [0, 1, 2, 3]
list2.value = [0, 1, 2]
// result.value: [3, 4, 5]
```

### Use with reactive array and use function comparison

```ts
import { useArrayDifference } from '@vueuse/core'

const list1 = ref([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }])
const list2 = ref([{ id: 4 }, { id: 5 }, { id: 6 }])

const result = useArrayDifference(list1, list2, (value, othVal) => value.id === othVal.id)
// result.value: [{ id: 1 }, { id: 2 }, { id: 3 }]
```

### Symmetric Difference

This composable also supports [Symmetric difference](https://en.wikipedia.org/wiki/Symmetric_difference) by passing the `symmetric` option.

```ts {10}
import { useArrayDifference } from '@vueuse/core'

const list1 = ref([{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }, { id: 5 }])
const list2 = ref([{ id: 4 }, { id: 5 }, { id: 6 }])

const result = useArrayDifference(
  list1,
  list2,
  (value, othVal) => value.id === othVal.id,
  { symmetric: true }
)
// result.value: [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 6 }]
```

## Type Declarations

```ts
export interface UseArrayDifferenceOptions {
  /**
   * Returns asymmetric difference
   *
   * @see https://en.wikipedia.org/wiki/Symmetric_difference
   * @default false
   */
  symmetric?: boolean
}
export type UseArrayDifferenceReturn<T = any> = ComputedRef<T[]>
export declare function useArrayDifference<T>(
  list: MaybeRefOrGetter<T[]>,
  values: MaybeRefOrGetter<T[]>,
  key?: keyof T,
  options?: UseArrayDifferenceOptions,
): UseArrayDifferenceReturn<T>
export declare function useArrayDifference<T>(
  list: MaybeRefOrGetter<T[]>,
  values: MaybeRefOrGetter<T[]>,
  compareFn?: (value: T, othVal: T) => boolean,
  options?: UseArrayDifferenceOptions,
): UseArrayDifferenceReturn<T>
```

---

<!-- source: references/useArrayEvery.md -->
---
category: Array
---

# useArrayEvery

Reactive `Array.every`

## Usage

### Use with array of multiple refs

```ts
import { useArrayEvery } from '@vueuse/core'

const item1 = ref(0)
const item2 = ref(2)
const item3 = ref(4)
const item4 = ref(6)
const item5 = ref(8)
const list = [item1, item2, item3, item4, item5]
const result = useArrayEvery(list, i => i % 2 === 0)
// result.value: true
item1.value = 1
// result.value: false
```

### Use with reactive array

```ts
import { useArrayEvery } from '@vueuse/core'

const list = ref([0, 2, 4, 6, 8])
const result = useArrayEvery(list, i => i % 2 === 0)
// result.value: true
list.value.push(9)
// result.value: false
```

## Type Declarations

```ts
export type UseArrayEveryReturn = ComputedRef<boolean>
/**
 * Reactive `Array.every`
 *
 * @see https://vueuse.org/useArrayEvery
 * @param list - the array was called upon.
 * @param fn - a function to test each element.
 *
 * @returns **true** if the `fn` function returns a **truthy** value for every element from the array. Otherwise, **false**.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayEvery<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: MaybeRefOrGetter<T>[]) => unknown,
): UseArrayEveryReturn
```

---

<!-- source: references/useArrayFilter.md -->
---
category: Array
---

# useArrayFilter

Reactive `Array.filter`

## Usage

### Use with array of multiple refs

```ts
import { useArrayFilter } from '@vueuse/core'

const item1 = ref(0)
const item2 = ref(2)
const item3 = ref(4)
const item4 = ref(6)
const item5 = ref(8)
const list = [item1, item2, item3, item4, item5]
const result = useArrayFilter(list, i => i % 2 === 0)
// result.value: [0, 2, 4, 6, 8]
item2.value = 1
// result.value: [0, 4, 6, 8]
```

### Use with reactive array

```ts
import { useArrayFilter } from '@vueuse/core'

const list = ref([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
const result = useArrayFilter(list, i => i % 2 === 0)
// result.value: [0, 2, 4, 6, 8]
list.value.shift()
// result.value: [2, 4, 6, 8]
```

## Type Declarations

```ts
export type UseArrayFilterReturn<T = any> = ComputedRef<T[]>
/**
 * Reactive `Array.filter`
 *
 * @see https://vueuse.org/useArrayFilter
 * @param list - the array was called upon.
 * @param fn - a function that is called for every element of the given `list`. Each time `fn` executes, the returned value is added to the new array.
 *
 * @returns a shallow copy of a portion of the given array, filtered down to just the elements from the given array that pass the test implemented by the provided function. If no elements pass the test, an empty array will be returned.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayFilter<T, S extends T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: T[]) => element is S,
): UseArrayFilterReturn<S>
export declare function useArrayFilter<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: T[]) => unknown,
): UseArrayFilterReturn<T>
```

---

<!-- source: references/useArrayFind.md -->
---
category: Array
---

# useArrayFind

Reactive `Array.find`.

## Usage

```ts
import { useArrayFind } from '@vueuse/core'

const list = [ref(1), ref(-1), ref(2)]
const positive = useArrayFind(list, val => val > 0)
// positive.value: 1
```

### Use with reactive array

```ts
import { useArrayFind } from '@vueuse/core'

const list = reactive([-1, -2])
const positive = useArrayFind(list, val => val > 0)
// positive.value: undefined
list.push(1)
// positive.value: 1
```

## Type Declarations

```ts
export type UseArrayFindReturn<T = any> = ComputedRef<T | undefined>
/**
 * Reactive `Array.find`
 *
 * @see https://vueuse.org/useArrayFind
 * @param list - the array was called upon.
 * @param fn - a function to test each element.
 *
 * @returns the first element in the array that satisfies the provided testing function. Otherwise, undefined is returned.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayFind<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: MaybeRefOrGetter<T>[]) => boolean,
): UseArrayFindReturn<T>
```

---

<!-- source: references/useArrayFindIndex.md -->
---
category: Array
---

# useArrayFindIndex

Reactive `Array.findIndex`

## Usage

### Use with array of multiple refs

```ts
import { useArrayFindIndex } from '@vueuse/core'

const item1 = ref(0)
const item2 = ref(2)
const item3 = ref(4)
const item4 = ref(6)
const item5 = ref(8)
const list = [item1, item2, item3, item4, item5]
const result = useArrayFindIndex(list, i => i % 2 === 0)
// result.value: 0
item1.value = 1
// result.value: 1
```

### Use with reactive array

```ts
import { useArrayFindIndex } from '@vueuse/core'

const list = ref([0, 2, 4, 6, 8])
const result = useArrayFindIndex(list, i => i % 2 === 0)
// result.value: 0
list.value.unshift(-1)
// result.value: 1
```

## Type Declarations

```ts
export type UseArrayFindIndexReturn = ComputedRef<number>
/**
 * Reactive `Array.findIndex`
 *
 * @see https://vueuse.org/useArrayFindIndex
 * @param list - the array was called upon.
 * @param fn - a function to test each element.
 *
 * @returns the index of the first element in the array that passes the test. Otherwise, "-1".
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayFindIndex<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: MaybeRefOrGetter<T>[]) => unknown,
): UseArrayFindIndexReturn
```

---

<!-- source: references/useArrayFindLast.md -->
---
category: Array
---

# useArrayFindLast

Reactive `Array.findLast`.

## Usage

```ts
import { useArrayFindLast } from '@vueuse/core'

const list = [ref(1), ref(-1), ref(2)]
const positive = useArrayFindLast(list, val => val > 0)
// positive.value: 2
```

### Use with reactive array

```ts
import { useArrayFindLast } from '@vueuse/core'

const list = reactive([-1, -2])
const positive = useArrayFindLast(list, val => val > 0)
// positive.value: undefined
list.push(10)
// positive.value: 10
list.push(5)
// positive.value: 5
```

## Type Declarations

```ts
export type UseArrayFindLastReturn<T = any> = ComputedRef<T | undefined>
/**
 * Reactive `Array.findLast`
 *
 * @see https://vueuse.org/useArrayFindLast
 * @param list - the array was called upon.
 * @param fn - a function to test each element.
 *
 * @returns the last element in the array that satisfies the provided testing function. Otherwise, undefined is returned.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayFindLast<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: MaybeRefOrGetter<T>[]) => boolean,
): UseArrayFindLastReturn<T>
```

---

<!-- source: references/useArrayIncludes.md -->
---
category: Array
---

# useArrayIncludes

Reactive `Array.includes`

## Usage

### Use with reactive array

```ts
import { useArrayIncludes } from '@vueuse/core'

const list = ref([0, 2, 4, 6, 8])
const result = useArrayIncludes(list, 10)
// result.value: false
list.value.push(10)
// result.value: true
list.value.pop()
// result.value: false
```

## Type Declarations

```ts
export type UseArrayIncludesComparatorFn<T, V> = (
  element: T,
  value: V,
  index: number,
  array: MaybeRefOrGetter<T>[],
) => boolean
export interface UseArrayIncludesOptions<T, V> {
  fromIndex?: number
  comparator?: UseArrayIncludesComparatorFn<T, V> | keyof T
}
export type UseArrayIncludesReturn = ComputedRef<boolean>
/**
 * Reactive `Array.includes`
 *
 * @see https://vueuse.org/useArrayIncludes
 *
 * @returns true if the `value` is found in the array. Otherwise, false.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayIncludes<T, V = any>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  value: MaybeRefOrGetter<V>,
  comparator?: UseArrayIncludesComparatorFn<T, V>,
): UseArrayIncludesReturn
export declare function useArrayIncludes<T, V = any>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  value: MaybeRefOrGetter<V>,
  comparator?: keyof T,
): UseArrayIncludesReturn
export declare function useArrayIncludes<T, V = any>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  value: MaybeRefOrGetter<V>,
  options?: UseArrayIncludesOptions<T, V>,
): UseArrayIncludesReturn
```

---

<!-- source: references/useArrayJoin.md -->
---
category: Array
---

# useArrayJoin

Reactive `Array.join`

## Usage

### Use with array of multiple refs

```ts
import { useArrayJoin } from '@vueuse/core'

const item1 = ref('foo')
const item2 = ref(0)
const item3 = ref({ prop: 'val' })
const list = [item1, item2, item3]
const result = useArrayJoin(list)
// result.value: foo,0,[object Object]
item1.value = 'bar'
// result.value: bar,0,[object Object]
```

### Use with reactive array

```ts
import { useArrayJoin } from '@vueuse/core'

const list = ref(['string', 0, { prop: 'val' }, false, [1], [[2]], null, undefined, []])
const result = useArrayJoin(list)
// result.value: string,0,[object Object],false,1,2,,,
list.value.push(true)
// result.value: string,0,[object Object],false,1,2,,,,true
list.value = [null, 'string', undefined]
// result.value: ,string,
```

### Use with reactive separator

```ts
import { useArrayJoin } from '@vueuse/core'

const list = ref(['string', 0, { prop: 'val' }])
const separator = ref()
const result = useArrayJoin(list, separator)
// result.value: string,0,[object Object]
separator.value = ''
// result.value: string0[object Object]
separator.value = '--'
// result.value: string--0--[object Object]
```

## Type Declarations

```ts
export type UseArrayJoinReturn = ComputedRef<string>
/**
 * Reactive `Array.join`
 *
 * @see https://vueuse.org/useArrayJoin
 * @param list - the array was called upon.
 * @param separator - a string to separate each pair of adjacent elements of the array. If omitted, the array elements are separated with a comma (",").
 *
 * @returns a string with all array elements joined. If arr.length is 0, the empty string is returned.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayJoin(
  list: MaybeRefOrGetter<MaybeRefOrGetter<any>[]>,
  separator?: MaybeRefOrGetter<string>,
): UseArrayJoinReturn
```

---

<!-- source: references/useArrayMap.md -->
---
category: Array
---

# useArrayMap

Reactive `Array.map`

## Usage

### Use with array of multiple refs

```ts
import { useArrayMap } from '@vueuse/core'

const item1 = ref(0)
const item2 = ref(2)
const item3 = ref(4)
const item4 = ref(6)
const item5 = ref(8)
const list = [item1, item2, item3, item4, item5]
const result = useArrayMap(list, i => i * 2)
// result.value: [0, 4, 8, 12, 16]
item1.value = 1
// result.value: [2, 4, 8, 12, 16]
```

### Use with reactive array

```ts
import { useArrayMap } from '@vueuse/core'

const list = ref([0, 1, 2, 3, 4])
const result = useArrayMap(list, i => i * 2)
// result.value: [0, 2, 4, 6, 8]
list.value.pop()
// result.value: [0, 2, 4, 6]
```

## Type Declarations

```ts
export type UseArrayMapReturn<T = any> = ComputedRef<T[]>
/**
 * Reactive `Array.map`
 *
 * @see https://vueuse.org/useArrayMap
 * @param list - the array was called upon.
 * @param fn - a function that is called for every element of the given `list`. Each time `fn` executes, the returned value is added to the new array.
 *
 * @returns a new array with each element being the result of the callback function.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayMap<T, U = T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: T[]) => U,
): UseArrayMapReturn<U>
```

---

<!-- source: references/useArrayReduce.md -->
---
category: Array
---

# useArrayReduce

Reactive `Array.reduce`.

## Usage

```ts
import { useArrayReduce } from '@vueuse/core'

const sum = useArrayReduce([ref(1), ref(2), ref(3)], (sum, val) => sum + val)
// sum.value: 6
```

### Use with reactive array

```ts
import { useArrayReduce } from '@vueuse/core'

const list = reactive([1, 2])
const sum = useArrayReduce(list, (sum, val) => sum + val)

list.push(3)
// sum.value: 6
```

### Use with initialValue

```ts
import { useArrayReduce } from '@vueuse/core'

const list = reactive([{ num: 1 }, { num: 2 }])
const sum = useArrayReduce(list, (sum, val) => sum + val.num, 0)
// sum.value: 3
```

## Type Declarations

```ts
export type UseArrayReducer<PV, CV, R> = (
  previousValue: PV,
  currentValue: CV,
  currentIndex: number,
) => R
export type UseArrayReduceReturn<T = any> = ComputedRef<T>
/**
 * Reactive `Array.reduce`
 *
 * @see https://vueuse.org/useArrayReduce
 * @param list - the array was called upon.
 * @param reducer - a "reducer" function.
 *
 * @returns the value that results from running the "reducer" callback function to completion over the entire array.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayReduce<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  reducer: UseArrayReducer<T, T, T>,
): UseArrayReduceReturn<T>
/**
 * Reactive `Array.reduce`
 *
 * @see https://vueuse.org/useArrayReduce
 * @param list - the array was called upon.
 * @param reducer - a "reducer" function.
 * @param initialValue - a value to be initialized the first time when the callback is called.
 *
 * @returns the value that results from running the "reducer" callback function to completion over the entire array.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayReduce<T, U>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  reducer: UseArrayReducer<U, T, U>,
  initialValue: MaybeRefOrGetter<U>,
): UseArrayReduceReturn<U>
```

---

<!-- source: references/useArraySome.md -->
---
category: Array
---

# useArraySome

Reactive `Array.some`

## Usage

### Use with array of multiple refs

```ts
import { useArraySome } from '@vueuse/core'

const item1 = ref(0)
const item2 = ref(2)
const item3 = ref(4)
const item4 = ref(6)
const item5 = ref(8)
const list = [item1, item2, item3, item4, item5]
const result = useArraySome(list, i => i > 10)
// result.value: false
item1.value = 11
// result.value: true
```

### Use with reactive array

```ts
import { useArraySome } from '@vueuse/core'

const list = ref([0, 2, 4, 6, 8])
const result = useArraySome(list, i => i > 10)
// result.value: false
list.value.push(11)
// result.value: true
```

## Type Declarations

```ts
export type UseArraySomeReturn = ComputedRef<boolean>
/**
 * Reactive `Array.some`
 *
 * @see https://vueuse.org/useArraySome
 * @param list - the array was called upon.
 * @param fn - a function to test each element.
 *
 * @returns **true** if the `fn` function returns a **truthy** value for any element from the array. Otherwise, **false**.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArraySome<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  fn: (element: T, index: number, array: MaybeRefOrGetter<T>[]) => unknown,
): UseArraySomeReturn
```

---

<!-- source: references/useArrayUnique.md -->
---
category: Array
---

# useArrayUnique

reactive unique array

## Usage

### Use with array of multiple refs

```ts
import { useArrayUnique } from '@vueuse/core'

const item1 = ref(0)
const item2 = ref(1)
const item3 = ref(1)
const item4 = ref(2)
const item5 = ref(3)
const list = [item1, item2, item3, item4, item5]
const result = useArrayUnique(list)
// result.value: [0, 1, 2, 3]
item5.value = 1
// result.value: [0, 1, 2]
```

### Use with reactive array

```ts
import { useArrayUnique } from '@vueuse/core'

const list = reactive([1, 2, 2, 3])
const result = useArrayUnique(list)
// result.value: [1, 2, 3]

list.push(1)
// result.value: [1, 2, 3]
```

### Use with custom function

```ts
import { useArrayUnique } from '@vueuse/core'

const list = reactive([
  { id: 1, name: 'foo' },
  { id: 2, name: 'bar' },
  { id: 1, name: 'baz' },
])

const result = useArrayUnique(list, (a, b) => a.id === b.id)
// result.value: [{ id: 1, name: 'foo' }, { id: 2, name: 'bar' }]

list.push({ id: 1, name: 'qux' })
// result.value: [{ id: 1, name: 'foo' }, { id: 2, name: 'bar' }]
```

## Type Declarations

```ts
export type UseArrayUniqueReturn<T = any> = ComputedRef<T[]>
/**
 * reactive unique array
 * @see https://vueuse.org/useArrayUnique
 * @param list - the array was called upon.
 * @param compareFn
 * @returns A computed ref that returns a unique array of items.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useArrayUnique<T>(
  list: MaybeRefOrGetter<MaybeRefOrGetter<T>[]>,
  compareFn?: (a: T, b: T, array: T[]) => boolean,
): UseArrayUniqueReturn<T>
```

---

<!-- source: references/useAsyncQueue.md -->
---
category: Utilities
---

# useAsyncQueue

Executes each asynchronous task sequentially and passes the current task result to the next task.

## Usage

```ts
import { useAsyncQueue } from '@vueuse/core'

function p1() {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(1000)
    }, 10)
  })
}

function p2(result: number) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(1000 + result)
    }, 20)
  })
}

const { activeIndex, result } = useAsyncQueue([p1, p2])

console.log(activeIndex.value) // current pending task index

console.log(result) // the tasks result
```

### Result State

Each task in the result array has a `state` and `data` property:

```ts
interface UseAsyncQueueResult<T> {
  state: 'aborted' | 'fulfilled' | 'pending' | 'rejected'
  data: T | null
}
```

### Interrupt on Failure

By default, if a task fails, subsequent tasks will not be executed. Set `interrupt: false` to continue executing even after failures.

```ts
const { result } = useAsyncQueue([p1, p2], {
  interrupt: false, // continue even if p1 fails
})
```

### Callbacks

```ts
const { result } = useAsyncQueue([p1, p2], {
  onError() {
    console.log('A task failed')
  },
  onFinished() {
    console.log('All tasks completed (or interrupted)')
  },
})
```

### Abort Signal

You can pass an `AbortSignal` to cancel the queue execution.

```ts
const controller = new AbortController()

const { result } = useAsyncQueue([p1, p2], {
  signal: controller.signal,
})

// Later, abort the queue
controller.abort()
```

## Type Declarations

```ts
export type UseAsyncQueueTask<T> = (...args: any[]) => T | Promise<T>
type MapQueueTask<T extends any[]> = {
  [K in keyof T]: UseAsyncQueueTask<T[K]>
}
export interface UseAsyncQueueResult<T> {
  state: "aborted" | "fulfilled" | "pending" | "rejected"
  data: T | null
}
export interface UseAsyncQueueReturn<T> {
  activeIndex: ShallowRef<number>
  result: T
}
export interface UseAsyncQueueOptions {
  /**
   * Interrupt tasks when current task fails.
   *
   * @default true
   */
  interrupt?: boolean
  /**
   * Trigger it when the tasks fails.
   *
   */
  onError?: () => void
  /**
   * Trigger it when the tasks ends.
   *
   */
  onFinished?: () => void
  /**
   * A AbortSignal that can be used to abort the task.
   */
  signal?: AbortSignal
}
/**
 * Asynchronous queue task controller.
 *
 * @see https://vueuse.org/useAsyncQueue
 * @param tasks
 * @param options
 */
export declare function useAsyncQueue<T extends any[], S = MapQueueTask<T>>(
  tasks: S & Array<UseAsyncQueueTask<any>>,
  options?: UseAsyncQueueOptions,
): UseAsyncQueueReturn<{
  [P in keyof T]: UseAsyncQueueResult<T[P]>
}>
```

---

<!-- source: references/useAsyncState.md -->
---
category: State
---

# useAsyncState

Reactive async state. Will not block your setup function and will trigger changes once the promise is ready. The state is a `shallowRef` by default.

## Usage

```ts
import { useAsyncState } from '@vueuse/core'
import axios from 'axios'

const { state, isReady, isLoading, error } = useAsyncState(
  axios
    .get('https://jsonplaceholder.typicode.com/todos/1')
    .then(t => t.data),
  { id: null },
)
```

### Return Values

| Property           | Description                                         |
| ------------------ | --------------------------------------------------- |
| `state`            | The result of the async function                    |
| `isReady`          | `true` when the promise has resolved at least once  |
| `isLoading`        | `true` while the promise is pending                 |
| `error`            | The error if the promise was rejected               |
| `execute`          | Re-execute the async function with optional delay   |
| `executeImmediate` | Re-execute immediately (shorthand for `execute(0)`) |

### Awaiting the Result

The return value is thenable, so you can await it in async functions or `<script setup>`:

```ts
const { state, isReady } = await useAsyncState(fetchData, null)
// `state` is now populated, `isReady` is true
```

### Manual Execution

Set `immediate: false` to prevent automatic execution on creation.

```vue
<script setup lang="ts">
import { useAsyncState } from '@vueuse/core'

const { state, execute, executeImmediate } = useAsyncState(action, '', { immediate: false })

async function action(event) {
  await new Promise(resolve => setTimeout(resolve, 500))
  return `${event.target.textContent} clicked!`
}
</script>

<template>
  <p>State: {{ state }}</p>

  <button class="button" @click="executeImmediate">
    Execute now
  </button>

  <button class="ml-2 button" @click="event => execute(500, event)">
    Execute with delay
  </button>
</template>
```

### Options

```ts
const { state } = useAsyncState(promise, initialState, {
  // Execute immediately on creation (default: true)
  immediate: true,
  // Delay before first execution in ms (default: 0)
  delay: 0,
  // Reset state to initial before each execution (default: true)
  resetOnExecute: true,
  // Use shallowRef for state (default: true)
  shallow: true,
  // Throw errors instead of catching them (default: false)
  throwError: false,
  // Called when promise resolves
  onSuccess(data) {
    console.log('Success:', data)
  },
  // Called when promise rejects
  onError(error) {
    console.error('Error:', error)
  },
})
```

## Type Declarations

```ts
export interface UseAsyncStateReturnBase<
  Data,
  Params extends any[],
  Shallow extends boolean,
> {
  state: Shallow extends true ? Ref<Data> : Ref<UnwrapRef<Data>>
  isReady: Ref<boolean>
  isLoading: Ref<boolean>
  error: Ref<unknown>
  execute: (delay?: number, ...args: Params) => Promise<Data | undefined>
  executeImmediate: (...args: Params) => Promise<Data | undefined>
}
export type UseAsyncStateReturn<
  Data,
  Params extends any[],
  Shallow extends boolean,
> = UseAsyncStateReturnBase<Data, Params, Shallow> &
  PromiseLike<UseAsyncStateReturnBase<Data, Params, Shallow>>
export interface UseAsyncStateOptions<Shallow extends boolean, D = any> {
  /**
   * Delay for the first execution of the promise when "immediate" is true. In milliseconds.
   *
   * @default 0
   */
  delay?: number
  /**
   * Execute the promise right after the function is invoked.
   * Will apply the delay if any.
   *
   * When set to false, you will need to execute it manually.
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Callback when error is caught.
   */
  onError?: (e: unknown) => void
  /**
   * Callback when success is caught.
   * @param {D} data
   */
  onSuccess?: (data: D) => void
  /**
   * Sets the state to initialState before executing the promise.
   *
   * This can be useful when calling the execute function more than once (for
   * example, to refresh data). When set to false, the current state remains
   * unchanged until the promise resolves.
   *
   * @default true
   */
  resetOnExecute?: boolean
  /**
   * Use shallowRef.
   *
   * @default true
   */
  shallow?: Shallow
  /**
   *
   * An error is thrown when executing the execute function
   *
   * @default false
   */
  throwError?: boolean
}
/**
 * Reactive async state. Will not block your setup function and will trigger changes once
 * the promise is ready.
 *
 * @see https://vueuse.org/useAsyncState
 * @param promise         The promise / async function to be resolved
 * @param initialState    The initial state, used until the first evaluation finishes
 * @param options
 */
export declare function useAsyncState<
  Data,
  Params extends any[] = any[],
  Shallow extends boolean = true,
>(
  promise: Promise<Data> | ((...args: Params) => Promise<Data>),
  initialState: MaybeRef<Data>,
  options?: UseAsyncStateOptions<Shallow, Data>,
): UseAsyncStateReturn<Data, Params, Shallow>
```

---

<!-- source: references/useAsyncValidator.md -->
---
category: '@Integrations'
---

# useAsyncValidator

Wrapper for [`async-validator`](https://github.com/yiminghe/async-validator).

## Install

```bash
npm i async-validator@^4
```

## Usage

```ts
import { useAsyncValidator } from '@vueuse/integrations/useAsyncValidator'
```

## Type Declarations

```ts
export type AsyncValidatorError = Error & {
  errors: ValidateError[]
  fields: Record<string, ValidateError[]>
}
export interface UseAsyncValidatorExecuteReturn {
  pass: boolean
  errors: AsyncValidatorError["errors"] | undefined
  errorInfo: AsyncValidatorError | null
  errorFields: AsyncValidatorError["fields"] | undefined
}
export interface UseAsyncValidatorReturn {
  pass: ShallowRef<boolean>
  isFinished: ShallowRef<boolean>
  errors: ComputedRef<AsyncValidatorError["errors"] | undefined>
  errorInfo: ShallowRef<AsyncValidatorError | null>
  errorFields: ComputedRef<AsyncValidatorError["fields"] | undefined>
  execute: () => Promise<UseAsyncValidatorExecuteReturn>
}
export interface UseAsyncValidatorOptions {
  /**
   * @see https://github.com/yiminghe/async-validator#options
   */
  validateOption?: ValidateOption
  /**
   * The validation will be triggered right away for the first time.
   * Only works when `manual` is not set to true.
   *
   * @default true
   */
  immediate?: boolean
  /**
   * If set to true, the validation will not be triggered automatically.
   */
  manual?: boolean
}
/**
 * Wrapper for async-validator.
 *
 * @see https://vueuse.org/useAsyncValidator
 * @see https://github.com/yiminghe/async-validator
 */
export declare function useAsyncValidator(
  value: MaybeRefOrGetter<Record<string, any>>,
  rules: MaybeRefOrGetter<Rules>,
  options?: UseAsyncValidatorOptions,
): UseAsyncValidatorReturn & PromiseLike<UseAsyncValidatorReturn>
```

---

<!-- source: references/useAuth.md -->
---
category: '@Firebase'
---

# useAuth

Reactive [Firebase Auth](https://firebase.google.com/docs/auth) binding. It provides a reactive `user` and `isAuthenticated` so you
can easily react to changes in the users' authentication status.

## Usage

```vue
<script setup lang="ts">
import { useAuth } from '@vueuse/firebase/useAuth'
import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider, signInWithPopup } from 'firebase/auth'

const app = initializeApp({ /* config */ })
const auth = getAuth(app)
const { isAuthenticated, user } = useAuth(auth)

const signIn = () => signInWithPopup(auth, new GoogleAuthProvider())
</script>

<template>
  <pre v-if="isAuthenticated">{{ user }}</pre>
  <div v-else>
    <button @click="signIn">
      Sign In with Google
    </button>
  </div>
</template>
```

## Return Values

| Name              | Type                   | Description                                               |
| ----------------- | ---------------------- | --------------------------------------------------------- |
| `user`            | `Ref<User \| null>`    | The current Firebase user, or `null` if not authenticated |
| `isAuthenticated` | `ComputedRef<boolean>` | Whether a user is currently authenticated                 |

The composable automatically updates when the user's ID token changes (including sign-in, sign-out, and token refresh events) using Firebase's `onIdTokenChanged` listener.

## Type Declarations

```ts
export interface UseFirebaseAuthOptions {
  isAuthenticated: ComputedRef<boolean>
  user: Ref<User | null>
}
/**
 * Reactive Firebase Auth binding
 *
 * @see https://vueuse.org/useAuth
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useAuth(auth: Auth): {
  isAuthenticated: ComputedRef<boolean>
  user: Ref<
    {
      readonly emailVerified: boolean
      readonly isAnonymous: boolean
      readonly metadata: {
        readonly creationTime?: string | undefined
        readonly lastSignInTime?: string | undefined
      }
      readonly providerData: {
        readonly displayName: string | null
        readonly email: string | null
        readonly phoneNumber: string | null
        readonly photoURL: string | null
        readonly providerId: string
        readonly uid: string
      }[]
      readonly refreshToken: string
      readonly tenantId: string | null
      delete: () => Promise<void>
      getIdToken: (forceRefresh?: boolean) => Promise<string>
      getIdTokenResult: (forceRefresh?: boolean) => Promise<IdTokenResult>
      reload: () => Promise<void>
      toJSON: () => object
      readonly displayName: string | null
      readonly email: string | null
      readonly phoneNumber: string | null
      readonly photoURL: string | null
      readonly providerId: string
      readonly uid: string
    } | null,
    | User
    | {
        readonly emailVerified: boolean
        readonly isAnonymous: boolean
        readonly metadata: {
          readonly creationTime?: string | undefined
          readonly lastSignInTime?: string | undefined
        }
        readonly providerData: {
          readonly displayName: string | null
          readonly email: string | null
          readonly phoneNumber: string | null
          readonly photoURL: string | null
          readonly providerId: string
          readonly uid: string
        }[]
        readonly refreshToken: string
        readonly tenantId: string | null
        delete: () => Promise<void>
        getIdToken: (forceRefresh?: boolean) => Promise<string>
        getIdTokenResult: (forceRefresh?: boolean) => Promise<IdTokenResult>
        reload: () => Promise<void>
        toJSON: () => object
        readonly displayName: string | null
        readonly email: string | null
        readonly phoneNumber: string | null
        readonly photoURL: string | null
        readonly providerId: string
        readonly uid: string
      }
    | null
  >
}
```

---

<!-- source: references/useAverage.md -->
---
category: '@Math'
---

# useAverage

Get the average of an array reactively.

## Usage

```ts
import { useAverage } from '@vueuse/math'

const list = ref([1, 2, 3])
const averageValue = useAverage(list) // Ref<2>
```

```ts
import { useAverage } from '@vueuse/math'

const a = ref(1)
const b = ref(3)

const averageValue = useAverage(a, b) // Ref<2>
```

## Type Declarations

```ts
export declare function useAverage(
  array: MaybeRefOrGetter<MaybeRefOrGetter<number>[]>,
): ComputedRef<number>
export declare function useAverage(
  ...args: MaybeRefOrGetter<number>[]
): ComputedRef<number>
```

---

<!-- source: references/useAxios.md -->
---
category: '@Integrations'
---

# useAxios

Wrapper for [`axios`](https://github.com/axios/axios).

## Install

```bash
npm i axios@^1
```

## Usage

```ts
import { useAxios } from '@vueuse/integrations/useAxios'

const { data, isFinished } = useAxios('/api/posts')
```

### Return Values

| Property           | Type                         | Description                              |
| ------------------ | ---------------------------- | ---------------------------------------- |
| `data`             | `Ref<T>`                     | Response data                            |
| `response`         | `Ref<AxiosResponse>`         | Full axios response                      |
| `error`            | `Ref<unknown>`               | Error if request failed                  |
| `isFinished`       | `Ref<boolean>`               | Request has completed (success or error) |
| `isLoading`        | `Ref<boolean>`               | Request is in progress                   |
| `isAborted`        | `Ref<boolean>`               | Request was aborted                      |
| `abort` / `cancel` | `() => void`                 | Abort the current request                |
| `execute`          | `(url?, config?) => Promise` | Execute/re-execute the request           |

### With Axios Instance

```ts
import { useAxios } from '@vueuse/integrations/useAxios'
import axios from 'axios'

const instance = axios.create({
  baseURL: '/api',
})

const { data, isFinished } = useAxios('/posts', instance)
```

### With Config Options

```ts
import { useAxios } from '@vueuse/integrations/useAxios'
import axios from 'axios'

const instance = axios.create({
  baseURL: '/api',
})

const { data, isFinished } = useAxios('/posts', { method: 'POST' }, instance)
```

### Manual Execution

When you don't pass a `url`, the request won't fire immediately:

```ts
import { useAxios } from '@vueuse/integrations/useAxios'

const { execute } = useAxios()
execute(url)
```

The `execute` function `url` is optional - `url2` will replace `url1`:

```ts
import { useAxios } from '@vueuse/integrations/useAxios'

const { execute } = useAxios(url1, {}, { immediate: false })
execute(url2)
```

The `execute` function can accept config only:

```ts
import { useAxios } from '@vueuse/integrations/useAxios'

const { execute } = useAxios(url1, { method: 'GET' }, { immediate: false })
execute({ params: { key: 1 } })
execute({ params: { key: 2 } })
```

### Awaiting Results

The return value is thenable, so you can await it:

```ts
import { useAxios } from '@vueuse/integrations/useAxios'

const { data, isFinished, error } = await useAxios('/api/posts')
// data is now populated
```

Or await the execute function:

```ts
import { useAxios } from '@vueuse/integrations/useAxios'

const { execute } = useAxios()
const result = await execute(url)
```

### Options

```ts
const { data } = useAxios('/api/posts', config, instance, {
  // Execute immediately (default: true if url provided)
  immediate: true,
  // Use shallowRef for data (default: true)
  shallow: true,
  // Abort previous request on new execute (default: true)
  abortPrevious: true,
  // Reset data before executing (default: false)
  resetOnExecute: false,
  // Initial data value
  initialData: [],
  // Callbacks
  onSuccess: data => console.log('Success:', data),
  onError: error => console.error('Error:', error),
  onFinish: () => console.log('Finished'),
})
```

## Type Declarations

```ts
export interface UseAxiosReturn<
  T,
  R = AxiosResponse<T>,
  _D = any,
  O extends UseAxiosOptions = UseAxiosOptions<T>,
> {
  /**
   * Axios Response
   */
  response: ShallowRef<R | undefined>
  /**
   * Axios response data
   */
  data: O extends UseAxiosOptionsWithInitialData<T>
    ? Ref<T>
    : Ref<T | undefined>
  /**
   * Indicates if the request has finished
   */
  isFinished: Ref<boolean>
  /**
   * Indicates if the request is currently loading
   */
  isLoading: Ref<boolean>
  /**
   * Indicates if the request was canceled
   */
  isAborted: Ref<boolean>
  /**
   * Any errors that may have occurred
   */
  error: ShallowRef<unknown | undefined>
  /**
   * Aborts the current request
   */
  abort: (message?: string | undefined) => void
  /**
   * Alias to `abort`
   */
  cancel: (message?: string | undefined) => void
  /**
   * Alias to `isAborted`
   */
  isCanceled: Ref<boolean>
}
export interface StrictUseAxiosReturn<
  T,
  R,
  D,
  O extends UseAxiosOptions = UseAxiosOptions<T>,
> extends UseAxiosReturn<T, R, D, O> {
  /**
   * Manually call the axios request
   */
  execute: (
    url?: string | AxiosRequestConfig<D>,
    config?: AxiosRequestConfig<D>,
  ) => Promise<StrictUseAxiosReturn<T, R, D, O>>
}
export interface EasyUseAxiosReturn<T, R, D> extends UseAxiosReturn<T, R, D> {
  /**
   * Manually call the axios request
   */
  execute: (
    url: string,
    config?: AxiosRequestConfig<D>,
  ) => Promise<EasyUseAxiosReturn<T, R, D>>
}
export interface UseAxiosOptionsBase<T = any> {
  /**
   * Will automatically run axios request when `useAxios` is used
   *
   */
  immediate?: boolean
  /**
   * Use shallowRef.
   *
   * @default true
   */
  shallow?: boolean
  /**
   * Abort previous request when a new request is made.
   *
   * @default true
   */
  abortPrevious?: boolean
  /**
   * Callback when error is caught.
   */
  onError?: (e: unknown) => void
  /**
   * Callback when success is caught.
   */
  onSuccess?: (data: T) => void
  /**
   * Sets the state to initialState before executing the promise.
   */
  resetOnExecute?: boolean
  /**
   * Callback when request is finished.
   */
  onFinish?: () => void
}
export interface UseAxiosOptionsWithInitialData<
  T,
> extends UseAxiosOptionsBase<T> {
  /**
   * Initial data
   */
  initialData: T
}
export type UseAxiosOptions<T = any> =
  | UseAxiosOptionsBase<T>
  | UseAxiosOptionsWithInitialData<T>
export declare function useAxios<
  T = any,
  R = AxiosResponse<T>,
  D = any,
  O extends UseAxiosOptionsWithInitialData<T> =
    UseAxiosOptionsWithInitialData<T>,
>(
  url: string,
  config?: AxiosRequestConfig<D>,
  options?: O,
): StrictUseAxiosReturn<T, R, D, O> & Promise<StrictUseAxiosReturn<T, R, D, O>>
export declare function useAxios<
  T = any,
  R = AxiosResponse<T>,
  D = any,
  O extends UseAxiosOptionsWithInitialData<T> =
    UseAxiosOptionsWithInitialData<T>,
>(
  url: string,
  instance?: AxiosInstance,
  options?: O,
): StrictUseAxiosReturn<T, R, D, O> & Promise<StrictUseAxiosReturn<T, R, D, O>>
export declare function useAxios<
  T = any,
  R = AxiosResponse<T>,
  D = any,
  O extends UseAxiosOptionsWithInitialData<T> =
    UseAxiosOptionsWithInitialData<T>,
>(
  url: string,
  config: AxiosRequestConfig<D>,
  instance: AxiosInstance,
  options?: O,
): StrictUseAxiosReturn<T, R, D, O> & Promise<StrictUseAxiosReturn<T, R, D, O>>
export declare function useAxios<
  T = any,
  R = AxiosResponse<T>,
  D = any,
  O extends UseAxiosOptionsBase<T> = UseAxiosOptionsBase<T>,
>(
  url: string,
  config?: AxiosRequestConfig<D>,
  options?: O,
): StrictUseAxiosReturn<T, R, D, O> & Promise<StrictUseAxiosReturn<T, R, D, O>>
export declare function useAxios<
  T = any,
  R = AxiosResponse<T>,
  D = any,
  O extends UseAxiosOptionsBase<T> = UseAxiosOptionsBase<T>,
>(
  url: string,
  instance?: AxiosInstance,
  options?: O,
): StrictUseAxiosReturn<T, R, D, O> & Promise<StrictUseAxiosReturn<T, R, D, O>>
export declare function useAxios<
  T = any,
  R = AxiosResponse<T>,
  D = any,
  O extends UseAxiosOptionsBase<T> = UseAxiosOptionsBase<T>,
>(
  url: string,
  config: AxiosRequestConfig<D>,
  instance: AxiosInstance,
  options?: O,
): StrictUseAxiosReturn<T, R, D, O> & Promise<StrictUseAxiosReturn<T, R, D, O>>
export declare function useAxios<T = any, R = AxiosResponse<T>, D = any>(
  config?: AxiosRequestConfig<D>,
): EasyUseAxiosReturn<T, R, D> & Promise<EasyUseAxiosReturn<T, R, D>>
export declare function useAxios<T = any, R = AxiosResponse<T>, D = any>(
  instance?: AxiosInstance,
): EasyUseAxiosReturn<T, R, D> & Promise<EasyUseAxiosReturn<T, R, D>>
export declare function useAxios<T = any, R = AxiosResponse<T>, D = any>(
  config?: AxiosRequestConfig<D>,
  instance?: AxiosInstance,
): EasyUseAxiosReturn<T, R, D> & Promise<EasyUseAxiosReturn<T, R, D>>
```

---

<!-- source: references/useBase64.md -->
---
category: Utilities
---

# useBase64

Reactive base64 transforming. Supports plain text, buffer, files, canvas, objects, maps, sets and images.

## Usage

```ts
import { useBase64 } from '@vueuse/core'
import { shallowRef } from 'vue'

const text = shallowRef('')

const { base64, promise, execute } = useBase64(text)
```

### Supported Input Types

- `string` - Plain text
- `Blob` - File or blob data
- `ArrayBuffer` - Binary data
- `HTMLCanvasElement` - Canvas element
- `HTMLImageElement` - Image element
- `Object` / `Array` / `Map` / `Set` - Serialized to JSON

### Return Values

| Property  | Description                               |
| --------- | ----------------------------------------- |
| `base64`  | The resulting base64 string               |
| `promise` | The promise of the current transformation |
| `execute` | Manually trigger the transformation       |

### Data URL Format

By default, the output is in Data URL format (e.g., `data:text/plain;base64,...`). Set `dataUrl: false` to get raw base64.

```ts
const { base64 } = useBase64(text, { dataUrl: false })
// Returns raw base64 without the data URL prefix
```

### Canvas and Image Options

When transforming canvas or image elements, you can specify the MIME type and quality.

```ts
const canvas = document.querySelector('canvas')

const { base64 } = useBase64(canvas, {
  type: 'image/jpeg', // MIME type
  quality: 0.8, // Image quality (0-1, for jpeg/webp)
})
```

### Custom Serializer

For objects, arrays, maps and sets, you can provide a custom serializer. Otherwise, the data will be serialized using `JSON.stringify` (maps are converted to objects, sets to arrays).

```ts
const data = shallowRef({ foo: 'bar' })

const { base64 } = useBase64(data, {
  serializer: v => JSON.stringify(v, null, 2),
})
```

## Type Declarations

```ts
export interface UseBase64Options {
  /**
   * Output as Data URL format
   *
   * @default true
   */
  dataUrl?: boolean
}
export interface ToDataURLOptions extends UseBase64Options {
  /**
   * MIME type
   */
  type?: string | undefined
  /**
   * Image quality of jpeg or webp
   */
  quality?: any
}
export interface UseBase64ObjectOptions<T> extends UseBase64Options {
  serializer?: (v: T) => string
}
export interface UseBase64Return {
  base64: ShallowRef<string>
  promise: ShallowRef<Promise<string>>
  execute: () => Promise<string>
}
export declare function useBase64(
  target: MaybeRefOrGetter<string | undefined>,
  options?: UseBase64Options,
): UseBase64Return
export declare function useBase64(
  target: MaybeRefOrGetter<Blob | undefined>,
  options?: UseBase64Options,
): UseBase64Return
export declare function useBase64(
  target: MaybeRefOrGetter<ArrayBuffer | undefined>,
  options?: UseBase64Options,
): UseBase64Return
export declare function useBase64(
  target: MaybeRefOrGetter<HTMLCanvasElement | undefined>,
  options?: ToDataURLOptions,
): UseBase64Return
export declare function useBase64(
  target: MaybeRefOrGetter<HTMLImageElement | undefined>,
  options?: ToDataURLOptions,
): UseBase64Return
export declare function useBase64<T extends Record<string, unknown>>(
  target: MaybeRefOrGetter<T>,
  options?: UseBase64ObjectOptions<T>,
): UseBase64Return
export declare function useBase64<T extends Map<string, unknown>>(
  target: MaybeRefOrGetter<T>,
  options?: UseBase64ObjectOptions<T>,
): UseBase64Return
export declare function useBase64<T extends Set<unknown>>(
  target: MaybeRefOrGetter<T>,
  options?: UseBase64ObjectOptions<T>,
): UseBase64Return
export declare function useBase64<T>(
  target: MaybeRefOrGetter<T[]>,
  options?: UseBase64ObjectOptions<T[]>,
): UseBase64Return
```

---

<!-- source: references/useBattery.md -->
---
category: Sensors
---

# useBattery

Reactive [Battery Status API](https://developer.mozilla.org/en-US/docs/Web/API/Battery_Status_API), more often referred to as the Battery API, provides information about the system's battery charge level and lets you be notified by events that are sent when the battery level or charging status change. This can be used to adjust your app's resource usage to reduce battery drain when the battery is low, or to save changes before the battery runs out in order to prevent data loss.

## Usage

```ts
import { useBattery } from '@vueuse/core'

const { isSupported, charging, chargingTime, dischargingTime, level } = useBattery()
```

| State           | Type      | Description                                                       |
| --------------- | --------- | ----------------------------------------------------------------- |
| isSupported     | `Boolean` | If the Battery Status API is supported in the current browser.    |
| charging        | `Boolean` | If the device is currently charging.                              |
| chargingTime    | `Number`  | The number of seconds until the device becomes fully charged.     |
| dischargingTime | `Number`  | The number of seconds before the device becomes fully discharged. |
| level           | `Number`  | A number between 0 and 1 representing the current charge level.   |

::: warning Browser Support
The Battery Status API has limited browser support. It is currently only available in Chromium-based browsers. Always check `isSupported` before using the values.
:::

## Use-cases

Our applications normally are not empathetic to battery level, we can make a few adjustments to our applications that will be more friendly to low battery users.

- Trigger a special "dark-mode" battery saver theme settings.
- Stop auto playing videos in news feeds.
- Disable some background workers that are not critical.
- Limit network calls and reduce CPU/Memory consumption.

## Component Usage

```vue
<template>
  <UseBattery v-slot="{ isSupported, charging, level }">
    <div v-if="isSupported">
      <p>Is Charging: {{ charging }}</p>
      <p>Battery Level: {{ (level * 100).toFixed(0) }}%</p>
    </div>
    <div v-else>
      Battery API not supported
    </div>
  </UseBattery>
</template>
```

## Type Declarations

```ts
export interface UseBatteryOptions extends ConfigurableNavigator {}
export interface UseBatteryReturn extends Supportable {
  charging: ShallowRef<boolean>
  chargingTime: ShallowRef<number>
  dischargingTime: ShallowRef<number>
  level: ShallowRef<number>
}
export interface BatteryManager extends EventTarget {
  charging: boolean
  chargingTime: number
  dischargingTime: number
  level: number
}
/**
 * Reactive Battery Status API.
 *
 * @see https://vueuse.org/useBattery
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useBattery(
  options?: UseBatteryOptions,
): UseBatteryReturn
```

---

<!-- source: references/useBluetooth.md -->
---
category: Browser
---

# useBluetooth

Reactive [Web Bluetooth API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API). Provides the ability to connect and interact with Bluetooth Low Energy peripherals.

The Web Bluetooth API lets websites discover and communicate with devices over the Bluetooth 4 wireless standard using the Generic Attribute Profile (GATT).

N.B. It is currently partially implemented in Android M, Chrome OS, Mac, and Windows 10. For a full overview of browser compatibility please see [Web Bluetooth API Browser Compatibility](https://developer.mozilla.org/en-US/docs/Web/API/Web_Bluetooth_API#browser_compatibility)

N.B. There are a number of caveats to be aware of with the web bluetooth API specification. Please refer to the [Web Bluetooth W3C Draft Report](https://webbluetoothcg.github.io/web-bluetooth/) for numerous caveats around device detection and connection.

N.B. This API is not available in Web Workers (not exposed via WorkerNavigator).

## Usage Default

```vue
<script setup lang="ts">
import { useBluetooth } from '@vueuse/core'

const {
  isSupported,
  isConnected,
  device,
  requestDevice,
  server,
  error,
} = useBluetooth({
  acceptAllDevices: true,
})
</script>

<template>
  <button @click="requestDevice()">
    Request Bluetooth Device
  </button>
  <div v-if="error">
    Error: {{ error }}
  </div>
</template>
```

### Return Values

| Property        | Type                             | Description                                |
| --------------- | -------------------------------- | ------------------------------------------ |
| `isSupported`   | `ComputedRef<boolean>`           | Whether the Web Bluetooth API is supported |
| `isConnected`   | `Ref<boolean>`                   | Whether a device is currently connected    |
| `device`        | `Ref<BluetoothDevice>`           | The connected Bluetooth device             |
| `server`        | `Ref<BluetoothRemoteGATTServer>` | The GATT server for the connected device   |
| `error`         | `Ref<unknown>`                   | Any error that occurred during connection  |
| `requestDevice` | `() => Promise<void>`            | Function to request a Bluetooth device     |

When the device has paired and is connected, you can then work with the server object as you wish.

## Usage Battery Level Example

This sample illustrates the use of the Web Bluetooth API to read battery level and be notified of changes from a nearby Bluetooth Device advertising Battery information with Bluetooth Low Energy.

Here, we use the characteristicvaluechanged event listener to handle reading battery level characteristic value. This event listener will optionally handle upcoming notifications as well.

```vue
<script setup lang="ts">
import { useBluetooth, useEventListener, watchPausable } from '@vueuse/core'

const {
  isSupported,
  isConnected,
  device,
  requestDevice,
  server,
} = useBluetooth({
  acceptAllDevices: true,
  optionalServices: [
    'battery_service',
  ],
})

const batteryPercent = ref<undefined | number>()

const isGettingBatteryLevels = ref(false)

async function getBatteryLevels() {
  isGettingBatteryLevels.value = true

  // Get the battery service:
  const batteryService = await server.getPrimaryService('battery_service')

  // Get the current battery level
  const batteryLevelCharacteristic = await batteryService.getCharacteristic(
    'battery_level',
  )

  // Listen to when characteristic value changes on `characteristicvaluechanged` event:
  useEventListener(batteryLevelCharacteristic, 'characteristicvaluechanged', (event) => {
    batteryPercent.value = event.target.value.getUint8(0)
  }, { passive: true })

  // Convert received buffer to number:
  const batteryLevel = await batteryLevelCharacteristic.readValue()

  batteryPercent.value = await batteryLevel.getUint8(0)
}

const { stop } = watchPausable(isConnected, (newIsConnected) => {
  if (!newIsConnected || !server.value || isGettingBatteryLevels.value)
    return
  // Attempt to get the battery levels of the device:
  getBatteryLevels()
  // We only want to run this on the initial connection, as we will use an event listener to handle updates:
  stop()
})
</script>

<template>
  <button @click="requestDevice()">
    Request Bluetooth Device
  </button>
</template>
```

More samples can be found on [Google Chrome's Web Bluetooth Samples](https://googlechrome.github.io/samples/web-bluetooth/).

## Type Declarations

```ts
export interface UseBluetoothRequestDeviceOptions {
  /**
   *
   * An array of BluetoothScanFilters. This filter consists of an array
   * of BluetoothServiceUUIDs, a name parameter, and a namePrefix parameter.
   *
   */
  filters?: BluetoothLEScanFilter[] | undefined
  /**
   *
   * An array of BluetoothServiceUUIDs.
   *
   * @see https://developer.mozilla.org/en-US/docs/Web/API/BluetoothRemoteGATTService/uuid
   *
   */
  optionalServices?: BluetoothServiceUUID[] | undefined
}
export interface UseBluetoothOptions
  extends UseBluetoothRequestDeviceOptions, ConfigurableNavigator {
  /**
   *
   * A boolean value indicating that the requesting script can accept all Bluetooth
   * devices. The default is false.
   *
   * !! This may result in a bunch of unrelated devices being shown
   * in the chooser and energy being wasted as there are no filters.
   *
   *
   * Use it with caution.
   *
   * @default false
   *
   */
  acceptAllDevices?: boolean
}
export declare function useBluetooth(
  options?: UseBluetoothOptions,
): UseBluetoothReturn
export interface UseBluetoothReturn extends Supportable {
  isConnected: Readonly<ShallowRef<boolean>>
  device: ShallowRef<BluetoothDevice | undefined>
  requestDevice: () => Promise<void>
  server: ShallowRef<BluetoothRemoteGATTServer | undefined>
  error: ShallowRef<unknown | null>
}
```

---

<!-- source: references/useBreakpoints.md -->
---
category: Browser
---

# useBreakpoints

Reactive viewport breakpoints.

## Usage

```ts
import { breakpointsTailwind, useBreakpoints } from '@vueuse/core'

const breakpoints = useBreakpoints(breakpointsTailwind)

const smAndLarger = breakpoints.greaterOrEqual('sm') // sm and larger
const largerThanSm = breakpoints.greater('sm') // only larger than sm
const lgAndSmaller = breakpoints.smallerOrEqual('lg') // lg and smaller
const smallerThanLg = breakpoints.smaller('lg') // only smaller than lg
```

```vue
<script setup lang="ts">
import { useBreakpoints } from '@vueuse/core'

const breakpoints = useBreakpoints({
  mobile: 0, // optional
  tablet: 640,
  laptop: 1024,
  desktop: 1280,
})

// Can be 'mobile' or 'tablet' or 'laptop' or 'desktop'
const activeBreakpoint = breakpoints.active()

// true or false
const laptop = breakpoints.between('laptop', 'desktop')
</script>

<template>
  <div :class="activeBreakpoint">
    ...
  </div>
</template>
```

### Shortcut Methods

You can access breakpoints directly as properties on the returned object. These return reactive refs.

```ts
const breakpoints = useBreakpoints({
  tablet: 640,
  laptop: 1024,
})

// Equivalent to breakpoints.greaterOrEqual('tablet') with min-width strategy
const isTablet = breakpoints.tablet
```

### Strategy

The `strategy` option controls how the shortcut properties behave:

- `min-width` (default, mobile-first): `breakpoints.lg` is `true` when viewport is `>= lg`
- `max-width` (desktop-first): `breakpoints.lg` is `true` when viewport is `< xl`

```ts
const breakpoints = useBreakpoints(breakpointsTailwind, {
  strategy: 'max-width', // desktop-first
})
```

### Available Methods

| Method                | Description                                              |
| --------------------- | -------------------------------------------------------- |
| `greaterOrEqual(k)`   | Reactive: viewport width >= breakpoint                   |
| `greater(k)`          | Reactive: viewport width > breakpoint                    |
| `smallerOrEqual(k)`   | Reactive: viewport width <= breakpoint                   |
| `smaller(k)`          | Reactive: viewport width < breakpoint                    |
| `between(a, b)`       | Reactive: viewport width between a and b                 |
| `isGreaterOrEqual(k)` | Non-reactive: returns boolean immediately                |
| `isGreater(k)`        | Non-reactive: returns boolean immediately                |
| `isSmallerOrEqual(k)` | Non-reactive: returns boolean immediately                |
| `isSmaller(k)`        | Non-reactive: returns boolean immediately                |
| `isInBetween(a, b)`   | Non-reactive: returns boolean immediately                |
| `current()`           | Returns computed array of all matching breakpoints       |
| `active()`            | Returns computed string of the current active breakpoint |

#### Server Side Rendering and Nuxt

If you are using `useBreakpoints` with SSR enabled, then you need to specify which screen size you would like to render on the server and before hydration to avoid an hydration mismatch

```ts
import { breakpointsTailwind, useBreakpoints } from '@vueuse/core'

const breakpoints = useBreakpoints(breakpointsTailwind, {
  ssrWidth: 768 // Will enable SSR mode and render like if the screen was 768px wide
})
```

Alternatively you can set this up globally for your app using [`provideSSRWidth`](../useSSRWidth/index.md)

## Presets

- Tailwind: `breakpointsTailwind`
- Bootstrap v5: `breakpointsBootstrapV5`
- Vuetify v2: `breakpointsVuetifyV2` (deprecated: `breakpointsVuetify`)
- Vuetify v3: `breakpointsVuetifyV3`
- Ant Design: `breakpointsAntDesign`
- Quasar v2: `breakpointsQuasar`
- Sematic: `breakpointsSematic`
- Master CSS: `breakpointsMasterCss`
- Prime Flex: `breakpointsPrimeFlex`
- ElementUI / ElementPlus: `breakpointsElement`

_Breakpoint presets are deliberately not auto-imported, as they do not start with `use` to have the scope of VueUse. They have to be explicitly imported:_

```js
import { breakpointsTailwind } from '@vueuse/core'
// and so on
```

## Type Declarations

```ts
export * from "./breakpoints"
export type Breakpoints<K extends string = string> = Record<
  K,
  MaybeRefOrGetter<number | string>
>
export interface UseBreakpointsOptions extends ConfigurableWindow {
  /**
   * The query strategy to use for the generated shortcut methods like `.lg`
   *
   * 'min-width' - .lg will be true when the viewport is greater than or equal to the lg breakpoint (mobile-first)
   * 'max-width' - .lg will be true when the viewport is smaller than the xl breakpoint (desktop-first)
   *
   * @default "min-width"
   */
  strategy?: "min-width" | "max-width"
  ssrWidth?: number
}
export type UseBreakpointReturn<K extends string = string> = Record<
  K,
  ComputedRef<boolean>
> & {
  greaterOrEqual: (k: MaybeRefOrGetter<K>) => ComputedRef<boolean>
  smallerOrEqual: (k: MaybeRefOrGetter<K>) => ComputedRef<boolean>
  greater: (k: MaybeRefOrGetter<K>) => ComputedRef<boolean>
  smaller: (k: MaybeRefOrGetter<K>) => ComputedRef<boolean>
  between: (
    a: MaybeRefOrGetter<K>,
    b: MaybeRefOrGetter<K>,
  ) => ComputedRef<boolean>
  isGreater: (k: MaybeRefOrGetter<K>) => boolean
  isGreaterOrEqual: (k: MaybeRefOrGetter<K>) => boolean
  isSmaller: (k: MaybeRefOrGetter<K>) => boolean
  isSmallerOrEqual: (k: MaybeRefOrGetter<K>) => boolean
  isInBetween: (a: MaybeRefOrGetter<K>, b: MaybeRefOrGetter<K>) => boolean
  current: () => ComputedRef<K[]>
  active: () => ComputedRef<K | "">
}
/**
 * Reactively viewport breakpoints
 *
 * @see https://vueuse.org/useBreakpoints
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useBreakpoints<K extends string>(
  breakpoints: Breakpoints<K>,
  options?: UseBreakpointsOptions,
): UseBreakpointReturn<K>
```

---

<!-- source: references/useBroadcastChannel.md -->
---
category: Browser
---

# useBroadcastChannel

Reactive [BroadcastChannel API](https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel).

Closes a broadcast channel automatically component unmounted.

## Usage

The BroadcastChannel interface represents a named channel that any browsing
context of a given origin can subscribe to. It allows communication between
different documents (in different windows, tabs, frames, or iframes) of the
same origin.

Messages are broadcasted via a message event fired at all BroadcastChannel
objects listening to the channel.

```ts
import { useBroadcastChannel } from '@vueuse/core'
import { shallowRef } from 'vue'

const {
  isSupported,
  channel,
  post,
  close,
  error,
  isClosed,
} = useBroadcastChannel({ name: 'vueuse-demo-channel' })

const message = shallowRef('')

message.value = 'Hello, VueUse World!'

// Post the message to the broadcast channel:
post(message.value)

// Option to close the channel if you wish:
close()
```

## Type Declarations

```ts
export interface UseBroadcastChannelOptions extends ConfigurableWindow {
  /**
   * The name of the channel.
   */
  name: string
}
/**
 * Reactive BroadcastChannel
 *
 * @see https://vueuse.org/useBroadcastChannel
 * @see https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel
 * @param options
 *
 */
export declare function useBroadcastChannel<D, P>(
  options: UseBroadcastChannelOptions,
): UseBroadcastChannelReturn<D, P>
export interface UseBroadcastChannelReturn<D, P> extends Supportable {
  channel: Ref<BroadcastChannel | undefined>
  data: Ref<D>
  post: (data: P) => void
  close: () => void
  error: ShallowRef<Event | null>
  isClosed: ShallowRef<boolean>
}
```

---

<!-- source: references/useBrowserLocation.md -->
---
category: Browser
---

# useBrowserLocation

Reactive browser location

> NOTE: If you're using Vue Router, use [`useRoute`](https://router.vuejs.org/guide/advanced/composition-api.html) provided by Vue Router instead.

## Usage

```ts
import { useBrowserLocation } from '@vueuse/core'

const location = useBrowserLocation()
```

## Component Usage

```vue
<UseBrowserLocation v-slot="location">
  Browser Location: {{ location }}
</UseBrowserLocation>
```

## Type Declarations

```ts
export interface UseBrowserLocationOptions extends ConfigurableWindow {}
export interface BrowserLocationState {
  readonly trigger: string
  readonly state?: any
  readonly length?: number
  readonly origin?: string
  hash?: string
  host?: string
  hostname?: string
  href?: string
  pathname?: string
  port?: string
  protocol?: string
  search?: string
}
export type UseBrowserLocationReturn = Ref<BrowserLocationState>
/**
 * Reactive browser location.
 *
 * @see https://vueuse.org/useBrowserLocation
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useBrowserLocation(
  options?: UseBrowserLocationOptions,
): UseBrowserLocationReturn
```

---

<!-- source: references/useCached.md -->
---
category: Utilities
---

# useCached

Cache a ref with a custom comparator.

## Usage

```ts
import { useCached } from '@vueuse/core'
import { shallowRef } from 'vue'

interface Data {
  value: number
  extra: number
}

const source = shallowRef<Data>({ value: 42, extra: 0 })
const cached = useCached(source, (a, b) => a.value === b.value)

source.value = {
  value: 42,
  extra: 1,
}

console.log(cached.value) // { value: 42, extra: 0 }

source.value = {
  value: 43,
  extra: 1,
}

console.log(cached.value) // { value: 43, extra: 1 }
```

## Type Declarations

```ts
export interface UseCachedOptions<D extends boolean = true>
  extends ConfigurableDeepRefs<D>, WatchOptions {}
export declare function useCached<T, D extends boolean = true>(
  refValue: Ref<T>,
  comparator?: (a: T, b: T) => boolean,
  options?: UseCachedOptions<D>,
): UseCachedReturn<T, D>
export type UseCachedReturn<
  T = any,
  D extends boolean = true,
> = ShallowOrDeepRef<T, D>
```

---

<!-- source: references/useCeil.md -->
---
category: '@Math'
---

# useCeil

Reactive `Math.ceil`

## Usage

```ts
import { useCeil } from '@vueuse/math'

const value = ref(0.95)
const result = useCeil(value) // 1
```

## Type Declarations

```ts
/**
 * Reactive `Math.ceil`.
 *
 * @see https://vueuse.org/useCeil
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useCeil(
  value: MaybeRefOrGetter<number>,
): ComputedRef<number>
```

---

<!-- source: references/useChangeCase.md -->
---
category: '@Integrations'
---

# useChangeCase

Reactive wrapper for [`change-case`](https://github.com/blakeembrey/change-case).

Subsitutes `useCamelCase`, `usePascalCase`, `useSnakeCase`, `useSentenceCase`, `useCapitalize`, etc.

## Install

```bash
npm i change-case@^5
```

## Usage

```ts
import { useChangeCase } from '@vueuse/integrations/useChangeCase'

// `changeCase` will be a computed
const changeCase = useChangeCase('hello world', 'camelCase')
changeCase.value // helloWorld
changeCase.value = 'vue use'
changeCase.value // vueUse
// Supported methods
// export {
//   camelCase,
//   capitalCase,
//   constantCase,
//   dotCase,
//   headerCase,
//   noCase,
//   paramCase,
//   pascalCase,
//   pathCase,
//   sentenceCase,
//   snakeCase,
// } from 'change-case'
```

or passing a `ref` to it, the returned `computed` will change along with the source ref's changes.

Can be passed into `options` for customization

```ts
import { useChangeCase } from '@vueuse/integrations/useChangeCase'
import { shallowRef } from 'vue'

const input = shallowRef('helloWorld')
const changeCase = useChangeCase(input, 'camelCase', {
  delimiter: '-',
})
changeCase.value // hello-World
input.value = 'vue use'
changeCase.value // vue-Use
```

## Type Declarations

```ts
type EndsWithCase<T> = T extends `${infer _}Case` ? T : never
type FilterKeys<T> = {
  [K in keyof T as K extends string ? K : never]: EndsWithCase<K>
}
type ChangeCaseKeys = FilterKeys<typeof changeCase>
export type ChangeCaseType = ChangeCaseKeys[keyof ChangeCaseKeys]
export declare function useChangeCase(
  input: MaybeRef<string>,
  type: MaybeRefOrGetter<ChangeCaseType>,
  options?: MaybeRefOrGetter<Options> | undefined,
): WritableComputedRef<string>
export declare function useChangeCase(
  input: MaybeRefOrGetter<string>,
  type: MaybeRefOrGetter<ChangeCaseType>,
  options?: MaybeRefOrGetter<Options> | undefined,
): ComputedRef<string>
```

---

<!-- source: references/useClamp.md -->
---
category: '@Math'
---

# useClamp

Reactively clamp a value between two other values.

## Usage

```ts
import { useClamp } from '@vueuse/math'

const min = shallowRef(0)
const max = shallowRef(10)
const value = useClamp(0, min, max)
```

### Writable Ref

When you pass a mutable `ref`, the returned value is a **writable computed** that clamps values when setting:

```ts
import { useClamp } from '@vueuse/math'

const number = shallowRef(0)
const clamped = useClamp(number, 0, 10)

clamped.value = 15 // clamped.value will be 10
clamped.value = -5 // clamped.value will be 0
```

### Read-only Mode

When you pass a getter function or readonly ref, the returned value is a read-only computed:

```ts
import { useClamp } from '@vueuse/math'

const value = ref(5)
const clamped = useClamp(() => value.value * 2, 0, 10)

// clamped.value is computed from the getter
```

### Reactive Bounds

All arguments (value, min, max) can be reactive:

```ts
import { useClamp } from '@vueuse/math'

const value = shallowRef(5)
const min = shallowRef(0)
const max = shallowRef(10)

const clamped = useClamp(value, min, max)

max.value = 3 // clamped.value automatically becomes 3
```

## Type Declarations

```ts
/**
 * Reactively clamp a value between two other values.
 *
 * @see https://vueuse.org/useClamp
 * @param value number
 * @param min
 * @param max
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useClamp(
  value: ReadonlyRefOrGetter<number>,
  min: MaybeRefOrGetter<number>,
  max: MaybeRefOrGetter<number>,
): ComputedRef<number>
export declare function useClamp(
  value: MaybeRefOrGetter<number>,
  min: MaybeRefOrGetter<number>,
  max: MaybeRefOrGetter<number>,
): Ref<number>
```

---

<!-- source: references/useClipboard.md -->
---
category: Browser
---

# useClipboard

Reactive [Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API). Provides the ability to respond to clipboard commands (cut, copy, and paste) as well as to asynchronously read from and write to the system clipboard. Access to the contents of the clipboard is gated behind the [Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API). Without user permission, reading or altering the clipboard contents is not permitted.

<CourseLink href="https://vueschool.io/lessons/reactive-browser-wrappers-in-vueuse-useclipboard?friend=vueuse">Learn how to reactively save text to the clipboard with this FREE video lesson from Vue School!</CourseLink>

## Usage

```vue
<script setup lang="ts">
import { useClipboard } from '@vueuse/core'

const source = ref('Hello')
const { text, copy, copied, isSupported } = useClipboard({ source })
</script>

<template>
  <div v-if="isSupported">
    <button @click="copy(source)">
      <!-- by default, `copied` will be reset in 1.5s -->
      <span v-if="!copied">Copy</span>
      <span v-else>Copied!</span>
    </button>
    <p>Current copied: <code>{{ text || 'none' }}</code></p>
  </div>
  <p v-else>
    Your browser does not support Clipboard API
  </p>
</template>
```

### Options

| Option         | Type                       | Default | Description                                                       |
| -------------- | -------------------------- | ------- | ----------------------------------------------------------------- |
| `source`       | `MaybeRefOrGetter<string>` | —       | Default content to copy when `copy()` is called without arguments |
| `read`         | `boolean`                  | `false` | Enable reading clipboard content on copy/cut events               |
| `copiedDuring` | `number`                   | `1500`  | Milliseconds before `copied` resets to `false`                    |
| `legacy`       | `boolean`                  | `false` | Fallback to `document.execCommand` if Clipboard API unavailable   |

### Return Values

| Property      | Type                               | Description                                       |
| ------------- | ---------------------------------- | ------------------------------------------------- |
| `isSupported` | `ComputedRef<boolean>`             | Whether clipboard is supported (native or legacy) |
| `text`        | `Ref<string>`                      | Current clipboard content (when `read: true`)     |
| `copied`      | `Ref<boolean>`                     | `true` after successful copy, auto-resets         |
| `copy`        | `(text?: string) => Promise<void>` | Copy text to clipboard                            |

### Legacy Mode

Set `legacy: true` to keep the ability to copy if [Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API) is not available. It will handle copy with [execCommand](https://developer.mozilla.org/en-US/docs/Web/API/Document/execCommand) as fallback.

```ts
const { copy, isSupported } = useClipboard({ legacy: true })
```

## Component Usage

```vue
<template>
  <UseClipboard v-slot="{ copy, copied }" source="copy me">
    <button @click="copy()">
      {{ copied ? 'Copied' : 'Copy' }}
    </button>
  </UseClipboard>
</template>
```

## Type Declarations

```ts
export interface UseClipboardOptions<Source> extends ConfigurableNavigator {
  /**
   * Enabled reading for clipboard
   *
   * @default false
   */
  read?: boolean
  /**
   * Copy source
   */
  source?: Source
  /**
   * Milliseconds to reset state of `copied` ref
   *
   * @default 1500
   */
  copiedDuring?: number
  /**
   * Whether fallback to document.execCommand('copy') if clipboard is undefined.
   *
   * @default false
   */
  legacy?: boolean
}
export interface UseClipboardReturn<Optional> extends Supportable {
  text: Readonly<ShallowRef<string>>
  copied: Readonly<ShallowRef<boolean>>
  copy: Optional extends true
    ? (text?: string) => Promise<void>
    : (text: string) => Promise<void>
}
/**
 * Reactive Clipboard API.
 *
 * @see https://vueuse.org/useClipboard
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useClipboard(
  options?: UseClipboardOptions<undefined>,
): UseClipboardReturn<false>
export declare function useClipboard(
  options: UseClipboardOptions<MaybeRefOrGetter<string>>,
): UseClipboardReturn<true>
```

---

<!-- source: references/useClipboardItems.md -->
---
category: Browser
related:
  - useClipboard
---

# useClipboardItems

Reactive [Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API). Provides the ability to respond to clipboard commands (cut, copy, and paste) as well as to asynchronously read from and write to the system clipboard. Access to the contents of the clipboard is gated behind the [Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API). Without user permission, reading or altering the clipboard contents is not permitted.

## Difference from `useClipboard`

`useClipboard` is a "text-only" function, while `useClipboardItems` is a [ClipboardItem](https://developer.mozilla.org/en-US/docs/Web/API/ClipboardItem) based function. You can use `useClipboardItems` to copy any content supported by [ClipboardItem](https://developer.mozilla.org/en-US/docs/Web/API/ClipboardItem).

## Usage

```vue
<script setup lang="ts">
import { useClipboardItems } from '@vueuse/core'

const mime = 'text/plain'
const source = ref([
  new ClipboardItem({
    [mime]: new Blob(['plain text'], { type: mime }),
  })
])

const { content, copy, copied, isSupported } = useClipboardItems({ source })
</script>

<template>
  <div v-if="isSupported">
    <button @click="copy(source)">
      <!-- by default, `copied` will be reset in 1.5s -->
      <span v-if="!copied">Copy</span>
      <span v-else>Copied!</span>
    </button>
    <p>
      Current copied: <code>{{ content || 'none' }}</code>
    </p>
  </div>
  <p v-else>
    Your browser does not support Clipboard API
  </p>
</template>
```

## Type Declarations

```ts
export interface UseClipboardItemsOptions<
  Source,
> extends ConfigurableNavigator {
  /**
   * Enabled reading for clipboard
   *
   * @default false
   */
  read?: boolean
  /**
   * Copy source
   */
  source?: Source
  /**
   * Milliseconds to reset state of `copied` ref
   *
   * @default 1500
   */
  copiedDuring?: number
}
export interface UseClipboardItemsReturn<Optional> extends Supportable {
  content: Readonly<Ref<ClipboardItems>>
  copied: Readonly<ShallowRef<boolean>>
  copy: Optional extends true
    ? (content?: ClipboardItems) => Promise<void>
    : (text: ClipboardItems) => Promise<void>
  read: () => void
}
/**
 * Reactive Clipboard API.
 *
 * @see https://vueuse.org/useClipboardItems
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useClipboardItems(
  options?: UseClipboardItemsOptions<undefined>,
): UseClipboardItemsReturn<false>
export declare function useClipboardItems(
  options: UseClipboardItemsOptions<MaybeRefOrGetter<ClipboardItems>>,
): UseClipboardItemsReturn<true>
```

---

<!-- source: references/useCloned.md -->
---
category: Utilities
---

# useCloned

Reactive clone of a ref. By default, it use `JSON.parse(JSON.stringify())` to do the clone.

## Usage

```ts
import { useCloned } from '@vueuse/core'

const original = ref({ key: 'value' })

const { cloned } = useCloned(original)

original.value.key = 'some new value'

console.log(cloned.value.key) // 'value'
```

## Manual cloning

```ts
import { useCloned } from '@vueuse/core'

const original = ref({ key: 'value' })

const { cloned, sync } = useCloned(original, { manual: true })

original.value.key = 'manual'

console.log(cloned.value.key) // 'value'

sync()

console.log(cloned.value.key)// 'manual'
```

## Custom Clone Function

Using [`klona`](https://www.npmjs.com/package/klona) for example:

```ts
import { useCloned } from '@vueuse/core'
import { klona } from 'klona'

const original = ref({ key: 'value' })

const { cloned, isModified, sync } = useCloned(original, { clone: klona })
```

## Type Declarations

```ts
export interface UseClonedOptions<T = any> extends WatchOptions {
  /**
   * Custom clone function.
   *
   * By default, it use `JSON.parse(JSON.stringify(value))` to clone.
   */
  clone?: (source: T) => T
  /**
   * Manually sync the ref
   *
   * @default false
   */
  manual?: boolean
}
export interface UseClonedReturn<T> {
  /**
   * Cloned ref
   */
  cloned: Ref<T>
  /**
   * Ref indicates whether the cloned data is modified
   */
  isModified: Ref<boolean>
  /**
   * Sync cloned data with source manually
   */
  sync: () => void
}
export type CloneFn<F, T = F> = (x: F) => T
export declare function cloneFnJSON<T>(source: T): T
export declare function useCloned<T>(
  source: MaybeRefOrGetter<T>,
  options?: UseClonedOptions,
): UseClonedReturn<T>
```

---

<!-- source: references/useColorMode.md -->
---
category: Browser
related:
  - useDark
  - usePreferredDark
  - useStorage
---

# useColorMode

Reactive color mode (dark / light / customs) with auto data persistence.

## Basic Usage

```ts
import { useColorMode } from '@vueuse/core'

const mode = useColorMode() // Ref<'dark' | 'light'>
```

By default, it will match with users' browser preference using `usePreferredDark` (a.k.a `auto` mode). When reading the ref, it will by default return the current color mode (`dark`, `light` or your custom modes). The `auto` mode can be included in the returned modes by enabling the `emitAuto` option. When writing to the ref, it will trigger DOM updates and persist the color mode to local storage (or your custom storage). You can pass `auto` to set back to auto mode.

```ts
import { useColorMode } from '@vueuse/core'

const mode = useColorMode()
// ---cut---
mode.value // 'dark' | 'light'

mode.value = 'dark' // change to dark mode and persist

mode.value = 'auto' // change to auto mode
```

## Config

```ts
import { useColorMode } from '@vueuse/core'

const mode = useColorMode({
  attribute: 'theme',
  modes: {
    // custom colors
    dim: 'dim',
    cafe: 'cafe',
  },
}) // Ref<'dark' | 'light' | 'dim' | 'cafe'>
```

## Advanced Usage

You can also explicit access to the system preference and storaged user override mode.

```ts
import { useColorMode } from '@vueuse/core'

const { system, store } = useColorMode()

system.value // 'dark' | 'light'
store.value // 'dark' | 'light' | 'auto'

const myColorMode = computed(() => store.value === 'auto' ? system.value : store.value)
```

## Component Usage

```vue
<template>
  <UseColorMode v-slot="color">
    <button @click="color.mode = color.mode === 'dark' ? 'light' : 'dark'">
      Mode {{ color.mode }}
    </button>
  </UseColorMode>
</template>
```

## Type Declarations

```ts
export type BasicColorMode = "light" | "dark"
export type BasicColorSchema = BasicColorMode | "auto"
export interface UseColorModeOptions<
  T extends string = BasicColorMode,
> extends UseStorageOptions<T | BasicColorMode> {
  /**
   * CSS Selector for the target element applying to
   *
   * @default 'html'
   */
  selector?: string | MaybeElementRef
  /**
   * HTML attribute applying the target element
   *
   * @default 'class'
   */
  attribute?: string
  /**
   * The initial color mode
   *
   * @default 'auto'
   */
  initialValue?: MaybeRefOrGetter<T | BasicColorSchema>
  /**
   * Prefix when adding value to the attribute
   */
  modes?: Partial<Record<T | BasicColorSchema, string>>
  /**
   * A custom handler for handle the updates.
   * When specified, the default behavior will be overridden.
   *
   * @default undefined
   */
  onChanged?: (
    mode: T | BasicColorMode,
    defaultHandler: (mode: T | BasicColorMode) => void,
  ) => void
  /**
   * Custom storage ref
   *
   * When provided, `useStorage` will be skipped
   */
  storageRef?: Ref<T | BasicColorSchema>
  /**
   * Key to persist the data into localStorage/sessionStorage.
   *
   * Pass `null` to disable persistence
   *
   * @default 'vueuse-color-scheme'
   */
  storageKey?: string | null
  /**
   * Storage object, can be localStorage or sessionStorage
   *
   * @default localStorage
   */
  storage?: StorageLike
  /**
   * Emit `auto` mode from state
   *
   * When set to `true`, preferred mode won't be translated into `light` or `dark`.
   * This is useful when the fact that `auto` mode was selected needs to be known.
   *
   * @default undefined
   * @deprecated use `store.value` when `auto` mode needs to be known
   * @see https://vueuse.org/core/useColorMode/#advanced-usage
   */
  emitAuto?: boolean
  /**
   * Disable transition on switch
   *
   * @see https://paco.me/writing/disable-theme-transitions
   * @default true
   */
  disableTransition?: boolean
}
export type UseColorModeReturn<T extends string = BasicColorMode> = Ref<
  T | BasicColorSchema
> & {
  store: Ref<T | BasicColorSchema>
  system: ComputedRef<BasicColorMode>
  state: ComputedRef<T | BasicColorMode>
}
/**
 * Reactive color mode with auto data persistence.
 *
 * @see https://vueuse.org/useColorMode
 * @param options
 */
export declare function useColorMode<T extends string = BasicColorMode>(
  options?: UseColorModeOptions<T>,
): UseColorModeReturn<T>
```

---

<!-- source: references/useConfirmDialog.md -->
---
category: Utilities
---

# useConfirmDialog

Creates event hooks to support modals and confirmation dialog chains.

Functions can be used on the template, and hooks are a handy skeleton for the business logic of modals dialog or other actions that require user confirmation.

## Functions and hooks

- `reveal()` - triggers `onReveal` hook and sets `revealed.value` to `true`. Returns promise that resolves by `confirm()` or `cancel()`.
- `confirm()` - sets `isRevealed.value` to `false` and triggers `onConfirm` hook.
- `cancel()` - sets `isRevealed.value` to `false` and triggers `onCancel` hook.

## Basic Usage

### Using hooks

```vue
<script setup lang="ts">
import { useConfirmDialog } from '@vueuse/core'

const { isRevealed, reveal, confirm, cancel, onReveal, onConfirm, onCancel }
  = useConfirmDialog()
</script>

<template>
  <button @click="reveal">
    Reveal Modal
  </button>

  <teleport to="body">
    <div v-if="isRevealed" class="modal-bg">
      <div class="modal">
        <h2>Confirm?</h2>
        <button @click="confirm">
          Yes
        </button>
        <button @click="cancel">
          Cancel
        </button>
      </div>
    </div>
  </teleport>
</template>
```

### Promise

If you prefer working with promises:

```vue
<script setup lang="ts">
import { useConfirmDialog } from '@vueuse/core'

const {
  isRevealed,
  reveal,
  confirm,
  cancel,
} = useConfirmDialog()

async function openDialog() {
  const { data, isCanceled } = await reveal()
  if (!isCanceled)
    console.log(data)
}
</script>

<template>
  <button @click="openDialog">
    Show Modal
  </button>

  <teleport to="body">
    <div v-if="isRevealed" class="modal-layout">
      <div class="modal">
        <h2>Confirm?</h2>
        <button @click="confirm(true)">
          Yes
        </button>
        <button @click="confirm(false)">
          No
        </button>
      </div>
    </div>
  </teleport>
</template>
```

## Type Declarations

```ts
export type UseConfirmDialogRevealResult<C, D> =
  | {
      data?: C
      isCanceled: false
    }
  | {
      data?: D
      isCanceled: true
    }
export interface UseConfirmDialogReturn<RevealData, ConfirmData, CancelData> {
  /**
   * Revealing state
   */
  isRevealed: ComputedRef<boolean>
  /**
   * Opens the dialog.
   * Create promise and return it. Triggers `onReveal` hook.
   */
  reveal: (
    data?: RevealData,
  ) => Promise<UseConfirmDialogRevealResult<ConfirmData, CancelData>>
  /**
   * Confirms and closes the dialog. Triggers a callback inside `onConfirm` hook.
   * Resolves promise from `reveal()` with `data` and `isCanceled` ref with `false` value.
   * Can accept any data and to pass it to `onConfirm` hook.
   */
  confirm: (data?: ConfirmData) => void
  /**
   * Cancels and closes the dialog. Triggers a callback inside `onCancel` hook.
   * Resolves promise from `reveal()` with `data` and `isCanceled` ref with `true` value.
   * Can accept any data and to pass it to `onCancel` hook.
   */
  cancel: (data?: CancelData) => void
  /**
   * Event Hook to be triggered right before dialog creating.
   */
  onReveal: EventHookOn<RevealData>
  /**
   * Event Hook to be called on `confirm()`.
   * Gets data object from `confirm` function.
   */
  onConfirm: EventHookOn<ConfirmData>
  /**
   * Event Hook to be called on `cancel()`.
   * Gets data object from `cancel` function.
   */
  onCancel: EventHookOn<CancelData>
}
/**
 * Hooks for creating confirm dialogs. Useful for modal windows, popups and logins.
 *
 * @see https://vueuse.org/useConfirmDialog/
 * @param revealed `boolean` `ref` that handles a modal window
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useConfirmDialog<
  RevealData = any,
  ConfirmData = any,
  CancelData = any,
>(
  revealed?: ShallowRef<boolean>,
): UseConfirmDialogReturn<RevealData, ConfirmData, CancelData>
```

---

<!-- source: references/useCookies.md -->
---
category: '@Integrations'
---

# useCookies

Wrapper for [`universal-cookie`](https://www.npmjs.com/package/universal-cookie).

::: tip
When using with Nuxt 3, this functions will **NOT** be auto imported in favor of Nuxt's built-in [`useCookie()`](https://v3.nuxtjs.org/api/composables/use-cookie). Use explicit import if you want to use the function from VueUse.
:::

## Install

```bash
npm i universal-cookie@^7
```

## Usage

### Common usage

```vue
<script setup lang="ts">
import { useCookies } from '@vueuse/integrations/useCookies'

const cookies = useCookies(['locale'])
</script>

<template>
  <div>
    <strong>locale</strong>: {{ cookies.get('locale') }}
    <hr>
    <pre>{{ cookies.getAll() }}</pre>
    <button @click="cookies.set('locale', 'ru-RU')">
      Russian
    </button>
    <button @click="cookies.set('locale', 'en-US')">
      English
    </button>
  </div>
</template>
```

## Options

Access and modify cookies using vue composition-api.

> By default, you should use it inside `setup()`, but this function also works anywhere else.

```ts
import { useCookies } from '@vueuse/integrations/useCookies'
// ---cut---
const {
  get,
  getAll,
  set,
  remove,
  addChangeListener,
  removeChangeListener
} = useCookies(['cookie-name'], {
  doNotParse: false,
  autoUpdateDependencies: false
})
```

### `dependencies` (optional)

Let you optionally specify a list of cookie names your component depend on or that should trigger a re-render. If unspecified, it will render on every cookie change.

### `options` (optional)

- `doNotParse` (boolean = false): do not convert the cookie into an object no matter what. **Passed as default value to `get`/`getAll` methods.**
- `autoUpdateDependencies` (boolean = false): automatically add cookie names ever provided to `get` method. If **true** then you don't need to care about provided `dependencies`.

### `cookies` (optional)

Let you provide a `universal-cookie` instance (creates a new instance by default)

> Info about methods available in the [universal-cookie api docs](https://www.npmjs.com/package/universal-cookie#api---cookies-class)

## `createCookies([req])`

Create a `universal-cookie` instance using request (default is window.document.cookie) and returns `useCookies` function with provided universal-cookie instance

- req (object): Node's [http.IncomingMessage](https://nodejs.org/api/http.html#http_class_http_incomingmessage) request object

## Type Declarations

```ts
/**
 * Creates a new {@link useCookies} function
 * @param req - incoming http request (for SSR)
 * @see https://github.com/reactivestack/cookies/tree/master/packages/universal-cookie universal-cookie
 * @description Creates universal-cookie instance using request (default is window.document.cookie) and returns {@link useCookies} function with provided universal-cookie instance
 */
export declare function createCookies(req?: IncomingMessage): (
  dependencies?: string[] | null,
  {
    doNotParse,
    autoUpdateDependencies,
  }?: {
    doNotParse?: boolean | undefined
    autoUpdateDependencies?: boolean | undefined
  },
) => {
  /**
   * Reactive get cookie by name. If **autoUpdateDependencies = true** then it will update watching dependencies
   */
  get: <T = any>(name: string, options?: CookieGetOptions | undefined) => T
  /**
   * Reactive get all cookies
   */
  getAll: <T = any>(options?: CookieGetOptions | undefined) => T
  set: (
    name: string,
    value: any,
    options?: CookieSetOptions | undefined,
  ) => void
  remove: (name: string, options?: CookieSetOptions | undefined) => void
  addChangeListener: (callback: CookieChangeListener) => void
  removeChangeListener: (callback: CookieChangeListener) => void
}
/**
 * Reactive methods to work with cookies (use {@link createCookies} method instead if you are using SSR)
 * @param dependencies - array of watching cookie's names. Pass empty array if don't want to watch cookies changes.
 * @param options
 * @param options.doNotParse - don't try parse value as JSON
 * @param options.autoUpdateDependencies - automatically update watching dependencies
 * @param cookies - universal-cookie instance
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useCookies(
  dependencies?: string[] | null,
  {
    doNotParse,
    autoUpdateDependencies,
  }?: {
    doNotParse?: boolean | undefined
    autoUpdateDependencies?: boolean | undefined
  },
  cookies?: Cookie,
): {
  /**
   * Reactive get cookie by name. If **autoUpdateDependencies = true** then it will update watching dependencies
   */
  get: <T = any>(name: string, options?: CookieGetOptions | undefined) => T
  /**
   * Reactive get all cookies
   */
  getAll: <T = any>(options?: CookieGetOptions | undefined) => T
  set: (
    name: string,
    value: any,
    options?: CookieSetOptions | undefined,
  ) => void
  remove: (name: string, options?: CookieSetOptions | undefined) => void
  addChangeListener: (callback: CookieChangeListener) => void
  removeChangeListener: (callback: CookieChangeListener) => void
}
```

---

<!-- source: references/useCountdown.md -->
---
category: Time
---

# useCountdown

Reactive countdown timer in seconds.

## Usage

```ts
import { useCountdown } from '@vueuse/core'

const countdownSeconds = 5
const { remaining, start, stop, pause, resume } = useCountdown(countdownSeconds, {
  onComplete() {

  },
  onTick() {

  }
})
```

You can use a `ref` to change the initial countdown.
`start()` and `resume()` also accept a new countdown value for the next countdown.

```ts
import { useCountdown } from '@vueuse/core'
import { shallowRef } from 'vue'

const countdown = shallowRef(5)
const { start, reset } = useCountdown(countdown, {
})

// change the countdown value
countdown.value = 10

// start a new countdown with 2 seconds
start(2)

// reset the countdown to 4, but do not start it
reset(4)

// start the countdown with the current value of `countdown`
start()
```

## Type Declarations

```ts
export interface UseCountdownOptions extends ConfigurableScheduler {
  /**
   *  Interval for the countdown in milliseconds. Default is 1000ms.
   *
   * @deprecated Please use `scheduler` option instead
   */
  interval?: MaybeRefOrGetter<number>
  /**
   * Callback function called when the countdown reaches 0.
   */
  onComplete?: () => void
  /**
   * Callback function called on each tick of the countdown.
   */
  onTick?: () => void
  /**
   * Start the countdown immediately
   *
   * @deprecated Please use `scheduler` option instead
   * @default false
   */
  immediate?: boolean
}
export interface UseCountdownReturn extends Pausable {
  /**
   * Current countdown value.
   */
  remaining: ShallowRef<number>
  /**
   * Resets the countdown and repeatsLeft to their initial values.
   */
  reset: (countdown?: MaybeRefOrGetter<number>) => void
  /**
   * Stops the countdown and resets its state.
   */
  stop: () => void
  /**
   * Reset the countdown and start it again.
   */
  start: (countdown?: MaybeRefOrGetter<number>) => void
}
/**
 * Reactive countdown timer in seconds.
 *
 * @param initialCountdown
 * @param options
 *
 * @see https://vueuse.org/useCountdown
 */
export declare function useCountdown(
  initialCountdown: MaybeRefOrGetter<number>,
  options?: UseCountdownOptions,
): UseCountdownReturn
```

---

<!-- source: references/useCounter.md -->
---
category: Utilities
---

# useCounter

Basic counter with utility functions.

## Basic Usage

```ts
import { useCounter } from '@vueuse/core'

const { count, inc, dec, set, reset } = useCounter()
```

## Usage with options

```ts
import { useCounter } from '@vueuse/core'

const { count, inc, dec, set, reset } = useCounter(1, { min: 0, max: 16 })
```

## Type Declarations

```ts
export interface UseCounterOptions {
  min?: number
  max?: number
}
export interface UseCounterReturn {
  /**
   * The current value of the counter.
   */
  readonly count: Readonly<Ref<number>>
  /**
   * Increment the counter.
   *
   * @param {number} [delta=1] The number to increment.
   */
  inc: (delta?: number) => void
  /**
   * Decrement the counter.
   *
   * @param {number} [delta=1] The number to decrement.
   */
  dec: (delta?: number) => void
  /**
   * Get the current value of the counter.
   */
  get: () => number
  /**
   * Set the counter to a new value.
   *
   * @param val The new value of the counter.
   */
  set: (val: number) => void
  /**
   * Reset the counter to an initial value.
   */
  reset: (val?: number) => number
}
/**
 * Basic counter with utility functions.
 *
 * @see https://vueuse.org/useCounter
 * @param [initialValue]
 * @param options
 */
export declare function useCounter(
  initialValue?: MaybeRef<number>,
  options?: UseCounterOptions,
): {
  count: Readonly<
    | Ref<number, number>
    | ShallowRef<number, number>
    | WritableComputedRef<number, number>
  >
  inc: (delta?: number) => number
  dec: (delta?: number) => number
  get: () => number
  set: (val: number) => number
  reset: (val?: number) => number
}
```

---

<!-- source: references/useCssSupports.md -->
---
category: Browser
---

# useCssSupports

SSR compatible and reactive [`CSS.supports`](https://developer.mozilla.org/docs/Web/API/CSS/supports_static).

## Usage

```ts
import { useCssSupports } from '@vueuse/core'

const { isSupported } = useCssSupports('container-type', 'scroll-state')
```

## Type Declarations

```ts
export interface UseCssSupportsOptions extends ConfigurableWindow {
  ssrValue?: boolean
}
export interface UseCssSupportsReturn extends Supportable {}
export declare function useCssSupports(
  property: MaybeRefOrGetter<string>,
  value: MaybeRefOrGetter<string>,
  options?: UseCssSupportsOptions,
): UseCssSupportsReturn
export declare function useCssSupports(
  conditionText: MaybeRefOrGetter<string>,
  options?: UseCssSupportsOptions,
): UseCssSupportsReturn
```

---

<!-- source: references/useCssVar.md -->
---
category: Browser
---

# useCssVar

Manipulate CSS variables

## Usage

```ts
import { useCssVar } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const color1 = useCssVar('--color', el)

const elv = useTemplateRef('elv')
const key = ref('--color')
const colorVal = useCssVar(key, elv)

const someEl = useTemplateRef('someEl')
const color2 = useCssVar('--color', someEl, { initialValue: '#eee' })
```

## Type Declarations

```ts
export interface UseCssVarOptions extends ConfigurableWindow {
  initialValue?: string
  /**
   * Use MutationObserver to monitor variable changes
   * @default false
   */
  observe?: boolean
}
/**
 * Manipulate CSS variables.
 *
 * @see https://vueuse.org/useCssVar
 * @param prop
 * @param target
 * @param options
 */
export declare function useCssVar(
  prop: MaybeRefOrGetter<string | null | undefined>,
  target?: MaybeElementRef,
  options?: UseCssVarOptions,
): ShallowRef<string | undefined, string | undefined>
```

---

<!-- source: references/useCurrentElement.md -->
---
category: Component
---

# useCurrentElement

Get the DOM element of current component as a ref.

## Usage

```ts
import { useCurrentElement } from '@vueuse/core'

const el = useCurrentElement() // ComputedRef<Element>
```

Or pass a specific vue component

```vue
<script setup lang="ts">
import { useCurrentElement, VueInstance } from '@vueuse/core'
import { shallowRef } from 'vue'

const componentRef = shallowRef<VueInstance>(null as unknown as VueInstance)

const el = useCurrentElement(componentRef) // ComputedRef<Element>
</script>

<template>
  <div>
    <OtherVueComponent ref="componentRef" />
    <p>Hello world</p>
  </div>
</template>
```

## Caveats

This functions uses [`$el` under the hood](https://vuejs.org/api/component-instance.html#el).

Value of the ref will be `undefined` until the component is mounted.

- For components with a single root element, it will point to that element.
- For components with text root, it will point to the text node.
- For components with multiple root nodes, it will be the placeholder DOM node that Vue uses to keep track of the component's position in the DOM.

It's recommend to only use this function for components with **a single root element**.

## Type Declarations

```ts
export declare function useCurrentElement<
  T extends MaybeElement = MaybeElement,
  R extends VueInstance = VueInstance,
  E extends MaybeElement = MaybeElement extends T
    ? IsAny<R["$el"]> extends false
      ? R["$el"]
      : T
    : T,
>(rootComponent?: MaybeElementRef<R>): ComputedRefWithControl<E>
```

---

<!-- source: references/useCycleList.md -->
---
category: Utilities
---

# useCycleList

Cycle through a list of items.

<CourseLink href="https://vueschool.io/lessons/create-an-image-carousel-with-vueuse?friend=vueuse">Learn how to use useCycleList to create an image carousel with this FREE video lesson from Vue School!</CourseLink>

## Usage

```ts
import { useCycleList } from '@vueuse/core'

const { state, next, prev, go } = useCycleList([
  'Dog',
  'Cat',
  'Lizard',
  'Shark',
  'Whale',
  'Dolphin',
  'Octopus',
  'Seal',
])

console.log(state.value) // 'Dog'

prev()

console.log(state.value) // 'Seal'

go(3)

console.log(state.value) // 'Shark'
```

## Type Declarations

```ts
export interface UseCycleListOptions<T> {
  /**
   * The initial value of the state.
   * A ref can be provided to reuse.
   */
  initialValue?: MaybeRef<T>
  /**
   * The default index when
   */
  fallbackIndex?: number
  /**
   * Custom function to get the index of the current value.
   */
  getIndexOf?: (value: T, list: T[]) => number
}
/**
 * Cycle through a list of items
 *
 * @see https://vueuse.org/useCycleList
 */
export declare function useCycleList<T>(
  list: MaybeRefOrGetter<T[]>,
  options?: UseCycleListOptions<T>,
): UseCycleListReturn<T>
export interface UseCycleListReturn<T> {
  state: ShallowRef<T>
  index: WritableComputedRef<number>
  next: (n?: number) => T
  prev: (n?: number) => T
  /**
   * Go to a specific index
   */
  go: (i: number) => T
}
```

---

<!-- source: references/useDark.md -->
---
category: Browser
related:
  - useColorMode
  - usePreferredDark
  - useStorage
---

# useDark

Reactive dark mode with auto data persistence.

<CourseLink href="https://vueschool.io/lessons/theming-with-vueuse-usedark-and-usecolormode?friend=vueuse">Learn useDark with this FREE video lesson from Vue School!</CourseLink>

## Basic Usage

```ts
import { useDark, useToggle } from '@vueuse/core'

const isDark = useDark()
const toggleDark = useToggle(isDark)
```

## Behavior

`useDark` combines with `usePreferredDark` and `useStorage`. On start up, it reads the value from localStorage/sessionStorage (the key is configurable) to see if there is a user configured color scheme, if not, it will use users' system preferences. When you change the `isDark` ref, it will update the corresponding element's attribute and then store the preference to storage (default key: `vueuse-color-scheme`) for persistence.

> Please note `useDark` only handles the DOM attribute changes for you to apply proper selector in your CSS. It does NOT handle the actual style, theme or CSS for you.

## Configuration

By default, it uses [Tailwind CSS favored dark mode](https://tailwindcss.com/docs/dark-mode#toggling-dark-mode-manually), which enables dark mode when class `dark` is applied to the `html` tag, for example:

```html
<!--light-->
<html>
  ...
</html>

<!--dark-->
<html class="dark">
  ...
</html>
```

Still, you can also customize it to make it work with most CSS frameworks.

For example:

```ts
import { useDark } from '@vueuse/core'
// ---cut---
const isDark = useDark({
  selector: 'body',
  attribute: 'color-scheme',
  valueDark: 'dark',
  valueLight: 'light',
})
```

will work like

```html
<!--light-->
<html>
  <body color-scheme="light">
    ...
  </body>
</html>

<!--dark-->
<html>
  <body color-scheme="dark">
    ...
  </body>
</html>
```

If the configuration above still does not fit your needs, you can use the`onChanged` option to take full control over how you handle updates.

```ts
import { useDark } from '@vueuse/core'
// ---cut---
const isDark = useDark({
  onChanged(dark) {
    // update the dom, call the API or something
  },
})
```

## Component Usage

```vue
<template>
  <UseDark v-slot="{ isDark, toggleDark }">
    <button @click="toggleDark()">
      Is Dark: {{ isDark }}
    </button>
  </UseDark>
</template>
```

## Type Declarations

```ts
export interface UseDarkOptions extends Omit<
  UseColorModeOptions<BasicColorSchema>,
  "modes" | "onChanged"
> {
  /**
   * Value applying to the target element when isDark=true
   *
   * @default 'dark'
   */
  valueDark?: string
  /**
   * Value applying to the target element when isDark=false
   *
   * @default ''
   */
  valueLight?: string
  /**
   * A custom handler for handle the updates.
   * When specified, the default behavior will be overridden.
   *
   * @default undefined
   */
  onChanged?: (
    isDark: boolean,
    defaultHandler: (mode: BasicColorSchema) => void,
    mode: BasicColorSchema,
  ) => void
}
export type UseDarkReturn = WritableComputedRef<boolean>
/**
 * Reactive dark mode with auto data persistence.
 *
 * @see https://vueuse.org/useDark
 * @param options
 */
export declare function useDark(options?: UseDarkOptions): UseDarkReturn
```

---

<!-- source: references/useDateFormat.md -->
---
category: Time
---

# useDateFormat

Get the formatted date according to the string of tokens passed in, inspired
by [dayjs](https://github.com/iamkun/dayjs).

**List of all available formats (HH:mm:ss by default):**

| Format | Output                   | Description                             |
| ------ | ------------------------ | --------------------------------------- |
| `Yo`   | 2018th                   | Ordinal formatted year                  |
| `YY`   | 18                       | Two-digit year                          |
| `YYYY` | 2018                     | Four-digit year                         |
| `M`    | 1-12                     | The month, beginning at 1               |
| `Mo`   | 1st, 2nd, ..., 12th      | The month, ordinal formatted            |
| `MM`   | 01-12                    | The month, 2-digits                     |
| `MMM`  | Jan-Dec                  | The abbreviated month name              |
| `MMMM` | January-December         | The full month name                     |
| `D`    | 1-31                     | The day of the month                    |
| `Do`   | 1st, 2nd, ..., 31st      | The day of the month, ordinal formatted |
| `DD`   | 01-31                    | The day of the month, 2-digits          |
| `H`    | 0-23                     | The hour                                |
| `Ho`   | 0th, 1st, 2nd, ..., 23rd | The hour, ordinal formatted             |
| `HH`   | 00-23                    | The hour, 2-digits                      |
| `h`    | 1-12                     | The hour, 12-hour clock                 |
| `ho`   | 1st, 2nd, ..., 12th      | The hour, 12-hour clock, sorted         |
| `hh`   | 01-12                    | The hour, 12-hour clock, 2-digits       |
| `m`    | 0-59                     | The minute                              |
| `mo`   | 0th, 1st, ..., 59th      | The minute, ordinal formatted           |
| `mm`   | 00-59                    | The minute, 2-digits                    |
| `s`    | 0-59                     | The second                              |
| `so`   | 0th, 1st, ..., 59th      | The second, ordinal formatted           |
| `ss`   | 00-59                    | The second, 2-digits                    |
| `SSS`  | 000-999                  | The millisecond, 3-digits               |
| `A`    | AM PM                    | The meridiem                            |
| `AA`   | A.M. P.M.                | The meridiem, periods                   |
| `a`    | am pm                    | The meridiem, lowercase                 |
| `aa`   | a.m. p.m.                | The meridiem, lowercase and periods     |
| `d`    | 0-6                      | The day of the week, with Sunday as 0   |
| `dd`   | S-S                      | The min name of the day of the week     |
| `ddd`  | Sun-Sat                  | The short name of the day of the week   |
| `dddd` | Sunday-Saturday          | The name of the day of the week         |
| `z`    | GMT, GMT+1               | The timezone with offset                |
| `zz`   | GMT, GMT+1               | The timezone with offset                |
| `zzz`  | GMT, GMT+1               | The timezone with offset                |
| `zzzz` | GMT, GMT+01:00           | The long timezone with offset           |

- Meridiem is customizable by defining `customMeridiem` in `options`.

## Usage

### Basic

```vue
<script setup lang="ts">
import { useDateFormat, useNow } from '@vueuse/core'

const formatted = useDateFormat(useNow(), 'YYYY-MM-DD HH:mm:ss')
</script>

<template>
  <div>{{ formatted }}</div>
</template>
```

### Use with locales

```vue
<script setup lang="ts">
import { useDateFormat, useNow } from '@vueuse/core'

const formatted = useDateFormat(useNow(), 'YYYY-MM-DD (ddd)', { locales: 'en-US' })
</script>

<template>
  <div>{{ formatted }}</div>
</template>
```

### Use with custom meridiem

```vue
<script setup lang="ts">
import { useDateFormat } from '@vueuse/core'

function customMeridiem(hours: number, minutes: number, isLowercase?: boolean, hasPeriod?: boolean) {
  const m = hours > 11 ? (isLowercase ? 'μμ' : 'ΜΜ') : (isLowercase ? 'πμ' : 'ΠΜ')
  return hasPeriod ? m.split('').reduce((acc, current) => acc += `${current}.`, '') : m
}

const am = useDateFormat('2022-01-01 05:05:05', 'hh:mm:ss A', { customMeridiem })
// am.value = '05:05:05 ΠΜ'
const pm = useDateFormat('2022-01-01 17:05:05', 'hh:mm:ss AA', { customMeridiem })
// pm.value = '05:05:05 Μ.Μ.'
</script>
```

## Type Declarations

```ts
export type DateLike = Date | number | string | undefined
export interface UseDateFormatOptions {
  /**
   * The locale(s) to used for dd/ddd/dddd/MMM/MMMM format
   *
   * [MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl#locales_argument).
   */
  locales?: MaybeRefOrGetter<Intl.LocalesArgument>
  /**
   * A custom function to re-modify the way to display meridiem
   *
   */
  customMeridiem?: (
    hours: number,
    minutes: number,
    isLowercase?: boolean,
    hasPeriod?: boolean,
  ) => string
}
export declare function formatDate(
  date: Date,
  formatStr: string,
  options?: UseDateFormatOptions,
): string
export declare function normalizeDate(date: DateLike): Date
export type UseDateFormatReturn = ComputedRef<string>
/**
 * Get the formatted date according to the string of tokens passed in.
 *
 * @see https://vueuse.org/useDateFormat
 * @param date - The date to format, can either be a `Date` object, a timestamp, or a string
 * @param formatStr - The combination of tokens to format the date
 * @param options - UseDateFormatOptions
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useDateFormat(
  date: MaybeRefOrGetter<DateLike>,
  formatStr?: MaybeRefOrGetter<string>,
  options?: UseDateFormatOptions,
): UseDateFormatReturn
```

---

<!-- source: references/useDebounceFn.md -->
---
category: Utilities
related: useThrottleFn
---

# useDebounceFn

Debounce execution of a function.

> Debounce is an overloaded waiter: if you keep asking, your requests will be ignored until you stop and give them some time to think about your latest inquiry.

## Usage

```ts
import { useDebounceFn, useEventListener } from '@vueuse/core'

const debouncedFn = useDebounceFn(() => {
  // do something
}, 1000)

useEventListener(window, 'resize', debouncedFn)
```

You can also pass a 3rd parameter to this, with a maximum wait time, similar to [lodash debounce](https://lodash.com/docs/4.17.15#debounce)

```ts
import { useDebounceFn, useEventListener } from '@vueuse/core'

// If no invokation after 5000ms due to repeated input,
// the function will be called anyway.
const debouncedFn = useDebounceFn(() => {
  // do something
}, 1000, { maxWait: 5000 })

useEventListener(window, 'resize', debouncedFn)
```

Optionally, you can get the return value of the function using promise operations.

```ts
import { useDebounceFn } from '@vueuse/core'

const debouncedRequest = useDebounceFn(() => 'response', 1000)

debouncedRequest().then((value) => {
  console.log(value) // 'response'
})

// or use async/await
async function doRequest() {
  const value = await debouncedRequest()
  console.log(value) // 'response'
}
```

Since unhandled rejection error is quite annoying when developer doesn't need the return value, the promise will **NOT** be rejected if the function is canceled **by default**. You need to specify the option `rejectOnCancel: true` to capture the rejection.

```ts
import { useDebounceFn } from '@vueuse/core'

const debouncedRequest = useDebounceFn(() => 'response', 1000, { rejectOnCancel: true })

debouncedRequest()
  .then((value) => {
    // do something
  })
  .catch(() => {
    // do something when canceled
  })

// calling it again will cancel the previous request and gets rejected
setTimeout(debouncedRequest, 500)
```

## Recommended Reading

- [**Debounce vs Throttle**: Definitive Visual Guide](https://kettanaito.com/blog/debounce-vs-throttle)

## Type Declarations

```ts
export type UseDebounceFnReturn<T extends FunctionArgs> = PromisifyFn<T>
/**
 * Debounce execution of a function.
 *
 * @see https://vueuse.org/useDebounceFn
 * @param  fn          A function to be executed after delay milliseconds debounced.
 * @param  ms          A zero-or-greater delay in milliseconds. For event callbacks, values around 100 or 250 (or even higher) are most useful.
 * @param  options     Options
 *
 * @return A new, debounce, function.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useDebounceFn<T extends FunctionArgs>(
  fn: T,
  ms?: MaybeRefOrGetter<number>,
  options?: DebounceFilterOptions,
): UseDebounceFnReturn<T>
```

---

<!-- source: references/useDebouncedRefHistory.md -->
---
category: State
related:
  - useRefHistory
  - useThrottledRefHistory
---

# useDebouncedRefHistory

Shorthand for `useRefHistory` with debounced filter.

## Usage

This function takes a snapshot of your counter after 1000ms when the value of it starts to change.

```ts
import { useDebouncedRefHistory } from '@vueuse/core'
import { shallowRef } from 'vue'

const counter = shallowRef(0)
const { history, undo, redo } = useDebouncedRefHistory(counter, { deep: true, debounce: 1000 })
```

## Type Declarations

```ts
/**
 * Shorthand for [useRefHistory](https://vueuse.org/useRefHistory) with debounce filter.
 *
 * @see https://vueuse.org/useDebouncedRefHistory
 * @param source
 * @param options
 */
export declare function useDebouncedRefHistory<Raw, Serialized = Raw>(
  source: Ref<Raw>,
  options?: Omit<UseRefHistoryOptions<Raw, Serialized>, "eventFilter"> & {
    debounce?: MaybeRefOrGetter<number>
  },
): UseRefHistoryReturn<Raw, Serialized>
```

---

<!-- source: references/useDeviceMotion.md -->
---
category: Sensors
---

# useDeviceMotion

Reactive [DeviceMotionEvent](https://developer.mozilla.org/en-US/docs/Web/API/DeviceMotionEvent). Provide web developers with information about the speed of changes for the device's position and orientation.

## Usage

```ts
import { useDeviceMotion } from '@vueuse/core'

const {
  acceleration,
  accelerationIncludingGravity,
  rotationRate,
  interval,
} = useDeviceMotion()
```

> Note: For iOS, you need to use `trigger` and bind it with user interaction.
> After permission granted, the API will run automatically

| State                        | Type            | Description                                                                                                          |
| ---------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------- |
| acceleration                 | `object`        | An object giving the acceleration of the device on the three axis X, Y and Z.                                        |
| accelerationIncludingGravity | `object`        | An object giving the acceleration of the device on the three axis X, Y and Z with the effect of gravity.             |
| rotationRate                 | `object`        | An object giving the rate of change of the device's orientation on the three orientation axis alpha, beta and gamma. |
| interval                     | `Number`        | A number representing the interval of time, in milliseconds, at which data is obtained from the device..             |
| ensurePermissions            | `boolean`       | Indicates whether the platform requires permission to use the API                                                    |
| permissionGranted            | `boolean`       | Indicates whether the user has granted permission. The default is always false                                       |
| trigger                      | `Promise<void>` | An async function to request user permission. The API runs automatically once permission is granted                  |

You can find [more information about the state on the MDN](https://developer.mozilla.org/en-US/docs/Web/API/DeviceMotionEvent#instance_properties).

## Component Usage

```vue
<template>
  <UseDeviceMotion v-slot="{ acceleration }">
    Acceleration: {{ acceleration }}
  </UseDeviceMotion>
</template>
```

## Type Declarations

```ts
export interface UseDeviceMotionOptions
  extends ConfigurableWindow, ConfigurableEventFilter {
  /**
   * Request for permissions immediately if it's not granted,
   * otherwise label and deviceIds could be empty
   *
   * @default false
   */
  requestPermissions?: boolean
}
/** @deprecated use {@link UseDeviceMotionOptions} instead */
export type DeviceMotionOptions = UseDeviceMotionOptions
export interface UseDeviceMotionReturn extends Supportable {
  acceleration: Ref<DeviceMotionEventAcceleration | null>
  accelerationIncludingGravity: Ref<DeviceMotionEventAcceleration | null>
  rotationRate: Ref<DeviceMotionEventRotationRate | null>
  interval: ShallowRef<number>
  requirePermissions: ComputedRef<boolean>
  ensurePermissions: () => Promise<void>
  permissionGranted: ShallowRef<boolean>
}
/**
 * Reactive DeviceMotionEvent.
 *
 * @see https://vueuse.org/useDeviceMotion
 * @param options
 */
export declare function useDeviceMotion(
  options?: UseDeviceMotionOptions,
): UseDeviceMotionReturn
```

---

<!-- source: references/useDeviceOrientation.md -->
---
category: Sensors
---

# useDeviceOrientation

Reactive [DeviceOrientationEvent](https://developer.mozilla.org/en-US/docs/Web/API/DeviceOrientationEvent). Provide web developers with information from the physical orientation of the device running the web page.

## Usage

```ts
import { useDeviceOrientation } from '@vueuse/core'

const {
  isAbsolute,
  alpha,
  beta,
  gamma,
} = useDeviceOrientation()
```

| State      | Type      | Description                                                                                                                |
| ---------- | --------- | -------------------------------------------------------------------------------------------------------------------------- |
| isAbsolute | `boolean` | A boolean that indicates whether or not the device is providing orientation data absolutely.                               |
| alpha      | `number`  | A number representing the motion of the device around the z axis, express in degrees with values ranging from 0 to 360.    |
| beta       | `number`  | A number representing the motion of the device around the x axis, express in degrees with values ranging from -180 to 180. |
| gamma      | `number`  | A number representing the motion of the device around the y axis, express in degrees with values ranging from -90 to 90.   |

You can find [more information about the state on the MDN](https://developer.mozilla.org/en-US/docs/Web/API/DeviceOrientationEvent#instance_properties).

## Component Usage

```vue
<template>
  <UseDeviceOrientation v-slot="{ alpha, beta, gamma }">
    Alpha: {{ alpha }}
    Beta: {{ beta }}
    Gamma: {{ gamma }}
  </UseDeviceOrientation>
</template>
```

## Type Declarations

```ts
export interface UseDeviceOrientationOptions extends ConfigurableWindow {}
export interface UseDeviceOrientationReturn extends Supportable {
  isAbsolute: ShallowRef<boolean, boolean>
  alpha: Ref<number | null, number | null>
  beta: Ref<number | null, number | null>
  gamma: Ref<number | null, number | null>
}
/**
 * Reactive DeviceOrientationEvent.
 *
 * @see https://vueuse.org/useDeviceOrientation
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useDeviceOrientation(
  options?: UseDeviceOrientationOptions,
): UseDeviceOrientationReturn
```

---

<!-- source: references/useDevicePixelRatio.md -->
---
category: Sensors
---

# useDevicePixelRatio

Reactively track [`window.devicePixelRatio`](https://developer.mozilla.org/docs/Web/API/Window/devicePixelRatio)

> NOTE: there is no event listener for `window.devicePixelRatio` change. So this function uses [`Testing media queries programmatically (window.matchMedia)`](https://developer.mozilla.org/en-US/docs/Web/CSS/Media_Queries/Testing_media_queries) applying the same mechanism as described in [this example](https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio#monitoring_screen_resolution_or_zoom_level_changes).

## Usage

```ts
import { useDevicePixelRatio } from '@vueuse/core'

const { pixelRatio } = useDevicePixelRatio()
```

## Component Usage

```vue
<template>
  <UseDevicePixelRatio v-slot="{ pixelRatio }">
    Pixel Ratio: {{ pixelRatio }}
  </UseDevicePixelRatio>
</template>
```

## Type Declarations

```ts
export interface UseDevicePixelRatioOptions extends ConfigurableWindow {}
export interface UseDevicePixelRatioReturn {
  pixelRatio: ShallowRef<number>
  stop: WatchStopHandle
}
/**
 * Reactively track `window.devicePixelRatio`.
 *
 * @see https://vueuse.org/useDevicePixelRatio
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useDevicePixelRatio(
  options?: UseDevicePixelRatioOptions,
): UseDevicePixelRatioReturn
```

---

<!-- source: references/useDevicesList.md -->
---
category: Sensors
---

# useDevicesList

Reactive [enumerateDevices](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices) listing available input/output devices.

## Usage

```ts
import { useDevicesList } from '@vueuse/core'

const {
  devices,
  videoInputs: cameras,
  audioInputs: microphones,
  audioOutputs: speakers,
} = useDevicesList()
```

## Requesting Permissions

To request permissions, use the `ensurePermissions` method.

```ts
import { useDevicesList } from '@vueuse/core'
// ---cut---
const {
  ensurePermissions,
  permissionGranted,
} = useDevicesList()

await ensurePermissions()
console.log(permissionsGranted.value)
```

# Component

```vue
<template>
  <UseDevicesList v-slot="{ videoInputs, audioInputs, audioOutputs }">
    Cameras: {{ videoInputs }}
    Microphones: {{ audioInputs }}
    Speakers: {{ audioOutputs }}
  </UseDevicesList>
</template>
```

## Type Declarations

```ts
export interface UseDevicesListOptions extends ConfigurableNavigator {
  onUpdated?: (devices: MediaDeviceInfo[]) => void
  /**
   * Request for permissions immediately if it's not granted,
   * otherwise label and deviceIds could be empty
   *
   * @default false
   */
  requestPermissions?: boolean
  /**
   * Request for types of media permissions
   *
   * @default { audio: true, video: true }
   */
  constraints?: MediaStreamConstraints
}
export interface UseDevicesListReturn extends Supportable {
  /**
   * All devices
   */
  devices: Ref<MediaDeviceInfo[]>
  videoInputs: ComputedRef<MediaDeviceInfo[]>
  audioInputs: ComputedRef<MediaDeviceInfo[]>
  audioOutputs: ComputedRef<MediaDeviceInfo[]>
  permissionGranted: ShallowRef<boolean>
  ensurePermissions: () => Promise<boolean>
}
/**
 * Reactive `enumerateDevices` listing available input/output devices
 *
 * @see https://vueuse.org/useDevicesList
 * @param options
 */
export declare function useDevicesList(
  options?: UseDevicesListOptions,
): UseDevicesListReturn
```

---

<!-- source: references/useDisplayMedia.md -->
---
category: Sensors
related: useUserMedia
---

# useDisplayMedia

Reactive [`mediaDevices.getDisplayMedia`](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia) streaming.

## Usage

```vue
<script setup lang="ts">
import { useDisplayMedia } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const { stream, start } = useDisplayMedia()

// start streaming
start()

const videoRef = useTemplateRef('video')
watchEffect(() => {
  // preview on a video element
  videoRef.value.srcObject = stream.value
})
</script>

<template>
  <video ref="video" />
</template>
```

## Type Declarations

```ts
export interface UseDisplayMediaOptions extends ConfigurableNavigator {
  /**
   * If the stream is enabled
   * @default false
   */
  enabled?: MaybeRef<boolean>
  /**
   * If the stream video media constraints
   */
  video?: boolean | MediaTrackConstraints | undefined
  /**
   * If the stream audio media constraints
   */
  audio?: boolean | MediaTrackConstraints | undefined
}
export interface UseDisplayMediaReturn extends Supportable {
  stream: ShallowRef<MediaStream | undefined>
  start: () => Promise<MediaStream | undefined>
  stop: () => void
  enabled: ShallowRef<boolean>
}
/**
 * Reactive `mediaDevices.getDisplayMedia` streaming
 *
 * @see https://vueuse.org/useDisplayMedia
 * @param options
 */
export declare function useDisplayMedia(
  options?: UseDisplayMediaOptions,
): UseDisplayMediaReturn
```

---

<!-- source: references/useDocumentVisibility.md -->
---
category: Elements
---

# useDocumentVisibility

Reactively track [`document.visibilityState`](https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilityState)

## Usage

```vue
<script setup lang="ts">
import { useDocumentVisibility } from '@vueuse/core'

const visibility = useDocumentVisibility()
</script>
```

## Component Usage

```vue
<template>
  <UseDocumentVisibility v-slot="{ visibility }">
    Document Visibility: {{ visibility }}
  </UseDocumentVisibility>
</template>
```

## Type Declarations

```ts
export interface UseDocumentVisibilityOptions extends ConfigurableDocument {}
export type UseDocumentVisibilityReturn = ShallowRef<DocumentVisibilityState>
/**
 * Reactively track `document.visibilityState`.
 *
 * @see https://vueuse.org/useDocumentVisibility
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useDocumentVisibility(
  options?: UseDocumentVisibilityOptions,
): UseDocumentVisibilityReturn
```

---

<!-- source: references/useDraggable.md -->
---
category: Elements
---

# useDraggable

Make elements draggable.

## Usage

```vue
<script setup lang="ts">
import { useDraggable } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')

// `style` will be a helper computed for `left: ?px; top: ?px;`
const { x, y, style } = useDraggable(el, {
  initialValue: { x: 40, y: 40 },
})
</script>

<template>
  <div ref="el" :style="style" style="position: fixed">
    Drag me! I am at {{ x }}, {{ y }}
  </div>
</template>
```

### Return Values

| Property     | Type                   | Description                             |
| ------------ | ---------------------- | --------------------------------------- |
| `x`          | `Ref<number>`          | Current x position                      |
| `y`          | `Ref<number>`          | Current y position                      |
| `position`   | `Ref<{x, y}>`          | Current position object                 |
| `isDragging` | `ComputedRef<boolean>` | Whether currently dragging              |
| `style`      | `ComputedRef<string>`  | CSS style string `left: ?px; top: ?px;` |

### Options

```ts
useDraggable(el, {
  // Initial position (default: { x: 0, y: 0 })
  initialValue: { x: 40, y: 40 },
  // Restrict dragging to specific axis: 'x', 'y', or 'both' (default)
  axis: 'both',
  // Only trigger when clicking directly on the element (default: false)
  exact: false,
  // Prevent default browser behavior (default: false)
  preventDefault: true,
  // Stop event propagation (default: false)
  stopPropagation: false,
  // Use capture phase for events (default: true)
  capture: true,
  // Disable dragging (default: false)
  disabled: false,
  // Mouse buttons that trigger drag (default: [0] - left button)
  buttons: [0],
  // Pointer types to listen to (default: ['mouse', 'touch', 'pen'])
  pointerTypes: ['mouse', 'touch', 'pen'],
  // Custom drag handle element (default: target element)
  handle: handleRef,
  // Container element for bounds (default: none)
  containerElement: containerRef,
  // Element to attach pointermove/pointerup events (default: window)
  draggingElement: window,
  // Callbacks
  onStart: (position, event) => {
    // Return false to prevent dragging
  },
  onMove: (position, event) => {},
  onEnd: (position, event) => {},
})
```

### Prevent Default

Set `preventDefault: true` to override the default drag-and-drop behavior of certain elements in the browser (e.g., images).

```ts
import { useDraggable } from '@vueuse/core'

const { x, y, style } = useDraggable(el, {
  preventDefault: true,
})
```

### Container Bounds

Use `containerElement` to constrain dragging within a container.

```ts
import { useDraggable } from '@vueuse/core'

const { x, y } = useDraggable(el, {
  containerElement: containerRef,
})
```

Set `autoScroll: true` to enable auto-scroll when dragging near the edges.

```ts
const { x, y, style } = useDraggable(el, {
  autoScroll: {
    speed: 2, // Control the speed of auto-scroll.
    margin: 30, // Set the margin from the edge that triggers auto-scroll.
    direction: 'both' // Determine the direction of auto-scroll.
  },
})
```

## Component Usage

```vue
<template>
  <UseDraggable v-slot="{ x, y }" :initial-value="{ x: 10, y: 10 }">
    Drag me! I am at {{ x }}, {{ y }}
  </UseDraggable>
</template>
```

For component usage, additional props `storageKey` and `storageType` can be passed to the component and enable the persistence of the element position.

```vue
<template>
  <UseDraggable storage-key="vueuse-draggable" storage-type="session">
    Refresh the page and I am still in the same position!
  </UseDraggable>
</template>
```

## Type Declarations

```ts
export interface UseDraggableOptions {
  /**
   * Only start the dragging when click on the element directly
   *
   * @default false
   */
  exact?: MaybeRefOrGetter<boolean>
  /**
   * Prevent events defaults
   *
   * @default false
   */
  preventDefault?: MaybeRefOrGetter<boolean>
  /**
   * Prevent events propagation
   *
   * @default false
   */
  stopPropagation?: MaybeRefOrGetter<boolean>
  /**
   * Whether dispatch events in capturing phase
   *
   * @default true
   */
  capture?: boolean
  /**
   * Element to attach `pointermove` and `pointerup` events to.
   *
   * @default window
   */
  draggingElement?: MaybeRefOrGetter<
    HTMLElement | SVGElement | Window | Document | null | undefined
  >
  /**
   * Element for calculating bounds (If not set, it will use the event's target).
   *
   * @default undefined
   */
  containerElement?: MaybeRefOrGetter<
    HTMLElement | SVGElement | null | undefined
  >
  /**
   * Handle that triggers the drag event
   *
   * @default target
   */
  handle?: MaybeRefOrGetter<HTMLElement | SVGElement | null | undefined>
  /**
   * Pointer types that listen to.
   *
   * @default ['mouse', 'touch', 'pen']
   */
  pointerTypes?: PointerType[]
  /**
   * Initial position of the element.
   *
   * @default { x: 0, y: 0 }
   */
  initialValue?: MaybeRefOrGetter<Position>
  /**
   * Callback when the dragging starts. Return `false` to prevent dragging.
   */
  onStart?: (position: Position, event: PointerEvent) => void | false
  /**
   * Callback during dragging.
   */
  onMove?: (position: Position, event: PointerEvent) => void
  /**
   * Callback when dragging end.
   */
  onEnd?: (position: Position, event: PointerEvent) => void
  /**
   * Axis to drag on.
   *
   * @default 'both'
   */
  axis?: "x" | "y" | "both"
  /**
   * Disabled drag and drop.
   *
   * @default false
   */
  disabled?: MaybeRefOrGetter<boolean>
  /**
   * Mouse buttons that are allowed to trigger drag events.
   *
   * - `0`: Main button, usually the left button or the un-initialized state
   * - `1`: Auxiliary button, usually the wheel button or the middle button (if present)
   * - `2`: Secondary button, usually the right button
   * - `3`: Fourth button, typically the Browser Back button
   * - `4`: Fifth button, typically the Browser Forward button
   *
   * @see https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent/button#value
   * @default [0]
   */
  buttons?: MaybeRefOrGetter<number[]>
  /**
   * Whether to restrict dragging within the visible area of the container.
   *
   * If enabled, the draggable element will not leave the visible area of its container,
   * ensuring it remains within the viewport of the container during the drag.
   *
   * @default false
   */
  restrictInView?: MaybeRefOrGetter<boolean>
  /**
   * Whether to enable auto-scroll when dragging near the edges.
   *
   * @default false
   */
  autoScroll?: MaybeRefOrGetter<
    | boolean
    | {
        /**
         * Speed of auto-scroll.
         *
         * @default 2
         */
        speed?: MaybeRefOrGetter<number | Position>
        /**
         * Margin from the edge to trigger auto-scroll.
         *
         * @default 30
         */
        margin?: MaybeRefOrGetter<number | Position>
        /**
         * Direction of auto-scroll.
         *
         * @default 'both'
         */
        direction?: "x" | "y" | "both"
      }
  >
}
export interface UseDraggableReturn {
  x: Ref<number>
  y: Ref<number>
  position: Ref<Position>
  isDragging: ComputedRef<boolean>
  style: ComputedRef<string>
}
/**
 * Make elements draggable.
 *
 * @see https://vueuse.org/useDraggable
 * @param target
 * @param options
 */
export declare function useDraggable(
  target: MaybeRefOrGetter<HTMLElement | SVGElement | null | undefined>,
  options?: UseDraggableOptions,
): UseDraggableReturn
```

---

<!-- source: references/useDrauu.md -->
---
category: '@Integrations'
---

# useDrauu

Reactive instance for [drauu](https://github.com/antfu/drauu).

## Install

```bash
npm i drauu@^0
```

## Usage

```vue
<script setup lang="ts">
import { toRefs } from '@vueuse/core'
import { useDrauu } from '@vueuse/integrations/useDrauu'
import { useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const { undo, redo, canUndo, canRedo, brush } = useDrauu(target)
const { color, size } = toRefs(brush)
</script>

<template>
  <svg ref="target" />
</template>
```

## Type Declarations

```ts
export type UseDrauuOptions = Omit<Options, "el">
export interface UseDrauuReturn {
  drauuInstance: Ref<Drauu | undefined>
  load: (svg: string) => void
  dump: () => string | undefined
  clear: () => void
  cancel: () => void
  undo: () => boolean | undefined
  redo: () => boolean | undefined
  canUndo: ShallowRef<boolean>
  canRedo: ShallowRef<boolean>
  brush: Ref<Brush>
  onChanged: EventHookOn
  onCommitted: EventHookOn
  onStart: EventHookOn
  onEnd: EventHookOn
  onCanceled: EventHookOn
}
/**
 * Reactive drauu
 *
 * @see https://vueuse.org/useDrauu
 * @param target The target svg element
 * @param options Drauu Options
 */
export declare function useDrauu(
  target: MaybeComputedElementRef,
  options?: UseDrauuOptions,
): UseDrauuReturn
```

---

<!-- source: references/useDropZone.md -->
---
category: Elements
---

# useDropZone

Create a zone where files can be dropped.

::: warning

Due to Safari browser limitations, file type validation is only possible during the drop event, not during drag events. As a result, the `isOverDropZone` value will always be `true` during drag operations in Safari, regardless of file type.

:::

## Usage

```vue
<script setup lang="ts">
import { useDropZone } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const dropZoneRef = useTemplateRef('dropZoneRef')

function onDrop(files: File[] | null) {
  // called when files are dropped on zone
}

const { isOverDropZone } = useDropZone(dropZoneRef, {
  onDrop,
  // specify the types of data to be received.
  dataTypes: ['image/jpeg'],
  // control multi-file drop
  multiple: true,
  // whether to prevent default behavior for unhandled events
  preventDefaultForUnhandled: false,
})
</script>

<template>
  <div ref="dropZoneRef">
    Drop files here
  </div>
</template>
```

## Type Declarations

```ts
export interface UseDropZoneReturn {
  files: ShallowRef<File[] | null>
  isOverDropZone: ShallowRef<boolean>
}
export interface UseDropZoneOptions {
  /**
   * Allowed data types, if not set, all data types are allowed.
   * Also can be a function to check the data types.
   */
  dataTypes?:
    | MaybeRef<readonly string[]>
    | ((types: readonly string[]) => boolean)
  /**
   * Similar to dataTypes, but exposes the DataTransferItemList for custom validation.
   * If provided, this function takes precedence over dataTypes.
   */
  checkValidity?: (items: DataTransferItemList) => boolean
  onDrop?: (files: File[] | null, event: DragEvent) => void
  onEnter?: (files: File[] | null, event: DragEvent) => void
  onLeave?: (files: File[] | null, event: DragEvent) => void
  onOver?: (files: File[] | null, event: DragEvent) => void
  /**
   * Allow multiple files to be dropped. Defaults to true.
   */
  multiple?: boolean
  /**
   * Prevent default behavior for unhandled events. Defaults to false.
   */
  preventDefaultForUnhandled?: boolean
}
export declare function useDropZone(
  target: MaybeRefOrGetter<HTMLElement | Document | null | undefined>,
  options?: UseDropZoneOptions | UseDropZoneOptions["onDrop"],
): UseDropZoneReturn
```

---

<!-- source: references/useElementBounding.md -->
---
category: Elements
---

# useElementBounding

Reactive [bounding box](https://developer.mozilla.org/en-US/docs/Web/API/Element/getBoundingClientRect) of an HTML element

## Usage

```vue
<script setup lang="ts">
import { useElementBounding } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { x, y, top, right, bottom, left, width, height } = useElementBounding(el)
</script>

<template>
  <div ref="el" />
</template>
```

## Component Usage

```vue
<template>
  <UseElementBounding v-slot="{ width, height }">
    Width: {{ width }} Height: {{ height }}
  </UseElementBounding>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vElementBounding } from '@vueuse/components'

interface BoundingType {
  height: number
  bottom: number
  left: number
  right: number
  top: number
  width: number
  x: number
  y: number
}

function onBounding({ height, bottom, left, right, top, width, x, y }: BoundingType) {
  console.log(height, bottom, left, right, top, width, x, y)
}

const options = {
  reset: true,
  windowResize: true,
  windowScroll: true,
  immediate: true,
  updateTiming: 'sync',
}
</script>

<template>
  <textarea v-element-bounding="onBounding" />
  <!-- with options -->
  <textarea v-element-bounding="[onBounding, options]" />
</template>
```

## Type Declarations

```ts
export interface UseElementBoundingOptions {
  /**
   * Reset values to 0 on component unmounted
   *
   * @default true
   */
  reset?: boolean
  /**
   * Listen to window resize event
   *
   * @default true
   */
  windowResize?: boolean
  /**
   * Listen to window scroll event
   *
   * @default true
   */
  windowScroll?: boolean
  /**
   * Immediately call update on component mounted
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Timing to recalculate the bounding box
   *
   * Setting to `next-frame` can be useful when using this together with something like {@link useBreakpoints}
   * and therefore the layout (which influences the bounding box of the observed element) is not updated on the current tick.
   *
   * @default 'sync'
   */
  updateTiming?: "sync" | "next-frame"
}
export interface UseElementBoundingReturn {
  height: ShallowRef<number>
  bottom: ShallowRef<number>
  left: ShallowRef<number>
  right: ShallowRef<number>
  top: ShallowRef<number>
  width: ShallowRef<number>
  x: ShallowRef<number>
  y: ShallowRef<number>
  update: () => void
}
/**
 * Reactive bounding box of an HTML element.
 *
 * @see https://vueuse.org/useElementBounding
 * @param target
 */
export declare function useElementBounding(
  target: MaybeComputedElementRef,
  options?: UseElementBoundingOptions,
): UseElementBoundingReturn
```

---

<!-- source: references/useElementByPoint.md -->
---
category: Sensors
---

# useElementByPoint

Reactive element by point.

## Usage

```ts
import { useElementByPoint, useMouse } from '@vueuse/core'

const { x, y } = useMouse({ type: 'client' })
const { element } = useElementByPoint({ x, y })
```

## Type Declarations

```ts
export interface UseElementByPointOptions<Multiple extends boolean = false>
  extends ConfigurableDocument, ConfigurableScheduler {
  x: MaybeRefOrGetter<number>
  y: MaybeRefOrGetter<number>
  multiple?: MaybeRefOrGetter<Multiple>
  /** @deprecated Please use `scheduler` option instead */
  immediate?: boolean
  /** @deprecated Please use `scheduler` option instead */
  interval?: "requestAnimationFrame" | number
}
export interface UseElementByPointReturn<Multiple extends boolean = false>
  extends Supportable, Pausable {
  element: ShallowRef<
    Multiple extends true ? HTMLElement[] : HTMLElement | null
  >
}
/**
 * Reactive element by point.
 *
 * @see https://vueuse.org/useElementByPoint
 * @param options - UseElementByPointOptions
 */
export declare function useElementByPoint<M extends boolean = false>(
  options: UseElementByPointOptions<M>,
): UseElementByPointReturn<M>
```

---

<!-- source: references/useElementHover.md -->
---
category: Sensors
---

# useElementHover

Reactive element's hover state.

## Usage

```vue
<script setup lang="ts">
import { useElementHover } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const myHoverableElement = useTemplateRef('myHoverableElement')
const isHovered = useElementHover(myHoverableElement)
</script>

<template>
  <button ref="myHoverableElement">
    {{ isHovered }}
  </button>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vElementHover } from '@vueuse/components'
import { shallowRef } from 'vue'

const isHovered = shallowRef(false)
function onHover(state: boolean) {
  isHovered.value = state
}
</script>

<template>
  <button v-element-hover="onHover">
    {{ isHovered ? 'Thank you!' : 'Hover me' }}
  </button>
</template>
```

You can also provide hover options:

```vue
<script setup lang="ts">
import { vElementHover } from '@vueuse/components'
import { shallowRef } from 'vue'

const isHovered = shallowRef(false)
function onHover(hovered: boolean) {
  isHovered.value = hovered
}
</script>

<template>
  <button v-element-hover="[onHover, { delayEnter: 1000 }]">
    <span>{{ isHovered ? 'Thank you!' : 'Hover me' }}</span>
  </button>
</template>
```

## Type Declarations

```ts
export interface UseElementHoverOptions extends ConfigurableWindow {
  delayEnter?: number
  delayLeave?: number
  triggerOnRemoval?: boolean
}
export declare function useElementHover(
  el: MaybeRefOrGetter<EventTarget | null | undefined>,
  options?: UseElementHoverOptions,
): ShallowRef<boolean>
```

---

<!-- source: references/useElementSize.md -->
---
category: Elements
---

# useElementSize

Reactive size of an HTML element. [ResizeObserver MDN](https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver)

## Usage

```vue
<script setup lang="ts">
import { useElementSize } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { width, height } = useElementSize(el)
</script>

<template>
  <div ref="el">
    Height: {{ height }}
    Width: {{ width }}
  </div>
</template>
```

## Component Usage

```vue
<template>
  <UseElementSize v-slot="{ width, height }">
    Width: {{ width }} Height: {{ height }}
  </UseElementSize>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vElementSize } from '@vueuse/components'

function onResize({ width, height }: { width: number, height: number }) {
  console.log(width, height)
}
</script>

<template>
  <textarea v-element-size="onResize" />
  <!-- with options -->
  <textarea v-element-size="[onResize, { width: 100, height: 100 }, { box: 'content-box' }]" />
</template>
```

## Type Declarations

```ts
export interface ElementSize {
  width: number
  height: number
}
export interface UseElementSizeOptions extends UseResizeObserverOptions {}
export interface UseElementSizeReturn {
  width: ShallowRef<number>
  height: ShallowRef<number>
  stop: () => void
}
/**
 * Reactive size of an HTML element.
 *
 * @see https://vueuse.org/useElementSize
 */
export declare function useElementSize(
  target: MaybeComputedElementRef,
  initialSize?: ElementSize,
  options?: UseElementSizeOptions,
): UseElementSizeReturn
```

---

<!-- source: references/useElementVisibility.md -->
---
category: Elements
---

# useElementVisibility

Tracks the visibility of an element within the viewport.

## Usage

```vue
<script setup lang="ts">
import { useElementVisibility } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const targetIsVisible = useElementVisibility(target)
</script>

<template>
  <div ref="target">
    <h1>Hello world</h1>
  </div>
</template>
```

### rootMargin

If you wish to trigger your callback sooner before the element is fully visible, you can use
the `rootMargin` option (See [MDN IntersectionObserver/rootMargin](https://developer.mozilla.org/en-US/docs/Web/API/IntersectionObserver/rootMargin)).

```ts
import { useElementVisibility } from '@vueuse/core'
// ---cut---
const targetIsVisible = useElementVisibility(target, {
  rootMargin: '0px 0px 100px 0px',
})
```

### threshold

If you want to control the percentage of the visibility required to update the value, you can use the `threshold` option (See [MDN IntersectionObserver/threshold](https://developer.mozilla.org/en-US/docs/Web/API/IntersectionObserver/IntersectionObserver#threshold)).

```ts
const targetIsVisible = useElementVisibility(target, {
  threshold: 1.0, // 100% visible
})
```

## Component Usage

```vue
<template>
  <UseElementVisibility v-slot="{ isVisible }">
    Is Visible: {{ isVisible }}
  </UseElementVisibility>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vElementVisibility } from '@vueuse/components'
import { shallowRef, useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const isVisible = shallowRef(false)

function onElementVisibility(state) {
  isVisible.value = state
}
</script>

<template>
  <div v-element-visibility="onElementVisibility">
    {{ isVisible ? 'inside' : 'outside' }}
  </div>

  <!-- with options -->
  <div ref="target">
    <div v-element-visibility="[onElementVisibility, { scrollTarget: target }]">
      {{ isVisible ? 'inside' : 'outside' }}
    </div>
  </div>
</template>
```

## Type Declarations

```ts
export interface UseElementVisibilityOptions
  extends
    ConfigurableWindow,
    Pick<UseIntersectionObserverOptions, "rootMargin" | "threshold"> {
  /**
   * Initial value.
   *
   * @default false
   */
  initialValue?: boolean
  /**
   * The element that is used as the viewport for checking visibility of the target.
   */
  scrollTarget?: UseIntersectionObserverOptions["root"]
  /**
   * Stop tracking when element visibility changes for the first time
   *
   * @default false
   */
  once?: boolean
}
export type UseElementVisibilityReturn = ShallowRef<boolean>
/**
 * Tracks the visibility of an element within the viewport.
 *
 * @see https://vueuse.org/useElementVisibility
 */
export declare function useElementVisibility(
  element: MaybeComputedElementRef,
  options?: UseElementVisibilityOptions,
): UseElementVisibilityReturn
```

---

<!-- source: references/useEventBus.md -->
---
category: Utilities
---

# useEventBus

A basic event bus.

## Usage

```ts
import { useEventBus } from '@vueuse/core'

const bus = useEventBus<string>('news')

function listener(event: string) {
  console.log(`news: ${event}`)
}

// listen to an event
const unsubscribe = bus.on(listener)

// fire an event
bus.emit('The Tokyo Olympics has begun')

// unregister the listener
unsubscribe()
// or
bus.off(listener)

// clearing all listeners
bus.reset()
```

Listeners registered inside of components `setup` will be unregistered automatically when the component gets unmounted.

## TypeScript

Using `EventBusKey` is the key to bind the event type to the key, similar to Vue's [`InjectionKey`](https://antfu.me/posts/typed-provide-and-inject-in-vue) util.

```ts
// fooKey.ts
import type { EventBusKey } from '@vueuse/core'

export const fooKey: EventBusKey<{ name: foo }> = Symbol('symbol-key')
```

```ts
import { useEventBus } from '@vueuse/core'

import { fooKey } from './fooKey'

const bus = useEventBus(fooKey)

bus.on((e) => {
  // `e` will be `{ name: foo }`
})
```

## Type Declarations

```ts
export type EventBusListener<T = unknown, P = any> = (
  event: T,
  payload?: P,
) => void
export type EventBusEvents<T, P = any> = Set<EventBusListener<T, P>>
export interface EventBusKey<T> extends Symbol {}
export type EventBusIdentifier<T = unknown> = EventBusKey<T> | string | number
export interface UseEventBusReturn<T, P> {
  /**
   * Subscribe to an event. When calling emit, the listeners will execute.
   * @param listener watch listener.
   * @returns a stop function to remove the current callback.
   */
  on: (listener: EventBusListener<T, P>) => Fn
  /**
   * Similar to `on`, but only fires once
   * @param listener watch listener.
   * @returns a stop function to remove the current callback.
   */
  once: (listener: EventBusListener<T, P>) => Fn
  /**
   * Emit an event, the corresponding event listeners will execute.
   * @param event data sent.
   */
  emit: (event?: T, payload?: P) => void
  /**
   * Remove the corresponding listener.
   * @param listener watch listener.
   */
  off: (listener: EventBusListener<T>) => void
  /**
   * Clear all events
   */
  reset: () => void
}
export declare function useEventBus<T = unknown, P = any>(
  key: EventBusIdentifier<T>,
): UseEventBusReturn<T, P>
```

---

<!-- source: references/useEventListener.md -->
---
category: Browser
---

# useEventListener

Use EventListener with ease. Register using [addEventListener](https://developer.mozilla.org/en-US/docs/Web/API/EventTarget/addEventListener) on mounted, and [removeEventListener](https://developer.mozilla.org/en-US/docs/Web/API/EventTarget/removeEventListener) automatically on unmounted.

## Usage

```ts
import { useEventListener } from '@vueuse/core'

useEventListener(document, 'visibilitychange', (evt) => {
  console.log(evt)
})
```

### Default Target

When the target is omitted, it defaults to `window`:

```ts
import { useEventListener } from '@vueuse/core'

// Listens on window
useEventListener('resize', (evt) => {
  console.log(evt)
})
```

### Reactive Target

You can pass a ref as the event target, `useEventListener` will unregister the previous event and register the new one when the target changes.

```vue
<script setup lang="ts">
import { useEventListener } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const element = useTemplateRef('element')
useEventListener(element, 'keydown', (e) => {
  console.log(e.key)
})
</script>

<template>
  <div v-if="cond" ref="element">
    Div1
  </div>
  <div v-else ref="element">
    Div2
  </div>
</template>
```

### Multiple Events

You can pass an array of events to listen to multiple events at once:

```ts
import { useEventListener } from '@vueuse/core'

useEventListener(document, ['mouseenter', 'mouseleave'], (evt) => {
  console.log(evt.type)
})
```

### Multiple Targets

You can also pass an array of targets:

```ts
import { useEventListener } from '@vueuse/core'

const buttons = document.querySelectorAll('button')
useEventListener(buttons, 'click', (evt) => {
  console.log('Button clicked')
})
```

### Cleanup

Returns a cleanup function to manually unregister the listener:

```ts
import { useEventListener } from '@vueuse/core'

const cleanup = useEventListener(document, 'keydown', (e) => {
  console.log(e.key)
})

cleanup() // This will unregister the listener.
```

Note if your components also run in SSR (Server Side Rendering), you might get errors (like `document is not defined`) because DOM APIs like `document` and `window` are not available in Node.js. To avoid that you can put the logic inside `onMounted` hook.

```ts
import { useEventListener } from '@vueuse/core'
// ---cut---
// onMounted will only be called in the client side
// so it guarantees the DOM APIs are available.
onMounted(() => {
  useEventListener(document, 'keydown', (e) => {
    console.log(e.key)
  })
})
```

## Type Declarations

```ts
interface InferEventTarget<Events> {
  addEventListener: (event: Events, fn?: any, options?: any) => any
  removeEventListener: (event: Events, fn?: any, options?: any) => any
}
export type WindowEventName = keyof WindowEventMap
export type DocumentEventName = keyof DocumentEventMap
export type ShadowRootEventName = keyof ShadowRootEventMap
export interface GeneralEventListener<E = Event> {
  (evt: E): void
}
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 1: Omitted Window target
 *
 * @see https://vueuse.org/useEventListener
 */
export declare function useEventListener<E extends keyof WindowEventMap>(
  event: MaybeRefOrGetter<Arrayable<E>>,
  listener: MaybeRef<Arrayable<(this: Window, ev: WindowEventMap[E]) => any>>,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 2: Explicitly Window target
 *
 * @see https://vueuse.org/useEventListener
 * @param target
 * @param event
 * @param listener
 * @param options
 */
export declare function useEventListener<E extends keyof WindowEventMap>(
  target: Window,
  event: MaybeRefOrGetter<Arrayable<E>>,
  listener: MaybeRef<Arrayable<(this: Window, ev: WindowEventMap[E]) => any>>,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 3: Explicitly Document target
 *
 * @see https://vueuse.org/useEventListener
 */
export declare function useEventListener<E extends keyof DocumentEventMap>(
  target: Document,
  event: MaybeRefOrGetter<Arrayable<E>>,
  listener: MaybeRef<
    Arrayable<(this: Document, ev: DocumentEventMap[E]) => any>
  >,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 4: Explicitly ShadowRoot target
 *
 * @see https://vueuse.org/useEventListener
 */
export declare function useEventListener<E extends keyof ShadowRootEventMap>(
  target: MaybeRefOrGetter<Arrayable<ShadowRoot> | null | undefined>,
  event: MaybeRefOrGetter<Arrayable<E>>,
  listener: MaybeRef<
    Arrayable<(this: ShadowRoot, ev: ShadowRootEventMap[E]) => any>
  >,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 5: Explicitly HTMLElement target
 *
 * @see https://vueuse.org/useEventListener
 */
export declare function useEventListener<E extends keyof HTMLElementEventMap>(
  target: MaybeRefOrGetter<Arrayable<HTMLElement> | null | undefined>,
  event: MaybeRefOrGetter<Arrayable<E>>,
  listener: MaybeRef<(this: HTMLElement, ev: HTMLElementEventMap[E]) => any>,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 6: Custom event target with event type infer
 *
 * @see https://vueuse.org/useEventListener
 */
export declare function useEventListener<
  Names extends string,
  EventType = Event,
>(
  target: MaybeRefOrGetter<
    Arrayable<InferEventTarget<Names>> | null | undefined
  >,
  event: MaybeRefOrGetter<Arrayable<Names>>,
  listener: MaybeRef<Arrayable<GeneralEventListener<EventType>>>,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
/**
 * Register using addEventListener on mounted, and removeEventListener automatically on unmounted.
 *
 * Overload 7: Custom event target fallback
 *
 * @see https://vueuse.org/useEventListener
 */
export declare function useEventListener<EventType = Event>(
  target: MaybeRefOrGetter<Arrayable<EventTarget> | null | undefined>,
  event: MaybeRefOrGetter<Arrayable<string>>,
  listener: MaybeRef<Arrayable<GeneralEventListener<EventType>>>,
  options?: MaybeRefOrGetter<boolean | AddEventListenerOptions>,
): Fn
```

---

<!-- source: references/useEventSource.md -->
---
category: Network
---

# useEventSource

An [EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource) or [Server-Sent-Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) instance opens a persistent connection to an HTTP server, which sends events in text/event-stream format.

## Usage

```ts
import { useEventSource } from '@vueuse/core'

const { status, data, error, close } = useEventSource('https://event-source-url')
```

See the [Type Declarations](#type-declarations) for more options.

### Named Events

You can define named events with the second parameter

```ts
import { useEventSource } from '@vueuse/core'
// ---cut---
const { event, data } = useEventSource(
  'https://event-source-url',
  ['notice', 'update']
)
```

### immediate

Enable by default.

Establish the connection immediately when the composable is called.

### autoConnect

Enable by default.

If url is provided as a ref, when the url changes, it will automatically reconnect to the new url.

### Auto Reconnection on Errors

Reconnect on errors automatically (disabled by default).

```ts
import { useEventSource } from '@vueuse/core'
// ---cut---
const { status, data, close } = useEventSource(
  'https://event-source-url',
  [],
  {
    autoReconnect: true,
  }
)
```

Or with more controls over its behavior:

```ts
import { useEventSource } from '@vueuse/core'
// ---cut---
const { status, data, close } = useEventSource(
  'https://event-source-url',
  [],
  {
    autoReconnect: {
      retries: 3,
      delay: 1000,
      onFailed() {
        alert('Failed to connect EventSource after 3 retries')
      },
    },
  }
)
```

### Data Serialization

Apply custom transformations to incoming data using a serialization function.

```ts
import { useEventSource } from '@vueuse/core'
// ---cut---
const { data } = useEventSource(
  'https://event-source-url',
  [],
  {
    serializer: {
      read: rawData => JSON.parse(rawData),
    },
  }
)

// If server sends: '{"name":"John","age":30}'
// data.value will be: { name: 'John', age: 30 }
```

## Type Declarations

```ts
export type EventSourceStatus = "CONNECTING" | "OPEN" | "CLOSED"
export interface UseEventSourceOptions<Data> extends EventSourceInit {
  /**
   * Enabled auto reconnect
   *
   * @default false
   */
  autoReconnect?:
    | boolean
    | {
        /**
         * Maximum retry times.
         *
         * Or you can pass a predicate function (which returns true if you want to retry).
         *
         * @default -1
         */
        retries?: number | (() => boolean)
        /**
         * Delay for reconnect, in milliseconds
         *
         * @default 1000
         */
        delay?: number
        /**
         * On maximum retry times reached.
         */
        onFailed?: Fn
      }
  /**
   * Immediately open the connection when calling this composable
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Automatically connect to the websocket when URL changes
   *
   * @default true
   */
  autoConnect?: boolean
  /**
   * Custom data serialization
   */
  serializer?: {
    read: (v?: string) => Data
  }
}
export interface UseEventSourceReturn<Events extends string[], Data = any> {
  /**
   * Reference to the latest data received via the EventSource,
   * can be watched to respond to incoming messages
   */
  data: ShallowRef<Data | null>
  /**
   * The current state of the connection, can be only one of:
   * 'CONNECTING', 'OPEN' 'CLOSED'
   */
  status: ShallowRef<EventSourceStatus>
  /**
   * The latest named event
   */
  event: ShallowRef<Events[number] | null>
  /**
   * The current error
   */
  error: ShallowRef<Event | null>
  /**
   * Closes the EventSource connection gracefully.
   */
  close: EventSource["close"]
  /**
   * Reopen the EventSource connection.
   * If there the current one is active, will close it before opening a new one.
   */
  open: Fn
  /**
   * Reference to the current EventSource instance.
   */
  eventSource: Ref<EventSource | null>
  /**
   * The last event ID string, for server-sent events.
   * @see https://developer.mozilla.org/en-US/docs/Web/API/MessageEvent/lastEventId
   */
  lastEventId: ShallowRef<string | null>
}
/**
 * Reactive wrapper for EventSource.
 *
 * @see https://vueuse.org/useEventSource
 * @see https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource EventSource
 * @param url
 * @param events
 * @param options
 */
export declare function useEventSource<Events extends string[], Data = any>(
  url: MaybeRefOrGetter<string | URL | undefined>,
  events?: Events,
  options?: UseEventSourceOptions<Data>,
): UseEventSourceReturn<Events, Data>
```

---

<!-- source: references/useExtractedObservable.md -->
---
category: '@RxJS'
---

# useExtractedObservable

Use an RxJS [`Observable`](https://rxjs.dev/guide/observable) as extracted from one or more composables, return a `ref`,
and automatically unsubscribe from it when the component is unmounted.

Automatically unsubscribe on observable change, and automatically unsubscribe from it when the component is unmounted.

Supports signatures that match all overloads
of [`watch`](https://vuejs.org/guide/essentials/watchers.html#basic-example).

## Usage

<!-- TODO: import rxjs error if enable twoslash -->

```ts no-twoslash
import { useExtractedObservable } from '@vueuse/rxjs'
import ObservableSocket from 'observable-socket'
import { computed } from 'vue'
import { makeSocket, useUser } from '../some/lib/func'

// setup()
const user = useUser()
const lastMessage = useExtractedObservable(user, u => ObservableSocket.create(makeSocket(u.id)).down)
```

If you want to add custom error handling to an `Observable` that might error, you can supply an optional `onError`
configuration. Without this, RxJS will treat any error in the supplied `Observable` as an "unhandled error" and it will
be thrown in a new call stack and reported to `window.onerror` (or `process.on('error')` if you happen to be in Node).

```ts no-twoslash
import { useExtractedObservable } from '@vueuse/rxjs'
import { interval } from 'rxjs'
import { mapTo, scan, startWith, tap } from 'rxjs/operators'
import { shallowRef } from 'vue'

// setup()
const start = shallowRef(0)

const count = useExtractedObservable(
  start,
  (start) => {
    return interval(1000).pipe(
      mapTo(1),
      startWith(start),
      scan((total, next) => next + total),
      tap((n) => {
        if (n === 10)
          throw new Error('oops')
      })
    )
  },
  {
    onError: (err) => {
      console.log(err.message) // "oops"
    },
  }
)
```

You can also supply an optional `onComplete` configuration if you need to attach special behavior when the watched
observable completes.

```ts no-twoslash
import { useExtractedObservable } from '@vueuse/rxjs'
import { interval } from 'rxjs'
import { mapTo, scan, startWith, takeWhile } from 'rxjs/operators'
import { shallowRef } from 'vue'

// setup()
const start = shallowRef(0)

const count = useExtractedObservable(
  start,
  (start) => {
    return interval(1000).pipe(
      mapTo(1),
      startWith(start),
      scan((total, next) => next + total),
      takeWhile(num => num < 10)
    )
  },
  {
    onComplete: () => {
      console.log('Done!')
    },
  }
)
```

If you want, you can also pass `watch` options as the last argument:

```ts no-twoslash
import { useExtractedObservable } from '@vueuse/rxjs'
import { interval } from 'rxjs'
import { mapTo, scan, startWith, takeWhile } from 'rxjs/operators'
import { shallowRef } from 'vue'

// setup()
const start = shallowRef<number>()

const count = useExtractedObservable(
  start,
  (start) => {
    return interval(1000).pipe(
      mapTo(1),
      startWith(start),
      scan((total, next) => next + total),
      takeWhile(num => num < 10)
    )
  },
  {},
  {
    immediate: false
  }
)
```

## Options

| Option         | Type                 | Description                              |
| -------------- | -------------------- | ---------------------------------------- |
| `initialValue` | `T`                  | Value to use before the Observable emits |
| `onError`      | `(err: any) => void` | Error handler for Observable errors      |
| `onComplete`   | `() => void`         | Called when the Observable completes     |

## Return Value

Returns a readonly `ShallowRef` containing the latest value emitted by the extracted Observable.

## Type Declarations

```ts
export interface UseExtractedObservableOptions<
  E,
> extends UseObservableOptions<E> {
  onComplete?: () => void
}
export declare function useExtractedObservable<
  T extends MultiWatchSources,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  extractor: WatchExtractedObservableCallback<
    MapSources<T>,
    MapOldSources<T, Immediate>,
    E
  >,
  options?: UseExtractedObservableOptions<E>,
  watchOptions?: WatchOptions<Immediate>,
): Readonly<ShallowRef<E>>
export declare function useExtractedObservable<
  T extends Readonly<MultiWatchSources>,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  sources: T,
  extractor: WatchExtractedObservableCallback<
    MapSources<T>,
    MapOldSources<T, Immediate>,
    E
  >,
  options?: UseExtractedObservableOptions<E>,
  watchOptions?: WatchOptions<Immediate>,
): Readonly<ShallowRef<E>>
export declare function useExtractedObservable<
  T,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  sources: WatchSource<T>,
  extractor: WatchExtractedObservableCallback<
    T,
    Immediate extends true ? T | undefined : T,
    E
  >,
  options?: UseExtractedObservableOptions<E>,
  watchOptions?: WatchOptions<Immediate>,
): Readonly<ShallowRef<E>>
export declare function useExtractedObservable<
  T extends object,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  sources: T,
  extractor: WatchExtractedObservableCallback<
    T,
    Immediate extends true ? T | undefined : T,
    E
  >,
  options?: UseExtractedObservableOptions<E>,
  watchOptions?: WatchOptions<Immediate>,
): Readonly<ShallowRef<E>>
```

---

<!-- source: references/useEyeDropper.md -->
---
category: Browser
---

# useEyeDropper

Reactive [EyeDropper API](https://developer.mozilla.org/en-US/docs/Web/API/EyeDropper_API)

## Usage

```ts
import { useEyeDropper } from '@vueuse/core'

const { isSupported, open, sRGBHex } = useEyeDropper()
```

## Component Usage

```vue
<template>
  <UseEyeDropper v-slot="{ isSupported, sRGBHex, open }">
    <button :disabled="!isSupported" @click="() => open()">
      sRGBHex: {{ sRGBHex }}
    </button>
  </UseEyeDropper>
</template>
```

## Type Declarations

```ts
export interface EyeDropperOpenOptions {
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal
   */
  signal?: AbortSignal
}
export interface EyeDropper {
  new (): EyeDropper
  open: (options?: EyeDropperOpenOptions) => Promise<{
    sRGBHex: string
  }>
  [Symbol.toStringTag]: "EyeDropper"
}
export interface UseEyeDropperOptions {
  /**
   * Initial sRGBHex.
   *
   * @default ''
   */
  initialValue?: string
}
export interface UseEyeDropperReturn extends Supportable {
  sRGBHex: ShallowRef<string>
  open: (openOptions?: EyeDropperOpenOptions) => Promise<
    | {
        sRGBHex: string
      }
    | undefined
  >
}
/**
 * Reactive [EyeDropper API](https://developer.mozilla.org/en-US/docs/Web/API/EyeDropper_API)
 *
 * @see https://vueuse.org/useEyeDropper
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useEyeDropper(
  options?: UseEyeDropperOptions,
): UseEyeDropperReturn
```

---

<!-- source: references/useFavicon.md -->
---
category: Browser
---

# useFavicon

Reactive favicon

## Usage

```ts {3}
import { useFavicon } from '@vueuse/core'

const icon = useFavicon()

icon.value = 'dark.png' // change current icon
```

### Passing a source ref

You can pass a `ref` to it, changes from of the source ref will be reflected to your favicon automatically.

```ts {7}
import { useFavicon, usePreferredDark } from '@vueuse/core'
import { computed } from 'vue'

const isDark = usePreferredDark()
const favicon = computed(() => isDark.value ? 'dark.png' : 'light.png')

useFavicon(favicon)
```

When a source ref is passed, the return ref will be identical to the source ref

```ts
import { useFavicon } from '@vueuse/core'
// ---cut---
const source = shallowRef('icon.png')
const icon = useFavicon(source)

console.log(icon === source) // true
```

## Type Declarations

```ts
export interface UseFaviconOptions extends ConfigurableDocument {
  baseUrl?: string
  rel?: string
}
export type UseFaviconReturn =
  | ComputedRef<string | null | undefined>
  | Ref<string | null | undefined>
/**
 * Reactive favicon.
 *
 * @see https://vueuse.org/useFavicon
 * @param newIcon
 * @param options
 */
export declare function useFavicon(
  newIcon: ReadonlyRefOrGetter<string | null | undefined>,
  options?: UseFaviconOptions,
): ComputedRef<string | null | undefined>
export declare function useFavicon(
  newIcon?: MaybeRef<string | null | undefined>,
  options?: UseFaviconOptions,
): Ref<string | null | undefined>
```

---

<!-- source: references/useFetch.md -->
---
category: Network
---

# useFetch

Reactive [Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API) provides the ability to abort requests, intercept requests before
they are fired, automatically refetch requests when the url changes, and create your own `useFetch` with predefined options.

<CourseLink href="https://vueschool.io/lessons/vueuse-utilities-usefetch-and-reactify?friend=vueuse">Learn useFetch with this FREE video lesson from Vue School!</CourseLink>

::: tip
When using with Nuxt 3, this function will **NOT** be auto imported in favor of Nuxt's built-in [`useFetch()`](https://v3.nuxtjs.org/api/composables/use-fetch). Use explicit import if you want to use the function from VueUse.
:::

## Usage

### Basic Usage

The `useFetch` function can be used by simply providing a url. The url can be either a string or a `ref`. The `data` object will contain the result of the request, the `error` object will contain any errors, and the `isFetching` object will indicate if the request is loading.

```ts
import { useFetch } from '@vueuse/core'

const { isFetching, error, data } = useFetch(url)
```

### Asynchronous Usage

`useFetch` can also be awaited just like a normal fetch. Note that whenever a component is asynchronous, whatever component that uses
it must wrap the component in a `<Suspense>` tag. You can read more about the suspense api in the [Official Vue 3 Docs](https://vuejs.org/guide/built-ins/suspense.html)

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { isFetching, error, data } = await useFetch(url)
```

### Refetching on URL change

Using a `ref` for the url parameter will allow the `useFetch` function to automatically trigger another request when the url is changed.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const url = ref('https://my-api.com/user/1')

const { data } = useFetch(url, { refetch: true })

url.value = 'https://my-api.com/user/2' // Will trigger another request
```

### Prevent request from firing immediately

Setting the `immediate` option to false will prevent the request from firing until the `execute` function is called.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { execute } = useFetch(url, { immediate: false })

execute()
```

### Aborting a request

A request can be aborted by using the `abort` function from the `useFetch` function. The `canAbort` property indicates if the request can be aborted.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { abort, canAbort } = useFetch(url)

setTimeout(() => {
  if (canAbort.value)
    abort()
}, 100)
```

A request can also be aborted automatically by using `timeout` property. It will call `abort` function when the given timeout is reached.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { data } = useFetch(url, { timeout: 100 })
```

### Intercepting a request

The `beforeFetch` option can intercept a request before it is sent and modify the request options and url.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { data } = useFetch(url, {
  async beforeFetch({ url, options, cancel }) {
    const myToken = await getMyToken()

    if (!myToken)
      cancel()

    options.headers = {
      ...options.headers,
      Authorization: `Bearer ${myToken}`,
    }

    return {
      options,
    }
  },
})
```

The `afterFetch` option can intercept the response data before it is updated.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { data } = useFetch(url, {
  afterFetch(ctx) {
    if (ctx.data.title === 'HxH')
      ctx.data.title = 'Hunter x Hunter' // Modifies the response data

    return ctx
  },
})
```

The `onFetchError` option can intercept the response data and error before it is updated when `updateDataOnError` is set to `true`.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { data } = useFetch(url, {
  updateDataOnError: true,
  onFetchError(ctx) {
    // ctx.data can be null when 5xx response
    if (ctx.data === null)
      ctx.data = { title: 'Hunter x Hunter' } // Modifies the response data

    ctx.error = new Error('Custom Error') // Modifies the error
    return ctx
  },
})

console.log(data.value) // { title: 'Hunter x Hunter' }
```

### Setting the request method and return type

The request method and return type can be set by adding the appropriate methods to the end of `useFetch`

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
// Request will be sent with GET method and data will be parsed as JSON
const { data } = useFetch(url).get().json()

// Request will be sent with POST method and data will be parsed as text
const { data } = useFetch(url).post().text()

// Or set the method using the options

// Request will be sent with GET method and data will be parsed as blob
const { data } = useFetch(url, { method: 'GET' }, { refetch: true }).blob()
```

### Creating a Custom Instance

The `createFetch` function will return a useFetch function with whatever pre-configured options that are provided to it. This is useful for interacting with API's throughout an application that uses the same base URL or needs Authorization headers.

```ts
import { createFetch } from '@vueuse/core'
// ---cut---
const useMyFetch = createFetch({
  baseUrl: 'https://my-api.com',
  options: {
    async beforeFetch({ options }) {
      const myToken = await getMyToken()
      options.headers.Authorization = `Bearer ${myToken}`

      return { options }
    },
  },
  fetchOptions: {
    mode: 'cors',
  },
})

const { isFetching, error, data } = useMyFetch('users')
```

If you want to control the behavior of `beforeFetch`, `afterFetch`, `onFetchError` between the pre-configured instance and newly spawned instance. You can provide a `combination` option to toggle between `overwrite` or `chaining`.

```ts
import { createFetch } from '@vueuse/core'
// ---cut---
const useMyFetch = createFetch({
  baseUrl: 'https://my-api.com',
  combination: 'overwrite',
  options: {
    // beforeFetch in pre-configured instance will only run when the newly spawned instance do not pass beforeFetch
    async beforeFetch({ options }) {
      const myToken = await getMyToken()
      options.headers.Authorization = `Bearer ${myToken}`

      return { options }
    },
  },
})

// use useMyFetch beforeFetch
const { isFetching, error, data } = useMyFetch('users')

// use custom beforeFetch
const { isFetching, error, data } = useMyFetch('users', {
  async beforeFetch({ url, options, cancel }) {
    const myToken = await getMyToken()

    if (!myToken)
      cancel()

    options.headers = {
      ...options.headers,
      Authorization: `Bearer ${myToken}`,
    }

    return {
      options,
    }
  },
})
```

You can re-execute the request by calling the `execute` method in `afterFetch` or `onFetchError`. Here is a simple example of refreshing a token:

```ts
import { createFetch } from '@vueuse/core'
// ---cut---
let isRefreshing = false
const refreshSubscribers: Array<() => void> = []

const useMyFetch = createFetch({
  baseUrl: 'https://my-api.com',
  options: {
    async beforeFetch({ options }) {
      const myToken = await getMyToken()
      options.headers.Authorization = `Bearer ${myToken}`

      return { options }
    },
    afterFetch({ data, response, context, execute }) {
      if (needRefreshToken) {
        if (!isRefreshing) {
          isRefreshing = true
          refreshToken().then((newToken) => {
            if (newToken.value) {
              isRefreshing = false
              setMyToken(newToken.value)
              onRefreshed()
            }
            else {
              refreshSubscribers.length = 0
              // handle refresh token error
            }
          })
        }

        return new Promise((resolve) => {
          addRefreshSubscriber(() => {
            execute().then((response) => {
              resolve({ data, response })
            })
          })
        })
      }

      return { data, response }
    },
    // or use onFetchError with updateDataOnError
    updateDataOnError: true,
    onFetchError({ error, data, response, context, execute }) {
      // same as afterFetch
      return { error, data }
    },
  },
  fetchOptions: {
    mode: 'cors',
  },
})

async function refreshToken() {
  const { data, execute } = useFetch<string>('refresh-token', {
    immediate: false,
  })

  await execute()
  return data
}

function onRefreshed() {
  refreshSubscribers.forEach(callback => callback())
  refreshSubscribers.length = 0
}

function addRefreshSubscriber(callback: () => void) {
  refreshSubscribers.push(callback)
}

const { isFetching, error, data } = useMyFetch('users')
```

### Events

The `onFetchResponse` and `onFetchError` will fire on fetch request responses and errors respectively.

```ts
import { useFetch } from '@vueuse/core'
// ---cut---
const { onFetchResponse, onFetchError } = useFetch(url)

onFetchResponse((response) => {
  console.log(response.status)
})

onFetchError((error) => {
  console.error(error.message)
})
```

## Type Declarations

```ts
export interface UseFetchReturn<T> {
  /**
   * Indicates if the fetch request has finished
   */
  isFinished: Readonly<ShallowRef<boolean>>
  /**
   * The statusCode of the HTTP fetch response
   */
  statusCode: ShallowRef<number | null>
  /**
   * The raw response of the fetch response
   */
  response: ShallowRef<Response | null>
  /**
   * Any fetch errors that may have occurred
   */
  error: ShallowRef<any>
  /**
   * The fetch response body on success, may either be JSON or text
   */
  data: ShallowRef<T | null>
  /**
   * Indicates if the request is currently being fetched.
   */
  isFetching: Readonly<ShallowRef<boolean>>
  /**
   * Indicates if the fetch request is able to be aborted
   */
  canAbort: ComputedRef<boolean>
  /**
   * Indicates if the fetch request was aborted
   */
  aborted: ShallowRef<boolean>
  /**
   * Abort the fetch request
   */
  abort: (reason?: any) => void
  /**
   * Manually call the fetch
   * (default not throwing error)
   */
  execute: (throwOnFailed?: boolean) => Promise<any>
  /**
   * Fires after the fetch request has finished
   */
  onFetchResponse: EventHookOn<Response>
  /**
   * Fires after a fetch request error
   */
  onFetchError: EventHookOn
  /**
   * Fires after a fetch has completed
   */
  onFetchFinally: EventHookOn
  get: () => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  post: (
    payload?: MaybeRefOrGetter<unknown>,
    type?: string,
  ) => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  put: (
    payload?: MaybeRefOrGetter<unknown>,
    type?: string,
  ) => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  delete: (
    payload?: MaybeRefOrGetter<unknown>,
    type?: string,
  ) => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  patch: (
    payload?: MaybeRefOrGetter<unknown>,
    type?: string,
  ) => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  head: (
    payload?: MaybeRefOrGetter<unknown>,
    type?: string,
  ) => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  options: (
    payload?: MaybeRefOrGetter<unknown>,
    type?: string,
  ) => UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
  json: <JSON = any>() => UseFetchReturn<JSON> &
    PromiseLike<UseFetchReturn<JSON>>
  text: () => UseFetchReturn<string> & PromiseLike<UseFetchReturn<string>>
  blob: () => UseFetchReturn<Blob> & PromiseLike<UseFetchReturn<Blob>>
  arrayBuffer: () => UseFetchReturn<ArrayBuffer> &
    PromiseLike<UseFetchReturn<ArrayBuffer>>
  formData: () => UseFetchReturn<FormData> &
    PromiseLike<UseFetchReturn<FormData>>
}
type Combination = "overwrite" | "chain"
export interface BeforeFetchContext {
  /**
   * The computed url of the current request
   */
  url: string
  /**
   * The request options of the current request
   */
  options: RequestInit
  /**
   * Cancels the current request
   */
  cancel: Fn
}
export interface AfterFetchContext<T = any> {
  response: Response
  data: T | null
  context: BeforeFetchContext
  execute: (throwOnFailed?: boolean) => Promise<any>
}
export interface OnFetchErrorContext<T = any, E = any> {
  error: E
  data: T | null
  response: Response | null
  context: BeforeFetchContext
  execute: (throwOnFailed?: boolean) => Promise<any>
}
export interface UseFetchOptions {
  /**
   * Fetch function
   */
  fetch?: typeof window.fetch
  /**
   * Will automatically run fetch when `useFetch` is used
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Will automatically refetch when:
   * - the URL is changed if the URL is a ref
   * - the payload is changed if the payload is a ref
   *
   * @default false
   */
  refetch?: MaybeRefOrGetter<boolean>
  /**
   * Initial data before the request finished
   *
   * @default null
   */
  initialData?: any
  /**
   * Timeout for abort request after number of millisecond
   * `0` means use browser default
   *
   * @default 0
   */
  timeout?: number
  /**
   * Allow update the `data` ref when fetch error whenever provided, or mutated in the `onFetchError` callback
   *
   * @default false
   */
  updateDataOnError?: boolean
  /**
   * Will run immediately before the fetch request is dispatched
   */
  beforeFetch?: (
    ctx: BeforeFetchContext,
  ) =>
    | Promise<Partial<BeforeFetchContext> | void>
    | Partial<BeforeFetchContext>
    | void
  /**
   * Will run immediately after the fetch request is returned.
   * Runs after any 2xx response
   */
  afterFetch?: (
    ctx: AfterFetchContext,
  ) => Promise<Partial<AfterFetchContext>> | Partial<AfterFetchContext>
  /**
   * Will run immediately after the fetch request is returned.
   * Runs after any 4xx and 5xx response
   */
  onFetchError?: (
    ctx: OnFetchErrorContext,
  ) => Promise<Partial<OnFetchErrorContext>> | Partial<OnFetchErrorContext>
}
export interface CreateFetchOptions {
  /**
   * The base URL that will be prefixed to all urls unless urls are absolute
   */
  baseUrl?: MaybeRefOrGetter<string>
  /**
   * Determine the inherit behavior for beforeFetch, afterFetch, onFetchError
   * @default 'chain'
   */
  combination?: Combination
  /**
   * Default Options for the useFetch function
   */
  options?: UseFetchOptions
  /**
   * Options for the fetch request
   */
  fetchOptions?: RequestInit
}
export declare function createFetch(
  config?: CreateFetchOptions,
): typeof useFetch
export declare function useFetch<T>(
  url: MaybeRefOrGetter<string>,
): UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
export declare function useFetch<T>(
  url: MaybeRefOrGetter<string>,
  useFetchOptions: UseFetchOptions,
): UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
export declare function useFetch<T>(
  url: MaybeRefOrGetter<string>,
  options: RequestInit,
  useFetchOptions?: UseFetchOptions,
): UseFetchReturn<T> & PromiseLike<UseFetchReturn<T>>
```

---

<!-- source: references/useFileDialog.md -->
---
category: Browser
---

# useFileDialog

Open file dialog with ease.

## Usage

```vue
<script setup lang="ts">
import { useFileDialog } from '@vueuse/core'

const { files, open, reset, onCancel, onChange } = useFileDialog({
  accept: 'image/*', // Set to accept only image files
  directory: true, // Select directories instead of files if set true
})

onChange((files) => {
  /** do something with files */
})

onCancel(() => {
  /** do something on cancel */
})
</script>

<template>
  <button type="button" @click="open">
    Choose file
  </button>
</template>
```

## Type Declarations

```ts
export interface UseFileDialogOptions extends ConfigurableDocument {
  /**
   * @default true
   */
  multiple?: MaybeRef<boolean>
  /**
   * @default '*'
   */
  accept?: MaybeRef<string>
  /**
   * Select the input source for the capture file.
   * @see [HTMLInputElement Capture](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/capture)
   */
  capture?: MaybeRef<string>
  /**
   * Reset when open file dialog.
   * @default false
   */
  reset?: MaybeRef<boolean>
  /**
   * Select directories instead of files.
   * @see [HTMLInputElement webkitdirectory](https://developer.mozilla.org/en-US/docs/Web/API/HTMLInputElement/webkitdirectory)
   * @default false
   */
  directory?: MaybeRef<boolean>
  /**
   * Initial files to set.
   * @default null
   */
  initialFiles?: Array<File> | FileList
  /**
   * The input element to use for file dialog.
   * @default document.createElement('input')
   */
  input?: MaybeElementRef<HTMLInputElement>
}
export interface UseFileDialogReturn {
  files: Ref<FileList | null>
  open: (localOptions?: Partial<UseFileDialogOptions>) => void
  reset: () => void
  onChange: EventHookOn<FileList | null>
  onCancel: EventHookOn
}
/**
 * Open file dialog with ease.
 *
 * @see https://vueuse.org/useFileDialog
 * @param options
 */
export declare function useFileDialog(
  options?: UseFileDialogOptions,
): UseFileDialogReturn
```

---

<!-- source: references/useFileSystemAccess.md -->
---
category: Browser
---

# useFileSystemAccess

Create and read and write local files with [FileSystemAccessAPI](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API)

## Usage

```ts
import { useFileSystemAccess } from '@vueuse/core'

const {
  isSupported,
  data,
  file,
  fileName,
  fileMIME,
  fileSize,
  fileLastModified,
  create,
  open,
  save,
  saveAs,
  updateData
} = useFileSystemAccess()
```

## Type Declarations

```ts
/**
 * window.showOpenFilePicker parameters
 * @see https://developer.mozilla.org/en-US/docs/Web/API/window/showOpenFilePicker#parameters
 */
export interface FileSystemAccessShowOpenFileOptions {
  multiple?: boolean
  types?: Array<{
    description?: string
    accept: Record<string, string[]>
  }>
  excludeAcceptAllOption?: boolean
}
/**
 * window.showSaveFilePicker parameters
 * @see https://developer.mozilla.org/en-US/docs/Web/API/window/showSaveFilePicker#parameters
 */
export interface FileSystemAccessShowSaveFileOptions {
  suggestedName?: string
  types?: Array<{
    description?: string
    accept: Record<string, string[]>
  }>
  excludeAcceptAllOption?: boolean
}
/**
 * FileHandle
 * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemFileHandle
 */
export interface FileSystemFileHandle {
  getFile: () => Promise<File>
  createWritable: () => FileSystemWritableFileStream
}
/**
 * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemWritableFileStream
 */
interface FileSystemWritableFileStream extends WritableStream {
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemWritableFileStream/write
   */
  write: FileSystemWritableFileStreamWrite
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemWritableFileStream/seek
   */
  seek: (position: number) => Promise<void>
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemWritableFileStream/truncate
   */
  truncate: (size: number) => Promise<void>
}
/**
 * FileStream.write
 * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemWritableFileStream/write
 */
interface FileSystemWritableFileStreamWrite {
  (data: string | BufferSource | Blob): Promise<void>
  (options: {
    type: "write"
    position: number
    data: string | BufferSource | Blob
  }): Promise<void>
  (options: { type: "seek"; position: number }): Promise<void>
  (options: { type: "truncate"; size: number }): Promise<void>
}
/**
 * FileStream.write
 * @see https://developer.mozilla.org/en-US/docs/Web/API/FileSystemWritableFileStream/write
 */
export type FileSystemAccessWindow = Window & {
  showSaveFilePicker: (
    options: FileSystemAccessShowSaveFileOptions,
  ) => Promise<FileSystemFileHandle>
  showOpenFilePicker: (
    options: FileSystemAccessShowOpenFileOptions,
  ) => Promise<FileSystemFileHandle[]>
}
export type UseFileSystemAccessCommonOptions = Pick<
  FileSystemAccessShowOpenFileOptions,
  "types" | "excludeAcceptAllOption"
>
export type UseFileSystemAccessShowSaveFileOptions = Pick<
  FileSystemAccessShowSaveFileOptions,
  "suggestedName"
>
export type UseFileSystemAccessOptions = ConfigurableWindow &
  UseFileSystemAccessCommonOptions & {
    /**
     * file data type
     */
    dataType?: MaybeRefOrGetter<"Text" | "ArrayBuffer" | "Blob">
  }
/**
 * Create and read and write local files.
 * @see https://vueuse.org/useFileSystemAccess
 */
export declare function useFileSystemAccess(): UseFileSystemAccessReturn<
  string | ArrayBuffer | Blob
>
export declare function useFileSystemAccess(
  options: UseFileSystemAccessOptions & {
    dataType: "Text"
  },
): UseFileSystemAccessReturn<string>
export declare function useFileSystemAccess(
  options: UseFileSystemAccessOptions & {
    dataType: "ArrayBuffer"
  },
): UseFileSystemAccessReturn<ArrayBuffer>
export declare function useFileSystemAccess(
  options: UseFileSystemAccessOptions & {
    dataType: "Blob"
  },
): UseFileSystemAccessReturn<Blob>
export declare function useFileSystemAccess(
  options: UseFileSystemAccessOptions,
): UseFileSystemAccessReturn<string | ArrayBuffer | Blob>
export interface UseFileSystemAccessReturn<T = string> extends Supportable {
  data: ShallowRef<T | undefined>
  file: ShallowRef<File | undefined>
  fileName: ComputedRef<string>
  fileMIME: ComputedRef<string>
  fileSize: ComputedRef<number>
  fileLastModified: ComputedRef<number>
  open: (_options?: UseFileSystemAccessCommonOptions) => Awaitable<void>
  create: (_options?: UseFileSystemAccessShowSaveFileOptions) => Awaitable<void>
  save: (_options?: UseFileSystemAccessShowSaveFileOptions) => Awaitable<void>
  saveAs: (_options?: UseFileSystemAccessShowSaveFileOptions) => Awaitable<void>
  updateData: () => Awaitable<void>
}
```

---

<!-- source: references/useFirestore.md -->
---
category: '@Firebase'
---

# useFirestore

Reactive [Firestore](https://firebase.google.com/docs/firestore) binding. Making it straightforward to **always keep your local data in sync** with remotes databases.

## Usage

```ts {9,12,17,22}
import { useFirestore } from '@vueuse/firebase/useFirestore'
import { initializeApp } from 'firebase/app'
import { collection, doc, getFirestore, limit, orderBy, query } from 'firebase/firestore'
import { computed, shallowRef } from 'vue'

const app = initializeApp({ projectId: 'MY PROJECT ID' })
const db = getFirestore(app)

const todos = useFirestore(collection(db, 'todos'))

// or for doc reference
const user = useFirestore(doc(db, 'users', 'my-user-id'))

// you can also use ref value for reactive query
const postsLimit = shallowRef(10)
const postsQuery = computed(() => query(collection(db, 'posts'), orderBy('createdAt', 'desc'), limit(postsLimit.value)))
const posts = useFirestore(postsQuery)

// you can use the boolean value to tell a query when it is ready to run
// when it gets falsy value, return the initial value
const userId = shallowRef('')
const userQuery = computed(() => userId.value && doc(db, 'users', userId.value))
const userData = useFirestore(userQuery, null)
```

### Return Value

- For **Document Reference**: Returns `Ref<T | null>` (single document with `id` property)
- For **Query**: Returns `Ref<T[]>` (array of documents, each with `id` property)

The document `id` is automatically added as a read-only property to each returned document.

### Options

| Option         | Type                   | Default         | Description                                                                |
| -------------- | ---------------------- | --------------- | -------------------------------------------------------------------------- |
| `errorHandler` | `(err: Error) => void` | `console.error` | Custom error handler                                                       |
| `autoDispose`  | `boolean \| number`    | `true`          | Auto-unsubscribe on scope dispose. Pass a number for delayed dispose (ms). |

### Error Handling

```ts
const todos = useFirestore(collection(db, 'todos'), [], {
  errorHandler: (err) => {
    console.error('Firestore error:', err)
    // Handle error (e.g., show notification)
  },
})
```

## Share across instances

You can reuse the db reference by passing `autoDispose: false`. You can also set an amount of milliseconds before auto disposing the db reference.

Note : Getting a not disposed db reference again don't cost a Firestore read.

```ts
import { useFirestore } from '@vueuse/firebase/useFirestore'
import { collection } from 'firebase/firestore'
// ---cut---
const todos = useFirestore(collection(db, 'todos'), undefined, { autoDispose: false })
```

or use `createGlobalState` from the core package

```ts twoslash include store
// @filename: store.ts
// ---cut---
// store.ts
import { createGlobalState } from '@vueuse/core'
import { useFirestore } from '@vueuse/firebase/useFirestore'

export const useTodos = createGlobalState(
  () => useFirestore(collection(db, 'todos')),
)
```

```vue
<!-- app.vue -->
<script setup lang="ts">
// @include: store
// ---cut---
import { useTodos } from './store'

const todos = useTodos()
</script>
```

## Type Declarations

```ts
export interface UseFirestoreOptions {
  errorHandler?: (err: Error) => void
  autoDispose?: boolean | number
}
export type FirebaseDocRef<T> = Query<T> | DocumentReference<T>
type Falsy = false | 0 | "" | null | undefined
export declare function useFirestore<T extends DocumentData>(
  maybeDocRef: MaybeRef<DocumentReference<T> | Falsy>,
  initialValue: T,
  options?: UseFirestoreOptions,
): Ref<T | null>
export declare function useFirestore<T extends DocumentData>(
  maybeDocRef: MaybeRef<Query<T> | Falsy>,
  initialValue: T[],
  options?: UseFirestoreOptions,
): Ref<T[]>
export declare function useFirestore<T extends DocumentData>(
  maybeDocRef: MaybeRef<DocumentReference<T> | Falsy>,
  initialValue?: T | undefined | null,
  options?: UseFirestoreOptions,
): Ref<T | undefined | null>
export declare function useFirestore<T extends DocumentData>(
  maybeDocRef: MaybeRef<Query<T> | Falsy>,
  initialValue?: T[],
  options?: UseFirestoreOptions,
): Ref<T[] | undefined>
```

---

<!-- source: references/useFloor.md -->
---
category: '@Math'
---

# useFloor

Reactive `Math.floor`.

## Usage

```ts
import { useFloor } from '@vueuse/math'

const value = ref(45.95)
const result = useFloor(value) // 45
```

## Type Declarations

```ts
/**
 * Reactive `Math.floor`
 *
 * @see https://vueuse.org/useFloor
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useFloor(
  value: MaybeRefOrGetter<number>,
): ComputedRef<number>
```

---

<!-- source: references/useFocus.md -->
---
category: Sensors
---

# useFocus

Reactive utility to track or set the focus state of a DOM element. State changes to reflect whether the target element is the focused element. Setting reactive value from the outside will trigger `focus` and `blur` events for `true` and `false` values respectively.

## Basic Usage

```ts
import { useFocus } from '@vueuse/core'

const target = shallowRef()
const { focused } = useFocus(target)

watch(focused, (focused) => {
  if (focused)
    console.log('input element has been focused')
  else console.log('input element has lost focus')
})
```

## Setting initial focus

To focus the element on its first render one can provide the `initialValue` option as `true`. This will trigger a `focus` event on the target element.

```ts
import { useFocus } from '@vueuse/core'

const target = shallowRef()
const { focused } = useFocus(target, { initialValue: true })
```

## Change focus state

Changes of the `focused` reactive ref will automatically trigger `focus` and `blur` events for `true` and `false` values respectively. You can utilize this behavior to focus the target element as a result of another action (e.g. when a button click as shown below).

```vue
<script setup lang="ts">
import { useFocus } from '@vueuse/core'
import { shallowRef } from 'vue'

const input = shallowRef()
const { focused } = useFocus(input)
</script>

<template>
  <div>
    <button type="button" @click="focused = true">
      Click me to focus input below
    </button>
    <input ref="input" type="text">
  </div>
</template>
```

## Type Declarations

```ts
export interface UseFocusOptions extends ConfigurableWindow {
  /**
   * Initial value. If set true, then focus will be set on the target
   *
   * @default false
   */
  initialValue?: boolean
  /**
   * Replicate the :focus-visible behavior of CSS
   *
   * @default false
   */
  focusVisible?: boolean
  /**
   * Prevent scrolling to the element when it is focused.
   *
   * @default false
   */
  preventScroll?: boolean
}
export interface UseFocusReturn {
  /**
   * If read as true, then the element has focus. If read as false, then the element does not have focus
   * If set to true, then the element will be focused. If set to false, the element will be blurred.
   */
  focused: WritableComputedRef<boolean>
}
/**
 * Track or set the focus state of a DOM element.
 *
 * @see https://vueuse.org/useFocus
 * @param target The target element for the focus and blur events.
 * @param options
 */
export declare function useFocus(
  target: MaybeElementRef,
  options?: UseFocusOptions,
): UseFocusReturn
```

---

<!-- source: references/useFocusTrap.md -->
---
category: '@Integrations'
---

# useFocusTrap

Reactive wrapper for [`focus-trap`](https://github.com/focus-trap/focus-trap).

For more information on what options can be passed, see [`createOptions`](https://github.com/focus-trap/focus-trap#createoptions) in the `focus-trap` documentation.

## Install

```bash
npm i focus-trap@^7
```

## Usage

**Basic Usage**

```vue
<script setup lang="ts">
import { useFocusTrap } from '@vueuse/integrations/useFocusTrap'
import { useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const { hasFocus, activate, deactivate } = useFocusTrap(target)
</script>

<template>
  <div>
    <button @click="activate()">
      Activate
    </button>
    <div ref="target">
      <span>Has Focus: {{ hasFocus }}</span>
      <input type="text">
      <button @click="deactivate()">
        Deactivate
      </button>
    </div>
  </div>
</template>
```

**Multiple Refs**

```vue
<script setup lang="ts">
import { useFocusTrap } from '@vueuse/integrations/useFocusTrap'
import { useTemplateRef } from 'vue'

const targetOne = useTemplateRef('targetOne')
const targetTwo = useTemplateRef('targetTwo')
const { hasFocus, activate, deactivate } = useFocusTrap([targetOne, targetTwo])
</script>

<template>
  <div>
    <button @click="activate()">
      Activate
    </button>
    <div ref="targetOne">
      <span>Has Focus: {{ hasFocus }}</span>
      <input type="text">
    </div>
    ...
    <div ref="targetTow">
      <p>Another target here</p>
      <input type="text">
      <button @click="deactivate()">
        Deactivate
      </button>
    </div>
  </div>
</template>
```

**Dynamic Focus Target**

```vue
<script setup lang="ts">
import { useFocusTrap } from '@vueuse/integrations/useFocusTrap'
import { computed, shallowRef, useTemplateRef } from 'vue'

const left = useTemplateRef('left')
const right = useTemplateRef('right')
const currentRef = shallowRef<'left' | 'right'>('left')

const target = computed(() =>
  currentRef.value === 'left'
    ? left
    : currentRef.value === 'right'
      ? right
      : null,
)

const { activate } = useFocusTrap(target)
</script>

<template>
  <div>
    <div ref="left" class="left">
      ...
    </div>
    <div ref="right" class="right">
      ...
    </div>
  </div>
</template>
```

**Automatically Focus**

```vue
<script setup lang="ts">
import { useFocusTrap } from '@vueuse/integrations/useFocusTrap'
import { useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const { hasFocus, activate, deactivate } = useFocusTrap(target, { immediate: true })
</script>

<template>
  <div>
    <div ref="target">
      ...
    </div>
  </div>
</template>
```

**Conditional Rendering**

This function can't properly activate focus on elements with conditional rendering using `v-if`. This is because they do not exist in the DOM at the time of the focus activation. To solve this you need to activate on the next tick.

```vue
<script setup lang="ts">
import { useFocusTrap } from '@vueuse/integrations/useFocusTrap'
import { nextTick, useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const { activate, deactivate } = useFocusTrap(target, { immediate: true })

const show = ref(false)

async function reveal() {
  show.value = true

  await nextTick()
  activate()
}
</script>

<template>
  <div>
    <div v-if="show" ref="target">
      ...
    </div>

    <button @click="reveal">
      Reveal and Focus
    </button>
  </div>
</template>
```

## Using Component

With the `UseFocusTrap` component, Focus Trap will be activated automatically on mounting this component and deactivated on unmount.

```vue
<script setup lang="ts">
import { UseFocusTrap } from '@vueuse/integrations/useFocusTrap/component'
import { shallowRef } from 'vue'

const show = shallowRef(false)
</script>

<template>
  <UseFocusTrap v-if="show" :options="{ immediate: true }">
    <div class="modal">
      ...
    </div>
  </UseFocusTrap>
</template>
```

## Type Declarations

```ts
export interface UseFocusTrapOptions extends Options {
  /**
   * Immediately activate the trap
   */
  immediate?: boolean
}
export interface UseFocusTrapReturn {
  /**
   * Indicates if the focus trap is currently active
   */
  hasFocus: ShallowRef<boolean>
  /**
   * Indicates if the focus trap is currently paused
   */
  isPaused: ShallowRef<boolean>
  /**
   * Activate the focus trap
   *
   * @see https://github.com/focus-trap/focus-trap#trapactivateactivateoptions
   * @param opts Activate focus trap options
   */
  activate: (opts?: ActivateOptions) => void
  /**
   * Deactivate the focus trap
   *
   * @see https://github.com/focus-trap/focus-trap#trapdeactivatedeactivateoptions
   * @param opts Deactivate focus trap options
   */
  deactivate: (opts?: DeactivateOptions) => void
  /**
   * Pause the focus trap
   *
   * @see https://github.com/focus-trap/focus-trap#trappause
   */
  pause: Fn
  /**
   * Unpauses the focus trap
   *
   * @see https://github.com/focus-trap/focus-trap#trapunpause
   */
  unpause: Fn
}
/**
 * Reactive focus-trap
 *
 * @see https://vueuse.org/useFocusTrap
 */
export declare function useFocusTrap(
  target: MaybeRefOrGetter<
    Arrayable<MaybeRefOrGetter<string> | MaybeComputedElementRef>
  >,
  options?: UseFocusTrapOptions,
): UseFocusTrapReturn
```

---

<!-- source: references/useFocusWithin.md -->
---
category: Sensors
---

# useFocusWithin

Reactive utility to track if an element or one of its decendants has focus. It is meant to match the behavior of the `:focus-within` CSS pseudo-class. A common use case would be on a form element to see if any of its inputs currently have focus.

## Basic Usage

```vue
<script setup lang="ts">
import { useFocusWithin } from '@vueuse/core'
import { ref, watch } from 'vue'

const target = ref()
const { focused } = useFocusWithin(target)

watch(focused, (focused) => {
  if (focused)
    console.log('Target contains the focused element')
  else
    console.log('Target does NOT contain the focused element')
})
</script>

<template>
  <form ref="target">
    <input type="text" placeholder="First Name">
    <input type="text" placeholder="Last Name">
    <input type="text" placeholder="Email">
    <input type="text" placeholder="Password">
  </form>
</template>
```

## Type Declarations

```ts
export interface UseFocusWithinReturn {
  /**
   * True if the element or any of its descendants are focused
   */
  focused: ComputedRef<boolean>
}
/**
 * Track if focus is contained within the target element
 *
 * @see https://vueuse.org/useFocusWithin
 * @param target The target element to track
 * @param options Focus within options
 */
export declare function useFocusWithin(
  target: MaybeElementRef,
  options?: ConfigurableWindow,
): UseFocusWithinReturn
```

---

<!-- source: references/useFps.md -->
---
category: Sensors
---

# useFps

Reactive FPS (frames per second).

## Usage

```ts
import { useFps } from '@vueuse/core'

const fps = useFps()
```

## Type Declarations

```ts
export interface UseFpsOptions {
  /**
   * Calculate the FPS on every x frames.
   * @default 10
   */
  every?: number
}
export declare function useFps(options?: UseFpsOptions): ShallowRef<number>
```

---

<!-- source: references/useFullscreen.md -->
---
category: Browser
---

# useFullscreen

Reactive [Fullscreen API](https://developer.mozilla.org/en-US/docs/Web/API/Fullscreen_API). It adds methods to present a specific Element (and its descendants) in full-screen mode, and to exit full-screen mode once it is no longer needed. This makes it possible to present desired content—such as an online game—using the user's entire screen, removing all browser user interface elements and other applications from the screen until full-screen mode is shut off.

## Usage

```ts
import { useFullscreen } from '@vueuse/core'

const { isFullscreen, enter, exit, toggle } = useFullscreen()
```

Fullscreen specified element. Some platforms (like iOS's Safari) only allow fullscreen on video elements.

```vue
<script setup lang="ts">
import { useFullscreen } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { isFullscreen, enter, exit, toggle } = useFullscreen(el)
</script>

<template>
  <video ref="el" />
</template>
```

## Component Usage

```vue
<template>
  <UseFullscreen v-slot="{ toggle }">
    <video />
    <button @click="toggle">
      Go Fullscreen
    </button>
  </UseFullscreen>
</template>
```

## Type Declarations

```ts
export interface UseFullscreenOptions extends ConfigurableDocument {
  /**
   * Automatically exit fullscreen when component is unmounted
   *
   * @default false
   */
  autoExit?: boolean
}
export interface UseFullscreenReturn extends Supportable {
  isFullscreen: ShallowRef<boolean>
  enter: () => Promise<void>
  exit: () => Promise<void>
  toggle: () => Promise<void>
}
/**
 * Reactive Fullscreen API.
 *
 * @see https://vueuse.org/useFullscreen
 * @param target
 * @param options
 */
export declare function useFullscreen(
  target?: MaybeElementRef,
  options?: UseFullscreenOptions,
): UseFullscreenReturn
```

---

<!-- source: references/useFuse.md -->
---
category: '@Integrations'
---

# useFuse

Easily implement fuzzy search using a composable with [Fuse.js](https://github.com/krisk/fuse).

From the Fuse.js website:

> What is fuzzy searching?
>
> Generally speaking, fuzzy searching (more formally known as approximate string matching) is the technique of finding strings that are approximately equal to a given pattern (rather than exactly).

## Install Fuse.js as a peer dependency

### NPM

```bash
npm install fuse.js@^7
```

### Yarn

```bash
yarn add fuse.js
```

## Usage

```ts
import { useFuse } from '@vueuse/integrations/useFuse'
import { shallowRef } from 'vue'

const data = [
  'John Smith',
  'John Doe',
  'Jane Doe',
  'Phillip Green',
  'Peter Brown',
]

const input = shallowRef('Jhon D')

const { results } = useFuse(input, data)

/*
 * Results:
 *
 * { "item": "John Doe", "index": 1 }
 * { "item": "John Smith", "index": 0 }
 * { "item": "Jane Doe", "index": 2 }
 *
 */
```

## Type Declarations

```ts
export type FuseOptions<T> = IFuseOptions<T>
export interface UseFuseOptions<T> {
  fuseOptions?: FuseOptions<T>
  resultLimit?: number
  matchAllWhenSearchEmpty?: boolean
}
export interface UseFuseReturn<DataItem> {
  fuse: Ref<Fuse<DataItem>>
  results: ComputedRef<FuseResult<DataItem>[]>
}
export declare function useFuse<DataItem>(
  search: MaybeRefOrGetter<string>,
  data: MaybeRefOrGetter<DataItem[]>,
  options?: MaybeRefOrGetter<UseFuseOptions<DataItem>>,
): UseFuseReturn<DataItem>
```

---

<!-- source: references/useGamepad.md -->
---
category: Browser
---

# useGamepad

Provides reactive bindings for the [Gamepad API](https://developer.mozilla.org/en-US/docs/Web/API/Gamepad_API).

## Usage

> Due to how the Gamepad API works, you must interact with the page using the gamepad before it will be detected.

```vue
<script setup lang="ts">
import { useGamepad } from '@vueuse/core'
import { computed } from 'vue'

const { isSupported, gamepads } = useGamepad()
const gamepad = computed(() => gamepads.value.find(g => g.mapping === 'standard'))
</script>

<template>
  <span>
    {{ gamepad.id }}
  </span>
</template>
```

### Gamepad Updates

Currently the Gamepad API does not have event support to update the state of the gamepad. To update the gamepad state, `requestAnimationFrame` is used to poll for gamepad changes. You can control this polling by using the `pause` and `resume` functions provided by `useGamepad`

```ts
import { useGamepad } from '@vueuse/core'

const { pause, resume, gamepads } = useGamepad()

pause()

// gamepads object will not update

resume()

// gamepads object will update on user input
```

### Gamepad Connect & Disconnect Events

The `onConnected` and `onDisconnected` events will trigger when a gamepad is connected or disconnected.

```ts
import { useGamepad } from '@vueuse/core'
// ---cut---
const { gamepads, onConnected, onDisconnected } = useGamepad()

onConnected((index) => {
  console.log(`${gamepads.value[index].id} connected`)
})

onDisconnected((index) => {
  console.log(`${index} disconnected`)
})
```

### Vibration

> The Gamepad Haptics API is sparse, so check the [compatibility table](https://developer.mozilla.org/en-US/docs/Web/API/GamepadHapticActuator#browser_compatibility) before using.

<!-- eslint-disable import/first -->

```ts
import { useGamepad } from '@vueuse/core'

const { gamepads, onConnected, onDisconnected } = useGamepad()
const gamepad = gamepads.value[0]!
// ---cut---
import { computed } from 'vue'

const supportsVibration = computed(() => gamepad.hapticActuators.length > 0)
function vibrate() {
  if (supportsVibration.value) {
    const actuator = gamepad.hapticActuators[0]
    actuator.playEffect('dual-rumble', {
      startDelay: 0,
      duration: 1000,
      weakMagnitude: 1,
      strongMagnitude: 1,
    })
  }
}
```

### Mappings

To make the Gamepad API easier to use, we provide mappings to map a controller to a controllers button layout.

#### Xbox360 Controller

```vue
<script setup>
import { mapGamepadToXbox360Controller } from '@vueuse/core'

const controller = mapGamepadToXbox360Controller(gamepad)
</script>

<template>
  <span>{{ controller.buttons.a.pressed }}</span>
  <span>{{ controller.buttons.b.pressed }}</span>
  <span>{{ controller.buttons.x.pressed }}</span>
  <span>{{ controller.buttons.y.pressed }}</span>
</template>
```

Currently there are only mappings for the Xbox 360 controller. If you have controller you want to add mappings for, feel free to open a PR for more controller mappings!

### SSR Compatibility

This component is designed to be used in the client side. In some cases, SSR might cause some hydration mismatches.

If you are using Nuxt, you can simply rename your component file with the `.client.vue` suffix (e.g., `GamepadComponent.client.vue`) which will automatically make it render only on the client side, avoiding hydration mismatches.

In other frameworks or plain Vue, you can wrap your usage component with a `<ClientOnly>` component to ensure it is only rendered on the client side.

## Type Declarations

```ts
export interface UseGamepadOptions
  extends ConfigurableWindow, ConfigurableNavigator {}
export interface UseGamepadReturn extends Supportable, Pausable {
  onConnected: EventHookOn<number>
  onDisconnected: EventHookOn<number>
  gamepads: Ref<Gamepad[]>
}
/**
 * Maps a standard standard gamepad to an Xbox 360 Controller.
 */
export declare function mapGamepadToXbox360Controller(
  gamepad: Ref<Gamepad | undefined>,
): ComputedRef<{
  buttons: {
    a: GamepadButton
    b: GamepadButton
    x: GamepadButton
    y: GamepadButton
  }
  bumper: {
    left: GamepadButton
    right: GamepadButton
  }
  triggers: {
    left: GamepadButton
    right: GamepadButton
  }
  stick: {
    left: {
      horizontal: number
      vertical: number
      button: GamepadButton
    }
    right: {
      horizontal: number
      vertical: number
      button: GamepadButton
    }
  }
  dpad: {
    up: GamepadButton
    down: GamepadButton
    left: GamepadButton
    right: GamepadButton
  }
  back: GamepadButton
  start: GamepadButton
} | null>
export declare function useGamepad(
  options?: UseGamepadOptions,
): UseGamepadReturn
```

---

<!-- source: references/useGeolocation.md -->
---
category: Sensors
---

# useGeolocation

Reactive [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API). It allows the user to provide their location to web applications if they so desire. For privacy reasons, the user is asked for permission to report location information.

## Usage

```ts
import { useGeolocation } from '@vueuse/core'

const { coords, locatedAt, error, resume, pause } = useGeolocation()
```

| State     | Type                                                                          | Description                                                              |
| --------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| coords    | [`Coordinates`](https://developer.mozilla.org/en-US/docs/Web/API/Coordinates) | information about the position retrieved like the latitude and longitude |
| locatedAt | `Date`                                                                        | The time of the last geolocation call                                    |
| error     | `string`                                                                      | An error message in case geolocation API fails.                          |
| resume    | `function`                                                                    | Control function to resume updating geolocation                          |
| pause     | `function`                                                                    | Control function to pause updating geolocation                           |

## Config

`useGeolocation` function takes [PositionOptions](https://developer.mozilla.org/en-US/docs/Web/API/PositionOptions) object as an optional parameter.

## Component Usage

```vue
<template>
  <UseGeolocation v-slot="{ coords: { latitude, longitude } }">
    Latitude: {{ latitude }}
    Longitude: {{ longitude }}
  </UseGeolocation>
</template>
```

## Type Declarations

```ts
export interface UseGeolocationOptions
  extends Partial<PositionOptions>, ConfigurableNavigator {
  immediate?: boolean
}
export interface UseGeolocationReturn extends Supportable {
  coords: Ref<Omit<GeolocationPosition["coords"], "toJSON">>
  locatedAt: ShallowRef<number | null>
  error: ShallowRef<GeolocationPositionError | null>
  resume: () => void
  pause: () => void
}
/**
 * Reactive Geolocation API.
 *
 * @see https://vueuse.org/useGeolocation
 * @param options
 */
export declare function useGeolocation(
  options?: UseGeolocationOptions,
): UseGeolocationReturn
```

---

<!-- source: references/useIDBKeyval.md -->
---
category: '@Integrations'
---

# useIDBKeyval

Wrapper for [`idb-keyval`](https://www.npmjs.com/package/idb-keyval).

## Install idb-keyval as a peer dependency

```bash
npm install idb-keyval@^6
```

## Usage

```ts
import { useIDBKeyval } from '@vueuse/integrations/useIDBKeyval'

// bind object
const { data: storedObject, isFinished } = useIDBKeyval('my-idb-keyval-store', { hello: 'hi', greeting: 'Hello' })

// update object
storedObject.value.hello = 'hola'

// bind boolean
const flag = useIDBKeyval('my-flag', true) // returns Ref<boolean>

// bind number
const count = useIDBKeyval('my-count', 0) // returns Ref<number>

// awaiting IDB transaction
await count.set(10)
console.log('IDB transaction finished!')

// delete data from idb storage
storedObject.value = null
```

## Type Declarations

```ts
interface Serializer<T> {
  read: (raw: unknown) => T
  write: (value: T) => unknown
}
export interface UseIDBOptions<T> extends ConfigurableFlush {
  /**
   * Watch for deep changes
   *
   * @default true
   */
  deep?: boolean
  /**
   * On error callback
   *
   * Default log error to `console.error`
   */
  onError?: (error: unknown) => void
  /**
   * Use shallow ref as reference
   *
   * @default false
   */
  shallow?: boolean
  /**
   * Write the default value to the storage when it does not exist
   *
   * @default true
   */
  writeDefaults?: boolean
  /**
   * Custom data serialization
   */
  serializer?: Serializer<T>
}
export interface UseIDBKeyvalReturn<T> {
  data: RemovableRef<T>
  isFinished: ShallowRef<boolean>
  set: (value: T) => Promise<void>
}
/**
 *
 * @param key
 * @param initialValue
 * @param options
 */
export declare function useIDBKeyval<T>(
  key: IDBValidKey,
  initialValue: MaybeRefOrGetter<T>,
  options?: UseIDBOptions<T>,
): UseIDBKeyvalReturn<T>
```

---

<!-- source: references/useIdle.md -->
---
category: Sensors
---

# useIdle

Tracks whether the user is being inactive.

## Usage

```ts
import { useIdle } from '@vueuse/core'

const { idle, lastActive } = useIdle(5 * 60 * 1000) // 5 min

console.log(idle.value) // true or false
```

Programatically resetting:

```ts
import { useCounter, useIdle } from '@vueuse/core'
import { watch } from 'vue'

const { inc, count } = useCounter()

const { idle, lastActive, reset } = useIdle(5 * 60 * 1000) // 5 min

watch(idle, (idleValue) => {
  if (idleValue) {
    inc()
    console.log(`Triggered ${count.value} times`)
    reset() // restarts the idle timer. Does not change lastActive value
  }
})
```

## Component Usage

```vue
<template>
  <UseIdle v-slot="{ idle }" :timeout="5 * 60 * 1000">
    Is Idle: {{ idle }}
  </UseIdle>
</template>
```

## Type Declarations

```ts
export interface UseIdleOptions
  extends ConfigurableWindow, ConfigurableEventFilter {
  /**
   * Event names that listen to for detected user activity
   *
   * @default ['mousemove', 'mousedown', 'resize', 'keydown', 'touchstart', 'wheel']
   */
  events?: WindowEventName[]
  /**
   * Listen for document visibility change
   *
   * @default true
   */
  listenForVisibilityChange?: boolean
  /**
   * Initial state of the ref idle
   *
   * @default false
   */
  initialState?: boolean
}
export interface UseIdleReturn extends Stoppable {
  idle: ShallowRef<boolean>
  lastActive: ShallowRef<number>
  reset: () => void
}
/**
 * Tracks whether the user is being inactive.
 *
 * @see https://vueuse.org/useIdle
 * @param timeout default to 1 minute
 * @param options IdleOptions
 */
export declare function useIdle(
  timeout?: number,
  options?: UseIdleOptions,
): UseIdleReturn
```

---

<!-- source: references/useImage.md -->
---
category: Browser
---

# useImage

Reactive load an image in the browser, you can wait the result to display it or show a fallback.

## Usage

```vue
<script setup lang="ts">
import { useImage } from '@vueuse/core'

const avatarUrl = 'https://place.dog/300/200'
const { isLoading } = useImage({ src: avatarUrl })
</script>

<template>
  <span v-if="isLoading">Loading</span>
  <img v-else :src="avatarUrl">
</template>
```

## Component Usage

```vue
<template>
  <UseImage src="https://place.dog/300/200">
    <template #loading>
      Loading..
    </template>

    <template #error>
      Failed
    </template>
  </UseImage>
</template>
```

## Type Declarations

```ts
export interface UseImageOptions {
  /** Address of the resource */
  src: string
  /** Images to use in different situations, e.g., high-resolution displays, small monitors, etc. */
  srcset?: string
  /** Image sizes for different page layouts */
  sizes?: string
  /** Image alternative information */
  alt?: string
  /** Image classes */
  class?: string
  /** Image loading */
  loading?: HTMLImageElement["loading"]
  /** Image CORS settings */
  crossorigin?: string
  /** Referrer policy for fetch https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy */
  referrerPolicy?: HTMLImageElement["referrerPolicy"]
  /** Image width */
  width?: HTMLImageElement["width"]
  /** Image height */
  height?: HTMLImageElement["height"]
  /** https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img#decoding */
  decoding?: HTMLImageElement["decoding"]
  /** Provides a hint of the relative priority to use when fetching the image */
  fetchPriority?: HTMLImageElement["fetchPriority"]
  /** Provides a hint of the importance of the image */
  ismap?: HTMLImageElement["isMap"]
  /** The partial URL (starting with #) of an image map associated with the element */
  usemap?: HTMLImageElement["useMap"]
}
export type UseImageReturn = UseAsyncStateReturn<
  HTMLImageElement | undefined,
  any[],
  true
>
/**
 * Reactive load an image in the browser, you can wait the result to display it or show a fallback.
 *
 * @see https://vueuse.org/useImage
 * @param options Image attributes, as used in the <img> tag
 * @param asyncStateOptions
 */
export declare function useImage<Shallow extends true>(
  options: MaybeRefOrGetter<UseImageOptions>,
  asyncStateOptions?: UseAsyncStateOptions<Shallow>,
): UseImageReturn
```

---

<!-- source: references/useInfiniteScroll.md -->
---
category: Sensors
---

# useInfiniteScroll

Infinite scrolling of the element.

## Usage

```vue
<script setup lang="ts">
import { useInfiniteScroll } from '@vueuse/core'
import { ref, useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const data = ref([1, 2, 3, 4, 5, 6])

const { reset } = useInfiniteScroll(
  el,
  () => {
    // load more
    data.value.push(...moreData)
  },
  {
    distance: 10,
    canLoadMore: () => {
      // inidicate when there is no more content to load so onLoadMore stops triggering
      // if (noMoreContent) return false
      return true // for demo purposes
    },
  }
)

function resetList() {
  data.value = []
  reset()
}
</script>

<template>
  <div ref="el">
    <div v-for="item in data">
      {{ item }}
    </div>
  </div>
  <button @click="resetList()">
    Reset
  </button>
</template>
```

## Direction

Different scroll directions require different CSS style settings:

| Direction          | Required CSS                                          |
| ------------------ | ----------------------------------------------------- |
| `bottom` (default) | No special settings required                          |
| `top`              | `display: flex;`<br>`flex-direction: column-reverse;` |
| `left`             | `display: flex;`<br>`flex-direction: row-reverse;`    |
| `right`            | `display: flex;`                                      |

::: warning
Make sure to indicate when there is no more content to load with `canLoadMore`, otherwise `onLoadMore` will trigger as long as there is space for more content.
:::

## Directive Usage

```vue
<script setup lang="ts">
import { vInfiniteScroll } from '@vueuse/components'
import { ref } from 'vue'

const data = ref([1, 2, 3, 4, 5, 6])

function onLoadMore() {
  const length = data.value.length + 1
  data.value.push(...Array.from({ length: 5 }, (_, i) => length + i))
}
function canLoadMore() {
  // inidicate when there is no more content to load so onLoadMore stops triggering
  // if (noMoreContent) return false
  return true // for demo purposes
}
</script>

<template>
  <div v-infinite-scroll="onLoadMore">
    <div v-for="item in data" :key="item">
      {{ item }}
    </div>
  </div>

  <!-- with options -->
  <div v-infinite-scroll="[onLoadMore, { distance: 10, canLoadMore }]">
    <div v-for="item in data" :key="item">
      {{ item }}
    </div>
  </div>
</template>
```

## Type Declarations

```ts
type InfiniteScrollElement =
  | HTMLElement
  | SVGElement
  | Window
  | Document
  | null
  | undefined
export interface UseInfiniteScrollOptions<
  T extends InfiniteScrollElement = InfiniteScrollElement,
> extends UseScrollOptions {
  /**
   * The minimum distance between the bottom of the element and the bottom of the viewport
   *
   * @default 0
   */
  distance?: number
  /**
   * The direction in which to listen the scroll.
   *
   * @default 'bottom'
   */
  direction?: "top" | "bottom" | "left" | "right"
  /**
   * The interval time between two load more (to avoid too many invokes).
   *
   * @default 100
   */
  interval?: number
  /**
   * A function that determines whether more content can be loaded for a specific element.
   * Should return `true` if loading more content is allowed for the given element,
   * and `false` otherwise.
   */
  canLoadMore?: (el: T) => boolean
}
export interface UseInfiniteScrollReturn {
  isLoading: ComputedRef<boolean>
  reset: () => void
}
/**
 * Reactive infinite scroll.
 *
 * @see https://vueuse.org/useInfiniteScroll
 */
export declare function useInfiniteScroll<T extends InfiniteScrollElement>(
  element: MaybeRefOrGetter<T>,
  onLoadMore: (state: UnwrapNestedRefs<UseScrollReturn>) => Awaitable<void>,
  options?: UseInfiniteScrollOptions<T>,
): UseInfiniteScrollReturn
```

---

<!-- source: references/useIntersectionObserver.md -->
---
category: Elements
---

# useIntersectionObserver

Detects that a target element's visibility.

## Usage

```vue
<script setup lang="ts">
import { useIntersectionObserver } from '@vueuse/core'
import { shallowRef, useTemplateRef } from 'vue'

const target = useTemplateRef('target')
const targetIsVisible = shallowRef(false)

const { stop } = useIntersectionObserver(
  target,
  ([entry], observerElement) => {
    targetIsVisible.value = entry?.isIntersecting || false
  },
)
</script>

<template>
  <div ref="target">
    <h1>Hello world</h1>
  </div>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vIntersectionObserver } from '@vueuse/components'
import { shallowRef, useTemplateRef } from 'vue'

const root = useTemplateRef('root')

const isVisible = shallowRef(false)

function onIntersectionObserver([entry]: IntersectionObserverEntry[]) {
  isVisible.value = entry?.isIntersecting || false
}
</script>

<template>
  <div>
    <p>
      Scroll me down!
    </p>
    <div v-intersection-observer="onIntersectionObserver">
      <p>Hello world!</p>
    </div>
  </div>

  <!-- with options -->
  <div ref="root">
    <p>
      Scroll me down!
    </p>
    <div v-intersection-observer="[onIntersectionObserver, { root }]">
      <p>Hello world!</p>
    </div>
  </div>
</template>
```

[IntersectionObserver MDN](https://developer.mozilla.org/en-US/docs/Web/API/IntersectionObserver/IntersectionObserver)

## Type Declarations

```ts
export interface UseIntersectionObserverOptions extends ConfigurableWindow {
  /**
   * Start the IntersectionObserver immediately on creation
   *
   * @default true
   */
  immediate?: boolean
  /**
   * The Element or Document whose bounds are used as the bounding box when testing for intersection.
   */
  root?: MaybeComputedElementRef | Document
  /**
   * A string which specifies a set of offsets to add to the root's bounding_box when calculating intersections.
   */
  rootMargin?: MaybeRefOrGetter<string>
  /**
   * Either a single number or an array of numbers between 0.0 and 1.
   * @default 0
   */
  threshold?: number | number[]
}
export interface UseIntersectionObserverReturn extends Supportable, Pausable {
  stop: () => void
}
/**
 * Detects that a target element's visibility.
 *
 * @see https://vueuse.org/useIntersectionObserver
 * @param target
 * @param callback
 * @param options
 */
export declare function useIntersectionObserver(
  target:
    | MaybeComputedElementRef
    | MaybeRefOrGetter<MaybeElement[]>
    | MaybeComputedElementRef[],
  callback: IntersectionObserverCallback,
  options?: UseIntersectionObserverOptions,
): UseIntersectionObserverReturn
```

---

<!-- source: references/useInterval.md -->
---
category: Animation
---

# useInterval

Reactive counter that increases on every interval.

## Usage

```ts
import { useInterval } from '@vueuse/core'

// count will increase every 200ms
const counter = useInterval(200)
```

### With Controls

```ts
import { useInterval } from '@vueuse/core'

const { counter, reset, pause, resume, isActive } = useInterval(200, {
  controls: true,
})

// Reset counter to 0
reset()

// Pause/resume the interval
pause()
resume()
```

### Options

| Option      | Type                      | Default | Description                                                |
| ----------- | ------------------------- | ------- | ---------------------------------------------------------- |
| `controls`  | `boolean`                 | `false` | Expose `pause`, `resume`, `reset`, and `isActive` controls |
| `immediate` | `boolean`                 | `true`  | Start the interval immediately                             |
| `callback`  | `(count: number) => void` | —       | Called on every interval with the current count            |

### Reactive Interval

The interval can be reactive:

```ts
import { useInterval } from '@vueuse/core'

const intervalMs = ref(1000)
const counter = useInterval(intervalMs)

// Change the interval dynamically
intervalMs.value = 500
```

### Callback on Every Interval

```ts
import { useInterval } from '@vueuse/core'

useInterval(1000, {
  callback: (count) => {
    console.log(`Tick ${count}`)
  },
})
```

## Type Declarations

```ts
export interface UseIntervalOptions<Controls extends boolean> {
  /**
   * Expose more controls
   *
   * @default false
   */
  controls?: Controls
  /**
   * Execute the update immediately on calling
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Callback on every interval
   */
  callback?: (count: number) => void
}
export interface UseIntervalControls {
  counter: ShallowRef<number>
  reset: () => void
}
export type UseIntervalReturn =
  | Readonly<ShallowRef<number>>
  | Readonly<UseIntervalControls & Pausable>
/**
 * Reactive counter increases on every interval
 *
 * @see https://vueuse.org/useInterval
 * @param interval
 * @param options
 */
export declare function useInterval(
  interval?: MaybeRefOrGetter<number>,
  options?: UseIntervalOptions<false>,
): Readonly<ShallowRef<number>>
export declare function useInterval(
  interval: MaybeRefOrGetter<number>,
  options: UseIntervalOptions<true>,
): Readonly<UseIntervalControls & Pausable>
```

---

<!-- source: references/useIntervalFn.md -->
---
category: Animation
---

# useIntervalFn

Wrapper for `setInterval` with controls

## Usage

```ts
import { useIntervalFn } from '@vueuse/core'

const { pause, resume, isActive } = useIntervalFn(() => {
  /* your function */
}, 1000)
```

## Type Declarations

```ts
export interface UseIntervalFnOptions {
  /**
   * Start the timer immediately
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Execute the callback immediately after calling `resume`
   *
   * @default false
   */
  immediateCallback?: boolean
}
export type UseIntervalFnReturn = Pausable
/**
 * Wrapper for `setInterval` with controls
 *
 * @see https://vueuse.org/useIntervalFn
 * @param cb
 * @param interval
 * @param options
 */
export declare function useIntervalFn(
  cb: Fn,
  interval?: MaybeRefOrGetter<number>,
  options?: UseIntervalFnOptions,
): UseIntervalFnReturn
```

---

<!-- source: references/useIpcRenderer.md -->
---
category: '@Electron'
---

# useIpcRenderer

Provides [ipcRenderer](https://www.electronjs.org/docs/api/ipc-renderer) and all of its APIs with Vue reactivity.

## Usage

```ts
import { useIpcRenderer } from '@vueuse/electron'
import { computed } from 'vue'

// enable nodeIntegration if you don't provide ipcRenderer explicitly
// see: https://www.electronjs.org/docs/api/webview-tag#nodeintegration
const ipcRenderer = useIpcRenderer()

// Ref result will return
const result = ipcRenderer.invoke<string>('custom-channel', 'some data')
const msg = computed(() => result.value?.msg)

// remove listener automatically on unmounted
ipcRenderer.on('custom-event', (event, ...args) => {
  console.log(args)
})
```

### Available Methods

| Method                                     | Description                                          |
| ------------------------------------------ | ---------------------------------------------------- |
| `on(channel, listener)`                    | Listen to channel. Auto-removes listener on unmount. |
| `once(channel, listener)`                  | Listen to channel once                               |
| `removeListener(channel, listener)`        | Remove specific listener                             |
| `removeAllListeners(channel)`              | Remove all listeners for channel                     |
| `send(channel, ...args)`                   | Send async message to main process                   |
| `invoke(channel, ...args)`                 | Send message and get response as `ShallowRef`        |
| `sendSync(channel, ...args)`               | Send sync message and get response as `ShallowRef`   |
| `postMessage(channel, message, transfer?)` | Send message with transferable objects               |
| `sendTo(webContentsId, channel, ...args)`  | Send to specific webContents                         |
| `sendToHost(channel, ...args)`             | Send to webview host                                 |

### With Custom IpcRenderer

If `nodeIntegration` is disabled, you can pass the `ipcRenderer` instance explicitly:

```ts
import { useIpcRenderer } from '@vueuse/electron'
import { ipcRenderer } from 'electron'

const ipc = useIpcRenderer(ipcRenderer)
```

## Type Declarations

```ts
/**
 * Result from useIpcRenderer
 *
 * @see https://www.electronjs.org/docs/api/ipc-renderer
 */
export interface UseIpcRendererReturn {
  /**
   * Listens to channel, when a new message arrives listener would be called with listener(event, args...).
   * [ipcRenderer.removeListener](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovelistenerchannel-listener) automatically on unmounted.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendereronchannel-listener
   */
  on: (channel: string, listener: IpcRendererListener) => IpcRenderer
  /**
   * Adds a one time listener function for the event. This listener is invoked only the next time a message is sent to channel, after which it is removed.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendereroncechannel-listener
   */
  once: (
    channel: string,
    listener: (event: IpcRendererEvent, ...args: any[]) => void,
  ) => IpcRenderer
  /**
   * Removes the specified listener from the listener array for the specified channel.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovelistenerchannel-listener
   */
  removeListener: (
    channel: string,
    listener: (...args: any[]) => void,
  ) => IpcRenderer
  /**
   * Removes all listeners, or those of the specified channel.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovealllistenerschannel
   */
  removeAllListeners: (channel: string) => IpcRenderer
  /**
   * Send an asynchronous message to the main process via channel, along with arguments.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrenderersendchannel-args
   */
  send: (channel: string, ...args: any[]) => void
  /**
   * Returns Promise<any> - Resolves with the response from the main process.
   * Send a message to the main process via channel and expect a result ~~asynchronously~~.
   * As composition-api, it makes asynchronous operations look like synchronous.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererinvokechannel-args
   */
  invoke: <T>(channel: string, ...args: any[]) => ShallowRef<T | null>
  /**
   * Returns any - The value sent back by the ipcMain handler.
   * Send a message to the main process via channel and expect a result synchronously.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrenderersendsyncchannel-args
   */
  sendSync: <T>(channel: string, ...args: any[]) => ShallowRef<T | null>
  /**
   * Send a message to the main process, optionally transferring ownership of zero or more MessagePort objects.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererpostmessagechannel-message-transfer
   */
  postMessage: (channel: string, message: any, transfer?: MessagePort[]) => void
  /**
   * Sends a message to a window with webContentsId via channel.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrenderersendtowebcontentsid-channel-args
   */
  sendTo: (webContentsId: number, channel: string, ...args: any[]) => void
  /**
   * Like ipcRenderer.send but the event will be sent to the <webview> element in the host page instead of the main process.
   *
   * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrenderersendtohostchannel-args
   */
  sendToHost: (channel: string, ...args: any[]) => void
}
/**
 * Get the `ipcRenderer` module with all APIs.
 *
 * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrenderersendtohostchannel-args
 * @see https://vueuse.org/useIpcRenderer
 */
export declare function useIpcRenderer(
  ipcRenderer?: IpcRenderer,
): UseIpcRendererReturn
```

---

<!-- source: references/useIpcRendererInvoke.md -->
---
category: '@Electron'
---

# useIpcRendererInvoke

Reactive [ipcRenderer.invoke API](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererinvokechannel-args) result. Make asynchronous operations look synchronous.

## Usage

```ts
import { useIpcRendererInvoke } from '@vueuse/electron'
import { computed } from 'vue'

// enable nodeIntegration if you don't provide ipcRenderer explicitly
// see: https://www.electronjs.org/docs/api/webview-tag#nodeintegration
// Ref result will return
const result = useIpcRendererInvoke<string>('custom-channel', 'some data')
const msg = computed(() => result.value?.msg)
```

## Type Declarations

```ts
/**
 * Returns Promise<any> - Resolves with the response from the main process.
 *
 * Send a message to the main process via channel and expect a result ~~asynchronously~~. As composition-api, it makes asynchronous operations look like synchronous.
 *
 * You need to provide `ipcRenderer` to this function.
 *
 * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererinvokechannel-args
 * @see https://vueuse.org/useIpcRendererInvoke
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useIpcRendererInvoke<T>(
  ipcRenderer: IpcRenderer,
  channel: string,
  ...args: any[]
): ShallowRef<T | null>
/**
 * Returns Promise<any> - Resolves with the response from the main process.
 *
 * Send a message to the main process via channel and expect a result ~~asynchronously~~. As composition-api, it makes asynchronous operations look like synchronous.
 *
 * `ipcRenderer` will be automatically gotten.
 *
 * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererinvokechannel-args
 * @see https://vueuse.org/useIpcRendererInvoke
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useIpcRendererInvoke<T>(
  channel: string,
  ...args: any[]
): ShallowRef<T | null>
```

---

<!-- source: references/useIpcRendererOn.md -->
---
category: '@Electron'
---

# useIpcRendererOn

Use [ipcRenderer.on](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendereronchannel-listener) with ease and [ipcRenderer.removeListener](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovelistenerchannel-listener) automatically on unmounted.

## Usage

```ts
import { useIpcRendererOn } from '@vueuse/electron'

// enable nodeIntegration if you don't provide ipcRenderer explicitly
// see: https://www.electronjs.org/docs/api/webview-tag#nodeintegration
// remove listener automatically on unmounted
useIpcRendererOn('custom-event', (event, ...args) => {
  console.log(args)
})
```

## Type Declarations

```ts
/**
 * Listens to channel, when a new message arrives listener would be called with listener(event, args...).
 * [ipcRenderer.removeListener](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovelistenerchannel-listener) automatically on unmounted.
 *
 * You need to provide `ipcRenderer` to this function.
 *
 * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendereronchannel-listener
 * @see https://vueuse.org/useIpcRendererOn
 */
export declare function useIpcRendererOn(
  ipcRenderer: IpcRenderer,
  channel: string,
  listener: IpcRendererListener,
): IpcRenderer
/**
 * Listens to channel, when a new message arrives listener would be called with listener(event, args...).
 * [ipcRenderer.removeListener](https://www.electronjs.org/docs/api/ipc-renderer#ipcrendererremovelistenerchannel-listener) automatically on unmounted.
 *
 * `ipcRenderer` will be automatically gotten.
 *
 * @see https://www.electronjs.org/docs/api/ipc-renderer#ipcrendereronchannel-listener
 * @see https://vueuse.org/useIpcRendererOn
 */
export declare function useIpcRendererOn(
  channel: string,
  listener: IpcRendererListener,
): IpcRenderer
```

---

<!-- source: references/useJwt.md -->
---
category: '@Integrations'
---

# useJwt

Wrapper for [`jwt-decode`](https://github.com/auth0/jwt-decode).

## Install

```bash
npm install jwt-decode@^4
```

## Usage

```ts
import { useJwt } from '@vueuse/integrations/useJwt'
import { defineComponent } from 'vue'

const encodedJwt = ref('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaWF0IjoxNTE2MjM5MDIyfQ.L8i6g3PfcHlioHCCPURC9pmXT7gdJpx3kOoyAfNUwCc')
const { header, payload } = useJwt(encodedJwt)
```

## Type Declarations

```ts
export interface UseJwtOptions<Fallback> {
  /**
   * Value returned when encounter error on decoding
   *
   * @default null
   */
  fallbackValue?: Fallback
  /**
   * Error callback for decoding
   */
  onError?: (error: unknown) => void
}
export interface UseJwtReturn<Payload, Header, Fallback> {
  header: ComputedRef<Header | Fallback>
  payload: ComputedRef<Payload | Fallback>
}
/**
 * Reactive decoded jwt token.
 *
 * @see https://vueuse.org/useJwt
 */
export declare function useJwt<
  Payload extends object = JwtPayload,
  Header extends object = JwtHeader,
  Fallback = null,
>(
  encodedJwt: MaybeRefOrGetter<string>,
  options?: UseJwtOptions<Fallback>,
): UseJwtReturn<Payload, Header, Fallback>
```

---

<!-- source: references/useKeyModifier.md -->
---
category: Sensors
---

# useKeyModifier

Reactive [Modifier State](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/getModifierState). Tracks state of any of the [supported modifiers](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/getModifierState#browser_compatibility) - see Browser Compatibility notes.

<CourseLink href="https://vueschool.io/lessons/alt-drag-to-clone-tasks?friend=vueuse">Learn useKeyModifier with this FREE video lesson from Vue School!</CourseLink>

## Usage

```ts
import { useKeyModifier } from '@vueuse/core'

const capsLockState = useKeyModifier('CapsLock')

console.log(capsLockState.value)
```

## Events

You can customize which events will prompt the state to update. By default, these are `mouseup`, `mousedown`, `keyup`, `keydown`. To customize these events:

```ts
import { useKeyModifier } from '@vueuse/core'

const capsLockState = useKeyModifier('CapsLock', { events: ['mouseup', 'mousedown'] })

console.log(capsLockState) // null

// Caps Lock turned on with key press
console.log(capsLockState) // null

// Mouse button clicked
console.log(capsLockState) // true
```

## Initial State

By default, the returned ref will be `Ref<null>` until the first event is received. You can explicitly pass the initial state to it via:

```ts
import { useKeyModifier } from '@vueuse/core'
// ---cut---
const capsLockState1 = useKeyModifier('CapsLock') // Ref<boolean | null>
const capsLockState2 = useKeyModifier('CapsLock', { initial: false }) // Ref<boolean>
```

## Type Declarations

```ts
export type KeyModifier =
  | "Alt"
  | "AltGraph"
  | "CapsLock"
  | "Control"
  | "Fn"
  | "FnLock"
  | "Meta"
  | "NumLock"
  | "ScrollLock"
  | "Shift"
  | "Symbol"
  | "SymbolLock"
export interface UseModifierOptions<Initial> extends ConfigurableDocument {
  /**
   * Event names that will prompt update to modifier states
   *
   * @default ['mousedown', 'mouseup', 'keydown', 'keyup']
   */
  events?: WindowEventName[]
  /**
   * Initial value of the returned ref
   *
   * @default null
   */
  initial?: Initial
}
export type UseKeyModifierReturn<Initial> = ShallowRef<
  Initial extends boolean ? boolean : boolean | null
>
export declare function useKeyModifier<Initial extends boolean | null>(
  modifier: KeyModifier,
  options?: UseModifierOptions<Initial>,
): UseKeyModifierReturn<Initial>
```

---

<!-- source: references/useLastChanged.md -->
---
category: State
---

# useLastChanged

Records the timestamp of the last change

## Usage

```ts
import { useLastChanged } from '@vueuse/core'
import { nextTick } from 'vue'

const a = ref(0)
const lastChanged = useLastChanged(a)

a.value = 1

await nextTick()

console.log(lastChanged.value) // 1704709379457
```

By default the change is recorded on the next tick (`watch()` with `flush: 'post'`). If you want to record the change immediately, pass `flush: 'sync'` as the second argument.

```ts
import { useLastChanged } from '@vueuse/core'

const a = ref(0)
const lastChanged = useLastChanged(a, { flush: 'sync' })

a.value = 1

console.log(lastChanged.value) // 1704709379457
```

## Type Declarations

```ts
export interface UseLastChangedOptions<
  Immediate extends boolean,
  InitialValue extends number | null | undefined = undefined,
> extends WatchOptions<Immediate> {
  initialValue?: InitialValue
}
export type UseLastChangedReturn =
  | Readonly<ShallowRef<number | null>>
  | Readonly<ShallowRef<number>>
/**
 * Records the timestamp of the last change
 *
 * @see https://vueuse.org/useLastChanged
 */
export declare function useLastChanged(
  source: WatchSource,
  options?: UseLastChangedOptions<false>,
): Readonly<ShallowRef<number | null>>
export declare function useLastChanged(
  source: WatchSource,
  options: UseLastChangedOptions<true> | UseLastChangedOptions<boolean, number>,
): Readonly<ShallowRef<number>>
```

---

<!-- source: references/useLocalStorage.md -->
---
category: State
---

# useLocalStorage

Reactive [LocalStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage).

## Usage

Please refer to `useStorage`.

## Type Declarations

```ts
export declare function useLocalStorage(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<string>,
  options?: UseStorageOptions<string>,
): RemovableRef<string>
export declare function useLocalStorage(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<boolean>,
  options?: UseStorageOptions<boolean>,
): RemovableRef<boolean>
export declare function useLocalStorage(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<number>,
  options?: UseStorageOptions<number>,
): RemovableRef<number>
export declare function useLocalStorage<T>(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<T>,
  options?: UseStorageOptions<T>,
): RemovableRef<T>
export declare function useLocalStorage<T = unknown>(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<null>,
  options?: UseStorageOptions<T>,
): RemovableRef<T>
```

---

<!-- source: references/useMagicKeys.md -->
---
category: Sensors
---

# useMagicKeys

Reactive keys pressed state, with magical keys combination support.

## Usage

```ts
import { useMagicKeys } from '@vueuse/core'

const { shift, space, a /* keys you want to monitor */ } = useMagicKeys()

watch(space, (v) => {
  if (v)
    console.log('space has been pressed')
})

watchEffect(() => {
  if (shift.value && a.value)
    console.log('Shift + A have been pressed')
})
```

::: tip NOTE
If you're using TypeScript with `noUncheckedIndexedAccess` enabled in your `tsconfig.json` (or using Nuxt which enables it by default), the destructured keys will have the type `ComputedRef<boolean> | undefined`.

The `noUncheckedIndexedAccess` TypeScript option adds `undefined` to any un-declared field accessed via index signatures. Since `useMagicKeys()` uses an index signature to allow accessing any key dynamically, TypeScript will treat destructured properties as potentially undefined for type safety.

You'll need to use optional chaining or wrap with a getter function:

```ts
const { shift, space, a } = useMagicKeys()

watch(
  () => space?.value,
  (v) => {
    if (v)
      console.log('space has been pressed')
  },
)

watchEffect(() => {
  if (shift?.value && a?.value)
    console.log('Shift + A have been pressed')
})
```

Check the [TypeScript documentation](https://www.typescriptlang.org/tsconfig/#noUncheckedIndexedAccess) for more details about `noUncheckedIndexedAccess`.

:::

Check out [all the possible keycodes](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/code/code_values).

### Combinations

You can magically use combinations (shortcuts/hotkeys) by connecting keys with `+` or `_`.

```ts
import { useMagicKeys } from '@vueuse/core'

const keys = useMagicKeys()
const shiftCtrlA = keys['Shift+Ctrl+A']

watch(shiftCtrlA, (v) => {
  if (v)
    console.log('Shift + Ctrl + A have been pressed')
})
```

```ts
import { useMagicKeys } from '@vueuse/core'

const { Ctrl_A_B, space, alt_s /* ... */ } = useMagicKeys()

watch(Ctrl_A_B, (v) => {
  if (v)
    console.log('Control+A+B have been pressed')
})
```

You can also use `whenever` function to make it shorter

```ts
import { useMagicKeys, whenever } from '@vueuse/core'

const keys = useMagicKeys()

whenever(keys.shift_space, () => {
  console.log('Shift+Space have been pressed')
})
```

### Current Pressed keys

A special property `current` is provided to representing all the keys been pressed currently.

```ts
import { useMagicKeys, whenever } from '@vueuse/core'

const { current } = useMagicKeys()

console.log(current) // Set { 'control', 'a' }

whenever(
  () => current.has('a') && !current.has('b'),
  () => console.log('A is pressed but not B'),
)
```

### Key Aliasing

```ts
import { useMagicKeys, whenever } from '@vueuse/core'

const { shift_cool } = useMagicKeys({
  aliasMap: {
    cool: 'space',
  },
})

whenever(shift_cool, () => console.log('Shift + Space have been pressed'))
```

By default, we have some [preconfigured alias for common practices](https://github.com/vueuse/vueuse/blob/main/packages/core/useMagicKeys/aliasMap.ts).

### Conditionally Disable

You might have some `<input />` elements in your apps, and you don't want to trigger the magic keys handling when users focused on those inputs. There is an example of using `useActiveElement` and `logicAnd` to do that.

```ts
import { useActiveElement, useMagicKeys, whenever } from '@vueuse/core'
import { logicAnd } from '@vueuse/math'

const activeElement = useActiveElement()
const notUsingInput = computed(() =>
  activeElement.value?.tagName !== 'INPUT'
  && activeElement.value?.tagName !== 'TEXTAREA',)

const { tab } = useMagicKeys()

whenever(logicAnd(tab, notUsingInput), () => {
  console.log('Tab has been pressed outside of inputs!')
})
```

### Custom Event Handler

```ts
import { useMagicKeys, whenever } from '@vueuse/core'

const { ctrl_s } = useMagicKeys({
  passive: false,
  onEventFired(e) {
    if (e.ctrlKey && e.key === 's' && e.type === 'keydown')
      e.preventDefault()
  },
})

whenever(ctrl_s, () => console.log('Ctrl+S have been pressed'))
```

> ⚠️ This usage is NOT recommended, please use with caution.

### Reactive Mode

By default, the values of `useMagicKeys()` are `Ref<boolean>`. If you want to use the object in the template, you can set it to reactive mode.

```ts
import { useMagicKeys } from '@vueuse/core'
// ---cut---
const keys = useMagicKeys({ reactive: true })
```

```vue
<template>
  <div v-if="keys.shift">
    You are holding the Shift key!
  </div>
</template>
```

## Type Declarations

```ts
export interface UseMagicKeysOptions<Reactive extends boolean> {
  /**
   * Returns a reactive object instead of an object of refs
   *
   * @default false
   */
  reactive?: Reactive
  /**
   * Target for listening events
   *
   * @default window
   */
  target?: MaybeRefOrGetter<EventTarget>
  /**
   * Alias map for keys, all the keys should be lowercase
   * { target: keycode }
   *
   * @example { ctrl: "control" }
   * @default <predefined-map>
   */
  aliasMap?: Record<string, string>
  /**
   * Register passive listener
   *
   * @default true
   */
  passive?: boolean
  /**
   * Custom event handler for keydown/keyup event.
   * Useful when you want to apply custom logic.
   *
   * When using `e.preventDefault()`, you will need to pass `passive: false` to useMagicKeys().
   */
  onEventFired?: (e: KeyboardEvent) => void | boolean
}
export interface MagicKeysInternal {
  /**
   * A Set of currently pressed keys,
   * Stores raw keyCodes.
   *
   * @see https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key
   */
  current: Set<string>
}
export type UseMagicKeysReturn<Reactive extends boolean> = Readonly<
  Record<string, Reactive extends true ? boolean : ComputedRef<boolean>> &
    MagicKeysInternal
>
/**
 * Reactive keys pressed state, with magical keys combination support.
 *
 * @see https://vueuse.org/useMagicKeys
 */
export declare function useMagicKeys<T extends boolean = false>(
  options?: UseMagicKeysOptions<T>,
): UseMagicKeysReturn<T>
export { DefaultMagicKeysAliasMap } from "./aliasMap"
```

---

<!-- source: references/useManualRefHistory.md -->
---
category: State
related: useRefHistory
---

# useManualRefHistory

Manually track the change history of a ref when the using calls `commit()`, also provides undo and redo functionality

## Usage

```ts {5} twoslash include usage
import { useManualRefHistory } from '@vueuse/core'
import { shallowRef } from 'vue'

const counter = shallowRef(0)
const { history, commit, undo, redo } = useManualRefHistory(counter)

counter.value += 1
commit()

console.log(history.value)
/* [
  { snapshot: 1, timestamp: 1601912898062 },
  { snapshot: 0, timestamp: 1601912898061 }
] */
```

You can use `undo` to reset the ref value to the last history point.

```ts
// @include: usage
// ---cut---
console.log(counter.value) // 1
undo()
console.log(counter.value) // 0
```

#### History of mutable objects

If you are going to mutate the source, you need to pass a custom clone function or use `clone` `true` as a param, that is a shortcut for a minimal clone function `x => JSON.parse(JSON.stringify(x))` that will be used in both `dump` and `parse`.

```ts {5}
import { useManualRefHistory } from '@vueuse/core'
import { ref } from 'vue'

const counter = ref({ foo: 1, bar: 2 })
const { history, commit, undo, redo } = useManualRefHistory(counter, { clone: true })

counter.value.foo += 1
commit()
```

#### Custom Clone Function

To use a full featured or custom clone function, you can set up via the `clone` options.

For example, using [structuredClone](https://developer.mozilla.org/en-US/docs/Web/API/structuredClone):

```ts
import { useManualRefHistory } from '@vueuse/core'

const refHistory = useManualRefHistory(target, { clone: structuredClone })
```

Or by using [lodash's `cloneDeep`](https://lodash.com/docs/4.17.15#cloneDeep):

```ts
import { useManualRefHistory } from '@vueuse/core'
import { cloneDeep } from 'lodash-es'

const refHistory = useManualRefHistory(target, { clone: cloneDeep })
```

Or a more lightweight [`klona`](https://github.com/lukeed/klona):

```ts
import { useManualRefHistory } from '@vueuse/core'
import { klona } from 'klona'

const refHistory = useManualRefHistory(target, { clone: klona })
```

#### Custom Dump and Parse Function

Instead of using the `clone` options, you can pass custom functions to control the serialization and parsing. In case you do not need history values to be objects, this can save an extra clone when undoing. It is also useful in case you want to have the snapshots already stringified to be saved to local storage for example.

```ts
import { useManualRefHistory } from '@vueuse/core'

const refHistory = useManualRefHistory(target, {
  dump: JSON.stringify,
  parse: JSON.parse,
})
```

### History Capacity

We will keep all the history by default (unlimited) until you explicitly clear them up, you can set the maximal amount of history to be kept by `capacity` options.

```ts
import { useManualRefHistory } from '@vueuse/core'

const refHistory = useManualRefHistory(target, {
  capacity: 15, // limit to 15 history records
})

refHistory.clear() // explicitly clear all the history
```

## Type Declarations

```ts
export interface UseRefHistoryRecord<T> {
  snapshot: T
  timestamp: number
}
export interface UseManualRefHistoryOptions<Raw, Serialized = Raw> {
  /**
   * Maximum number of history to be kept. Default to unlimited.
   */
  capacity?: number
  /**
   * Clone when taking a snapshot, shortcut for dump: JSON.parse(JSON.stringify(value)).
   * Default to false
   *
   * @default false
   */
  clone?: boolean | CloneFn<Raw>
  /**
   * Serialize data into the history
   */
  dump?: (v: Raw) => Serialized
  /**
   * Deserialize data from the history
   */
  parse?: (v: Serialized) => Raw
  /**
   * set data source
   */
  setSource?: (source: Ref<Raw>, v: Raw) => void
}
export interface UseManualRefHistoryReturn<Raw, Serialized> {
  /**
   * Bypassed tracking ref from the argument
   */
  source: Ref<Raw>
  /**
   * An array of history records for undo, newest comes to first
   */
  history: Ref<UseRefHistoryRecord<Serialized>[]>
  /**
   * Last history point, source can be different if paused
   */
  last: Ref<UseRefHistoryRecord<Serialized>>
  /**
   * Same as {@link UseManualRefHistoryReturn.history | history}
   */
  undoStack: Ref<UseRefHistoryRecord<Serialized>[]>
  /**
   * Records array for redo
   */
  redoStack: Ref<UseRefHistoryRecord<Serialized>[]>
  /**
   * A ref representing if undo is possible (non empty undoStack)
   */
  canUndo: ComputedRef<boolean>
  /**
   * A ref representing if redo is possible (non empty redoStack)
   */
  canRedo: ComputedRef<boolean>
  /**
   * Undo changes
   */
  undo: () => void
  /**
   * Redo changes
   */
  redo: () => void
  /**
   * Clear all the history
   */
  clear: () => void
  /**
   * Create a new history record
   */
  commit: () => void
  /**
   * Reset ref's value with latest history
   */
  reset: () => void
}
/**
 * Track the change history of a ref, also provides undo and redo functionality.
 *
 * @see https://vueuse.org/useManualRefHistory
 * @param source
 * @param options
 */
export declare function useManualRefHistory<Raw, Serialized = Raw>(
  source: Ref<Raw>,
  options?: UseManualRefHistoryOptions<Raw, Serialized>,
): UseManualRefHistoryReturn<Raw, Serialized>
```

---

<!-- source: references/useMath.md -->
---
category: '@Math'
---

# useMath

Reactive `Math` methods.

## Usage

```ts
import { useMath } from '@vueuse/math'

const base = ref(2)
const exponent = ref(3)
const result = useMath('pow', base, exponent) // Ref<8>

const num = ref(2)
const root = useMath('sqrt', num) // Ref<1.4142135623730951>

num.value = 4
console.log(root.value) // 2
```

## Type Declarations

```ts
export type UseMathKeys = keyof {
  [K in keyof Math as Math[K] extends (...args: any) => any
    ? K
    : never]: unknown
}
export type UseMathReturn<K extends keyof Math> = ReturnType<
  Reactified<Math[K], true>
>
/**
 * Reactive `Math` methods.
 *
 * @see https://vueuse.org/useMath
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useMath<K extends keyof Math>(
  key: K,
  ...args: ArgumentsType<Reactified<Math[K], true>>
): UseMathReturn<K>
```

---

<!-- source: references/useMax.md -->
---
category: '@Math'
---

# useMax

Reactive `Math.max`.

## Usage

```ts
import { useMax } from '@vueuse/math'

const array = ref([1, 2, 3, 4])
const max = useMax(array) // Ref<4>
```

```ts
import { useMax } from '@vueuse/math'

const a = ref(1)
const b = ref(3)

const max = useMax(a, b, 2) // Ref<3>
```

## Type Declarations

```ts
export declare function useMax(
  array: MaybeRefOrGetter<MaybeRefOrGetter<number>[]>,
): ComputedRef<number>
export declare function useMax(
  ...args: MaybeRefOrGetter<number>[]
): ComputedRef<number>
```

---

<!-- source: references/useMediaControls.md -->
---
category: Browser
---

# useMediaControls

Reactive media controls for both `audio` and `video` elements

## Usage

### Basic Usage

```vue
<script setup lang="ts">
import { useMediaControls } from '@vueuse/core'
import { onMounted, useTemplateRef } from 'vue'

const video = useTemplateRef('video')
const { playing, currentTime, duration, volume } = useMediaControls(video, {
  src: 'video.mp4',
})

// Change initial media properties
onMounted(() => {
  volume.value = 0.5
  currentTime.value = 60
})
</script>

<template>
  <video ref="video" />
  <button @click="playing = !playing">
    Play / Pause
  </button>
  <span>{{ currentTime }} / {{ duration }}</span>
</template>
```

### Providing Captions, Subtitles, etc...

You can provide captions, subtitles, etc in the `tracks` options of the
`useMediaControls` function. The function will return an array of tracks
along with two functions for controlling them, `enableTrack`, `disableTrack`, and `selectedTrack`.
Using these you can manage the currently selected track. `selectedTrack` will
be `-1` if there is no selected track.

```vue
<script setup lang="ts">
import { useMediaControls } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const video = useTemplateRef('video')
const {
  tracks,
  enableTrack
} = useMediaControls(video, {
  src: 'video.mp4',
  tracks: [
    {
      default: true,
      src: './subtitles.vtt',
      kind: 'subtitles',
      label: 'English',
      srcLang: 'en',
    },
  ]
})
</script>

<template>
  <video ref="video" />
  <button v-for="track in tracks" :key="track.id" @click="enableTrack(track)">
    {{ track.label }}
  </button>
</template>
```

## Type Declarations

```ts
/**
 * Many of the jsdoc definitions here are modified version of the
 * documentation from MDN(https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement)
 */
export interface UseMediaSource {
  /**
   * The source url for the media
   */
  src: string
  /**
   * The media codec type
   */
  type?: string
  /**
   * Specifies the media query for the resource's intended media.
   */
  media?: string
}
export interface UseMediaTextTrackSource {
  /**
   * Indicates that the track should be enabled unless the user's preferences indicate
   * that another track is more appropriate
   */
  default?: boolean
  /**
   * How the text track is meant to be used. If omitted the default kind is subtitles.
   */
  kind: TextTrackKind
  /**
   * A user-readable title of the text track which is used by the browser
   * when listing available text tracks.
   */
  label: string
  /**
   * Address of the track (.vtt file). Must be a valid URL. This attribute
   * must be specified and its URL value must have the same origin as the document
   */
  src: string
  /**
   * Language of the track text data. It must be a valid BCP 47 language tag.
   * If the kind attribute is set to subtitles, then srclang must be defined.
   */
  srcLang: string
}
interface UseMediaControlsOptions extends ConfigurableDocument {
  /**
   * The source for the media, may either be a string, a `UseMediaSource` object, or a list
   * of `UseMediaSource` objects.
   */
  src?: MaybeRefOrGetter<string | UseMediaSource | UseMediaSource[]>
  /**
   * A list of text tracks for the media
   */
  tracks?: MaybeRefOrGetter<UseMediaTextTrackSource[]>
}
export interface UseMediaTextTrack {
  /**
   * The index of the text track
   */
  id: number
  /**
   * The text track label
   */
  label: string
  /**
   * Language of the track text data. It must be a valid BCP 47 language tag.
   * If the kind attribute is set to subtitles, then srclang must be defined.
   */
  language: string
  /**
   * Specifies the display mode of the text track, either `disabled`,
   * `hidden`, or `showing`
   */
  mode: TextTrackMode
  /**
   * How the text track is meant to be used. If omitted the default kind is subtitles.
   */
  kind: TextTrackKind
  /**
   * Indicates the track's in-band metadata track dispatch type.
   */
  inBandMetadataTrackDispatchType: string
  /**
   * A list of text track cues
   */
  cues: TextTrackCueList | null
  /**
   * A list of active text track cues
   */
  activeCues: TextTrackCueList | null
}
export interface UseMediaControlsReturn {
  currentTime: ShallowRef<number>
  duration: ShallowRef<number>
  waiting: ShallowRef<boolean>
  seeking: ShallowRef<boolean>
  ended: ShallowRef<boolean>
  stalled: ShallowRef<boolean>
  buffered: Ref<[number, number][]>
  playing: ShallowRef<boolean>
  rate: ShallowRef<number>
  volume: ShallowRef<number>
  muted: ShallowRef<boolean>
  tracks: Ref<UseMediaTextTrack[]>
  selectedTrack: ShallowRef<number>
  enableTrack: (
    track: number | UseMediaTextTrack,
    disableTracks?: boolean,
  ) => void
  disableTrack: (track?: number | UseMediaTextTrack) => void
  supportsPictureInPicture: boolean
  togglePictureInPicture: () => Promise<PictureInPictureWindow | void>
  isPictureInPicture: ShallowRef<boolean>
  onSourceError: EventHookOn<Event>
  onPlaybackError: EventHookOn<Event>
}
export declare function useMediaControls(
  target: MaybeRef<HTMLMediaElement | null | undefined>,
  options?: UseMediaControlsOptions,
): UseMediaControlsReturn
```

---

<!-- source: references/useMediaQuery.md -->
---
category: Browser
---

# useMediaQuery

Reactive [Media Query](https://developer.mozilla.org/en-US/docs/Web/CSS/Media_Queries/Testing_media_queries). Once you've created a MediaQueryList object, you can check the result of the query or receive notifications when the result changes.

## Usage

```ts
import { useMediaQuery } from '@vueuse/core'

const isLargeScreen = useMediaQuery('(min-width: 1024px)')
const isPreferredDark = useMediaQuery('(prefers-color-scheme: dark)')
```

#### Server Side Rendering and Nuxt

If you are using `useMediaQuery` with SSR enabled, then you need to specify which screen size you would like to render on the server and before hydration to avoid an hydration mismatch

```ts
import { useMediaQuery } from '@vueuse/core'

const isLarge = useMediaQuery('(min-width: 1024px)', {
  ssrWidth: 768 // Will enable SSR mode and render like if the screen was 768px wide
})

console.log(isLarge.value) // always false because ssrWidth of 768px is smaller than 1024px
onMounted(() => {
  console.log(isLarge.value) // false if screen is smaller than 1024px, true if larger than 1024px
})
```

Alternatively you can set this up globally for your app using [`provideSSRWidth`](../useSSRWidth/index.md)

## Type Declarations

```ts
/**
 * Reactive Media Query.
 *
 * @see https://vueuse.org/useMediaQuery
 * @param query
 * @param options
 */
export declare function useMediaQuery(
  query: MaybeRefOrGetter<string>,
  options?: ConfigurableWindow & {
    ssrWidth?: number
  },
): ComputedRef<boolean>
```

---

<!-- source: references/useMemoize.md -->
---
category: Utilities
---

# useMemoize

Cache results of functions depending on arguments and keep it reactive. It can also be used for asynchronous functions and will reuse existing promises to avoid fetching the same data at the same time.

::: tip
The results are not cleared automatically. Call `clear()` in case you no longer need the results or use own caching mechanism to avoid memory leaks.
:::

## Usage

```ts
import { useMemoize } from '@vueuse/core'

const getUser = useMemoize(
  async (userId: number): Promise<UserData> =>
    axios.get(`users/${userId}`).then(({ data }) => data),
)

const user1 = await getUser(1) // Request users/1
const user2 = await getUser(2) // Request users/2
// ...
const user1 = await getUser(1) // Retrieve from cache

// ...
const user1 = await getUser.load(1) // Request users/1

// ...
getUser.delete(1) // Delete cache from user 1
getUser.clear() // Clear full cache
```

Combine with `computed` or `computedAsync` to achieve reactivity:

```ts
import { computedAsync, useMemoize } from '@vueuse/core'

const getUser = useMemoize(
  async (userId: number): Promise<UserData> =>
    axios.get(`users/${userId}`).then(({ data }) => data),
)
// ---cut---
const user1 = computedAsync(() => getUser(1))
// ...
await getUser.load(1) // Will also update user1
```

### Resolving cache key

The key for caching is determined by the arguments given to the function and will be serialized by default with `JSON.stringify`.
This will allow equal objects to receive the same cache key. In case you want to customize the key you can pass `getKey`

::: warning Performance Consideration
Using `JSON.stringify` as the default key generator can be **slow for large or complex objects**. For better performance with complex arguments, it's highly recommended to provide a custom `getKey` function that generates keys based on primitive values or unique identifiers.
:::

#### Basic Example

```ts
import { useMemoize } from '@vueuse/core'
// ---cut---
const getUser = useMemoize(
  async (userId: number, headers: AxiosRequestHeaders): Promise<UserData> =>
    axios.get(`users/${userId}`, { headers }).then(({ data }) => data),
  {
    // Use only userId to get/set cache and ignore headers
    getKey: (userId, headers) => userId,
  },
)
```

### Customize cache mechanism

By default, the results are cached within a `Map`. You can implement your own mechanism by passing `cache` as options with following structure:

```ts
export interface MemoizeCache<Key, Value> {
  /**
   * Get value for key
   */
  get: (key: Key) => Value | undefined
  /**
   * Set value for key
   */
  set: (key: Key, value: Value) => void
  /**
   * Return flag if key exists
   */
  has: (key: Key) => boolean
  /**
   * Delete value for key
   */
  delete: (key: Key) => void
  /**
   * Clear cache
   */
  clear: () => void
}
```

## Type Declarations

```ts
type CacheKey = any
/**
 * Custom memoize cache handler
 */
export interface UseMemoizeCache<Key, Value> {
  /**
   * Get value for key
   */
  get: (key: Key) => Value | undefined
  /**
   * Set value for key
   */
  set: (key: Key, value: Value) => void
  /**
   * Return flag if key exists
   */
  has: (key: Key) => boolean
  /**
   * Delete value for key
   */
  delete: (key: Key) => void
  /**
   * Clear cache
   */
  clear: () => void
}
/**
 * Memoized function
 */
export interface UseMemoizeReturn<Result, Args extends unknown[]> {
  /**
   * Get result from cache or call memoized function
   */
  (...args: Args): Result
  /**
   * Call memoized function and update cache
   */
  load: (...args: Args) => Result
  /**
   * Delete cache of given arguments
   */
  delete: (...args: Args) => void
  /**
   * Clear cache
   */
  clear: () => void
  /**
   * Generate cache key for given arguments
   */
  generateKey: (...args: Args) => CacheKey
  /**
   * Cache container
   */
  cache: UseMemoizeCache<CacheKey, Result>
}
export interface UseMemoizeOptions<Result, Args extends unknown[]> {
  getKey?: (...args: Args) => string | number
  cache?: UseMemoizeCache<CacheKey, Result>
}
/**
 * Reactive function result cache based on arguments
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useMemoize<Result, Args extends unknown[]>(
  resolver: (...args: Args) => Result,
  options?: UseMemoizeOptions<Result, Args>,
): UseMemoizeReturn<Result, Args>
```

---

<!-- source: references/useMemory.md -->
---
category: Browser
---

# useMemory

Reactive Memory Info.

## Usage

```ts
import { useMemory } from '@vueuse/core'

const { isSupported, memory } = useMemory()
```

## Type Declarations

```ts
/**
 * Performance.memory
 *
 * @see https://developer.mozilla.org/en-US/docs/Web/API/Performance/memory
 */
export interface MemoryInfo {
  /**
   * The maximum size of the heap, in bytes, that is available to the context.
   */
  readonly jsHeapSizeLimit: number
  /**
   *  The total allocated heap size, in bytes.
   */
  readonly totalJSHeapSize: number
  /**
   * The currently active segment of JS heap, in bytes.
   */
  readonly usedJSHeapSize: number
  [Symbol.toStringTag]: "MemoryInfo"
}
export interface UseMemoryOptions extends ConfigurableScheduler {
  /**
   * Start the timer immediately
   *
   * @deprecated Please use `scheduler` option instead
   * @default true
   */
  immediate?: boolean
  /**
   * Execute the callback immediately after calling `resume`
   *
   * @deprecated Please use `scheduler` option instead
   * @default false
   */
  immediateCallback?: boolean
  /** @deprecated Please use `scheduler` option instead */
  interval?: number
}
export interface UseMemoryReturn extends Supportable {
  memory: Ref<MemoryInfo | undefined>
}
/**
 * Reactive Memory Info.
 *
 * @see https://vueuse.org/useMemory
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useMemory(options?: UseMemoryOptions): UseMemoryReturn
```

---

<!-- source: references/useMin.md -->
---
category: '@Math'
---

# useMin

Reactive `Math.min`.

## Usage

```ts
import { useMin } from '@vueuse/math'

const array = ref([1, 2, 3, 4])
const min = useMin(array) // Ref<1>
```

```ts
import { useMin } from '@vueuse/math'

const a = ref(1)
const b = ref(3)

const min = useMin(a, b, 2) // Ref<1>
```

## Type Declarations

```ts
export declare function useMin(
  array: MaybeRefOrGetter<MaybeRefOrGetter<number>[]>,
): ComputedRef<number>
export declare function useMin(
  ...args: MaybeRefOrGetter<number>[]
): ComputedRef<number>
```

---

<!-- source: references/useMounted.md -->
---
category: Component
---

# useMounted

Mounted state in ref.

## Usage

```ts
import { useMounted } from '@vueuse/core'

const isMounted = useMounted()
```

Which is essentially a shorthand of:

```ts
const isMounted = ref(false)

onMounted(() => {
  isMounted.value = true
})
```

## Type Declarations

```ts
/**
 * Mounted state in ref.
 *
 * @see https://vueuse.org/useMounted
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useMounted(): ShallowRef<boolean, boolean>
```

---

<!-- source: references/useMouse.md -->
---
category: Sensors
---

# useMouse

Reactive mouse position

## Basic Usage

```ts twoslash
import { useMouse } from '@vueuse/core'

const { x, y, sourceType } = useMouse()
```

Touch is enabled by default. To only detect mouse changes, set `touch` to `false`.
The `dragover` event is used to track mouse position while dragging.

```ts twoslash
import { useMouse } from '@vueuse/core'
// ---cut---
const { x, y } = useMouse({ touch: false })
```

## Custom Extractor

It's also possible to provide a custom extractor function to get the position from the event.

```ts twoslash
import type { UseMouseEventExtractor } from '@vueuse/core'
import { useMouse, useParentElement } from '@vueuse/core'

const parentEl = useParentElement()

const extractor: UseMouseEventExtractor = event => (
  event instanceof MouseEvent
    ? [event.offsetX, event.offsetY]
    : null
)

const { x, y, sourceType } = useMouse({ target: parentEl, type: extractor })
```

## Component Usage

```vue
<template>
  <UseMouse v-slot="{ x, y }">
    x: {{ x }}
    y: {{ y }}
  </UseMouse>
</template>
```

## Type Declarations

```ts
export type UseMouseCoordType = "page" | "client" | "screen" | "movement"
export type UseMouseSourceType = "mouse" | "touch" | null
export type UseMouseEventExtractor = (
  event: MouseEvent | Touch,
) => [x: number, y: number] | null | undefined
export interface UseMouseOptions
  extends ConfigurableWindow, ConfigurableEventFilter {
  /**
   * Mouse position based by page, client, screen, or relative to previous position
   *
   * @default 'page'
   */
  type?: UseMouseCoordType | UseMouseEventExtractor
  /**
   * Listen events on `target` element
   *
   * @default 'Window'
   */
  target?: MaybeRefOrGetter<Window | EventTarget | null | undefined>
  /**
   * Listen to `touchmove` events
   *
   * @default true
   */
  touch?: boolean
  /**
   * Listen to `scroll` events on window, only effective on type `page`
   *
   * @default true
   */
  scroll?: boolean
  /**
   * Reset to initial value when `touchend` event fired
   *
   * @default false
   */
  resetOnTouchEnds?: boolean
  /**
   * Initial values
   */
  initialValue?: Position
}
export interface UseMouseReturn {
  x: ShallowRef<number>
  y: ShallowRef<number>
  sourceType: ShallowRef<UseMouseSourceType>
}
/**
 * Reactive mouse position.
 *
 * @see https://vueuse.org/useMouse
 * @param options
 */
export declare function useMouse(options?: UseMouseOptions): UseMouseReturn
```

---

<!-- source: references/useMouseInElement.md -->
---
category: Elements
---

# useMouseInElement

Reactive mouse position related to an element

## Usage

```vue
<script setup lang="ts">
import { useMouseInElement } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const target = useTemplateRef('target')

const { x, y, isOutside } = useMouseInElement(target)
</script>

<template>
  <div ref="target">
    <h1>Hello world</h1>
  </div>
</template>
```

## Component Usage

```vue
<template>
  <UseMouseInElement v-slot="{ elementX, elementY, isOutside }">
    x: {{ elementX }}
    y: {{ elementY }}
    Is Outside: {{ isOutside }}
  </UseMouseInElement>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vMouseInElement } from '@vueuse/components'
import { UseMouseSourceType } from '@vueuse/core'

interface MouseInElementType {
  x: number
  y: number
  sourceType: UseMouseSourceType
  elementX: number
  elementY: number
  elementPositionX: number
  elementPositionY: number
  elementHeight: number
  elementWidth: number
  isOutside: boolean
}

const options = {
  handleOutside: true
}
function onMouseInElement({ x, y, sourceType, elementX, elementY, elementPositionX, elementPositionY, elementHeight, elementWidth, isOutside }: MouseInElementType) {
  console.log(x, y, sourceType, elementX, elementY, elementPositionX, elementPositionY, elementHeight, elementWidth, isOutside)
}
</script>

<template>
  <textarea v-mouse-in-element="onMouseInElement" />
  <!-- with options -->
  <textarea v-mouse-in-element="[onMouseInElement, options]" />
</template>
```

## Type Declarations

```ts
export interface MouseInElementOptions extends UseMouseOptions {
  /**
   * Whether to handle mouse events when the cursor is outside the target element.
   * When enabled, mouse position will continue to be tracked even when outside the element bounds.
   *
   * @default true
   */
  handleOutside?: boolean
  /**
   * Listen to window resize event
   *
   * @default true
   */
  windowScroll?: boolean
  /**
   * Listen to window scroll event
   *
   * @default true
   */
  windowResize?: boolean
}
export interface UseMouseInElementReturn extends UseMouseReturn {
  elementX: ShallowRef<number>
  elementY: ShallowRef<number>
  elementPositionX: ShallowRef<number>
  elementPositionY: ShallowRef<number>
  elementHeight: ShallowRef<number>
  elementWidth: ShallowRef<number>
  isOutside: ShallowRef<boolean>
  stop: () => void
}
/**
 * Reactive mouse position related to an element.
 *
 * @see https://vueuse.org/useMouseInElement
 * @param target
 * @param options
 */
export declare function useMouseInElement(
  target?: MaybeElementRef,
  options?: MouseInElementOptions,
): {
  x: ShallowRef<number>
  y: ShallowRef<number>
  sourceType: ShallowRef<UseMouseSourceType>
  elementX: ShallowRef<number, number>
  elementY: ShallowRef<number, number>
  elementPositionX: ShallowRef<number, number>
  elementPositionY: ShallowRef<number, number>
  elementHeight: ShallowRef<number, number>
  elementWidth: ShallowRef<number, number>
  isOutside: ShallowRef<boolean, boolean>
  stop: () => void
}
```

---

<!-- source: references/useMousePressed.md -->
---
category: Sensors
---

# useMousePressed

Reactive mouse pressing state. Triggered by `mousedown` `touchstart` on target element and released by `mouseup` `mouseleave` `touchend` `touchcancel` on window.

## Basic Usage

```ts
import { useMousePressed } from '@vueuse/core'

const { pressed } = useMousePressed()
```

Touching is enabled by default. To make it only detects mouse changes, set `touch` to `false`

```ts
import { useMousePressed } from '@vueuse/core'
// ---cut---
const { pressed } = useMousePressed({ touch: false })
```

To only capture `mousedown` and `touchstart` on specific element, you can specify `target` by passing a ref of the element.

```vue
<script setup lang="ts">
import { useMousePressed } from '@vueuse/core'
// ---cut---
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')

const { pressed } = useMousePressed({ target: el })
</script>

<template>
  <div ref="el">
    Only clicking on this element will trigger the update.
  </div>
</template>
```

## Component Usage

```vue
<template>
  <UseMousePressed v-slot="{ pressed }">
    Is Pressed: {{ pressed }}
  </UseMousePressed>
</template>
```

## Type Declarations

```ts
export interface UseMousePressedOptions extends ConfigurableWindow {
  /**
   * Listen to `touchstart` `touchend` events
   *
   * @default true
   */
  touch?: boolean
  /**
   * Listen to `dragstart` `drop` and `dragend` events
   *
   * @default true
   */
  drag?: boolean
  /**
   * Add event listeners with the `capture` option set to `true`
   * (see [MDN](https://developer.mozilla.org/en-US/docs/Web/API/EventTarget/addEventListener#capture))
   *
   * @default false
   */
  capture?: boolean
  /**
   * Initial values
   *
   * @default false
   */
  initialValue?: boolean
  /**
   * Element target to be capture the click
   */
  target?: MaybeComputedElementRef
  /**
   * Callback to be called when the mouse is pressed
   *
   * @param event
   */
  onPressed?: (event: MouseEvent | TouchEvent | DragEvent) => void
  /**
   * Callback to be called when the mouse is released
   *
   * @param event
   */
  onReleased?: (event: MouseEvent | TouchEvent | DragEvent) => void
}
/** @deprecated use {@link UseMousePressedOptions} instead */
export type MousePressedOptions = UseMousePressedOptions
export interface UseMousePressedReturn {
  pressed: ShallowRef<boolean>
  sourceType: ShallowRef<UseMouseSourceType>
}
/**
 * Reactive mouse pressing state.
 *
 * @see https://vueuse.org/useMousePressed
 * @param options
 */
export declare function useMousePressed(
  options?: UseMousePressedOptions,
): UseMousePressedReturn
```

---

<!-- source: references/useMutationObserver.md -->
---
category: Elements
---

# useMutationObserver

Watch for changes being made to the DOM tree. [MutationObserver MDN](https://developer.mozilla.org/en-US/docs/Web/API/MutationObserver)

## Usage

```vue
<script setup lang="ts">
import { useMutationObserver } from '@vueuse/core'
import { ref, useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const messages = ref([])

useMutationObserver(el, (mutations) => {
  if (mutations[0])
    messages.value.push(mutations[0].attributeName)
}, {
  attributes: true,
})
</script>

<template>
  <div ref="el">
    Hello VueUse
  </div>
</template>
```

## Type Declarations

```ts
export interface UseMutationObserverOptions
  extends MutationObserverInit, ConfigurableWindow {}
export interface UseMutationObserverReturn extends Supportable {
  stop: () => void
  takeRecords: () => MutationRecord[] | undefined
}
/**
 * Watch for changes being made to the DOM tree.
 *
 * @see https://vueuse.org/useMutationObserver
 * @see https://developer.mozilla.org/en-US/docs/Web/API/MutationObserver MutationObserver MDN
 * @param target
 * @param callback
 * @param options
 */
export declare function useMutationObserver(
  target:
    | MaybeComputedElementRef
    | MaybeComputedElementRef[]
    | MaybeRefOrGetter<MaybeElement[]>,
  callback: MutationCallback,
  options?: UseMutationObserverOptions,
): UseMutationObserverReturn
```

---

<!-- source: references/useNProgress.md -->
---
category: '@Integrations'
---

# useNProgress

Reactive wrapper for [`nprogress`](https://github.com/rstacruz/nprogress).

## Install

```bash
npm i nprogress@^0
```

## Usage

```ts {6}
import { useNProgress } from '@vueuse/integrations/useNProgress'

const { isLoading } = useNProgress()

function toggle() {
  isLoading.value = !isLoading.value
}
```

### Passing a progress percentage

You can pass a percentage to indicate where the bar should start from.

```ts {3}
import { useNProgress } from '@vueuse/integrations/useNProgress'

const { progress } = useNProgress(0.5)

function done() {
  progress.value = 1.0
}
```

> To change the progress percentage, set `progress.value = n`, where n is a number between 0..1.

### Customization

Just edit [nprogress.css](https://github.com/rstacruz/nprogress/blob/master/nprogress.css) to your liking. Tip: you probably only want to find and replace occurrences of #29d.

You can [configure](https://github.com/rstacruz/nprogress#configuration) it by passing an object as a second parameter.

```ts {4}
import { useNProgress } from '@vueuse/integrations/useNProgress'

useNProgress(null, {
  minimum: 0.1,
  // ...
})
```

## Type Declarations

```ts
export type UseNProgressOptions = Partial<NProgressOptions>
export interface UseNProgressReturn {
  isLoading: WritableComputedRef<boolean, boolean>
  progress: Ref<number | null | undefined>
  start: () => NProgress
  done: (force?: boolean) => NProgress
  remove: () => void
}
/**
 * Reactive progress bar.
 *
 * @see https://vueuse.org/useNProgress
 */
export declare function useNProgress(
  currentProgress?: MaybeRefOrGetter<number | null | undefined>,
  options?: UseNProgressOptions,
): UseNProgressReturn
```

---

<!-- source: references/useNavigatorLanguage.md -->
---
category: Sensors
---

# useNavigatorLanguage

Reactive [navigator.language](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/language).

## Usage

```ts
import { useNavigatorLanguage } from '@vueuse/core'

const { language } = useNavigatorLanguage()

watch(language, () => {
  // Listen to the value changing
})
```

## Type Declarations

```ts
export interface NavigatorLanguageState extends Supportable {
  /**
   *
   * ISO 639-1 standard Language Code
   *
   * @info The detected user agent language preference as a language tag
   * (which is sometimes referred to as a "locale identifier").
   * This consists of a 2-3 letter base language tag that indicates a
   * language, optionally followed by additional subtags separated by
   * '-'. The most common extra information is the country or region
   * variant (like 'en-US' or 'fr-CA').
   *
   *
   * @see https://www.iso.org/iso-639-language-codes.html
   * @see https://www.loc.gov/standards/iso639-2/php/code_list.php
   *
   */
  language: ShallowRef<string | undefined>
}
export interface UseNavigatorLanguageOptions extends ConfigurableWindow {}
export type UseNavigatorLanguageReturn = Readonly<NavigatorLanguageState>
/**
 *
 * Reactive useNavigatorLanguage
 *
 * Detects the currently selected user language and returns a reactive language
 * @see https://vueuse.org/useNavigatorLanguage
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useNavigatorLanguage(
  options?: UseNavigatorLanguageOptions,
): UseNavigatorLanguageReturn
```

---

<!-- source: references/useNetwork.md -->
---
category: Sensors
---

# useNetwork

Reactive [Network status](https://developer.mozilla.org/en-US/docs/Web/API/Network_Information_API). The Network Information API provides information about the system's connection in terms of general connection type (e.g., 'wifi', 'cellular', etc.). This can be used to select high definition content or low definition content based on the user's connection. The entire API consists of the addition of the NetworkInformation interface and a single property to the Navigator interface: Navigator.connection.

## Usage

```ts
import { useNetwork } from '@vueuse/core'

const { isOnline, offlineAt, downlink, downlinkMax, effectiveType, saveData, type } = useNetwork()

console.log(isOnline.value)
```

To use as an object, wrap it with `reactive()`

```ts
import { useNetwork } from '@vueuse/core'
// ---cut---
import { reactive } from 'vue'

const network = reactive(useNetwork())

console.log(network.isOnline)
```

## Component Usage

```vue
<template>
  <UseNetwork v-slot="{ isOnline, type }">
    Is Online: {{ isOnline }}
    Type: {{ type }}
  </UseNetwork>
</template>
```

## Type Declarations

```ts
export interface UseNetworkOptions extends ConfigurableWindow {}
export type NetworkType =
  | "bluetooth"
  | "cellular"
  | "ethernet"
  | "none"
  | "wifi"
  | "wimax"
  | "other"
  | "unknown"
export type NetworkEffectiveType = "slow-2g" | "2g" | "3g" | "4g" | undefined
export interface NetworkState extends Supportable {
  /**
   * If the user is currently connected.
   */
  isOnline: Readonly<ShallowRef<boolean>>
  /**
   * The time since the user was last connected.
   */
  offlineAt: Readonly<ShallowRef<number | undefined>>
  /**
   * At this time, if the user is offline and reconnects
   */
  onlineAt: Readonly<ShallowRef<number | undefined>>
  /**
   * The download speed in Mbps.
   */
  downlink: Readonly<ShallowRef<number | undefined>>
  /**
   * The max reachable download speed in Mbps.
   */
  downlinkMax: Readonly<ShallowRef<number | undefined>>
  /**
   * The detected effective speed type.
   */
  effectiveType: Readonly<ShallowRef<NetworkEffectiveType | undefined>>
  /**
   * The estimated effective round-trip time of the current connection.
   */
  rtt: Readonly<ShallowRef<number | undefined>>
  /**
   * If the user activated data saver mode.
   */
  saveData: Readonly<ShallowRef<boolean | undefined>>
  /**
   * The detected connection/network type.
   */
  type: Readonly<ShallowRef<NetworkType>>
}
export type UseNetworkReturn = Readonly<NetworkState>
/**
 * Reactive Network status.
 *
 * @see https://vueuse.org/useNetwork
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useNetwork(
  options?: UseNetworkOptions,
): UseNetworkReturn
```

---

<!-- source: references/useNow.md -->
---
category: Animation
---

# useNow

Reactive current Date instance.

## Usage

```ts
import { useNow } from '@vueuse/core'

const now = useNow()
```

```ts
import { useNow } from '@vueuse/core'
// ---cut---
const { now, pause, resume } = useNow({ controls: true })
```

## Component Usage

```vue
<template>
  <UseNow v-slot="{ now, pause, resume }">
    Now: {{ now }}
    <button @click="pause()">
      Pause
    </button>
    <button @click="resume()">
      Resume
    </button>
  </UseNow>
</template>
```

## Type Declarations

```ts
export interface UseNowOptions<
  Controls extends boolean,
> extends ConfigurableScheduler {
  /**
   * Expose more controls
   *
   * @default false
   */
  controls?: Controls
  /**
   * Start the clock immediately
   *
   * @deprecated Please use `scheduler` option instead
   * @default true
   */
  immediate?: boolean
  /**
   * Update interval in milliseconds, or use requestAnimationFrame
   *
   * @deprecated Please use `scheduler` option instead
   * @default requestAnimationFrame
   */
  interval?: "requestAnimationFrame" | number
}
export type UseNowReturn<Controls extends boolean> = Controls extends true
  ? {
      now: Ref<Date>
    } & Pausable
  : Ref<Date>
/**
 * Reactive current Date instance.
 *
 * @see https://vueuse.org/useNow
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useNow(options?: UseNowOptions<false>): Ref<Date>
export declare function useNow(options: UseNowOptions<true>): {
  now: Ref<Date>
} & Pausable
```

---

<!-- source: references/useObjectUrl.md -->
---
category: Browser
---

# useObjectUrl

Reactive URL representing an object.

Creates an URL for the provided `File`, `Blob`, or `MediaSource` via [URL.createObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL) and automatically releases the URL via [URL.revokeObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/revokeObjectURL) when the source changes or the component is unmounted.

## Usage

```vue
<script setup lang="ts">
import { useObjectUrl } from '@vueuse/core'
import { shallowRef } from 'vue'

const file = shallowRef()
const url = useObjectUrl(file)

function onFileChange(event) {
  file.value = event.target.files[0]
}
</script>

<template>
  <input type="file" @change="onFileChange">

  <a :href="url">Open file</a>
</template>
```

## Component Usage

```vue
<template>
  <UseObjectUrl v-slot="url" :object="file">
    <a :href="url">Open file</a>
  </UseObjectUrl>
</template>
```

## Type Declarations

```ts
/**
 * Reactive URL representing an object.
 *
 * @see https://vueuse.org/useObjectUrl
 * @param object
 */
export declare function useObjectUrl(
  object: MaybeRefOrGetter<Blob | MediaSource | null | undefined>,
): Readonly<Ref<string | undefined, string | undefined>>
```

---

<!-- source: references/useObservable.md -->
---
category: '@RxJS'
---

# useObservable

Use an RxJS [`Observable`](https://rxjs.dev/guide/observable), return a `ref`, and automatically unsubscribe from it when the component is unmounted.

## Usage

<!-- TODO: import rxjs error if enable twoslash -->

```ts no-twoslash
import { useObservable } from '@vueuse/rxjs'
import { interval } from 'rxjs'
import { mapTo, scan, startWith } from 'rxjs/operators'

// setup()
const count = useObservable(
  interval(1000).pipe(
    mapTo(1),
    startWith(0),
    scan((total, next) => next + total),
  ),
)
```

### Initial Value

You can provide an initial value that will be used before the Observable emits its first value:

```ts no-twoslash
import { useObservable } from '@vueuse/rxjs'
import { interval } from 'rxjs'

const count = useObservable(
  interval(1000),
  { initialValue: 0 },
)
// count.value is 0 until the first emission
```

### Error Handling

If you want to add custom error handling to an `Observable` that might error, you can supply an optional `onError` configuration. Without this, RxJS will treat any error in the supplied `Observable` as an "unhandled error" and it will be thrown in a new call stack and reported to `window.onerror` (or `process.on('error')` if you happen to be in Node).

```ts no-twoslash
import { useObservable } from '@vueuse/rxjs'
import { interval } from 'rxjs'
import { map } from 'rxjs/operators'

// setup()
const count = useObservable(
  interval(1000).pipe(
    map((n) => {
      if (n === 10)
        throw new Error('oops')

      return n + n
    }),
  ),
  {
    onError: (err) => {
      console.log(err.message) // "oops"
    },
  },
)
```

### Options

| Option         | Type                 | Description                              |
| -------------- | -------------------- | ---------------------------------------- |
| `initialValue` | `T`                  | Value to use before the Observable emits |
| `onError`      | `(err: any) => void` | Error handler for Observable errors      |

## Type Declarations

```ts
export interface UseObservableOptions<I> {
  onError?: (err: any) => void
  /**
   * The value that should be set if the observable has not emitted.
   */
  initialValue?: I | undefined
}
export declare function useObservable<H, I = undefined>(
  observable: Observable<H>,
  options?: UseObservableOptions<I | undefined>,
): Readonly<Ref<H | I>>
```

---

<!-- source: references/useOffsetPagination.md -->
---
category: Utilities
---

# useOffsetPagination

Reactive offset pagination.

## Usage

```ts
import { useOffsetPagination } from '@vueuse/core'

function fetchData({ currentPage, currentPageSize }: { currentPage: number, currentPageSize: number }) {
  fetch(currentPage, currentPageSize).then((responseData) => {
    data.value = responseData
  })
}

const {
  currentPage,
  currentPageSize,
  pageCount,
  isFirstPage,
  isLastPage,
  prev,
  next,
} = useOffsetPagination({
  total: database.value.length,
  page: 1,
  pageSize: 10,
  onPageChange: fetchData,
  onPageSizeChange: fetchData,
})
```

## Component Usage

```vue
<template>
  <UseOffsetPagination
    v-slot="{
      currentPage,
      currentPageSize,
      next,
      prev,
      pageCount,
      isFirstPage,
      isLastPage,
    }"
    :total="database.length"
    @page-change="fetchData"
    @page-size-change="fetchData"
  >
    <div class="gap-x-4 gap-y-2 grid-cols-2 inline-grid items-center">
      <div opacity="50">
        total:
      </div>
      <div>{{ database.length }}</div>
      <div opacity="50">
        pageCount:
      </div>
      <div>{{ pageCount }}</div>
      <div opacity="50">
        currentPageSize:
      </div>
      <div>{{ currentPageSize }}</div>
      <div opacity="50">
        currentPage:
      </div>
      <div>{{ currentPage }}</div>
      <div opacity="50">
        isFirstPage:
      </div>
      <div>{{ isFirstPage }}</div>
      <div opacity="50">
        isLastPage:
      </div>
      <div>{{ isLastPage }}</div>
    </div>
    <div>
      <button :disabled="isFirstPage" @click="prev">
        prev
      </button>
      <button :disabled="isLastPage" @click="next">
        next
      </button>
    </div>
  </UseOffsetPagination>
</template>
```

Component event supported props event callback and event listener.

event listener:

```vue
<template>
  <UseOffsetPagination
    v-slot="{
      currentPage,
      currentPageSize,
      next,
      prev,
      pageCount,
      isFirstPage,
      isLastPage,
    }"
    :total="database.length"
    @page-change="fetchData"
    @page-size-change="fetchData"
    @page-count-change="onPageCountChange"
  >
    <!-- your code -->
  </UseOffsetPagination>
</template>
```

or props event callback:

```vue
<template>
  <UseOffsetPagination
    v-slot="{
      currentPage,
      currentPageSize,
      next,
      prev,
      pageCount,
      isFirstPage,
      isLastPage,
    }"
    :total="database.length"
    :on-page-change="fetchData"
    :on-page-size-change="fetchData"
    :on-page-count-change="onPageCountChange"
  >
    <!-- your code -->
  </UseOffsetPagination>
</template>
```

## Type Declarations

```ts
export interface UseOffsetPaginationOptions {
  /**
   * Total number of items.
   */
  total?: MaybeRefOrGetter<number>
  /**
   * The number of items to display per page.
   * @default 10
   */
  pageSize?: MaybeRefOrGetter<number>
  /**
   * The current page number.
   * @default 1
   */
  page?: MaybeRef<number>
  /**
   * Callback when the `page` change.
   */
  onPageChange?: (
    returnValue: UnwrapNestedRefs<UseOffsetPaginationReturn>,
  ) => unknown
  /**
   * Callback when the `pageSize` change.
   */
  onPageSizeChange?: (
    returnValue: UnwrapNestedRefs<UseOffsetPaginationReturn>,
  ) => unknown
  /**
   * Callback when the `pageCount` change.
   */
  onPageCountChange?: (
    returnValue: UnwrapNestedRefs<UseOffsetPaginationReturn>,
  ) => unknown
}
export interface UseOffsetPaginationReturn {
  currentPage: Ref<number>
  currentPageSize: Ref<number>
  pageCount: ComputedRef<number>
  isFirstPage: ComputedRef<boolean>
  isLastPage: ComputedRef<boolean>
  prev: () => void
  next: () => void
}
export type UseOffsetPaginationInfinityPageReturn = Omit<
  UseOffsetPaginationReturn,
  "isLastPage"
>
export declare function useOffsetPagination(
  options: Omit<UseOffsetPaginationOptions, "total">,
): UseOffsetPaginationInfinityPageReturn
export declare function useOffsetPagination(
  options: UseOffsetPaginationOptions,
): UseOffsetPaginationReturn
```

---

<!-- source: references/useOnline.md -->
---
category: Sensors
---

# useOnline

Reactive online state. A wrapper of `useNetwork`.

## Usage

```ts
import { useOnline } from '@vueuse/core'

const online = useOnline()
```

## Component Usage

```vue
<template>
  <UseOnline v-slot="{ isOnline }">
    Is Online: {{ isOnline }}
  </UseOnline>
</template>
```

## Type Declarations

```ts
/**
 * Reactive online state.
 *
 * @see https://vueuse.org/useOnline
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useOnline(
  options?: ConfigurableWindow,
): Readonly<ShallowRef<boolean>>
```

---

<!-- source: references/usePageLeave.md -->
---
category: Sensors
---

# usePageLeave

Reactive state to show whether the mouse leaves the page.

## Usage

```ts
import { usePageLeave } from '@vueuse/core'

const isLeft = usePageLeave()
```

## Component Usage

```vue
<template>
  <UsePageLeave v-slot="{ isLeft }">
    Has Left Page: {{ isLeft }}
  </UsePageLeave>
</template>
```

## Type Declarations

```ts
export interface UsePageLeaveOptions extends ConfigurableWindow {}
export type UsePageLeaveReturn = ShallowRef<boolean>
/**
 * Reactive state to show whether mouse leaves the page.
 *
 * @see https://vueuse.org/usePageLeave
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePageLeave(
  options?: UsePageLeaveOptions,
): UsePageLeaveReturn
```

---

<!-- source: references/useParallax.md -->
---
category: Sensors
---

# useParallax

Create parallax effect easily. It uses `useDeviceOrientation` and fallback to `useMouse` if orientation is not supported.

## Usage

```vue
<script setup lang="ts">
import { useParallax } from '@vueuse/core'

const container = ref(null)
const { tilt, roll, source } = useParallax(container)
</script>

<template>
  <div ref="container" />
</template>
```

## Type Declarations

```ts
export interface UseParallaxOptions extends ConfigurableWindow {
  deviceOrientationTiltAdjust?: (i: number) => number
  deviceOrientationRollAdjust?: (i: number) => number
  mouseTiltAdjust?: (i: number) => number
  mouseRollAdjust?: (i: number) => number
}
export interface UseParallaxReturn {
  /**
   * Roll value. Scaled to `-0.5 ~ 0.5`
   */
  roll: ComputedRef<number>
  /**
   * Tilt value. Scaled to `-0.5 ~ 0.5`
   */
  tilt: ComputedRef<number>
  /**
   * Sensor source, can be `mouse` or `deviceOrientation`
   */
  source: ComputedRef<"deviceOrientation" | "mouse">
}
/**
 * Create parallax effect easily. It uses `useDeviceOrientation` and fallback to `useMouse`
 * if orientation is not supported.
 *
 * @param target
 * @param options
 */
export declare function useParallax(
  target: MaybeElementRef,
  options?: UseParallaxOptions,
): UseParallaxReturn
```

---

<!-- source: references/useParentElement.md -->
---
category: Elements
---

# useParentElement

Get parent element of the given element

## Usage

When no argument is passed, it will return the parent element of the current component.

```vue
<script setup lang="ts">
import { useParentElement } from '@vueuse/core'

const parentEl = useParentElement()

onMounted(() => {
  console.log(parentEl.value)
})
</script>
```

It can also accept a `ref` as the first argument.

```vue
<script setup lang="ts">
import { useParentElement } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const tooltip = useTemplateRef('tooltip')

const tooltipWrapper = useParentElement(tooltip)

onMounted(() => {
  console.log(tooltipWrapper.value)
})
</script>

<template>
  <div>
    <p ref="tooltip" />
  </div>
</template>
```

## Type Declarations

```ts
export declare function useParentElement(
  element?: MaybeRefOrGetter<HTMLElement | SVGElement | null | undefined>,
): Readonly<ShallowRef<HTMLElement | SVGElement | null | undefined>>
```

---

<!-- source: references/usePerformanceObserver.md -->
---
category: Browser
---

# usePerformanceObserver

Observe performance metrics.

## Usage

```ts
import { usePerformanceObserver } from '@vueuse/core'

const entrys = ref<PerformanceEntry[]>([])
usePerformanceObserver({
  entryTypes: ['paint'],
}, (list) => {
  entrys.value = list.getEntries()
})
```

## Type Declarations

```ts
export type UsePerformanceObserverOptions = PerformanceObserverInit &
  ConfigurableWindow & {
    /**
     * Start the observer immediate.
     *
     * @default true
     */
    immediate?: boolean
  }
/**
 * Observe performance metrics.
 *
 * @see https://vueuse.org/usePerformanceObserver
 * @param options
 */
export declare function usePerformanceObserver(
  options: UsePerformanceObserverOptions,
  callback: PerformanceObserverCallback,
): {
  isSupported: UseSupportedReturn
  start: () => void
  stop: () => void
}
```

---

<!-- source: references/usePermission.md -->
---
category: Browser
---

# usePermission

Reactive [Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API). The Permissions API provides the tools to allow developers to implement a better user experience as far as permissions are concerned.

## Usage

```ts
import { usePermission } from '@vueuse/core'

const microphoneAccess = usePermission('microphone')
```

## Type Declarations

```ts
type DescriptorNamePolyfill =
  | "accelerometer"
  | "accessibility-events"
  | "ambient-light-sensor"
  | "background-sync"
  | "camera"
  | "clipboard-read"
  | "clipboard-write"
  | "gyroscope"
  | "magnetometer"
  | "microphone"
  | "notifications"
  | "payment-handler"
  | "persistent-storage"
  | "push"
  | "speaker"
  | "local-fonts"
export type GeneralPermissionDescriptor =
  | PermissionDescriptor
  | {
      name: DescriptorNamePolyfill
    }
export interface UsePermissionOptions<
  Controls extends boolean,
> extends ConfigurableNavigator {
  /**
   * Expose more controls
   *
   * @default false
   */
  controls?: Controls
}
export type UsePermissionReturn = Readonly<
  ShallowRef<PermissionState | undefined>
>
export interface UsePermissionReturnWithControls extends Supportable {
  state: UsePermissionReturn
  query: () => Promise<PermissionStatus | undefined>
}
/**
 * Reactive Permissions API.
 *
 * @see https://vueuse.org/usePermission
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePermission(
  permissionDesc:
    | GeneralPermissionDescriptor
    | GeneralPermissionDescriptor["name"],
  options?: UsePermissionOptions<false>,
): UsePermissionReturn
export declare function usePermission(
  permissionDesc:
    | GeneralPermissionDescriptor
    | GeneralPermissionDescriptor["name"],
  options: UsePermissionOptions<true>,
): UsePermissionReturnWithControls
```

---

<!-- source: references/usePointer.md -->
---
category: Sensors
---

# usePointer

Reactive [pointer state](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events).

## Basic Usage

```ts
import { usePointer } from '@vueuse/core'

const { x, y, pressure, pointerType } = usePointer()
```

## Component Usage

By default, the component will track the pointer on `window`

```vue
<template>
  <UsePointer v-slot="{ x, y }">
    x: {{ x }}
    y: {{ y }}
  </UsePointer>
</template>
```

To track local position in the element, set `target="self"`:

```vue
<template>
  <UsePointer v-slot="{ x, y }" target="self">
    x: {{ x }} y: {{ y }}
  </UsePointer>
</template>
```

## Type Declarations

```ts
export interface UsePointerState extends Position {
  pressure: number
  pointerId: number
  tiltX: number
  tiltY: number
  width: number
  height: number
  twist: number
  pointerType: PointerType | null
}
export interface UsePointerOptions extends ConfigurableWindow {
  /**
   * Pointer types that listen to.
   *
   * @default ['mouse', 'touch', 'pen']
   */
  pointerTypes?: PointerType[]
  /**
   * Initial values
   */
  initialValue?: MaybeRef<Partial<UsePointerState>>
  /**
   * @default window
   */
  target?: MaybeRef<EventTarget | null | undefined> | Document | Window
}
export interface UsePointerReturn {
  pressure: Ref<number>
  pointerId: Ref<number>
  tiltX: Ref<number>
  tiltY: Ref<number>
  width: Ref<number>
  height: Ref<number>
  twist: Ref<number>
  pointerType: Ref<PointerType | null>
  x: Ref<number>
  y: Ref<number>
  isInside: ShallowRef<boolean>
}
/**
 * Reactive pointer state.
 *
 * @see https://vueuse.org/usePointer
 * @param options
 */
export declare function usePointer(
  options?: UsePointerOptions,
): UsePointerReturn
```

---

<!-- source: references/usePointerLock.md -->
---
category: Sensors
---

# usePointerLock

Reactive [pointer lock](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_Lock_API).

## Basic Usage

```ts
import { usePointerLock } from '@vueuse/core'

const {
  isSupported,
  lock,
  unlock,
  element,
  triggerElement
} = usePointerLock()
```

## Component Usage

```vue
<template>
  <UsePointerLock v-slot="{ lock }">
    <canvas />
    <button @click="lock">
      Lock Pointer on Canvas
    </button>
  </UsePointerLock>
</template>
```

## Type Declarations

```ts
export interface UsePointerLockOptions extends ConfigurableDocument {}
export interface UsePointerLockReturn extends Supportable {
  element: ShallowRef<MaybeElement>
  triggerElement: ShallowRef<MaybeElement>
  lock: (e: MaybeElementRef | Event) => Promise<MaybeElement>
  unlock: () => Promise<boolean>
}
/**
 * Reactive pointer lock.
 *
 * @see https://vueuse.org/usePointerLock
 * @param target
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePointerLock(
  target?: MaybeElementRef,
  options?: UsePointerLockOptions,
): UsePointerLockReturn
```

---

<!-- source: references/usePointerSwipe.md -->
---
category: Sensors
---

# usePointerSwipe

Reactive swipe detection based on [PointerEvents](https://developer.mozilla.org/en-US/docs/Web/API/PointerEvent).

## Usage

```vue
<script setup lang="ts">
import { usePointerSwipe } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { isSwiping, direction } = usePointerSwipe(el)
</script>

<template>
  <div ref="el">
    Swipe here
  </div>
</template>
```

## Type Declarations

```ts
export interface UsePointerSwipeOptions {
  /**
   * @default 50
   */
  threshold?: number
  /**
   * Callback on swipe start.
   */
  onSwipeStart?: (e: PointerEvent) => void
  /**
   * Callback on swipe move.
   */
  onSwipe?: (e: PointerEvent) => void
  /**
   * Callback on swipe end.
   */
  onSwipeEnd?: (e: PointerEvent, direction: UseSwipeDirection) => void
  /**
   * Pointer types to listen to.
   *
   * @default ['mouse', 'touch', 'pen']
   */
  pointerTypes?: PointerType[]
  /**
   * Disable text selection on swipe.
   *
   * @default false
   */
  disableTextSelect?: boolean
}
export interface UsePointerSwipeReturn {
  readonly isSwiping: ShallowRef<boolean>
  direction: Readonly<ShallowRef<UseSwipeDirection>>
  readonly posStart: Position
  readonly posEnd: Position
  distanceX: Readonly<ComputedRef<number>>
  distanceY: Readonly<ComputedRef<number>>
  stop: () => void
}
/**
 * Reactive swipe detection based on PointerEvents.
 *
 * @see https://vueuse.org/usePointerSwipe
 * @param target
 * @param options
 */
export declare function usePointerSwipe(
  target: MaybeRefOrGetter<HTMLElement | null | undefined>,
  options?: UsePointerSwipeOptions,
): UsePointerSwipeReturn
```

---

<!-- source: references/usePrecision.md -->
---
category: '@Math'
---

# usePrecision

Reactively set the precision of a number.

## Usage

```ts
import { usePrecision } from '@vueuse/math'

const value = ref(3.1415)
const result = usePrecision(value, 2) // 3.14

const ceilResult = usePrecision(value, 2, {
  math: 'ceil'
}) // 3.15

const floorResult = usePrecision(value, 3, {
  math: 'floor'
}) // 3.141
```

## Type Declarations

```ts
export interface UsePrecisionOptions {
  /**
   * Method to use for rounding
   *
   * @default 'round'
   */
  math?: "floor" | "ceil" | "round"
}
/**
 * Reactively set the precision of a number.
 *
 * @see https://vueuse.org/usePrecision
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePrecision(
  value: MaybeRefOrGetter<number>,
  digits: MaybeRefOrGetter<number>,
  options?: MaybeRefOrGetter<UsePrecisionOptions>,
): ComputedRef<number>
```

---

<!-- source: references/usePreferredColorScheme.md -->
---
category: Browser
---

# usePreferredColorScheme

Reactive [prefers-color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme) media query.

## Usage

```ts
import { usePreferredColorScheme } from '@vueuse/core'

const preferredColor = usePreferredColorScheme()
```

## Component Usage

```vue
<template>
  <UsePreferredColorScheme v-slot="{ colorScheme }">
    Preferred Color Scheme: {{ colorScheme }}
  </UsePreferredColorScheme>
</template>
```

## Type Declarations

```ts
export type ColorSchemeType = "dark" | "light" | "no-preference"
/**
 * Reactive prefers-color-scheme media query.
 *
 * @see https://vueuse.org/usePreferredColorScheme
 * @param [options]
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePreferredColorScheme(
  options?: ConfigurableWindow,
): ComputedRef<ColorSchemeType>
```

---

<!-- source: references/usePreferredContrast.md -->
---
category: Browser
---

# usePreferredContrast

Reactive [prefers-contrast](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-contrast) media query.

## Usage

```ts
import { usePreferredContrast } from '@vueuse/core'

const preferredContrast = usePreferredContrast()
```

## Component Usage

```vue
<template>
  <UsePreferredContrast v-slot="{ contrast }">
    Preferred Contrast: {{ contrast }}
  </UsePreferredContrast>
</template>
```

## Type Declarations

```ts
export type ContrastType = "more" | "less" | "custom" | "no-preference"
/**
 * Reactive prefers-contrast media query.
 *
 * @see https://vueuse.org/usePreferredContrast
 * @param [options]
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePreferredContrast(
  options?: ConfigurableWindow,
): ComputedRef<ContrastType>
```

---

<!-- source: references/usePreferredDark.md -->
---
category: Browser
---

# usePreferredDark

Reactive dark theme preference.

## Usage

```ts
import { usePreferredDark } from '@vueuse/core'

const isDark = usePreferredDark()
```

## Component Usage

```vue
<template>
  <UsePreferredDark v-slot="{ prefersDark }">
    Prefers Dark: {{ prefersDark }}
  </UsePreferredDark>
</template>
```

## Type Declarations

```ts
/**
 * Reactive dark theme preference.
 *
 * @see https://vueuse.org/usePreferredDark
 * @param [options]
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePreferredDark(
  options?: ConfigurableWindow,
): ComputedRef<boolean>
```

---

<!-- source: references/usePreferredLanguages.md -->
---
category: Browser
---

# usePreferredLanguages

Reactive [Navigator Languages](https://developer.mozilla.org/en-US/docs/Web/API/NavigatorLanguage/languages). It provides web developers with information about the user's preferred languages. For example, this may be useful to adjust the language of the user interface based on the user's preferred languages in order to provide better experience.

## Usage

```ts
import { usePreferredLanguages } from '@vueuse/core'

const languages = usePreferredLanguages()
```

## Component Usage

```vue
<template>
  <UsePreferredLanguages v-slot="{ languages }">
    Preferred Languages: {{ languages }}
  </UsePreferredLanguages>
</template>
```

## Type Declarations

```ts
/**
 * Reactive Navigator Languages.
 *
 * @see https://vueuse.org/usePreferredLanguages
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePreferredLanguages(
  options?: ConfigurableWindow,
): ShallowRef<readonly string[]>
```

---

<!-- source: references/usePreferredReducedMotion.md -->
---
category: Browser
---

# usePreferredReducedMotion

Reactive [prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion) media query.

## Usage

```ts
import { usePreferredReducedMotion } from '@vueuse/core'

const preferredMotion = usePreferredReducedMotion()
```

## Component Usage

```vue
<template>
  <UsePreferredReducedMotion v-slot="{ motion }">
    Preferred Reduced Motion: {{ motion }}
  </UsePreferredReducedMotion>
</template>
```

## Type Declarations

```ts
export type ReducedMotionType = "reduce" | "no-preference"
/**
 * Reactive prefers-reduced-motion media query.
 *
 * @see https://vueuse.org/usePreferredReducedMotion
 * @param [options]
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePreferredReducedMotion(
  options?: ConfigurableWindow,
): ComputedRef<ReducedMotionType>
```

---

<!-- source: references/usePreferredReducedTransparency.md -->
---
category: Browser
---

# usePreferredReducedTransparency

Reactive [prefers-reduced-transparency](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency) media query.

## Usage

```ts
import { usePreferredReducedTransparency } from '@vueuse/core'

const preferredTransparency = usePreferredReducedTransparency()
```

## Component Usage

```vue
<template>
  <UsePreferredReducedTransparency v-slot="{ transparency }">
    Preferred Reduced transparency: {{ transparency }}
  </UsePreferredReducedTransparency>
</template>
```

## Type Declarations

```ts
export type ReducedTransparencyType = "reduce" | "no-preference"
/**
 * Reactive prefers-reduced-transparency media query.
 *
 * @see https://vueuse.org/usePreferredReducedTransparency
 * @param [options]
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function usePreferredReducedTransparency(
  options?: ConfigurableWindow,
): ComputedRef<ReducedTransparencyType>
```

---

<!-- source: references/usePrevious.md -->
---
category: Utilities
---

# usePrevious

Holds the previous value of a ref.

## Usage

```ts
import { usePrevious } from '@vueuse/core'
import { shallowRef } from 'vue'

const counter = shallowRef('Hello')
const previous = usePrevious(counter)

console.log(previous.value) // undefined

counter.value = 'World'

console.log(previous.value) // Hello
```

## Type Declarations

```ts
/**
 * Holds the previous value of a ref.
 *
 * @see   {@link https://vueuse.org/usePrevious}
 */
export declare function usePrevious<T>(
  value: MaybeRefOrGetter<T>,
): Readonly<ShallowRef<T | undefined>>
export declare function usePrevious<T>(
  value: MaybeRefOrGetter<T>,
  initialValue: T,
): Readonly<ShallowRef<T>>
```

---

<!-- source: references/useProjection.md -->
---
category: '@Math'
related: createGenericProjection
---

# useProjection

Reactive numeric projection from one domain to another.

## Usage

```ts
import { useProjection } from '@vueuse/math'

const input = ref(0)
const projected = useProjection(input, [0, 10], [0, 100])

input.value = 5 // projected.value === 50
input.value = 10 // projected.value === 100
```

## Type Declarations

```ts
/**
 * Reactive numeric projection from one domain to another.
 *
 * @see https://vueuse.org/useProjection
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useProjection(
  input: MaybeRefOrGetter<number>,
  fromDomain: MaybeRefOrGetter<readonly [number, number]>,
  toDomain: MaybeRefOrGetter<readonly [number, number]>,
  projector?: ProjectorFunction<number, number>,
): ComputedRef<number>
```

---

<!-- source: references/useQRCode.md -->
---
category: '@Integrations'
---

# useQRCode

Wrapper for [`qrcode`](https://github.com/soldair/node-qrcode).

## Install

```bash
npm i qrcode@^1
```

## Usage

```ts
import { useQRCode } from '@vueuse/integrations/useQRCode'

// `qrcode` will be a ref of data URL
const qrcode = useQRCode('text-to-encode')
```

or passing a `ref` to it, the returned data URL ref will change along with the source ref's changes.

```ts
import { useQRCode } from '@vueuse/integrations/useQRCode'
import { shallowRef } from 'vue'

const text = shallowRef('text-to-encode')
const qrcode = useQRCode(text)
```

```html
<input v-model="text" type="text" />
<img :src="qrcode" alt="QR Code" />
```

## Type Declarations

```ts
/**
 * Wrapper for qrcode.
 *
 * @see https://vueuse.org/useQRCode
 * @param text
 * @param options
 */
export declare function useQRCode(
  text: MaybeRefOrGetter<string>,
  options?: QRCode.QRCodeToDataURLOptions,
): ShallowRef<string, string>
```

---

<!-- source: references/useRTDB.md -->
---
category: '@Firebase'
---

# useRTDB

Reactive [Firebase Realtime Database](https://firebase.google.com/docs/database) binding. Making it straightforward to **always keep your local data in sync** with remotes databases.

## Usage

```ts
import { useRTDB } from '@vueuse/firebase/useRTDB'
import { initializeApp } from 'firebase/app'
import { getDatabase } from 'firebase/database'

const app = initializeApp({ /* config */ })
const db = getDatabase(app)

// in setup()
const todos = useRTDB(db.ref('todos'))
```

## Options

| Option         | Type                   | Default         | Description                                               |
| -------------- | ---------------------- | --------------- | --------------------------------------------------------- |
| `autoDispose`  | `boolean`              | `true`          | Automatically unsubscribe when the component is unmounted |
| `errorHandler` | `(err: Error) => void` | `console.error` | Custom error handler for database errors                  |

## Return Value

Returns a `Ref<T | undefined>` that is automatically updated when the database value changes.

## Reusing Database References

You can reuse the db reference by passing `autoDispose: false`

```ts
const todos = useRTDB(db.ref('todos'), { autoDispose: false })
```

or use `createGlobalState` from the core package

```ts twoslash include store
// @filename: store.ts
// ---cut---
// store.ts
import { createGlobalState } from '@vueuse/core'
import { useRTDB } from '@vueuse/firebase/useRTDB'

export const useTodos = createGlobalState(
  () => useRTDB(db.ref('todos')),
)
```

```vue
<!-- app.vue -->
<script setup lang="ts">
// @include: store
// ---cut---
import { useTodos } from './store'

const todos = useTodos()
</script>
```

## Type Declarations

```ts
export interface UseRTDBOptions {
  errorHandler?: (err: Error) => void
  autoDispose?: boolean
}
/**
 * Reactive Firebase Realtime Database binding.
 *
 * @see https://vueuse.org/useRTDB
 */
export declare function useRTDB<T = any>(
  docRef: DatabaseReference,
  options?: UseRTDBOptions,
): Ref<T | undefined, T | undefined>
```

---

<!-- source: references/useRafFn.md -->
---
category: Animation
---

# useRafFn

Call function on every `requestAnimationFrame`. With controls of pausing and resuming.

## Usage

```ts
import { useRafFn } from '@vueuse/core'
import { shallowRef } from 'vue'

const count = shallowRef(0)

const { pause, resume } = useRafFn(() => {
  count.value++
  console.log(count.value)
})
```

## Type Declarations

```ts
export interface UseRafFnCallbackArguments {
  /**
   * Time elapsed between this and the last frame.
   */
  delta: number
  /**
   * Time elapsed since the creation of the web page. See {@link https://developer.mozilla.org/en-US/docs/Web/API/DOMHighResTimeStamp#the_time_origin Time origin}.
   */
  timestamp: DOMHighResTimeStamp
}
export interface UseRafFnOptions extends ConfigurableWindow {
  /**
   * Start the requestAnimationFrame loop immediately on creation
   *
   * @default true
   */
  immediate?: boolean
  /**
   * The maximum frame per second to execute the function.
   * Set to `null` to disable the limit.
   *
   * @default null
   */
  fpsLimit?: MaybeRefOrGetter<number | null>
  /**
   * After the requestAnimationFrame loop executed once, it will be automatically stopped.
   *
   * @default false
   */
  once?: boolean
}
/**
 * Call function on every `requestAnimationFrame`. With controls of pausing and resuming.
 *
 * @see https://vueuse.org/useRafFn
 * @param fn
 * @param options
 */
export declare function useRafFn(
  fn: (args: UseRafFnCallbackArguments) => void,
  options?: UseRafFnOptions,
): Pausable
```

---

<!-- source: references/useRefHistory.md -->
---
category: State
related: useManualRefHistory
---

# useRefHistory

Track the change history of a ref, also provides undo and redo functionality

<CourseLink href="https://vueschool.io/lessons/ref-history-with-vueuse?friend=vueuse">Learn useRefHistory with this FREE video lesson from Vue School!</CourseLink>

## Usage

```ts {5} twoslash include usage
import { useRefHistory } from '@vueuse/core'
import { shallowRef } from 'vue'

const counter = shallowRef(0)
const { history, undo, redo } = useRefHistory(counter)
```

Internally, `watch` is used to trigger a history point when the ref value is modified. This means that history points are triggered asynchronously batching modifications in the same "tick".

```ts
// @include: usage
// ---cut---
counter.value += 1

await nextTick()
console.log(history.value)
/* [
  { snapshot: 1, timestamp: 1601912898062 },
  { snapshot: 0, timestamp: 1601912898061 }
] */
```

You can use `undo` to reset the ref value to the last history point.

```ts
// @include: usage
// ---cut---
console.log(counter.value) // 1
undo()
console.log(counter.value) // 0
```

### Objects / arrays

When working with objects or arrays, since changing their attributes does not change the reference, it will not trigger the committing. To track attribute changes, you would need to pass `deep: true`. It will create clones for each history record.

```ts
import { useRefHistory } from '@vueuse/core'
// ---cut---
const state = ref({
  foo: 1,
  bar: 'bar',
})

const { history, undo, redo } = useRefHistory(state, {
  deep: true,
})

state.value.foo = 2

await nextTick()
console.log(history.value)
/* [
  { snapshot: { foo: 2, bar: 'bar' } },
  { snapshot: { foo: 1, bar: 'bar' } }
] */
```

#### Custom Clone Function

`useRefHistory` only embeds the minimal clone function `x => JSON.parse(JSON.stringify(x))`. To use a full featured or custom clone function, you can set up via the `clone` options.

For example, using [structuredClone](https://developer.mozilla.org/en-US/docs/Web/API/structuredClone):

```ts
import { useRefHistory } from '@vueuse/core'

const refHistory = useRefHistory(target, { clone: structuredClone })
```

Or by using [lodash's `cloneDeep`](https://lodash.com/docs/4.17.15#cloneDeep):

```ts
import { useRefHistory } from '@vueuse/core'
import { cloneDeep } from 'lodash-es'

const refHistory = useRefHistory(target, { clone: cloneDeep })
```

Or a more lightweight [`klona`](https://github.com/lukeed/klona):

```ts
import { useRefHistory } from '@vueuse/core'
import { klona } from 'klona'

const refHistory = useRefHistory(target, { clone: klona })
```

#### Custom Dump and Parse Function

Instead of using the `clone` options, you can pass custom functions to control the serialization and parsing. In case you do not need history values to be objects, this can save an extra clone when undoing. It is also useful in case you want to have the snapshots already stringified to be saved to local storage for example.

```ts
import { useRefHistory } from '@vueuse/core'

const refHistory = useRefHistory(target, {
  dump: JSON.stringify,
  parse: JSON.parse,
})
```

### History Capacity

We will keep all the history by default (unlimited) until you explicitly clear them up, you can set the maximal amount of history to be kept by `capacity` options.

```ts
import { useRefHistory } from '@vueuse/core'
// ---cut---
const refHistory = useRefHistory(target, {
  capacity: 15, // limit to 15 history records
})

refHistory.clear() // explicitly clear all the history
```

### History WatchOptionFlush Timing

From [Vue's documentation](https://vuejs.org/guide/essentials/watchers.html#callback-flush-timing): Vue's reactivity system buffers invalidated effects and flush them asynchronously to avoid unnecessary duplicate invocation when there are many state mutations happening in the same "tick".

In the same way as `watch`, you can modify the flush timing using the `flush` option.

```ts
import { useRefHistory } from '@vueuse/core'
// ---cut---
const refHistory = useRefHistory(target, {
  flush: 'sync', // options 'pre' (default), 'post' and 'sync'
})
```

The default is `'pre'`, to align this composable with the default for Vue's watchers. This also helps to avoid common issues, like several history points generated as part of a multi-step update to a ref value that can break invariants of the app state. You can use `commit()` in case you need to create multiple history points in the same "tick"

```ts
import { useRefHistory } from '@vueuse/core'
// ---cut---
const r = shallowRef(0)
const { history, commit } = useRefHistory(r)

r.value = 1
commit()

r.value = 2
commit()

console.log(history.value)
/* [
  { snapshot: 2 },
  { snapshot: 1 },
  { snapshot: 0 },
] */
```

On the other hand, when using flush `'sync'`, you can use `batch(fn)` to generate a single history point for several sync operations

```ts
import { useRefHistory } from '@vueuse/core'
// ---cut---
const r = ref({ names: [], version: 1 })
const { history, batch } = useRefHistory(r, { flush: 'sync' })

batch(() => {
  r.value.names.push('Lena')
  r.value.version++
})

console.log(history.value)
/* [
  { snapshot: { names: [ 'Lena' ], version: 2 },
  { snapshot: { names: [], version: 1 },
] */
```

If `{ flush: 'sync', deep: true }` is used, `batch` is also useful when doing a mutable `splice` in an array. `splice` can generate up to three atomic operations that will be pushed to the ref history.

```ts
import { useRefHistory } from '@vueuse/core'
// ---cut---
const arr = ref([1, 2, 3])
const { history, batch } = useRefHistory(arr, { deep: true, flush: 'sync' })

batch(() => {
  arr.value.splice(1, 1) // batch ensures only one history point is generated
})
```

Another option is to avoid mutating the original ref value using `arr.value = [...arr.value].splice(1,1)`.

## Recommended Readings

- [History and Persistence](https://patak.dev/vue/history-and-persistence.html) - by [@patak-dev](https://github.com/patak-dev)

## Type Declarations

```ts
export interface UseRefHistoryOptions<Raw, Serialized = Raw>
  extends ConfigurableEventFilter, ConfigurableFlush {
  /**
   * Watch for deep changes, default to false
   *
   * When set to true, it will also create clones for values store in the history
   *
   * @default false
   */
  deep?: boolean
  /**
   * Maximum number of history to be kept. Default to unlimited.
   */
  capacity?: number
  /**
   * Clone when taking a snapshot, shortcut for dump: JSON.parse(JSON.stringify(value)).
   * Default to false
   *
   * @default false
   */
  clone?: boolean | CloneFn<Raw>
  /**
   * Serialize data into the history
   */
  dump?: (v: Raw) => Serialized
  /**
   * Deserialize data from the history
   */
  parse?: (v: Serialized) => Raw
  /**
   * Function to determine if the commit should proceed
   * @param oldValue Previous value
   * @param newValue New value
   * @returns boolean indicating if commit should proceed
   */
  shouldCommit?: (oldValue: Raw | undefined, newValue: Raw) => boolean
}
export interface UseRefHistoryReturn<
  Raw,
  Serialized,
> extends UseManualRefHistoryReturn<Raw, Serialized> {
  /**
   * A ref representing if the tracking is enabled
   */
  isTracking: Ref<boolean>
  /**
   * Pause change tracking
   */
  pause: () => void
  /**
   * Resume change tracking
   *
   * @param [commit] if true, a history record will be create after resuming
   */
  resume: (commit?: boolean) => void
  /**
   * A sugar for auto pause and auto resuming within a function scope
   *
   * @param fn
   */
  batch: (fn: (cancel: Fn) => void) => void
  /**
   * Clear the data and stop the watch
   */
  dispose: () => void
}
/**
 * Track the change history of a ref, also provides undo and redo functionality.
 *
 * @see https://vueuse.org/useRefHistory
 * @param source
 * @param options
 */
export declare function useRefHistory<Raw, Serialized = Raw>(
  source: Ref<Raw>,
  options?: UseRefHistoryOptions<Raw, Serialized>,
): UseRefHistoryReturn<Raw, Serialized>
```

---

<!-- source: references/useResizeObserver.md -->
---
category: Elements
---

# useResizeObserver

Reports changes to the dimensions of an Element's content or the border-box

## Usage

```vue
<script setup lang="ts">
import { useResizeObserver } from '@vueuse/core'
import { ref, useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const text = ref('')

useResizeObserver(el, (entries) => {
  const entry = entries[0]
  const { width, height } = entry.contentRect
  text.value = `width: ${width}, height: ${height}`
})
</script>

<template>
  <div ref="el">
    {{ text }}
  </div>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vResizeObserver } from '@vueuse/components'

const text = ref('')

function onResizeObserver(entries) {
  const [entry] = entries
  const { width, height } = entry.contentRect
  text.value = `width: ${width}, height: ${height}`
}
</script>

<template>
  <div v-resize-observer="onResizeObserver">
    {{ text }}
  </div>
</template>
```

[ResizeObserver MDN](https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver)

## Type Declarations

```ts
/**
 * @deprecated This interface is now available in the DOM lib.
 * Use the global {@link globalThis.ResizeObserverSize} instead.
 */
export interface ResizeObserverSize {
  readonly inlineSize: number
  readonly blockSize: number
}
/**
 * @deprecated This interface is now available in the DOM lib.
 * Use the global {@link globalThis.ResizeObserverEntry} instead.
 */
export interface ResizeObserverEntry {
  readonly target: Element
  readonly contentRect: DOMRectReadOnly
  readonly borderBoxSize: ReadonlyArray<ResizeObserverSize>
  readonly contentBoxSize: ReadonlyArray<ResizeObserverSize>
  readonly devicePixelContentBoxSize: ReadonlyArray<ResizeObserverSize>
}
/**
 * @deprecated This interface is now available in the DOM lib.
 * Use the global {@link globalThis.ResizeObserverCallback} instead.
 */
export type ResizeObserverCallback = (
  entries: ReadonlyArray<ResizeObserverEntry>,
  observer: ResizeObserver,
) => void
export interface UseResizeObserverOptions
  extends ResizeObserverOptions, ConfigurableWindow {}
export interface UseResizeObserverReturn extends Supportable {
  stop: () => void
}
/**
 * Reports changes to the dimensions of an Element's content or the border-box
 *
 * @see https://vueuse.org/useResizeObserver
 * @param target
 * @param callback
 * @param options
 */
export declare function useResizeObserver(
  target:
    | MaybeComputedElementRef
    | MaybeComputedElementRef[]
    | MaybeRefOrGetter<MaybeElement[]>,
  callback: globalThis.ResizeObserverCallback,
  options?: UseResizeObserverOptions,
): UseResizeObserverReturn
```

---

<!-- source: references/useRound.md -->
---
category: '@Math'
---

# useRound

Reactive `Math.round`.

## Usage

```ts
import { useRound } from '@vueuse/math'

const value = ref(20.49)
const result = useRound(value) // 20
```

## Type Declarations

```ts
/**
 * Reactive `Math.round`.
 *
 * @see https://vueuse.org/useRound
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useRound(
  value: MaybeRefOrGetter<number>,
): ComputedRef<number>
```

---

<!-- source: references/useRouteHash.md -->
---
category: '@Router'
---

# useRouteHash

Shorthand for a reactive `route.hash`.

## Usage

```ts
import { useRouteHash } from '@vueuse/router'

const search = useRouteHash()

console.log(search.value) // route.hash
search.value = 'foobar' // router.replace({ hash: 'foobar' })
```

## Type Declarations

```ts
export declare function useRouteHash(
  defaultValue?: MaybeRefOrGetter<RouteHashValueRaw>,
  { mode, route, router }?: ReactiveRouteOptions,
): Ref<RouteHashValueRaw, RouteHashValueRaw>
```

---

<!-- source: references/useRouteParams.md -->
---
category: '@Router'
---

# useRouteParams

Shorthand for a reactive `route.params`.

## Usage

```ts
import { useRouteParams } from '@vueuse/router'

const userId = useRouteParams('userId')

const userId = useRouteParams('userId', '-1') // or with a default value

const userId = useRouteParams('page', '1', { transform: Number }) // or transforming value

console.log(userId.value) // route.params.userId
userId.value = '100' // router.replace({ params: { userId: '100' } })
```

## Type Declarations

```ts
export declare function useRouteParams(
  name: string,
): Ref<null | string | string[]>
export declare function useRouteParams<
  T extends RouteParamValueRaw = RouteParamValueRaw,
  K = T,
>(
  name: string,
  defaultValue?: MaybeRefOrGetter<T>,
  options?: ReactiveRouteOptionsWithTransform<T, K>,
): Ref<K>
```

---

<!-- source: references/useRouteQuery.md -->
---
category: '@Router'
---

# useRouteQuery

Shorthand for a reactive `route.query`. Updates the URL query parameters when the ref changes.

## Usage

```ts
import { useRouteQuery } from '@vueuse/router'

const search = useRouteQuery('search')

const search = useRouteQuery('search', 'foo') // or with a default value

const page = useRouteQuery('page', '1', { transform: Number }) // or transforming value

console.log(search.value) // route.query.search
search.value = 'foobar' // router.replace({ query: { search: 'foobar' } })
```

### Navigation Mode

By default, changes use `router.replace()`. Set `mode: 'push'` to use `router.push()` instead.

```ts
import { useRouteQuery } from '@vueuse/router'

const search = useRouteQuery('search', '', { mode: 'push' })
```

### Bidirectional Transform

You can provide separate `get` and `set` transforms for reading and writing values.

```ts
import { useRouteQuery } from '@vueuse/router'

const filters = useRouteQuery('filters', [], {
  transform: {
    get: v => v ? v.split(',') : [],
    set: v => v.join(','),
  },
})

// Reading: 'a,b,c' -> ['a', 'b', 'c']
// Writing: ['a', 'b', 'c'] -> 'a,b,c'
```

### Default Value Behavior

When the value equals the default value, the query parameter is removed from the URL.

```ts
import { useRouteQuery } from '@vueuse/router'

const page = useRouteQuery('page', '1')

page.value = '2' // URL: ?page=2
page.value = '1' // URL: (no page param, since it equals default)
```

## Type Declarations

```ts
export declare function useRouteQuery(
  name: string,
): Ref<undefined | null | string | string[]>
export declare function useRouteQuery<
  T extends RouteQueryValueRaw = RouteQueryValueRaw,
  K = T,
>(
  name: string,
  defaultValue?: MaybeRefOrGetter<T>,
  options?: ReactiveRouteOptionsWithTransform<T, K>,
): Ref<K>
```

---

<!-- source: references/useSSRWidth.md -->
---
category: Browser
---

# useSSRWidth

Used to set a global viewport width which will be used when rendering SSR components that rely on the viewport width like [`useMediaQuery`](../useMediaQuery/index.md) or [`useBreakpoints`](../useBreakpoints/index.md)

## Usage

```ts
import { provideSSRWidth } from '@vueuse/core'

const app = createApp(App)

provideSSRWidth(500, app)
```

Or in the root component

```vue
<script setup lang="ts">
import { provideSSRWidth } from '@vueuse/core'

provideSSRWidth(500)
</script>
```

To retrieve the provided value if you need it in a subcomponent

```vue
<script setup lang="ts">
import { useSSRWidth } from '@vueuse/core'

const width = useSSRWidth()
</script>
```

## Type Declarations

```ts
export declare function useSSRWidth(): number | undefined
export declare function provideSSRWidth(
  width: number | null,
  app?: App<unknown>,
): void
```

---

<!-- source: references/useScreenOrientation.md -->
---
category: Browser
---

# useScreenOrientation

Reactive [Screen Orientation API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Orientation_API). It provides web developers with information about the user's current screen orientation.

## Usage

```ts
import { useScreenOrientation } from '@vueuse/core'

const {
  isSupported,
  orientation,
  angle,
  lockOrientation,
  unlockOrientation,
} = useScreenOrientation()
```

To lock the orientation, you can pass an [OrientationLockType](https://developer.mozilla.org/en-US/docs/Web/API/ScreenOrientation/type) to the lockOrientation function:

```ts
import { useScreenOrientation } from '@vueuse/core'

const {
  isSupported,
  orientation,
  angle,
  lockOrientation,
  unlockOrientation,
} = useScreenOrientation()

lockOrientation('portrait-primary')
```

and then unlock again, with the following:

```ts
import { useScreenOrientation } from '@vueuse/core'

const { unlockOrientation } = useScreenOrientation()
// ---cut---
unlockOrientation()
```

Accepted orientation types are one of `"landscape-primary"`, `"landscape-secondary"`, `"portrait-primary"`, `"portrait-secondary"`, `"any"`, `"landscape"`, `"natural"` and `"portrait"`.

[Screen Orientation API MDN](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Orientation_API)

## Type Declarations

```ts
export type OrientationType =
  | "portrait-primary"
  | "portrait-secondary"
  | "landscape-primary"
  | "landscape-secondary"
export type OrientationLockType =
  | "any"
  | "natural"
  | "landscape"
  | "portrait"
  | "portrait-primary"
  | "portrait-secondary"
  | "landscape-primary"
  | "landscape-secondary"
export interface ScreenOrientation extends EventTarget {
  lock: (orientation: OrientationLockType) => Promise<void>
  unlock: () => void
  readonly type: OrientationType
  readonly angle: number
  addEventListener: (
    type: "change",
    listener: (this: this, ev: Event) => any,
    useCapture?: boolean,
  ) => void
}
export interface UseScreenOrientationOptions extends ConfigurableWindow {}
export interface UseScreenOrientationReturn extends Supportable {
  orientation: Ref<OrientationType | undefined>
  angle: ShallowRef<number>
  lockOrientation: (type: OrientationLockType) => Promise<void>
  unlockOrientation: () => void
}
/**
 * Reactive screen orientation
 *
 * @see https://vueuse.org/useScreenOrientation
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useScreenOrientation(
  options?: UseScreenOrientationOptions,
): UseScreenOrientationReturn
```

---

<!-- source: references/useScreenSafeArea.md -->
---
category: Browser
---

# useScreenSafeArea

Reactive `env(safe-area-inset-*)`

![image](https://webkit.org/wp-content/uploads/safe-areas-1.png)

## Usage

In order to make the page to be fully rendered in the screen, the additional attribute `viewport-fit=cover` within `viewport` meta tag must be set firstly, the viewport meta tag may look like this:

```html
<meta name="viewport" content="initial-scale=1, viewport-fit=cover" />
```

Then we could use `useScreenSafeArea` in the component as shown below:

```ts
import { useScreenSafeArea } from '@vueuse/core'

const {
  top,
  right,
  bottom,
  left,
} = useScreenSafeArea()
```

For further details, you may refer to this documentation: [Designing Websites for iPhone X](https://webkit.org/blog/7929/designing-websites-for-iphone-x/)

## Component Usage

```vue
<template>
  <UseScreenSafeArea top right bottom left>
    content
  </UseScreenSafeArea>
</template>
```

## Type Declarations

```ts
export interface UseScreenSafeAreaReturn {
  top: ShallowRef<string>
  right: ShallowRef<string>
  bottom: ShallowRef<string>
  left: ShallowRef<string>
  update: () => void
}
/**
 * Reactive `env(safe-area-inset-*)`
 *
 * @see https://vueuse.org/useScreenSafeArea
 */
export declare function useScreenSafeArea(): UseScreenSafeAreaReturn
```

---

<!-- source: references/useScriptTag.md -->
---
category: Browser
---

# useScriptTag

Creates a script tag, with support for automatically unloading (deleting) the script tag on unmount.

If a script tag already exists for the given URL, `useScriptTag()` will not create another script tag, but keep in mind that depending on how you use it, `useScriptTag()` might have already loaded then unloaded that particular JS file from a previous call of `useScriptTag()`.

## Usage

```ts
import { useScriptTag } from '@vueuse/core'

useScriptTag(
  'https://player.twitch.tv/js/embed/v1.js',
  // on script tag loaded.
  (el: HTMLScriptElement) => {
    // do something
  },
)
```

The script will be automatically loaded when the component is mounted and removed when the component is unmounted.

## Configuration

Set `manual: true` to have manual control over the timing to load the script.

```ts
import { useScriptTag } from '@vueuse/core'

const { scriptTag, load, unload } = useScriptTag(
  'https://player.twitch.tv/js/embed/v1.js',
  () => {
    // do something
  },
  { manual: true },
)

// manual controls
await load()
await unload()
```

## Type Declarations

```ts
export interface UseScriptTagOptions extends ConfigurableDocument {
  /**
   * Load the script immediately
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Add `async` attribute to the script tag
   *
   * @default true
   */
  async?: boolean
  /**
   * Script type
   *
   * @default 'text/javascript'
   */
  type?: string
  /**
   * Manual controls the timing of loading and unloading
   *
   * @default false
   */
  manual?: boolean
  crossOrigin?: "anonymous" | "use-credentials"
  referrerPolicy?:
    | "no-referrer"
    | "no-referrer-when-downgrade"
    | "origin"
    | "origin-when-cross-origin"
    | "same-origin"
    | "strict-origin"
    | "strict-origin-when-cross-origin"
    | "unsafe-url"
  noModule?: boolean
  defer?: boolean
  /**
   * Add custom attribute to the script tag
   *
   */
  attrs?: Record<string, string>
  /**
   * Nonce value for CSP (Content Security Policy)
   * @default undefined
   */
  nonce?: string
}
export interface UseScriptTagReturn {
  scriptTag: ShallowRef<HTMLScriptElement | null>
  load: (waitForScriptLoad?: boolean) => Promise<HTMLScriptElement | boolean>
  unload: () => void
}
/**
 * Async script tag loading.
 *
 * @see https://vueuse.org/useScriptTag
 * @param src
 * @param onLoaded
 * @param options
 */
export declare function useScriptTag(
  src: MaybeRefOrGetter<string>,
  onLoaded?: (el: HTMLScriptElement) => void,
  options?: UseScriptTagOptions,
): UseScriptTagReturn
```

---

<!-- source: references/useScroll.md -->
---
category: Sensors
---

# useScroll

Reactive scroll position and state.

## Usage

```vue
<script setup lang="ts">
import { useScroll } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { x, y, isScrolling, arrivedState, directions } = useScroll(el)
</script>

<template>
  <div ref="el" />
</template>
```

### With offsets

```ts
import { useScroll } from '@vueuse/core'
// ---cut---
const { x, y, isScrolling, arrivedState, directions } = useScroll(el, {
  offset: { top: 30, bottom: 30, right: 30, left: 30 },
})
```

### Setting scroll position

Set the `x` and `y` values to make the element scroll to that position.

```vue
<script setup lang="ts">
import { useScroll } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { x, y } = useScroll(el)
</script>

<template>
  <div ref="el" />
  <button @click="x += 10">
    Scroll right 10px
  </button>
  <button @click="y += 10">
    Scroll down 10px
  </button>
</template>
```

### Smooth scrolling

Set `behavior: smooth` to enable smooth scrolling. The `behavior` option defaults to `auto`, which means no smooth scrolling. See the `behavior` option on [`window.scrollTo()`](https://developer.mozilla.org/en-US/docs/Web/API/Window/scrollTo) for more information.

```ts
import { useScroll } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { x, y } = useScroll(el, { behavior: 'smooth' })

// Or as a `ref`:
const smooth = ref(false)
const behavior = computed(() => smooth.value ? 'smooth' : 'auto')
const { x, y } = useScroll(el, { behavior })
```

### Recalculate scroll state

You can call the `measure()` method to manually update the scroll position and `arrivedState` at any time.

This is useful, for example, after dynamic content changes or when you want to recalculate the scroll state outside of scroll events.

```ts
import { useScroll } from '@vueuse/core'
import { nextTick, onMounted, useTemplateRef, watch } from 'vue'

const el = useTemplateRef('el')
const reactiveValue = shallowRef(false)

const { measure } = useScroll(el)

// In a watcher
watch(reactiveValue, () => {
  measure()
})

// Or inside any function
function updateScrollState() {
  // ...some logic
  nextTick(() => {
    measure()
  })
}
```

> [!NOTE]
> it's recommended to call `measure()` inside `nextTick()`, to ensure the DOM is updated first.
> The scroll state is initialized automatically `onMount`.
> You only need to call `measure()` manually if you want to recalculate the state after some dynamic changes.

## Directive Usage

```vue
<script setup lang="ts">
import type { UseScrollReturn } from '@vueuse/core'
import { vScroll } from '@vueuse/components'

const data = ref([1, 2, 3, 4, 5, 6])

function onScroll(state: UseScrollReturn) {
  console.log(state) // {x, y, isScrolling, arrivedState, directions}
}
</script>

<template>
  <div v-scroll="onScroll">
    <div v-for="item in data" :key="item">
      {{ item }}
    </div>
  </div>

  <!-- with options -->
  <div v-scroll="[onScroll, { throttle: 10 }]">
    <div v-for="item in data" :key="item">
      {{ item }}
    </div>
  </div>
</template>
```

## Type Declarations

```ts
export interface UseScrollOptions extends ConfigurableWindow {
  /**
   * Throttle time for scroll event, it’s disabled by default.
   *
   * @default 0
   */
  throttle?: number
  /**
   * The check time when scrolling ends.
   * This configuration will be setting to (throttle + idle) when the `throttle` is configured.
   *
   * @default 200
   */
  idle?: number
  /**
   * Offset arrived states by x pixels
   *
   */
  offset?: {
    left?: number
    right?: number
    top?: number
    bottom?: number
  }
  /**
   * Use MutationObserver to monitor specific DOM changes,
   * such as attribute modifications, child node additions or removals, or subtree changes.
   * @default { mutation: boolean }
   */
  observe?:
    | boolean
    | {
        mutation?: boolean
      }
  /**
   * Trigger it when scrolling.
   *
   */
  onScroll?: (e: Event) => void
  /**
   * Trigger it when scrolling ends.
   *
   */
  onStop?: (e: Event) => void
  /**
   * Listener options for scroll event.
   *
   * @default {capture: false, passive: true}
   */
  eventListenerOptions?: boolean | AddEventListenerOptions
  /**
   * Optionally specify a scroll behavior of `auto` (default, not smooth scrolling) or
   * `smooth` (for smooth scrolling) which takes effect when changing the `x` or `y` refs.
   *
   * @default 'auto'
   */
  behavior?: MaybeRefOrGetter<ScrollBehavior>
  /**
   * On error callback
   *
   * Default log error to `console.error`
   */
  onError?: (error: unknown) => void
}
export interface UseScrollReturn {
  x: WritableComputedRef<number>
  y: WritableComputedRef<number>
  isScrolling: ShallowRef<boolean>
  arrivedState: {
    left: boolean
    right: boolean
    top: boolean
    bottom: boolean
  }
  directions: {
    left: boolean
    right: boolean
    top: boolean
    bottom: boolean
  }
  measure: () => void
}
/**
 * Reactive scroll.
 *
 * @see https://vueuse.org/useScroll
 * @param element
 * @param options
 */
export declare function useScroll(
  element: MaybeRefOrGetter<
    HTMLElement | SVGElement | Window | Document | null | undefined
  >,
  options?: UseScrollOptions,
): UseScrollReturn
```

---

<!-- source: references/useScrollLock.md -->
---
category: Sensors
---

# useScrollLock

Lock scrolling of the element.

## Usage

```vue
<script setup lang="ts">
import { useScrollLock } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const isLocked = useScrollLock(el)

isLocked.value = true // lock
isLocked.value = false // unlock
</script>

<template>
  <div ref="el" />
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vScrollLock } from '@vueuse/components'

const data = ref([1, 2, 3, 4, 5, 6])
const isLocked = ref(false)
const toggleLock = useToggle(isLocked)
</script>

<template>
  <div v-scroll-lock="isLocked">
    <div v-for="item in data" :key="item">
      {{ item }}
    </div>
  </div>
  <button @click="toggleLock()">
    Toggle lock state
  </button>
</template>
```

## Type Declarations

```ts
/**
 * Lock scrolling of the element.
 *
 * @see https://vueuse.org/useScrollLock
 * @param element
 */
export declare function useScrollLock(
  element: MaybeRefOrGetter<
    HTMLElement | SVGElement | Window | Document | null | undefined
  >,
  initialState?: boolean,
): WritableComputedRef<boolean, boolean>
```

---

<!-- source: references/useSessionStorage.md -->
---
category: State
---

# useSessionStorage

Reactive [SessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage).

## Usage

Please refer to `useStorage`.

## Type Declarations

```ts
export declare function useSessionStorage(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<string>,
  options?: UseStorageOptions<string>,
): RemovableRef<string>
export declare function useSessionStorage(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<boolean>,
  options?: UseStorageOptions<boolean>,
): RemovableRef<boolean>
export declare function useSessionStorage(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<number>,
  options?: UseStorageOptions<number>,
): RemovableRef<number>
export declare function useSessionStorage<T>(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<T>,
  options?: UseStorageOptions<T>,
): RemovableRef<T>
export declare function useSessionStorage<T = unknown>(
  key: MaybeRefOrGetter<string>,
  initialValue: MaybeRefOrGetter<null>,
  options?: UseStorageOptions<T>,
): RemovableRef<T>
```

---

<!-- source: references/useShare.md -->
---
category: Browser
---

# useShare

Reactive [Web Share API](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/share). The Browser provides features that can share content in text or file.

> The `share` method has to be called following a user gesture like a button click. It can’t simply be called on page load for example. That’s in place to help prevent abuse.

## Usage

```ts
import { useShare } from '@vueuse/core'

const { share, isSupported } = useShare()

function startShare() {
  share({
    title: 'Hello',
    text: 'Hello my friend!',
    url: location.href,
  })
}
```

### Passing a source ref

You can pass a `ref` to it, changes from the source ref will be reflected to your sharing options.

```ts {6}
import { ref } from 'vue'

const shareOptions = ref<ShareOptions>({ text: 'foo' })
const { share, isSupported } = useShare(shareOptions)

shareOptions.value.text = 'bar'

share()
```

## Type Declarations

```ts
export interface UseShareOptions {
  title?: string
  files?: File[]
  text?: string
  url?: string
}
export interface UseShareReturn extends Supportable {
  share: (overrideOptions?: MaybeRefOrGetter<UseShareOptions>) => Promise<void>
}
/**
 * Reactive Web Share API.
 *
 * @see https://vueuse.org/useShare
 * @param shareOptions
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useShare(
  shareOptions?: MaybeRefOrGetter<UseShareOptions>,
  options?: ConfigurableNavigator,
): UseShareReturn
```

---

<!-- source: references/useSortable.md -->
---
category: '@Integrations'
---

# useSortable

Wrapper for [`sortable`](https://github.com/SortableJS/Sortable).

For more information on what options can be passed, see [`Sortable.options`](https://github.com/SortableJS/Sortable#options) in the `Sortable` documentation.

::: warning
Currently, `useSortable` only implements drag-and-drop sorting for a single list.
:::

## Install

```bash
npm i sortablejs@^1
```

## Usage

### Use template ref

```vue
<script setup lang="ts">
import { useSortable } from '@vueuse/integrations/useSortable'
import { shallowRef, useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const list = shallowRef([{ id: 1, name: 'a' }, { id: 2, name: 'b' }, { id: 3, name: 'c' }])

useSortable(el, list)
</script>

<template>
  <div ref="el">
    <div v-for="item in list" :key="item.id">
      {{ item.name }}
    </div>
  </div>
</template>
```

### Use specifies the selector to operate on

```vue
<script setup lang="ts">
import { useSortable } from '@vueuse/integrations/useSortable'
import { shallowRef, useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const list = shallowRef([{ id: 1, name: 'a' }, { id: 2, name: 'b' }, { id: 3, name: 'c' }])

const animation = 200

const { option } = useSortable(el, list, {
  handle: '.handle',
  // or option set
  // animation
})

// You can use the option method to set and get the option of Sortable
option('animation', animation)
// option('animation') // 200
</script>

<template>
  <div ref="el">
    <div v-for="item in list" :key="item.id">
      <span>{{ item.name }}</span>
      <span class="handle">*</span>
    </div>
  </div>
</template>
```

### Use a selector to get the root element

```vue
<script setup lang="ts">
import { useSortable } from '@vueuse/integrations/useSortable'
import { shallowRef } from 'vue'

const list = shallowRef([{ id: 1, name: 'a' }, { id: 2, name: 'b' }, { id: 3, name: 'c' }])

useSortable('#dv', list)
</script>

<template>
  <div id="dv">
    <div v-for="item in list" :key="item.id">
      <span>{{ item.name }}</span>
    </div>
  </div>
</template>
```

### Return Values

| Property | Description                                                      |
| -------- | ---------------------------------------------------------------- |
| `start`  | Initialize the Sortable instance (called automatically on mount) |
| `stop`   | Destroy the Sortable instance                                    |
| `option` | Get or set Sortable options at runtime                           |

```ts
const { start, stop, option } = useSortable(el, list)

// Stop sorting
stop()

// Start sorting again
start()

// Get/set options
option('animation', 200) // set
const animation = option('animation') // get
```

### Watch Element Changes

Use the `watchElement` option to automatically reinitialize Sortable when the element changes (useful with `v-if`).

```ts
import { useSortable } from '@vueuse/integrations/useSortable'

useSortable(el, list, {
  watchElement: true, // auto-reinitialize when element changes
})
```

### Custom Update Handler

If you want to handle the `onUpdate` yourself, you can pass in `onUpdate` parameters, and we also exposed a function to move the item position.

```ts
import { moveArrayElement, useSortable } from '@vueuse/integrations/useSortable'

useSortable(el, list, {
  onUpdate: (e) => {
    // do something
    moveArrayElement(list, e.oldIndex, e.newIndex, e)
    // nextTick required here as moveArrayElement is executed in a microtask
    // so we need to wait until the next tick until that is finished.
    nextTick(() => {
      /* do something */
    })
  }
})
```

### Helper Functions

The following helper functions are also exported:

| Function                                   | Description                                           |
| ------------------------------------------ | ----------------------------------------------------- |
| `moveArrayElement(list, from, to, event?)` | Move an element in an array from one index to another |
| `insertNodeAt(parent, element, index)`     | Insert a DOM node at a specific index                 |
| `removeNode(node)`                         | Remove a DOM node from its parent                     |

## Type Declarations

```ts
export interface UseSortableReturn {
  /**
   * start sortable instance
   */
  start: () => void
  /**
   * destroy sortable instance
   */
  stop: () => void
  /**
   * Options getter/setter
   * @param name a Sortable.Options property.
   * @param value a value.
   */
  option: (<K extends keyof Sortable.Options>(
    name: K,
    value: Sortable.Options[K],
  ) => void) &
    (<K extends keyof Sortable.Options>(name: K) => Sortable.Options[K])
}
export interface UseSortableOptions extends Options, ConfigurableDocument {
  /**
   * Watch the element reference for changes and automatically reinitialize Sortable
   * when the element changes.
   *
   * When `false` (default), Sortable is only initialized once on mount.
   * You must manually call `start()` if the element reference changes.
   *
   * When `true`, automatically watches the element reference and reinitializes
   * Sortable whenever it changes (e.g., conditional rendering with v-if).
   *
   * @default false
   */
  watchElement?: boolean
}
export declare function useSortable<T>(
  selector: string,
  list: MaybeRef<T[]>,
  options?: UseSortableOptions,
): UseSortableReturn
export declare function useSortable<T>(
  el: MaybeRefOrGetter<MaybeElement>,
  list: MaybeRef<T[]>,
  options?: UseSortableOptions,
): UseSortableReturn
/**
 * Inserts a element into the DOM at a given index.
 * @param parentElement
 * @param element
 * @param {number} index
 * @see https://github.com/Alfred-Skyblue/vue-draggable-plus/blob/a3829222095e1949bf2c9a20979d7b5930e66f14/src/utils/index.ts#L81C1-L94C2
 */
export declare function insertNodeAt(
  parentElement: Element,
  element: Element,
  index: number,
): void
/**
 * Removes a node from the DOM.
 * @param {Node} node
 * @see https://github.com/Alfred-Skyblue/vue-draggable-plus/blob/a3829222095e1949bf2c9a20979d7b5930e66f14/src/utils/index.ts#L96C1-L102C2
 */
export declare function removeNode(node: Node): void
export declare function moveArrayElement<T>(
  list: MaybeRef<T[]>,
  from: number,
  to: number,
  e?: Sortable.SortableEvent | null,
): void
```

---

<!-- source: references/useSorted.md -->
---
category: Array
---

# useSorted

reactive sort array

## Usage

```ts
import { useSorted } from '@vueuse/core'

// general sort
const source = [10, 3, 5, 7, 2, 1, 8, 6, 9, 4]
const sorted = useSorted(source)
console.log(sorted.value) // [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
console.log(source) // [10, 3, 5, 7, 2, 1, 8, 6, 9, 4]

// object sort
const objArr = [{
  name: 'John',
  age: 40,
}, {
  name: 'Jane',
  age: 20,
}, {
  name: 'Joe',
  age: 30,
}, {
  name: 'Jenny',
  age: 22,
}]
const objSorted = useSorted(objArr, (a, b) => a.age - b.age)
```

### dirty mode

dirty mode will change the source array.

```ts
const source = ref([10, 3, 5, 7, 2, 1, 8, 6, 9, 4])
const sorted = useSorted(source, (a, b) => a - b, {
  dirty: true,
})
console.log(source)// output: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
```

## Type Declarations

```ts
export type UseSortedCompareFn<T = any> = (a: T, b: T) => number
export type UseSortedFn<T = any> = (
  arr: T[],
  compareFn: UseSortedCompareFn<T>,
) => T[]
export interface UseSortedOptions<T = any> {
  /**
   * sort algorithm
   */
  sortFn?: UseSortedFn<T>
  /**
   * compare function
   */
  compareFn?: UseSortedCompareFn<T>
  /**
   * change the value of the source array
   * @default false
   */
  dirty?: boolean
}
/**
 * reactive sort array
 *
 * @see https://vueuse.org/useSorted
 */
export declare function useSorted<T = any>(
  source: MaybeRefOrGetter<T[]>,
  compareFn?: UseSortedCompareFn<T>,
): Ref<T[]>
export declare function useSorted<T = any>(
  source: MaybeRefOrGetter<T[]>,
  options?: UseSortedOptions<T>,
): Ref<T[]>
export declare function useSorted<T = any>(
  source: MaybeRefOrGetter<T[]>,
  compareFn?: UseSortedCompareFn<T>,
  options?: Omit<UseSortedOptions<T>, "compareFn">,
): Ref<T[]>
```

---

<!-- source: references/useSpeechRecognition.md -->
---
category: Sensors
---

# useSpeechRecognition

Reactive [SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).

> [Can I use?](https://caniuse.com/mdn-api_speechrecognitionevent)

## Usage

```ts
import { useSpeechRecognition } from '@vueuse/core'

const {
  isSupported,
  isListening,
  isFinal,
  result,
  start,
  stop,
} = useSpeechRecognition()
```

### Options

The following shows the default values of the options, they will be directly passed to [SpeechRecognition API](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).

```ts
import { useSpeechRecognition } from '@vueuse/core'
// ---cut---
useSpeechRecognition({
  lang: 'en-US',
  interimResults: true,
  continuous: true,
})
```

## Type Declarations

```ts
export interface UseSpeechRecognitionOptions extends ConfigurableWindow {
  /**
   * Controls whether continuous results are returned for each recognition, or only a single result.
   *
   * @default true
   */
  continuous?: boolean
  /**
   * Controls whether interim results should be returned (true) or not (false.) Interim results are results that are not yet final
   *
   * @default true
   */
  interimResults?: boolean
  /**
   * Language for SpeechRecognition
   *
   * @default 'en-US'
   */
  lang?: MaybeRefOrGetter<string>
  /**
   * A number representing the maximum returned alternatives for each result.
   *
   * @see https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/maxAlternatives
   * @default 1
   */
  maxAlternatives?: number
}
export interface UseSpeechRecognitionReturn extends Supportable {
  isListening: ShallowRef<boolean>
  isFinal: ShallowRef<boolean>
  recognition: SpeechRecognition | undefined
  result: ShallowRef<string>
  error: ShallowRef<SpeechRecognitionErrorEvent | Error | undefined>
  toggle: (value?: boolean) => void
  start: () => void
  stop: () => void
}
/**
 * Reactive SpeechRecognition.
 *
 * @see https://vueuse.org/useSpeechRecognition
 * @see https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition SpeechRecognition
 * @param options
 */
export declare function useSpeechRecognition(
  options?: UseSpeechRecognitionOptions,
): UseSpeechRecognitionReturn
```

---

<!-- source: references/useSpeechSynthesis.md -->
---
category: Sensors
---

# useSpeechSynthesis

Reactive [SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis).

> [Can I use?](https://caniuse.com/mdn-api_speechsynthesis)

## Usage

```ts
import { useSpeechSynthesis } from '@vueuse/core'

const {
  isSupported,
  isPlaying,
  status,
  voiceInfo,
  utterance,
  error,
  stop,
  toggle,
  speak,
} = useSpeechSynthesis()
```

### Options

The following shows the default values of the options, they will be directly passed to [SpeechSynthesis API](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis).

```ts
import { useSpeechSynthesis } from '@vueuse/core'
// ---cut---
useSpeechSynthesis({
  lang: 'en-US',
  pitch: 1,
  rate: 1,
  volume: 1,
})
```

## Type Declarations

```ts
export type UseSpeechSynthesisStatus = "init" | "play" | "pause" | "end"
export interface UseSpeechSynthesisOptions extends ConfigurableWindow {
  /**
   * Language for SpeechSynthesis
   *
   * @default 'en-US'
   */
  lang?: MaybeRefOrGetter<string>
  /**
   * Gets and sets the pitch at which the utterance will be spoken at.
   *
   * @default 1
   */
  pitch?: MaybeRefOrGetter<SpeechSynthesisUtterance["pitch"]>
  /**
   * Gets and sets the speed at which the utterance will be spoken at.
   *
   * @default 1
   */
  rate?: MaybeRefOrGetter<SpeechSynthesisUtterance["rate"]>
  /**
   * Gets and sets the voice that will be used to speak the utterance.
   */
  voice?: MaybeRef<SpeechSynthesisVoice>
  /**
   * Gets and sets the volume that the utterance will be spoken at.
   *
   * @default 1
   */
  volume?: MaybeRefOrGetter<SpeechSynthesisUtterance["volume"]>
  /**
   * Callback function that is called when the boundary event is triggered.
   */
  onBoundary?: (event: SpeechSynthesisEvent) => void
}
export interface UseSpeechSynthesisReturn extends Supportable {
  isPlaying: ShallowRef<boolean>
  status: ShallowRef<UseSpeechSynthesisStatus>
  utterance: ComputedRef<SpeechSynthesisUtterance>
  error: ShallowRef<SpeechSynthesisErrorEvent | undefined>
  stop: () => void
  toggle: (value?: boolean) => void
  speak: () => void
}
/**
 * Reactive SpeechSynthesis.
 *
 * @see https://vueuse.org/useSpeechSynthesis
 * @see https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis SpeechSynthesis
 */
export declare function useSpeechSynthesis(
  text: MaybeRefOrGetter<string>,
  options?: UseSpeechSynthesisOptions,
): UseSpeechSynthesisReturn
```

---

<!-- source: references/useStepper.md -->
---
category: Utilities
---

# useStepper

Provides helpers for building a multi-step wizard interface.

## Usage

### Steps as array

```ts
import { useStepper } from '@vueuse/core'

const {
  steps,
  stepNames,
  index,
  current,
  next,
  previous,
  isFirst,
  isLast,
  goTo,
  goToNext,
  goToPrevious,
  goBackTo,
  isNext,
  isPrevious,
  isCurrent,
  isBefore,
  isAfter,
} = useStepper([
  'billing-address',
  'terms',
  'payment',
])

// Access the step through `current`
console.log(current.value) // 'billing-address'
```

### Steps as object

```ts
import { useStepper } from '@vueuse/core'

const {
  steps,
  stepNames,
  index,
  current,
  next,
  previous,
  isFirst,
  isLast,
  goTo,
  goToNext,
  goToPrevious,
  goBackTo,
  isNext,
  isPrevious,
  isCurrent,
  isBefore,
  isAfter,
} = useStepper({
  'user-information': {
    title: 'User information',
  },
  'billing-address': {
    title: 'Billing address',
  },
  'terms': {
    title: 'Terms',
  },
  'payment': {
    title: 'Payment',
  },
})

// Access the step object through `current`
console.log(current.value.title) // 'User information'
```

## Type Declarations

```ts
export interface UseStepperReturn<StepName, Steps, Step> {
  /** List of steps. */
  steps: Readonly<Ref<Steps>>
  /** List of step names. */
  stepNames: Readonly<Ref<StepName[]>>
  /** Index of the current step. */
  index: Ref<number>
  /** Current step. */
  current: ComputedRef<Step>
  /** Next step, or undefined if the current step is the last one. */
  next: ComputedRef<StepName | undefined>
  /** Previous step, or undefined if the current step is the first one. */
  previous: ComputedRef<StepName | undefined>
  /** Whether the current step is the first one. */
  isFirst: ComputedRef<boolean>
  /** Whether the current step is the last one. */
  isLast: ComputedRef<boolean>
  /** Get the step at the specified index. */
  at: (index: number) => Step | undefined
  /** Get a step by the specified name. */
  get: (step: StepName) => Step | undefined
  /** Go to the specified step. */
  goTo: (step: StepName) => void
  /** Go to the next step. Does nothing if the current step is the last one. */
  goToNext: () => void
  /** Go to the previous step. Does nothing if the current step is the previous one. */
  goToPrevious: () => void
  /** Go back to the given step, only if the current step is after. */
  goBackTo: (step: StepName) => void
  /** Checks whether the given step is the next step. */
  isNext: (step: StepName) => boolean
  /** Checks whether the given step is the previous step. */
  isPrevious: (step: StepName) => boolean
  /** Checks whether the given step is the current step. */
  isCurrent: (step: StepName) => boolean
  /** Checks if the current step is before the given step. */
  isBefore: (step: StepName) => boolean
  /** Checks if the current step is after the given step. */
  isAfter: (step: StepName) => boolean
}
export declare function useStepper<T extends string | number>(
  steps: MaybeRef<T[]>,
  initialStep?: T,
): UseStepperReturn<T, T[], T>
export declare function useStepper<T extends Record<string, any>>(
  steps: MaybeRef<T>,
  initialStep?: keyof T,
): UseStepperReturn<Exclude<keyof T, symbol>, T, T[keyof T]>
```

---

<!-- source: references/useStorage.md -->
---
category: State
related: useLocalStorage, useSessionStorage, useStorageAsync
---

# useStorage

Create a reactive ref that can be used to access & modify [LocalStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage) or [SessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage).

Uses localStorage by default, other storage sources be specified via third argument.

## Usage

::: tip
When using with Nuxt 3, this function will **NOT** be auto imported in favor of Nitro's built-in [`useStorage()`](https://nitro.unjs.io/guide/storage). Use explicit import if you want to use the function from VueUse.
:::

```ts
import { useStorage } from '@vueuse/core'

// bind object
const state = useStorage('my-store', { hello: 'hi', greeting: 'Hello' })

// bind boolean
const flag = useStorage('my-flag', true) // returns Ref<boolean>

// bind number
const count = useStorage('my-count', 0) // returns Ref<number>

// bind string with SessionStorage
const id = useStorage('my-id', 'some-string-id', sessionStorage) // returns Ref<string>

// delete data from storage
state.value = null
```

## Merge Defaults

By default, `useStorage` will use the value from storage if it is present and ignores the default value. Be aware that when you are adding more properties to the default value, the key might be `undefined` if client's storage does not have that key.

```ts
import { useStorage } from '@vueuse/core'
// ---cut---
localStorage.setItem('my-store', '{"hello": "hello"}')

const state = useStorage('my-store', { hello: 'hi', greeting: 'hello' }, localStorage)

console.log(state.value.greeting) // undefined, since the value is not presented in storage
```

To solve that, you can enable `mergeDefaults` option.

```ts
import { useStorage } from '@vueuse/core'
// ---cut---
localStorage.setItem('my-store', '{"hello": "nihao"}')

const state = useStorage(
  'my-store',
  { hello: 'hi', greeting: 'hello' },
  localStorage,
  { mergeDefaults: true } // <--
)

console.log(state.value.hello) // 'nihao', from storage
console.log(state.value.greeting) // 'hello', from merged default value
```

When setting it to true, it will perform a **shallow merge** for objects. You can pass a function to perform custom merge (e.g. deep merge), for example:

```ts
import { useStorage } from '@vueuse/core'
// ---cut---
const state = useStorage(
  'my-store',
  { hello: 'hi', greeting: 'hello' },
  localStorage,
  { mergeDefaults: (storageValue, defaults) => deepMerge(defaults, storageValue) } // <--
)
```

## Custom Serialization

By default, `useStorage` will smartly use the corresponding serializer based on the data type of provided default value. For example, `JSON.stringify` / `JSON.parse` will be used for objects, `Number.toString` / `parseFloat` for numbers, etc.

You can also provide your own serialization function to `useStorage`:

```ts
import { useStorage } from '@vueuse/core'

useStorage(
  'key',
  {},
  undefined,
  {
    serializer: {
      read: (v: any) => v ? JSON.parse(v) : null,
      write: (v: any) => JSON.stringify(v),
    },
  },
)
```

Please note when you provide `null` as the default value, `useStorage` can't assume the data type from it. In this case, you can provide a custom serializer or reuse the built-in ones explicitly.

```ts
import { StorageSerializers, useStorage } from '@vueuse/core'

const objectLike = useStorage('key', null, undefined, { serializer: StorageSerializers.object })
objectLike.value = { foo: 'bar' }
```

### Built-in Serializers

The following serializers are available via `StorageSerializers`:

| Type      | Description                           |
| --------- | ------------------------------------- |
| `string`  | Plain string                          |
| `number`  | Number (via `parseFloat`)             |
| `boolean` | Boolean                               |
| `object`  | JSON object/array                     |
| `map`     | JavaScript `Map`                      |
| `set`     | JavaScript `Set`                      |
| `date`    | JavaScript `Date` (via `toISOString`) |
| `any`     | Raw string passthrough                |

```ts
import { StorageSerializers, useStorage } from '@vueuse/core'

const myMap = useStorage('my-map', new Map(), undefined, {
  serializer: StorageSerializers.map,
})
```

## Options

```ts
useStorage('key', defaults, storage, {
  // Watch for deep changes in objects/arrays (default: true)
  deep: true,
  // Sync across tabs via storage events (default: true)
  listenToStorageChanges: true,
  // Write default value to storage if not present (default: true)
  writeDefaults: true,
  // Use shallowRef instead of ref (default: false)
  shallow: false,
  // Initialize only after component is mounted (default: false)
  initOnMounted: false,
  // Custom error handler (default: console.error)
  onError: e => console.error(e),
  // Watch flush timing (default: 'pre')
  flush: 'pre',
})
```

## Reactive Key

The storage key can be a ref or getter, and the data will be updated when the key changes:

```ts
import { useStorage } from '@vueuse/core'

const userId = ref('user-1')
const userData = useStorage(
  () => `user-data-${userId.value}`,
  { name: '' },
)

// Changing the key will read from the new storage location
userId.value = 'user-2'
```

## Type Declarations

```ts
export interface Serializer<T> {
  read: (raw: string) => T
  write: (value: T) => string
}
export interface SerializerAsync<T> {
  read: (raw: string) => Awaitable<T>
  write: (value: T) => Awaitable<string>
}
export declare const StorageSerializers: Record<
  "boolean" | "object" | "number" | "any" | "string" | "map" | "set" | "date",
  Serializer<any>
>
export declare const customStorageEventName = "vueuse-storage"
export interface StorageEventLike {
  storageArea: StorageLike | null
  key: StorageEvent["key"]
  oldValue: StorageEvent["oldValue"]
  newValue: StorageEvent["newValue"]
}
export interface UseStorageOptions<T>
  extends ConfigurableEventFilter, ConfigurableWindow, ConfigurableFlush {
  /**
   * Watch for deep changes
   *
   * @default true
   */
  deep?: boolean
  /**
   * Listen to storage changes, useful for multiple tabs application
   *
   * @default true
   */
  listenToStorageChanges?: boolean
  /**
   * Write the default value to the storage when it does not exist
   *
   * @default true
   */
  writeDefaults?: boolean
  /**
   * Merge the default value with the value read from the storage.
   *
   * When setting it to true, it will perform a **shallow merge** for objects.
   * You can pass a function to perform custom merge (e.g. deep merge), for example:
   *
   * @default false
   */
  mergeDefaults?: boolean | ((storageValue: T, defaults: T) => T)
  /**
   * Custom data serialization
   */
  serializer?: Serializer<T>
  /**
   * On error callback
   *
   * Default log error to `console.error`
   */
  onError?: (error: unknown) => void
  /**
   * Use shallow ref as reference
   *
   * @default false
   */
  shallow?: boolean
  /**
   * Wait for the component to be mounted before reading the storage.
   *
   * @default false
   */
  initOnMounted?: boolean
}
export declare function useStorage(
  key: MaybeRefOrGetter<string>,
  defaults: MaybeRefOrGetter<string>,
  storage?: StorageLike,
  options?: UseStorageOptions<string>,
): RemovableRef<string>
export declare function useStorage(
  key: MaybeRefOrGetter<string>,
  defaults: MaybeRefOrGetter<boolean>,
  storage?: StorageLike,
  options?: UseStorageOptions<boolean>,
): RemovableRef<boolean>
export declare function useStorage(
  key: MaybeRefOrGetter<string>,
  defaults: MaybeRefOrGetter<number>,
  storage?: StorageLike,
  options?: UseStorageOptions<number>,
): RemovableRef<number>
export declare function useStorage<T>(
  key: MaybeRefOrGetter<string>,
  defaults: MaybeRefOrGetter<T>,
  storage?: StorageLike,
  options?: UseStorageOptions<T>,
): RemovableRef<T>
export declare function useStorage<T = unknown>(
  key: MaybeRefOrGetter<string>,
  defaults: MaybeRefOrGetter<null>,
  storage?: StorageLike,
  options?: UseStorageOptions<T>,
): RemovableRef<T>
```

---

<!-- source: references/useStorageAsync.md -->
---
category: State
---

# useStorageAsync

Reactive Storage in with async support.

## Usage

The basic usage please refer to `useStorage`.

## Wait First Loaded

When user entering your app, `useStorageAsync()` will start loading value from an async storage,
sometimes you may get the default initial value, not the real value stored in storage at the very
beginning.

```ts
import { useStorageAsync } from '@vueuse/core'

const accessToken = useStorageAsync('access.token', '', SomeAsyncStorage)

// accessToken.value may be empty before the async storage is ready
console.log(accessToken.value) // ""

setTimeout(() => {
  // After some time, the async storage is ready
  console.log(accessToken.value) // "the real value stored in storage"
}, 500)
```

In this case, you can wait the storage prepared, the returned value is also a `Promise`,
so you can wait it resolved in your template or script.

```ts
// Use top-level await if your environment supports it
const accessToken = await useStorageAsync('access.token', '', SomeAsyncStorage)

console.log(accessToken.value) // "the real value stored in storage"
```

If you must wait multiple storages, put them into a `Promise.allSettled()`

```ts
router.onReady(async () => {
  await Promise.allSettled([
    accessToken,
    refreshToken,
    userData,
  ])

  app.mount('app')
})
```

There is a callback named `onReady` in options:

```ts
import { useStorageAsync } from '@vueuse/core'

// Use ES2024 Promise.withResolvers, you may use any Deferred object or EventBus to do same thing.
const { promise, resolve } = Promise.withResolvers()

const accessToken = useStorageAsync('access.token', '', SomeAsyncStorage, {
  onReady(value) {
    resolve(value)
  }
})

// At main.ts
router.onReady(async () => {
  // Let's wait accessToken loaded
  await promise

  // Now accessToken has loaded, we can safely mount our app

  app.mount('app')
})
```

Simply use `resolve` as callback:

```ts
const accessToken = useStorageAsync('access.token', '', SomeAsyncStorage, {
  onReady: resolve
})
```

## Type Declarations

```ts
export interface UseStorageAsyncOptions<T> extends Omit<
  UseStorageOptions<T>,
  "serializer"
> {
  /**
   * Custom data serialization
   */
  serializer?: SerializerAsync<T>
  /**
   * On first value loaded hook.
   */
  onReady?: (value: T) => void
}
export declare function useStorageAsync(
  key: string,
  initialValue: MaybeRefOrGetter<string>,
  storage?: StorageLikeAsync,
  options?: UseStorageAsyncOptions<string>,
): RemovableRef<string> & Promise<RemovableRef<string>>
export declare function useStorageAsync(
  key: string,
  initialValue: MaybeRefOrGetter<boolean>,
  storage?: StorageLikeAsync,
  options?: UseStorageAsyncOptions<boolean>,
): RemovableRef<boolean> & Promise<RemovableRef<boolean>>
export declare function useStorageAsync(
  key: string,
  initialValue: MaybeRefOrGetter<number>,
  storage?: StorageLikeAsync,
  options?: UseStorageAsyncOptions<number>,
): RemovableRef<number> & Promise<RemovableRef<number>>
export declare function useStorageAsync<T>(
  key: string,
  initialValue: MaybeRefOrGetter<T>,
  storage?: StorageLikeAsync,
  options?: UseStorageAsyncOptions<T>,
): RemovableRef<T> & Promise<RemovableRef<T>>
export declare function useStorageAsync<T = unknown>(
  key: string,
  initialValue: MaybeRefOrGetter<null>,
  storage?: StorageLikeAsync,
  options?: UseStorageAsyncOptions<T>,
): RemovableRef<T> & Promise<RemovableRef<T>>
```

---

<!-- source: references/useStyleTag.md -->
---
category: Browser
---

# useStyleTag

Inject reactive `style` element in head.

## Usage

### Basic usage

Provide a CSS string, then `useStyleTag` will automatically generate an id and inject it in `<head>`.

```ts
import { useStyleTag } from '@vueuse/core'

const {
  id,
  css,
  load,
  unload,
  isLoaded,
} = useStyleTag('.foo { margin-top: 32px; }')

// Later you can modify styles
css.value = '.foo { margin-top: 64px; }'
```

This code will be injected to `<head>`:

```html
<style id="vueuse_styletag_1">
  .foo {
    margin-top: 64px;
  }
</style>
```

### Custom ID

If you need to define your own id, you can pass `id` as first argument.

```ts
import { useStyleTag } from '@vueuse/core'
// ---cut---
useStyleTag('.foo { margin-top: 32px; }', { id: 'custom-id' })
```

```html
<!-- injected to <head> -->
<style id="custom-id">
  .foo {
    margin-top: 32px;
  }
</style>
```

### Media query

You can pass media attributes as last argument within object.

```ts
import { useStyleTag } from '@vueuse/core'
// ---cut---
useStyleTag('.foo { margin-top: 32px; }', { media: 'print' })
```

```html
<!-- injected to <head> -->
<style id="vueuse_styletag_1" media="print">
  .foo {
    margin-top: 32px;
  }
</style>
```

## Type Declarations

```ts
export interface UseStyleTagOptions extends ConfigurableDocument {
  /**
   * Media query for styles to apply
   */
  media?: string
  /**
   * Load the style immediately
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Manual controls the timing of loading and unloading
   *
   * @default false
   */
  manual?: boolean
  /**
   * DOM id of the style tag
   *
   * @default auto-incremented
   */
  id?: string
  /**
   * Nonce value for CSP (Content Security Policy)
   *
   * @default undefined
   */
  nonce?: string
}
export interface UseStyleTagReturn {
  id: string
  css: ShallowRef<string>
  load: () => void
  unload: () => void
  isLoaded: Readonly<ShallowRef<boolean>>
}
/**
 * Inject <style> element in head.
 *
 * Overload: Omitted id
 *
 * @see https://vueuse.org/useStyleTag
 * @param css
 * @param options
 */
export declare function useStyleTag(
  css: MaybeRef<string>,
  options?: UseStyleTagOptions,
): UseStyleTagReturn
```

---

<!-- source: references/useSubject.md -->
---
category: '@RxJS'
---

# useSubject

Bind an RxJS [`Subject`](https://rxjs.dev/guide/subject) to a `ref` and propagate value changes both ways.

## Usage

<!-- TODO: import rxjs error if enable twoslash -->

```ts no-twoslash
import { useSubject } from '@vueuse/rxjs'
import { Subject } from 'rxjs'

const subject = new Subject()

// setup()
const subjectRef = useSubject(subject)

// Changes to subjectRef.value will be pushed to the subject
subjectRef.value = 'new value'

// Values emitted by the subject will update subjectRef
subject.next('from subject')
```

### With BehaviorSubject

When using a `BehaviorSubject`, the returned ref is initialized with the subject's current value and the type does not include `undefined`:

```ts no-twoslash
import { useSubject } from '@vueuse/rxjs'
import { BehaviorSubject } from 'rxjs'

const subject = new BehaviorSubject('initial')

// setup()
const subjectRef = useSubject(subject) // Ref<string>, not Ref<string | undefined>
console.log(subjectRef.value) // 'initial'
```

### Error Handling

If you want to add custom error handling to a Subject that might error, you can supply an optional `onError` configuration. Without this, RxJS will treat any error in the supplied observable as an "unhandled error" and it will be thrown in a new call stack and reported to `window.onerror` (or `process.on('error')` if you happen to be in node).

```ts no-twoslash
import { useSubject } from '@vueuse/rxjs'
import { Subject } from 'rxjs'

const subject = new Subject()

// setup()
const subjectRef = useSubject(subject, {
  onError: (err) => {
    console.log(err.message) // "oops"
  },
},)
```

## Type Declarations

```ts
export interface UseSubjectOptions<I = undefined> extends Omit<
  UseObservableOptions<I>,
  "initialValue"
> {}
export declare function useSubject<H>(
  subject: BehaviorSubject<H>,
  options?: UseSubjectOptions,
): Ref<H>
export declare function useSubject<H>(
  subject: Subject<H>,
  options?: UseSubjectOptions,
): Ref<H | undefined>
```

---

<!-- source: references/useSubscription.md -->
---
category: '@RxJS'
---

# useSubscription

Use an RxJS [`Subscription`](https://rxjs.dev/guide/subscription) without worrying about unsubscribing from it or creating memory leaks.

## Usage

<!-- TODO: import rxjs error if enable twoslash -->

```ts no-twoslash
import { useSubscription } from '@vueuse/rxjs'
import { interval } from 'rxjs'

const count = ref(0)

// useSubscription call unsubscribe method before unmount the component
useSubscription(
  interval(1000)
    .subscribe(() => {
      count.value++
      console.log(count)
    }),
)
```

## Type Declarations

```ts
export declare function useSubscription(subscription: Unsubscribable): void
```

---

<!-- source: references/useSum.md -->
---
category: '@Math'
---

# useSum

Get the sum of an array reactively

## Usage

```ts
import { useSum } from '@vueuse/math'

const array = ref([1, 2, 3, 4])
const sum = useSum(array) // Ref<10>
```

```ts
import { useSum } from '@vueuse/math'

const a = ref(1)
const b = ref(3)

const sum = useSum(a, b, 2) // Ref<6>
```

## Type Declarations

```ts
export declare function useSum(
  array: MaybeRefOrGetter<MaybeRefOrGetter<number>[]>,
): ComputedRef<number>
export declare function useSum(
  ...args: MaybeRefOrGetter<number>[]
): ComputedRef<number>
```

---

<!-- source: references/useSupported.md -->
---
category: Utilities
---

# useSupported

SSR compatibility `isSupported`

## Usage

```ts
import { useSupported } from '@vueuse/core'

const isSupported = useSupported(() => navigator && 'getBattery' in navigator)

if (isSupported.value) {
  // do something
  navigator.getBattery
}
```

## Type Declarations

```ts
export type UseSupportedReturn = ComputedRef<boolean>
export declare function useSupported(
  callback: () => unknown,
): UseSupportedReturn
```

---

<!-- source: references/useSwipe.md -->
---
category: Sensors
---

# useSwipe

Reactive swipe detection based on [`TouchEvents`](https://developer.mozilla.org/en-US/docs/Web/API/TouchEvent).

## Usage

```vue
<script setup lang="ts">
import { useSwipe } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const el = useTemplateRef('el')
const { isSwiping, direction } = useSwipe(el)
</script>

<template>
  <div ref="el">
    Swipe here
  </div>
</template>
```

## Type Declarations

```ts
export type UseSwipeDirection = "up" | "down" | "left" | "right" | "none"
export interface UseSwipeOptions extends ConfigurableWindow {
  /**
   * Register events as passive
   *
   * @default true
   */
  passive?: boolean
  /**
   * @default 50
   */
  threshold?: number
  /**
   * Callback on swipe start
   */
  onSwipeStart?: (e: TouchEvent) => void
  /**
   * Callback on swipe moves
   */
  onSwipe?: (e: TouchEvent) => void
  /**
   * Callback on swipe ends
   */
  onSwipeEnd?: (e: TouchEvent, direction: UseSwipeDirection) => void
}
export interface UseSwipeReturn {
  isSwiping: ShallowRef<boolean>
  direction: ComputedRef<UseSwipeDirection>
  coordsStart: Readonly<Position>
  coordsEnd: Readonly<Position>
  lengthX: ComputedRef<number>
  lengthY: ComputedRef<number>
  stop: () => void
}
/**
 * Reactive swipe detection.
 *
 * @see https://vueuse.org/useSwipe
 * @param target
 * @param options
 */
export declare function useSwipe(
  target: MaybeRefOrGetter<EventTarget | null | undefined>,
  options?: UseSwipeOptions,
): UseSwipeReturn
```

---

<!-- source: references/useTemplateRefsList.md -->
---
category: Component
---

# useTemplateRefsList

Shorthand for binding refs to template elements and components inside `v-for`.

## Usage

```vue
<script setup lang="ts">
import { useTemplateRefsList } from '@vueuse/core'
import { onUpdated } from 'vue'

const refs = useTemplateRefsList<HTMLDivElement>()

onUpdated(() => {
  console.log(refs)
})
</script>

<template>
  <div v-for="i of 5" :key="i" :ref="refs.set" />
</template>
```

## Type Declarations

```ts
export type TemplateRefsList<T> = T[] & {
  set: (el: object | null) => void
}
export declare function useTemplateRefsList<T = Element>(): Readonly<
  Ref<Readonly<TemplateRefsList<T>>>
>
```

---

<!-- source: references/useTextDirection.md -->
---
category: Browser
---

# useTextDirection

Reactive [dir](https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/dir) of the element's text.

## Usage

```ts
import { useTextDirection } from '@vueuse/core'

const dir = useTextDirection() // Ref<'ltr' | 'rtl' | 'auto'>
```

By default, it returns `rtl` direction when dir `rtl` is applied to the `html` tag, for example:

```html
<!--ltr-->
<html>
  ...
</html>

<!--rtl-->
<html dir="rtl">
  ...
</html>
```

## Options

```ts
import { useTextDirection } from '@vueuse/core'

const mode = useTextDirection({
  selector: 'body'
}) // Ref<'ltr' | 'rtl' | 'auto'>
```

## Type Declarations

```ts
export type UseTextDirectionValue = "ltr" | "rtl" | "auto"
export interface UseTextDirectionOptions extends ConfigurableDocument {
  /**
   * CSS Selector for the target element applying to
   *
   * @default 'html'
   */
  selector?: string
  /**
   * Observe `document.querySelector(selector)` changes using MutationObserve
   *
   * @default false
   */
  observe?: boolean
  /**
   * Initial value
   *
   * @default 'ltr'
   */
  initialValue?: UseTextDirectionValue
}
/**
 * Reactive dir of the element's text.
 *
 * @see https://vueuse.org/useTextDirection
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useTextDirection(
  options?: UseTextDirectionOptions,
): WritableComputedRef<UseTextDirectionValue, UseTextDirectionValue>
```

---

<!-- source: references/useTextSelection.md -->
---
category: Sensors
---

# useTextSelection

Reactively track user text selection based on [`Window.getSelection`](https://developer.mozilla.org/en-US/docs/Web/API/Window/getSelection).

## Usage

```vue
<script setup lang="ts">
import { useTextSelection } from '@vueuse/core'

const state = useTextSelection()
</script>

<template>
  <p>{{ state.text }}</p>
</template>
```

## Type Declarations

```ts
export interface UseTextSelectionOptions extends ConfigurableWindow {}
export interface UseTextSelectionReturn {
  text: ComputedRef<string>
  rects: ComputedRef<DOMRect[]>
  ranges: ComputedRef<Range[]>
  selection: ShallowRef<Selection | null>
}
/**
 * Reactively track user text selection based on [`Window.getSelection`](https://developer.mozilla.org/en-US/docs/Web/API/Window/getSelection).
 *
 * @see https://vueuse.org/useTextSelection
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useTextSelection(
  options?: UseTextSelectionOptions,
): UseTextSelectionReturn
```

---

<!-- source: references/useTextareaAutosize.md -->
---
category: Browser
---

# useTextareaAutosize

Automatically update the height of a textarea depending on the content.

## Usage

### Simple example

```vue
<script setup lang="ts">
import { useTextareaAutosize } from '@vueuse/core'

const { textarea, input } = useTextareaAutosize()
</script>

<template>
  <textarea
    ref="textarea"
    v-model="input"
    class="resize-none"
    placeholder="What's on your mind?"
  />
</template>
```

::: info

It's recommended to reset the scrollbar styles for the textarea element to avoid incorrect height values for large amounts of text.

```css
textarea {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

textarea::-webkit-scrollbar {
  display: none;
}
```

:::

### With `rows` attribute

If you need support for the rows attribute on a textarea element, then you should set the `styleProp` option to `minHeight`.

```vue
<script setup lang="ts">
import { useTextareaAutosize } from '@vueuse/core'

const { textarea, input } = useTextareaAutosize({ styleProp: 'minHeight' })
</script>

<template>
  <textarea
    ref="textarea"
    v-model="input"
    class="resize-none"
    placeholder="What's on your mind?"
    rows="3"
  />
</template>
```

## Type Declarations

```ts
export interface UseTextareaAutosizeOptions extends ConfigurableWindow {
  /** Textarea element to autosize. */
  element?: MaybeRef<HTMLTextAreaElement | undefined | null>
  /** Textarea content. */
  input?: MaybeRef<string>
  /** Watch sources that should trigger a textarea resize. */
  watch?: WatchSource | MultiWatchSources
  /** Function called when the textarea size changes. */
  onResize?: () => void
  /** Specify style target to apply the height based on textarea content. If not provided it will use textarea it self.  */
  styleTarget?: MaybeRef<HTMLElement | undefined>
  /** Specify the style property that will be used to manipulate height. Can be `height | minHeight`. Default value is `height`. */
  styleProp?: "height" | "minHeight"
}
export interface UseTextareaAutosizeReturn {
  textarea: Ref<HTMLTextAreaElement | undefined | null>
  input: Ref<string>
  triggerResize: () => void
}
export declare function useTextareaAutosize(
  options?: UseTextareaAutosizeOptions,
): UseTextareaAutosizeReturn
```

---

<!-- source: references/useThrottleFn.md -->
---
category: Utilities
related: refThrottled, refDebounced, useDebounceFn
---

# useThrottleFn

Throttle execution of a function. Especially useful for rate limiting execution of handlers on events like resize and scroll.

> Throttle is a spring that throws balls: after a ball flies out it needs some time to shrink back, so it cannot throw any more balls unless it's ready.

## Usage

```ts
import { useThrottleFn } from '@vueuse/core'

const throttledFn = useThrottleFn(() => {
  // do something, it will be called at most 1 time per second
}, 1000)

useEventListener(window, 'resize', throttledFn)
```

## Recommended Reading

- [**Debounce vs Throttle**: Definitive Visual Guide](https://kettanaito.com/blog/debounce-vs-throttle)

## Type Declarations

```ts
/**
 * Throttle execution of a function. Especially useful for rate limiting
 * execution of handlers on events like resize and scroll.
 *
 * @param   fn             A function to be executed after delay milliseconds. The `this` context and all arguments are passed through, as-is,
 *                                    to `callback` when the throttled-function is executed.
 * @param   ms             A zero-or-greater delay in milliseconds. For event callbacks, values around 100 or 250 (or even higher) are most useful.
 *                                    (default value: 200)
 *
 * @param [trailing] if true, call fn again after the time is up (default value: false)
 *
 * @param [leading] if true, call fn on the leading edge of the ms timeout (default value: true)
 *
 * @param [rejectOnCancel] if true, reject the last call if it's been cancel (default value: false)
 *
 * @return  A new, throttled, function.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useThrottleFn<T extends FunctionArgs>(
  fn: T,
  ms?: MaybeRefOrGetter<number>,
  trailing?: boolean,
  leading?: boolean,
  rejectOnCancel?: boolean,
): PromisifyFn<T>
```

---

<!-- source: references/useThrottledRefHistory.md -->
---
category: State
related: useDebouncedRefHistory, useRefHistory
---

# useThrottledRefHistory

Shorthand for `useRefHistory` with throttled filter.

## Usage

This function takes the first snapshot right after the counter's value was changed and the second with a delay of 1000ms.

```ts
import { useThrottledRefHistory } from '@vueuse/core'
import { shallowRef } from 'vue'

const counter = shallowRef(0)
const { history, undo, redo } = useThrottledRefHistory(counter, { deep: true, throttle: 1000 })
```

## Type Declarations

```ts
export type UseThrottledRefHistoryOptions<Raw, Serialized = Raw> = Omit<
  UseRefHistoryOptions<Raw, Serialized>,
  "eventFilter"
> & {
  throttle?: MaybeRef<number>
  trailing?: boolean
}
export type UseThrottledRefHistoryReturn<
  Raw,
  Serialized = Raw,
> = UseRefHistoryReturn<Raw, Serialized>
/**
 * Shorthand for [useRefHistory](https://vueuse.org/useRefHistory) with throttled filter.
 *
 * @see https://vueuse.org/useThrottledRefHistory
 * @param source
 * @param options
 */
export declare function useThrottledRefHistory<Raw, Serialized = Raw>(
  source: Ref<Raw>,
  options?: UseThrottledRefHistoryOptions<Raw, Serialized>,
): UseThrottledRefHistoryReturn<Raw, Serialized>
```

---

<!-- source: references/useTimeAgo.md -->
---
category: Time
---

# useTimeAgo

Reactive time ago. Automatically update the time ago string when the time changes.

## Usage

```ts
import { useTimeAgo } from '@vueuse/core'

const timeAgo = useTimeAgo(new Date(2021, 0, 1))
```

## Component Usage

```vue
<template>
  <UseTimeAgo v-slot="{ timeAgo }" :time="new Date(2021, 0, 1)">
    Time Ago: {{ timeAgo }}
  </UseTimeAgo>
</template>
```

## Non-Reactivity Usage

In case you don't need the reactivity, you can use the `formatTimeAgo` function to get the formatted string instead of a Ref.

```ts
import { formatTimeAgo } from '@vueuse/core'

const timeAgo = formatTimeAgo(new Date(2021, 0, 1)) // string
```

## Type Declarations

```ts
export type UseTimeAgoFormatter<T = number> = (
  value: T,
  isPast: boolean,
) => string
export type UseTimeAgoUnitNamesDefault =
  | "second"
  | "minute"
  | "hour"
  | "day"
  | "week"
  | "month"
  | "year"
export interface UseTimeAgoMessagesBuiltIn {
  justNow: string
  past: string | UseTimeAgoFormatter<string>
  future: string | UseTimeAgoFormatter<string>
  invalid: string
}
export type UseTimeAgoMessages<
  UnitNames extends string = UseTimeAgoUnitNamesDefault,
> = UseTimeAgoMessagesBuiltIn &
  Record<UnitNames, string | UseTimeAgoFormatter<number>>
export interface FormatTimeAgoOptions<
  UnitNames extends string = UseTimeAgoUnitNamesDefault,
> {
  /**
   * Maximum unit (of diff in milliseconds) to display the full date instead of relative
   *
   * @default undefined
   */
  max?: UnitNames | number
  /**
   * Formatter for full date
   */
  fullDateFormatter?: (date: Date) => string
  /**
   * Messages for formatting the string
   */
  messages?: UseTimeAgoMessages<UnitNames>
  /**
   * Minimum display time unit (default is minute)
   *
   * @default false
   */
  showSecond?: boolean
  /**
   * Rounding method to apply.
   *
   * @default 'round'
   */
  rounding?: "round" | "ceil" | "floor" | number
  /**
   * Custom units
   */
  units?: UseTimeAgoUnit<UnitNames>[]
}
export interface UseTimeAgoOptions<
  Controls extends boolean,
  UnitNames extends string = UseTimeAgoUnitNamesDefault,
>
  extends FormatTimeAgoOptions<UnitNames>, ConfigurableScheduler {
  /**
   * Expose more controls
   *
   * @default false
   */
  controls?: Controls
  /**
   * Intervals to update, set 0 to disable auto update
   *
   * @deprecated Please use `scheduler` option instead
   * @default 30_000
   */
  updateInterval?: number
}
export interface UseTimeAgoUnit<
  Unit extends string = UseTimeAgoUnitNamesDefault,
> {
  max: number
  value: number
  name: Unit
}
export type UseTimeAgoReturn<Controls extends boolean = false> =
  Controls extends true
    ? {
        timeAgo: ComputedRef<string>
      } & Pausable
    : ComputedRef<string>
/**
 * Reactive time ago formatter.
 *
 * @see https://vueuse.org/useTimeAgo
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useTimeAgo<
  UnitNames extends string = UseTimeAgoUnitNamesDefault,
>(
  time: MaybeRefOrGetter<Date | number | string>,
  options?: UseTimeAgoOptions<false, UnitNames>,
): UseTimeAgoReturn<false>
export declare function useTimeAgo<
  UnitNames extends string = UseTimeAgoUnitNamesDefault,
>(
  time: MaybeRefOrGetter<Date | number | string>,
  options: UseTimeAgoOptions<true, UnitNames>,
): UseTimeAgoReturn<true>
export declare function formatTimeAgo<
  UnitNames extends string = UseTimeAgoUnitNamesDefault,
>(
  from: Date,
  options?: FormatTimeAgoOptions<UnitNames>,
  now?: Date | number,
): string
```

---

<!-- source: references/useTimeAgoIntl.md -->
---
category: Time
---

# useTimeAgoIntl

Reactive time ago with i18n supported. Automatically update the time ago string when the time changes. Powered by `Intl.RelativeTimeFormat`.

## Usage

```js
import { useTimeAgoIntl } from '@vueuse/core'

const timeAgoIntl = useTimeAgoIntl(new Date(2021, 0, 1))
```

## Non-Reactivity Usage

In case you don't need the reactivity, you can use the `formatTimeAgo` function to get the formatted string instead of a Ref.

```js
import { formatTimeAgoIntl } from '@vueuse/core'

const timeAgoIntl = formatTimeAgoIntl(new Date(2021, 0, 1)) // string
```

## Type Declarations

```ts
type Locale = Intl.UnicodeBCP47LocaleIdentifier | Intl.Locale
export interface FormatTimeAgoIntlOptions {
  /**
   * The locale to format with
   *
   * @default undefined
   * @see https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat/RelativeTimeFormat#locales
   */
  locale?: Locale
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat/RelativeTimeFormat#options
   */
  relativeTimeFormatOptions?: Intl.RelativeTimeFormatOptions
  /**
   * Whether to insert spaces between parts.
   *
   * Ignored if `joinParts` is provided.
   *
   * @default true
   */
  insertSpace?: boolean
  /**
   * Custom function to join the parts returned by `Intl.RelativeTimeFormat.formatToParts`.
   *
   * If provided, it will be used instead of the default join logic.
   */
  joinParts?: (
    parts: Intl.RelativeTimeFormatPart[],
    locale?: Intl.UnicodeBCP47LocaleIdentifier | Intl.Locale,
  ) => string
  /**
   * Custom units
   */
  units?: TimeAgoUnit[]
}
export interface UseTimeAgoIntlOptions<Controls extends boolean>
  extends FormatTimeAgoIntlOptions, ConfigurableScheduler {
  /**
   * Expose more controls and the raw `parts` result.
   *
   * @default false
   */
  controls?: Controls
  /**
   * Update interval in milliseconds, set 0 to disable auto update
   *
   * @deprecated Please use `scheduler` option instead
   * @default 30_000
   */
  updateInterval?: number
}
type UseTimeAgoReturn<Controls extends boolean = false> = Controls extends true
  ? {
      timeAgoIntl: ComputedRef<string>
      parts: ComputedRef<Intl.RelativeTimeFormatPart[]>
    } & Pausable
  : ComputedRef<string>
export interface TimeAgoUnit {
  name: Intl.RelativeTimeFormatUnit
  ms: number
}
/**
 * A reactive wrapper for `Intl.RelativeTimeFormat`.
 */
export declare function useTimeAgoIntl(
  time: MaybeRefOrGetter<Date | number | string>,
  options?: UseTimeAgoIntlOptions<false>,
): UseTimeAgoReturn<false>
export declare function useTimeAgoIntl(
  time: MaybeRefOrGetter<Date | number | string>,
  options: UseTimeAgoIntlOptions<true>,
): UseTimeAgoReturn<true>
/**
 * Non-reactive version of useTimeAgoIntl
 */
export declare function formatTimeAgoIntl(
  from: Date,
  options?: FormatTimeAgoIntlOptions,
  now?: Date | number,
): string
/**
 * Format parts into a string
 */
export declare function formatTimeAgoIntlParts(
  parts: Intl.RelativeTimeFormatPart[],
  options?: FormatTimeAgoIntlOptions,
): string
```

---

<!-- source: references/useTimeout.md -->
---
category: Animation
---

# useTimeout

Reactive value that becomes `true` after a given time.

## Usage

```ts
import { useTimeout } from '@vueuse/core'

const ready = useTimeout(1000)
```

After 1 second, `ready.value` becomes `true`.

### With Controls

```ts
import { useTimeout } from '@vueuse/core'

const { ready, start, stop, isPending } = useTimeout(1000, { controls: true })

// Check if timeout is pending
console.log(isPending.value) // true

// Stop the timeout
stop()

// Start/restart the timeout
start()
```

### Options

| Option      | Type         | Default | Description                                      |
| ----------- | ------------ | ------- | ------------------------------------------------ |
| `controls`  | `boolean`    | `false` | Expose `start`, `stop`, and `isPending` controls |
| `immediate` | `boolean`    | `true`  | Start the timeout immediately                    |
| `callback`  | `() => void` | —       | Called when the timeout completes                |

### Callback on Timeout

```ts
import { useTimeout } from '@vueuse/core'

useTimeout(1000, {
  callback: () => {
    console.log('Timeout completed!')
  },
})
```

### Reactive Interval

The timeout duration can be reactive:

```ts
import { useTimeout } from '@vueuse/core'

const duration = ref(1000)
const ready = useTimeout(duration)

// Change the duration (only affects future timeouts when using controls)
duration.value = 2000
```

## Type Declarations

```ts
export interface UseTimeoutOptions<
  Controls extends boolean,
> extends UseTimeoutFnOptions {
  /**
   * Expose more controls
   *
   * @default false
   */
  controls?: Controls
  /**
   * Callback on timeout
   */
  callback?: Fn
}
export type UseTimeoutReturn =
  | ComputedRef<boolean>
  | ({
      readonly ready: ComputedRef<boolean>
    } & Stoppable)
/**
 * @deprecated use UseTimeoutReturn instead
 */
export type UseTimoutReturn = UseTimeoutReturn
/**
 * Update value after a given time with controls.
 *
 * @see   {@link https://vueuse.org/useTimeout}
 * @param interval
 * @param options
 */
export declare function useTimeout(
  interval?: MaybeRefOrGetter<number>,
  options?: UseTimeoutOptions<false>,
): ComputedRef<boolean>
export declare function useTimeout(
  interval: MaybeRefOrGetter<number>,
  options: UseTimeoutOptions<true>,
): {
  ready: ComputedRef<boolean>
} & Stoppable
```

---

<!-- source: references/useTimeoutFn.md -->
---
category: Animation
---

# useTimeoutFn

Wrapper for `setTimeout` with controls.

## Usage

```ts
import { useTimeoutFn } from '@vueuse/core'

const { isPending, start, stop } = useTimeoutFn(() => {
  /* ... */
}, 3000)
```

## Type Declarations

```ts
export interface UseTimeoutFnOptions {
  /**
   * Start the timer immediately
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Execute the callback immediately after calling `start`
   *
   * @default false
   */
  immediateCallback?: boolean
}
export type UseTimeoutFnReturn<CallbackFn extends AnyFn> = Stoppable<
  Parameters<CallbackFn> | []
>
/**
 * Wrapper for `setTimeout` with controls.
 *
 * @param cb
 * @param interval
 * @param options
 */
export declare function useTimeoutFn<CallbackFn extends AnyFn>(
  cb: CallbackFn,
  interval: MaybeRefOrGetter<number>,
  options?: UseTimeoutFnOptions,
): UseTimeoutFnReturn<CallbackFn>
```

---

<!-- source: references/useTimeoutPoll.md -->
---
category: Utilities
---

# useTimeoutPoll

Use timeout to poll something. It will trigger callback after last task is done.

## Usage

```ts
import { useTimeoutPoll } from '@vueuse/core'

const count = ref(0)

async function fetchData() {
  await new Promise(resolve => setTimeout(resolve, 1000))
  count.value++
}

// Only trigger after last fetch is done
const { isActive, pause, resume } = useTimeoutPoll(fetchData, 1000)
```

## Type Declarations

```ts
export interface UseTimeoutPollOptions {
  /**
   * Start the timer immediately
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Execute the callback immediately after calling `resume`
   *
   * @default false
   */
  immediateCallback?: boolean
}
export declare function useTimeoutPoll(
  fn: () => Awaitable<void>,
  interval: MaybeRefOrGetter<number>,
  options?: UseTimeoutFnOptions,
): Pausable
```

---

<!-- source: references/useTimestamp.md -->
---
category: Animation
---

# useTimestamp

Reactive current timestamp

## Usage

```ts
import { useTimestamp } from '@vueuse/core'

const timestamp = useTimestamp({ offset: 0 })
```

```ts
import { useTimestamp } from '@vueuse/core'
// ---cut---
const { timestamp, pause, resume } = useTimestamp({ controls: true })
```

## Component Usage

```vue
<template>
  <UseTimestamp v-slot="{ timestamp, pause, resume }">
    Current Time: {{ timestamp }}
    <button @click="pause()">
      Pause
    </button>
    <button @click="resume()">
      Resume
    </button>
  </UseTimestamp>
</template>
```

## Type Declarations

```ts
export interface UseTimestampOptions<
  Controls extends boolean,
> extends ConfigurableScheduler {
  /**
   * Expose more controls
   *
   * @default false
   */
  controls?: Controls
  /**
   * Offset value adding to the value
   *
   * @default 0
   */
  offset?: number
  /**
   * Update the timestamp immediately
   *
   * @deprecated Please use `scheduler` option instead
   * @default true
   */
  immediate?: boolean
  /**
   * Update interval, or use requestAnimationFrame
   *
   * @deprecated Please use `scheduler` option instead
   * @default requestAnimationFrame
   */
  interval?: "requestAnimationFrame" | number
  /**
   * Callback on each update
   */
  callback?: (timestamp: number) => void
}
export type UseTimestampReturn<Controls extends boolean> = Controls extends true
  ? {
      timestamp: ShallowRef<number>
    } & Pausable
  : ShallowRef<number>
/**
 * Reactive current timestamp.
 *
 * @see https://vueuse.org/useTimestamp
 * @param options
 */
export declare function useTimestamp(
  options?: UseTimestampOptions<false>,
): ShallowRef<number>
export declare function useTimestamp(options: UseTimestampOptions<true>): {
  timestamp: ShallowRef<number>
} & Pausable
```

---

<!-- source: references/useTitle.md -->
---
category: Browser
---

# useTitle

Reactive document title.

::: warning
This composable isn't compatible with SSR.
:::

## Usage

```ts
import { useTitle } from '@vueuse/core'

const title = useTitle()
console.log(title.value) // print current title
title.value = 'Hello' // change current title
```

Set initial title immediately:

```ts
import { useTitle } from '@vueuse/core'
// ---cut---
const title = useTitle('New Title')
```

Pass a `ref` and the title will be updated when the source ref changes:

```ts
import { useTitle } from '@vueuse/core'
import { shallowRef } from 'vue'

const messages = shallowRef(0)

const title = computed(() => {
  return !messages.value ? 'No message' : `${messages.value} new messages`
})

useTitle(title) // document title will match with the ref "title"
```

Pass an optional template tag [Vue Meta Title Template](https://vue-meta.nuxtjs.org/guide/metainfo.html) to update the title to be injected into this template:

```ts
import { useTitle } from '@vueuse/core'
// ---cut---
const title = useTitle('New Title', {
  titleTemplate: '%s | My Awesome Website'
})
```

::: warning
`observe` is incompatible with `titleTemplate`.
:::

## Type Declarations

```ts
export type UseTitleOptionsBase = {
  /**
   * Restore the original title when unmounted
   * @param originTitle original title
   * @returns restored title
   */
  restoreOnUnmount?:
    | false
    | ((
        originalTitle: string,
        currentTitle: string,
      ) => string | null | undefined)
} & (
  | {
      /**
       * Observe `document.title` changes using MutationObserve
       * Cannot be used together with `titleTemplate` option.
       *
       * @default false
       */
      observe?: boolean
    }
  | {
      /**
       * The template string to parse the title (e.g., '%s | My Website')
       * Cannot be used together with `observe` option.
       *
       * @default '%s'
       */
      titleTemplate?: MaybeRef<string> | ((title: string) => string)
    }
)
export type UseTitleOptions = ConfigurableDocument & UseTitleOptionsBase
export type UseTitleReturn =
  | ComputedRef<string | null | undefined>
  | Ref<string | null | undefined>
/**
 * Reactive document title.
 *
 * @see https://vueuse.org/useTitle
 * @param newTitle
 * @param options
 * @description It's not SSR compatible. Your value will be applied only on client-side.
 */
export declare function useTitle(
  newTitle: ReadonlyRefOrGetter<string | null | undefined>,
  options?: UseTitleOptions,
): ComputedRef<string | null | undefined>
export declare function useTitle(
  newTitle?: MaybeRef<string | null | undefined>,
  options?: UseTitleOptions,
): Ref<string | null | undefined>
```

---

<!-- source: references/useToNumber.md -->
---
category: Utilities
---

# useToNumber

Reactively convert a string ref to number.

## Usage

```ts
import { useToNumber } from '@vueuse/core'
import { shallowRef } from 'vue'

const str = shallowRef('123')
const number = useToNumber(str)

number.value // 123
```

## Type Declarations

```ts
export interface UseToNumberOptions {
  /**
   * Method to use to convert the value to a number.
   *
   * Or a custom function for the conversion.
   *
   * @default 'parseFloat'
   */
  method?: "parseFloat" | "parseInt" | ((value: string | number) => number)
  /**
   * The base in mathematical numeral systems passed to `parseInt`.
   * Only works with `method: 'parseInt'`
   */
  radix?: number
  /**
   * Replace NaN with zero
   *
   * @default false
   */
  nanToZero?: boolean
}
/**
 * Reactively convert a string ref to number.
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useToNumber(
  value: MaybeRefOrGetter<number | string>,
  options?: UseToNumberOptions,
): ComputedRef<number>
```

---

<!-- source: references/useToString.md -->
---
category: Utilities
---

# useToString

Reactively convert a ref to string.

## Usage

```ts
import { useToString } from '@vueuse/core'
import { shallowRef } from 'vue'

const number = shallowRef(3.14)
const str = useToString(number)

str.value // '3.14'
```

## Type Declarations

```ts
/**
 * Reactively convert a ref to string.
 *
 * @see https://vueuse.org/useToString
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useToString(
  value: MaybeRefOrGetter<unknown>,
): ComputedRef<string>
```

---

<!-- source: references/useToggle.md -->
---
category: Utilities
---

# useToggle

A boolean switcher with utility functions.

## Usage

```ts
import { useToggle } from '@vueuse/core'

const [value, toggle] = useToggle()
```

When you pass a ref, `useToggle` will return a simple toggle function instead:

```ts
import { useDark, useToggle } from '@vueuse/core'

const isDark = useDark()
const toggleDark = useToggle(isDark)
```

### Toggle Function

The toggle function can be called in two ways:

```ts
const [value, toggle] = useToggle()

toggle() // toggle between true and false
toggle(true) // set to specific value

// The toggle function returns the new value
const newValue = toggle() // returns the new value after toggling
```

### Custom Values

You can use custom truthy and falsy values instead of `true` and `false`:

```ts
import { useToggle } from '@vueuse/core'

const [value, toggle] = useToggle('on', {
  truthyValue: 'on',
  falsyValue: 'off',
})

toggle() // 'off'
toggle() // 'on'
```

The custom values can also be reactive:

```ts
import { useToggle } from '@vueuse/core'
import { ref } from 'vue'

const truthy = ref('yes')
const falsy = ref('no')

const [value, toggle] = useToggle('yes', {
  truthyValue: truthy,
  falsyValue: falsy,
})
```

## Caution

Be aware that the toggle function accepts the first argument as the override value. You might want to avoid directly passing the function to events in the template, as the event object will be passed in.

```html
<!-- caution: $event will be passed in -->
<button @click="toggleDark" />
<!-- recommended to do this -->
<button @click="toggleDark()" />
```

## Type Declarations

```ts
export type ToggleFn = (value?: boolean) => void
export type UseToggleReturn = [ShallowRef<boolean>, ToggleFn] | ToggleFn
export interface UseToggleOptions<Truthy, Falsy> {
  truthyValue?: MaybeRefOrGetter<Truthy>
  falsyValue?: MaybeRefOrGetter<Falsy>
}
export declare function useToggle<Truthy, Falsy, T = Truthy | Falsy>(
  initialValue: Ref<T>,
  options?: UseToggleOptions<Truthy, Falsy>,
): (value?: T) => T
export declare function useToggle<
  Truthy = true,
  Falsy = false,
  T = Truthy | Falsy,
>(
  initialValue?: T,
  options?: UseToggleOptions<Truthy, Falsy>,
): [ShallowRef<T>, (value?: T) => T]
```

---

<!-- source: references/useTransition.md -->
---
category: Animation
---

# useTransition

Transition between values

## Usage

Define a source value to follow, and when changed the output will transition to the new value. If the source changes while a transition is in progress, a new transition will begin from where the previous one was interrupted.

```ts
import { TransitionPresets, useTransition } from '@vueuse/core'
import { shallowRef } from 'vue'

const source = shallowRef(0)

const output = useTransition(source, {
  duration: 1000,
  easing: TransitionPresets.easeInOutCubic,
})
```

Transition easing can be customized using [cubic bezier curves](https://developer.mozilla.org/en-US/docs/Web/CSS/easing-function/cubic-bezier#description).

```ts
import { useTransition } from '@vueuse/core'
// ---cut---
useTransition(source, {
  easing: [0.75, 0, 0.25, 1],
})
```

The following transitions are available via the `TransitionPresets` constant.

- [`linear`](https://cubic-bezier.com/#0,0,1,1)
- [`easeInSine`](https://cubic-bezier.com/#.12,0,.39,0)
- [`easeOutSine`](https://cubic-bezier.com/#.61,1,.88,1)
- [`easeInOutSine`](https://cubic-bezier.com/#.37,0,.63,1)
- [`easeInQuad`](https://cubic-bezier.com/#.11,0,.5,0)
- [`easeOutQuad`](https://cubic-bezier.com/#.5,1,.89,1)
- [`easeInOutQuad`](https://cubic-bezier.com/#.45,0,.55,1)
- [`easeInCubic`](https://cubic-bezier.com/#.32,0,.67,0)
- [`easeOutCubic`](https://cubic-bezier.com/#.33,1,.68,1)
- [`easeInOutCubic`](https://cubic-bezier.com/#.65,0,.35,1)
- [`easeInQuart`](https://cubic-bezier.com/#.5,0,.75,0)
- [`easeOutQuart`](https://cubic-bezier.com/#.25,1,.5,1)
- [`easeInOutQuart`](https://cubic-bezier.com/#.76,0,.24,1)
- [`easeInQuint`](https://cubic-bezier.com/#.64,0,.78,0)
- [`easeOutQuint`](https://cubic-bezier.com/#.22,1,.36,1)
- [`easeInOutQuint`](https://cubic-bezier.com/#.83,0,.17,1)
- [`easeInExpo`](https://cubic-bezier.com/#.7,0,.84,0)
- [`easeOutExpo`](https://cubic-bezier.com/#.16,1,.3,1)
- [`easeInOutExpo`](https://cubic-bezier.com/#.87,0,.13,1)
- [`easeInCirc`](https://cubic-bezier.com/#.55,0,1,.45)
- [`easeOutCirc`](https://cubic-bezier.com/#0,.55,.45,1)
- [`easeInOutCirc`](https://cubic-bezier.com/#.85,0,.15,1)
- [`easeInBack`](https://cubic-bezier.com/#.36,0,.66,-.56)
- [`easeOutBack`](https://cubic-bezier.com/#.34,1.56,.64,1)
- [`easeInOutBack`](https://cubic-bezier.com/#.68,-.6,.32,1.6)

For more complex easing, a custom function can be provided.

```ts
import { useTransition } from '@vueuse/core'
// ---cut---
function easeOutElastic(n) {
  return n === 0
    ? 0
    : n === 1
      ? 1
      : (2 ** (-10 * n)) * Math.sin((n * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1
}

useTransition(source, {
  easing: easeOutElastic,
})
```

By default the `source` must be a number, or array of numbers. For more complex values, define a custom `interpolation` function. For example, the following would transition a Three.js rotation.

```ts
import { useTransition } from '@vueuse/core'
// ---cut---
import { Quaternion } from 'three'

const source = ref(new Quaternion())

const output = useTransition(source, {
  interpolation: (q1, q2, t) => new Quaternion().slerpQuaternions(q1, q2, t)
})
```

To control when a transition starts, set a `delay` value. To choreograph behavior around a transition, define `onStarted` or `onFinished` callbacks.

```ts
import { useTransition } from '@vueuse/core'
// ---cut---
useTransition(source, {
  delay: 1000,
  onStarted() {
    // called after the transition starts
  },
  onFinished() {
    // called after the transition ends
  },
})
```

To stop transitioning, define a boolean `disabled` property. Be aware, this is not the same a `duration` of `0`. Disabled transitions track the source value **_synchronously_**. They do not respect a `delay`, and do not fire `onStarted` or `onFinished` callbacks.

For even more control, transitions can be executed manually via the `transition` function. This function returns a promise that resolves when the transition is complete. Manual transitions can be cancelled by defining an `abort` function that returns a truthy value.

```ts
import { transition } from '@vueuse/core'

await transition(source, from, to, {
  abort() {
    if (shouldAbort)
      return true
  }
})
```

## Type Declarations

```ts
/**
 * Cubic bezier points
 */
export type CubicBezierPoints = [number, number, number, number]
/**
 * Easing function
 */
export type EasingFunction = (n: number) => number
/**
 * Interpolation function
 */
export type InterpolationFunction<T> = (from: T, to: T, t: number) => T
/**
 * Transition options
 */
export interface TransitionOptions<T> extends ConfigurableWindow {
  /**
   * Manually abort a transition
   */
  abort?: () => any
  /**
   * Transition duration in milliseconds
   */
  duration?: MaybeRef<number>
  /**
   * Easing function or cubic bezier points to calculate transition progress
   */
  easing?: MaybeRef<EasingFunction | CubicBezierPoints>
  /**
   * Custom interpolation function
   */
  interpolation?: InterpolationFunction<T>
  /**
   * Easing function or cubic bezier points to calculate transition progress
   * @deprecated The `transition` option is deprecated, use `easing` instead.
   */
  transition?: MaybeRef<EasingFunction | CubicBezierPoints>
}
export interface UseTransitionOptions<T> extends TransitionOptions<T> {
  /**
   * Milliseconds to wait before starting transition
   */
  delay?: MaybeRef<number>
  /**
   * Disables the transition
   */
  disabled?: MaybeRef<boolean>
  /**
   * Callback to execute after transition finishes
   */
  onFinished?: () => void
  /**
   * Callback to execute after transition starts
   */
  onStarted?: () => void
}
declare const _TransitionPresets: {
  readonly easeInSine: readonly [0.12, 0, 0.39, 0]
  readonly easeOutSine: readonly [0.61, 1, 0.88, 1]
  readonly easeInOutSine: readonly [0.37, 0, 0.63, 1]
  readonly easeInQuad: readonly [0.11, 0, 0.5, 0]
  readonly easeOutQuad: readonly [0.5, 1, 0.89, 1]
  readonly easeInOutQuad: readonly [0.45, 0, 0.55, 1]
  readonly easeInCubic: readonly [0.32, 0, 0.67, 0]
  readonly easeOutCubic: readonly [0.33, 1, 0.68, 1]
  readonly easeInOutCubic: readonly [0.65, 0, 0.35, 1]
  readonly easeInQuart: readonly [0.5, 0, 0.75, 0]
  readonly easeOutQuart: readonly [0.25, 1, 0.5, 1]
  readonly easeInOutQuart: readonly [0.76, 0, 0.24, 1]
  readonly easeInQuint: readonly [0.64, 0, 0.78, 0]
  readonly easeOutQuint: readonly [0.22, 1, 0.36, 1]
  readonly easeInOutQuint: readonly [0.83, 0, 0.17, 1]
  readonly easeInExpo: readonly [0.7, 0, 0.84, 0]
  readonly easeOutExpo: readonly [0.16, 1, 0.3, 1]
  readonly easeInOutExpo: readonly [0.87, 0, 0.13, 1]
  readonly easeInCirc: readonly [0.55, 0, 1, 0.45]
  readonly easeOutCirc: readonly [0, 0.55, 0.45, 1]
  readonly easeInOutCirc: readonly [0.85, 0, 0.15, 1]
  readonly easeInBack: readonly [0.36, 0, 0.66, -0.56]
  readonly easeOutBack: readonly [0.34, 1.56, 0.64, 1]
  readonly easeInOutBack: readonly [0.68, -0.6, 0.32, 1.6]
}
/**
 * Common transitions
 *
 * @see https://easings.net
 */
export declare const TransitionPresets: Record<
  keyof typeof _TransitionPresets,
  CubicBezierPoints
> & {
  linear: EasingFunction
}
/**
 * Transition from one value to another.
 *
 * @param source
 * @param from
 * @param to
 * @param options
 */
export declare function transition<T>(
  source: Ref<T>,
  from: MaybeRefOrGetter<T>,
  to: MaybeRefOrGetter<T>,
  options?: TransitionOptions<T>,
): PromiseLike<void>
/**
 * Transition from one value to another.
 * @deprecated The `executeTransition` function is deprecated, use `transition` instead.
 *
 * @param source
 * @param from
 * @param to
 * @param options
 */
export declare function executeTransition<T>(
  source: Ref<T>,
  from: MaybeRefOrGetter<T>,
  to: MaybeRefOrGetter<T>,
  options?: TransitionOptions<T>,
): PromiseLike<void>
export declare function useTransition<T extends MaybeRefOrGetter<number>[]>(
  source: [...T],
  options?: UseTransitionOptions<T>,
): ComputedRef<{
  [K in keyof T]: number
}>
export declare function useTransition<T extends MaybeRefOrGetter<number[]>>(
  source: T,
  options?: UseTransitionOptions<T>,
): ComputedRef<number[]>
export declare function useTransition<T>(
  source: MaybeRefOrGetter<T>,
  options?: UseTransitionOptions<T>,
): ComputedRef<T>
```

---

<!-- source: references/useTrunc.md -->
---
category: '@Math'
---

# useTrunc

Reactive `Math.trunc`.

## Usage

```ts
import { useTrunc } from '@vueuse/math'

const value1 = ref(0.95)
const value2 = ref(-2.34)
const result1 = useTrunc(value1) // 0
const result2 = useTrunc(value2) // -2
```

## Type Declarations

```ts
/**
 * Reactive `Math.trunc`.
 *
 * @see https://vueuse.org/useTrunc
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useTrunc(
  value: MaybeRefOrGetter<number>,
): ComputedRef<number>
```

---

<!-- source: references/useUrlSearchParams.md -->
---
category: Browser
---

# useUrlSearchParams

Reactive [URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams)

## Usage

```ts
import { useUrlSearchParams } from '@vueuse/core'

const params = useUrlSearchParams('history')

console.log(params.foo) // 'bar'

params.foo = 'bar'
params.vueuse = 'awesome'
// url updated to `?foo=bar&vueuse=awesome`
```

### Hash Mode

When using with hash mode route, specify the `mode` to `hash`

```ts
import { useUrlSearchParams } from '@vueuse/core'

const params = useUrlSearchParams('hash')

params.foo = 'bar'
params.vueuse = 'awesome'
// url updated to `#/your/route?foo=bar&vueuse=awesome`
```

### Hash Params

When using with history mode route, but want to use hash as params, specify the `mode` to `hash-params`

```ts
import { useUrlSearchParams } from '@vueuse/core'

const params = useUrlSearchParams('hash-params')

params.foo = 'bar'
params.vueuse = 'awesome'
// url updated to `/your/route#foo=bar&vueuse=awesome`
```

### Custom Stringify Function

You can provide a custom function to serialize URL parameters using the `stringify` option. This is useful when you need special formatting for your query string.

```js
import { useUrlSearchParams } from '@vueuse/core'

// Custom stringify function that removes equal signs for empty values
const params = useUrlSearchParams('history', {
  stringify: (params) => {
    return params.toString().replace(/=(&|$)/g, '$1')
  }
})

params.foo = ''
params.bar = 'value'
// url updated to `?foo&bar=value` instead of `?foo=&bar=value`
```

## Type Declarations

```ts
export type UrlParams = Record<string, string[] | string>
export interface UseUrlSearchParamsOptions<T> extends ConfigurableWindow {
  /**
   * @default true
   */
  removeNullishValues?: boolean
  /**
   * @default false
   */
  removeFalsyValues?: boolean
  /**
   * @default {}
   */
  initialValue?: T
  /**
   * Write back to `window.history` automatically
   *
   * @default true
   */
  write?: boolean
  /**
   * Write mode for `window.history` when `write` is enabled
   * - `replace`: replace the current history entry
   * - `push`: push a new history entry
   * @default 'replace'
   */
  writeMode?: "replace" | "push"
  /**
   * Custom function to serialize URL parameters
   * When provided, this function will be used instead of the default URLSearchParams.toString()
   * @param params The URLSearchParams object to serialize
   * @returns The serialized query string (should not include the leading '?' or '#')
   */
  stringify?: (params: URLSearchParams) => string
}
/**
 * Reactive URLSearchParams
 *
 * @see https://vueuse.org/useUrlSearchParams
 * @param mode
 * @param options
 */
export declare function useUrlSearchParams<
  T extends Record<string, any> = UrlParams,
>(
  mode?: "history" | "hash" | "hash-params",
  options?: UseUrlSearchParamsOptions<T>,
): T
```

---

<!-- source: references/useUserMedia.md -->
---
category: Sensors
related: useDevicesList, usePermission
---

# useUserMedia

Reactive [`mediaDevices.getUserMedia`](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) streaming.

## Usage

```vue
<script setup lang="ts">
import { useUserMedia } from '@vueuse/core'
import { useTemplateRef, watchEffect } from 'vue'

const { stream, start } = useUserMedia()
start()

const videoRef = useTemplateRef('video')
watchEffect(() => {
  // preview on a video element
  videoRef.value.srcObject = stream.value
})
</script>

<template>
  <video ref="video" />
</template>
```

### Devices

```ts
import { useDevicesList, useUserMedia } from '@vueuse/core'
import { computed, reactive } from 'vue'

const {
  videoInputs: cameras,
  audioInputs: microphones,
} = useDevicesList({
  requestPermissions: true,
})
const currentCamera = computed(() => cameras.value[0]?.deviceId)
const currentMicrophone = computed(() => microphones.value[0]?.deviceId)

const { stream } = useUserMedia({
  constraints: reactive({
    video: { deviceId: currentCamera },
    audio: { deviceId: currentMicrophone, }
  })
})
```

## Type Declarations

```ts
export interface UseUserMediaOptions extends ConfigurableNavigator {
  /**
   * If the stream is enabled
   * @default false
   */
  enabled?: MaybeRef<boolean>
  /**
   * Recreate stream when deviceIds or constraints changed
   *
   * @default true
   */
  autoSwitch?: MaybeRef<boolean>
  /**
   * MediaStreamConstraints to be applied to the requested MediaStream
   * If provided, the constraints will override videoDeviceId and audioDeviceId
   *
   * @default {}
   */
  constraints?: MaybeRef<MediaStreamConstraints>
}
export interface UseUserMediaReturn extends Supportable {
  stream: Ref<MediaStream | undefined>
  start: () => Promise<MediaStream | undefined>
  stop: () => void
  restart: () => Promise<MediaStream | undefined>
  constraints: Ref<MediaStreamConstraints | undefined>
  enabled: ShallowRef<boolean>
  autoSwitch: ShallowRef<boolean>
}
/**
 * Reactive `mediaDevices.getUserMedia` streaming
 *
 * @see https://vueuse.org/useUserMedia
 * @param options
 */
export declare function useUserMedia(
  options?: UseUserMediaOptions,
): UseUserMediaReturn
```

---

<!-- source: references/useVModel.md -->
---
category: Component
---

# useVModel

Shorthand for v-model binding, props + emit -> ref

> We encourage you to use Vue's [`defineModel`](https://vuejs.org/api/sfc-script-setup.html#definemodel) over this composable, however there are some edge-cases like using `TSX` or the `deep: true` option that `defineModel` doesn't support.

## Usage

```ts
import { useVModel } from '@vueuse/core'

const props = defineProps<{
  modelValue: string
}>()
const emit = defineEmits(['update:modelValue'])

const data = useVModel(props, 'modelValue', emit)
```

### Options API

```ts
import { useVModel } from '@vueuse/core'

export default {
  setup(props, { emit }) {
    const data = useVModel(props, 'data', emit)

    console.log(data.value) // props.data
    data.value = 'foo' // emit('update:data', 'foo')
  },
}
```

## Options

### Passive Mode

By default, `useVModel` returns a computed ref. In passive mode, it creates a local ref that syncs with the prop via `watch`, allowing deep reactivity tracking.

```ts
const data = useVModel(props, 'modelValue', emit, { passive: true })
```

### Deep Watching

When using `passive: true`, you can enable deep watching for nested object changes:

```ts
const data = useVModel(props, 'modelValue', emit, {
  passive: true,
  deep: true,
})
```

### Clone Values

Clone the prop value to avoid mutating the original object. Set to `true` to use `JSON.parse(JSON.stringify())` or provide a custom clone function.

```ts
const data = useVModel(props, 'modelValue', emit, {
  clone: true,
  // or provide custom clone function
  // clone: (val) => structuredClone(val),
})
```

### Default Value

Provide a default value when the prop is undefined:

```ts
const data = useVModel(props, 'modelValue', emit, {
  defaultValue: 'default',
})
```

### Custom Event Name

Override the default `update:propName` event name:

```ts
const data = useVModel(props, 'value', emit, {
  eventName: 'change',
})
```

### Emit Validation

Use `shouldEmit` to validate before emitting. Return `false` to prevent the emit:

```ts
const data = useVModel(props, 'modelValue', emit, {
  shouldEmit: (value) => {
    // Only emit if value is valid
    return value.length > 0
  },
})
```

## Type Declarations

```ts
export interface UseVModelOptions<T, Passive extends boolean = false> {
  /**
   * When passive is set to `true`, it will use `watch` to sync with props and ref.
   * Instead of relying on the `v-model` or `.sync` to work.
   *
   * @default false
   */
  passive?: Passive
  /**
   * When eventName is set, it's value will be used to overwrite the emit event name.
   *
   * @default undefined
   */
  eventName?: string
  /**
   * Attempting to check for changes of properties in a deeply nested object or array.
   * Apply only when `passive` option is set to `true`
   *
   * @default false
   */
  deep?: boolean
  /**
   * Defining default value for return ref when no value is passed.
   *
   * @default undefined
   */
  defaultValue?: T
  /**
   * Clone the props.
   * Accepts a custom clone function.
   * When setting to `true`, it will use `JSON.parse(JSON.stringify(value))` to clone.
   *
   * @default false
   */
  clone?: boolean | CloneFn<T>
  /**
   * The hook before triggering the emit event can be used for form validation.
   * if false is returned, the emit event will not be triggered.
   *
   * @default undefined
   */
  shouldEmit?: (v: T) => boolean
}
/**
 * Shorthand for v-model binding, props + emit -> ref
 *
 * @see https://vueuse.org/useVModel
 * @param props
 * @param key (default 'modelValue')
 * @param emit
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useVModel<
  P extends object,
  K extends keyof P,
  Name extends string,
>(
  props: P,
  key?: K,
  emit?: (name: Name, ...args: any[]) => void,
  options?: UseVModelOptions<P[K], false>,
): WritableComputedRef<P[K]>
export declare function useVModel<
  P extends object,
  K extends keyof P,
  Name extends string,
>(
  props: P,
  key?: K,
  emit?: (name: Name, ...args: any[]) => void,
  options?: UseVModelOptions<P[K], true>,
): Ref<UnwrapRef<P[K]>>
```

---

<!-- source: references/useVModels.md -->
---
category: Component
related: useVModel
---

# useVModels

Shorthand for props v-model binding. Think it like `toRefs(props)` but changes will also trigger emit.

## Usage

```ts
import { useVModels } from '@vueuse/core'

const props = defineProps({
  foo: string,
  bar: number,
})

const emit = defineEmits(['update:foo', 'update:bar'])

const { foo, bar } = useVModels(props, emit)
```

### Options API

```ts
import { useVModels } from '@vueuse/core'

export default {
  props: {
    foo: String,
    bar: Number,
  },
  setup(props, { emit }) {
    const { foo, bar } = useVModels(props, emit)

    console.log(foo.value) // props.foo
    foo.value = 'foo' // emit('update:foo', 'foo')
  },
}
```

## Type Declarations

```ts
/**
 * Shorthand for props v-model binding. Think like `toRefs(props)` but changes will also emit out.
 *
 * @see https://vueuse.org/useVModels
 * @param props
 * @param emit
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useVModels<P extends object, Name extends string>(
  props: P,
  emit?: (name: Name, ...args: any[]) => void,
  options?: UseVModelOptions<any, true>,
): ToRefs<P>
export declare function useVModels<P extends object, Name extends string>(
  props: P,
  emit?: (name: Name, ...args: any[]) => void,
  options?: UseVModelOptions<any, false>,
): ToRefs<P>
```

---

<!-- source: references/useVibrate.md -->
---
category: Browser
---

# useVibrate

Reactive [Vibration API](https://developer.mozilla.org/en-US/docs/Web/API/Vibration_API)

Most modern mobile devices include vibration hardware, which lets software
code provides physical feedback to the user by causing the device to shake.

The Vibration API offers Web apps the ability to access this hardware,
if it exists, and does nothing if the device doesn't support it.

## Usage

Vibration is described as a pattern of on-off pulses, which may be of varying
lengths.

The pattern may consist of either a single integer describing the
number of milliseconds to vibrate, or an array of integers describing
a pattern of vibrations and pauses.

```ts
import { useVibrate } from '@vueuse/core'

// This vibrates the device for 300 ms
// then pauses for 100 ms before vibrating the device again for another 300 ms:
const { vibrate, stop, isSupported } = useVibrate({ pattern: [300, 100, 300] })

// Start the vibration, it will automatically stop when the pattern is complete:
vibrate()

// But if you want to stop it, you can:
stop()
```

## Type Declarations

```ts
export interface UseVibrateOptions
  extends ConfigurableNavigator, ConfigurableScheduler {
  /**
   *
   * Vibration Pattern
   *
   * An array of values describes alternating periods in which the
   * device is vibrating and not vibrating. Each value in the array
   * is converted to an integer, then interpreted alternately as
   * the number of milliseconds the device should vibrate and the
   * number of milliseconds it should not be vibrating
   *
   * @default []
   *
   */
  pattern?: MaybeRefOrGetter<Arrayable<number>>
  /**
   * Interval to run a persistent vibration, in ms
   *
   * Pass `0` to disable
   *
   * @deprecated Please use `scheduler` option instead
   * @default 0
   *
   */
  interval: number
}
export interface UseVibrateReturn extends Supportable {
  pattern: MaybeRefOrGetter<Arrayable<number>>
  intervalControls?: Pausable
  vibrate: (pattern?: Arrayable<number>) => void
  stop: () => void
}
/**
 * Reactive vibrate
 *
 * @see https://vueuse.org/useVibrate
 * @see https://developer.mozilla.org/en-US/docs/Web/API/Vibration_API
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useVibrate(
  options?: UseVibrateOptions,
): UseVibrateReturn
```

---

<!-- source: references/useVirtualList.md -->
---
category: Component
---

# useVirtualList

::: warning
Consider using [`@tanstack/vue-virtual`](https://tanstack.com/virtual/v3/docs/framework/vue/vue-virtual) instead, if you are looking for more features.
:::

Create virtual lists with ease. Virtual lists (sometimes called [_virtual scrollers_](https://vue-virtual-scroller-demo.netlify.app/)) allow you to render a large number of items performantly. They only render the minimum number of DOM nodes necessary to show the items within the `container` element by using the `wrapper` element to emulate the container element's full height.

## Usage

### Simple list

```ts
import { useVirtualList } from '@vueuse/core'

const { list, containerProps, wrapperProps } = useVirtualList(
  Array.from(Array.from({ length: 99999 }).keys()),
  {
    // Keep `itemHeight` in sync with the item's row.
    itemHeight: 22,
  },
)
```

### Config

| State      | Type     | Description                                                                                     |
| ---------- | -------- | ----------------------------------------------------------------------------------------------- |
| itemHeight | `number` | ensure that the total height of the `wrapper` element is calculated correctly.\*                |
| itemWidth  | `number` | ensure that the total width of the `wrapper` element is calculated correctly.\*                 |
| overscan   | `number` | number of pre-rendered DOM nodes. Prevents whitespace between items if you scroll very quickly. |

\* The `itemHeight` or `itemWidth` must be kept in sync with the height of each row rendered. If you are seeing extra whitespace or jitter when scrolling to the bottom of the list, ensure the `itemHeight` or `itemWidth` is the same height as the row.

### Reactive list

```ts
import { useToggle, useVirtualList } from '@vueuse/core'
import { computed } from 'vue'

const [isEven, toggle] = useToggle()
const allItems = Array.from(Array.from({ length: 99999 }).keys())
const filteredList = computed(() => allItems.filter(i => isEven.value ? i % 2 === 0 : i % 2 === 1))

const { list, containerProps, wrapperProps } = useVirtualList(
  filteredList,
  {
    itemHeight: 22,
  },
)
```

```vue
<template>
  <p>Showing {{ isEven ? 'even' : 'odd' }} items</p>
  <button @click="toggle">
    Toggle Even/Odd
  </button>
  <div v-bind="containerProps" style="height: 300px">
    <div v-bind="wrapperProps">
      <div v-for="item in list" :key="item.index" style="height: 22px">
        Row: {{ item.data }}
      </div>
    </div>
  </div>
</template>
```

### Horizontal list

```ts
import { useVirtualList } from '@vueuse/core'

const allItems = Array.from(Array.from({ length: 99999 }).keys())

const { list, containerProps, wrapperProps } = useVirtualList(
  allItems,
  {
    itemWidth: 200,
  },
)
```

```vue
<template>
  <div v-bind="containerProps" style="height: 300px">
    <div v-bind="wrapperProps">
      <div v-for="item in list" :key="item.index" style="width: 200px">
        Row: {{ item.data }}
      </div>
    </div>
  </div>
</template>
```

## Component Usage

```vue
<template>
  <UseVirtualList :list="list" :options="options" height="300px">
    <template #default="props">
      <!-- you can get current item of list here -->
      <div style="height: 22px">
        Row {{ props.index }} {{ props.data }}
      </div>
    </template>
  </UseVirtualList>
</template>
```

To scroll to a specific element, the component exposes `scrollTo(index: number) => void`.

## Type Declarations

```ts
type UseVirtualListItemSize = number | ((index: number) => number)
export interface UseHorizontalVirtualListOptions extends UseVirtualListOptionsBase {
  /**
   * item width, accept a pixel value or a function that returns the width
   *
   * @default 0
   */
  itemWidth: UseVirtualListItemSize
}
export interface UseVerticalVirtualListOptions extends UseVirtualListOptionsBase {
  /**
   * item height, accept a pixel value or a function that returns the height
   *
   * @default 0
   */
  itemHeight: UseVirtualListItemSize
}
export interface UseVirtualListOptionsBase {
  /**
   * the extra buffer items outside of the view area
   *
   * @default 5
   */
  overscan?: number
}
export type UseVirtualListOptions =
  | UseHorizontalVirtualListOptions
  | UseVerticalVirtualListOptions
export interface UseVirtualListItem<T> {
  data: T
  index: number
}
export interface UseVirtualListReturn<T> {
  list: Ref<UseVirtualListItem<T>[]>
  scrollTo: (index: number) => void
  containerProps: {
    ref: Ref<HTMLElement | null>
    onScroll: () => void
    style: StyleValue
  }
  wrapperProps: ComputedRef<{
    style:
      | {
          width: string
          height: string
          marginTop: string
        }
      | {
          width: string
          height: string
          marginLeft: string
          display: string
        }
  }>
}
/**
 * Please consider using [`vue-virtual-scroller`](https://github.com/Akryum/vue-virtual-scroller) if you are looking for more features.
 */
export declare function useVirtualList<T = any>(
  list: MaybeRef<readonly T[]>,
  options: UseVirtualListOptions,
): UseVirtualListReturn<T>
```

---

<!-- source: references/useWakeLock.md -->
---
category: Browser
---

# useWakeLock

Reactive [Screen Wake Lock API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API). Provides a way to prevent devices from dimming or locking the screen when an application needs to keep running.

## Usage

```ts
import { useWakeLock } from '@vueuse/core'

const { isSupported, isActive, forceRequest, request, release } = useWakeLock()
```

When `request` is called, the wake lock will be requested if the document is visible. Otherwise, the request will be queued until the document becomes visible. If the request is successful, `isActive` will be **true**. Whenever the document is hidden, the `isActive` will be **false**.

When `release` is called, the wake lock will be released. If there is a queued request, it will be canceled.

To request a wake lock immediately, even if the document is hidden, use `forceRequest`. Note that this may throw an error if the document is hidden.

## Type Declarations

```ts
type WakeLockType = "screen"
export interface WakeLockSentinel extends EventTarget {
  type: WakeLockType
  released: boolean
  release: () => Promise<void>
}
export type UseWakeLockOptions = ConfigurableNavigator & ConfigurableDocument
export interface UseWakeLockReturn extends Supportable {
  sentinel: ShallowRef<WakeLockSentinel | null>
  isActive: ComputedRef<boolean>
  request: (type: WakeLockType) => Promise<void>
  forceRequest: (type: WakeLockType) => Promise<void>
  release: () => Promise<void>
}
/**
 * Reactive Screen Wake Lock API.
 *
 * @see https://vueuse.org/useWakeLock
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useWakeLock(
  options?: UseWakeLockOptions,
): UseWakeLockReturn
```

---

<!-- source: references/useWebNotification.md -->
---
category: Browser
---

# useWebNotification

Reactive [Notification](https://developer.mozilla.org/en-US/docs/Web/API/notification)

The Web Notification interface of the Notifications API is used to configure and display desktop notifications to the user.

## Usage

::: tip
Before an app can send a notification, the user must grant the application the right to do so. The user's OS settings may also prevent expected notification behaviour.
:::

```ts
import { useWebNotification } from '@vueuse/core'

const {
  isSupported,
  notification,
  permissionGranted,
  show,
  close,
  onClick,
  onShow,
  onError,
  onClose,
} = useWebNotification({
  title: 'Hello, VueUse world!',
  dir: 'auto',
  lang: 'en',
  renotify: true,
  tag: 'test',
})

if (isSupported.value && permissionGranted.value)
  show()
```

This composable also utilizes the createEventHook utility from '@vueuse/shared`:

```ts
import { useWebNotification } from '@vueuse/core'

const { onClick, onShow, onError, onClose, } = useWebNotification()
// ---cut---
onClick((evt: Event) => {
  // Do something with the notification on:click event...
})

onShow((evt: Event) => {
  // Do something with the notification on:show event...
})

onError((evt: Event) => {
  // Do something with the notification on:error event...
})

onClose((evt: Event) => {
  // Do something with the notification on:close event...
})
```

## Type Declarations

```ts
export interface WebNotificationOptions {
  /**
   * The title read-only property of the Notification interface indicates
   * the title of the notification
   *
   * @default ''
   */
  title?: string
  /**
   * The body string of the notification as specified in the constructor's
   * options parameter.
   *
   * @default ''
   */
  body?: string
  /**
   * The text direction of the notification as specified in the constructor's
   * options parameter.
   *
   * @default ''
   */
  dir?: "auto" | "ltr" | "rtl"
  /**
   * The language code of the notification as specified in the constructor's
   * options parameter.
   *
   * @default DOMString
   */
  lang?: string
  /**
   * The ID of the notification(if any) as specified in the constructor's options
   * parameter.
   *
   * @default ''
   */
  tag?: string
  /**
   * The URL of the image used as an icon of the notification as specified
   * in the constructor's options parameter.
   *
   * @default ''
   */
  icon?: string
  /**
   * Specifies whether the user should be notified after a new notification
   * replaces an old one.
   *
   * @default false
   */
  renotify?: boolean
  /**
   * A boolean value indicating that a notification should remain active until the
   * user clicks or dismisses it, rather than closing automatically.
   *
   * @default false
   */
  requireInteraction?: boolean
  /**
   * The silent read-only property of the Notification interface specifies
   * whether the notification should be silent, i.e., no sounds or vibrations
   * should be issued, regardless of the device settings.
   *
   * @default false
   */
  silent?: boolean
  /**
   * Specifies a vibration pattern for devices with vibration hardware to emit.
   * A vibration pattern, as specified in the Vibration API spec
   *
   * @see https://w3c.github.io/vibration/
   */
  vibrate?: number[]
}
export interface UseWebNotificationOptions
  extends ConfigurableWindow, WebNotificationOptions {
  /**
   * Request for permissions onMounted if it's not granted.
   *
   * Can be disabled and calling `ensurePermissions` to grant afterwords.
   *
   * @default true
   */
  requestPermissions?: boolean
}
export interface UseWebNotificationReturn extends Supportable {
  notification: Ref<Notification | null>
  ensurePermissions: () => Promise<boolean | undefined>
  permissionGranted: ShallowRef<boolean>
  show: (
    overrides?: WebNotificationOptions,
  ) => Promise<Notification | undefined>
  close: () => void
  onClick: EventHookOn<Event>
  onShow: EventHookOn<Event>
  onError: EventHookOn<Event>
  onClose: EventHookOn<Event>
}
/**
 * Reactive useWebNotification
 *
 * @see https://vueuse.org/useWebNotification
 * @see https://developer.mozilla.org/en-US/docs/Web/API/notification
 */
export declare function useWebNotification(
  options?: UseWebNotificationOptions,
): UseWebNotificationReturn
```

---

<!-- source: references/useWebSocket.md -->
---
category: Network
---

# useWebSocket

Reactive [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket) client.

## Usage

```ts
import { useWebSocket } from '@vueuse/core'

const { status, data, send, open, close, ws } = useWebSocket('ws://websocketurl')
```

### Return Values

| Property | Type                                      | Description                          |
| -------- | ----------------------------------------- | ------------------------------------ |
| `data`   | `Ref<any>`                                | Latest received data                 |
| `status` | `Ref<'OPEN' \| 'CONNECTING' \| 'CLOSED'>` | Connection status                    |
| `ws`     | `Ref<WebSocket>`                          | WebSocket instance                   |
| `send`   | `(data, useBuffer?) => boolean`           | Send data (buffers if not connected) |
| `open`   | `() => void`                              | Open/reconnect the connection        |
| `close`  | `(code?, reason?) => void`                | Close the connection                 |

### Callbacks

```ts
const { data } = useWebSocket('ws://websocketurl', {
  onConnected(ws) {
    console.log('Connected!')
  },
  onDisconnected(ws, event) {
    console.log('Disconnected!', event.code)
  },
  onError(ws, event) {
    console.error('Error:', event)
  },
  onMessage(ws, event) {
    console.log('Message:', event.data)
  },
})
```

See the [Type Declarations](#type-declarations) for more options.

### immediate

Enable by default.

Establish the connection immediately when the composable is called.

### autoConnect

Enable by default.

If a URL is provided as a ref, when the URL changes, it will automatically reconnect to the new URL.

### autoClose

Enable by default.

This will call `close()` automatically when the `beforeunload` event is triggered or the associated effect scope is stopped.

### autoReconnect

Reconnect on errors automatically (disabled by default).

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, close } = useWebSocket('ws://websocketurl', {
  autoReconnect: true,
})
```

Or with more controls over its behavior:

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, close } = useWebSocket('ws://websocketurl', {
  autoReconnect: {
    retries: 3,
    delay: 1000,
    onFailed() {
      alert('Failed to connect WebSocket after 3 retries')
    },
  },
})
```

You can also pass a function to `delay` to calculate the delay based on the number of retries. This is useful for implementing exponential backoff:

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, close } = useWebSocket('ws://websocketurl', {
  autoReconnect: {
    retries: 5,
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s
    delay: retries => Math.min(1000 * 2 ** (retries - 1), 30000),
  },
})
```

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, close } = useWebSocket('ws://websocketurl', {
  autoReconnect: {
    retries: 5,
    // Linear backoff: 1s, 2s, 3s, 4s, 5s
    delay: retries => retries * 1000,
  },
})
```

Explicitly calling `close()` won't trigger the auto reconnection.

### heartbeat

It's common practice to send a small message (heartbeat) for every given time passed to keep the connection active. In this function we provide a convenient helper to do it:

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, close } = useWebSocket('ws://websocketurl', {
  heartbeat: true,
})
```

Or with more controls:

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, close } = useWebSocket('ws://websocketurl', {
  heartbeat: {
    message: 'ping',
    scheduler: cb => useIntervalFn(cb, 2000),
    pongTimeout: 1000,
  },
})
```

### Sub-protocols

List of one or more subprotocols to use, in this case SOAP and WAMP.

```ts
import { useWebSocket } from '@vueuse/core'
// ---cut---
const { status, data, send, open, close } = useWebSocket('ws://websocketurl', {
  protocols: ['soap'], // ['soap', 'wamp']
})
```

## Type Declarations

```ts
export type WebSocketStatus = "OPEN" | "CONNECTING" | "CLOSED"
export type WebSocketHeartbeatMessage = string | ArrayBuffer | Blob
export interface UseWebSocketOptions {
  onConnected?: (ws: WebSocket) => void
  onDisconnected?: (ws: WebSocket, event: CloseEvent) => void
  onError?: (ws: WebSocket, event: Event) => void
  onMessage?: (ws: WebSocket, event: MessageEvent) => void
  /**
   * Send heartbeat for every x milliseconds passed
   *
   * @default false
   */
  heartbeat?:
    | boolean
    | (ConfigurableScheduler & {
        /**
         * Message for the heartbeat
         *
         * @default 'ping'
         */
        message?: MaybeRefOrGetter<WebSocketHeartbeatMessage>
        /**
         * Response message for the heartbeat, if undefined the message will be used
         */
        responseMessage?: MaybeRefOrGetter<WebSocketHeartbeatMessage>
        /**
         * Interval, in milliseconds
         *
         * @deprecated Please use `scheduler` option instead
         * @default 1000
         */
        interval?: number
        /**
         * Heartbeat response timeout, in milliseconds
         *
         * @default 1000
         */
        pongTimeout?: number
      })
  /**
   * Enabled auto reconnect
   *
   * @default false
   */
  autoReconnect?:
    | boolean
    | {
        /**
         * Maximum retry times.
         *
         * Or you can pass a predicate function (which returns true if you want to retry).
         *
         * @default -1
         */
        retries?: number | ((retried: number) => boolean)
        /**
         * Delay for reconnect, in milliseconds
         *
         * Or you can pass a function to calculate the delay based on the number of retries.
         *
         * @default 1000
         */
        delay?: number | ((retries: number) => number)
        /**
         * On maximum retry times reached.
         */
        onFailed?: Fn
      }
  /**
   * Immediately open the connection when calling this composable
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Automatically connect to the websocket when URL changes
   *
   * @default true
   */
  autoConnect?: boolean
  /**
   * Automatically close a connection
   *
   * @default true
   */
  autoClose?: boolean
  /**
   * List of one or more sub-protocol strings
   *
   * @default []
   */
  protocols?: string[]
}
export interface UseWebSocketReturn<T> {
  /**
   * Reference to the latest data received via the websocket,
   * can be watched to respond to incoming messages
   */
  data: Ref<T | null>
  /**
   * The current websocket status, can be only one of:
   * 'OPEN', 'CONNECTING', 'CLOSED'
   */
  status: ShallowRef<WebSocketStatus>
  /**
   * Closes the websocket connection gracefully.
   */
  close: WebSocket["close"]
  /**
   * Reopen the websocket connection.
   * If there the current one is active, will close it before opening a new one.
   */
  open: Fn
  /**
   * Sends data through the websocket connection.
   *
   * @param data
   * @param useBuffer when the socket is not yet open, store the data into the buffer and sent them one connected. Default to true.
   */
  send: (data: string | ArrayBuffer | Blob, useBuffer?: boolean) => boolean
  /**
   * Reference to the WebSocket instance.
   */
  ws: Ref<WebSocket | undefined>
}
/**
 * Reactive WebSocket client.
 *
 * @see https://vueuse.org/useWebSocket
 * @param url
 */
export declare function useWebSocket<Data = any>(
  url: MaybeRefOrGetter<string | URL | undefined>,
  options?: UseWebSocketOptions,
): UseWebSocketReturn<Data>
```

---

<!-- source: references/useWebWorker.md -->
---
category: Browser
related: useWebWorkerFn
---

# useWebWorker

Simple [Web Workers](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Using_web_workers) registration and communication.

## Usage

```ts
import { useWebWorker } from '@vueuse/core'

const { data, post, terminate, worker } = useWebWorker('/path/to/worker.js')
```

| State  | Type                              | Description                                                                                          |
| ------ | --------------------------------- | ---------------------------------------------------------------------------------------------------- |
| data   | `Ref<any>`                        | Reference to the latest data received via the worker, can be watched to respond to incoming messages |
| worker | `ShallowRef<Worker \| undefined>` | Reference to the instance of the WebWorker                                                           |

| Method    | Signature                                                                                                                     | Description                      |
| --------- | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| post      | `(message: any, transfer: Transferable[]): void`<br>`(message: any, options?: StructuredSerializeOptions \| undefined): void` | Sends data to the worker thread. |
| terminate | `() => void`                                                                                                                  | Stops and terminates the worker. |

## Type Declarations

```ts
type PostMessage = (typeof Worker.prototype)["postMessage"]
export interface UseWebWorkerReturn<Data = any> {
  data: Ref<Data>
  post: PostMessage
  terminate: () => void
  worker: ShallowRef<Worker | undefined>
}
type WorkerFn = (...args: unknown[]) => Worker
/**
 * Simple Web Workers registration and communication.
 *
 * @see https://vueuse.org/useWebWorker
 * @param url
 * @param workerOptions
 * @param options
 */
export declare function useWebWorker<T = any>(
  url: string,
  workerOptions?: WorkerOptions,
  options?: ConfigurableWindow,
): UseWebWorkerReturn<T>
/**
 * Simple Web Workers registration and communication.
 *
 * @see https://vueuse.org/useWebWorker
 */
export declare function useWebWorker<T = any>(
  worker: Worker | WorkerFn,
): UseWebWorkerReturn<T>
```

---

<!-- source: references/useWebWorkerFn.md -->
---
category: Browser
---

# useWebWorkerFn

Run expensive functions without blocking the UI, using a simple syntax that makes use of Promise. A port of [alewin/useWorker](https://github.com/alewin/useWorker).

## Usage

### Basic example

```ts
import { useWebWorkerFn } from '@vueuse/core'

const { workerFn } = useWebWorkerFn(() => {
  // some heavy works to do in web worker
})
```

### With dependencies

```ts {7-9}
import { useWebWorkerFn } from '@vueuse/core'

const { workerFn, workerStatus, workerTerminate } = useWebWorkerFn(
  dates => dates.sort(dateFns.compareAsc),
  {
    timeout: 50000,
    dependencies: [
      'https://cdnjs.cloudflare.com/ajax/libs/date-fns/1.30.1/date_fns.js', // dateFns
    ],
  },
)
```

### With local dependencies

```ts {9-9}
import { useWebWorkerFn } from '@vueuse/core'

const pow = (a: number) => a * a

const { workerFn, workerStatus, workerTerminate } = useWebWorkerFn(
  numbers => pow(numbers),
  {
    timeout: 50000,
    localDependencies: [pow]
  },
)
```

## Web Worker

Before you start using this function, we suggest you read the [Web Worker](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Using_web_workers) documentation.

## Credit

This function is a Vue port of https://github.com/alewin/useWorker by Alessio Koci, with the help of [@Donskelle](https://github.com/Donskelle) to migration.

## Type Declarations

```ts
export type WebWorkerStatus =
  | "PENDING"
  | "SUCCESS"
  | "RUNNING"
  | "ERROR"
  | "TIMEOUT_EXPIRED"
export interface UseWebWorkerOptions extends ConfigurableWindow {
  /**
   * Number of milliseconds before killing the worker
   *
   * @default undefined
   */
  timeout?: number
  /**
   * An array that contains the external dependencies needed to run the worker
   */
  dependencies?: string[]
  /**
   * An array that contains the local dependencies needed to run the worker
   */
  localDependencies?: Function[]
}
export interface UseWebWorkerFnReturn<T extends (...fnArgs: any[]) => any> {
  workerFn: (...fnArgs: Parameters<T>) => Promise<ReturnType<T>>
  workerStatus: ShallowRef<WebWorkerStatus>
  workerTerminate: (status?: WebWorkerStatus) => void
}
/**
 * Run expensive function without blocking the UI, using a simple syntax that makes use of Promise.
 *
 * @see https://vueuse.org/useWebWorkerFn
 * @param fn
 * @param options
 */
export declare function useWebWorkerFn<T extends (...fnArgs: any[]) => any>(
  fn: T,
  options?: UseWebWorkerOptions,
): UseWebWorkerFnReturn<T>
```

---

<!-- source: references/useWindowFocus.md -->
---
category: Elements
---

# useWindowFocus

Reactively track window focus with `window.onfocus` and `window.onblur` events.

## Usage

```vue
<script setup lang="ts">
import { useWindowFocus } from '@vueuse/core'

const focused = useWindowFocus()
</script>

<template>
  <div>{{ focused }}</div>
</template>
```

## Component Usage

```vue
<template>
  <UseWindowFocus v-slot="{ focused }">
    Document Focus: {{ focused }}
  </UseWindowFocus>
</template>
```

## Type Declarations

```ts
/**
 * Reactively track window focus with `window.onfocus` and `window.onblur`.
 *
 * @see https://vueuse.org/useWindowFocus
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useWindowFocus(
  options?: ConfigurableWindow,
): ShallowRef<boolean>
```

---

<!-- source: references/useWindowScroll.md -->
---
category: Elements
---

# useWindowScroll

Reactive window scroll

## Usage

```vue
<script setup lang="ts">
import { useWindowScroll } from '@vueuse/core'

const { x, y } = useWindowScroll()
</script>

<template>
  <div>
    read current x, y scroll: {{ x }}, {{ y }}
  </div>
  <button @click="x = 100">
    scroll X to 100
  </button>
  <button @click="y = 100">
    scroll Y to 100
  </button>
</template>
```

## Type Declarations

```ts
export interface UseWindowScrollOptions
  extends ConfigurableWindow, UseScrollOptions {}
export interface UseWindowScrollReturn extends UseScrollReturn {}
/**
 * Reactive window scroll.
 *
 * @see https://vueuse.org/useWindowScroll
 * @param options
 */
export declare function useWindowScroll(
  options?: UseWindowScrollOptions,
): UseWindowScrollReturn
```

---

<!-- source: references/useWindowSize.md -->
---
category: Elements
---

# useWindowSize

Reactive window size

## Usage

```vue
<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'

const { width, height } = useWindowSize()
</script>

<template>
  <div>
    Width: {{ width }}
    Height: {{ height }}
  </div>
</template>
```

## Component Usage

```vue
<template>
  <UseWindowSize v-slot="{ width, height }">
    Width: {{ width }}
    Height: {{ height }}
  </UseWindowSize>
</template>
```

## Type Declarations

```ts
export interface UseWindowSizeOptions extends ConfigurableWindow {
  initialWidth?: number
  initialHeight?: number
  /**
   * Listen to window `orientationchange` event
   *
   * @default true
   */
  listenOrientation?: boolean
  /**
   * Whether the scrollbar should be included in the width and height
   * Only effective when `type` is `'inner'`
   *
   * @default true
   */
  includeScrollbar?: boolean
  /**
   * Use `window.innerWidth` or `window.outerWidth` or `window.visualViewport`
   * visualViewport documentation from MDN(https://developer.mozilla.org/zh-CN/docs/Web/API/VisualViewport)
   * @default 'inner'
   */
  type?: "inner" | "outer" | "visual"
}
export interface UseWindowSizeReturn {
  width: ShallowRef<number>
  height: ShallowRef<number>
}
/**
 * Reactive window size.
 *
 * @see https://vueuse.org/useWindowSize
 * @param options
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function useWindowSize(
  options?: UseWindowSizeOptions,
): UseWindowSizeReturn
```

---

<!-- source: references/useZoomFactor.md -->
---
category: '@Electron'
---

# useZoomFactor

Reactive [WebFrame](https://www.electronjs.org/docs/api/web-frame#webframe) zoom factor.

## Usage

```ts
import { useZoomFactor } from '@vueuse/electron'

// enable nodeIntegration if you don't provide webFrame explicitly
// see: https://www.electronjs.org/docs/api/webview-tag#nodeintegration
// Ref result will return
const factor = useZoomFactor()
console.log(factor.value) // print current zoom factor
factor.value = 2 // change current zoom factor
```

Set initial zoom factor immediately

```ts
import { useZoomFactor } from '@vueuse/electron'

const factor = useZoomFactor(2)
```

Pass a `ref` and the factor will be updated when the source ref changes

```ts
import { useZoomFactor } from '@vueuse/electron'
import { shallowRef } from 'vue'

const factor = shallowRef(1)

useZoomFactor(factor) // zoom factor will match with the ref

factor.value = 2 // zoom factor will change
```

## Type Declarations

```ts
export declare function useZoomFactor(factor: MaybeRef<number>): Ref<number>
export declare function useZoomFactor(
  webFrame: WebFrame,
  factor: MaybeRef<number>,
): Ref<number>
export declare function useZoomFactor(webFrame: WebFrame): Ref<number>
export declare function useZoomFactor(): Ref<number>
```

---

<!-- source: references/useZoomLevel.md -->
---
category: '@Electron'
---

# useZoomLevel

Reactive [WebFrame](https://www.electronjs.org/docs/api/web-frame#webframe) zoom level.

## Usage

```ts
import { useZoomLevel } from '@vueuse/electron'

// enable nodeIntegration if you don't provide webFrame explicitly
// see: https://www.electronjs.org/docs/api/webview-tag#nodeintegration
// Ref result will return
const level = useZoomLevel()
console.log(level.value) // print current zoom level
level.value = 2 // change current zoom level
```

Set initial zoom level immediately

```ts
import { useZoomLevel } from '@vueuse/electron'

const level = useZoomLevel(2)
```

Pass a `ref` and the level will be updated when the source ref changes

```ts
import { useZoomLevel } from '@vueuse/electron'
import { shallowRef } from 'vue'

const level = shallowRef(1)

useZoomLevel(level) // zoom level will match with the ref

level.value = 2 // zoom level will change
```

## Type Declarations

```ts
export declare function useZoomLevel(level: MaybeRef<number>): Ref<number>
export declare function useZoomLevel(
  webFrame: WebFrame,
  level: MaybeRef<number>,
): Ref<number>
export declare function useZoomLevel(webFrame: WebFrame): Ref<number>
export declare function useZoomLevel(): Ref<number>
```
