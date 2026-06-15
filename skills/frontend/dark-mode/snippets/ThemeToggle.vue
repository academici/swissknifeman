<!-- Source: anonymized production project -->
<!--
  Мини-переключатель темы: три состояния light | dark | system.
  Всё состояние и сохранение — в useDarkMode; компонент остаётся тонким.
  Подсветка активной кнопки идёт через appearance (выбор), не resolvedAppearance:
  пользователь должен видеть, что выбран именно 'system', а не во что он разрешился.
  Цвета — через семантические токены/dark:* (см. frontend/tailwind-conventions).
-->
<script setup lang="ts">
import { useDarkMode, type Appearance } from '@/composables/useDarkMode';

const { appearance, updateAppearance } = useDarkMode();

const options: { value: Appearance; label: string }[] = [
    { value: 'light', label: 'Светлая' },
    { value: 'dark', label: 'Тёмная' },
    { value: 'system', label: 'Системная' },
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
