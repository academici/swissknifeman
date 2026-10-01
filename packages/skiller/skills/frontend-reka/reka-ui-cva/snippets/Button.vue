<!-- Source: anonymized production project -->
<!-- components/ui/button/Button.vue -->
<!-- Thin primitive wrapper Primitive: behavior and polymorphism from reka-ui,
     appearance - from cva-variants merged via cn(). -->
<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import type { ButtonVariants } from "."
import { Primitive } from "reka-ui"
import { cn } from "@/lib/utils"
import { buttonVariants } from "."

// Props expand PrimitiveProps (give as and asChild) + axis options from cva,
// typed via inferred type - not manually typed string literals.
interface Props extends PrimitiveProps {
  variant?: ButtonVariants["variant"]
  size?: ButtonVariants["size"]
  class?: HTMLAttributes["class"]
}

// as default - "button"; via as you can change the tag via asChild
// (as-child) merge styles/behavior in a single child element
// (for example <Button as-child><Link/></Button> — link with a button view).
const props = withDefaults(defineProps<Props>(), {
  as: "button",
})
</script>

<template>
  <Primitive
    data-slot="button"
    :as="as"
    :as-child="asChild"
    :class="cn(buttonVariants({ variant, size }), props.class)"
  >
    <slot />
  </Primitive>
</template>
