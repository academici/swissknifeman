<!-- Source: anonymized production project -->
<script setup lang="ts">
import * as icons from 'lucide-vue-next';
import { computed, type Component } from 'vue';

import type { IconName } from './icon-name.type';

interface Props {
    /** The name of the icon in the set. Type-safe: autocomplete + check on assembly. */
    name: IconName;
    /** Add. CSS-classes - merge with the base ones, do not overwrite them. */
    class?: string;
    size?: number | string;
    color?: string;
    strokeWidth?: number | string;
}

const props = withDefaults(defineProps<Props>(), {
    class: '',
    size: 16,
    strokeWidth: 2,
});

// Base classes + custom. Here is manual concatenation;
// in a project usually cn(...)/clsx for deduplication Tailwind-classes.
const className = computed(() => ['h-4 w-4', props.class].filter(Boolean).join(' '));

// Normalize the name to suit the dialing convention.
// lucide exports PascalCase ('ArrowRight'), data is often in lower/kebab.
// Minimum case: the first letter is in upper case. For kebab-case
// ('arrow-right' -> 'ArrowRight') replace with segment-by-segment capitalization.
function toIconKey(name: string): string {
    return name.charAt(0).toUpperCase() + name.slice(1);
}

// Lazy selection: recalculated only when changing name. The dictionary of the set is the map,
// none if/switch. Fallback HelpCircle in case of unknown name.
const icon = computed<Component>(() => {
    const set = icons as Record<string, Component>;
    return set[toIconKey(props.name)] ?? set.HelpCircle;
});
</script>

<template>
    <component
        :is="icon"
        :class="className"
        :size="size"
        :stroke-width="strokeWidth"
        :color="color"
    />
</template>
