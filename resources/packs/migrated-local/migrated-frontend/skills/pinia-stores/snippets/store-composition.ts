// Source: anonymized production project
//
// Two patterns around stores:
//   1) Composition (store within a store): one store uses another,
//      to build a derived state without duplicating data.
//   2) Access to the store OUTSIDE the component (normal .ts-module: event bus,
//      ws-adapter, service). The key rule is to call useXxxStore()
//      INSIDE a function/handler, not at the top level of the module.

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

// --- base store ---
export const useCartStore = defineStore('cart', () => {
    const items = ref<Array<{ id: number; price: number; qty: number }>>([]);

    const total = computed(() =>
        items.value.reduce((sum, line) => sum + line.price * line.qty, 0),
    );

    function add(id: number, price: number): void {
        const existing = items.value.find((line) => line.id === id);
        if (existing) {
            existing.qty += 1;
        } else {
            items.value.push({ id, price, qty: 1 });
        }
    }

    function clear(): void {
        items.value = [];
    }

    return { items, total, add, clear };
});

// === 1. COMPOSITION: side inside side ===
// Discount store reads state/getters basket and constructs the derived value.
// We do not duplicate positions/amount - we take it from the source.
// Avoiding reciprocal loops (cart should NOT depend on discount).
export const useDiscountStore = defineStore('discount', () => {
    const cart = useCartStore(); // call inside the setup - Pinia is already active
    const rate = ref(0);

    const discounted = computed(() => cart.total * (1 - rate.value));

    function applyRate(value: number): void {
        rate.value = Math.min(Math.max(value, 0), 1);
    }

    return { rate, discounted, applyRate };
});

// === 2. ACCESS TO A STORY OUTSIDE A COMPONENT ===
// Regular module (event bus / ws-adapter). Pinia at the time of import
// of this file may not yet be installed via app.use(pinia),
// therefore useCartStore() is called INSIDE the handler, and not at the top level.

export function subscribeToPriceFeed(socket: { on(event: string, cb: (p: { id: number; price: number }) => void): void }): void {
    socket.on('item.added', (payload) => {
        // CORRECT: the store resolves at the moment of the event - Pinia is already active
        const cart = useCartStore();
        cart.add(payload.id, payload.price);
    });
}

// ANTIPATTERN (DON'T DO):
//   const cart = useCartStore(); // at the top level of the module
//   -> "getActivePinia() was called but there was no active Pinia"
//
// Pass specific instance - useCartStore(pinia) — is only needed in code
// BEFORE app.use(pinia) or on the server outside the request lifecycle (SSR).
