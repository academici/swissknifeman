// Reference spec Vue-component: mount + createTestingPinia + async/await flushPromises + emits.
// The location mirrors the source:
//   components/cart/CartSummary.vue -> tests/components/cart/CartSummary.spec.ts
//
// Covers the practices of this skill:
//   - mount (not shallowMount) — render the actual markup for the user script;
//   - createTestingPinia — isolated side, actions are stabilized (stubActions);
//   - data-testid — stable selectors, independent of classes/structures;
//   - flushPromises + nextTick — correct expectation async-updates DOM;
//   - emitted() — checking the contract outward (events up).

import { mount, flushPromises } from '@vue/test-utils';
import { createTestingPinia } from '@pinia/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CartSummary from '@/components/cart/CartSummary.vue';
import { useCartStore } from '@/stores/cart';

// Mount Helper: Single Point of Configuration plugins/stubs, so that tests are not repeated boilerplate.
function mountSummary(initialState?: Record<string, unknown>) {
    const wrapper = mount(CartSummary, {
        global: {
            plugins: [
                createTestingPinia({
                    // stubActions: false — let the store's actions actually take place
                    // (default true: actions are mocked and only calls are recorded).
                    stubActions: false,
                    createSpy: vi.fn,
                    initialState: { cart: initialState ?? {} },
                }),
            ],
            // Jamming the heavy one/external child: testing CartSummary, and not its child component.
            stubs: { PaymentIcon: true },
        },
    });

    return { wrapper, store: useCartStore() };
}

describe('CartSummary', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('shows the total from the store', () => {
        const { wrapper } = mountSummary({ items: [{ id: 1, price: 100, qty: 2 }] });

        // Robust selector by data-testid, and not by text/class.
        expect(wrapper.get('[data-testid="cart-total"]').text()).toBe('200');
    });

    it('issue checkout with amount on click', async () => {
        const { wrapper } = mountSummary({ items: [{ id: 1, price: 100, qty: 1 }] });

        await wrapper.get('[data-testid="checkout-btn"]').trigger('click');

        // Checking the contract outside: the event and its payload.
        const events = wrapper.emitted('checkout');
        expect(events).toHaveLength(1);
        expect(events?.[0]).toEqual([{ total: 100 }]);
    });

    it('pulls up the discount through async-action store and updates DOM', async () => {
        const { wrapper, store } = mountSummary({ items: [{ id: 1, price: 100, qty: 1 }] });

        // stubActions:false — real actions are performed; we precisely replace ONLY the action
        // at the border I/O (fetchDiscount: HTTP-request), so as not to go online. Business logic
        // applyPromo (recalculation total with discount) is performed for real.
        vi.spyOn(store, 'fetchDiscount').mockResolvedValue(10);

        await wrapper.get('[data-testid="apply-promo"]').trigger('click');
        await flushPromises(); // wait for the promise to resolve in action
        // nextTick is implicitly included in flushPromises; is clearly needed if DOM changes
        // strictly in the next tick after a synchronous change in the reactive state.

        expect(wrapper.get('[data-testid="cart-total"]').text()).toBe('90');
    });
});
