// Source: anonymized production project
//
// Два паттерна вокруг сторов:
//   1) Композиция (стор внутри стора): один стор использует другой,
//      чтобы строить производное состояние без дублирования данных.
//   2) Доступ к стору ВНЕ компонента (обычный .ts-модуль: шина событий,
//      ws-адаптер, сервис). Ключевое правило — вызывать useXxxStore()
//      ВНУТРИ функции/обработчика, а не на верхнем уровне модуля.

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

// --- базовый стор ---
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

// === 1. КОМПОЗИЦИЯ: стор внутри стора ===
// Стор скидок читает state/getters корзины и строит производное значение.
// Не дублируем позиции/сумму — берём их у источника.
// Избегаем взаимных циклов (cart НЕ должен зависеть от discount).
export const useDiscountStore = defineStore('discount', () => {
    const cart = useCartStore(); // вызов внутри сетапа — Pinia уже активна
    const rate = ref(0);

    const discounted = computed(() => cart.total * (1 - rate.value));

    function applyRate(value: number): void {
        rate.value = Math.min(Math.max(value, 0), 1);
    }

    return { rate, discounted, applyRate };
});

// === 2. ДОСТУП К СТОРУ ВНЕ КОМПОНЕНТА ===
// Обычный модуль (шина событий / ws-адаптер). Pinia на момент импорта
// этого файла может быть ещё не установлена через app.use(pinia),
// поэтому useCartStore() вызываем ВНУТРИ обработчика, а не на верхнем уровне.

export function subscribeToPriceFeed(socket: { on(event: string, cb: (p: { id: number; price: number }) => void): void }): void {
    socket.on('item.added', (payload) => {
        // ПРАВИЛЬНО: стор резолвится в момент события — Pinia уже активна
        const cart = useCartStore();
        cart.add(payload.id, payload.price);
    });
}

// АНТИПАТТЕРН (НЕ ДЕЛАТЬ):
//   const cart = useCartStore(); // на верхнем уровне модуля
//   -> "getActivePinia() was called but there was no active Pinia"
//
// Передавать конкретный экземпляр — useCartStore(pinia) — нужно только в коде
// ДО app.use(pinia) либо на сервере вне жизненного цикла запроса (SSR).
