// Source: anonymized production project
//
// Setup-стор Pinia (Vue 3). Демонстрирует три роли:
//   ref()      -> state
//   computed() -> getters (кэшируются)
//   function   -> actions (мутации state + async)
// Приватное (объявлено в сетапе, но НЕ возвращено) снаружи недоступно.
// Файл и фабрика: use<Domain>Store. Первый аргумент — стабильный строковый id.

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

export const useExampleStore = defineStore('example', () => {
    // --- state ---
    const items = ref<string[]>([]);
    const isLoading = ref(false);
    const selectedId = ref<number | null>(null);

    // приватное состояние сетапа: НЕ возвращается => недоступно снаружи,
    // не попадает в devtools / SSR-снапшот / persist
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    // --- getters (computed) ---
    const count = computed(() => items.value.length);
    const hasSelection = computed(() => selectedId.value !== null);

    // --- actions (function) ---

    // Инициализация от сервера (hydration): сеем state значением,
    // которое backend уже отрендерил в props/initial-state.
    function init(initial: string[]): void {
        items.value = initial;
    }

    function add(item: string): void {
        items.value.push(item);
    }

    function select(id: number): void {
        selectedId.value = id;
    }

    // Асинхронный action: грузит данные, держит флаг загрузки.
    async function refresh(): Promise<void> {
        isLoading.value = true;
        try {
            const response = await fetch('/api/items');
            items.value = (await response.json()) as string[];
        } finally {
            isLoading.value = false;
        }
    }

    function reset(): void {
        items.value = [];
        selectedId.value = null;

        if (refreshTimer) {
            clearTimeout(refreshTimer);
            refreshTimer = null;
        }
    }

    // Возвращаем ВСЁ публичное. State-ref, не попавший в return,
    // не будет считаться состоянием стора — поэтому возвращаем и его.
    return {
        // state
        items,
        isLoading,
        selectedId,
        // getters
        count,
        hasSelection,
        // actions
        init,
        add,
        select,
        refresh,
        reset,
    };
});

// --- persist (опционально) ---
// Подключается плагином pinia-plugin-persistedstate. Персистить только то,
// что реально должно пережить перезагрузку (UI-предпочтения, черновик).
// Токены/чувствительное и серверный кэш — НЕ персистить.
//
// export const useUiPrefsStore = defineStore(
//     'ui-prefs',
//     () => {
//         const sidebarCollapsed = ref(false);
//         function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value; }
//         return { sidebarCollapsed, toggleSidebar };
//     },
//     { persist: true }, // или { persist: { storage: sessionStorage, pick: ['sidebarCollapsed'] } }
// );
