// Эталонный спек Vue-компонента: mount + createTestingPinia + async/await flushPromises + emits.
// Расположение зеркалит исходник:
//   components/cart/CartSummary.vue -> tests/components/cart/CartSummary.spec.ts
//
// Покрывает практики этого скилла:
//   - mount (не shallowMount) — рендерим реальную разметку для пользовательского сценария;
//   - createTestingPinia — изолированный стор, действия застаблены (stubActions);
//   - data-testid — устойчивые селекторы, не зависят от классов/структуры;
//   - flushPromises + nextTick — корректное ожидание async-обновлений DOM;
//   - emitted() — проверка контракта наружу (события вверх).

import { mount, flushPromises } from '@vue/test-utils';
import { createTestingPinia } from '@pinia/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CartSummary from '@/components/cart/CartSummary.vue';
import { useCartStore } from '@/stores/cart';

// Хелпер монтирования: единая точка настройки plugins/stubs, чтобы тесты не повторяли boilerplate.
function mountSummary(initialState?: Record<string, unknown>) {
    const wrapper = mount(CartSummary, {
        global: {
            plugins: [
                createTestingPinia({
                    // stubActions: false — даём действиям стора реально выполниться
                    // (по умолчанию true: действия мокаются и только фиксируются вызовы).
                    stubActions: false,
                    createSpy: vi.fn,
                    initialState: { cart: initialState ?? {} },
                }),
            ],
            // Глушим тяжёлого/внешнего ребёнка: тестируем CartSummary, а не его дочерний компонент.
            stubs: { PaymentIcon: true },
        },
    });

    return { wrapper, store: useCartStore() };
}

describe('CartSummary', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('показывает итоговую сумму из стора', () => {
        const { wrapper } = mountSummary({ items: [{ id: 1, price: 100, qty: 2 }] });

        // Устойчивый селектор по data-testid, а не по тексту/классу.
        expect(wrapper.get('[data-testid="cart-total"]').text()).toBe('200');
    });

    it('эмитит checkout с суммой при клике', async () => {
        const { wrapper } = mountSummary({ items: [{ id: 1, price: 100, qty: 1 }] });

        await wrapper.get('[data-testid="checkout-btn"]').trigger('click');

        // Проверяем контракт наружу: событие и его payload.
        const events = wrapper.emitted('checkout');
        expect(events).toHaveLength(1);
        expect(events?.[0]).toEqual([{ total: 100 }]);
    });

    it('подтягивает скидку через async-действие стора и обновляет DOM', async () => {
        const { wrapper, store } = mountSummary({ items: [{ id: 1, price: 100, qty: 1 }] });

        // stubActions:false — реальные действия выполняются; точечно подменяем ТОЛЬКО действие
        // на границе I/O (fetchDiscount: HTTP-запрос), чтобы не ходить в сеть. Бизнес-логика
        // applyPromo (пересчёт total со скидкой) при этом исполняется по-настоящему.
        vi.spyOn(store, 'fetchDiscount').mockResolvedValue(10);

        await wrapper.get('[data-testid="apply-promo"]').trigger('click');
        await flushPromises(); // дожидаемся резолва промиса в действии
        // nextTick неявно входит во flushPromises; явно нужен, если DOM меняется
        // строго в следующем тике после синхронного изменения реактивного состояния.

        expect(wrapper.get('[data-testid="cart-total"]').text()).toBe('90');
    });
});
