// Source: anonymized production project
//
// Setup-side Pinia (Vue 3). Demonstrates three roles:
//   ref()      -> state
//   computed() -> getters (are cached)
//   function   -> actions (mutations state + async)
// Private (declared in setup but NOT returned) not accessible from outside.
// File and factory: use<Domain>Store. First argument is a stable string id.

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

export const useExampleStore = defineStore('example', () => {
    // --- state ---
    const items = ref<string[]>([]);
    const isLoading = ref(false);
    const selectedId = ref<number | null>(null);

    // private setup state: NOT returned => not accessible from outside,
    // does not hit devtools / SSR-snapshot / persist
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    // --- getters (computed) ---
    const count = computed(() => items.value.length);
    const hasSelection = computed(() => selectedId.value !== null);

    // --- actions (function) ---

    // Initialization from server (hydration): sow state value,
    // which backend has already rendered in props/initial-state.
    function init(initial: string[]): void {
        items.value = initial;
    }

    function add(item: string): void {
        items.value.push(item);
    }

    function select(id: number): void {
        selectedId.value = id;
    }

    // Asynchronous action: loads data, holds the loading flag.
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

    // We return EVERYTHING public. State-ref, not included in return,
    // will not be considered the state of the store - so we return it too.
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

// --- persist (optional) ---
// Connected by plugin pinia-plugin-persistedstate. Persist only that
// that really should survive a reboot (UI-preferences, draft).
// Tokens/sensitive and server cache - DO NOT persist.
//
// export const useUiPrefsStore = defineStore(
//     'ui-prefs',
//     () => {
//         const sidebarCollapsed = ref(false);
//         function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value; }
//         return { sidebarCollapsed, toggleSidebar };
//     },
//     { persist: true }, // or { persist: { storage: sessionStorage, pick: ['sidebarCollapsed'] } }
// );
