<!-- Source: anonymized production project -->
<!--
  Usage Pinia-store in the component <script setup>:
    - const store = useXxxStore()
    - state/getters destructured via storeToRefs (maintains reactivity);
      normal destructuring const { count } = store ROOM reactivity
    - actions call directly from the side (store.add(...)) or destructure it as is
    - hydration: sow the initial value from the server into onMounted (one owner)
-->
<script setup lang="ts">
import { onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useExampleStore } from '@/stores/useExampleStore';

// Initial data comes from the server (for example, via props pages / initial-state).
const props = defineProps<{ initialItems: string[] }>();

const store = useExampleStore();

// state + getters while maintaining reactivity
const { items, isLoading, count, hasSelection } = storeToRefs(store);

// actions can be taken directly - they are not reactive
const { add, select, refresh } = store;

// Hydration: store owner resets server state when mounted.
// We do not duplicate what backend has already rendered, and we don’t fetch it again
// which has already arrived in props.
onMounted(() => {
    store.init(props.initialItems);
});
</script>

<template>
    <section>
        <p>Total: {{ count }} <span v-if="hasSelection">(there is a choice)</span></p>

        <ul>
            <li
                v-for="(item, index) in items"
                :key="index"
                @click="select(index)"
            >
                {{ item }}
            </li>
        </ul>

        <button :disabled="isLoading" @click="add('new item')">Add</button>
        <button :disabled="isLoading" @click="refresh()">Update</button>
    </section>
</template>
