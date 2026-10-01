<!-- Source: anonymized production project -->
# Composite component: Root / Trigger / Content on Reka UI

Composite primitive (Dialog, Popover, Tooltip, DropdownMenu) is collected from
parts: each part is separate `.vue`-file in `components/ui/dialog/`,
re-exported from `index.ts`. Behavior (focus trap, portal, ARIA,
`data-[state]`) gives Reka UI; your task is to forward props and merge classes.

## index.ts — public API folders

```ts
export { default as Dialog } from "./Dialog.vue"
export { default as DialogTrigger } from "./DialogTrigger.vue"
export { default as DialogContent } from "./DialogContent.vue"
export { default as DialogHeader } from "./DialogHeader.vue"
export { default as DialogTitle } from "./DialogTitle.vue"
```

## Root — Dialog.vue (forward propov + emitters without classes)

`useForwardPropsEmits` transparently passes all props/primitive emitters; at Root
doesn't have one `class`, so there is no need to exclude anything.

```vue
<script setup lang="ts">
import type { DialogRootEmits, DialogRootProps } from "reka-ui"
import { DialogRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<DialogRootProps>()
const emits = defineEmits<DialogRootEmits>()
const forwarded = useForwardPropsEmits(props, emits)
</script>

<template>
  <DialogRoot data-slot="dialog" v-bind="forwarded">
    <slot />
  </DialogRoot>
</template>
```

## Trigger — DialogTrigger.vue (thin wrapper under asChild-button)

```vue
<script setup lang="ts">
import type { DialogTriggerProps } from "reka-ui"
import { DialogTrigger } from "reka-ui"

const props = defineProps<DialogTriggerProps>()
</script>

<template>
  <DialogTrigger data-slot="dialog-trigger" v-bind="props">
    <slot />
  </DialogTrigger>
</template>
```

## Content — DialogContent.vue (portal + overlay + merging its class)

Key Technique: The piece has its own `class`, so its **exclude**
from forward via `reactiveOmit(props, "class")`, and poured separately into `cn()` —
otherwise `class` will go into the primitive twice. Portal/overlay require
`inheritAttrs: false` and forwarding `{ ...$attrs, ...forwarded }`. Classes
`data-[state=open]:`/`data-[state=closed]:` read the status set
primitive, and attach animations.

```vue
<script setup lang="ts">
import type { DialogContentEmits, DialogContentProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { X } from "lucide-vue-next"
import { DialogClose, DialogContent, DialogPortal, useForwardPropsEmits } from "reka-ui"
import { cn } from "@/lib/utils"
import DialogOverlay from "./DialogOverlay.vue"

defineOptions({ inheritAttrs: false })

const props = defineProps<DialogContentProps & { class?: HTMLAttributes["class"] }>()
const emits = defineEmits<DialogContentEmits>()

// class is excluded from the forward so as not to be duplicated in the primitive
const delegated = reactiveOmit(props, "class")
const forwarded = useForwardPropsEmits(delegated, emits)
</script>

<template>
  <DialogPortal>
    <DialogOverlay />
    <DialogContent
      data-slot="dialog-content"
      v-bind="{ ...$attrs, ...forwarded }"
      :class="cn(
        'bg-background fixed top-[50%] left-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95',
        props.class,
      )"
    >
      <slot />
      <DialogClose data-slot="dialog-close" class="absolute top-4 right-4 rounded-xs opacity-70 transition-opacity hover:opacity-100">
        <X />
        <span class="sr-only">Close</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
```

## Structural part - DialogHeader.vue (normal div + cn)

Not every part needs a primitive: header/footer - simple `div` with his base
and custom `class`, merged via `cn()`.

```vue
<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{ class?: HTMLAttributes["class"] }>()
</script>

<template>
  <div data-slot="dialog-header" :class="cn('flex flex-col gap-2 text-center sm:text-left', props.class)">
    <slot />
  </div>
</template>
```

## Usage

```vue
<Dialog>
  <DialogTrigger as-child>
    <Button>Open</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Header</DialogTitle>
    </DialogHeader>
    <!-- contents -->
  </DialogContent>
</Dialog>
```
