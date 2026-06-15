<!-- Source: anonymized production project -->
<!-- components/ui/button/Button.vue -->
<!-- Тонкая обёртка примитива Primitive: поведение и полиморфизм из reka-ui,
     внешний вид — из cva-вариантов, слитых через cn(). -->
<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import type { ButtonVariants } from "."
import { Primitive } from "reka-ui"
import { cn } from "@/lib/utils"
import { buttonVariants } from "."

// Пропы расширяют PrimitiveProps (дают as и asChild) + оси вариантов из cva,
// типизированные через выведенный тип — не строковыми литералами вручную.
interface Props extends PrimitiveProps {
  variant?: ButtonVariants["variant"]
  size?: ButtonVariants["size"]
  class?: HTMLAttributes["class"]
}

// as по умолчанию — "button"; через as можно сменить тег, через asChild
// (as-child) слить стили/поведение в единственный дочерний элемент
// (например <Button as-child><Link/></Button> — ссылка с видом кнопки).
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
