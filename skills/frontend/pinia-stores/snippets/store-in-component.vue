<!-- Source: anonymized production project -->
<!--
  Использование Pinia-стора в компоненте <script setup>:
    - const store = useXxxStore()
    - state/getters деструктурируем через storeToRefs (сохраняет реактивность);
      обычная деструктуризация const { count } = store РВЁТ реактивность
    - actions вызываем прямо со стора (store.add(...)) или деструктурируем как есть
    - hydration: сеем начальное значение от сервера в onMounted (один владелец)
-->
<script setup lang="ts">
import { onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useExampleStore } from '@/stores/useExampleStore';

// Начальные данные приходят с сервера (например, через props страницы / initial-state).
const props = defineProps<{ initialItems: string[] }>();

const store = useExampleStore();

// state + getters с сохранением реактивности
const { items, isLoading, count, hasSelection } = storeToRefs(store);

// actions можно брать напрямую — они не реактивны
const { add, select, refresh } = store;

// Hydration: владелец стора сеет серверное состояние при монтировании.
// Не дублируем то, что backend уже отрендерил, и не фетчим повторно то,
// что уже пришло в props.
onMounted(() => {
    store.init(props.initialItems);
});
</script>

<template>
    <section>
        <p>Всего: {{ count }} <span v-if="hasSelection">(есть выбор)</span></p>

        <ul>
            <li
                v-for="(item, index) in items"
                :key="index"
                @click="select(index)"
            >
                {{ item }}
            </li>
        </ul>

        <button :disabled="isLoading" @click="add('new item')">Добавить</button>
        <button :disabled="isLoading" @click="refresh()">Обновить</button>
    </section>
</template>
