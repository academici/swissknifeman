<!-- Source: anonymized production Laravel project (resources/js/pages/Orders/Row.vue) -->
<script setup lang="ts">
// Using generated types at the front.
// App.* — GLOBAL namespace from resources/js/types/generated.d.ts
// (declare namespace App). You do NOT need to import it - it's enough to
// generated.d.ts was included in "include" tsconfig.json.
//
// Boundary: data (App.Data.* / App.Enums.*) — this skill (typescript-transformer).
// Routes/URL — skill frontend/wayfinder (import { show } from '@/wayfinder/...').

import { computed } from 'vue';

// DTO like props: not a single field is duplicated by hand - the source of truth is in the back.
const props = defineProps<{
  order: App.Data.Order.OrderListItem;
}>();

// enum as type: TS will check whether a literal belongs to a value set.
const isPayable = computed<boolean>(() => {
  const payable: App.Enums.Order.OrderStatus[] = ['draft', 'pending'];
  return payable.includes(props.order.status);
});

// Mapping enum -> signature for UI. Record by union gives a comprehensive check:
// add case on the back, regenerate the types - TS will highlight the missing key.
const statusLabels: Record<App.Enums.Order.OrderStatus, string> = {
  draft: 'Draft',
  pending: 'Awaiting payment',
  paid: 'Paid',
  cancelled: 'Canceled',
};

const statusLabel = computed<string>(() => statusLabels[props.order.status]);
</script>

<template>
  <article class="order-row">
    <span class="order-row__number">{{ order.number ?? '—' }}</span>
    <span class="order-row__status">{{ statusLabel }}</span>
    <span v-if="order.customer">{{ order.customer.name }}</span>
    <button :disabled="!isPayable">Pay</button>
  </article>
</template>
