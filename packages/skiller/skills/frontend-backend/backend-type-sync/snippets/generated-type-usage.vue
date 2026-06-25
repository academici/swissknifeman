<!-- Source: anonymized production Laravel project (resources/js/pages/Orders/Row.vue) -->
<script setup lang="ts">
// Использование сгенерированных типов на фронте.
// App.* — ГЛОБАЛЬНЫЙ неймспейс из resources/js/types/generated.d.ts
// (declare namespace App). Импортировать его НЕ нужно — достаточно, чтобы
// generated.d.ts входил в "include" tsconfig.json.
//
// Граница: данные (App.Data.* / App.Enums.*) — этот скилл (typescript-transformer).
// Роуты/URL — скилл frontend/wayfinder (import { show } from '@/wayfinder/...').

import { computed } from 'vue';

// DTO как пропсы: ни одно поле не продублировано руками — источник правды на бэке.
const props = defineProps<{
  order: App.Data.Order.OrderListItem;
}>();

// enum как тип: TS проверит принадлежность литерала множеству значений.
const isPayable = computed<boolean>(() => {
  const payable: App.Enums.Order.OrderStatus[] = ['draft', 'pending'];
  return payable.includes(props.order.status);
});

// Маппинг enum -> подпись для UI. Record по union даёт исчерпывающую проверку:
// добавишь case на бэке, перегенерируешь типы — TS подсветит недостающий ключ.
const statusLabels: Record<App.Enums.Order.OrderStatus, string> = {
  draft: 'Черновик',
  pending: 'Ожидает оплаты',
  paid: 'Оплачен',
  cancelled: 'Отменён',
};

const statusLabel = computed<string>(() => statusLabels[props.order.status]);
</script>

<template>
  <article class="order-row">
    <span class="order-row__number">{{ order.number ?? '—' }}</span>
    <span class="order-row__status">{{ statusLabel }}</span>
    <span v-if="order.customer">{{ order.customer.name }}</span>
    <button :disabled="!isPayable">Оплатить</button>
  </article>
</template>
