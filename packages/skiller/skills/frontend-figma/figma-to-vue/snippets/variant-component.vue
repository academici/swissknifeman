<!-- Source: {project}/resources/js/components/ui/Button.vue (anonymized) -->
<!-- Figma Component Set (Variant: Intent × Size × State) → cva-options. Tokens from @theme. -->
<script setup lang="ts">
import { computed } from 'vue'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/cn' // see skill tailwind-conventions (clsx + tailwind-merge)

// Variant-axes from Figma are mapped 1:1 in variants. Names - from Figma Variant properties.
const button = cva(
  'inline-flex items-center justify-center gap-sm rounded-md font-medium transition-colors disabled:opacity-50',
  {
    variants: {
      intent: {
        primary: 'bg-primary text-white hover:bg-primary/90',
        ghost: 'bg-transparent text-primary hover:bg-primary/10',
      },
      size: {
        sm: 'h-8 px-md text-sm',
        md: 'h-10 px-lg text-base',
      },
    },
    defaultVariants: { intent: 'primary', size: 'md' },
  },
)

type ButtonProps = VariantProps<typeof button>
const props = defineProps<{ intent?: ButtonProps['intent']; size?: ButtonProps['size']; class?: string }>()

const classes = computed(() => cn(button({ intent: props.intent, size: props.size }), props.class))
</script>

<template>
  <button :class="classes">
    <slot />
  </button>
</template>
