<!-- Source: anonymized production project -->
# Составной компонент: Root / Trigger / Content на Reka UI

Составной примитив (Dialog, Popover, Tooltip, DropdownMenu) собирается из
частей: каждая часть — отдельный `.vue`-файл в `components/ui/dialog/`,
реэкспортированный из `index.ts`. Поведение (фокус-ловушка, портал, ARIA,
`data-[state]`) даёт Reka UI; ваша задача — форвардинг пропов и слияние классов.

## index.ts — публичное API папки

```ts
export { default as Dialog } from "./Dialog.vue"
export { default as DialogTrigger } from "./DialogTrigger.vue"
export { default as DialogContent } from "./DialogContent.vue"
export { default as DialogHeader } from "./DialogHeader.vue"
export { default as DialogTitle } from "./DialogTitle.vue"
```

## Root — Dialog.vue (форвард пропов + эмитов без классов)

`useForwardPropsEmits` прозрачно прокидывает все пропы/эмиты примитива; у Root
нет своего `class`, поэтому ничего исключать не нужно.

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

## Trigger — DialogTrigger.vue (тонкая обёртка под asChild-кнопку)

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

## Content — DialogContent.vue (портал + оверлей + слияние своего class)

Ключевой приём: у части есть собственный `class`, поэтому его **исключают**
из форварда через `reactiveOmit(props, "class")`, а сливают отдельно в `cn()` —
иначе `class` уйдёт в примитив дважды. Портал/оверлей требуют
`inheritAttrs: false` и проброса `{ ...$attrs, ...forwarded }`. Классы
`data-[state=open]:`/`data-[state=closed]:` читают состояние, выставляемое
примитивом, и навешивают анимации.

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

// class исключён из форварда, чтобы не дублировался в примитиве
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

## Структурная часть — DialogHeader.vue (обычный div + cn)

Не каждой части нужен примитив: заголовок/футер — просто `div` со своим base
и пользовательским `class`, слитыми через `cn()`.

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

## Использование

```vue
<Dialog>
  <DialogTrigger as-child>
    <Button>Открыть</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Заголовок</DialogTitle>
    </DialogHeader>
    <!-- содержимое -->
  </DialogContent>
</Dialog>
```
