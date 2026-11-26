<!-- source: references/watchArray.md -->
---
category: Watch
---

# watchArray

Watch for an array with additions and removals.

## Usage

Similar to `watch`, but provides the added and removed elements to the callback function. Pass `{ deep: true }` if the list is updated in place with `push`, `splice`, etc.

```ts
import { watchArray } from '@vueuse/core'

const list = ref([1, 2, 3])

watchArray(list, (newList, oldList, added, removed) => {
  console.log(newList) // [1, 2, 3, 4]
  console.log(oldList) // [1, 2, 3]
  console.log(added) // [4]
  console.log(removed) // []
})

onMounted(() => {
  list.value = [...list.value, 4]
})
```

## Type Declarations

```ts
export declare type WatchArrayCallback<V = any, OV = any> = (
  value: V,
  oldValue: OV,
  added: V,
  removed: OV,
  onCleanup: (cleanupFn: () => void) => void,
) => any
/**
 * Watch for an array with additions and removals.
 *
 * @see https://vueuse.org/watchArray
 */
export declare function watchArray<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T[]> | T[],
  cb: WatchArrayCallback<T[], Immediate extends true ? T[] | undefined : T[]>,
  options?: WatchOptions<Immediate>,
): WatchHandle
```

---

<!-- source: references/watchAtMost.md -->
---
category: Watch
---

# watchAtMost

`watch` with the number of times triggered.

## Usage

Similar to `watch` with an extra option `count` which set up the number of times the callback function is triggered. After the count is reached, the watch will be stopped automatically.

```ts
import { watchAtMost } from '@vueuse/core'

watchAtMost(
  source,
  () => { console.log('trigger!') }, // triggered it at most 3 times
  {
    count: 3, // the number of times triggered
  },
)
```

## Type Declarations

```ts
export interface WatchAtMostOptions<
  Immediate,
> extends WatchWithFilterOptions<Immediate> {
  count: MaybeRefOrGetter<number>
}
export interface WatchAtMostReturn {
  stop: WatchStopHandle
  pause: () => void
  resume: () => void
  count: ShallowRef<number>
}
export declare function watchAtMost<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options: WatchAtMostOptions<Immediate>,
): WatchAtMostReturn
export declare function watchAtMost<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  sources: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options: WatchAtMostOptions<Immediate>,
): WatchAtMostReturn
```

---

<!-- source: references/watchDebounced.md -->
---
category: Watch
alias: debouncedWatch
---

# watchDebounced

Debounced watch. The callback will only be invoked after the source stops changing for the specified duration.

## Usage

Similar to `watch`, but offering extra options `debounce` and `maxWait` which will be applied to the callback function.

```ts
import { watchDebounced } from '@vueuse/core'

watchDebounced(
  source,
  () => { console.log('changed!') },
  { debounce: 500, maxWait: 1000 },
)
```

### Options

| Option     | Type                       | Default | Description                                |
| ---------- | -------------------------- | ------- | ------------------------------------------ |
| `debounce` | `MaybeRefOrGetter<number>` | `0`     | Debounce delay in ms (can be reactive)     |
| `maxWait`  | `MaybeRefOrGetter<number>` | —       | Maximum wait time before forced invocation |

All standard `watch` options (`deep`, `immediate`, `flush`, etc.) are also supported.

### Reactive Debounce Time

The debounce time can be reactive:

```ts
import { watchDebounced } from '@vueuse/core'

const debounceMs = ref(500)

watchDebounced(
  source,
  () => { console.log('changed!') },
  { debounce: debounceMs },
)

// Later, change the debounce time
debounceMs.value = 1000
```

## How It Works

It's essentially a shorthand for the following code:

```ts
import { debounceFilter, watchWithFilter } from '@vueuse/core'

watchWithFilter(
  source,
  () => { console.log('changed!') },
  {
    eventFilter: debounceFilter(500, { maxWait: 1000 }),
  },
)
```

## Type Declarations

```ts
export interface WatchDebouncedOptions<Immediate>
  extends WatchOptions<Immediate>, DebounceFilterOptions {
  debounce?: MaybeRefOrGetter<number>
}
export declare function watchDebounced<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options?: WatchDebouncedOptions<Immediate>,
): WatchHandle
export declare function watchDebounced<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchDebouncedOptions<Immediate>,
): WatchHandle
export declare function watchDebounced<
  T extends object,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchDebouncedOptions<Immediate>,
): WatchHandle
/** @deprecated use `watchDebounced` instead */
export declare const debouncedWatch: typeof watchDebounced
```

---

<!-- source: references/watchDeep.md -->
---
category: Watch
---

# watchDeep

Shorthand for watching value with `{deep: true}`

## Usage

Similar to `watch`, but with `{ deep: true }`

```ts
import { watchDeep } from '@vueuse/core'

const nestedObject = ref({ foo: { bar: { deep: 5 } } })

watchDeep(nestedObject, (updated) => {
  console.log(updated)
})

onMounted(() => {
  nestedObject.value.foo.bar.deep = 10
})
```

## Type Declarations

```ts
export declare function watchDeep<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  source: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options?: Omit<WatchOptions<Immediate>, "deep">,
): WatchHandle
export declare function watchDeep<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: Omit<WatchOptions<Immediate>, "deep">,
): WatchHandle
export declare function watchDeep<
  T extends object,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: Omit<WatchOptions<Immediate>, "deep">,
): WatchHandle
```

---

<!-- source: references/watchExtractedObservable.md -->
---
category: '@RxJS'
---

# watchExtractedObservable

Watch the values of an RxJS [`Observable`](https://rxjs.dev/guide/observable) as extracted from one or more composables.

Automatically unsubscribe on observable change, and automatically unsubscribe from it when the component is unmounted.

Supports all overloads of [`watch`](https://vuejs.org/guide/essentials/watchers.html#basic-example).

## Usage

<!-- TODO: import rxjs error if enable twoslash -->

```ts no-twoslash
import { watchExtractedObservable } from '@vueuse/rxjs'
import { computed, reactive, useTemplateRef } from 'vue'
import { AudioPlayer } from '../my/libs/AudioPlayer'

// setup()

const audio = useTemplateRef('audio')
const player = computed(() => (audio.value ? new AudioPlayer(audio.value) : null))
const state = reactive({
  progress: 0,
})

watchExtractedObservable(player, p => p.progress$, (percentage) => {
  state.progress = percentage * 100
})
```

If you want to add custom error handling to an `Observable` that might error, you can supply an optional `onError` configuration. Without this, RxJS will treat any error in the supplied `Observable` as an "unhandled error" and it will be thrown in a new call stack and reported to `window.onerror` (or `process.on('error')` if you happen to be in Node).

You can also supply an optional `onComplete` configuration if you need to attach special behavior when the watched observable completes.

```ts no-twoslash
import { watchExtractedObservable } from '@vueuse/rxjs'
import { computed, reactive, useTemplateRef } from 'vue'
import { AudioPlayer } from '../my/libs/AudioPlayer'

// setup()

const audio = useTemplateRef('audio')
const player = computed(() => (audio.value ? new AudioPlayer(audio.value) : null))
const state = reactive({
  progress: 0,
})

watchExtractedObservable(player, p => p.progress$, (percentage) => {
  state.progress = percentage * 100
}, {
  onError: (err: unknown) => {
    console.error(err)
  },
  onComplete: () => {
    state.progress = 100 // or 0, or whatever
  },
})
```

If you want, you can also pass `watch` options as the last argument:

```ts no-twoslash
import { watchExtractedObservable } from '@vueuse/rxjs'
import { computed, reactive, useTemplateRef } from 'vue'
import { AudioPlayer } from '../my/libs/AudioPlayer'

// setup()

const audio = useTemplateRef('audio')
const player = computed(() => (audio.value ? new AudioPlayer(audio.value) : null))
const state = reactive({
  progress: 0,
})

watchExtractedObservable(player, p => p.progress$, (percentage) => {
  state.progress = percentage * 100
}, {
  onError: (err: unknown) => {
    console.error(err)
  }
}, {
  immediate: true
})
```

## Subscription Options

| Option       | Type                     | Description                          |
| ------------ | ------------------------ | ------------------------------------ |
| `onError`    | `(err: unknown) => void` | Error handler for Observable errors  |
| `onComplete` | `() => void`             | Called when the Observable completes |

## Return Value

Returns a `WatchHandle` that can be used to stop watching:

```ts no-twoslash
import { watchExtractedObservable } from '@vueuse/rxjs'
import { ref } from 'vue'

const source = ref({ data$: null })

const stop = watchExtractedObservable(source, s => s.data$, (data) => {
  console.log(data)
})

// Later, stop watching
stop()
```

## Type Declarations

```ts
export type OnCleanup = (cleanupFn: () => void) => void
export type WatchExtractedObservableCallback<
  Value,
  OldValue,
  ObservableElement,
> = (
  value: NonNullable<Value>,
  oldValue: OldValue,
  onCleanup: OnCleanup,
) => Observable<ObservableElement>
export interface WatchExtractedObservableOptions {
  onError?: (err: unknown) => void
  onComplete?: () => void
}
export declare function watchExtractedObservable<
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
  callback: (snapshot: E) => void,
  subscriptionOptions?: WatchExtractedObservableOptions,
  watchOptions?: WatchOptions<Immediate>,
): WatchHandle
export declare function watchExtractedObservable<
  T extends Readonly<MultiWatchSources>,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  extractor: WatchExtractedObservableCallback<
    MapSources<T>,
    MapOldSources<T, Immediate>,
    E
  >,
  callback: (snapshot: E) => void,
  subscriptionOptions?: WatchExtractedObservableOptions,
  watchOptions?: WatchOptions<Immediate>,
): WatchHandle
export declare function watchExtractedObservable<
  T,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  extractor: WatchExtractedObservableCallback<
    T,
    Immediate extends true ? T | undefined : T,
    E
  >,
  callback: (snapshot: E) => void,
  subscriptionOptions?: WatchExtractedObservableOptions,
  watchOptions?: WatchOptions<Immediate>,
): WatchHandle
export declare function watchExtractedObservable<
  T extends object,
  E,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  extractor: WatchExtractedObservableCallback<
    T,
    Immediate extends true ? T | undefined : T,
    E
  >,
  callback: (snapshot: E) => void,
  subscriptionOptions?: WatchExtractedObservableOptions,
  watchOptions?: WatchOptions<Immediate>,
): WatchHandle
```

---

<!-- source: references/watchIgnorable.md -->
---
category: Watch
alias: ignorableWatch
---

# watchIgnorable

Ignorable watch

## Usage

Extended `watch` that returns extra `ignoreUpdates(updater)` and `ignorePrevAsyncUpdates()` to ignore particular updates to the source.

```ts
import { watchIgnorable } from '@vueuse/core'
import { nextTick, shallowRef } from 'vue'

const source = shallowRef('foo')

const { stop, ignoreUpdates } = watchIgnorable(
  source,
  v => console.log(`Changed to ${v}!`),
)

source.value = 'bar'
await nextTick() // logs: Changed to bar!

ignoreUpdates(() => {
  source.value = 'foobar'
})
await nextTick() // (nothing happened)

source.value = 'hello'
await nextTick() // logs: Changed to hello!

ignoreUpdates(() => {
  source.value = 'ignored'
})
source.value = 'logged'

await nextTick() // logs: Changed to logged!
```

## WatchOptionFlush timing

`watchIgnorable` accepts the same options as `watch` and uses the same defaults.
So, by default the composable works using `flush: 'pre'`.

## `ignorePrevAsyncUpdates`

This feature is only for async flush `'pre'` and `'post'`. If `flush: 'sync'` is used, `ignorePrevAsyncUpdates()` is a no-op as the watch will trigger immediately after each update to the source. It is still provided for sync flush so the code can be more generic.

```ts
import { watchIgnorable } from '@vueuse/core'
import { nextTick, shallowRef } from 'vue'

const source = shallowRef('foo')

const { ignorePrevAsyncUpdates } = watchIgnorable(
  source,
  v => console.log(`Changed to ${v}!`),
)

source.value = 'bar'
await nextTick() // logs: Changed to bar!

source.value = 'good'
source.value = 'by'
ignorePrevAsyncUpdates()

await nextTick() // (nothing happened)

source.value = 'prev'
ignorePrevAsyncUpdates()
source.value = 'after'

await nextTick() // logs: Changed to after!
```

## Recommended Readings

- [Ignorable Watch](https://patak.dev/vue/ignorable-watch.html) - by [@patak-dev](https://github.com/patak-dev)

## Type Declarations

```ts
export type IgnoredUpdater = (updater: () => void) => void
export type IgnoredPrevAsyncUpdates = () => void
export interface WatchIgnorableReturn {
  ignoreUpdates: IgnoredUpdater
  ignorePrevAsyncUpdates: IgnoredPrevAsyncUpdates
  stop: WatchStopHandle
}
export declare function watchIgnorable<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options?: WatchWithFilterOptions<Immediate>,
): WatchIgnorableReturn
export declare function watchIgnorable<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchWithFilterOptions<Immediate>,
): WatchIgnorableReturn
export declare function watchIgnorable<
  T extends object,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchWithFilterOptions<Immediate>,
): WatchIgnorableReturn
/** @deprecated use `watchIgnorable` instead */
export declare const ignorableWatch: typeof watchIgnorable
```

---

<!-- source: references/watchImmediate.md -->
---
category: Watch
---

# watchImmediate

Shorthand for watching value with `{immediate: true}`

## Usage

Similar to `watch`, but with `{ immediate: true }`

```ts
import { watchImmediate } from '@vueuse/core'

const obj = ref('vue-use')

// changing the value from some external store/composables
obj.value = 'VueUse'

watchImmediate(obj, (updated) => {
  console.log(updated) // Console.log will be logged twice
})
```

## Type Declarations

```ts
export declare function watchImmediate<T extends Readonly<MultiWatchSources>>(
  source: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, true>>,
  options?: Omit<WatchOptions<true>, "immediate">,
): WatchHandle
export declare function watchImmediate<T>(
  source: WatchSource<T>,
  cb: WatchCallback<T, T | undefined>,
  options?: Omit<WatchOptions<true>, "immediate">,
): WatchHandle
export declare function watchImmediate<T extends object>(
  source: T,
  cb: WatchCallback<T, T | undefined>,
  options?: Omit<WatchOptions<true>, "immediate">,
): WatchHandle
```

---

<!-- source: references/watchOnce.md -->
---
category: Watch
---

# watchOnce

Shorthand for watching value with `{ once: true }`. Once the callback fires once, the watcher will be stopped.
See [Vue's docs](https://vuejs.org/guide/essentials/watchers.html#once-watchers) for full details.

## Usage

Similar to `watch`, but with `{ once: true }`

```ts
import { watchOnce } from '@vueuse/core'

watchOnce(source, () => {
  // triggers only once
  console.log('source changed!')
})
```

## Type Declarations

```ts
export declare function watchOnce<T extends Readonly<MultiWatchSources>>(
  source: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, true>>,
  options?: Omit<WatchOptions<true>, "once">,
): WatchHandle
export declare function watchOnce<T>(
  source: WatchSource<T>,
  cb: WatchCallback<T, T | undefined>,
  options?: Omit<WatchOptions<true>, "once">,
): WatchHandle
export declare function watchOnce<T extends object>(
  source: T,
  cb: WatchCallback<T, T | undefined>,
  options?: Omit<WatchOptions<true>, "once">,
): WatchHandle
```

---

<!-- source: references/watchPausable.md -->
---
category: Watch
alias: pausableWatch
---

# watchPausable

Pausable watch

::: info
This function will be removed in future version.
:::

::: tip

[Pausable Watcher](https://vuejs.org/api/reactivity-core.html#watch) has been added to Vue [since 3.5](https://github.com/vuejs/core/pull/9651), use `const { stop, pause, resume } = watch(watchSource, callback)` instead.

:::

## Usage

Use as normal the `watch`, but return extra `pause()` and `resume()` functions to control.

```ts
import { watchPausable } from '@vueuse/core'
import { nextTick, shallowRef } from 'vue'

const source = shallowRef('foo')

const { stop, pause, resume } = watchPausable(
  source,
  v => console.log(`Changed to ${v}!`),
)

source.value = 'bar'
await nextTick() // Changed to bar!

pause()

source.value = 'foobar'
await nextTick() // (nothing happend)

resume()

source.value = 'hello'
await nextTick() // Changed to hello!
```

## Type Declarations

```ts
export interface WatchPausableReturn extends Pausable {
  stop: WatchStopHandle
}
export type WatchPausableOptions<Immediate> =
  WatchWithFilterOptions<Immediate> & PausableFilterOptions
/** @deprecated Use Vue's built-in `watch` instead. This function will be removed in future version. */
export declare function watchPausable<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options?: WatchPausableOptions<Immediate>,
): WatchPausableReturn
/** @deprecated Use Vue's built-in `watch` instead. This function will be removed in future version. */
export declare function watchPausable<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchPausableOptions<Immediate>,
): WatchPausableReturn
/** @deprecated Use Vue's built-in `watch` instead. This function will be removed in future version. */
export declare function watchPausable<
  T extends object,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchPausableOptions<Immediate>,
): WatchPausableReturn
/** @deprecated Use Vue's built-in `watch` instead. This function will be removed in future version. */
export declare const pausableWatch: typeof watchPausable
```

---

<!-- source: references/watchThrottled.md -->
---
category: Watch
alias: throttledWatch
---

# watchThrottled

Throttled watch. The callback will be invoked at most once per specified duration.

## Usage

Similar to `watch`, but offering extra options `throttle`, `trailing`, and `leading` which will be applied to the callback function.

```ts
import { watchThrottled } from '@vueuse/core'

watchThrottled(
  source,
  () => { console.log('changed!') },
  { throttle: 500 },
)
```

### Options

| Option     | Type                       | Default | Description                               |
| ---------- | -------------------------- | ------- | ----------------------------------------- |
| `throttle` | `MaybeRefOrGetter<number>` | `0`     | Throttle interval in ms (can be reactive) |
| `trailing` | `boolean`                  | `true`  | Invoke on the trailing edge               |
| `leading`  | `boolean`                  | `true`  | Invoke on the leading edge                |

All standard `watch` options (`deep`, `immediate`, `flush`, etc.) are also supported.

### Leading and Trailing

Control when the callback is invoked:

```ts
import { watchThrottled } from '@vueuse/core'

// Only invoke at the start of each throttle period
watchThrottled(source, callback, {
  throttle: 500,
  leading: true,
  trailing: false,
})

// Only invoke at the end of each throttle period
watchThrottled(source, callback, {
  throttle: 500,
  leading: false,
  trailing: true,
})
```

## How It Works

It's essentially a shorthand for the following code:

```ts
import { throttleFilter, watchWithFilter } from '@vueuse/core'

watchWithFilter(
  source,
  () => { console.log('changed!') },
  {
    eventFilter: throttleFilter(500),
  },
)
```

## Type Declarations

```ts
export interface WatchThrottledOptions<
  Immediate,
> extends WatchOptions<Immediate> {
  throttle?: MaybeRefOrGetter<number>
  trailing?: boolean
  leading?: boolean
}
export declare function watchThrottled<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options?: WatchThrottledOptions<Immediate>,
): WatchHandle
export declare function watchThrottled<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchThrottledOptions<Immediate>,
): WatchHandle
export declare function watchThrottled<
  T extends object,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchThrottledOptions<Immediate>,
): WatchHandle
/** @deprecated use `watchThrottled` instead */
export declare const throttledWatch: typeof watchThrottled
```

---

<!-- source: references/watchTriggerable.md -->
---
category: Watch
---

# watchTriggerable

Watch that can be triggered manually

## Usage

A `watch` wrapper that supports manual triggering of `WatchCallback`, which returns an additional `trigger` to execute a `WatchCallback` immediately.

```ts
import { watchTriggerable } from '@vueuse/core'
import { nextTick, shallowRef } from 'vue'

const source = shallowRef(0)

const { trigger, ignoreUpdates } = watchTriggerable(
  source,
  v => console.log(`Changed to ${v}!`),
)

source.value = 'bar'
await nextTick() // logs: Changed to bar!

// Execution of WatchCallback via `trigger` does not require waiting
trigger() // logs: Changed to bar!
```

### `onCleanup`

When you want to manually call a `watch` that uses the onCleanup parameter; simply taking the `WatchCallback` out and calling it doesn't make it easy to implement the `onCleanup` parameter.

Using `watchTriggerable` will solve this problem.

```ts
import { watchTriggerable } from '@vueuse/core'
import { shallowRef } from 'vue'

const source = shallowRef(0)

const { trigger } = watchTriggerable(
  source,
  async (v, _, onCleanup) => {
    let canceled = false
    onCleanup(() => canceled = true)

    await new Promise(resolve => setTimeout(resolve, 500))
    if (canceled)
      return

    console.log(`The value is "${v}"\n`)
  },
)

source.value = 1 // no log
await trigger() // logs (after 500 ms): The value is "1"
```

## Type Declarations

```ts
export interface WatchTriggerableReturn<
  FnReturnT = void,
> extends WatchIgnorableReturn {
  /** Execute `WatchCallback` immediately */
  trigger: () => FnReturnT
}
type OnCleanup = (cleanupFn: () => void) => void
export type WatchTriggerableCallback<V = any, OV = any, R = void> = (
  value: V,
  oldValue: OV,
  onCleanup: OnCleanup,
) => R
export declare function watchTriggerable<
  T extends Readonly<MultiWatchSources>,
  FnReturnT,
>(
  sources: [...T],
  cb: WatchTriggerableCallback<
    MapSources<T>,
    MapOldSources<T, true>,
    FnReturnT
  >,
  options?: WatchWithFilterOptions<boolean>,
): WatchTriggerableReturn<FnReturnT>
export declare function watchTriggerable<T, FnReturnT>(
  source: WatchSource<T>,
  cb: WatchTriggerableCallback<T, T | undefined, FnReturnT>,
  options?: WatchWithFilterOptions<boolean>,
): WatchTriggerableReturn<FnReturnT>
export declare function watchTriggerable<T extends object, FnReturnT>(
  source: T,
  cb: WatchTriggerableCallback<T, T | undefined, FnReturnT>,
  options?: WatchWithFilterOptions<boolean>,
): WatchTriggerableReturn<FnReturnT>
```

---

<!-- source: references/watchWithFilter.md -->
---
category: Watch
---

# watchWithFilter

`watch` with additional EventFilter control.

## Usage

Similar to `watch`, but offering an extra option `eventFilter` which will be applied to the callback function.

```ts
import { debounceFilter, watchWithFilter } from '@vueuse/core'

watchWithFilter(
  source,
  () => { console.log('changed!') }, // callback will be called in 500ms debounced manner
  {
    eventFilter: debounceFilter(500), // throttledFilter, pausableFilter or custom filters
  },
)
```

## Type Declarations

```ts
export interface WatchWithFilterOptions<Immediate>
  extends WatchOptions<Immediate>, ConfigurableEventFilter {}
export declare function watchWithFilter<
  T extends Readonly<MultiWatchSources>,
  Immediate extends Readonly<boolean> = false,
>(
  sources: [...T],
  cb: WatchCallback<MapSources<T>, MapOldSources<T, Immediate>>,
  options?: WatchWithFilterOptions<Immediate>,
): WatchHandle
export declare function watchWithFilter<
  T,
  Immediate extends Readonly<boolean> = false,
>(
  source: WatchSource<T>,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchWithFilterOptions<Immediate>,
): WatchHandle
export declare function watchWithFilter<
  T extends object,
  Immediate extends Readonly<boolean> = false,
>(
  source: T,
  cb: WatchCallback<T, Immediate extends true ? T | undefined : T>,
  options?: WatchWithFilterOptions<Immediate>,
): WatchHandle
```

---

<!-- source: references/whenever.md -->
---
category: Watch
---

# whenever

Shorthand for watching value to be truthy.

## Usage

```js
import { useAsyncState, whenever } from '@vueuse/core'

const { state, isReady } = useAsyncState(
  fetch('https://jsonplaceholder.typicode.com/todos/1').then(t => t.json()),
  {},
)

whenever(isReady, () => console.log(state))
```

```ts
import { whenever } from '@vueuse/core'
// ---cut---
// this
whenever(ready, () => console.log(state))

// is equivalent to:
watch(ready, (isReady) => {
  if (isReady)
    console.log(state)
})
```

### Callback Function

Same as `watch`, the callback will be called with `cb(value, oldValue, onInvalidate)`.

```ts
import { whenever } from '@vueuse/core'
// ---cut---
whenever(height, (current, lastHeight) => {
  if (current > lastHeight)
    console.log(`Increasing height by ${current - lastHeight}`)
})
```

### Computed

Same as `watch`, you can pass a getter function to calculate on each change.

```ts
import { whenever } from '@vueuse/core'
// ---cut---
// this
whenever(
  () => counter.value === 7,
  () => console.log('counter is 7 now!'),
)
```

### Options

Options and defaults are same with `watch`.

```ts
import { whenever } from '@vueuse/core'
// ---cut---
// this
whenever(
  () => counter.value === 7,
  () => console.log('counter is 7 now!'),
  { flush: 'sync' },
)
```

## Type Declarations

```ts
export interface WheneverOptions extends WatchOptions {
  /**
   * Only trigger once when the condition is met
   *
   * Override the `once` option in `WatchOptions`
   *
   * @default false
   */
  once?: boolean
}
/**
 * Shorthand for watching value to be truthy
 *
 * @see https://vueuse.org/whenever
 */
export declare function whenever<T>(
  source: WatchSource<T | false | null | undefined>,
  cb: WatchCallback<T>,
  options?: WheneverOptions,
): WatchHandle
```
