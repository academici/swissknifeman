<!-- Source: anonymized production project -->
<script setup lang="ts">
import * as icons from 'lucide-vue-next';
import { computed, type Component } from 'vue';

import type { IconName } from './icon-name.type';

interface Props {
    /** Имя иконки в наборе. Типобезопасно: автокомплит + проверка на сборке. */
    name: IconName;
    /** Доп. CSS-классы — мерджатся с базовыми, не затирают их. */
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

// Базовые классы + пользовательские. Здесь — ручная конкатенация;
// в проекте обычно cn(...)/clsx для дедупликации Tailwind-классов.
const className = computed(() => ['h-4 w-4', props.class].filter(Boolean).join(' '));

// Нормализация имени под соглашение набора.
// lucide экспортирует PascalCase ('ArrowRight'), данные часто в lower/kebab.
// Минимальный кейс: первая буква в верхний регистр. Для kebab-case
// ('arrow-right' -> 'ArrowRight') заменить на посегментную капитализацию.
function toIconKey(name: string): string {
    return name.charAt(0).toUpperCase() + name.slice(1);
}

// Ленивый выбор: пересчитывается только при смене name. Словарь набора и есть карта,
// никаких if/switch. Фолбэк HelpCircle на случай неизвестного имени.
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
