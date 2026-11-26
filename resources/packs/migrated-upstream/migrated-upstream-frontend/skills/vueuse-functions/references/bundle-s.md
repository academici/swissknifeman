<!-- source: references/set.md -->
---
category: Utilities
---

# set

Shorthand for `ref.value = x`

## Usage

```ts
import { set } from '@vueuse/core'

const a = ref(0)

set(a, 1)

console.log(a.value) // 1
```

## Type Declarations

```ts
export declare function set<T>(ref: Ref<T>, value: T): void
export declare function set<O extends object, K extends keyof O>(
  target: O,
  key: K,
  value: O[K],
): void
```

---

<!-- source: references/syncRef.md -->
---
category: Reactivity
related: syncRefs
---

# syncRef

Two-way refs synchronization.

## Usage

```ts
import { syncRef } from '@vueuse/core'

const a = ref('a')
const b = ref('b')

const stop = syncRef(a, b)

console.log(a.value) // a

b.value = 'foo'

console.log(a.value) // foo

a.value = 'bar'

console.log(b.value) // bar
```

### One directional

```ts
import { syncRef } from '@vueuse/core'

const a = ref('a')
const b = ref('b')

const stop = syncRef(a, b, { direction: 'rtl' })
```

### Custom Transform

```ts
import { syncRef } from '@vueuse/core'

const a = ref(10)
const b = ref(2)

const stop = syncRef(a, b, {
  transform: {
    ltr: left => left * 2,
    rtl: right => right / 2
  }
})

console.log(b.value) // 20

b.value = 30

console.log(a.value) // 15
```

## Type Declarations

```ts
type Direction = "ltr" | "rtl" | "both"
type SpecificFieldPartial<T, K extends keyof T> = Partial<Pick<T, K>> &
  Omit<T, K>
/**
 * A = B
 */
type Equal<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false
/**
 * A ∩ B ≠ ∅
 */
type IntersectButNotEqual<A, B> =
  Equal<A, B> extends true ? false : A & B extends never ? false : true
/**
 * A ⊆ B
 */
type IncludeButNotEqual<A, B> =
  Equal<A, B> extends true ? false : A extends B ? true : false
/**
 * A ∩ B = ∅
 */
type NotIntersect<A, B> =
  Equal<A, B> extends true ? false : A & B extends never ? true : false
interface EqualType<
  D extends Direction,
  L,
  R,
  O extends keyof Transform<L, R> = D extends "both" ? "ltr" | "rtl" : D,
> {
  transform?: SpecificFieldPartial<Pick<Transform<L, R>, O>, O>
}
type StrictIncludeMap<
  IncludeType extends "LR" | "RL",
  D extends Exclude<Direction, "both">,
  L,
  R,
> = Equal<[IncludeType, D], ["LR", "ltr"]> &
  Equal<[IncludeType, D], ["RL", "rtl"]> extends true
  ? {
      transform?: SpecificFieldPartial<Pick<Transform<L, R>, D>, D>
    }
  : {
      transform: Pick<Transform<L, R>, D>
    }
type StrictIncludeType<
  IncludeType extends "LR" | "RL",
  D extends Direction,
  L,
  R,
> = D extends "both"
  ? {
      transform: SpecificFieldPartial<
        Transform<L, R>,
        IncludeType extends "LR" ? "ltr" : "rtl"
      >
    }
  : D extends Exclude<Direction, "both">
    ? StrictIncludeMap<IncludeType, D, L, R>
    : never
type IntersectButNotEqualType<D extends Direction, L, R> = D extends "both"
  ? {
      transform: Transform<L, R>
    }
  : D extends Exclude<Direction, "both">
    ? {
        transform: Pick<Transform<L, R>, D>
      }
    : never
type NotIntersectType<D extends Direction, L, R> = IntersectButNotEqualType<
  D,
  L,
  R
>
interface Transform<L, R> {
  ltr: (left: L) => R
  rtl: (right: R) => L
}
type TransformType<D extends Direction, L, R> =
  Equal<L, R> extends true
    ? EqualType<D, L, R>
    : IncludeButNotEqual<L, R> extends true
      ? StrictIncludeType<"LR", D, L, R>
      : IncludeButNotEqual<R, L> extends true
        ? StrictIncludeType<"RL", D, L, R>
        : IntersectButNotEqual<L, R> extends true
          ? IntersectButNotEqualType<D, L, R>
          : NotIntersect<L, R> extends true
            ? NotIntersectType<D, L, R>
            : never
export type SyncRefOptions<
  L,
  R,
  D extends Direction,
> = ConfigurableFlushSync & {
  /**
   * Watch deeply
   *
   * @default false
   */
  deep?: boolean
  /**
   * Sync values immediately
   *
   * @default true
   */
  immediate?: boolean
  /**
   * Direction of syncing. Value will be redefined if you define syncConvertors
   *
   * @default 'both'
   */
  direction?: D
} & TransformType<D, L, R>
/**
 * Two-way refs synchronization.
 * From the set theory perspective to restrict the option's type
 * Check in the following order:
 * 1. L = R
 * 2. L ∩ R ≠ ∅
 * 3. L ⊆ R
 * 4. L ∩ R = ∅
 */
export declare function syncRef<L, R, D extends Direction = "both">(
  left: Ref<L>,
  right: Ref<R>,
  ...[options]: Equal<L, R> extends true
    ? [options?: SyncRefOptions<L, R, D>]
    : [options: SyncRefOptions<L, R, D>]
): () => void
```

---

<!-- source: references/syncRefs.md -->
---
category: Reactivity
related: syncRef
---

# syncRefs

Keep target refs in sync with a source ref

## Usage

```ts
import { syncRefs } from '@vueuse/core'
import { shallowRef } from 'vue'

const source = shallowRef('hello')
const target = shallowRef('target')

const stop = syncRefs(source, target)

console.log(target.value) // hello

source.value = 'foo'

console.log(target.value) // foo
```

### Sync with multiple targets

You can also pass an array of refs to sync.

```ts
import { syncRefs } from '@vueuse/core'
import { shallowRef } from 'vue'

const source = shallowRef('hello')
const target1 = shallowRef('target1')
const target2 = shallowRef('target2')

const stop = syncRefs(source, [target1, target2])

console.log(target1.value) // hello
console.log(target2.value) // hello

source.value = 'foo'

console.log(target1.value) // foo
console.log(target2.value) // foo
```

## Watch options

The options for `syncRefs` are similar to `watch`'s `WatchOptions` but with different default values.

```ts
export interface SyncRefOptions {
  /**
   * Timing for syncing, same as watch's flush option
   *
   * @default 'sync'
   */
  flush?: WatchOptionFlush
  /**
   * Watch deeply
   *
   * @default false
   */
  deep?: boolean
  /**
   * Sync values immediately
   *
   * @default true
   */
  immediate?: boolean
}
```

When setting `{ flush: 'pre' }`, the target reference will be updated at [the end of the current "tick"](https://vuejs.org/guide/essentials/watchers.html#callback-flush-timing) before rendering starts.

```ts
import { syncRefs } from '@vueuse/core'
import { nextTick, shallowRef } from 'vue'

const source = shallowRef('hello')
const target = shallowRef('target')

syncRefs(source, target, { flush: 'pre' })

console.log(target.value) // hello

source.value = 'foo'

console.log(target.value) // hello <- still unchanged, because of flush 'pre'

await nextTick()

console.log(target.value) // foo <- changed!
```

## Type Declarations

```ts
export interface SyncRefsOptions extends ConfigurableFlushSync {
  /**
   * Watch deeply
   *
   * @default false
   */
  deep?: boolean
  /**
   * Sync values immediately
   *
   * @default true
   */
  immediate?: boolean
}
/**
 * Keep target ref(s) in sync with the source ref
 *
 * @param source source ref
 * @param targets
 */
export declare function syncRefs<T>(
  source: WatchSource<T>,
  targets: Ref<T> | Ref<T>[],
  options?: SyncRefsOptions,
): WatchHandle
```
