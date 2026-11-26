<!-- Source: anonymized production project -->
<!--
  Mini theme switch: three states light | dark | system.
  All state and saving are in The useDarkMode; component remains thin.
  The active button is illuminated via appearance (selection), not resolvedAppearance:
  the user should see that exactly 'system', and not what it resolved into.
  Colors - via semantic tokens/dark:* (see frontend/tailwind-conventions).
-->
<script setup lang="ts">
import { useDarkMode, type Appearance } from '@/composables/useDarkMode';

const { appearance, updateAppearance } = useDarkMode();

const options: { value: Appearance; label: string }[] = [
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
    { value: 'system', label: 'System' },
];
</script>

<template>
    <div class="inline-flex gap-1 rounded-lg bg-neutral-100 p-1 dark:bg-neutral-800">
        <button
            v-for="option in options"
            :key="option.value"
            type="button"
            class="rounded-md px-3 py-1.5 text-sm transition-colors"
            :class="
                appearance === option.value
                    ? 'bg-white text-neutral-900 shadow-sm dark:bg-neutral-700 dark:text-neutral-50'
                    : 'text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100'
            "
            :aria-pressed="appearance === option.value"
            @click="updateAppearance(option.value)"
        >
            {{ option.label }}
        </button>
    </div>
</template>
