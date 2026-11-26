<!-- source: references/logicAnd.md -->
---
category: '@Math'
alias: and
related: logicNot, logicOr
---

# logicAnd

`AND` condition for refs.

## Usage

```ts
import { whenever } from '@vueuse/core'
import { logicAnd } from '@vueuse/math'

const a = ref(true)
const b = ref(false)

whenever(logicAnd(a, b), () => {
  console.log('both a and b are now truthy!')
})
```

## Type Declarations

```ts
/**
 * `AND` conditions for refs.
 *
 * @see https://vueuse.org/logicAnd
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function logicAnd(
  ...args: MaybeRefOrGetter<any>[]
): ComputedRef<boolean>
/** @deprecated use `logicAnd` instead */
export declare const and: typeof logicAnd
```

---

<!-- source: references/logicNot.md -->
---
category: '@Math'
alias: not
---

# logicNot

`NOT` condition for ref.

## Usage

```ts
import { whenever } from '@vueuse/core'
import { logicNot } from '@vueuse/math'

const a = ref(true)

whenever(logicNot(a), () => {
  console.log('a is now falsy!')
})
```

## Type Declarations

```ts
/**
 * `NOT` conditions for refs.
 *
 * @see https://vueuse.org/logicNot
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function logicNot(v: MaybeRefOrGetter<any>): ComputedRef<boolean>
/** @deprecated use `logicNot` instead */
export declare const not: typeof logicNot
```

---

<!-- source: references/logicOr.md -->
---
category: '@Math'
alias: or
related: logicAnd, logicNot
---

# logicOr

`OR` conditions for refs.

## Usage

```ts
import { whenever } from '@vueuse/core'
import { logicOr } from '@vueuse/math'

const a = ref(true)
const b = ref(false)

whenever(logicOr(a, b), () => {
  console.log('either a or b is truthy!')
})
```

## Type Declarations

```ts
/**
 * `OR` conditions for refs.
 *
 * @see https://vueuse.org/logicOr
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare function logicOr(
  ...args: MaybeRefOrGetter<any>[]
): ComputedRef<boolean>
/** @deprecated use `logicOr` instead */
export declare const or: typeof logicOr
```
