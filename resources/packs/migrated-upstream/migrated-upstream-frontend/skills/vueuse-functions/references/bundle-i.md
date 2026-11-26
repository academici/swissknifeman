<!-- source: references/injectLocal.md -->
---
category: State
---

# injectLocal

Extended `inject` with ability to call `provideLocal` to provide the value in the same component.

## Usage

```vue
<script setup>
import { injectLocal, provideLocal } from '@vueuse/core'

provideLocal('MyInjectionKey', 1)
const injectedValue = injectLocal('MyInjectionKey') // injectedValue === 1
</script>
```

## Type Declarations

```ts
/**
 * On the basis of `inject`, it is allowed to directly call inject to obtain the value after call provide in the same component.
 *
 * @example
 * ```ts
 * injectLocal('MyInjectionKey', 1)
 * const injectedValue = injectLocal('MyInjectionKey') // injectedValue === 1
 * ```
 *
 * @__NO_SIDE_EFFECTS__
 */
export declare const injectLocal: typeof inject
```

---

<!-- source: references/isDefined.md -->
---
category: Utilities
---

# isDefined

Non-nullish checking type guard for Ref.

## Usage

```ts
import { isDefined } from '@vueuse/core'

const example = ref(Math.random() ? 'example' : undefined) // Ref<string | undefined>

if (isDefined(example))
  example // Ref<string>
```

## Type Declarations

```ts
export type IsDefinedReturn = boolean
export declare function isDefined<T>(
  v: ComputedRef<T>,
): v is ComputedRef<Exclude<T, null | undefined>>
export declare function isDefined<T>(
  v: Ref<T>,
): v is Ref<Exclude<T, null | undefined>>
export declare function isDefined<T>(v: T): v is Exclude<T, null | undefined>
```
