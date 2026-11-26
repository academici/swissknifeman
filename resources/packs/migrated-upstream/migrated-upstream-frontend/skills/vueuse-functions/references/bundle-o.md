<!-- source: references/onClickOutside.md -->
---
category: Sensors
---

# onClickOutside

Listen for clicks outside of an element. Useful for modals or dropdowns.

## Usage

```vue
<script setup lang="ts">
import { onClickOutside } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const target = useTemplateRef('target')

onClickOutside(target, event => console.log(event))
</script>

<template>
  <div ref="target">
    Hello world
  </div>
  <div>Outside element</div>
</template>
```

### Return Value

By default, `onClickOutside` returns a `stop` function to remove the event listeners.

```ts
const stop = onClickOutside(target, handler)

// Later, stop listening
stop()
```

### Controls

If you need more control over triggering the handler, you can use the `controls` option. This returns an object with `stop`, `cancel`, and `trigger` functions.

```ts
const { stop, cancel, trigger } = onClickOutside(
  modalRef,
  (event) => {
    modal.value = false
  },
  { controls: true },
)

// cancel prevents the next click from triggering the handler
cancel()

// trigger manually fires the handler
trigger(event)

// stop removes all event listeners
stop()
```

### Ignore Elements

Use the `ignore` option to prevent certain elements from triggering the handler. Provide elements as an array of Refs or CSS selectors.

```ts
const ignoreElRef = useTemplateRef('ignoreEl')

onClickOutside(
  target,
  event => console.log(event),
  { ignore: [ignoreElRef, '.ignore-class', '#ignore-id'] },
)
```

### Capture Phase

By default, the event listener uses the capture phase (`capture: true`). Set `capture: false` to use the bubbling phase instead.

```ts
onClickOutside(target, handler, { capture: false })
```

### Detect Iframe Clicks

Clicks inside an iframe are not detected by default. Enable `detectIframe` to also trigger the handler when focus moves to an iframe.

```ts
onClickOutside(target, handler, { detectIframe: true })
```

## Component Usage

```vue
<template>
  <OnClickOutside :options="{ ignore: [/* ... */] }" @trigger="count++">
    <div>
      Click Outside of Me
    </div>
  </OnClickOutside>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vOnClickOutside } from '@vueuse/components'
import { shallowRef } from 'vue'

const modal = shallowRef(false)
function closeModal() {
  modal.value = false
}
</script>

<template>
  <button @click="modal = true">
    Open Modal
  </button>
  <div v-if="modal" v-on-click-outside="closeModal">
    Hello World
  </div>
</template>
```

You can also set the handler as an array to set the configuration items of the instruction.

```vue
<script setup lang="ts">
import { vOnClickOutside } from '@vueuse/components'
import { shallowRef, useTemplateRef } from 'vue'

const modal = shallowRef(false)

const ignoreElRef = useTemplateRef('ignoreEl')

const onClickOutsideHandler = [
  (ev) => {
    console.log(ev)
    modal.value = false
  },
  { ignore: [ignoreElRef] },
]
</script>

<template>
  <button @click="modal = true">
    Open Modal
  </button>

  <div ref="ignoreElRef">
    click outside ignore element
  </div>

  <div v-if="modal" v-on-click-outside="onClickOutsideHandler">
    Hello World
  </div>
</template>
```

## Type Declarations

```ts
export interface OnClickOutsideOptions<
  Controls extends boolean = false,
> extends ConfigurableWindow {
  /**
   * List of elements that should not trigger the event,
   * provided as Refs or CSS Selectors.
   */
  ignore?: MaybeRefOrGetter<(MaybeElementRef | string)[]>
  /**
   * Use capturing phase for internal event listener.
   * @default true
   */
  capture?: boolean
  /**
   * Run handler function if focus moves to an iframe.
   * @default false
   */
  detectIframe?: boolean
  /**
   * Use controls to cancel/trigger listener.
   * @default false
   */
  controls?: Controls
}
export type OnClickOutsideHandler<
  T extends OnClickOutsideOptions<boolean> = OnClickOutsideOptions,
> = (
  event:
    | (T["detectIframe"] extends true ? FocusEvent : never)
    | (T["controls"] extends true ? Event : never)
    | PointerEvent,
) => void
export type OnClickOutsideReturn<Controls extends boolean = false> =
  Controls extends false
    ? Fn
    : {
        stop: Fn
        cancel: Fn
        trigger: (event: Event) => void
      }
/**
 * Listen for clicks outside of an element.
 *
 * @see https://vueuse.org/onClickOutside
 * @param target
 * @param handler
 * @param options
 */
export declare function onClickOutside<T extends OnClickOutsideOptions>(
  target: MaybeComputedElementRef,
  handler: OnClickOutsideHandler<T>,
  options?: T,
): Fn
export declare function onClickOutside<T extends OnClickOutsideOptions<true>>(
  target: MaybeComputedElementRef,
  handler: OnClickOutsideHandler<T>,
  options: T,
): {
  stop: Fn
  cancel: Fn
  trigger: (event: Event) => void
}
```

---

<!-- source: references/onElementRemoval.md -->
---
category: Sensors
---

# onElementRemoval

Fires when the element or any element containing it is removed from the DOM.

## Usage

```vue {13}
<script setup lang="ts">
import { onElementRemoval } from '@vueuse/core'
import { shallowRef, useTemplateRef } from 'vue'

const btnRef = useTemplateRef('btn')
const btnState = shallowRef(true)
const removedCount = shallowRef(0)

function btnOnClick() {
  btnState.value = !btnState.value
}

onElementRemoval(btnRef, () => ++removedCount.value)
</script>

<template>
  <button
    v-if="btnState"
    @click="btnOnClick"
  >
    recreate me
  </button>
  <button
    v-else
    ref="btnRef"
    @click="btnOnClick"
  >
    remove me
  </button>
  <b>removed times: {{ removedCount }}</b>
</template>
```

### Callback with Mutation Records

The callback receives an array of `MutationRecord` objects that triggered the removal.

```ts
import { onElementRemoval } from '@vueuse/core'

onElementRemoval(targetRef, (mutationRecords) => {
  console.log('Element removed', mutationRecords)
})
```

### Return Value

Returns a stop function to stop observing.

```ts
const stop = onElementRemoval(targetRef, callback)

// Later, stop observing
stop()
```

## Type Declarations

```ts
export interface OnElementRemovalOptions
  extends
    ConfigurableWindow,
    ConfigurableDocumentOrShadowRoot,
    WatchOptionsBase {}
/**
 * Fires when the element or any element containing it is removed.
 *
 * @param target
 * @param callback
 * @param options
 */
export declare function onElementRemoval(
  target: MaybeElementRef,
  callback: (mutationRecords: MutationRecord[]) => void,
  options?: OnElementRemovalOptions,
): Fn
```

---

<!-- source: references/onKeyStroke.md -->
---
category: Sensors
---

# onKeyStroke

Listen for keyboard keystrokes. By default, listens on `keydown` events on `window`.

## Usage

```ts
import { onKeyStroke } from '@vueuse/core'

onKeyStroke('ArrowDown', (e) => {
  e.preventDefault()
})
```

See [this table](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key/Key_Values) for all key codes.

### Return Value

Returns a stop function to remove the event listener.

```ts
const stop = onKeyStroke('Escape', handler)

// Later, stop listening
stop()
```

### Listen To Multiple Keys

```ts
import { onKeyStroke } from '@vueuse/core'

onKeyStroke(['s', 'S', 'ArrowDown'], (e) => {
  e.preventDefault()
})

// listen to all keys by passing `true` or skipping the key parameter
onKeyStroke(true, (e) => {
  e.preventDefault()
})
onKeyStroke((e) => {
  e.preventDefault()
})
```

### Custom Key Predicate

You can pass a custom function to determine which keys should trigger the handler.

```ts
import { onKeyStroke } from '@vueuse/core'

onKeyStroke(
  e => e.key === 'A' && e.shiftKey,
  (e) => {
    console.log('Shift+A pressed')
  },
)
```

### Custom Event Target

```ts
import { onKeyStroke } from '@vueuse/core'

onKeyStroke('A', (e) => {
  console.log('Key A pressed on document')
}, { target: document })
```

### Ignore Repeated Events

The callback will trigger only once when pressing `A` and **holding down**. The `dedupe` option can also be a reactive ref.

```ts
import { onKeyStroke } from '@vueuse/core'

onKeyStroke('A', (e) => {
  console.log('Key A pressed')
}, { dedupe: true })
```

Reference: [KeyboardEvent.repeat](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/repeat)

### Passive Mode

Set `passive: true` to use a passive event listener.

```ts
import { onKeyStroke } from '@vueuse/core'

onKeyStroke('A', handler, { passive: true })
```

## Directive Usage

```vue
<script setup lang="ts">
import { vOnKeyStroke } from '@vueuse/components'

function onUpdate(e: KeyboardEvent) {
  // impl...
}
</script>

<template>
  <input v-on-key-stroke:c,v="onUpdate" type="text">
  <!-- with options -->
  <input v-on-key-stroke:c,v="[onUpdate, { eventName: 'keyup' }]" type="text">
</template>
```

### Custom Keyboard Event

```ts
import { onKeyStroke } from '@vueuse/core'
// ---cut---
onKeyStroke('Shift', (e) => {
  console.log('Shift key up')
}, { eventName: 'keyup' })
```

Or

```ts
import { onKeyUp } from '@vueuse/core'
// ---cut---
onKeyUp('Shift', () => console.log('Shift key up'))
```

## Shorthands

- `onKeyDown` - alias for `onKeyStroke(key, handler, {eventName: 'keydown'})`
- `onKeyPressed` - alias for `onKeyStroke(key, handler, {eventName: 'keypress'})`
- `onKeyUp` - alias for `onKeyStroke(key, handler, {eventName: 'keyup'})`

## Type Declarations

```ts
export type KeyPredicate = (event: KeyboardEvent) => boolean
export type KeyFilter = true | string | string[] | KeyPredicate
export type KeyStrokeEventName = "keydown" | "keypress" | "keyup"
export interface OnKeyStrokeOptions {
  eventName?: KeyStrokeEventName
  target?: MaybeRefOrGetter<EventTarget | null | undefined>
  passive?: boolean
  /**
   * Set to `true` to ignore repeated events when the key is being held down.
   *
   * @default false
   */
  dedupe?: MaybeRefOrGetter<boolean>
}
/**
 * Listen for keyboard keystrokes.
 *
 * @see https://vueuse.org/onKeyStroke
 */
export declare function onKeyStroke(
  key: KeyFilter,
  handler: (event: KeyboardEvent) => void,
  options?: OnKeyStrokeOptions,
): () => void
export declare function onKeyStroke(
  handler: (event: KeyboardEvent) => void,
  options?: OnKeyStrokeOptions,
): () => void
/**
 * Listen to the keydown event of the given key.
 *
 * @see https://vueuse.org/onKeyStroke
 * @param key
 * @param handler
 * @param options
 */
export declare function onKeyDown(
  key: KeyFilter,
  handler: (event: KeyboardEvent) => void,
  options?: Omit<OnKeyStrokeOptions, "eventName">,
): () => void
/**
 * Listen to the keypress event of the given key.
 *
 * @see https://vueuse.org/onKeyStroke
 * @param key
 * @param handler
 * @param options
 */
export declare function onKeyPressed(
  key: KeyFilter,
  handler: (event: KeyboardEvent) => void,
  options?: Omit<OnKeyStrokeOptions, "eventName">,
): () => void
/**
 * Listen to the keyup event of the given key.
 *
 * @see https://vueuse.org/onKeyStroke
 * @param key
 * @param handler
 * @param options
 */
export declare function onKeyUp(
  key: KeyFilter,
  handler: (event: KeyboardEvent) => void,
  options?: Omit<OnKeyStrokeOptions, "eventName">,
): () => void
```

---

<!-- source: references/onLongPress.md -->
---
category: Sensors
---

# onLongPress

Listen for a long press on an element. Returns a stop function.

## Usage

```vue
<script setup lang="ts">
import { onLongPress } from '@vueuse/core'
import { shallowRef, useTemplateRef } from 'vue'

const htmlRefHook = useTemplateRef('htmlRefHook')
const longPressedHook = shallowRef(false)

function onLongPressCallbackHook(e: PointerEvent) {
  longPressedHook.value = true
}
function resetHook() {
  longPressedHook.value = false
}

onLongPress(
  htmlRefHook,
  onLongPressCallbackHook,
  {
    modifiers: {
      prevent: true
    }
  }
)
</script>

<template>
  <p>Long Pressed: {{ longPressedHook }}</p>

  <button ref="htmlRefHook" class="ml-2 button small">
    Press long
  </button>

  <button class="ml-2 button small" @click="resetHook">
    Reset
  </button>
</template>
```

### Custom Delay

By default, the handler fires after 500ms. You can customize this with the `delay` option. It can be a number or a function that receives the `PointerEvent`.

```ts
import { onLongPress } from '@vueuse/core'

// Fixed delay
onLongPress(target, handler, { delay: 1000 })

// Dynamic delay based on event
onLongPress(target, handler, {
  delay: ev => ev.pointerType === 'touch' ? 800 : 500,
})
```

### Distance Threshold

The long press will be canceled if the pointer moves more than the threshold (default: 10 pixels). Set to `false` to disable movement detection.

```ts
import { onLongPress } from '@vueuse/core'

// Custom threshold
onLongPress(target, handler, { distanceThreshold: 20 })

// Disable movement detection
onLongPress(target, handler, { distanceThreshold: false })
```

### On Mouse Up Callback

You can provide an `onMouseUp` callback to be notified when the pointer is released.

```ts
import { onLongPress } from '@vueuse/core'

onLongPress(target, handler, {
  onMouseUp(duration, distance, isLongPress) {
    console.log(`Held for ${duration}ms, moved ${distance}px, long press: ${isLongPress}`)
  },
})
```

### Modifiers

The following modifiers are available:

| Modifier  | Description                                  |
| --------- | -------------------------------------------- |
| `stop`    | Calls `event.stopPropagation()`              |
| `once`    | Removes event listener after first trigger   |
| `prevent` | Calls `event.preventDefault()`               |
| `capture` | Uses capture mode for event listener         |
| `self`    | Only trigger if target is the element itself |

```ts
onLongPress(target, handler, {
  modifiers: {
    prevent: true,
    stop: true,
  },
})
```

## Component Usage

```vue
<script setup lang="ts">
import { OnLongPress } from '@vueuse/components'
import { shallowRef } from 'vue'

const longPressedComponent = shallowRef(false)

function onLongPressCallbackComponent(e: PointerEvent) {
  longPressedComponent.value = true
}
function resetComponent() {
  longPressedComponent.value = false
}
</script>

<template>
  <p>Long Pressed: {{ longPressedComponent }}</p>

  <OnLongPress
    as="button"
    class="ml-2 button small"
    @trigger="onLongPressCallbackComponent"
  >
    Press long
  </OnLongPress>

  <button class="ml-2 button small" @click="resetComponent">
    Reset
  </button>
</template>
```

## Directive Usage

```vue
<script setup lang="ts">
import { vOnLongPress } from '@vueuse/components'
import { shallowRef } from 'vue'

const longPressedDirective = shallowRef(false)

function onLongPressCallbackDirective(e: PointerEvent) {
  longPressedDirective.value = true
}
function resetDirective() {
  longPressedDirective.value = false
}
</script>

<template>
  <p>Long Pressed: {{ longPressedDirective }}</p>

  <button
    v-on-long-press.prevent="onLongPressCallbackDirective"
    class="ml-2 button small"
  >
    Press long
  </button>

  <button
    v-on-long-press="[onLongPressCallbackDirective, { delay: 1000, modifiers: { stop: true } }]"
    class="ml-2 button small"
  >
    Press long (with options)
  </button>

  <button class="ml-2 button small" @click="resetDirective">
    Reset
  </button>
</template>
```

## Type Declarations

```ts
export interface OnLongPressOptions {
  /**
   * Time in ms till `longpress` gets called
   *
   * @default 500
   */
  delay?: number | ((ev: PointerEvent) => number)
  modifiers?: OnLongPressModifiers
  /**
   * Allowance of moving distance in pixels,
   * The action will get canceled When moving too far from the pointerdown position.
   * @default 10
   */
  distanceThreshold?: number | false
  /**
   * Function called when the ref element is released.
   * @param duration how long the element was pressed in ms
   * @param distance distance from the pointerdown position
   * @param isLongPress whether the action was a long press or not
   */
  onMouseUp?: (duration: number, distance: number, isLongPress: boolean) => void
}
export interface OnLongPressModifiers {
  stop?: boolean
  once?: boolean
  prevent?: boolean
  capture?: boolean
  self?: boolean
}
export type OnLongPressReturn = () => void
/** @deprecated use {@link OnLongPressReturn} instead */
export type UseOnLongPressReturn = OnLongPressReturn
export declare function onLongPress(
  target: MaybeElementRef,
  handler: (evt: PointerEvent) => void,
  options?: OnLongPressOptions,
): OnLongPressReturn
```

---

<!-- source: references/onStartTyping.md -->
---
category: Sensors
---

# onStartTyping

Fires when users start typing on non-editable elements. Useful for auto-focusing an input field when the user starts typing anywhere on the page.

## Usage

```vue
<script setup lang="ts">
import { onStartTyping } from '@vueuse/core'
import { useTemplateRef } from 'vue'

const input = useTemplateRef('input')

onStartTyping(() => {
  if (!input.value.active)
    input.value.focus()
})
</script>

<template>
  <input ref="input" type="text" placeholder="Start typing to focus">
</template>
```

## How It Works

The callback only fires when:

- No editable element (`<input>`, `<textarea>`, or `contenteditable`) is focused
- The pressed key is alphanumeric (A-Z, 0-9)
- No modifier keys (Ctrl, Alt, Meta) are held

This allows users to start typing anywhere on the page without accidentally triggering the callback when using keyboard shortcuts or interacting with form fields.

## Type Declarations

```ts
/**
 * Fires when users start typing on non-editable elements.
 *
 * @see https://vueuse.org/onStartTyping
 * @param callback
 * @param options
 */
export declare function onStartTyping(
  callback: (event: KeyboardEvent) => void,
  options?: ConfigurableDocument,
): void
```
